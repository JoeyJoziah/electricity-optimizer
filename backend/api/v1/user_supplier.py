"""
User Supplier API Router

Endpoints for supplier selection and account linking.
All endpoints require authentication and filter by the authenticated user's ID.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from api.dependencies import get_current_user, get_db_session, TokenData
from models.user_supplier import (
    SetSupplierRequest,
    LinkAccountRequest,
    UserSupplierResponse,
    LinkedAccountResponse,
)
from utils.encryption import encrypt_field, decrypt_field, mask_account_number

import structlog

logger = structlog.get_logger()

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_supplier_by_id(db: AsyncSession, supplier_id: str) -> Optional[dict]:
    """Fetch a supplier from supplier_registry by ID."""
    result = await db.execute(
        text("""
            SELECT id, name, regions, rating, green_energy, website, is_active
            FROM supplier_registry WHERE id = :id
        """),
        {"id": supplier_id},
    )
    row = result.mappings().first()
    if not row:
        return None
    return dict(row)


async def _ensure_user_exists(db: AsyncSession, user_id: str) -> None:
    """Verify the user exists in public.users."""
    result = await db.execute(
        text("SELECT id FROM public.users WHERE id = :id"),
        {"id": user_id},
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found. Please complete onboarding first.",
        )


# ---------------------------------------------------------------------------
# PUT /user/supplier — Set current supplier
# ---------------------------------------------------------------------------

@router.put("/supplier", response_model=UserSupplierResponse)
async def set_current_supplier(
    body: SetSupplierRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Set the authenticated user's current supplier."""
    # Fetch user region and validate supplier in two queries (was three)
    user_result = await db.execute(
        text("SELECT id, region FROM public.users WHERE id = :id"),
        {"id": current_user.user_id},
    )
    user_row = user_result.mappings().first()
    if not user_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found. Please complete onboarding first.",
        )

    supplier_id_str = str(body.supplier_id)
    supplier = await _get_supplier_by_id(db, supplier_id_str)

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )

    if not supplier["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supplier is not currently active",
        )

    # Validate user's region is in supplier's regions
    user_region = user_row["region"]
    if user_region and list(supplier["regions"]):
        if user_region.lower() not in [r.lower() for r in supplier["regions"]]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Supplier is not available in your region ({user_region})",
            )

    # Update both current_supplier (name, backward compat) and current_supplier_id (FK)
    await db.execute(
        text("""
            UPDATE public.users
            SET current_supplier = :name,
                current_supplier_id = :supplier_id,
                updated_at = NOW()
            WHERE id = :user_id
        """),
        {
            "name": supplier["name"],
            "supplier_id": supplier_id_str,
            "user_id": current_user.user_id,
        },
    )
    await db.commit()

    logger.info("supplier_set", user_id=current_user.user_id, supplier_id=supplier_id_str)

    return UserSupplierResponse(
        supplier_id=str(supplier["id"]),
        supplier_name=supplier["name"],
        regions=list(supplier["regions"]),
        rating=float(supplier["rating"]) if supplier["rating"] else None,
        green_energy=supplier["green_energy"],
        website=supplier["website"],
    )


# ---------------------------------------------------------------------------
# GET /user/supplier — Get current supplier
# ---------------------------------------------------------------------------

@router.get("/supplier")
async def get_current_supplier(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get the authenticated user's current supplier."""
    result = await db.execute(
        text("""
            SELECT u.current_supplier_id, u.current_supplier,
                   sr.id AS sr_id, sr.name, sr.regions, sr.rating,
                   sr.green_energy, sr.website
            FROM public.users u
            LEFT JOIN supplier_registry sr ON u.current_supplier_id = sr.id
            WHERE u.id = :user_id
        """),
        {"user_id": current_user.user_id},
    )
    row = result.mappings().first()

    if not row or not row["current_supplier_id"]:
        return {"supplier": None}

    return {
        "supplier": UserSupplierResponse(
            supplier_id=str(row["sr_id"]),
            supplier_name=row["name"],
            regions=list(row["regions"]) if row["regions"] else [],
            rating=float(row["rating"]) if row["rating"] else None,
            green_energy=row["green_energy"] or False,
            website=row["website"],
        ).model_dump()
    }


# ---------------------------------------------------------------------------
# DELETE /user/supplier — Remove current supplier
# ---------------------------------------------------------------------------

@router.delete("/supplier")
async def remove_current_supplier(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Remove the authenticated user's current supplier."""
    await db.execute(
        text("""
            UPDATE public.users
            SET current_supplier = NULL,
                current_supplier_id = NULL,
                updated_at = NOW()
            WHERE id = :user_id
        """),
        {"user_id": current_user.user_id},
    )
    await db.commit()

    logger.info("supplier_removed", user_id=current_user.user_id)

    return {"message": "Supplier removed"}


# ---------------------------------------------------------------------------
# POST /user/supplier/link — Link utility account
# ---------------------------------------------------------------------------

@router.post("/supplier/link", response_model=LinkedAccountResponse)
async def link_supplier_account(
    body: LinkAccountRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Link a utility account to a supplier (stores encrypted account number)."""
    await _ensure_user_exists(db, current_user.user_id)

    supplier_id_str = str(body.supplier_id)
    supplier = await _get_supplier_by_id(db, supplier_id_str)

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )

    # Encrypt account number and optional meter number
    encrypted_account = encrypt_field(body.account_number)
    encrypted_meter = encrypt_field(body.meter_number) if body.meter_number else None

    try:
        await db.execute(
            text("""
                INSERT INTO user_supplier_accounts
                    (user_id, supplier_id, account_number_encrypted, meter_number_encrypted,
                     service_zip, account_nickname, is_primary)
                VALUES (:user_id, :supplier_id, :account_enc, :meter_enc,
                        :zip, :nickname, TRUE)
                ON CONFLICT (user_id, supplier_id)
                DO UPDATE SET
                    account_number_encrypted = EXCLUDED.account_number_encrypted,
                    meter_number_encrypted = EXCLUDED.meter_number_encrypted,
                    service_zip = EXCLUDED.service_zip,
                    account_nickname = EXCLUDED.account_nickname,
                    updated_at = NOW()
            """),
            {
                "user_id": current_user.user_id,
                "supplier_id": supplier_id_str,
                "account_enc": encrypted_account,
                "meter_enc": encrypted_meter,
                "zip": body.service_zip,
                "nickname": body.account_nickname,
            },
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error("link_account_failed", user_id=current_user.user_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to link account",
        )

    logger.info("account_linked", user_id=current_user.user_id, supplier_id=supplier_id_str)

    return LinkedAccountResponse(
        supplier_id=str(supplier["id"]),
        supplier_name=supplier["name"],
        account_number_masked=mask_account_number(body.account_number),
        meter_number_masked=mask_account_number(body.meter_number) if body.meter_number else None,
        service_zip=body.service_zip,
        account_nickname=body.account_nickname,
        is_primary=True,
        verified_at=None,
        created_at="now",
    )


# ---------------------------------------------------------------------------
# GET /user/supplier/accounts — Get linked accounts (masked)
# ---------------------------------------------------------------------------

@router.get("/supplier/accounts")
async def get_linked_accounts(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get all linked supplier accounts for the authenticated user (masked)."""
    result = await db.execute(
        text("""
            SELECT usa.supplier_id, sr.name AS supplier_name,
                   usa.account_number_encrypted, usa.meter_number_encrypted,
                   usa.service_zip, usa.account_nickname, usa.is_primary,
                   usa.verified_at, usa.created_at
            FROM user_supplier_accounts usa
            JOIN supplier_registry sr ON usa.supplier_id = sr.id
            WHERE usa.user_id = :user_id
            ORDER BY usa.is_primary DESC, usa.created_at DESC
        """),
        {"user_id": current_user.user_id},
    )

    accounts = []
    for row in result.mappings().all():
        account_masked = None
        meter_masked = None

        if row["account_number_encrypted"]:
            try:
                decrypted = decrypt_field(bytes(row["account_number_encrypted"]))
                account_masked = mask_account_number(decrypted)
            except Exception:
                account_masked = "****"

        if row["meter_number_encrypted"]:
            try:
                decrypted = decrypt_field(bytes(row["meter_number_encrypted"]))
                meter_masked = mask_account_number(decrypted)
            except Exception:
                meter_masked = "****"

        accounts.append(
            LinkedAccountResponse(
                supplier_id=str(row["supplier_id"]),
                supplier_name=row["supplier_name"],
                account_number_masked=account_masked,
                meter_number_masked=meter_masked,
                service_zip=row["service_zip"],
                account_nickname=row["account_nickname"],
                is_primary=row["is_primary"],
                verified_at=str(row["verified_at"]) if row["verified_at"] else None,
                created_at=str(row["created_at"]),
            ).model_dump()
        )

    return {"accounts": accounts}


# ---------------------------------------------------------------------------
# DELETE /user/supplier/accounts/{supplier_id} — Unlink specific account
# ---------------------------------------------------------------------------

@router.delete("/supplier/accounts/{supplier_id}")
async def unlink_supplier_account(
    supplier_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Unlink a specific supplier account."""
    result = await db.execute(
        text("""
            DELETE FROM user_supplier_accounts
            WHERE user_id = :user_id AND supplier_id = :supplier_id
            RETURNING id
        """),
        {"user_id": current_user.user_id, "supplier_id": str(supplier_id)},
    )
    deleted = result.scalar_one_or_none()
    await db.commit()

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Linked account not found",
        )

    logger.info("account_unlinked", user_id=current_user.user_id, supplier_id=str(supplier_id))

    return {"message": "Account unlinked"}
