"""
CCA (Community Choice Aggregation) endpoints.

Covers: /cca/detect, /cca/compare/{cca_id}, /cca/info/{cca_id}, /cca/programs
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from services.cca_service import CCAService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/cca", tags=["CCA"])


@router.get("/detect")
async def detect_cca(
    zip_code: str = Query(None, description="5-digit zip code"),
    state: str = Query(None, description="2-letter state code"),
    municipality: str = Query(None, description="Municipality name"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Check if a location is served by a CCA program.

    Provide zip_code for best results, or state + municipality as fallback.
    """
    if not zip_code and not (state and municipality):
        raise HTTPException(
            status_code=400,
            detail="Provide zip_code or both state and municipality",
        )

    service = CCAService(db)
    cca = await service.detect_cca(
        zip_code=zip_code,
        state=state,
        municipality=municipality,
    )

    return {
        "in_cca": cca is not None,
        "program": cca,
    }


@router.get("/compare/{cca_id}")
async def compare_cca_rate(
    cca_id: uuid.UUID,
    default_rate: float = Query(..., gt=0, description="Default utility rate in $/kWh"),
    db: AsyncSession = Depends(get_db_session),
):
    """Compare a CCA program's rate against the default utility rate."""
    service = CCAService(db)
    result = await service.compare_cca_rate(str(cca_id), default_rate)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/info/{cca_id}")
async def cca_info(
    cca_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Get full CCA program details including opt-out information."""
    service = CCAService(db)
    info = await service.get_cca_info(str(cca_id))

    if not info:
        raise HTTPException(status_code=404, detail="CCA program not found")

    return info


@router.get("/programs")
async def list_programs(
    state: str = Query(None, description="Filter by 2-letter state code"),
    db: AsyncSession = Depends(get_db_session),
):
    """List active CCA programs, optionally filtered by state."""
    service = CCAService(db)
    programs = await service.list_cca_programs(state=state)

    return {
        "count": len(programs),
        "programs": programs,
    }
