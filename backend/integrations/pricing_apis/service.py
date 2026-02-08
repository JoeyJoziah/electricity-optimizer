"""
Unified Pricing Service

Provides a single interface to access electricity pricing from multiple sources
with automatic fallback, data aggregation, and best-source selection.

Features:
- Automatic API selection based on region
- Fallback to alternative sources on failure
- Price data aggregation and comparison
- Health monitoring across all APIs
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import asyncio

import structlog

from .base import (
    PriceData,
    PriceForecast,
    PricingRegion,
    APIError,
)
from .flatpeak import FlatpeakClient
from .nrel import NRELClient
from .iea import IEAClient
from .cache import PricingCache
from .rate_limiter import RateLimiter

logger = structlog.get_logger(__name__)


class PricingService:
    """
    Unified service for accessing electricity pricing data.

    Automatically routes requests to the appropriate API based on region
    and provides fallback mechanisms when primary sources fail.

    Example usage:
        ```python
        service = PricingService(
            flatpeak_key="...",
            nrel_key="...",
            iea_key="...",
        )

        async with service:
            # Get current price - automatically selects best API
            price = await service.get_current_price(PricingRegion.UK)

            # Get forecast
            forecast = await service.get_forecast(PricingRegion.US_CA, hours=24)

            # Compare prices across regions
            comparison = await service.compare_prices([
                PricingRegion.UK,
                PricingRegion.GERMANY,
                PricingRegion.US_CA,
            ])
        ```
    """

    def __init__(
        self,
        flatpeak_key: Optional[str] = None,
        nrel_key: Optional[str] = None,
        iea_key: Optional[str] = None,
        cache: Optional[PricingCache] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize the pricing service.

        Args:
            flatpeak_key: Flatpeak API key (for UK/EU)
            nrel_key: NREL API key (for US)
            iea_key: IEA Bearer token (for global)
            cache: Optional shared cache instance
            timeout: Request timeout in seconds
        """
        self.cache = cache
        self.timeout = timeout

        # Initialize clients based on available keys
        self._clients: dict[str, Optional[object]] = {}

        if flatpeak_key:
            self._clients["flatpeak"] = FlatpeakClient(
                api_key=flatpeak_key,
                cache=cache,
                timeout=timeout,
            )

        if nrel_key:
            self._clients["nrel"] = NRELClient(
                api_key=nrel_key,
                cache=cache,
                timeout=timeout,
            )

        if iea_key:
            self._clients["iea"] = IEAClient(
                api_key=iea_key,
                cache=cache,
                timeout=timeout,
            )

        self.logger = logger.bind(service="pricing")

    async def __aenter__(self) -> "PricingService":
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - close all clients"""
        await self.close()

    async def close(self) -> None:
        """Close all API clients"""
        for name, client in self._clients.items():
            if client:
                try:
                    await client.close()
                except Exception as e:
                    self.logger.error(
                        "client_close_error",
                        client=name,
                        error=str(e),
                    )

    def _get_primary_client(self, region: PricingRegion) -> tuple[str, object]:
        """
        Get the primary (best) client for a region.

        Returns:
            Tuple of (client_name, client_instance)
        """
        # UK/EU regions -> Flatpeak first
        eu_regions = {
            PricingRegion.UK,
            PricingRegion.UK_SCOTLAND,
            PricingRegion.UK_WALES,
            PricingRegion.IRELAND,
            PricingRegion.GERMANY,
            PricingRegion.FRANCE,
            PricingRegion.SPAIN,
            PricingRegion.ITALY,
            PricingRegion.NETHERLANDS,
            PricingRegion.BELGIUM,
            PricingRegion.AUSTRIA,
        }

        # US regions -> NREL first
        us_regions = {
            PricingRegion.US_CA,
            PricingRegion.US_TX,
            PricingRegion.US_NY,
            PricingRegion.US_FL,
            PricingRegion.US_IL,
            PricingRegion.US_PA,
            PricingRegion.US_OH,
            PricingRegion.US_GA,
            PricingRegion.US_NC,
            PricingRegion.US_MI,
            PricingRegion.US_CT,
        }

        if region in eu_regions:
            if self._clients.get("flatpeak"):
                return ("flatpeak", self._clients["flatpeak"])
            if self._clients.get("iea"):
                return ("iea", self._clients["iea"])

        if region in us_regions:
            if self._clients.get("nrel"):
                return ("nrel", self._clients["nrel"])
            if self._clients.get("iea"):
                return ("iea", self._clients["iea"])

        # Fallback to IEA for global regions
        if self._clients.get("iea"):
            return ("iea", self._clients["iea"])

        raise APIError(
            f"No API client available for region {region}",
            api_name="pricing_service",
        )

    def _get_fallback_clients(
        self,
        region: PricingRegion,
        exclude: str,
    ) -> list[tuple[str, object]]:
        """
        Get fallback clients for a region, excluding the primary.

        Returns:
            List of (client_name, client_instance) tuples
        """
        fallbacks = []

        for name, client in self._clients.items():
            if name == exclude or not client:
                continue
            if client.supports_region(region):
                fallbacks.append((name, client))

        return fallbacks

    async def get_current_price(
        self,
        region: PricingRegion,
        use_fallback: bool = True,
    ) -> PriceData:
        """
        Get current electricity price for a region.

        Automatically selects the best API for the region and falls back
        to alternatives if the primary fails.

        Args:
            region: The pricing region
            use_fallback: Whether to try fallback APIs on failure

        Returns:
            Current price data

        Raises:
            APIError: If all APIs fail
        """
        primary_name, primary_client = self._get_primary_client(region)

        try:
            self.logger.info(
                "fetching_price",
                region=region.value,
                client=primary_name,
            )
            return await primary_client.get_current_price(region)

        except Exception as e:
            self.logger.warning(
                "primary_client_failed",
                client=primary_name,
                region=region.value,
                error=str(e),
            )

            if not use_fallback:
                raise

            # Try fallbacks
            fallbacks = self._get_fallback_clients(region, primary_name)

            for fallback_name, fallback_client in fallbacks:
                try:
                    self.logger.info(
                        "trying_fallback",
                        client=fallback_name,
                        region=region.value,
                    )
                    return await fallback_client.get_current_price(region)
                except Exception as fallback_error:
                    self.logger.warning(
                        "fallback_failed",
                        client=fallback_name,
                        error=str(fallback_error),
                    )

            # All failed
            raise APIError(
                f"All API clients failed for region {region}",
                api_name="pricing_service",
            ) from e

    async def get_forecast(
        self,
        region: PricingRegion,
        hours: int = 24,
        use_fallback: bool = True,
    ) -> PriceForecast:
        """
        Get price forecast for a region.

        Args:
            region: The pricing region
            hours: Forecast horizon in hours
            use_fallback: Whether to try fallback APIs on failure

        Returns:
            Price forecast
        """
        primary_name, primary_client = self._get_primary_client(region)

        try:
            return await primary_client.get_price_forecast(region, hours)
        except Exception as e:
            if not use_fallback:
                raise

            fallbacks = self._get_fallback_clients(region, primary_name)

            for fallback_name, fallback_client in fallbacks:
                try:
                    return await fallback_client.get_price_forecast(region, hours)
                except Exception:
                    continue

            raise APIError(
                f"All API clients failed for forecast in {region}",
                api_name="pricing_service",
            ) from e

    async def compare_prices(
        self,
        regions: list[PricingRegion],
    ) -> dict[PricingRegion, PriceData]:
        """
        Compare current prices across multiple regions.

        Args:
            regions: List of regions to compare

        Returns:
            Dictionary mapping regions to their current prices
        """
        tasks = [self.get_current_price(region) for region in regions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        comparison = {}
        for region, result in zip(regions, results):
            if isinstance(result, Exception):
                self.logger.warning(
                    "comparison_failed",
                    region=region.value,
                    error=str(result),
                )
            else:
                comparison[region] = result

        return comparison

    async def get_cheapest_regions(
        self,
        regions: list[PricingRegion],
        top_n: int = 3,
    ) -> list[tuple[PricingRegion, PriceData]]:
        """
        Get the cheapest regions from a list.

        Args:
            regions: List of regions to compare
            top_n: Number of cheapest regions to return

        Returns:
            List of (region, price) tuples, sorted by price
        """
        comparison = await self.compare_prices(regions)

        sorted_prices = sorted(
            comparison.items(),
            key=lambda x: x[1].price,
        )

        return sorted_prices[:top_n]

    async def health_check(self) -> dict[str, bool]:
        """
        Check health of all configured API clients.

        Returns:
            Dictionary mapping client names to health status
        """
        health = {}

        for name, client in self._clients.items():
            if client:
                try:
                    health[name] = await client.health_check()
                except Exception as e:
                    self.logger.error(
                        "health_check_error",
                        client=name,
                        error=str(e),
                    )
                    health[name] = False
            else:
                health[name] = False

        return health

    def get_supported_regions(self) -> dict[str, list[PricingRegion]]:
        """
        Get supported regions for each configured client.

        Returns:
            Dictionary mapping client names to their supported regions
        """
        supported = {}

        for name, client in self._clients.items():
            if client:
                supported[name] = client.get_supported_regions()

        return supported

    def get_all_supported_regions(self) -> set[PricingRegion]:
        """
        Get all regions supported by at least one client.

        Returns:
            Set of all supported regions
        """
        all_regions = set()

        for name, client in self._clients.items():
            if client:
                all_regions.update(client.get_supported_regions())

        return all_regions


def create_pricing_service_from_settings() -> PricingService:
    """
    Factory function to create PricingService from application settings.

    Returns:
        Configured PricingService instance
    """
    from config.settings import settings

    return PricingService(
        flatpeak_key=settings.flatpeak_api_key,
        nrel_key=settings.nrel_api_key,
        iea_key=settings.iea_api_key,
    )
