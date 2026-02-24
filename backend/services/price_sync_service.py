"""
Price Sync Service

Orchestrates fetching prices from external APIs, converting them to the
internal Price model, and persisting them via the PriceRepository.
Called by the /prices/refresh endpoint and the GitHub Actions price-sync workflow.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models.price import Price
from models.region import Region as PricingRegion
from integrations.pricing_apis.service import create_pricing_service_from_settings
from integrations.pricing_apis.base import APIError, RateLimitError
from repositories.price_repository import PriceRepository

logger = logging.getLogger(__name__)

DEFAULT_REGIONS = [
    PricingRegion.US_CT,
    PricingRegion.US_NY,
    PricingRegion.US_CA,
    PricingRegion.UK,
    PricingRegion.GERMANY,
    PricingRegion.FRANCE,
]


async def sync_prices(
    session: AsyncSession,
    regions: Optional[List[PricingRegion]] = None,
) -> Dict[str, Any]:
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
    regions_covered: List[str] = []
    errors: List[str] = []
    prices_to_store: List[Price] = []

    pricing_service = create_pricing_service_from_settings()

    try:
        async with pricing_service:
            comparison = await pricing_service.compare_prices(target_regions)
            for region, price_data in comparison.items():
                kwh_price = price_data.convert_to_kwh()
                db_region = region.value

                prices_to_store.append(Price(
                    region=db_region,
                    supplier=kwh_price.supplier or "Unknown",
                    price_per_kwh=kwh_price.price,
                    timestamp=kwh_price.timestamp,
                    currency=kwh_price.currency,
                    is_peak=kwh_price.is_peak,
                    carbon_intensity=kwh_price.carbon_intensity,
                    source_api=kwh_price.source_api,
                ))
                regions_covered.append(region.value)

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

    return {
        "status": "refreshed" if synced_count > 0 else "partial",
        "message": f"Synced {synced_count} price records from {len(regions_covered)} regions",
        "synced_records": synced_count,
        "regions_covered": regions_covered,
        "alerts_sent": 0,
        "errors": errors if errors else None,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }
