"""
NREL (National Renewable Energy Laboratory) API Client

Provides access to US utility rates and electricity pricing data.

API Documentation: https://developer.nrel.gov/docs/electricity/
Rate Limit: 1000 requests/hour

Supported Regions:
- All US states via ZIP code or state abbreviation
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


# Build NREL_REGION_MAP dynamically for all US regions.
# PricingRegion is aliased to models.region.Region (all 50 states + DC).
NREL_REGION_MAP: dict[PricingRegion, str] = {
    r: r.state_code for r in PricingRegion if r.is_us
}

# Representative ZIP codes for each state (for API calls).
# Capital / major-city ZIP used for rate lookups.
STATE_ZIP_CODES: dict[str, str] = {
    "AL": "35203",  # Birmingham
    "AK": "99501",  # Anchorage
    "AZ": "85001",  # Phoenix
    "AR": "72201",  # Little Rock
    "CA": "90210",  # Los Angeles
    "CO": "80202",  # Denver
    "CT": "06510",  # New Haven
    "DE": "19901",  # Dover
    "DC": "20001",  # Washington
    "FL": "33101",  # Miami
    "GA": "30301",  # Atlanta
    "HI": "96801",  # Honolulu
    "ID": "83701",  # Boise
    "IL": "60601",  # Chicago
    "IN": "46201",  # Indianapolis
    "IA": "50301",  # Des Moines
    "KS": "66101",  # Kansas City
    "KY": "40201",  # Louisville
    "LA": "70112",  # New Orleans
    "ME": "04101",  # Portland
    "MD": "21201",  # Baltimore
    "MA": "02101",  # Boston
    "MI": "48201",  # Detroit
    "MN": "55401",  # Minneapolis
    "MS": "39201",  # Jackson
    "MO": "63101",  # St. Louis
    "MT": "59601",  # Helena
    "NE": "68101",  # Omaha
    "NV": "89101",  # Las Vegas
    "NH": "03301",  # Concord
    "NJ": "07101",  # Newark
    "NM": "87101",  # Albuquerque
    "NY": "10001",  # New York City
    "NC": "27601",  # Raleigh
    "ND": "58501",  # Bismarck
    "OH": "43215",  # Columbus
    "OK": "73101",  # Oklahoma City
    "OR": "97201",  # Portland
    "PA": "19101",  # Philadelphia
    "RI": "02901",  # Providence
    "SC": "29201",  # Columbia
    "SD": "57101",  # Sioux Falls
    "TN": "37201",  # Nashville
    "TX": "75201",  # Dallas
    "UT": "84101",  # Salt Lake City
    "VT": "05601",  # Montpelier
    "VA": "23219",  # Richmond
    "WA": "98101",  # Seattle
    "WV": "25301",  # Charleston
    "WI": "53201",  # Milwaukee
    "WY": "82001",  # Cheyenne
}

# Utility sector types
SECTOR_RESIDENTIAL = "residential"
SECTOR_COMMERCIAL = "commercial"
SECTOR_INDUSTRIAL = "industrial"


class NRELClient(BasePricingClient):
    """
    Async client for the NREL Utility Rates API.

    Provides access to US electricity utility rates including:
    - Current rates by location
    - Rate schedules (time-of-use, tiered)
    - Net metering policies
    - Demand charges

    Example usage:
        ```python
        async with NRELClient(api_key="your-nrel-key") as client:
            # Get current rate by ZIP code
            price = await client.get_current_price(PricingRegion.US_CA)
            print(f"Average rate: {price.price} {price.currency}/{price.unit}")

            # Get detailed rate structure
            rates = await client.get_utility_rates(zip_code="90210")
            print(f"Utility: {rates['utility_name']}")
        ```
    """

    BASE_URL = "https://developer.nrel.gov/api/utility_rates/v3"

    def __init__(
        self,
        api_key: str,
        timeout: float = 30.0,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        rate_limiter: Optional[RateLimiter] = None,
        cache: Optional[PricingCache] = None,
        default_sector: str = SECTOR_RESIDENTIAL,
    ):
        """
        Initialize NREL client.

        Args:
            api_key: NREL API key
            timeout: Request timeout in seconds
            retry_config: Configuration for retry behavior
            circuit_breaker_config: Configuration for circuit breaker
            rate_limiter: Optional rate limiter instance
            cache: Optional cache instance
            default_sector: Default rate sector (residential/commercial/industrial)
        """
        super().__init__(
            api_key=api_key,
            base_url=self.BASE_URL,
            client_name="nrel",
            timeout=timeout,
            retry_config=retry_config,
            circuit_breaker_config=circuit_breaker_config,
        )

        # Rate limiter (1000 requests/hour for NREL)
        self.rate_limiter = rate_limiter or create_api_rate_limiter(
            api_name="nrel",
            requests_per_hour=1000,
        )

        self.cache = cache
        self.default_sector = default_sector

        self.logger = logger.bind(api_client="nrel")

    def _get_default_headers(self) -> dict[str, str]:
        """Get default headers for NREL API"""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ElectricityOptimizer/1.0",
        }

    def get_supported_regions(self) -> list[PricingRegion]:
        """Get list of supported regions"""
        return list(NREL_REGION_MAP.keys())

    def _get_nrel_state(self, region: PricingRegion) -> str:
        """Convert PricingRegion to NREL state code"""
        if region not in NREL_REGION_MAP:
            raise ValueError(f"Region {region} not supported by NREL API")
        return NREL_REGION_MAP[region]

    def _get_zip_code(self, region: PricingRegion) -> str:
        """Get representative ZIP code for a region"""
        state = self._get_nrel_state(region)
        return STATE_ZIP_CODES.get(state, "90210")

    def _parse_rate_response(
        self,
        data: dict,
        region: PricingRegion,
        sector: str,
    ) -> PriceData:
        """Parse NREL rate response to PriceData"""
        # NREL returns rates in different formats based on structure
        outputs = data.get("outputs", {})

        # Get the appropriate rate based on sector
        if sector == SECTOR_RESIDENTIAL:
            rate_cents = outputs.get("residential", 0)
        elif sector == SECTOR_COMMERCIAL:
            rate_cents = outputs.get("commercial", 0)
        else:
            rate_cents = outputs.get("industrial", 0)

        # Convert cents/kWh to dollars/kWh
        price = Decimal(str(rate_cents)) / 100

        # Extract utility info
        utility_info = outputs.get("utility_info", {})

        return PriceData(
            region=region,
            timestamp=datetime.now(timezone.utc),
            price=price,
            unit=PriceUnit.KWH,
            currency="USD",
            supplier=utility_info.get("utility_name"),
            tariff_name=utility_info.get("rate_schedule"),
            source_api="nrel",
            # NREL doesn't provide detailed breakdown by default
            is_peak=None,
            is_renewable=None,
            carbon_intensity=None,
        )

    async def _check_rate_limit(self) -> None:
        """Wait for rate limit if necessary"""
        if self.rate_limiter:
            acquired = await self.rate_limiter.wait_for_token(
                key="nrel",
                timeout=30.0,
            )
            if not acquired:
                raise APIError(
                    "Rate limit timeout - could not acquire token",
                    api_name="nrel",
                )

    async def get_current_price(self, region: PricingRegion) -> PriceData:
        """
        Get current electricity rate for a region.

        Uses the average residential rate for the state.

        Args:
            region: The pricing region (US state)

        Returns:
            Current price data

        Raises:
            APIError: If API request fails
            ValueError: If region not supported
        """
        if not self.supports_region(region):
            raise ValueError(f"Region {region} not supported by NREL")

        # Check cache first
        if self.cache:
            cache_key = self.cache.current_price_key("nrel", region.value)
            cached = await self.cache.get(cache_key)
            if cached:
                self.logger.debug("cache_hit", region=region.value)
                return PriceData.from_dict(cached)

        await self._check_rate_limit()

        zip_code = self._get_zip_code(region)

        self.logger.info(
            "fetching_current_rate",
            region=region.value,
            zip_code=zip_code,
        )

        # NREL uses api_key as a query parameter
        response = await self.get(
            endpoint=".json",
            params={
                "api_key": self.api_key,
                "lat": None,  # Will be looked up from ZIP
                "lon": None,
                "address": zip_code,
            },
        )

        data = response.json()

        result = self._parse_rate_response(data, region, self.default_sector)

        # Cache the result
        if self.cache:
            await self.cache.set_current_price(
                api="nrel",
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

        Note: NREL doesn't provide forecasts directly, so this returns
        current rates projected forward with typical TOU patterns.

        Args:
            region: The pricing region
            hours: Forecast horizon in hours

        Returns:
            Price forecast (based on current rates and TOU patterns)
        """
        if not self.supports_region(region):
            raise ValueError(f"Region {region} not supported by NREL")

        # Check cache first
        if self.cache:
            cache_key = self.cache.forecast_key("nrel", region.value, hours)
            cached = await self.cache.get(cache_key)
            if cached:
                return PriceForecast.from_dict(cached)

        # Get current rate
        current_price = await self.get_current_price(region)

        # Generate forecast based on typical TOU patterns
        # This is a simplified model - real implementation would use
        # actual TOU schedules from the utility
        prices = []
        base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

        for hour_offset in range(hours):
            forecast_time = base_time + timedelta(hours=hour_offset)
            hour_of_day = forecast_time.hour

            # Apply simple TOU multiplier
            # Peak: 4 PM - 9 PM (hours 16-21)
            # Off-peak: 9 PM - 4 PM
            if 16 <= hour_of_day <= 21:
                multiplier = Decimal("1.3")  # 30% higher during peak
                is_peak = True
            elif 0 <= hour_of_day <= 6:
                multiplier = Decimal("0.8")  # 20% lower overnight
                is_peak = False
            else:
                multiplier = Decimal("1.0")
                is_peak = False

            prices.append(
                PriceData(
                    region=region,
                    timestamp=forecast_time,
                    price=current_price.price * multiplier,
                    unit=PriceUnit.KWH,
                    currency="USD",
                    supplier=current_price.supplier,
                    tariff_name=current_price.tariff_name,
                    source_api="nrel",
                    is_peak=is_peak,
                )
            )

        result = PriceForecast(
            region=region,
            forecast_generated_at=datetime.now(timezone.utc),
            forecast_horizon_hours=hours,
            source_api="nrel",
            prices=prices,
            model_version="simple_tou_v1",
            confidence_level=0.7,  # Lower confidence for synthetic forecast
        )

        # Cache the result
        if self.cache:
            await self.cache.set_forecast(
                api="nrel",
                region=region.value,
                hours=hours,
                data=result.to_dict(),
            )

        return result

    async def get_utility_rates(
        self,
        zip_code: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        address: Optional[str] = None,
    ) -> dict:
        """
        Get detailed utility rate information for a location.

        At least one of zip_code, (lat, lon), or address must be provided.

        Args:
            zip_code: ZIP code
            lat: Latitude
            lon: Longitude
            address: Street address

        Returns:
            Dictionary containing utility rate details
        """
        await self._check_rate_limit()

        params = {"api_key": self.api_key}

        if zip_code:
            params["address"] = zip_code
        elif lat is not None and lon is not None:
            params["lat"] = lat
            params["lon"] = lon
        elif address:
            params["address"] = address
        else:
            raise ValueError(
                "Must provide zip_code, (lat, lon), or address"
            )

        self.logger.info("fetching_utility_rates", params=params)

        response = await self.get(
            endpoint=".json",
            params=params,
        )

        return response.json()

    async def get_rates_by_utility_id(self, utility_id: str) -> dict:
        """
        Get rates for a specific utility by its NREL ID.

        Args:
            utility_id: NREL utility identifier

        Returns:
            Dictionary containing utility rate details
        """
        await self._check_rate_limit()

        response = await self.get(
            endpoint=".json",
            params={
                "api_key": self.api_key,
                "utility_id": utility_id,
            },
        )

        return response.json()

    async def get_all_utilities(self, state: str) -> list[dict]:
        """
        Get list of all utilities in a state.

        Args:
            state: Two-letter state abbreviation

        Returns:
            List of utility information dictionaries
        """
        await self._check_rate_limit()

        # NREL has a separate endpoint for utility listings
        # This is a simplified version - actual implementation
        # would use the full API capabilities
        self.logger.info("fetching_utilities", state=state)

        # Use a central location in the state
        zip_code = STATE_ZIP_CODES.get(state.upper())
        if not zip_code:
            raise ValueError(f"Unknown state: {state}")

        response = await self.get(
            endpoint=".json",
            params={
                "api_key": self.api_key,
                "address": zip_code,
            },
        )

        data = response.json()

        # Extract utility info
        outputs = data.get("outputs", {})
        utility_info = outputs.get("utility_info", {})

        return [utility_info] if utility_info else []

    async def health_check(self) -> bool:
        """
        Check if the NREL API is available.

        Returns:
            True if API is healthy
        """
        try:
            # Use a known ZIP code for health check
            response = await self.get(
                endpoint=".json",
                params={
                    "api_key": self.api_key,
                    "address": "90210",
                },
                deduplicate=False,
            )
            return response.status_code == 200
        except Exception as e:
            self.logger.warning("health_check_failed", error=str(e))
            return False
