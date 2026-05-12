"""
Public Rate Pages API

Lightweight, cacheable endpoints for SEO-driven rate pages.
No authentication required. Returns summary data only.

Routes
------
GET /public/rates/{state}/{utility_type}  — rate summary for a state + utility
GET /public/rates/states                  — list of states with available data
"""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/public/rates", tags=["Public Rates"])


@router.get("/states", summary="States with available rate data")
async def get_available_states(
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Return list of states that have rate data for any utility type."""
    if db is None:
        return {"states": []}

    result = await db.execute(text("""
            SELECT DISTINCT region AS state, 'electricity' AS utility_type
            FROM electricity_prices
            WHERE region IS NOT NULL
            UNION
            SELECT DISTINCT region AS state, 'natural_gas' AS utility_type
            FROM utility_rates
            WHERE utility_type = 'natural_gas' AND region IS NOT NULL
            UNION
            SELECT DISTINCT state, 'heating_oil' AS utility_type
            FROM heating_oil_prices
            WHERE state IS NOT NULL
            ORDER BY state, utility_type
        """))
    rows = result.mappings().all()
    states: dict[str, list[str]] = {}
    for row in rows:
        st = row["state"]
        ut = row["utility_type"]
        states.setdefault(st, []).append(ut)

    return {"states": states}


@router.get(
    "/{state}/{utility_type}",
    summary="Rate summary for SEO page",
)
async def get_rate_summary(
    state: str,
    utility_type: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Return rate summary for a state + utility type.

    Used by ISR pages for `/rates/[state]/[utility-type]`.
    """
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    state = state.upper()

    if utility_type == "electricity":
        return await _electricity_summary(db, state)
    elif utility_type == "natural_gas":
        return await _gas_summary(db, state)
    elif utility_type == "heating_oil":
        return await _heating_oil_summary(db, state)
    else:
        raise HTTPException(status_code=404, detail="Unknown utility type")


async def _electricity_summary(db: AsyncSession, state: str) -> dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT supplier, price_per_kwh, rate_type, updated_at
            FROM electricity_prices
            WHERE region = :state
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 10
        """),
        {"state": state},
    )
    rows = result.mappings().all()
    if not rows:
        raise HTTPException(
            status_code=404, detail="No electricity data for this state"
        )

    prices = [
        {
            "supplier": r["supplier"],
            "price": float(r["price_per_kwh"]) if r["price_per_kwh"] else None,
            "rate_type": r["rate_type"],
            "updated_at": str(r["updated_at"]) if r["updated_at"] else None,
        }
        for r in rows
    ]
    avg = sum(p["price"] for p in prices if p["price"]) / max(
        sum(1 for p in prices if p["price"]), 1
    )
    return {
        "state": state,
        "utility_type": "electricity",
        "unit": "kWh",
        "average_price": round(avg, 4),
        "suppliers": prices,
        "count": len(prices),
    }


async def _gas_summary(db: AsyncSession, state: str) -> dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT supplier, price, source, fetched_at
            FROM utility_rates
            WHERE region = :state AND utility_type = 'natural_gas'
            ORDER BY fetched_at DESC NULLS LAST
            LIMIT 10
        """),
        {"state": state},
    )
    rows = result.mappings().all()
    if not rows:
        raise HTTPException(status_code=404, detail="No gas data for this state")

    prices = [
        {
            "supplier": r["supplier"],
            "price": float(r["price"]) if r["price"] else None,
            "source": r["source"],
            "updated_at": str(r["fetched_at"]) if r["fetched_at"] else None,
        }
        for r in rows
    ]
    avg = sum(p["price"] for p in prices if p["price"]) / max(
        sum(1 for p in prices if p["price"]), 1
    )
    return {
        "state": state,
        "utility_type": "natural_gas",
        "unit": "therm",
        "average_price": round(avg, 4),
        "suppliers": prices,
        "count": len(prices),
    }


async def _heating_oil_summary(db: AsyncSession, state: str) -> dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT state, price_per_gallon, source, period_date, fetched_at
            FROM heating_oil_prices
            WHERE state = :state
            ORDER BY fetched_at DESC NULLS LAST
            LIMIT 5
        """),
        {"state": state},
    )
    rows = result.mappings().all()
    if not rows:
        raise HTTPException(
            status_code=404, detail="No heating oil data for this state"
        )

    prices = [
        {
            "price": float(r["price_per_gallon"]) if r["price_per_gallon"] else None,
            "source": r["source"],
            "period_date": str(r["period_date"]) if r["period_date"] else None,
            "updated_at": str(r["fetched_at"]) if r["fetched_at"] else None,
        }
        for r in rows
    ]
    latest = prices[0]["price"] if prices and prices[0]["price"] else None
    return {
        "state": state,
        "utility_type": "heating_oil",
        "unit": "gallon",
        "average_price": latest,
        "prices": prices,
        "count": len(prices),
    }
