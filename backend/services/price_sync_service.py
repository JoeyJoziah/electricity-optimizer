"""
Price Sync Service

Orchestrates fetching prices from external APIs, converting them to the
internal Price model, and persisting them via the PriceRepository.
Called by the /prices/refresh endpoint and the GitHub Actions price-sync workflow.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from integrations.pricing_apis.base import APIError, RateLimitError
from integrations.pricing_apis.service import \
    create_pricing_service_from_settings
from models.price import Price
from models.region import Region as PricingRegion
from repositories.price_repository import PriceRepository

logger = structlog.get_logger(__name__)

DEFAULT_REGIONS = [
    # Deregulated electricity states (highest priority — users can switch suppliers)
    PricingRegion.US_CT,
    PricingRegion.US_TX,
    PricingRegion.US_OH,
    PricingRegion.US_PA,
    PricingRegion.US_IL,
    PricingRegion.US_NY,
    PricingRegion.US_NJ,
    PricingRegion.US_MA,
    PricingRegion.US_MD,
    PricingRegion.US_RI,
    PricingRegion.US_NH,
    PricingRegion.US_ME,
    PricingRegion.US_DE,
    PricingRegion.US_MI,
    PricingRegion.US_VA,
    PricingRegion.US_DC,
    PricingRegion.US_OR,
    PricingRegion.US_MT,
    # Large regulated states (high user demand)
    PricingRegion.US_CA,
    PricingRegion.US_FL,
    PricingRegion.US_GA,
    # International
    PricingRegion.UK,
    PricingRegion.GERMANY,
    PricingRegion.FRANCE,
]


async def sync_prices(
    session: AsyncSession,
    regions: list[PricingRegion] | None = None,
) -> dict[str, Any]:
    """
    Fetch prices from external APIs and store in the database.

    Args:
        session: Database session for persistence.
        regions: Regions to sync. Defaults to DEFAULT_REGIONS.

    Returns:
        Dict with status, synced_records, regions_covered, errors, triggered_at.
    """
    target_regions = regions or DEFAULT_REGIONS
    synced_count = 0
    regions_covered: list[str] = []
    errors: list[str] = []
    prices_to_store: list[Price] = []

    pricing_service = create_pricing_service_from_settings()

    try:
        async with pricing_service:
            comparison = await pricing_service.compare_prices(target_regions)
            missing = [r.value for r in target_regions if r not in comparison]
            logger.info(
                "price_sync_comparison_result: requested=%d returned=%d missing=%s",
                len(target_regions),
                len(comparison),
                missing,
            )
            for region, price_data in comparison.items():
                kwh_price = price_data.convert_to_kwh()
                db_region = region.value

                prices_to_store.append(
                    Price(
                        region=db_region,
                        supplier=kwh_price.supplier or "Unknown",
                        price_per_kwh=kwh_price.price,
                        timestamp=kwh_price.timestamp,
                        currency=kwh_price.currency,
                        is_peak=kwh_price.is_peak,
                        carbon_intensity=kwh_price.carbon_intensity,
                        source_api=kwh_price.source_api,
                    )
                )
                regions_covered.append(region.value)

            if prices_to_store and not session:
                logger.error(
                    "price_sync_no_db_session: %d prices fetched but cannot persist — no database session",
                    len(prices_to_store),
                )
                errors.append("Database session unavailable — prices not persisted")

            if prices_to_store and session:
                repo = PriceRepository(session)
                synced_count = await repo.bulk_create(prices_to_store)

    except RateLimitError as e:
        logger.warning("price_sync_rate_limited", error=str(e), retry_after=e.retry_after)
        errors.append(f"Rate limited: {e}")
    except APIError as e:
        logger.warning("price_sync_api_error", error=str(e))
        errors.append(f"API error: {e}")
    except Exception as e:
        logger.error("price_sync_failed", error=str(e))
        errors.append(f"Unexpected error: {e}")

    if synced_count > 0:
        logger.info("price_sync_complete", count=synced_count, regions=regions_covered)
    elif not errors:
        logger.warning(
            "price_sync_zero_records: targets=%s — all API calls succeeded but returned zero price data",
            [r.value for r in target_regions],
        )

    status = "refreshed" if synced_count > 0 else ("error" if errors else "empty")

    return {
        "status": status,
        "message": f"Synced {synced_count} price records from {len(regions_covered)} regions",
        "synced_records": synced_count,
        "regions_covered": regions_covered,
        "alerts_sent": 0,
        "errors": errors if errors else None,
        "triggered_at": datetime.now(UTC).isoformat(),
    }
