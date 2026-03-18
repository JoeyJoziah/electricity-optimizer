"""
Rate extraction and comparison endpoints.

Routes (mounted under the /connections prefix in router.py):
  GET /{connection_id}/rates            — paginated list of extracted rates for a connection
  GET /{connection_id}/rates/current    — get the single most recent extracted rate

Route ordering note: /{connection_id}/rates/current must be registered AFTER
/{connection_id}/rates but BEFORE /{connection_id} wildcard in router.py.
FastAPI matches routes in registration order; since ``/rates/current`` is a
sub-path of ``/rates`` and not a path parameter itself, the router handles
this correctly as long as the rates router is included before the generic
CRUD wildcard router.
"""

import math
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import SessionData, get_db_session
from api.v1.connections.common import require_paid_tier
from models.connections import ExtractedRateListResponse, ExtractedRateResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /{connection_id}/rates  —  paginated list of extracted rates
# ---------------------------------------------------------------------------


@router.get(
    "/{connection_id}/rates",
    response_model=ExtractedRateListResponse,
    summary="Get extracted rates for a connection",
)
async def get_rates(
    connection_id: str,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Records per page (1-100, default 20)"),
    current_user: SessionData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> ExtractedRateListResponse:
    """Return a paginated list of rates extracted for the given connection (scoped to current user).

    Runs the COUNT and data queries sequentially (shared AsyncSession) for minimal
    latency.  When the result set is empty a lightweight EXISTS check distinguishes
    "connection not found" (404) from "connection exists but has no rates" (200,
    empty page).

    Pagination parameters:
    - ``page``: 1-based page number (default 1)
    - ``page_size``: records per page, 1–100 (default 20)

    Response includes ``total``, ``page``, ``page_size``, and ``pages`` so
    callers can navigate the full dataset without fetching all records at once.
    """
    # Clamp server-side as defence-in-depth even though FastAPI ge/le enforces it.
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size

    params = {"cid": connection_id, "uid": current_user.user_id}

    count_query = text("""
        SELECT COUNT(*)
        FROM connection_extracted_rates cer
        JOIN user_connections uc ON cer.connection_id = uc.id
        WHERE cer.connection_id = :cid
          AND uc.user_id = :uid
    """)

    data_query = text("""
        SELECT cer.id, cer.connection_id, cer.rate_per_kwh,
               cer.effective_date, cer.source, cer.raw_label
        FROM connection_extracted_rates cer
        JOIN user_connections uc ON cer.connection_id = uc.id
        WHERE cer.connection_id = :cid
          AND uc.user_id = :uid
        ORDER BY cer.effective_date DESC
        LIMIT :limit OFFSET :offset
    """)

    # Sequential execution — asyncio.gather on a shared AsyncSession
    # can corrupt internal state (see SA docs on session concurrency)
    count_result = await db.execute(count_query, params)
    data_result = await db.execute(data_query, {**params, "limit": page_size, "offset": offset})

    total: int = count_result.scalar() or 0
    rows = data_result.mappings().all()

    # When no rows and total is 0 we cannot distinguish "connection not found"
    # from "no rates yet" purely from the JOIN.  Do a lightweight EXISTS check.
    if total == 0:
        exists = await db.execute(
            text("SELECT 1 FROM user_connections WHERE id = :cid AND user_id = :uid"),
            {"cid": connection_id, "uid": current_user.user_id},
        )
        if exists.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found.",
            )

    pages = max(1, math.ceil(total / page_size)) if total > 0 else 1

    return ExtractedRateListResponse(
        rates=[ExtractedRateResponse(**dict(row)) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# ---------------------------------------------------------------------------
# GET /{connection_id}/rates/current  —  most recent rate
# ---------------------------------------------------------------------------


@router.get(
    "/{connection_id}/rates/current",
    response_model=Optional[ExtractedRateResponse],
    summary="Get the most recent extracted rate for a connection",
)
async def get_current_rate(
    connection_id: str,
    current_user: SessionData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> Optional[ExtractedRateResponse]:
    """Return the single most recent rate extracted for this connection.

    Ownership verification and rate fetch are combined into a single JOIN query.
    A NULL result from the JOIN means either: connection not found for this user,
    or connection exists but has no rates yet.  A secondary EXISTS check
    distinguishes the two cases only when the JOIN returns nothing.
    """
    result = await db.execute(
        text("""
            SELECT cer.id, cer.connection_id, cer.rate_per_kwh,
                   cer.effective_date, cer.source, cer.raw_label
            FROM connection_extracted_rates cer
            JOIN user_connections uc ON cer.connection_id = uc.id
            WHERE cer.connection_id = :cid
              AND uc.user_id = :uid
            ORDER BY cer.effective_date DESC
            LIMIT 1
        """),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    row = result.mappings().first()
    if row is not None:
        return ExtractedRateResponse(**dict(row))

    # No rate row: determine whether the connection itself is missing (404)
    # or simply has no extracted rates yet (return null).
    exists = await db.execute(
        text("SELECT 1 FROM user_connections WHERE id = :cid AND user_id = :uid"),
        {"cid": connection_id, "uid": current_user.user_id},
    )
    if exists.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )
    return None
