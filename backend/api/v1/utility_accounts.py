"""
Utility Accounts API Router

CRUD endpoints for managing user utility accounts (electricity, gas, etc.).
"""

from typing import List

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import SessionData, get_current_user, get_db_session
from models.utility import UtilityType
from models.utility_account import (UtilityAccount, UtilityAccountCreate,
                                    UtilityAccountResponse,
                                    UtilityAccountUpdate)
from repositories.utility_account_repository import UtilityAccountRepository

logger = structlog.get_logger()

router = APIRouter(tags=["Utility Accounts"])


@router.get("/", response_model=List[UtilityAccountResponse])
async def list_utility_accounts(
    utility_type: str | None = None,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """List all utility accounts for the current user."""
    repo = UtilityAccountRepository(db)
    filters = {"user_id": current_user.user_id}
    if utility_type:
        filters["utility_type"] = utility_type
    accounts = await repo.list(page=1, page_size=100, **filters)
    return [UtilityAccountResponse.model_validate(a) for a in accounts]


@router.post("/", response_model=UtilityAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_utility_account(
    body: UtilityAccountCreate,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new utility account for the current user."""
    repo = UtilityAccountRepository(db)

    # Build the full model from the create payload
    account = UtilityAccount(
        user_id=current_user.user_id,
        utility_type=body.utility_type,
        region=body.region,
        provider_name=body.provider_name,
        is_primary=body.is_primary,
        metadata=body.metadata,
        # account_number encryption would happen here in a real flow
        account_number_encrypted=body.account_number.encode() if body.account_number else None,
    )

    created = await repo.create(account)
    logger.info(
        "utility_account_created",
        user_id=current_user.user_id,
        account_id=created.id,
        utility_type=body.utility_type,
    )
    return UtilityAccountResponse.model_validate(created)


@router.get("/types")
async def list_utility_types():
    """List all supported utility types."""
    return [{"value": t.value, "label": t.value.replace("_", " ").title()} for t in UtilityType]


@router.get("/{account_id}", response_model=UtilityAccountResponse)
async def get_utility_account(
    account_id: str,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get a specific utility account (must belong to current user)."""
    repo = UtilityAccountRepository(db)
    account = await repo.get_by_id(account_id)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Utility account not found"
        )
    if account.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your account")

    return UtilityAccountResponse.model_validate(account)


@router.put("/{account_id}", response_model=UtilityAccountResponse)
async def update_utility_account(
    account_id: str,
    body: UtilityAccountUpdate,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Update a utility account (must belong to current user)."""
    repo = UtilityAccountRepository(db)

    # Ownership check
    existing = await repo.get_by_id(account_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Utility account not found"
        )
    if existing.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your account")

    # Build partial update entity
    update_entity = UtilityAccount(
        id=account_id,
        user_id=current_user.user_id,
        utility_type=existing.utility_type,
        region=existing.region,
        provider_name=body.provider_name or existing.provider_name,
        is_primary=body.is_primary if body.is_primary is not None else existing.is_primary,
        metadata=body.metadata if body.metadata is not None else existing.metadata,
    )

    updated = await repo.update(account_id, update_entity)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Update failed"
        )

    logger.info("utility_account_updated", user_id=current_user.user_id, account_id=account_id)
    return UtilityAccountResponse.model_validate(updated)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_utility_account(
    account_id: str,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Delete a utility account (must belong to current user)."""
    repo = UtilityAccountRepository(db)

    # Ownership check
    existing = await repo.get_by_id(account_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Utility account not found"
        )
    if existing.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your account")

    deleted = await repo.delete(account_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Delete failed"
        )

    logger.info("utility_account_deleted", user_id=current_user.user_id, account_id=account_id)
