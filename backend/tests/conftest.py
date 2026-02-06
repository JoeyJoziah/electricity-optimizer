"""
Pytest Configuration and Shared Fixtures

This module provides common fixtures and configuration for all tests.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import httpx

# Add backend directory to path for imports
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


# =============================================================================
# ASYNC CONFIGURATION
# =============================================================================


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# MOCK HTTP CLIENT FIXTURES
# =============================================================================


@pytest.fixture
def mock_httpx_response():
    """Factory fixture for creating mock HTTP responses"""
    def _create_response(
        status_code: int = 200,
        json_data: dict = None,
        text: str = "",
        headers: dict = None,
    ):
        response = AsyncMock(spec=httpx.Response)
        response.status_code = status_code
        response.text = text
        response.headers = headers or {}

        if json_data:
            response.json.return_value = json_data
        else:
            response.json.return_value = {}

        return response

    return _create_response


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx AsyncClient"""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.is_closed = False
    return client


# =============================================================================
# SAMPLE DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_price_data():
    """Sample price data for testing"""
    from integrations.pricing_apis.base import PriceData, PricingRegion, PriceUnit

    return PriceData(
        region=PricingRegion.UK,
        timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
        price=Decimal("0.2845"),
        unit=PriceUnit.KWH,
        currency="GBP",
        supplier="Octopus Energy",
        tariff_name="Agile Octopus",
        source_api="flatpeak",
        energy_cost=Decimal("0.15"),
        network_cost=Decimal("0.08"),
        taxes=Decimal("0.0345"),
        levies=Decimal("0.02"),
        is_peak=False,
        is_renewable=True,
        carbon_intensity=180.5,
    )


@pytest.fixture
def sample_forecast_data():
    """Sample forecast data for testing"""
    from integrations.pricing_apis.base import (
        PriceData,
        PriceForecast,
        PricingRegion,
        PriceUnit,
    )
    from datetime import timedelta

    base_time = datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)

    prices = [
        PriceData(
            region=PricingRegion.UK,
            timestamp=base_time + timedelta(hours=i),
            price=Decimal("0.25") + Decimal(str(0.05 * (i % 4))),
            unit=PriceUnit.KWH,
            currency="GBP",
            source_api="flatpeak",
            is_peak=16 <= i <= 21,
        )
        for i in range(24)
    ]

    return PriceForecast(
        region=PricingRegion.UK,
        forecast_generated_at=base_time,
        forecast_horizon_hours=24,
        source_api="flatpeak",
        prices=prices,
        model_version="v2.1",
        confidence_level=0.85,
    )


# =============================================================================
# API RESPONSE FIXTURES
# =============================================================================


@pytest.fixture
def flatpeak_current_response():
    """Sample Flatpeak current price API response"""
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
def flatpeak_forecast_response():
    """Sample Flatpeak forecast API response"""
    from datetime import timedelta

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
def nrel_rates_response():
    """Sample NREL utility rates API response"""
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
def iea_price_response():
    """Sample IEA price API response"""
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


# =============================================================================
# CACHE FIXTURES
# =============================================================================


@pytest.fixture
def memory_cache():
    """In-memory cache for testing"""
    from integrations.pricing_apis.cache import InMemoryCache, CacheConfig

    return InMemoryCache(CacheConfig(current_price_ttl=60))


@pytest.fixture
def cache_config():
    """Cache configuration for testing"""
    from integrations.pricing_apis.cache import CacheConfig

    return CacheConfig(
        current_price_ttl=60,
        price_forecast_ttl=300,
        historical_price_ttl=3600,
        background_refresh=False,  # Disable for testing
    )


# =============================================================================
# RATE LIMITER FIXTURES
# =============================================================================


@pytest.fixture
def token_bucket_limiter():
    """Token bucket rate limiter for testing"""
    from integrations.pricing_apis.rate_limiter import TokenBucketLimiter

    return TokenBucketLimiter(rate=100.0, capacity=100, name="test")


@pytest.fixture
def sliding_window_limiter():
    """Sliding window rate limiter for testing"""
    from integrations.pricing_apis.rate_limiter import SlidingWindowLimiter

    return SlidingWindowLimiter(
        requests_per_window=10,
        window_seconds=1.0,
        name="test",
    )


# =============================================================================
# CLIENT CONFIGURATION FIXTURES
# =============================================================================


@pytest.fixture
def retry_config():
    """Retry configuration for testing (fast retries)"""
    from integrations.pricing_apis.base import RetryConfig

    return RetryConfig(
        max_retries=2,
        base_delay_seconds=0.01,
        max_delay_seconds=0.1,
        jitter=False,
    )


@pytest.fixture
def circuit_breaker_config():
    """Circuit breaker configuration for testing"""
    from integrations.pricing_apis.base import CircuitBreakerConfig

    return CircuitBreakerConfig(
        failure_threshold=3,
        success_threshold=2,
        timeout_seconds=1,
        half_open_max_calls=2,
    )


# =============================================================================
# MOCK REDIS FIXTURE
# =============================================================================


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing"""
    redis = AsyncMock()

    # Mock basic operations
    redis.get.return_value = None
    redis.set.return_value = True
    redis.delete.return_value = 1
    redis.exists.return_value = 0
    redis.ttl.return_value = -2
    redis.ping.return_value = True

    # Mock pipeline
    pipeline = AsyncMock()
    pipeline.execute.return_value = []
    redis.pipeline.return_value = pipeline

    # Mock scan_iter
    async def scan_iter_mock(*args, **kwargs):
        return
        yield  # Make it an async generator that yields nothing

    redis.scan_iter = scan_iter_mock

    return redis


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def create_mock_response(
    status_code: int = 200,
    json_data: dict = None,
    headers: dict = None,
):
    """Helper function to create mock HTTP responses"""
    response = AsyncMock(spec=httpx.Response)
    response.status_code = status_code
    response.headers = headers or {}
    response.json.return_value = json_data or {}
    response.text = ""

    # Make raise_for_status work
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=response,
        )
    else:
        response.raise_for_status.return_value = None

    return response
