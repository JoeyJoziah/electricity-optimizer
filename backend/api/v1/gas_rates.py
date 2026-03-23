"""
Gas Rate API Endpoints

Public endpoints for natural gas price data: current rates, history,
deregulated states, and supplier comparison.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from models.region import DEREGULATED_GAS_STATES
from models.utility import UNIT_LABELS, PriceUnit
from services.gas_rate_service import GasRateService

router = APIRouter(tags=["Gas Rates"])


@router.get("/")
async def get_gas_rates(
    region: str = Query(..., description="Region code (e.g. us_ct)"),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
):
    """Get latest natural gas prices for a region."""
    service = GasRateService(db=db)
    prices = await service.get_gas_prices(region=region, limit=limit)

    state_code = region.replace("us_", "").upper() if region.startswith("us_") else None
    is_deregulated = state_code in DEREGULATED_GAS_STATES if state_code else False

    return {
        "region": region,
        "utility_type": "natural_gas",
        "unit": UNIT_LABELS[PriceUnit.THERM],
        "is_deregulated": is_deregulated,
        "count": len(prices),
        "prices": [
            {
                "id": p.id,
                "supplier": p.supplier,
                "price": str(p.price_per_kwh),
                "unit": UNIT_LABELS.get(PriceUnit(p.unit), "$/therm") if p.unit else "$/therm",
                "timestamp": p.timestamp.isoformat(),
                "source": p.source_api,
            }
            for p in prices
        ],
    }


@router.get("/history")
async def get_gas_price_history(
    region: str = Query(..., description="Region code (e.g. us_ct)"),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db_session),
):
    """Get gas price history for a region."""
    service = GasRateService(db=db)
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=days)

    prices = await service.get_gas_price_history(
        region=region,
        start_date=start_date,
        end_date=end_date,
    )

    return {
        "region": region,
        "utility_type": "natural_gas",
        "period_days": days,
        "count": len(prices),
        "prices": [
            {
                "price": str(p.price_per_kwh),
                "timestamp": p.timestamp.isoformat(),
                "supplier": p.supplier,
            }
            for p in prices
        ],
    }


@router.get("/stats")
async def get_gas_stats(
    region: str = Query(..., description="Region code (e.g. us_ct)"),
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db_session),
):
    """Get gas price statistics for a region."""
    service = GasRateService(db=db)
    stats = await service.get_gas_stats(region=region, days=days)
    return {
        "region": region,
        "utility_type": "natural_gas",
        "unit": UNIT_LABELS[PriceUnit.THERM],
        **stats,
    }


@router.get("/deregulated-states")
async def get_deregulated_gas_states(
    db: AsyncSession = Depends(get_db_session),
):
    """Get list of states with deregulated natural gas markets."""
    service = GasRateService(db=db)
    states = await service.get_deregulated_states()
    return {
        "count": len(states),
        "states": states,
    }


@router.get("/compare")
async def compare_gas_suppliers(
    region: str = Query(..., description="Region code (e.g. us_ct)"),
    db: AsyncSession = Depends(get_db_session),
):
    """Compare gas suppliers in a region (deregulated states only)."""
    state_code = region.replace("us_", "").upper() if region.startswith("us_") else None
    if not state_code or state_code not in DEREGULATED_GAS_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"Gas supplier comparison only available for deregulated states: {sorted(DEREGULATED_GAS_STATES)}",
        )

    service = GasRateService(db=db)
    prices = await service.get_gas_prices(region=region, limit=50)

    if not prices:
        return {
            "region": region,
            "is_deregulated": True,
            "suppliers": [],
            "message": "No gas rate data available yet. Rates are fetched weekly from EIA.",
        }

    # Group by supplier, take latest per supplier
    by_supplier: dict = {}
    for p in prices:
        if p.supplier not in by_supplier:
            by_supplier[p.supplier] = p

    sorted_suppliers = sorted(by_supplier.values(), key=lambda p: p.price_per_kwh)

    return {
        "region": region,
        "is_deregulated": True,
        "unit": UNIT_LABELS[PriceUnit.THERM],
        "suppliers": [
            {
                "supplier": p.supplier,
                "price": str(p.price_per_kwh),
                "timestamp": p.timestamp.isoformat(),
                "source": p.source_api,
            }
            for p in sorted_suppliers
        ],
        "cheapest": sorted_suppliers[0].supplier if sorted_suppliers else None,
    }
