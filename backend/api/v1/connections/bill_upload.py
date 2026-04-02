"""
Bill upload and OCR parsing endpoints.

Routes (mounted under the /connections prefix in router.py):
  POST /upload                                           — create a manual-upload connection stub
  POST /{connection_id}/upload                          — upload a bill file for parsing
  GET  /{connection_id}/uploads                         — list bill uploads for a connection
  GET  /{connection_id}/uploads/{upload_id}             — get a single upload's parse status
  POST /{connection_id}/uploads/{upload_id}/reparse     — re-trigger bill parsing

Also contains the background task helper ``_run_background_parse``.

Patching note:
  Tests patch ``api.v1.connections._UPLOADS_DIR`` and
  ``api.v1.connections._run_background_parse``.  Route handlers access both
  symbols via ``import api.v1.connections as _pkg`` inside each function body
  so the patch on the package namespace is observed at call time.  This lazy
  import is safe because by the time any request handler runs, the package is
  fully initialised.
"""

import asyncio
import uuid
from uuid import uuid4

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import SessionData, get_db_session
from api.v1.connections.common import require_paid_tier
from models.connections import (
    BillUploadListResponse,
    BillUploadResponse,
    ConnectionResponse,
    CreateUploadConnectionRequest,
)
from services.bill_parser import (
    MAX_FILE_SIZE_BYTES,
    BillParserService,
    build_storage_key,
    validate_upload_file,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Background helper
# ---------------------------------------------------------------------------


async def _run_background_parse(
    upload_id: str,
    connection_id: str,
    storage_key: str,
) -> None:
    """Background task: acquire a fresh DB session and run the bill parser."""
    # Import the package here (not at module level) to avoid circular imports.
    # The _UPLOADS_DIR used here is retrieved from the package at call time so
    # that ``patch("api.v1.connections._UPLOADS_DIR", ...)`` in tests is observed.
    import api.v1.connections as _pkg
    from api.dependencies import get_db_session as _get_db

    uploads_dir = _pkg._UPLOADS_DIR

    try:
        # get_db_session is an async generator — iterate it manually
        gen = _get_db()
        db: AsyncSession = await gen.__anext__()
        try:
            parser = BillParserService(db=db, uploads_dir=uploads_dir)
            await parser.parse(
                upload_id=upload_id,
                connection_id=connection_id,
                storage_key=storage_key,
            )
        finally:
            try:
                await gen.aclose()
            except Exception:
                pass
    except Exception as exc:
        logger.error(
            "background_parse_error",
            upload_id=upload_id,
            error=str(exc),
        )
        # Mark the upload as failed so the frontend stops polling.
        # This handles cases where DB session acquisition or other outer
        # errors prevent parser.parse() from ever running.
        try:
            from api.dependencies import get_db_session as _get_db_fallback

            gen_fb = _get_db_fallback()
            db_fb: AsyncSession = await gen_fb.__anext__()
            try:
                await db_fb.execute(
                    text("""
                        UPDATE bill_uploads
                        SET parse_status = 'failed',
                            parse_error  = :error,
                            updated_at   = NOW()
                        WHERE id = :uid AND parse_status = 'pending'
                    """),
                    {
                        "uid": upload_id,
                        "error": f"Background processing failed: {exc}",
                    },
                )
                await db_fb.commit()
            finally:
                try:
                    await gen_fb.aclose()
                except Exception:
                    pass
        except Exception as inner_exc:
            logger.error(
                "background_parse_failsafe_error",
                upload_id=upload_id,
                error=str(inner_exc),
            )


# ---------------------------------------------------------------------------
# POST /upload  —  create a manual-upload connection stub
# ---------------------------------------------------------------------------


@router.post(
    "/upload",
    response_model=ConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create upload connection stub",
)
async def create_upload_connection(
    payload: CreateUploadConnectionRequest,
    current_user: SessionData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> ConnectionResponse:
    """Create a manual-upload connection stub; actual file upload is separate."""
    connection_id = str(uuid4())

    await db.execute(
        text("""
            INSERT INTO user_connections
                (id, user_id, connection_type, label, status, created_at)
            VALUES
                (:id, :uid, 'manual_upload', :label, 'active', NOW())
        """),
        {
            "id": connection_id,
            "uid": current_user.user_id,
            "label": payload.label,
        },
    )
    await db.commit()

    return ConnectionResponse(
        id=connection_id,
        user_id=current_user.user_id,
        connection_type="manual_upload",
        status="active",
        label=payload.label,
    )


# ---------------------------------------------------------------------------
# POST /{connection_id}/upload  —  upload a bill file
# ---------------------------------------------------------------------------


@router.post(
    "/{connection_id}/upload",
    response_model=BillUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a utility bill file for parsing",
)
async def upload_bill_file(
    connection_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: SessionData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> BillUploadResponse:
    """
    Accept a PDF, PNG, or JPEG bill file, store it locally, create a
    ``bill_uploads`` record, and schedule background parsing.

    Returns the upload record with ``parse_status="pending"``; the client
    should poll ``GET /{connection_id}/uploads/{upload_id}`` for completion.

    Validation:
    - File extension must be .pdf, .png, .jpg, or .jpeg
    - Content-Type must match the extension
    - Magic bytes are checked to prevent MIME-type spoofing
    - File size must not exceed 10 MB
    """
    # Resolve _UPLOADS_DIR and _run_background_parse through the package so that
    # test patches on ``api.v1.connections._UPLOADS_DIR`` and
    # ``api.v1.connections._run_background_parse`` are observed at call time.
    import api.v1.connections as _pkg

    uploads_dir = _pkg._UPLOADS_DIR
    background_parse_fn = _pkg._run_background_parse

    log = logger.bind(
        connection_id=connection_id,
        user_id=current_user.user_id,
        filename=file.filename,
    )

    # Verify the connection belongs to the current user
    conn_result = await db.execute(
        text("SELECT id FROM user_connections WHERE id = :cid AND user_id = :uid"),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    if conn_result.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    # Read file content (bounded by RequestBodySizeLimitMiddleware at 10 MB)
    data = await file.read()

    # Size guard (belt-and-suspenders in addition to middleware)
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
        )

    if len(data) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # Validate file type via extension, MIME type, and magic bytes
    content_type = file.content_type or ""
    filename = file.filename or "upload.bin"

    try:
        file_type = validate_upload_file(filename, content_type, data)
    except ValueError as exc:
        log.warning("bill_upload_validation_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Please upload a PDF, PNG, or JPEG file.",
        ) from exc

    # Generate IDs and storage path
    upload_id = str(uuid4())
    storage_key = build_storage_key(str(connection_id), upload_id, filename)
    dest = uploads_dir / storage_key

    # Persist file to local storage (async to avoid blocking the event loop)
    try:
        await asyncio.to_thread(dest.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(dest.write_bytes, data)
    except OSError as exc:
        log.error("bill_upload_storage_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store uploaded file.",
        ) from exc

    # Insert bill_uploads record
    await db.execute(
        text("""
            INSERT INTO bill_uploads
                (id, connection_id, user_id, file_name, file_type,
                 file_size_bytes, storage_key, parse_status, created_at, updated_at)
            VALUES
                (:id, :connection_id, :user_id, :file_name, :file_type,
                 :file_size_bytes, :storage_key, 'pending', NOW(), NOW())
        """),
        {
            "id": upload_id,
            "connection_id": connection_id,
            "user_id": current_user.user_id,
            "file_name": filename,
            "file_type": file_type,
            "file_size_bytes": len(data),
            "storage_key": storage_key,
        },
    )
    await db.commit()

    log.info("bill_upload_created", upload_id=upload_id, file_type=file_type, bytes=len(data))

    # Schedule background parse (fire-and-forget; status queryable via GET)
    cid_str = str(connection_id)
    background_tasks.add_task(
        background_parse_fn,
        upload_id=upload_id,
        connection_id=cid_str,
        storage_key=storage_key,
    )

    return BillUploadResponse(
        id=upload_id,
        connection_id=cid_str,
        file_name=filename,
        file_type=file_type,
        file_size_bytes=len(data),
        parse_status="pending",
    )


# ---------------------------------------------------------------------------
# GET /{connection_id}/uploads  —  list bill uploads
# ---------------------------------------------------------------------------


@router.get(
    "/{connection_id}/uploads",
    response_model=BillUploadListResponse,
    summary="List bill uploads for a connection",
)
async def list_bill_uploads(
    connection_id: uuid.UUID,
    current_user: SessionData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> BillUploadListResponse:
    """Return all bill uploads for the given connection (scoped to current user)."""
    conn_result = await db.execute(
        text("SELECT id FROM user_connections WHERE id = :cid AND user_id = :uid"),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    if conn_result.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    result = await db.execute(
        text("""
            SELECT id, connection_id, file_name, file_type, file_size_bytes,
                   parse_status, detected_supplier, detected_rate_per_kwh,
                   detected_billing_period_start, detected_billing_period_end,
                   detected_total_kwh, detected_total_amount,
                   parse_error, created_at
            FROM bill_uploads
            WHERE connection_id = :cid
            ORDER BY created_at DESC
        """),
        {"cid": connection_id},
    )
    rows = result.mappings().all()

    uploads = []
    for row in rows:
        row_dict = dict(row)
        # Cast date columns to ISO string (may be date or str depending on driver)
        for date_col in ("detected_billing_period_start", "detected_billing_period_end"):
            val = row_dict.get(date_col)
            if val is not None and not isinstance(val, str):
                row_dict[date_col] = str(val)
        # Cast Decimal to float
        for num_col in ("detected_rate_per_kwh", "detected_total_kwh", "detected_total_amount"):
            val = row_dict.get(num_col)
            if val is not None:
                row_dict[num_col] = float(val)
        uploads.append(BillUploadResponse(**row_dict))

    return BillUploadListResponse(uploads=uploads, total=len(uploads))


# ---------------------------------------------------------------------------
# GET /{connection_id}/uploads/{upload_id}  —  single upload status
# ---------------------------------------------------------------------------


@router.get(
    "/{connection_id}/uploads/{upload_id}",
    response_model=BillUploadResponse,
    summary="Get single bill upload status",
)
async def get_bill_upload(
    connection_id: uuid.UUID,
    upload_id: uuid.UUID,
    current_user: SessionData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> BillUploadResponse:
    """Return a single bill upload record (for polling parse status)."""
    result = await db.execute(
        text("""
            SELECT bu.id, bu.connection_id, bu.file_name, bu.file_type,
                   bu.file_size_bytes, bu.parse_status, bu.detected_supplier,
                   bu.detected_rate_per_kwh, bu.detected_billing_period_start,
                   bu.detected_billing_period_end, bu.detected_total_kwh,
                   bu.detected_total_amount, bu.parse_error, bu.created_at
            FROM bill_uploads bu
            JOIN user_connections uc ON bu.connection_id = uc.id
            WHERE bu.id = :uid AND bu.connection_id = :cid AND uc.user_id = :user_id
        """),
        {"uid": upload_id, "cid": connection_id, "user_id": current_user.user_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Upload not found")

    row_dict = dict(row)
    # Cast date fields to string for Pydantic
    for date_col in ("detected_billing_period_start", "detected_billing_period_end"):
        val = row_dict.get(date_col)
        if val is not None:
            row_dict[date_col] = str(val)
    # Cast Decimal fields to float
    for num_col in ("detected_rate_per_kwh", "detected_total_kwh", "detected_total_amount"):
        val = row_dict.get(num_col)
        if val is not None:
            row_dict[num_col] = float(val)
    return BillUploadResponse(**row_dict)


# ---------------------------------------------------------------------------
# POST /{connection_id}/uploads/{upload_id}/reparse
# ---------------------------------------------------------------------------


@router.post(
    "/{connection_id}/uploads/{upload_id}/reparse",
    response_model=BillUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-trigger bill parsing for an upload",
)
async def reparse_bill_upload(
    connection_id: uuid.UUID,
    upload_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: SessionData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> BillUploadResponse:
    """
    Reset a bill upload's parse_status to 'pending' and schedule a fresh parse.

    Useful when:
    - The initial parse failed and the issue has been corrected.
    - Parser logic has been improved and historical bills need reprocessing.
    """
    # Resolve _run_background_parse through the package namespace so test patches
    # on ``api.v1.connections._run_background_parse`` are observed at call time.
    import api.v1.connections as _pkg

    background_parse_fn = _pkg._run_background_parse

    # Verify connection ownership
    conn_result = await db.execute(
        text("SELECT id FROM user_connections WHERE id = :cid AND user_id = :uid"),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    if conn_result.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    # Fetch the upload record (must belong to this connection)
    upload_result = await db.execute(
        text("""
            SELECT id, connection_id, file_name, file_type, file_size_bytes,
                   storage_key, parse_status, detected_supplier, detected_rate_per_kwh,
                   detected_billing_period_start, detected_billing_period_end,
                   detected_total_kwh, detected_total_amount,
                   parse_error, created_at
            FROM bill_uploads
            WHERE id = :upload_id AND connection_id = :cid
        """),
        {"upload_id": upload_id, "cid": connection_id},
    )
    row = upload_result.mappings().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found.",
        )

    storage_key = row["storage_key"]

    # Reset parse_status to pending
    await db.execute(
        text("""
            UPDATE bill_uploads
            SET parse_status = 'pending',
                parse_error  = NULL,
                parsed_at    = NULL,
                updated_at   = NOW()
            WHERE id = :upload_id
        """),
        {"upload_id": upload_id},
    )
    await db.commit()

    cid_str = str(connection_id)
    logger.info("bill_reparse_scheduled", upload_id=upload_id, connection_id=cid_str)

    # Schedule background parse
    background_tasks.add_task(
        background_parse_fn,
        upload_id=str(upload_id),
        connection_id=cid_str,
        storage_key=storage_key,
    )

    return BillUploadResponse(
        id=str(upload_id),
        connection_id=cid_str,
        file_name=row["file_name"],
        file_type=row["file_type"],
        file_size_bytes=row["file_size_bytes"],
        parse_status="pending",
        created_at=row["created_at"],
    )
