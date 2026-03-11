"""
Internal data pipeline endpoints.

Covers: /fetch-weather, /market-research, /scrape-rates, /geocode
"""

import json
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from services.data_persistence_helper import persist_batch

logger = structlog.get_logger(__name__)

router = APIRouter()

# All 51 US state/territory abbreviations for default weather fetch
_ALL_US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL",
    "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
]


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class WeatherRequest(BaseModel):
    regions: List[str] = Field(
        default_factory=list,
        description="US state abbreviations (e.g. NY, CA, TX). Empty = all 51 states",
    )


class MarketResearchRequest(BaseModel):
    regions: List[str] = Field(
        default=["NY", "CA", "TX"],
        description="Regions to scan for energy market news",
    )


class ScrapeRequest(BaseModel):
    supplier_urls: List[dict] = Field(
        default_factory=list,
        description=(
            '[{"supplier_id": "...", "url": "..."}, ...]. '
            "If empty, auto-discovers active suppliers with websites from DB."
        ),
    )


class GeocodeRequest(BaseModel):
    address: str = Field(..., description="US address to geocode")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/fetch-weather", tags=["Internal"])
async def fetch_weather_data(
    request: Optional[WeatherRequest] = None,
    db: AsyncSession = Depends(get_db_session),
):
    """Fetch current weather for US state regions.

    Budget: 1 call per region. 51 regions = 51 calls/day (5.1% of daily limit).
    Free tier: 1,000 calls/day.
    """
    from services.weather_service import WeatherService

    regions = request.regions if request and request.regions else _ALL_US_STATES
    service = WeatherService()
    results = await service.fetch_weather_for_regions(regions)

    # Persist weather data to weather_cache table
    rows = []
    for state, data in results.items():
        rows.append({
            "state": state,
            "temp": data.get("temp_f"),
            "humidity": data.get("humidity"),
            "wind": data.get("wind_mph"),
            "conditions": data.get("description"),
            "raw": json.dumps(data),
        })

    persisted = 0
    if db and rows:
        persisted = await persist_batch(
            db=db,
            table="weather_cache",
            sql="""
                INSERT INTO weather_cache
                    (state_code, temperature_f, humidity, wind_speed_mph, conditions, raw_data)
                VALUES (:state, :temp, :humidity, :wind, :conditions, :raw)
            """,
            rows=rows,
            log_context="weather_cache",
        )

    return {
        "status": "ok",
        "regions_fetched": len(results),
        "persisted": persisted,
        "data": results,
    }


@router.post("/market-research", tags=["Internal"])
async def run_market_research(
    request: MarketResearchRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Run weekly energy market intelligence scan via Tavily AI search.

    Budget: ~10 searches/week = 40/month (4% of free tier quota).
    Free tier: 1,000 credits/month.
    """
    from services.market_intelligence_service import MarketIntelligenceService

    service = MarketIntelligenceService()
    results = await service.weekly_market_scan(request.regions)

    # Flatten results into rows for batch insert
    rows = []
    if results:
        for item in results:
            query_str = item.get("query", "")
            region = query_str.split()[0] if query_str else None
            for result in item.get("data", {}).get("results", []):
                rows.append({
                    "query": query_str[:500],
                    "region": region,
                    "title": (result.get("title") or "")[:500],
                    "url": (result.get("url") or "")[:1000],
                    "content": result.get("content"),
                    "score": result.get("score"),
                    "raw": json.dumps(result),
                })

    persisted = 0
    if db and rows:
        persisted = await persist_batch(
            db=db,
            table="market_intelligence",
            sql="""
                INSERT INTO market_intelligence
                    (query, region, title, url, content, score, raw_data)
                VALUES (:query, :region, :title, :url, :content, :score, :raw)
            """,
            rows=rows,
            log_context="market_intel",
        )

    return {"status": "ok", "results": results, "persisted": persisted}


@router.post("/scrape-rates", tags=["Internal"])
async def scrape_supplier_rates(
    request: ScrapeRequest = ScrapeRequest(),
    db: AsyncSession = Depends(get_db_session),
):
    """Scrape supplier rate pages via Diffbot Extract API.

    When called with no body (or empty supplier_urls), auto-discovers active
    suppliers from the database that have a website URL.

    Each URL uses 1 Diffbot credit. Rate limited to 5 calls/min.
    Free tier: 10,000 credits/month.
    """
    from services.rate_scraper_service import RateScraperService

    supplier_urls = request.supplier_urls

    # Auto-discover suppliers with website URLs when no explicit list provided
    if not supplier_urls:
        result = await db.execute(
            text("""
                SELECT id, name, website
                FROM supplier_registry
                WHERE is_active = true
                  AND website IS NOT NULL
                  AND website != ''
                ORDER BY name
            """)
        )
        rows_db = result.fetchall()
        supplier_urls = [
            {"supplier_id": str(row[0]), "url": row[2]}
            for row in rows_db
        ]

    if not supplier_urls:
        return {"status": "ok", "results": [], "message": "No suppliers with website URLs found"}

    service = RateScraperService()
    batch = await service.scrape_supplier_rates(supplier_urls)

    # batch is now a summary dict: {total, succeeded, failed, errors, results}
    raw_results = batch.get("results", [])

    # Persist scraped rates to scraped_rates table
    persisted = 0
    if db and raw_results:
        url_lookup = {item.get("supplier_id"): item.get("url") for item in supplier_urls}
        name_lookup = {item.get("supplier_id"): item.get("name") for item in supplier_urls}

        rows = [
            {
                "sid": r.get("supplier_id"),
                "name": name_lookup.get(r.get("supplier_id")),
                "url": url_lookup.get(r.get("supplier_id")),
                "data": json.dumps(r.get("extracted_data")),
                "success": r.get("success", False),
            }
            for r in raw_results
        ]

        persisted = await persist_batch(
            db=db,
            table="scraped_rates",
            sql="""
                INSERT INTO scraped_rates (supplier_id, supplier_name, source_url, extracted_data, success)
                VALUES (:sid, :name, :url, :data, :success)
            """,
            rows=rows,
            log_context="scraped_rate",
        )

    return {
        "status": "ok",
        "total": batch["total"],
        "succeeded": batch["succeeded"],
        "failed": batch["failed"],
        "errors": batch["errors"],
        "persisted": persisted,
        "results": raw_results,
    }


@router.post("/geocode", tags=["Internal"])
async def geocode_address(request: GeocodeRequest):
    """Resolve a US address to a state/region via Google Geocoding API.

    Uses 1 geocoding credit per request. Free tier: 10,000/month.
    """
    from services.geocoding_service import GeocodingService

    service = GeocodingService()
    result = await service.geocode(request.address)
    if not result:
        raise HTTPException(status_code=404, detail="Could not geocode address")
    return {"status": "ok", "result": result}
