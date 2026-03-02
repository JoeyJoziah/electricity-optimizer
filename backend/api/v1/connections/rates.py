"""
Rate extraction and comparison endpoints.

Routes (mounted under the /connections prefix in router.py):
  GET /{connection_id}/rates            — list all extracted rates for a connection
  GET /{connection_id}/rates/current    — get the single most recent extracted rate

Route ordering note: /{connection_id}/rates/current must be registered AFTER
/{connection_id}/rates but BEFORE /{connection_id} wildcard in router.py.
FastAPI matches routes in registration order; since ``/rates/current`` is a
sub-path of ``/rates`` and not a path parameter itself, the router handles
this correctly as long as the rates router is included before the generic
CRUD wildcard router.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session, TokenData
from models.connections import ExtractedRateResponse
from api.v1.connections.common import require_paid_tier

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /{connection_id}/rates  —  list extracted rates
# ---------------------------------------------------------------------------


@router.get(
    "/{connection_id}/rates",
    response_model=List[ExtractedRateResponse],
    summary="Get extracted rates for a connection",
)
async def get_rates(
    connection_id: str,
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> List[ExtractedRateResponse]:
    """Return all rates extracted for the given connection (scoped to current user)."""
    # Verify ownership
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
            SELECT id, connection_id, rate_per_kwh, effective_date, source, raw_label
            FROM connection_extracted_rates
            WHERE connection_id = :cid
            ORDER BY effective_date DESC
        """),
        {"cid": connection_id},
    )
    rows = result.mappings().all()
    return [ExtractedRateResponse(**dict(row)) for row in rows]


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
    current_user: TokenData = Depends(require_paid_tier),
    db: AsyncSession = Depends(get_db_session),
) -> Optional[ExtractedRateResponse]:
    """Return the single most recent rate extracted for this connection."""
    # Verify ownership
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
            SELECT id, connection_id, rate_per_kwh, effective_date, source, raw_label
            FROM connection_extracted_rates
            WHERE connection_id = :cid
            ORDER BY effective_date DESC
            LIMIT 1
        """),
        {"cid": connection_id},
    )
    row = result.mappings().first()
    if row is None:
        return None
    return ExtractedRateResponse(**dict(row))
