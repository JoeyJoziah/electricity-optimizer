"""
EIA (Energy Information Administration) API Client

Provides access to US energy price data across all utility types:
- Electricity average retail prices by state
- Natural gas residential prices
- Heating oil and propane weekly surveys

API Documentation: https://www.eia.gov/opendata/documentation.php
API Version: v2
Rate Limit: Generous (no hard limit with API key), recommended <100/min
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
from models.utility import UtilityType

logger = structlog.get_logger(__name__)


# EIA series IDs for electricity average retail price by state
# Format: ELEC.PRICE.{state}-RES.M (monthly residential)
def _elec_series(state: str) -> str:
    return f"ELEC.PRICE.{state}-RES.M"


# EIA series IDs for natural gas residential price by state
# Format: NG.N3010{state}3.M (monthly residential)
def _gas_series(state: str) -> str:
    return f"NG.N3010{state}3.M"


# EIA petroleum product prices (heating oil, propane)
# Uses the weekly survey data
HEATING_OIL_SERIES = "PET.W_EPD2F_PRS_NUS_DPG.W"  # US average
PROPANE_SERIES = "PET.W_EPLLPA_PRS_NUS_DPG.W"      # US average

# State-level heating oil series (Northeast states)
HEATING_OIL_STATE_SERIES = {
    "CT": "PET.W_EPD2F_PRS_SCT_DPG.W",
    "MA": "PET.W_EPD2F_PRS_SMA_DPG.W",
    "NY": "PET.W_EPD2F_PRS_SNY_DPG.W",
    "NJ": "PET.W_EPD2F_PRS_SNJ_DPG.W",
    "PA": "PET.W_EPD2F_PRS_SPA_DPG.W",
    "ME": "PET.W_EPD2F_PRS_SME_DPG.W",
    "NH": "PET.W_EPD2F_PRS_SNH_DPG.W",
    "VT": "PET.W_EPD2F_PRS_SVT_DPG.W",
    "RI": "PET.W_EPD2F_PRS_SRI_DPG.W",
}

# State-level propane series
PROPANE_STATE_SERIES = {
    "CT": "PET.W_EPLLPA_PRS_SCT_DPG.W",
    "MA": "PET.W_EPLLPA_PRS_SMA_DPG.W",
    "NY": "PET.W_EPLLPA_PRS_SNY_DPG.W",
    "NJ": "PET.W_EPLLPA_PRS_SNJ_DPG.W",
    "PA": "PET.W_EPLLPA_PRS_SPA_DPG.W",
    "ME": "PET.W_EPLLPA_PRS_SME_DPG.W",
    "NH": "PET.W_EPLLPA_PRS_SNH_DPG.W",
    "VT": "PET.W_EPLLPA_PRS_SVT_DPG.W",
}


class EIAClient(BasePricingClient):
    """
    Async client for the EIA Open Data API v2.

    Fetches energy prices across utility types:
    - Electricity: average retail prices by state (monthly)
    - Natural gas: residential prices by state (monthly)
    - Heating oil: weekly survey prices (national + state where available)
    - Propane: weekly survey prices (national + state where available)

    Example usage:
        ```python
        async with EIAClient(api_key="your-eia-key") as client:
            price = await client.get_electricity_price(PricingRegion.US_CT)
            gas = await client.get_gas_price(PricingRegion.US_CT)
            oil = await client.get_heating_oil_price(PricingRegion.US_CT)
        ```
    """

    BASE_URL = "https://api.eia.gov/v2"

    def __init__(
        self,
        api_key: str,
        timeout: float = 30.0,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        rate_limiter: Optional[RateLimiter] = None,
        cache: Optional[PricingCache] = None,
    ):
        super().__init__(
            api_key=api_key,
            base_url=self.BASE_URL,
            client_name="eia",
            timeout=timeout,
            retry_config=retry_config,
            circuit_breaker_config=circuit_breaker_config,
        )
        self.rate_limiter = rate_limiter or create_api_rate_limiter(
            api_name="eia",
            requests_per_hour=3000,
        )
        self.cache = cache
        self.logger = logger.bind(api_client="eia")

    def _get_default_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ElectricityOptimizer/1.0",
        }

    def get_supported_regions(self) -> list[PricingRegion]:
        """All US regions are supported via EIA"""
        return [r for r in PricingRegion if r.is_us]

    async def _check_rate_limit(self) -> None:
        if self.rate_limiter:
            acquired = await self.rate_limiter.wait_for_token(
                key="eia", timeout=30.0,
            )
            if not acquired:
                raise APIError("Rate limit timeout", api_name="eia")

    async def _fetch_series(self, route: str, params: dict) -> dict:
        """Fetch data from EIA v2 API."""
        await self._check_rate_limit()
        params["api_key"] = self.api_key
        response = await self.get(endpoint=route, params=params)
        return response.json()

    # ------------------------------------------------------------------
    # Electricity
    # ------------------------------------------------------------------

    async def get_electricity_price(self, region: PricingRegion) -> PriceData:
        """
        Get latest average residential electricity price for a US state.

        Returns price in $/kWh (EIA reports in cents/kWh, we convert).
        """
        if not region.is_us:
            raise ValueError(f"EIA only supports US regions, got {region}")

        state = region.state_code

        # Check cache
        if self.cache:
            cache_key = self.cache.current_price_key("eia_elec", region.value)
            cached = await self.cache.get(cache_key)
            if cached:
                return PriceData.from_dict(cached)

        data = await self._fetch_series(
            route="/electricity/retail-sales/data/",
            params={
                "frequency": "monthly",
                "data[0]": "price",
                "facets[stateid][]": state,
                "facets[sectorid][]": "RES",
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "length": "1",
            },
        )

        rows = data.get("response", {}).get("data", [])
        if not rows:
            raise APIError(f"No electricity data for {state}", api_name="eia")

        row = rows[0]
        # EIA returns cents/kWh -- convert to dollars/kWh
        price_cents = Decimal(str(row.get("price", 0)))
        price_dollars = price_cents / 100

        result = PriceData(
            region=region,
            timestamp=datetime.now(timezone.utc),
            price=price_dollars,
            unit=PriceUnit.KWH,
            currency="USD",
            supplier=None,
            source_api="eia",
        )

        if self.cache:
            await self.cache.set_current_price(
                api="eia_elec", region=region.value, data=result.to_dict(),
            )

        return result

    # ------------------------------------------------------------------
    # Natural Gas
    # ------------------------------------------------------------------

    async def get_gas_price(self, region: PricingRegion) -> PriceData:
        """
        Get latest residential natural gas price for a US state.

        Returns price in $/therm (EIA reports in $/Mcf, we convert).
        1 Mcf ~ 10.37 therms.
        """
        if not region.is_us:
            raise ValueError(f"EIA only supports US regions, got {region}")

        state = region.state_code

        if self.cache:
            cache_key = self.cache.current_price_key("eia_gas", region.value)
            cached = await self.cache.get(cache_key)
            if cached:
                return PriceData.from_dict(cached)

        data = await self._fetch_series(
            route="/natural-gas/pri/sum/data/",
            params={
                "frequency": "monthly",
                "data[0]": "value",
                "facets[duoarea][]": f"S{state}",
                "facets[process][]": "PRS",
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "length": "1",
            },
        )

        rows = data.get("response", {}).get("data", [])
        if not rows:
            raise APIError(f"No gas data for {state}", api_name="eia")

        row = rows[0]
        # EIA returns $/Mcf. Convert to $/therm (1 Mcf ~ 10.37 therms).
        price_mcf = Decimal(str(row.get("value", 0)))
        price_therm = price_mcf / Decimal("10.37")

        result = PriceData(
            region=region,
            timestamp=datetime.now(timezone.utc),
            price=price_therm.quantize(Decimal("0.0001")),
            unit=PriceUnit.THERM,
            currency="USD",
            supplier=None,
            source_api="eia",
        )

        if self.cache:
            await self.cache.set_current_price(
                api="eia_gas", region=region.value, data=result.to_dict(),
            )

        return result

    # ------------------------------------------------------------------
    # Heating Oil
    # ------------------------------------------------------------------

    async def get_heating_oil_price(
        self, region: PricingRegion
    ) -> PriceData:
        """
        Get latest heating oil price ($/gallon).

        Uses state-level data for Northeast states, falls back to national average.
        """
        if not region.is_us:
            raise ValueError(f"EIA only supports US regions, got {region}")

        state = region.state_code

        if self.cache:
            cache_key = self.cache.current_price_key("eia_oil", region.value)
            cached = await self.cache.get(cache_key)
            if cached:
                return PriceData.from_dict(cached)

        # Use state-specific or national series
        series_id = HEATING_OIL_STATE_SERIES.get(
            state, HEATING_OIL_SERIES
        )

        data = await self._fetch_series(
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
        if not rows:
            raise APIError(
                f"No heating oil data for {state}", api_name="eia"
            )

        row = rows[0]
        price_gallon = Decimal(str(row.get("value", 0)))

        result = PriceData(
            region=region,
            timestamp=datetime.now(timezone.utc),
            price=price_gallon.quantize(Decimal("0.0001")),
            unit=PriceUnit.GALLON,
            currency="USD",
            supplier=None,
            source_api="eia",
        )

        if self.cache:
            await self.cache.set_current_price(
                api="eia_oil", region=region.value, data=result.to_dict(),
            )

        return result

    # ------------------------------------------------------------------
    # Propane
    # ------------------------------------------------------------------

    async def get_propane_price(self, region: PricingRegion) -> PriceData:
        """
        Get latest propane price ($/gallon).

        Uses state-level data where available, falls back to national average.
        """
        if not region.is_us:
            raise ValueError(f"EIA only supports US regions, got {region}")

        state = region.state_code

        if self.cache:
            cache_key = self.cache.current_price_key("eia_propane", region.value)
            cached = await self.cache.get(cache_key)
            if cached:
                return PriceData.from_dict(cached)

        series_id = PROPANE_STATE_SERIES.get(state, PROPANE_SERIES)

        data = await self._fetch_series(
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
        if not rows:
            raise APIError(f"No propane data for {state}", api_name="eia")

        row = rows[0]
        price_gallon = Decimal(str(row.get("value", 0)))

        result = PriceData(
            region=region,
            timestamp=datetime.now(timezone.utc),
            price=price_gallon.quantize(Decimal("0.0001")),
            unit=PriceUnit.GALLON,
            currency="USD",
            supplier=None,
            source_api="eia",
        )

        if self.cache:
            await self.cache.set_current_price(
                api="eia_propane", region=region.value, data=result.to_dict(),
            )

        return result

    # ------------------------------------------------------------------
    # Multi-utility convenience
    # ------------------------------------------------------------------

    async def get_price_by_utility_type(
        self,
        region: PricingRegion,
        utility_type: UtilityType,
    ) -> PriceData:
        """
        Get price for any supported utility type.

        Routes to the appropriate method based on utility_type.
        """
        dispatch = {
            UtilityType.ELECTRICITY: self.get_electricity_price,
            UtilityType.NATURAL_GAS: self.get_gas_price,
            UtilityType.HEATING_OIL: self.get_heating_oil_price,
            UtilityType.PROPANE: self.get_propane_price,
        }
        handler = dispatch.get(utility_type)
        if not handler:
            raise ValueError(
                f"Utility type {utility_type} not supported by EIA client"
            )
        return await handler(region)

    # ------------------------------------------------------------------
    # BasePricingClient abstract method implementations
    # ------------------------------------------------------------------

    async def get_current_price(self, region: PricingRegion) -> PriceData:
        """Get current electricity price (default utility type)."""
        return await self.get_electricity_price(region)

    async def get_price_forecast(
        self, region: PricingRegion, hours: int = 24,
    ) -> PriceForecast:
        """
        EIA does not provide forecasts. Returns current price projected forward.
        """
        current = await self.get_current_price(region)
        return PriceForecast(
            region=region,
            forecast_generated_at=datetime.now(timezone.utc),
            forecast_horizon_hours=hours,
            source_api="eia",
            prices=[current],
            model_version="eia_current_v1",
            confidence_level=0.5,
        )

    async def health_check(self) -> bool:
        """Check if EIA API is reachable."""
        try:
            response = await self.get(
                endpoint="/electricity/retail-sales/data/",
                params={
                    "api_key": self.api_key,
                    "frequency": "monthly",
                    "data[0]": "price",
                    "facets[stateid][]": "CT",
                    "facets[sectorid][]": "RES",
                    "length": "1",
                },
                deduplicate=False,
            )
            return response.status_code == 200
        except Exception as e:
            self.logger.warning("health_check_failed", error=str(e))
            return False
