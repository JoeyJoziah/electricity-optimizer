"""
Internal data pipeline endpoints.

Covers: /fetch-weather, /market-research, /scrape-rates, /geocode
"""

import json
import re

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from services.data_persistence_helper import persist_batch

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Rate extraction helpers
# ---------------------------------------------------------------------------


def _extract_rate_from_diffbot_data(extracted_data: dict) -> float | None:
    """Extract rate_per_kwh from Diffbot extracted data if possible.

    Searches for electricity rate patterns in the text content returned by
    Diffbot's Extract API.  Returns the first matched float value in $/kWh, or
    None when no pattern is found.

    Parameters
    ----------
    extracted_data:
        The ``extracted_data`` dict from a Diffbot scrape result.  May contain
        a top-level ``"text"`` key or an ``"objects"`` list where each object
        has a ``"text"`` field.

    Returns
    -------
    float | None
        Parsed rate in $/kWh, or None if no rate pattern was detected.
    """
    if not extracted_data:
        return None

    # Prefer the top-level text field; fall back to concatenating object texts.
    text_content: str = extracted_data.get("text", "") or ""
    if not text_content and isinstance(extracted_data.get("objects"), list):
        text_content = " ".join(
            obj.get("text", "") for obj in extracted_data["objects"] if obj.get("text")
        )

    if not text_content:
        return None

    rate_match = re.search(
        r"(?:rate|price|cost|charge)[:\s]*\$?([\d]+\.[\d]{2,4})\s*(?:/\s*)?(?:per\s+)?(?:kWh|kwh|KWH)",
        text_content,
        re.IGNORECASE,
    )
    if rate_match:
        try:
            return float(rate_match.group(1))
        except ValueError:
            return None
    return None


# All 51 US state/territory abbreviations for default weather fetch
_ALL_US_STATES = [
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "DC",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
]


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class WeatherRequest(BaseModel):
    regions: list[str] = Field(
        default_factory=list,
        description="US state abbreviations (e.g. NY, CA, TX). Empty = all 51 states",
    )


class MarketResearchRequest(BaseModel):
    regions: list[str] = Field(
        default=["NY", "CA", "TX"],
        description="Regions to scan for energy market news",
    )


class ScrapeRequest(BaseModel):
    supplier_urls: list[dict] = Field(
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
    request: WeatherRequest | None = None,
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
        rows.append(
            {
                "state": state,
                "temp": data.get("temp_f"),
                "humidity": data.get("humidity"),
                "wind": data.get("wind_mph"),
                "conditions": data.get("description"),
                "raw": json.dumps(data),
            }
        )

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
                rows.append(
                    {
                        "query": query_str[:500],
                        "region": region,
                        "title": (result.get("title") or "")[:500],
                        "url": (result.get("url") or "")[:1000],
                        "content": result.get("content"),
                        "score": result.get("score"),
                        "raw": json.dumps(result),
                    }
                )

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
        supplier_urls = [{"supplier_id": str(row[0]), "url": row[2]} for row in rows_db]

    if not supplier_urls:
        return {"status": "ok", "results": [], "message": "No suppliers with website URLs found"}

    service = RateScraperService()
    batch = await service.scrape_supplier_rates(supplier_urls)

    # batch is now a summary dict: {total, succeeded, failed, errors, results}
    raw_results = batch.get("results", [])

    # Persist scraped rates to scraped_rates table
    persisted = 0
    rows: list[dict] = []
    if db and raw_results:
        url_lookup = {item.get("supplier_id"): item.get("url") for item in supplier_urls}
        name_lookup = {item.get("supplier_id"): item.get("name") for item in supplier_urls}

        for r in raw_results:
            extracted_data = r.get("extracted_data") or {}
            extracted_rate = _extract_rate_from_diffbot_data(extracted_data)

            # Embed the detected rate back into extracted_data so it is
            # preserved in the JSONB column even without a dedicated column.
            if extracted_rate is not None and isinstance(extracted_data, dict):
                extracted_data = {**extracted_data, "_detected_rate_kwh": extracted_rate}

            rows.append(
                {
                    "sid": r.get("supplier_id"),
                    "name": name_lookup.get(r.get("supplier_id")),
                    "url": url_lookup.get(r.get("supplier_id")),
                    "data": json.dumps(extracted_data),
                    "success": r.get("success", False),
                    "rate": extracted_rate,
                }
            )

        if rows:
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

    rates_found = sum(1 for row in rows if row.get("rate") is not None)
    if rates_found:
        logger.info("scrape_rates_extracted", rates_found=rates_found)

    return {
        "status": "ok",
        "total": batch["total"],
        "succeeded": batch["succeeded"],
        "failed": batch["failed"],
        "errors": batch["errors"],
        "persisted": persisted,
        "rates_found": rates_found,
        "results": raw_results,
    }


@router.post("/fetch-gas-rates", tags=["Internal"])
async def fetch_gas_rates(
    db: AsyncSession = Depends(get_db_session),
):
    """Fetch natural gas rates from EIA for all deregulated states.

    Called by fetch-gas-rates.yml GHA cron (weekly).
    Stores prices in electricity_prices with utility_type=NATURAL_GAS.
    """
    from config.settings import get_settings
    from integrations.pricing_apis.eia import EIAClient
    from services.gas_rate_service import GasRateService

    settings = get_settings()
    if not settings.eia_api_key:
        raise HTTPException(status_code=503, detail="EIA API key not configured")

    async with EIAClient(api_key=settings.eia_api_key) as eia_client:
        service = GasRateService(db=db, eia_client=eia_client)
        result = await service.fetch_gas_rates()

    await db.commit()
    return result


@router.post("/fetch-heating-oil", tags=["Internal"])
async def fetch_heating_oil_prices(
    db: AsyncSession = Depends(get_db_session),
):
    """Fetch weekly heating oil prices from EIA for Northeast states + national avg.

    Called by fetch-heating-oil.yml GHA cron (weekly Monday).
    Stores prices in heating_oil_prices table.
    """
    from config.settings import get_settings
    from integrations.pricing_apis.eia import (
        HEATING_OIL_SERIES,
        HEATING_OIL_STATE_SERIES,
        EIAClient,
    )
    from services.heating_oil_service import HeatingOilService

    app_settings = get_settings()
    if not app_settings.eia_api_key:
        raise HTTPException(status_code=503, detail="EIA API key not configured")

    service = HeatingOilService(db)
    prices_to_store: list[dict] = []
    errors: list[str] = []

    async with EIAClient(api_key=app_settings.eia_api_key) as eia_client:
        # Fetch national average
        try:
            data = await eia_client._fetch_series(
                route="/petroleum/pri/wfr/data/",
                params={
                    "frequency": "weekly",
                    "data[0]": "value",
                    "facets[series][]": HEATING_OIL_SERIES,
                    "sort[0][column]": "period",
                    "sort[0][direction]": "desc",
                    "length": "1",
                },
            )
            rows = data.get("response", {}).get("data", [])
            if rows:
                prices_to_store.append(
                    {
                        "state": "US",
                        "price_per_gallon": float(rows[0]["value"]),
                        "source": "eia",
                        "period_date": rows[0]["period"],
                    }
                )
        except Exception as e:
            logger.error("fetch_price_failed", region="US", error=str(e))
            errors.append("US national: Fetch failed. See server logs for details.")

        # Fetch per-state prices
        for state_code, series_id in HEATING_OIL_STATE_SERIES.items():
            try:
                data = await eia_client._fetch_series(
                    route="/petroleum/pri/wfr/data/",
                    params={
                        "frequency": "weekly",
                        "data[0]": "value",
                        "facets[series][]": series_id,
                        "sort[0][column]": "period",
                        "sort[0][direction]": "desc",
                        "length": "1",
                    },
                )
                rows = data.get("response", {}).get("data", [])
                if rows:
                    prices_to_store.append(
                        {
                            "state": state_code,
                            "price_per_gallon": float(rows[0]["value"]),
                            "source": "eia",
                            "period_date": rows[0]["period"],
                        }
                    )
            except Exception as e:
                logger.error("fetch_price_failed", region=state_code, error=str(e))
                errors.append(f"{state_code}: Fetch failed. See server logs for details.")

    stored = await service.store_prices(prices_to_store)

    return {
        "status": "ok",
        "fetched": len(prices_to_store),
        "stored": stored,
        "errors": errors,
    }


@router.post("/fetch-propane", tags=["Internal"])
async def fetch_propane_prices(
    db: AsyncSession = Depends(get_db_session),
):
    """Fetch weekly propane prices from EIA for tracked states + national avg.

    Called by fetch-heating-oil.yml GHA cron (weekly Monday, same schedule).
    Stores prices in propane_prices table.
    """
    from config.settings import get_settings
    from integrations.pricing_apis.eia import (
        PROPANE_SERIES,
        PROPANE_STATE_SERIES,
        EIAClient,
    )
    from services.propane_service import PropaneService

    app_settings = get_settings()
    if not app_settings.eia_api_key:
        raise HTTPException(status_code=503, detail="EIA API key not configured")

    service = PropaneService(db)
    prices_to_store: list[dict] = []
    errors: list[str] = []

    async with EIAClient(api_key=app_settings.eia_api_key) as eia_client:
        # Fetch national average
        try:
            data = await eia_client._fetch_series(
                route="/petroleum/pri/wfr/data/",
                params={
                    "frequency": "weekly",
                    "data[0]": "value",
                    "facets[series][]": PROPANE_SERIES,
                    "sort[0][column]": "period",
                    "sort[0][direction]": "desc",
                    "length": "1",
                },
            )
            rows = data.get("response", {}).get("data", [])
            if rows:
                prices_to_store.append(
                    {
                        "state": "US",
                        "price_per_gallon": float(rows[0]["value"]),
                        "source": "eia",
                        "period_date": rows[0]["period"],
                    }
                )
        except Exception as e:
            logger.error("fetch_price_failed", region="US", error=str(e))
            errors.append("US national: Fetch failed. See server logs for details.")

        # Fetch per-state prices
        for state_code, series_id in PROPANE_STATE_SERIES.items():
            try:
                data = await eia_client._fetch_series(
                    route="/petroleum/pri/wfr/data/",
                    params={
                        "frequency": "weekly",
                        "data[0]": "value",
                        "facets[series][]": series_id,
                        "sort[0][column]": "period",
                        "sort[0][direction]": "desc",
                        "length": "1",
                    },
                )
                rows = data.get("response", {}).get("data", [])
                if rows:
                    prices_to_store.append(
                        {
                            "state": state_code,
                            "price_per_gallon": float(rows[0]["value"]),
                            "source": "eia",
                            "period_date": rows[0]["period"],
                        }
                    )
            except Exception as e:
                logger.error("fetch_price_failed", region=state_code, error=str(e))
                errors.append(f"{state_code}: Fetch failed. See server logs for details.")

    stored = await service.store_prices(prices_to_store)

    return {
        "status": "ok",
        "fetched": len(prices_to_store),
        "stored": stored,
        "errors": errors,
    }


@router.post("/geocode", tags=["Internal"])
async def geocode_address(request: GeocodeRequest):
    """Resolve a US address to a state/region via OpenWeatherMap + Nominatim.

    Primary: OpenWeatherMap Geocoding API (uses existing API key).
    Fallback: Nominatim / OpenStreetMap (free, no key required).
    """
    from services.geocoding_service import GeocodingService

    service = GeocodingService()
    result = await service.geocode(request.address)
    if not result:
        raise HTTPException(status_code=404, detail="Could not geocode address")
    return {"status": "ok", "result": result}


@router.post("/detect-rate-changes", tags=["Internal"])
async def detect_rate_changes(
    db: AsyncSession = Depends(get_db_session),
):
    """Run rate change detection across all utility types.

    Called by detect-rate-changes.yml GHA cron.
    Detects significant price changes and stores them with optional
    cheaper-alternative recommendations.
    """
    from services.rate_change_detector import RateChangeDetector

    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    detector = RateChangeDetector(db)
    all_changes: list[dict] = []
    errors: list[str] = []

    for utility_type in ["electricity", "natural_gas", "heating_oil", "propane"]:
        try:
            changes = await detector.detect_changes(utility_type)
            # Try to find cheaper alternatives for increases
            for change in changes:
                if change["change_direction"] == "increase":
                    try:
                        alt = await detector.find_cheaper_alternative(
                            utility_type=change["utility_type"],
                            region=change["region"],
                            current_price=change["current_price"],
                        )
                        if alt:
                            change["recommendation_supplier"] = alt["supplier"]
                            change["recommendation_price"] = alt["price"]
                            change["recommendation_savings"] = alt["savings"]
                    except Exception as e:
                        logger.warning(
                            "rate_change_recommendation_failed",
                            utility_type=utility_type,
                            region=change["region"],
                            error=str(e),
                        )
            all_changes.extend(changes)
        except Exception as e:
            logger.error(
                "rate_change_detection_failed",
                utility_type=utility_type,
                error=str(e),
            )
            errors.append(f"{utility_type}: Detection failed. See server logs for details.")

    stored = 0
    if all_changes:
        stored = await detector.store_changes(all_changes)

    logger.info(
        "detect_rate_changes_complete",
        detected=len(all_changes),
        stored=stored,
        errors=len(errors),
    )

    return {
        "status": "ok",
        "detected": len(all_changes),
        "stored": stored,
        "errors": errors,
    }
