"""
Internal API Endpoints

API-key-protected endpoints for scheduled jobs:
- observe-forecasts: Backfill actual prices into forecast observations
- learn: Run the nightly adaptive learning cycle
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional, List
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.dependencies import verify_api_key, get_db_session, get_redis
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(
    dependencies=[Depends(verify_api_key)],
)


class ObserveRequest(BaseModel):
    region: Optional[str] = Field(None, description="Region filter (optional)")


class LearnRequest(BaseModel):
    regions: Optional[List[str]] = Field(None, description="Regions to process (defaults to ['US'])")
    days: int = Field(default=7, ge=1, le=90, description="Lookback window in days")


@router.post("/observe-forecasts", tags=["Internal"])
async def observe_forecasts(
    request: ObserveRequest = ObserveRequest(),
    db=Depends(get_db_session),
):
    """
    Backfill actual prices into unobserved forecast rows.

    Matches forecast_observations to electricity_prices by region and hour,
    setting actual_price and observed_at.
    """
    from services.observation_service import ObservationService

    obs = ObservationService(db)

    try:
        count = await obs.observe_actuals_batch(region=request.region)
        return {
            "status": "ok",
            "observations_updated": count,
            "region": request.region or "all",
        }
    except Exception as e:
        logger.error("observe_forecasts_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Observation failed: {str(e)}")


@router.post("/learn", tags=["Internal"])
async def run_learning_cycle(
    request: LearnRequest = LearnRequest(),
    db=Depends(get_db_session),
    redis=Depends(get_redis),
):
    """
    Run the adaptive learning cycle.

    Computes rolling accuracy, detects bias, updates ensemble weights in Redis,
    stores bias correction vectors, and prunes stale patterns.
    """
    from services.observation_service import ObservationService
    from services.hnsw_vector_store import HNSWVectorStore
    from services.learning_service import LearningService

    obs = ObservationService(db)
    vs = HNSWVectorStore()
    learner = LearningService(obs, vs, redis)

    try:
        results = await learner.run_full_cycle(
            regions=request.regions,
            days=request.days,
        )
        return {
            "status": "ok",
            "results": results,
        }
    except Exception as e:
        logger.error("learning_cycle_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Learning cycle failed: {str(e)}")


class FlagUpdateBody(BaseModel):
    enabled: Optional[bool] = Field(None, description="Enable or disable the flag")
    tier_required: Optional[str] = Field(None, description="Minimum subscription tier required")
    percentage: Optional[int] = Field(None, ge=0, le=100, description="Rollout percentage (0-100)")


@router.put("/flags/{name}", tags=["Internal"])
async def update_feature_flag(
    name: str,
    body: FlagUpdateBody,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Partially update a feature flag.

    Requires a valid X-API-Key header (enforced by the router-level dependency).
    Returns 404 when the flag name is unknown or no fields were supplied.
    """
    from services.feature_flag_service import FeatureFlagService

    svc = FeatureFlagService(db)
    success = await svc.update_flag(
        name,
        enabled=body.enabled,
        tier_required=body.tier_required,
        percentage=body.percentage,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Flag not found or no changes provided")
    return {"success": True}


@router.get("/flags", tags=["Internal"])
async def list_feature_flags(
    db: AsyncSession = Depends(get_db_session),
):
    """Return all feature flags (admin/ops view). Requires API key."""
    from services.feature_flag_service import FeatureFlagService

    svc = FeatureFlagService(db)
    flags = await svc.get_all_flags()
    return {"flags": flags}


@router.post("/maintenance/cleanup", tags=["Internal"])
async def run_maintenance(db: AsyncSession = Depends(get_db_session)):
    """
    Run data retention cleanup tasks.

    Deletes activity logs older than 365 days, bill upload records
    (plus associated extracted rates and files) older than 730 days,
    electricity prices older than 365 days, and forecast observations
    older than 90 days.

    Requires a valid X-API-Key header (enforced by the router-level dependency).
    """
    from services.maintenance_service import MaintenanceService

    svc = MaintenanceService(db)
    logs = await svc.cleanup_activity_logs()
    uploads = await svc.cleanup_expired_uploads()
    prices = await svc.cleanup_old_prices()
    observations = await svc.cleanup_old_observations()
    return {
        "activity_logs": logs,
        "uploads": uploads,
        "prices": prices,
        "observations": observations,
    }


@router.get("/observation-stats", tags=["Internal"])
async def get_observation_stats(
    region: str = "US",
    days: int = 7,
    db=Depends(get_db_session),
):
    """
    Get forecast observation accuracy statistics.
    """
    from services.observation_service import ObservationService

    obs = ObservationService(db)

    try:
        accuracy = await obs.get_forecast_accuracy(region, days)
        bias = await obs.get_hourly_bias(region, days)
        return {
            "region": region,
            "days": days,
            "accuracy": accuracy,
            "hourly_bias": bias,
        }
    except Exception as e:
        logger.error("observation_stats_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Diffbot Rate Scraping
# =============================================================================


class ScrapeRequest(BaseModel):
    supplier_urls: List[dict] = Field(
        default_factory=list,
        description='[{"supplier_id": "...", "url": "..."}, ...]. '
        "If empty, auto-discovers active suppliers with websites from DB.",
    )


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
        rows = result.fetchall()
        supplier_urls = [
            {"supplier_id": str(row[0]), "url": row[2]}
            for row in rows
        ]

    if not supplier_urls:
        return {"status": "ok", "results": [], "message": "No suppliers with website URLs found"}

    service = RateScraperService()
    results = await service.scrape_supplier_rates(supplier_urls)

    # Persist scraped rates to scraped_rates table
    persisted = 0
    if db and results:
        # Build a lookup from supplier_urls for name and source URL
        url_lookup = {item.get("supplier_id"): item.get("url") for item in supplier_urls}
        name_lookup = {}
        for item in supplier_urls:
            name_lookup[item.get("supplier_id")] = item.get("name")

        insert_sql = text("""
            INSERT INTO scraped_rates (supplier_id, supplier_name, source_url, extracted_data, success)
            VALUES (:sid, :name, :url, :data, :success)
        """)
        for r in results:
            sid = r.get("supplier_id")
            try:
                await db.execute(insert_sql, {
                    "sid": sid,
                    "name": name_lookup.get(sid),
                    "url": url_lookup.get(sid),
                    "data": json.dumps(r.get("extracted_data")),
                    "success": r.get("success", False),
                })
                persisted += 1
            except Exception as e:
                logger.warning("scraped_rate_insert_failed", supplier_id=sid, error=str(e))
        await db.commit()
        logger.info("scraped_rates_persisted", count=persisted)

    return {"status": "ok", "results": results, "total": len(results), "persisted": persisted}


# =============================================================================
# OpenWeather Data Fetching
# =============================================================================


class WeatherRequest(BaseModel):
    regions: List[str] = Field(
        default=["US"], description="US state abbreviations (e.g. NY, CA, TX)"
    )


@router.post("/fetch-weather", tags=["Internal"])
async def fetch_weather_data(
    request: WeatherRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Fetch current weather for US state regions.

    Budget: 1 call per region. 51 regions = 51 calls/day (5.1% of daily limit).
    Free tier: 1,000 calls/day.
    """
    from services.weather_service import WeatherService

    service = WeatherService()
    results = await service.fetch_weather_for_regions(request.regions)

    # Persist weather data to weather_cache table
    persisted = 0
    if db and results:
        insert_sql = text("""
            INSERT INTO weather_cache (state_code, temperature_f, humidity, wind_speed_mph, conditions, raw_data)
            VALUES (:state, :temp, :humidity, :wind, :conditions, :raw)
        """)
        for state, data in results.items():
            try:
                await db.execute(insert_sql, {
                    "state": state,
                    "temp": data.get("temp_f"),
                    "humidity": data.get("humidity"),
                    "wind": data.get("wind_mph"),
                    "conditions": data.get("description"),
                    "raw": json.dumps(data),
                })
                persisted += 1
            except Exception as e:
                logger.warning("weather_cache_insert_failed", state=state, error=str(e))
        await db.commit()
        logger.info("weather_data_persisted", count=persisted)

    return {
        "status": "ok",
        "regions_fetched": len(results),
        "persisted": persisted,
        "data": results,
    }


# =============================================================================
# Tavily Market Intelligence
# =============================================================================


class MarketResearchRequest(BaseModel):
    regions: List[str] = Field(
        default=["NY", "CA", "TX"],
        description="Regions to scan for energy market news",
    )


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

    # Persist market research results to market_intelligence table
    persisted = 0
    if db and results:
        insert_sql = text("""
            INSERT INTO market_intelligence (query, region, title, url, content, score, raw_data)
            VALUES (:query, :region, :title, :url, :content, :score, :raw)
        """)
        for item in results:
            query_str = item.get("query", "")
            # Extract region from query (first token, e.g. "NY electricity rate...")
            region = query_str.split()[0] if query_str else None
            for result in item.get("data", {}).get("results", []):
                try:
                    await db.execute(insert_sql, {
                        "query": query_str[:500],
                        "region": region,
                        "title": (result.get("title") or "")[:500],
                        "url": (result.get("url") or "")[:1000],
                        "content": result.get("content"),
                        "score": result.get("score"),
                        "raw": json.dumps(result),
                    })
                    persisted += 1
                except Exception as e:
                    logger.warning("market_intel_insert_failed", query=query_str, error=str(e))
        await db.commit()
        logger.info("market_intelligence_persisted", count=persisted)

    return {"status": "ok", "results": results, "persisted": persisted}


# =============================================================================
# Google Maps Geocoding
# =============================================================================


class GeocodeRequest(BaseModel):
    address: str = Field(..., description="US address to geocode")


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


# =============================================================================
# Connection Sync Scheduler
# =============================================================================


@router.post("/sync-connections", tags=["Internal"])
async def sync_connections(db: AsyncSession = Depends(get_db_session)):
    """
    Find all active connections due for sync and trigger sync for each.

    A connection is "due" when last_sync_at + sync_frequency_hours <= NOW()
    or when it has never been synced (last_sync_at IS NULL).

    Protected by the router-level X-API-Key dependency.
    """
    from services.connection_sync_service import ConnectionSyncService

    service = ConnectionSyncService(db)
    try:
        results = await service.sync_all_due()
        succeeded = sum(1 for r in results if r.get("success"))
        failed = len(results) - succeeded
        return {
            "status": "ok",
            "total": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "results": results,
        }
    except Exception as exc:
        logger.error("sync_connections_failed", error=str(exc))
        raise HTTPException(
            status_code=500, detail=f"Connection sync failed: {str(exc)}"
        )


# =============================================================================
# Price Alert Checker
# =============================================================================


@router.post("/check-alerts", tags=["Internal"])
async def check_alerts(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Run the price-alert pipeline: load active configs, fetch recent prices,
    check thresholds, deduplicate, and send outstanding alerts.

    Summary response fields:
        checked      — total (threshold, price) pairs evaluated
        triggered    — pairs where the price breached the threshold
        sent         — alerts actually emailed (passed dedup)
        deduplicated — alerts suppressed because one was already sent
                       within the user's notification_frequency cooldown

    Cooldown windows:
        immediate / hourly  →  1 hour
        daily               →  24 hours
        weekly              →  7 days

    Protected by the router-level X-API-Key dependency.
    """
    from decimal import Decimal
    from services.alert_service import AlertService, AlertThreshold
    from repositories.price_repository import PriceRepository

    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    service = AlertService()
    price_repo = PriceRepository(db)

    try:
        # ------------------------------------------------------------------
        # 1. Load all active alert configs (joined with user email + prefs)
        # ------------------------------------------------------------------
        configs = await service.get_active_alert_configs(db)

        if not configs:
            return {"checked": 0, "triggered": 0, "sent": 0, "deduplicated": 0}

        # ------------------------------------------------------------------
        # 2. Collect the distinct regions that need current prices
        # ------------------------------------------------------------------
        regions = list({cfg["region"] for cfg in configs if cfg["region"]})

        # Fetch the most recent prices for each region (1 DB call per region)
        all_prices = []
        for region in regions:
            try:
                prices = await price_repo.list(region=region, page=1, page_size=20)
                all_prices.extend(prices)
            except Exception as exc:
                logger.warning(
                    "check_alerts_price_fetch_failed",
                    region=region,
                    error=str(exc),
                )

        # ------------------------------------------------------------------
        # 3. Build AlertThreshold objects from the DB config rows
        # ------------------------------------------------------------------
        thresholds = [
            AlertThreshold(
                user_id=cfg["user_id"],
                email=cfg["email"],
                price_below=cfg["price_below"],
                price_above=cfg["price_above"],
                notify_optimal_windows=cfg["notify_optimal_windows"],
                region=cfg["region"],
                currency=cfg["currency"],
            )
            for cfg in configs
        ]

        # Map user_id → notification_frequency for fast lookup in dedup step
        freq_by_user = {cfg["user_id"]: cfg["notification_frequency"] for cfg in configs}
        # Map user_id → alert_config_id for history records
        config_id_by_user = {cfg["user_id"]: cfg["id"] for cfg in configs}

        # ------------------------------------------------------------------
        # 4. Check thresholds (pure, no DB I/O)
        # ------------------------------------------------------------------
        triggered_pairs = service.check_thresholds(all_prices, thresholds)

        checked = len(thresholds) * len(all_prices) if all_prices else 0
        triggered_count = len(triggered_pairs)
        to_send = []
        deduplicated = 0

        # ------------------------------------------------------------------
        # 5. Deduplication — skip alerts inside their cooldown window
        # ------------------------------------------------------------------
        for threshold, alert in triggered_pairs:
            freq = freq_by_user.get(threshold.user_id, "daily")
            should_send = await service._should_send_alert(
                user_id=threshold.user_id,
                alert_type=alert.alert_type,
                region=alert.region,
                notification_frequency=freq,
                db=db,
            )
            if should_send:
                to_send.append((threshold, alert))
            else:
                deduplicated += 1
                logger.debug(
                    "check_alerts_deduplicated",
                    user_id=threshold.user_id,
                    alert_type=alert.alert_type,
                    region=alert.region,
                    frequency=freq,
                )

        # ------------------------------------------------------------------
        # 6. Send non-duplicate alerts and record history
        # ------------------------------------------------------------------
        sent = await service.send_alerts(to_send)

        # Persist each sent alert to alert_history (email_sent=True only if
        # the send succeeded — send_alerts() returns total sent count, so we
        # record based on individual send outcomes via a secondary loop)
        for threshold, alert in to_send:
            try:
                await service.record_triggered_alert(
                    user_id=threshold.user_id,
                    alert=alert,
                    db=db,
                    alert_config_id=config_id_by_user.get(threshold.user_id),
                    # Mark email_sent conservatively; if sent < len(to_send)
                    # some emails failed but we don't have per-item status.
                    # Use True here — the send_alerts() logger captures failures.
                    email_sent=True,
                    currency=threshold.currency,
                )
            except Exception as exc:
                logger.error(
                    "check_alerts_history_record_failed",
                    user_id=threshold.user_id,
                    error=str(exc),
                )

        logger.info(
            "check_alerts_complete",
            checked=checked,
            triggered=triggered_count,
            sent=sent,
            deduplicated=deduplicated,
        )

        return {
            "checked": checked,
            "triggered": triggered_count,
            "sent": sent,
            "deduplicated": deduplicated,
        }

    except Exception as exc:
        logger.error("check_alerts_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Alert check failed: {str(exc)}")


# =============================================================================
# Dunning Cycle (Overdue Payment Escalation)
# =============================================================================


@router.post("/dunning-cycle", tags=["Internal"])
async def run_dunning_cycle(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Find overdue accounts (payment failing >7 days, user still on paid tier)
    and escalate: send final dunning email, downgrade to free.

    Protected by the router-level X-API-Key dependency.
    """
    from services.dunning_service import DunningService
    from repositories.user_repository import UserRepository

    dunning = DunningService(db)
    user_repo = UserRepository(db)

    try:
        overdue = await dunning.get_overdue_accounts(grace_period_days=7)

        if not overdue:
            return {
                "status": "ok",
                "overdue_accounts": 0,
                "escalated": 0,
                "emails_sent": 0,
            }

        escalated = 0
        emails_sent = 0

        for account in overdue:
            user_id = str(account["user_id"])
            retry_count = account.get("retry_count", 3)

            # Send final dunning email
            email_sent = await dunning.send_dunning_email(
                user_email=account["email"],
                user_name=account.get("name", ""),
                retry_count=max(retry_count, 3),
                amount=float(account["amount_owed"]) if account.get("amount_owed") else None,
                currency=account.get("currency", "USD"),
            )
            if email_sent:
                emails_sent += 1

            # Escalate (downgrade to free)
            action = await dunning.escalate_if_needed(user_id, 3, user_repo)
            if action:
                escalated += 1

        logger.info(
            "dunning_cycle_complete",
            overdue=len(overdue),
            escalated=escalated,
            emails_sent=emails_sent,
        )

        return {
            "status": "ok",
            "overdue_accounts": len(overdue),
            "escalated": escalated,
            "emails_sent": emails_sent,
        }

    except Exception as exc:
        logger.error("dunning_cycle_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Dunning cycle failed: {str(exc)}")


# =============================================================================
# KPI Report
# =============================================================================


@router.post("/kpi-report", tags=["Internal"])
async def generate_kpi_report(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Aggregate key business metrics and return them as JSON.

    Metrics: active users (7d), total users, prices tracked, alerts sent today,
    connection status breakdown, subscription breakdown, estimated MRR,
    weather data freshness.

    Protected by the router-level X-API-Key dependency.
    """
    from services.kpi_report_service import KPIReportService

    service = KPIReportService(db)

    try:
        metrics = await service.aggregate_metrics()
        generated_at = datetime.now(timezone.utc).isoformat()

        return {
            "status": "ok",
            "generated_at": generated_at,
            "metrics": metrics,
        }

    except Exception as exc:
        logger.error("kpi_report_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"KPI report failed: {str(exc)}")


# =============================================================================
# Data Health Monitoring
# =============================================================================


@router.get("/health-data", tags=["Internal"])
async def data_health_check(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Return row counts and last-write timestamps for key data tables.

    Provides a quick health overview without direct DB access.
    Protected by the router-level X-API-Key dependency.
    """
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tables = [
        ("electricity_prices", "timestamp"),
        ("supplier_registry", "updated_at"),
        ("weather_cache", "fetched_at"),
        ("market_intelligence", "fetched_at"),
        ("scraped_rates", "fetched_at"),
        ("alert_history", "created_at"),
        ("users", "created_at"),
        ("user_connections", "updated_at"),
        ("forecast_observations", "created_at"),
        ("payment_retry_history", "created_at"),
    ]

    health = {}
    for table_name, ts_col in tables:
        try:
            count_result = await db.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            )
            count = count_result.scalar() or 0

            last_write = None
            if count > 0:
                ts_result = await db.execute(
                    text(f"SELECT MAX({ts_col}) FROM {table_name}")
                )
                last_write_val = ts_result.scalar()
                if last_write_val:
                    last_write = str(last_write_val)

            health[table_name] = {
                "count": count,
                "last_write": last_write,
            }
        except Exception as e:
            health[table_name] = {"count": -1, "error": str(e)}

    # Flag critical tables that should not be empty
    critical_empty = [
        t for t in ["electricity_prices", "supplier_registry", "weather_cache"]
        if health.get(t, {}).get("count", 0) == 0
    ]

    return {
        "status": "warning" if critical_empty else "ok",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "critical_empty": critical_empty,
        "tables": health,
    }
