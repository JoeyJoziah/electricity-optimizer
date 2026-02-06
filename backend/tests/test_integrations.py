"""
Comprehensive Test Suite for Pricing API Integrations

Tests cover:
- All three API clients (Flatpeak, NREL, IEA)
- Rate limiting behavior
- Caching functionality
- Circuit breaker patterns
- Error handling and retries
- Data normalization
"""

import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import json

import httpx
import pytest

# Import all components to test
from integrations.pricing_apis.base import (
    BasePricingClient,
    PriceData,
    PriceForecast,
    PricingRegion,
    PriceUnit,
    APIError,
    RateLimitError,
    AuthenticationError,
    ServiceUnavailableError,
    CircuitBreakerOpenError,
    CircuitBreaker,
    CircuitState,
    CircuitBreakerConfig,
    RetryConfig,
)
from integrations.pricing_apis.flatpeak import FlatpeakClient
from integrations.pricing_apis.nrel import NRELClient
from integrations.pricing_apis.iea import IEAClient
from integrations.pricing_apis.cache import (
    PricingCache,
    InMemoryCache,
    CacheConfig,
    CacheEntry,
)
from integrations.pricing_apis.rate_limiter import (
    TokenBucketLimiter,
    SlidingWindowLimiter,
    CompositeRateLimiter,
    create_api_rate_limiter,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx client"""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.is_closed = False
    return client


@pytest.fixture
def flatpeak_response_current():
    """Sample Flatpeak current price response"""
    return {
        "data": {
            "timestamp": "2024-01-15T10:30:00Z",
            "price": 0.2845,
            "unit": "kWh",
            "supplier": "Octopus Energy",
            "tariff_name": "Agile Octopus",
            "is_peak": False,
            "breakdown": {
                "energy": 0.15,
                "network": 0.08,
                "taxes": 0.0345,
                "levies": 0.02,
            },
            "renewable_percentage": 65,
            "carbon_intensity": 180.5,
        }
    }


@pytest.fixture
def flatpeak_response_forecast():
    """Sample Flatpeak forecast response"""
    base_time = datetime.now(timezone.utc)
    return {
        "data": {
            "model_version": "v2.1",
            "confidence": 0.85,
            "prices": [
                {
                    "timestamp": (base_time + timedelta(hours=i)).isoformat(),
                    "price": 0.25 + (0.05 * (i % 4)),
                    "unit": "kWh",
                    "is_peak": 16 <= (base_time.hour + i) % 24 <= 21,
                }
                for i in range(24)
            ],
        }
    }


@pytest.fixture
def nrel_response():
    """Sample NREL utility rates response"""
    return {
        "outputs": {
            "residential": 12.5,  # cents/kWh
            "commercial": 10.2,
            "industrial": 7.8,
            "utility_info": {
                "utility_name": "Pacific Gas & Electric",
                "rate_schedule": "E-TOU-C",
            },
        }
    }


@pytest.fixture
def iea_response():
    """Sample IEA price response"""
    return {
        "data": [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "price": 285.50,  # USD/MWh
                "unit": "MWh",
                "currency": "USD",
                "taxes": 45.0,
                "carbon_intensity": 320,
            }
        ]
    }


@pytest.fixture
def memory_cache():
    """Create an in-memory cache for testing"""
    return InMemoryCache(CacheConfig(current_price_ttl=60))


@pytest.fixture
def token_bucket_limiter():
    """Create a token bucket limiter for testing"""
    return TokenBucketLimiter(rate=10.0, capacity=10, name="test")


# =============================================================================
# BASE CLIENT TESTS
# =============================================================================


class TestPriceData:
    """Tests for PriceData model"""

    def test_create_price_data(self):
        """Test creating a PriceData instance"""
        price = PriceData(
            region=PricingRegion.UK,
            timestamp=datetime.now(timezone.utc),
            price=Decimal("0.2845"),
            unit=PriceUnit.KWH,
            currency="GBP",
            supplier="Octopus Energy",
        )

        assert price.region == PricingRegion.UK
        assert price.price == Decimal("0.2845")
        assert price.currency == "GBP"

    def test_price_data_serialization(self):
        """Test PriceData to_dict and from_dict"""
        original = PriceData(
            region=PricingRegion.GERMANY,
            timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            price=Decimal("0.35"),
            unit=PriceUnit.KWH,
            currency="EUR",
            energy_cost=Decimal("0.20"),
            taxes=Decimal("0.15"),
        )

        data = original.to_dict()
        restored = PriceData.from_dict(data)

        assert restored.region == original.region
        assert restored.price == original.price
        assert restored.energy_cost == original.energy_cost

    def test_convert_mwh_to_kwh(self):
        """Test MWh to kWh conversion"""
        price_mwh = PriceData(
            region=PricingRegion.UK,
            timestamp=datetime.now(timezone.utc),
            price=Decimal("285.0"),  # EUR/MWh
            unit=PriceUnit.MWH,
            currency="EUR",
        )

        price_kwh = price_mwh.convert_to_kwh()

        assert price_kwh.unit == PriceUnit.KWH
        assert price_kwh.price == Decimal("0.285")  # EUR/kWh


class TestPriceForecast:
    """Tests for PriceForecast model"""

    def test_create_forecast(self):
        """Test creating a PriceForecast instance"""
        prices = [
            PriceData(
                region=PricingRegion.UK,
                timestamp=datetime.now(timezone.utc) + timedelta(hours=i),
                price=Decimal("0.25"),
                unit=PriceUnit.KWH,
                currency="GBP",
            )
            for i in range(24)
        ]

        forecast = PriceForecast(
            region=PricingRegion.UK,
            forecast_generated_at=datetime.now(timezone.utc),
            forecast_horizon_hours=24,
            source_api="flatpeak",
            prices=prices,
            confidence_level=0.85,
        )

        assert len(forecast.prices) == 24
        assert forecast.confidence_level == 0.85

    def test_forecast_serialization(self):
        """Test PriceForecast serialization"""
        forecast = PriceForecast(
            region=PricingRegion.UK,
            forecast_generated_at=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            forecast_horizon_hours=24,
            source_api="test",
            prices=[],
            model_version="v1.0",
        )

        data = forecast.to_dict()
        restored = PriceForecast.from_dict(data)

        assert restored.region == forecast.region
        assert restored.model_version == "v1.0"


class TestCircuitBreaker:
    """Tests for circuit breaker pattern"""

    @pytest.mark.asyncio
    async def test_circuit_closed_allows_requests(self):
        """Test that closed circuit allows requests"""
        cb = CircuitBreaker("test")

        assert cb.state == CircuitState.CLOSED
        assert await cb.can_execute()

    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self):
        """Test that circuit opens after threshold failures"""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test", config)

        # Record failures
        for _ in range(3):
            await cb.record_failure()

        assert cb.state == CircuitState.OPEN
        assert not await cb.can_execute()

    @pytest.mark.asyncio
    async def test_circuit_half_open_after_timeout(self):
        """Test circuit transitions to half-open after timeout"""
        config = CircuitBreakerConfig(failure_threshold=2, timeout_seconds=0)
        cb = CircuitBreaker("test", config)

        # Trigger open state
        await cb.record_failure()
        await cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Wait for timeout (immediate since timeout=0)
        await asyncio.sleep(0.1)

        # Should be half-open now
        assert cb.state == CircuitState.HALF_OPEN
        assert await cb.can_execute()

    @pytest.mark.asyncio
    async def test_circuit_closes_after_success(self):
        """Test circuit closes after successful calls in half-open"""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=2,
            timeout_seconds=0,
        )
        cb = CircuitBreaker("test", config)

        # Open the circuit
        await cb.record_failure()
        await asyncio.sleep(0.1)  # Wait for timeout

        # Should be half-open
        assert cb.state == CircuitState.HALF_OPEN

        # Record successes
        await cb.record_success()
        await cb.record_success()

        assert cb.state == CircuitState.CLOSED


# =============================================================================
# RATE LIMITER TESTS
# =============================================================================


class TestTokenBucketLimiter:
    """Tests for token bucket rate limiter"""

    @pytest.mark.asyncio
    async def test_acquire_tokens(self, token_bucket_limiter):
        """Test acquiring tokens from bucket"""
        # Should have full capacity
        assert await token_bucket_limiter.acquire()

        remaining = await token_bucket_limiter.get_remaining()
        assert remaining == 9  # 10 - 1

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self):
        """Test behavior when rate limit exceeded"""
        limiter = TokenBucketLimiter(rate=0.1, capacity=2, name="test")

        # Exhaust tokens
        assert await limiter.acquire()
        assert await limiter.acquire()
        assert not await limiter.acquire()  # Should fail

    @pytest.mark.asyncio
    async def test_token_refill(self):
        """Test token refill over time"""
        limiter = TokenBucketLimiter(rate=100.0, capacity=10, name="test")

        # Exhaust some tokens
        await limiter.acquire()
        await limiter.acquire()

        # Wait for refill
        await asyncio.sleep(0.1)

        remaining = await limiter.get_remaining()
        assert remaining >= 8  # Should have refilled some

    @pytest.mark.asyncio
    async def test_wait_for_token(self):
        """Test waiting for token availability"""
        limiter = TokenBucketLimiter(rate=100.0, capacity=1, name="test")

        # Exhaust token
        await limiter.acquire()

        # Wait for new token
        start = asyncio.get_event_loop().time()
        result = await limiter.wait_for_token(timeout=1.0)
        elapsed = asyncio.get_event_loop().time() - start

        assert result
        assert elapsed < 0.5  # Should be fast with high rate


class TestSlidingWindowLimiter:
    """Tests for sliding window rate limiter"""

    @pytest.mark.asyncio
    async def test_sliding_window_basic(self):
        """Test basic sliding window functionality"""
        limiter = SlidingWindowLimiter(
            requests_per_window=5,
            window_seconds=1.0,
            name="test",
        )

        # Should allow up to 5 requests
        for _ in range(5):
            assert await limiter.acquire()

        # 6th should fail
        assert not await limiter.acquire()

    @pytest.mark.asyncio
    async def test_sliding_window_expiry(self):
        """Test that old requests expire from window"""
        limiter = SlidingWindowLimiter(
            requests_per_window=2,
            window_seconds=0.1,
            name="test",
        )

        # Use up quota
        await limiter.acquire()
        await limiter.acquire()
        assert not await limiter.acquire()

        # Wait for window to slide
        await asyncio.sleep(0.15)

        # Should be able to acquire again
        assert await limiter.acquire()


class TestCompositeRateLimiter:
    """Tests for composite rate limiter"""

    @pytest.mark.asyncio
    async def test_composite_limits(self):
        """Test that composite limiter respects all limits"""
        minute_limiter = TokenBucketLimiter(rate=10, capacity=5, name="minute")
        hour_limiter = TokenBucketLimiter(rate=1, capacity=3, name="hour")

        composite = CompositeRateLimiter(
            [minute_limiter, hour_limiter],
            name="test",
        )

        # Should be limited by the hour limiter (smaller capacity)
        assert await composite.acquire()
        assert await composite.acquire()
        assert await composite.acquire()
        assert not await composite.acquire()  # Hour limiter exhausted


class TestCreateApiRateLimiter:
    """Tests for rate limiter factory"""

    def test_create_with_minute_limit(self):
        """Test creating limiter with per-minute limit"""
        limiter = create_api_rate_limiter(
            api_name="test",
            requests_per_minute=100,
        )

        assert limiter is not None
        assert isinstance(limiter, SlidingWindowLimiter)

    def test_create_with_both_limits(self):
        """Test creating limiter with both minute and hour limits"""
        limiter = create_api_rate_limiter(
            api_name="test",
            requests_per_minute=100,
            requests_per_hour=1000,
        )

        assert isinstance(limiter, CompositeRateLimiter)


# =============================================================================
# CACHE TESTS
# =============================================================================


class TestCacheEntry:
    """Tests for CacheEntry"""

    def test_cache_entry_expiry(self):
        """Test cache entry expiration logic"""
        entry = CacheEntry(
            value={"price": 0.25},
            created_at=datetime.utcnow() - timedelta(seconds=120),
            ttl_seconds=60,
            key="test",
        )

        assert entry.is_expired
        assert entry.ttl_remaining == 0
        assert entry.age_ratio >= 1.0

    def test_cache_entry_fresh(self):
        """Test fresh cache entry"""
        entry = CacheEntry(
            value={"price": 0.25},
            created_at=datetime.utcnow(),
            ttl_seconds=60,
            key="test",
        )

        assert not entry.is_expired
        assert entry.ttl_remaining > 50
        assert entry.age_ratio < 0.2


class TestInMemoryCache:
    """Tests for in-memory cache"""

    @pytest.mark.asyncio
    async def test_set_and_get(self, memory_cache):
        """Test basic set and get operations"""
        await memory_cache.set("test_key", {"price": 0.25})

        result = await memory_cache.get("test_key")

        assert result == {"price": 0.25}

    @pytest.mark.asyncio
    async def test_cache_miss(self, memory_cache):
        """Test cache miss returns None"""
        result = await memory_cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_expiry(self):
        """Test that expired entries are not returned"""
        cache = InMemoryCache(CacheConfig(current_price_ttl=1))

        await cache.set("test_key", {"price": 0.25}, ttl=0)

        # Entry should be considered expired
        await asyncio.sleep(0.1)
        result = await cache.get("test_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_on_miss(self, memory_cache):
        """Test fetch function is called on cache miss"""
        async def fetch():
            return {"price": 0.30}

        result = await memory_cache.get("missing_key", fetch_func=fetch)

        assert result == {"price": 0.30}

        # Should be cached now
        cached = await memory_cache.get("missing_key")
        assert cached == {"price": 0.30}

    @pytest.mark.asyncio
    async def test_delete(self, memory_cache):
        """Test cache deletion"""
        await memory_cache.set("to_delete", {"value": 1})
        assert await memory_cache.exists("to_delete")

        await memory_cache.delete("to_delete")
        assert not await memory_cache.exists("to_delete")

    @pytest.mark.asyncio
    async def test_delete_pattern(self, memory_cache):
        """Test pattern-based deletion"""
        await memory_cache.set("api:flatpeak:uk", {"price": 0.25})
        await memory_cache.set("api:flatpeak:de", {"price": 0.30})
        await memory_cache.set("api:nrel:us", {"price": 0.12})

        deleted = await memory_cache.delete_pattern("*:flatpeak:*")

        assert deleted == 2
        assert not await memory_cache.exists("api:flatpeak:uk")
        assert await memory_cache.exists("api:nrel:us")

    @pytest.mark.asyncio
    async def test_current_price_convenience(self, memory_cache):
        """Test current price convenience methods"""
        price_data = {"price": "0.25", "region": "UK"}

        await memory_cache.set_current_price("flatpeak", "UK", price_data)

        result = await memory_cache.get_current_price("flatpeak", "UK")

        assert result == price_data

    @pytest.mark.asyncio
    async def test_metrics(self, memory_cache):
        """Test cache metrics collection"""
        await memory_cache.set("key1", {"value": 1})

        await memory_cache.get("key1")  # Hit
        await memory_cache.get("key2")  # Miss

        metrics = memory_cache.get_metrics()

        assert metrics["hits"] == 1
        assert metrics["misses"] == 1
        assert metrics["hit_rate_percent"] == 50.0


# =============================================================================
# FLATPEAK CLIENT TESTS
# =============================================================================


class TestFlatpeakClient:
    """Tests for Flatpeak API client"""

    @pytest.mark.asyncio
    async def test_get_current_price(self, flatpeak_response_current):
        """Test fetching current price from Flatpeak"""
        with patch("httpx.AsyncClient") as MockClient:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = flatpeak_response_current

            mock_client = AsyncMock()
            mock_client.is_closed = False
            mock_client.request.return_value = mock_response
            MockClient.return_value = mock_client

            async with FlatpeakClient(api_key="test-key") as client:
                client._client = mock_client

                price = await client.get_current_price(PricingRegion.UK)

                assert price.region == PricingRegion.UK
                assert price.price == Decimal("0.2845")
                assert price.currency == "GBP"
                assert price.supplier == "Octopus Energy"
                assert price.source_api == "flatpeak"

    @pytest.mark.asyncio
    async def test_get_price_forecast(self, flatpeak_response_forecast):
        """Test fetching price forecast from Flatpeak"""
        with patch("httpx.AsyncClient") as MockClient:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = flatpeak_response_forecast

            mock_client = AsyncMock()
            mock_client.is_closed = False
            mock_client.request.return_value = mock_response
            MockClient.return_value = mock_client

            async with FlatpeakClient(api_key="test-key") as client:
                client._client = mock_client

                forecast = await client.get_price_forecast(
                    PricingRegion.UK,
                    hours=24,
                )

                assert forecast.region == PricingRegion.UK
                assert len(forecast.prices) == 24
                assert forecast.source_api == "flatpeak"

    @pytest.mark.asyncio
    async def test_unsupported_region(self):
        """Test error for unsupported region"""
        async with FlatpeakClient(api_key="test-key") as client:
            with pytest.raises(ValueError, match="not supported"):
                await client.get_current_price(PricingRegion.US_CA)

    @pytest.mark.asyncio
    async def test_supported_regions(self):
        """Test that correct regions are reported as supported"""
        async with FlatpeakClient(api_key="test-key") as client:
            regions = client.get_supported_regions()

            assert PricingRegion.UK in regions
            assert PricingRegion.GERMANY in regions
            assert PricingRegion.US_CA not in regions

    def test_default_headers(self):
        """Test that correct headers are generated"""
        client = FlatpeakClient(api_key="test-api-key")

        headers = client._get_default_headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test-api-key"


# =============================================================================
# NREL CLIENT TESTS
# =============================================================================


class TestNRELClient:
    """Tests for NREL API client"""

    @pytest.mark.asyncio
    async def test_get_current_price(self, nrel_response):
        """Test fetching current rate from NREL"""
        with patch("httpx.AsyncClient") as MockClient:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = nrel_response

            mock_client = AsyncMock()
            mock_client.is_closed = False
            mock_client.request.return_value = mock_response
            MockClient.return_value = mock_client

            async with NRELClient(api_key="test-nrel-key") as client:
                client._client = mock_client

                price = await client.get_current_price(PricingRegion.US_CA)

                assert price.region == PricingRegion.US_CA
                assert price.price == Decimal("0.125")  # 12.5 cents -> 0.125 dollars
                assert price.currency == "USD"
                assert price.supplier == "Pacific Gas & Electric"

    @pytest.mark.asyncio
    async def test_get_price_forecast(self, nrel_response):
        """Test generating price forecast from NREL"""
        with patch("httpx.AsyncClient") as MockClient:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = nrel_response

            mock_client = AsyncMock()
            mock_client.is_closed = False
            mock_client.request.return_value = mock_response
            MockClient.return_value = mock_client

            async with NRELClient(api_key="test-nrel-key") as client:
                client._client = mock_client

                forecast = await client.get_price_forecast(
                    PricingRegion.US_CA,
                    hours=24,
                )

                assert forecast.region == PricingRegion.US_CA
                assert len(forecast.prices) == 24
                # NREL uses synthetic forecast, so lower confidence
                assert forecast.confidence_level == 0.7

    @pytest.mark.asyncio
    async def test_supported_regions(self):
        """Test that correct US regions are supported"""
        async with NRELClient(api_key="test-key") as client:
            regions = client.get_supported_regions()

            assert PricingRegion.US_CA in regions
            assert PricingRegion.US_TX in regions
            assert PricingRegion.UK not in regions


# =============================================================================
# IEA CLIENT TESTS
# =============================================================================


class TestIEAClient:
    """Tests for IEA API client"""

    @pytest.mark.asyncio
    async def test_get_current_price(self, iea_response):
        """Test fetching current price from IEA"""
        with patch("httpx.AsyncClient") as MockClient:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = iea_response

            mock_client = AsyncMock()
            mock_client.is_closed = False
            mock_client.request.return_value = mock_response
            MockClient.return_value = mock_client

            async with IEAClient(api_key="test-bearer-token") as client:
                client._client = mock_client

                price = await client.get_current_price(PricingRegion.UK)

                assert price.region == PricingRegion.UK
                # 285.50 USD/MWh -> 0.2855 USD/kWh
                assert price.price == Decimal("0.2855")
                assert price.source_api == "iea"

    @pytest.mark.asyncio
    async def test_bearer_auth(self):
        """Test that Bearer token authentication is used"""
        client = IEAClient(api_key="test-bearer-token")

        headers = client._get_default_headers()

        assert headers["Authorization"] == "Bearer test-bearer-token"

    @pytest.mark.asyncio
    async def test_global_region_support(self):
        """Test that global regions are supported"""
        async with IEAClient(api_key="test-key") as client:
            regions = client.get_supported_regions()

            assert PricingRegion.JAPAN in regions
            assert PricingRegion.AUSTRALIA in regions
            assert PricingRegion.CHINA in regions


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Tests for error handling across all clients"""

    @pytest.mark.asyncio
    async def test_rate_limit_error(self):
        """Test handling of rate limit errors"""
        with patch("httpx.AsyncClient") as MockClient:
            mock_response = AsyncMock()
            mock_response.status_code = 429
            mock_response.headers = {"Retry-After": "60"}
            mock_response.text = "Rate limit exceeded"

            mock_client = AsyncMock()
            mock_client.is_closed = False
            mock_client.request.return_value = mock_response
            MockClient.return_value = mock_client

            async with FlatpeakClient(api_key="test-key") as client:
                client._client = mock_client

                with pytest.raises(RateLimitError) as exc_info:
                    await client.get_current_price(PricingRegion.UK)

                assert exc_info.value.retry_after == 60

    @pytest.mark.asyncio
    async def test_authentication_error(self):
        """Test handling of authentication errors"""
        with patch("httpx.AsyncClient") as MockClient:
            mock_response = AsyncMock()
            mock_response.status_code = 401
            mock_response.text = "Invalid API key"

            mock_client = AsyncMock()
            mock_client.is_closed = False
            mock_client.request.return_value = mock_response
            MockClient.return_value = mock_client

            async with FlatpeakClient(api_key="invalid-key") as client:
                client._client = mock_client

                with pytest.raises(AuthenticationError):
                    await client.get_current_price(PricingRegion.UK)

    @pytest.mark.asyncio
    async def test_service_unavailable_error(self):
        """Test handling of 503 errors"""
        with patch("httpx.AsyncClient") as MockClient:
            mock_response = AsyncMock()
            mock_response.status_code = 503
            mock_response.text = "Service temporarily unavailable"

            mock_client = AsyncMock()
            mock_client.is_closed = False
            mock_client.request.return_value = mock_response
            MockClient.return_value = mock_client

            # Use minimal retries for faster test
            retry_config = RetryConfig(max_retries=0)

            async with FlatpeakClient(
                api_key="test-key",
                retry_config=retry_config,
            ) as client:
                client._client = mock_client

                with pytest.raises(ServiceUnavailableError):
                    await client.get_current_price(PricingRegion.UK)

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_failures(self):
        """Test that circuit breaker opens after repeated failures"""
        with patch("httpx.AsyncClient") as MockClient:
            mock_response = AsyncMock()
            mock_response.status_code = 500
            mock_response.text = "Internal server error"

            mock_client = AsyncMock()
            mock_client.is_closed = False
            mock_client.request.return_value = mock_response
            MockClient.return_value = mock_client

            circuit_config = CircuitBreakerConfig(failure_threshold=2)
            retry_config = RetryConfig(max_retries=0)

            async with FlatpeakClient(
                api_key="test-key",
                retry_config=retry_config,
                circuit_breaker_config=circuit_config,
            ) as client:
                client._client = mock_client

                # First failure
                with pytest.raises(ServiceUnavailableError):
                    await client.get_current_price(PricingRegion.UK)

                # Second failure - opens circuit
                with pytest.raises(ServiceUnavailableError):
                    await client.get_current_price(PricingRegion.UK)

                # Third attempt - circuit should be open
                with pytest.raises(CircuitBreakerOpenError):
                    await client.get_current_price(PricingRegion.UK)


# =============================================================================
# INTEGRATION TESTS (with cache)
# =============================================================================


class TestCacheIntegration:
    """Tests for cache integration with clients"""

    @pytest.mark.asyncio
    async def test_flatpeak_with_cache(self, flatpeak_response_current, memory_cache):
        """Test Flatpeak client uses cache correctly"""
        with patch("httpx.AsyncClient") as MockClient:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = flatpeak_response_current

            mock_client = AsyncMock()
            mock_client.is_closed = False
            mock_client.request.return_value = mock_response
            MockClient.return_value = mock_client

            async with FlatpeakClient(
                api_key="test-key",
                cache=memory_cache,
            ) as client:
                client._client = mock_client

                # First call - should hit API
                price1 = await client.get_current_price(PricingRegion.UK)
                assert mock_client.request.call_count == 1

                # Second call - should use cache
                price2 = await client.get_current_price(PricingRegion.UK)
                assert mock_client.request.call_count == 1  # No new API call

                assert price1.price == price2.price


# =============================================================================
# RETRY LOGIC TESTS
# =============================================================================


class TestRetryLogic:
    """Tests for retry behavior"""

    @pytest.mark.asyncio
    async def test_retry_on_500_error(self):
        """Test that 500 errors trigger retries"""
        call_count = 0

        with patch("httpx.AsyncClient") as MockClient:
            async def mock_request(*args, **kwargs):
                nonlocal call_count
                call_count += 1

                mock_response = AsyncMock()
                if call_count < 3:
                    mock_response.status_code = 500
                    mock_response.text = "Error"
                else:
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        "data": {
                            "timestamp": "2024-01-15T10:00:00Z",
                            "price": 0.25,
                            "unit": "kWh",
                        }
                    }
                return mock_response

            mock_client = AsyncMock()
            mock_client.is_closed = False
            mock_client.request = mock_request
            MockClient.return_value = mock_client

            retry_config = RetryConfig(
                max_retries=3,
                base_delay_seconds=0.01,  # Fast retries for test
            )

            async with FlatpeakClient(
                api_key="test-key",
                retry_config=retry_config,
            ) as client:
                client._client = mock_client

                price = await client.get_current_price(PricingRegion.UK)

                assert price is not None
                assert call_count == 3

    def test_exponential_backoff_calculation(self):
        """Test exponential backoff delay calculation"""
        config = RetryConfig(
            base_delay_seconds=1.0,
            exponential_base=2.0,
            jitter=False,
        )

        assert config.get_delay(0) == 1.0
        assert config.get_delay(1) == 2.0
        assert config.get_delay(2) == 4.0

    def test_max_delay_cap(self):
        """Test that delay is capped at max"""
        config = RetryConfig(
            base_delay_seconds=1.0,
            exponential_base=2.0,
            max_delay_seconds=5.0,
            jitter=False,
        )

        # 2^10 = 1024, but should be capped at 5
        assert config.get_delay(10) == 5.0


# =============================================================================
# RUN TESTS
# =============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
