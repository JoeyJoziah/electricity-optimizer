"""
Abstract Base Class for Pricing API Clients

Provides common functionality for all pricing API integrations including:
- HTTP client management with connection pooling
- Retry logic with exponential backoff
- Circuit breaker pattern for fault tolerance
- Structured logging
- Data model definitions
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Optional, TypeVar, Generic
import asyncio
import hashlib
import json

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Type variable for generic response handling
T = TypeVar("T")


# =============================================================================
# ENUMS
# =============================================================================


class PriceUnit(str, Enum):
    """Standardized price units across all APIs"""

    KWH = "kWh"  # Price per kilowatt-hour
    MWH = "MWh"  # Price per megawatt-hour
    GBP_KWH = "GBP/kWh"
    EUR_KWH = "EUR/kWh"
    USD_KWH = "USD/kWh"
    CENTS_KWH = "cents/kWh"


class PricingRegion(str, Enum):
    """Supported regions across all pricing APIs"""

    # UK
    UK = "UK"
    UK_SCOTLAND = "UK_SCOTLAND"
    UK_WALES = "UK_WALES"

    # EU
    IRELAND = "IE"
    GERMANY = "DE"
    FRANCE = "FR"
    SPAIN = "ES"
    ITALY = "IT"
    NETHERLANDS = "NL"
    BELGIUM = "BE"
    AUSTRIA = "AT"

    # US (selected states)
    US_CA = "US_CA"  # California
    US_TX = "US_TX"  # Texas
    US_NY = "US_NY"  # New York
    US_FL = "US_FL"  # Florida
    US_IL = "US_IL"  # Illinois
    US_PA = "US_PA"  # Pennsylvania
    US_OH = "US_OH"  # Ohio
    US_GA = "US_GA"  # Georgia
    US_NC = "US_NC"  # North Carolina
    US_MI = "US_MI"  # Michigan
    US_CT = "US_CT"  # Connecticut

    # Global/Other
    JAPAN = "JP"
    AUSTRALIA = "AU"
    CANADA = "CA"
    CHINA = "CN"
    INDIA = "IN"
    BRAZIL = "BR"


class CircuitState(str, Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


# =============================================================================
# EXCEPTIONS
# =============================================================================


class APIError(Exception):
    """Base exception for API errors"""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        api_name: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        self.api_name = api_name

    def __str__(self) -> str:
        parts = [self.message]
        if self.api_name:
            parts.insert(0, f"[{self.api_name}]")
        if self.status_code:
            parts.append(f"(HTTP {self.status_code})")
        return " ".join(parts)


class RateLimitError(APIError):
    """Raised when API rate limit is exceeded"""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class AuthenticationError(APIError):
    """Raised when API authentication fails"""

    def __init__(self, message: str = "Authentication failed", **kwargs):
        super().__init__(message, **kwargs)


class ServiceUnavailableError(APIError):
    """Raised when the API service is unavailable"""

    def __init__(self, message: str = "Service unavailable", **kwargs):
        super().__init__(message, **kwargs)


class CircuitBreakerOpenError(APIError):
    """Raised when circuit breaker is open"""

    def __init__(self, message: str = "Circuit breaker is open", **kwargs):
        super().__init__(message, **kwargs)


# =============================================================================
# DATA MODELS
# =============================================================================


@dataclass
class PriceData:
    """
    Normalized price data from any API source.

    All prices are converted to a common format for easy comparison.
    """

    region: PricingRegion
    timestamp: datetime
    price: Decimal
    unit: PriceUnit
    currency: str

    # Optional metadata
    supplier: Optional[str] = None
    tariff_name: Optional[str] = None
    source_api: Optional[str] = None

    # Price breakdown (if available)
    energy_cost: Optional[Decimal] = None
    network_cost: Optional[Decimal] = None
    taxes: Optional[Decimal] = None
    levies: Optional[Decimal] = None

    # Additional context
    is_peak: Optional[bool] = None
    is_renewable: Optional[bool] = None
    carbon_intensity: Optional[float] = None  # gCO2/kWh

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "region": self.region.value,
            "timestamp": self.timestamp.isoformat(),
            "price": str(self.price),
            "unit": self.unit.value,
            "currency": self.currency,
            "supplier": self.supplier,
            "tariff_name": self.tariff_name,
            "source_api": self.source_api,
            "energy_cost": str(self.energy_cost) if self.energy_cost else None,
            "network_cost": str(self.network_cost) if self.network_cost else None,
            "taxes": str(self.taxes) if self.taxes else None,
            "levies": str(self.levies) if self.levies else None,
            "is_peak": self.is_peak,
            "is_renewable": self.is_renewable,
            "carbon_intensity": self.carbon_intensity,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PriceData":
        """Create from dictionary"""
        return cls(
            region=PricingRegion(data["region"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            price=Decimal(data["price"]),
            unit=PriceUnit(data["unit"]),
            currency=data["currency"],
            supplier=data.get("supplier"),
            tariff_name=data.get("tariff_name"),
            source_api=data.get("source_api"),
            energy_cost=Decimal(data["energy_cost"]) if data.get("energy_cost") else None,
            network_cost=Decimal(data["network_cost"]) if data.get("network_cost") else None,
            taxes=Decimal(data["taxes"]) if data.get("taxes") else None,
            levies=Decimal(data["levies"]) if data.get("levies") else None,
            is_peak=data.get("is_peak"),
            is_renewable=data.get("is_renewable"),
            carbon_intensity=data.get("carbon_intensity"),
        )

    def convert_to_kwh(self) -> "PriceData":
        """Convert price to per-kWh basis if in MWh"""
        if self.unit == PriceUnit.MWH:
            return PriceData(
                region=self.region,
                timestamp=self.timestamp,
                price=self.price / 1000,
                unit=PriceUnit.KWH,
                currency=self.currency,
                supplier=self.supplier,
                tariff_name=self.tariff_name,
                source_api=self.source_api,
                energy_cost=self.energy_cost / 1000 if self.energy_cost else None,
                network_cost=self.network_cost / 1000 if self.network_cost else None,
                taxes=self.taxes / 1000 if self.taxes else None,
                levies=self.levies / 1000 if self.levies else None,
                is_peak=self.is_peak,
                is_renewable=self.is_renewable,
                carbon_intensity=self.carbon_intensity,
            )
        return self


@dataclass
class PriceForecast:
    """
    Price forecast data with confidence intervals.
    """

    region: PricingRegion
    forecast_generated_at: datetime
    forecast_horizon_hours: int
    source_api: str

    # List of forecasted prices
    prices: list[PriceData] = field(default_factory=list)

    # Forecast metadata
    model_version: Optional[str] = None
    confidence_level: Optional[float] = None  # 0.0 to 1.0

    # Statistical bounds (if available)
    lower_bound: Optional[list[Decimal]] = None
    upper_bound: Optional[list[Decimal]] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "region": self.region.value,
            "forecast_generated_at": self.forecast_generated_at.isoformat(),
            "forecast_horizon_hours": self.forecast_horizon_hours,
            "source_api": self.source_api,
            "prices": [p.to_dict() for p in self.prices],
            "model_version": self.model_version,
            "confidence_level": self.confidence_level,
            "lower_bound": [str(b) for b in self.lower_bound] if self.lower_bound else None,
            "upper_bound": [str(b) for b in self.upper_bound] if self.upper_bound else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PriceForecast":
        """Create from dictionary"""
        return cls(
            region=PricingRegion(data["region"]),
            forecast_generated_at=datetime.fromisoformat(data["forecast_generated_at"]),
            forecast_horizon_hours=data["forecast_horizon_hours"],
            source_api=data["source_api"],
            prices=[PriceData.from_dict(p) for p in data.get("prices", [])],
            model_version=data.get("model_version"),
            confidence_level=data.get("confidence_level"),
            lower_bound=[Decimal(b) for b in data["lower_bound"]] if data.get("lower_bound") else None,
            upper_bound=[Decimal(b) for b in data["upper_bound"]] if data.get("upper_bound") else None,
        )


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close from half-open
    timeout_seconds: int = 60  # Time before trying again (half-open)
    half_open_max_calls: int = 3  # Max calls in half-open state


class CircuitBreaker:
    """
    Circuit breaker implementation for fault tolerance.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Service is failing, reject requests immediately
    - HALF_OPEN: Testing if service recovered
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, checking for timeout transition"""
        if self._state == CircuitState.OPEN and self._last_failure_time:
            elapsed = (datetime.utcnow() - self._last_failure_time).total_seconds()
            if elapsed >= self.config.timeout_seconds:
                return CircuitState.HALF_OPEN
        return self._state

    async def can_execute(self) -> bool:
        """Check if request can be executed"""
        async with self._lock:
            current_state = self.state

            if current_state == CircuitState.CLOSED:
                return True

            if current_state == CircuitState.OPEN:
                return False

            # HALF_OPEN state
            if self._half_open_calls < self.config.half_open_max_calls:
                self._half_open_calls += 1
                return True

            return False

    async def record_success(self) -> None:
        """Record a successful call"""
        async with self._lock:
            current = self.state
            if current == CircuitState.HALF_OPEN:
                # Materialize virtual HALF_OPEN transition
                if self._state != CircuitState.HALF_OPEN:
                    self._state = CircuitState.HALF_OPEN
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition_to_closed()
            elif current == CircuitState.CLOSED:
                self._failure_count = 0

    async def record_failure(self) -> None:
        """Record a failed call"""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.utcnow()

            current = self.state
            if current == CircuitState.HALF_OPEN:
                self._transition_to_open()
            elif self._failure_count >= self.config.failure_threshold:
                self._transition_to_open()

    def _transition_to_open(self) -> None:
        """Transition to OPEN state"""
        logger.warning(
            "circuit_breaker_opened",
            name=self.name,
            failure_count=self._failure_count,
        )
        self._state = CircuitState.OPEN
        self._success_count = 0
        self._half_open_calls = 0

    def _transition_to_closed(self) -> None:
        """Transition to CLOSED state"""
        logger.info(
            "circuit_breaker_closed",
            name=self.name,
            success_count=self._success_count,
        )
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0

    async def reset(self) -> None:
        """Manually reset the circuit breaker"""
        async with self._lock:
            self._transition_to_closed()


# =============================================================================
# RETRY CONFIGURATION
# =============================================================================


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""

    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True  # Add randomness to prevent thundering herd

    # Retryable status codes
    retryable_status_codes: tuple[int, ...] = (408, 429, 500, 502, 503, 504)

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number"""
        import random

        delay = min(
            self.base_delay_seconds * (self.exponential_base ** attempt),
            self.max_delay_seconds
        )

        if self.jitter:
            delay = delay * (0.5 + random.random())

        return delay


# =============================================================================
# BASE CLIENT
# =============================================================================


class BasePricingClient(ABC):
    """
    Abstract base class for all pricing API clients.

    Provides common functionality:
    - HTTP client management
    - Retry logic with exponential backoff
    - Circuit breaker pattern
    - Request deduplication
    - Structured logging
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        client_name: str,
        timeout: float = 30.0,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client_name = client_name
        self.timeout = timeout
        self.retry_config = retry_config or RetryConfig()

        # Circuit breaker for fault tolerance
        self.circuit_breaker = CircuitBreaker(
            name=client_name,
            config=circuit_breaker_config,
        )

        # HTTP client (lazy initialization)
        self._client: Optional[httpx.AsyncClient] = None

        # Request deduplication
        self._pending_requests: dict[str, asyncio.Task] = {}
        self._pending_lock = asyncio.Lock()

        # Logger with context
        self.logger = logger.bind(api_client=client_name)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers=self._get_default_headers(),
                follow_redirects=True,
            )
        return self._client

    @abstractmethod
    def _get_default_headers(self) -> dict[str, str]:
        """Get default headers for requests. Override in subclasses."""
        pass

    async def close(self) -> None:
        """Close the HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "BasePricingClient":
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit"""
        await self.close()

    def _generate_cache_key(self, endpoint: str, params: Optional[dict] = None) -> str:
        """Generate a cache key for request deduplication"""
        key_data = {
            "client": self.client_name,
            "endpoint": endpoint,
            "params": params or {},
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]

    async def _execute_with_retry(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> httpx.Response:
        """
        Execute HTTP request with retry logic and circuit breaker.
        """
        # Check circuit breaker
        if not await self.circuit_breaker.can_execute():
            raise CircuitBreakerOpenError(
                f"Circuit breaker open for {self.client_name}",
                api_name=self.client_name,
            )

        last_exception: Optional[Exception] = None

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                client = await self._get_client()

                self.logger.debug(
                    "api_request_start",
                    method=method,
                    endpoint=endpoint,
                    attempt=attempt + 1,
                )

                response = await client.request(
                    method=method,
                    url=endpoint,
                    params=params,
                    json=json_body,
                )

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    await self.circuit_breaker.record_failure()
                    raise RateLimitError(
                        retry_after=retry_after,
                        status_code=429,
                        api_name=self.client_name,
                    )

                # Handle auth errors
                if response.status_code in (401, 403):
                    await self.circuit_breaker.record_failure()
                    raise AuthenticationError(
                        status_code=response.status_code,
                        response_body=response.text,
                        api_name=self.client_name,
                    )

                # Handle server errors
                if response.status_code >= 500:
                    await self.circuit_breaker.record_failure()
                    if response.status_code in self.retry_config.retryable_status_codes:
                        if attempt < self.retry_config.max_retries:
                            delay = self.retry_config.get_delay(attempt)
                            self.logger.warning(
                                "api_request_retry",
                                status_code=response.status_code,
                                attempt=attempt + 1,
                                delay=delay,
                            )
                            await asyncio.sleep(delay)
                            continue

                    raise ServiceUnavailableError(
                        status_code=response.status_code,
                        response_body=response.text,
                        api_name=self.client_name,
                    )

                # Check for other errors
                response.raise_for_status()

                # Success
                await self.circuit_breaker.record_success()

                self.logger.info(
                    "api_request_success",
                    method=method,
                    endpoint=endpoint,
                    status_code=response.status_code,
                )

                return response

            except httpx.TimeoutException as e:
                last_exception = e
                await self.circuit_breaker.record_failure()

                if attempt < self.retry_config.max_retries:
                    delay = self.retry_config.get_delay(attempt)
                    self.logger.warning(
                        "api_request_timeout",
                        attempt=attempt + 1,
                        delay=delay,
                    )
                    await asyncio.sleep(delay)
                    continue

            except httpx.HTTPStatusError as e:
                last_exception = e
                if e.response.status_code in self.retry_config.retryable_status_codes:
                    await self.circuit_breaker.record_failure()
                    if attempt < self.retry_config.max_retries:
                        delay = self.retry_config.get_delay(attempt)
                        await asyncio.sleep(delay)
                        continue
                raise

            except (RateLimitError, AuthenticationError, ServiceUnavailableError):
                raise

            except Exception as e:
                last_exception = e
                await self.circuit_breaker.record_failure()
                self.logger.error(
                    "api_request_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise APIError(
                    message=str(e),
                    api_name=self.client_name,
                ) from e

        # All retries exhausted
        raise APIError(
            message=f"Request failed after {self.retry_config.max_retries + 1} attempts",
            api_name=self.client_name,
        ) from last_exception

    async def _request_with_deduplication(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> httpx.Response:
        """
        Execute request with deduplication to prevent duplicate concurrent requests.
        """
        cache_key = self._generate_cache_key(endpoint, params)

        async with self._pending_lock:
            if cache_key in self._pending_requests:
                # Wait for existing request
                self.logger.debug(
                    "request_deduplicated",
                    endpoint=endpoint,
                    cache_key=cache_key,
                )
                return await self._pending_requests[cache_key]

            # Create new request task
            task = asyncio.create_task(
                self._execute_with_retry(method, endpoint, params, json_body)
            )
            self._pending_requests[cache_key] = task

        try:
            result = await task
            return result
        finally:
            async with self._pending_lock:
                self._pending_requests.pop(cache_key, None)

    async def get(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        deduplicate: bool = True,
    ) -> httpx.Response:
        """Make GET request"""
        if deduplicate:
            return await self._request_with_deduplication("GET", endpoint, params)
        return await self._execute_with_retry("GET", endpoint, params)

    async def post(
        self,
        endpoint: str,
        json_body: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> httpx.Response:
        """Make POST request"""
        return await self._execute_with_retry("POST", endpoint, params, json_body)

    # Abstract methods to be implemented by subclasses

    @abstractmethod
    async def get_current_price(self, region: PricingRegion) -> PriceData:
        """Get current electricity price for a region"""
        pass

    @abstractmethod
    async def get_price_forecast(
        self,
        region: PricingRegion,
        hours: int = 24,
    ) -> PriceForecast:
        """Get price forecast for a region"""
        pass

    @abstractmethod
    def get_supported_regions(self) -> list[PricingRegion]:
        """Get list of supported regions for this API"""
        pass

    def supports_region(self, region: PricingRegion) -> bool:
        """Check if region is supported by this API"""
        return region in self.get_supported_regions()
