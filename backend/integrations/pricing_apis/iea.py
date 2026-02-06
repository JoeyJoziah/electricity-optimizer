"""
IEA (International Energy Agency) API Client

Provides access to global electricity price statistics and market data.

API Documentation: https://www.iea.org/data-and-statistics/data-tools
Rate Limit: 500 requests/hour

Supported Regions:
- 40+ countries including major global economies
"""

from datetime import datetime, timezone
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


# Region mapping: PricingRegion -> IEA country code
IEA_REGION_MAP = {
    # Europe
    PricingRegion.UK: "GBR",
    PricingRegion.GERMANY: "DEU",
    PricingRegion.FRANCE: "FRA",
    PricingRegion.SPAIN: "ESP",
    PricingRegion.ITALY: "ITA",
    PricingRegion.NETHERLANDS: "NLD",
    PricingRegion.BELGIUM: "BEL",
    PricingRegion.AUSTRIA: "AUT",
    PricingRegion.IRELAND: "IRL",
    # Americas
    PricingRegion.US_CA: "USA",
    PricingRegion.US_TX: "USA",
    PricingRegion.US_NY: "USA",
    PricingRegion.CANADA: "CAN",
    PricingRegion.BRAZIL: "BRA",
    # Asia-Pacific
    PricingRegion.JAPAN: "JPN",
    PricingRegion.AUSTRALIA: "AUS",
    PricingRegion.CHINA: "CHN",
    PricingRegion.INDIA: "IND",
}

# Currency mapping for IEA regions
IEA_CURRENCY_MAP = {
    "GBR": "GBP",
    "DEU": "EUR",
    "FRA": "EUR",
    "ESP": "EUR",
    "ITA": "EUR",
    "NLD": "EUR",
    "BEL": "EUR",
    "AUT": "EUR",
    "IRL": "EUR",
    "USA": "USD",
    "CAN": "CAD",
    "BRA": "BRL",
    "JPN": "JPY",
    "AUS": "AUD",
    "CHN": "CNY",
    "IND": "INR",
}

# Sector types
SECTOR_HOUSEHOLD = "household"
SECTOR_INDUSTRY = "industry"


class IEAClient(BasePricingClient):
    """
    Async client for the IEA Electricity Statistics API.

    Provides access to:
    - Average electricity prices by country
    - Historical price trends
    - Price statistics and comparisons
    - Renewable energy data

    Note: IEA data is typically aggregated (monthly/quarterly/annual)
    rather than real-time, making it better suited for trend analysis
    and benchmarking rather than operational pricing decisions.

    Example usage:
        ```python
        async with IEAClient(api_key="your-bearer-token") as client:
            # Get current average price
            price = await client.get_current_price(PricingRegion.UK)
            print(f"Average price: {price.price} {price.currency}/{price.unit}")

            # Get price statistics
            stats = await client.get_price_statistics(
                region=PricingRegion.GERMANY,
                year=2024
            )
        ```
    """

    BASE_URL = "https://api.iea.org/electricity"

    def __init__(
        self,
        api_key: str,
        timeout: float = 30.0,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        rate_limiter: Optional[RateLimiter] = None,
        cache: Optional[PricingCache] = None,
        default_sector: str = SECTOR_HOUSEHOLD,
    ):
        """
        Initialize IEA client.

        Args:
            api_key: IEA Bearer token
            timeout: Request timeout in seconds
            retry_config: Configuration for retry behavior
            circuit_breaker_config: Configuration for circuit breaker
            rate_limiter: Optional rate limiter instance
            cache: Optional cache instance
            default_sector: Default price sector (household/industry)
        """
        super().__init__(
            api_key=api_key,
            base_url=self.BASE_URL,
            client_name="iea",
            timeout=timeout,
            retry_config=retry_config,
            circuit_breaker_config=circuit_breaker_config,
        )

        # Rate limiter (500 requests/hour for IEA)
        self.rate_limiter = rate_limiter or create_api_rate_limiter(
            api_name="iea",
            requests_per_hour=500,
        )

        self.cache = cache
        self.default_sector = default_sector

        self.logger = logger.bind(api_client="iea")

    def _get_default_headers(self) -> dict[str, str]:
        """Get default headers with Bearer token authentication"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ElectricityOptimizer/1.0",
        }

    def get_supported_regions(self) -> list[PricingRegion]:
        """Get list of supported regions"""
        return list(IEA_REGION_MAP.keys())

    def _get_iea_country(self, region: PricingRegion) -> str:
        """Convert PricingRegion to IEA country code"""
        if region not in IEA_REGION_MAP:
            raise ValueError(f"Region {region} not supported by IEA API")
        return IEA_REGION_MAP[region]

    def _get_currency(self, country_code: str) -> str:
        """Get currency for a country"""
        return IEA_CURRENCY_MAP.get(country_code, "USD")

    def _parse_price_response(
        self,
        data: dict,
        region: PricingRegion,
        country_code: str,
    ) -> PriceData:
        """Parse IEA price response to PriceData"""
        # IEA returns prices in various formats
        # Typically in local currency per MWh or USD/MWh

        price_value = data.get("price") or data.get("value", 0)
        unit_str = data.get("unit", "MWh")

        # Convert to Decimal
        price = Decimal(str(price_value))

        # Determine unit
        if "mwh" in unit_str.lower():
            unit = PriceUnit.MWH
            # Convert to kWh for consistency
            price = price / 1000
            unit = PriceUnit.KWH
        else:
            unit = PriceUnit.KWH

        # Get currency - IEA may report in USD or local
        currency = data.get("currency") or self._get_currency(country_code)

        # Parse timestamp
        timestamp_str = data.get("timestamp") or data.get("period")
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                # May be a period like "2024-Q1" or "2024"
                timestamp = datetime.now(timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)

        return PriceData(
            region=region,
            timestamp=timestamp,
            price=price,
            unit=unit,
            currency=currency,
            supplier=None,  # IEA doesn't provide supplier-level data
            tariff_name=data.get("tariff_type"),
            source_api="iea",
            # IEA may provide some breakdown
            taxes=Decimal(str(data.get("taxes", 0))) if data.get("taxes") else None,
            is_peak=None,
            is_renewable=None,
            carbon_intensity=data.get("carbon_intensity"),
        )

    async def _check_rate_limit(self) -> None:
        """Wait for rate limit if necessary"""
        if self.rate_limiter:
            acquired = await self.rate_limiter.wait_for_token(
                key="iea",
                timeout=30.0,
            )
            if not acquired:
                raise APIError(
                    "Rate limit timeout - could not acquire token",
                    api_name="iea",
                )

    async def get_current_price(self, region: PricingRegion) -> PriceData:
        """
        Get current average electricity price for a region.

        Note: IEA data may be delayed (monthly/quarterly updates).
        For real-time pricing, use Flatpeak (EU) or NREL (US).

        Args:
            region: The pricing region

        Returns:
            Most recent price data available

        Raises:
            APIError: If API request fails
            ValueError: If region not supported
        """
        if not self.supports_region(region):
            raise ValueError(f"Region {region} not supported by IEA")

        # Check cache first
        if self.cache:
            cache_key = self.cache.current_price_key("iea", region.value)
            cached = await self.cache.get(cache_key)
            if cached:
                self.logger.debug("cache_hit", region=region.value)
                return PriceData.from_dict(cached)

        await self._check_rate_limit()

        country_code = self._get_iea_country(region)

        self.logger.info(
            "fetching_current_price",
            region=region.value,
            country_code=country_code,
        )

        response = await self.get(
            endpoint="/prices",
            params={
                "country": country_code,
                "sector": self.default_sector,
                "latest": "true",
            },
        )

        data = response.json()

        # Handle IEA response format
        prices_data = data.get("data", [])
        if not prices_data:
            # Try alternative response structure
            prices_data = [data] if "price" in data or "value" in data else []

        if not prices_data:
            raise APIError(
                f"No price data available for {region}",
                api_name="iea",
            )

        # Get the most recent price
        latest = prices_data[0] if isinstance(prices_data, list) else prices_data

        result = self._parse_price_response(latest, region, country_code)

        # Cache the result (longer TTL for IEA since data updates less frequently)
        if self.cache:
            await self.cache.set(
                self.cache.current_price_key("iea", region.value),
                result.to_dict(),
                ttl=3600,  # 1 hour cache for IEA
            )

        return result

    async def get_price_forecast(
        self,
        region: PricingRegion,
        hours: int = 24,
    ) -> PriceForecast:
        """
        Get price forecast for a region.

        Note: IEA doesn't provide real-time forecasts. This method
        returns projections based on historical trends and seasonality.

        Args:
            region: The pricing region
            hours: Forecast horizon in hours

        Returns:
            Projected price forecast
        """
        if not self.supports_region(region):
            raise ValueError(f"Region {region} not supported by IEA")

        # Check cache first
        if self.cache:
            cache_key = self.cache.forecast_key("iea", region.value, hours)
            cached = await self.cache.get(cache_key)
            if cached:
                return PriceForecast.from_dict(cached)

        # Get current price as baseline
        current_price = await self.get_current_price(region)

        # Generate simple forecast based on current price
        # Real implementation would use historical data and ML models
        prices = []
        base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

        for hour_offset in range(hours):
            forecast_time = base_time + timedelta(hours=hour_offset)

            # Simple seasonal adjustment
            month = forecast_time.month
            hour_of_day = forecast_time.hour

            # Winter months typically have higher prices
            if month in [12, 1, 2]:
                seasonal_factor = Decimal("1.15")
            elif month in [6, 7, 8]:
                seasonal_factor = Decimal("1.10")  # Summer AC demand
            else:
                seasonal_factor = Decimal("1.0")

            # Time of day adjustment
            if 7 <= hour_of_day <= 9 or 17 <= hour_of_day <= 20:
                tod_factor = Decimal("1.2")
                is_peak = True
            elif 0 <= hour_of_day <= 5:
                tod_factor = Decimal("0.85")
                is_peak = False
            else:
                tod_factor = Decimal("1.0")
                is_peak = False

            adjusted_price = current_price.price * seasonal_factor * tod_factor

            prices.append(
                PriceData(
                    region=region,
                    timestamp=forecast_time,
                    price=adjusted_price,
                    unit=current_price.unit,
                    currency=current_price.currency,
                    source_api="iea",
                    is_peak=is_peak,
                )
            )

        result = PriceForecast(
            region=region,
            forecast_generated_at=datetime.now(timezone.utc),
            forecast_horizon_hours=hours,
            source_api="iea",
            prices=prices,
            model_version="seasonal_projection_v1",
            confidence_level=0.6,  # Lower confidence for synthetic forecast
        )

        # Cache the result
        if self.cache:
            await self.cache.set_forecast(
                api="iea",
                region=region.value,
                hours=hours,
                data=result.to_dict(),
            )

        return result

    async def get_price_statistics(
        self,
        region: PricingRegion,
        year: Optional[int] = None,
        sector: Optional[str] = None,
    ) -> dict:
        """
        Get price statistics for a region.

        Args:
            region: The pricing region
            year: Specific year (optional, defaults to latest)
            sector: Price sector (household/industry)

        Returns:
            Dictionary containing price statistics
        """
        if not self.supports_region(region):
            raise ValueError(f"Region {region} not supported by IEA")

        await self._check_rate_limit()

        country_code = self._get_iea_country(region)

        params = {
            "country": country_code,
            "sector": sector or self.default_sector,
        }

        if year:
            params["year"] = year

        self.logger.info(
            "fetching_price_statistics",
            region=region.value,
            year=year,
        )

        response = await self.get(
            endpoint="/statistics",
            params=params,
        )

        return response.json()

    async def get_historical_prices(
        self,
        region: PricingRegion,
        start_year: int,
        end_year: Optional[int] = None,
        sector: Optional[str] = None,
    ) -> list[PriceData]:
        """
        Get historical price data for a region.

        Args:
            region: The pricing region
            start_year: Start year
            end_year: End year (optional, defaults to current)
            sector: Price sector

        Returns:
            List of historical price data points
        """
        if not self.supports_region(region):
            raise ValueError(f"Region {region} not supported by IEA")

        await self._check_rate_limit()

        country_code = self._get_iea_country(region)

        params = {
            "country": country_code,
            "sector": sector or self.default_sector,
            "start_year": start_year,
        }

        if end_year:
            params["end_year"] = end_year

        self.logger.info(
            "fetching_historical_prices",
            region=region.value,
            start_year=start_year,
            end_year=end_year,
        )

        response = await self.get(
            endpoint="/prices/historical",
            params=params,
        )

        data = response.json()

        prices = []
        for item in data.get("data", []):
            prices.append(self._parse_price_response(item, region, country_code))

        return prices

    async def get_country_comparison(
        self,
        regions: list[PricingRegion],
        sector: Optional[str] = None,
    ) -> dict[PricingRegion, PriceData]:
        """
        Get price comparison across multiple regions.

        Args:
            regions: List of regions to compare
            sector: Price sector

        Returns:
            Dictionary mapping regions to their current prices
        """
        import asyncio

        results = {}

        # Fetch prices concurrently
        tasks = []
        valid_regions = []

        for region in regions:
            if self.supports_region(region):
                valid_regions.append(region)
                tasks.append(self.get_current_price(region))

        if tasks:
            prices = await asyncio.gather(*tasks, return_exceptions=True)

            for region, price in zip(valid_regions, prices):
                if isinstance(price, Exception):
                    self.logger.warning(
                        "comparison_fetch_failed",
                        region=region.value,
                        error=str(price),
                    )
                else:
                    results[region] = price

        return results

    async def get_renewable_share(
        self,
        region: PricingRegion,
        year: Optional[int] = None,
    ) -> dict:
        """
        Get renewable energy share in electricity generation.

        Args:
            region: The pricing region
            year: Specific year (optional)

        Returns:
            Dictionary containing renewable energy statistics
        """
        if not self.supports_region(region):
            raise ValueError(f"Region {region} not supported by IEA")

        await self._check_rate_limit()

        country_code = self._get_iea_country(region)

        params = {"country": country_code}
        if year:
            params["year"] = year

        response = await self.get(
            endpoint="/generation/renewable",
            params=params,
        )

        return response.json()

    async def health_check(self) -> bool:
        """
        Check if the IEA API is available.

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


# Import timedelta for the forecast method
from datetime import timedelta
