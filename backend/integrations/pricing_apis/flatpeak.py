"""
Flatpeak API Client

Provides access to UK/EU electricity price data from the Flatpeak API.

API Documentation: https://docs.flatpeak.com/
Rate Limit: 100 requests/minute

Supported Regions:
- UK (England, Scotland, Wales)
- Ireland
- Germany
- France
- Spain
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import structlog

from .base import (
    BasePricingClient,
    PriceData,
    PriceForecast,
    PricingRegion,
    PriceUnit,
    APIError,
    RetryConfig,
    CircuitBreakerConfig,
)
from .rate_limiter import RateLimiter, create_api_rate_limiter
from .cache import PricingCache

logger = structlog.get_logger(__name__)


# Region mapping: PricingRegion -> Flatpeak region code
FLATPEAK_REGION_MAP = {
    PricingRegion.UK: "GB",
    PricingRegion.UK_SCOTLAND: "GB-SCT",
    PricingRegion.UK_WALES: "GB-WLS",
    PricingRegion.IRELAND: "IE",
    PricingRegion.GERMANY: "DE",
    PricingRegion.FRANCE: "FR",
    PricingRegion.SPAIN: "ES",
    PricingRegion.ITALY: "IT",
    PricingRegion.NETHERLANDS: "NL",
    PricingRegion.BELGIUM: "BE",
    PricingRegion.AUSTRIA: "AT",
}

# Currency mapping
REGION_CURRENCY_MAP = {
    PricingRegion.UK: "GBP",
    PricingRegion.UK_SCOTLAND: "GBP",
    PricingRegion.UK_WALES: "GBP",
    PricingRegion.IRELAND: "EUR",
    PricingRegion.GERMANY: "EUR",
    PricingRegion.FRANCE: "EUR",
    PricingRegion.SPAIN: "EUR",
    PricingRegion.ITALY: "EUR",
    PricingRegion.NETHERLANDS: "EUR",
    PricingRegion.BELGIUM: "EUR",
    PricingRegion.AUSTRIA: "EUR",
}


class FlatpeakClient(BasePricingClient):
    """
    Async client for the Flatpeak electricity pricing API.

    Example usage:
        ```python
        async with FlatpeakClient(api_key="your-key") as client:
            price = await client.get_current_price(PricingRegion.UK)
            print(f"Current price: {price.price} {price.currency}/{price.unit}")

            forecast = await client.get_price_forecast(PricingRegion.UK, hours=24)
            for p in forecast.prices:
                print(f"{p.timestamp}: {p.price}")
        ```
    """

    BASE_URL = "https://api.flatpeak.com/v1"

    def __init__(
        self,
        api_key: str,
        timeout: float = 30.0,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        rate_limiter: Optional[RateLimiter] = None,
        cache: Optional[PricingCache] = None,
    ):
        """
        Initialize Flatpeak client.

        Args:
            api_key: Flatpeak API key
            timeout: Request timeout in seconds
            retry_config: Configuration for retry behavior
            circuit_breaker_config: Configuration for circuit breaker
            rate_limiter: Optional rate limiter instance
            cache: Optional cache instance
        """
        super().__init__(
            api_key=api_key,
            base_url=self.BASE_URL,
            client_name="flatpeak",
            timeout=timeout,
            retry_config=retry_config,
            circuit_breaker_config=circuit_breaker_config,
        )

        # Rate limiter (100 requests/minute for Flatpeak)
        self.rate_limiter = rate_limiter or create_api_rate_limiter(
            api_name="flatpeak",
            requests_per_minute=100,
        )

        # Cache
        self.cache = cache

        self.logger = logger.bind(api_client="flatpeak")

    def _get_default_headers(self) -> dict[str, str]:
        """Get default headers with API key authentication"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ElectricityOptimizer/1.0",
        }

    def get_supported_regions(self) -> list[PricingRegion]:
        """Get list of supported regions"""
        return list(FLATPEAK_REGION_MAP.keys())

    def _get_flatpeak_region(self, region: PricingRegion) -> str:
        """Convert PricingRegion to Flatpeak region code"""
        if region not in FLATPEAK_REGION_MAP:
            raise ValueError(f"Region {region} not supported by Flatpeak API")
        return FLATPEAK_REGION_MAP[region]

    def _parse_price_response(
        self,
        data: dict,
        region: PricingRegion,
    ) -> PriceData:
        """Parse Flatpeak price response to PriceData"""
        currency = REGION_CURRENCY_MAP.get(region, "EUR")

        # Parse timestamp (Flatpeak returns ISO format)
        timestamp_str = data.get("timestamp") or data.get("valid_from")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        else:
            timestamp = datetime.now(timezone.utc)

        # Price is typically in local currency per kWh
        price = Decimal(str(data.get("price", 0)))

        # Determine unit based on response
        unit_str = data.get("unit", "kWh")
        if unit_str.lower() == "mwh":
            unit = PriceUnit.MWH
        else:
            unit = PriceUnit.KWH

        # Extract price breakdown if available
        breakdown = data.get("breakdown", {})

        return PriceData(
            region=region,
            timestamp=timestamp,
            price=price,
            unit=unit,
            currency=currency,
            supplier=data.get("supplier"),
            tariff_name=data.get("tariff_name"),
            source_api="flatpeak",
            energy_cost=Decimal(str(breakdown.get("energy", 0))) if breakdown.get("energy") else None,
            network_cost=Decimal(str(breakdown.get("network", 0))) if breakdown.get("network") else None,
            taxes=Decimal(str(breakdown.get("taxes", 0))) if breakdown.get("taxes") else None,
            levies=Decimal(str(breakdown.get("levies", 0))) if breakdown.get("levies") else None,
            is_peak=data.get("is_peak"),
            is_renewable=data.get("renewable_percentage", 0) > 50,
            carbon_intensity=data.get("carbon_intensity"),
        )

    async def _check_rate_limit(self) -> None:
        """Wait for rate limit if necessary"""
        if self.rate_limiter:
            acquired = await self.rate_limiter.wait_for_token(
                key="flatpeak",
                timeout=30.0,
            )
            if not acquired:
                raise APIError(
                    "Rate limit timeout - could not acquire token",
                    api_name="flatpeak",
                )

    async def get_current_price(self, region: PricingRegion) -> PriceData:
        """
        Get current electricity price for a region.

        Args:
            region: The pricing region

        Returns:
            Current price data

        Raises:
            APIError: If API request fails
            ValueError: If region not supported
        """
        if not self.supports_region(region):
            raise ValueError(f"Region {region} not supported by Flatpeak")

        # Check cache first
        if self.cache:
            cache_key = self.cache.current_price_key("flatpeak", region.value)
            cached = await self.cache.get(cache_key)
            if cached:
                self.logger.debug("cache_hit", region=region.value)
                return PriceData.from_dict(cached)

        # Rate limit check
        await self._check_rate_limit()

        flatpeak_region = self._get_flatpeak_region(region)

        self.logger.info(
            "fetching_current_price",
            region=region.value,
            flatpeak_region=flatpeak_region,
        )

        response = await self.get(
            endpoint="/prices/current",
            params={"region": flatpeak_region},
        )

        data = response.json()

        # Handle response format (may be nested)
        price_data = data.get("data", data)

        result = self._parse_price_response(price_data, region)

        # Cache the result
        if self.cache:
            await self.cache.set_current_price(
                api="flatpeak",
                region=region.value,
                data=result.to_dict(),
            )

        return result

    async def get_price_forecast(
        self,
        region: PricingRegion,
        hours: int = 24,
    ) -> PriceForecast:
        """
        Get price forecast for a region.

        Args:
            region: The pricing region
            hours: Forecast horizon in hours (default 24)

        Returns:
            Price forecast data

        Raises:
            APIError: If API request fails
            ValueError: If region not supported
        """
        if not self.supports_region(region):
            raise ValueError(f"Region {region} not supported by Flatpeak")

        # Check cache first
        if self.cache:
            cache_key = self.cache.forecast_key("flatpeak", region.value, hours)
            cached = await self.cache.get(cache_key)
            if cached:
                self.logger.debug("forecast_cache_hit", region=region.value)
                return PriceForecast.from_dict(cached)

        # Rate limit check
        await self._check_rate_limit()

        flatpeak_region = self._get_flatpeak_region(region)

        self.logger.info(
            "fetching_price_forecast",
            region=region.value,
            hours=hours,
        )

        response = await self.get(
            endpoint="/prices/forecast",
            params={
                "region": flatpeak_region,
                "hours": hours,
            },
        )

        data = response.json()

        # Parse forecast data
        forecast_data = data.get("data", data)
        prices = []

        for item in forecast_data.get("prices", []):
            prices.append(self._parse_price_response(item, region))

        result = PriceForecast(
            region=region,
            forecast_generated_at=datetime.now(timezone.utc),
            forecast_horizon_hours=hours,
            source_api="flatpeak",
            prices=prices,
            model_version=forecast_data.get("model_version"),
            confidence_level=forecast_data.get("confidence"),
        )

        # Cache the result
        if self.cache:
            await self.cache.set_forecast(
                api="flatpeak",
                region=region.value,
                hours=hours,
                data=result.to_dict(),
            )

        return result

    async def get_historical_prices(
        self,
        region: PricingRegion,
        start_date: datetime,
        end_date: datetime,
        resolution: str = "1h",
    ) -> list[PriceData]:
        """
        Get historical prices for a region.

        Args:
            region: The pricing region
            start_date: Start of date range
            end_date: End of date range
            resolution: Data resolution (1h, 30m, 15m)

        Returns:
            List of historical price data points

        Raises:
            APIError: If API request fails
            ValueError: If region not supported
        """
        if not self.supports_region(region):
            raise ValueError(f"Region {region} not supported by Flatpeak")

        await self._check_rate_limit()

        flatpeak_region = self._get_flatpeak_region(region)

        self.logger.info(
            "fetching_historical_prices",
            region=region.value,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            resolution=resolution,
        )

        response = await self.get(
            endpoint="/prices/historical",
            params={
                "region": flatpeak_region,
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "resolution": resolution,
            },
        )

        data = response.json()
        historical_data = data.get("data", data)

        prices = []
        for item in historical_data.get("prices", []):
            prices.append(self._parse_price_response(item, region))

        return prices

    async def get_tariff_info(self, region: PricingRegion) -> dict:
        """
        Get available tariff information for a region.

        Args:
            region: The pricing region

        Returns:
            Dictionary containing tariff details
        """
        if not self.supports_region(region):
            raise ValueError(f"Region {region} not supported by Flatpeak")

        await self._check_rate_limit()

        flatpeak_region = self._get_flatpeak_region(region)

        response = await self.get(
            endpoint="/tariffs",
            params={"region": flatpeak_region},
        )

        return response.json()

    async def health_check(self) -> bool:
        """
        Check if the Flatpeak API is available.

        Returns:
            True if API is healthy
        """
        try:
            response = await self.get(
                endpoint="/health",
                deduplicate=False,
            )
            return response.status_code == 200
        except Exception as e:
            self.logger.warning("health_check_failed", error=str(e))
            return False
