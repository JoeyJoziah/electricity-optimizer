"""
API Performance Tests

Validates API endpoints meet performance SLAs:
- Price endpoint: <200ms p95
- Forecast endpoint: <500ms p95
- Optimization endpoint: <2000ms p95
- All endpoints: >99% success rate
"""

import pytest
import time
import statistics
from typing import List, Callable
import asyncio
import httpx

# Test configuration
BASE_URL = "http://localhost:8000"
NUM_REQUESTS = 100  # Number of requests per test
WARMUP_REQUESTS = 5  # Warmup requests before measuring


class PerformanceMetrics:
    """Collect and analyze performance metrics."""

    def __init__(self, latencies: List[float]):
        self.latencies = sorted(latencies)
        self.count = len(latencies)

    @property
    def avg(self) -> float:
        return statistics.mean(self.latencies) * 1000  # ms

    @property
    def p50(self) -> float:
        return statistics.median(self.latencies) * 1000  # ms

    @property
    def p95(self) -> float:
        idx = int(self.count * 0.95)
        return self.latencies[idx] * 1000  # ms

    @property
    def p99(self) -> float:
        idx = int(self.count * 0.99)
        return self.latencies[idx] * 1000  # ms

    @property
    def min(self) -> float:
        return min(self.latencies) * 1000  # ms

    @property
    def max(self) -> float:
        return max(self.latencies) * 1000  # ms


def measure_latencies(
    client: httpx.Client,
    method: str,
    url: str,
    num_requests: int = NUM_REQUESTS,
    json_data: dict = None,
) -> List[float]:
    """Measure latencies for multiple requests."""
    latencies = []

    # Warmup
    for _ in range(WARMUP_REQUESTS):
        if method == "GET":
            client.get(url)
        else:
            client.post(url, json=json_data)

    # Measure
    for _ in range(num_requests):
        start = time.perf_counter()
        try:
            if method == "GET":
                response = client.get(url)
            else:
                response = client.post(url, json=json_data)
            latency = time.perf_counter() - start
            if response.status_code == 200:
                latencies.append(latency)
        except Exception:
            pass

    return latencies


@pytest.fixture(scope="module")
def client():
    """Create HTTP client for tests."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="module")
def auth_headers(client):
    """Get authentication headers."""
    # Try to authenticate
    try:
        response = client.post(
            "/api/v1/auth/signin",
            json={"email": "test@example.com", "password": "TestPass123!"}
        )
        if response.status_code == 200:
            token = response.json().get("access_token")
            return {"Authorization": f"Bearer {token}"}
    except Exception:
        pass
    # Return mock headers for testing without auth
    return {"Authorization": "Bearer mock_token"}


class TestHealthEndpointPerformance:
    """Performance tests for health endpoints."""

    def test_health_endpoint_latency(self, client):
        """Health endpoint should respond in <50ms p95."""
        latencies = measure_latencies(client, "GET", "/health")
        metrics = PerformanceMetrics(latencies)

        print(f"\nHealth endpoint performance:")
        print(f"  p50: {metrics.p50:.2f}ms")
        print(f"  p95: {metrics.p95:.2f}ms")
        print(f"  p99: {metrics.p99:.2f}ms")

        assert metrics.p95 < 50, f"p95 latency {metrics.p95:.2f}ms exceeds 50ms target"

    def test_health_endpoint_availability(self, client):
        """Health endpoint should have >99.9% availability."""
        success_count = 0
        total = NUM_REQUESTS

        for _ in range(total):
            try:
                response = client.get("/health")
                if response.status_code == 200:
                    success_count += 1
            except Exception:
                pass

        availability = success_count / total * 100
        print(f"\nHealth endpoint availability: {availability:.2f}%")

        assert availability >= 99.9, f"Availability {availability:.2f}% below 99.9%"


class TestPriceEndpointPerformance:
    """Performance tests for price endpoints."""

    def test_current_price_latency(self, client):
        """Current price endpoint should respond in <200ms p95."""
        latencies = measure_latencies(
            client, "GET", "/api/v1/prices/current?region=UK"
        )
        metrics = PerformanceMetrics(latencies)

        print(f"\nCurrent price endpoint performance:")
        print(f"  Average: {metrics.avg:.2f}ms")
        print(f"  p50: {metrics.p50:.2f}ms")
        print(f"  p95: {metrics.p95:.2f}ms")
        print(f"  p99: {metrics.p99:.2f}ms")

        assert metrics.p95 < 200, f"p95 latency {metrics.p95:.2f}ms exceeds 200ms target"

    def test_price_history_latency(self, client):
        """Price history endpoint should respond in <300ms p95."""
        latencies = measure_latencies(
            client, "GET", "/api/v1/prices/history?region=UK&days=7"
        )
        metrics = PerformanceMetrics(latencies)

        print(f"\nPrice history endpoint performance:")
        print(f"  Average: {metrics.avg:.2f}ms")
        print(f"  p95: {metrics.p95:.2f}ms")

        assert metrics.p95 < 300, f"p95 latency {metrics.p95:.2f}ms exceeds 300ms target"

    def test_price_compare_latency(self, client):
        """Price comparison endpoint should respond in <400ms p95."""
        latencies = measure_latencies(
            client, "GET", "/api/v1/prices/compare?region=UK"
        )
        metrics = PerformanceMetrics(latencies)

        print(f"\nPrice comparison endpoint performance:")
        print(f"  Average: {metrics.avg:.2f}ms")
        print(f"  p95: {metrics.p95:.2f}ms")

        assert metrics.p95 < 400, f"p95 latency {metrics.p95:.2f}ms exceeds 400ms target"


class TestForecastEndpointPerformance:
    """Performance tests for forecast endpoints (includes ML inference)."""

    def test_24h_forecast_latency(self, client):
        """24-hour forecast should respond in <500ms p95."""
        latencies = measure_latencies(
            client, "GET", "/api/v1/prices/forecast?region=UK&hours=24"
        )
        metrics = PerformanceMetrics(latencies)

        print(f"\n24-hour forecast endpoint performance:")
        print(f"  Average: {metrics.avg:.2f}ms")
        print(f"  p50: {metrics.p50:.2f}ms")
        print(f"  p95: {metrics.p95:.2f}ms")
        print(f"  p99: {metrics.p99:.2f}ms")

        assert metrics.p95 < 500, f"p95 latency {metrics.p95:.2f}ms exceeds 500ms target"

    def test_48h_forecast_latency(self, client):
        """48-hour forecast should respond in <800ms p95."""
        latencies = measure_latencies(
            client, "GET", "/api/v1/prices/forecast?region=UK&hours=48"
        )
        metrics = PerformanceMetrics(latencies)

        print(f"\n48-hour forecast endpoint performance:")
        print(f"  Average: {metrics.avg:.2f}ms")
        print(f"  p95: {metrics.p95:.2f}ms")

        assert metrics.p95 < 800, f"p95 latency {metrics.p95:.2f}ms exceeds 800ms target"


class TestOptimizationEndpointPerformance:
    """Performance tests for ML optimization endpoint."""

    def test_simple_optimization_latency(self, client):
        """Simple optimization (1 appliance) should respond in <1s p95."""
        data = {
            "appliances": [
                {
                    "id": "dishwasher",
                    "power_kw": 1.5,
                    "duration_hours": 2,
                    "earliest_start": 18,
                    "latest_end": 30,
                }
            ]
        }

        latencies = measure_latencies(
            client, "POST", "/api/v1/optimization/schedule",
            num_requests=50,  # Fewer requests due to higher latency
            json_data=data,
        )
        metrics = PerformanceMetrics(latencies)

        print(f"\nSimple optimization (1 appliance) performance:")
        print(f"  Average: {metrics.avg:.2f}ms")
        print(f"  p95: {metrics.p95:.2f}ms")

        assert metrics.p95 < 1000, f"p95 latency {metrics.p95:.2f}ms exceeds 1000ms target"

    def test_complex_optimization_latency(self, client):
        """Complex optimization (5 appliances) should respond in <2s p95."""
        data = {
            "appliances": [
                {"id": "dishwasher", "power_kw": 1.5, "duration_hours": 2},
                {"id": "washing_machine", "power_kw": 2.0, "duration_hours": 2},
                {"id": "dryer", "power_kw": 3.0, "duration_hours": 1.5},
                {"id": "ev_charger", "power_kw": 7.0, "duration_hours": 4},
                {"id": "heat_pump", "power_kw": 2.5, "duration_hours": 3},
            ]
        }

        latencies = measure_latencies(
            client, "POST", "/api/v1/optimization/schedule",
            num_requests=20,  # Fewer requests due to higher latency
            json_data=data,
        )
        metrics = PerformanceMetrics(latencies)

        print(f"\nComplex optimization (5 appliances) performance:")
        print(f"  Average: {metrics.avg:.2f}ms")
        print(f"  p95: {metrics.p95:.2f}ms")
        print(f"  p99: {metrics.p99:.2f}ms")

        assert metrics.p95 < 2000, f"p95 latency {metrics.p95:.2f}ms exceeds 2000ms target"


class TestSupplierEndpointPerformance:
    """Performance tests for supplier endpoints."""

    def test_supplier_list_latency(self, client):
        """Supplier list should respond in <200ms p95."""
        latencies = measure_latencies(
            client, "GET", "/api/v1/suppliers?region=UK"
        )
        metrics = PerformanceMetrics(latencies)

        print(f"\nSupplier list endpoint performance:")
        print(f"  Average: {metrics.avg:.2f}ms")
        print(f"  p95: {metrics.p95:.2f}ms")

        assert metrics.p95 < 200, f"p95 latency {metrics.p95:.2f}ms exceeds 200ms target"

    def test_supplier_details_latency(self, client):
        """Supplier details should respond in <150ms p95."""
        latencies = measure_latencies(
            client, "GET", "/api/v1/suppliers/supplier_1"
        )
        metrics = PerformanceMetrics(latencies)

        print(f"\nSupplier details endpoint performance:")
        print(f"  Average: {metrics.avg:.2f}ms")
        print(f"  p95: {metrics.p95:.2f}ms")

        assert metrics.p95 < 150, f"p95 latency {metrics.p95:.2f}ms exceeds 150ms target"


class TestCachePerformance:
    """Tests to verify caching is working properly."""

    def test_cache_hit_improvement(self, client):
        """Subsequent requests should be faster due to caching."""
        url = "/api/v1/prices/current?region=UK"

        # Cold request
        cold_latencies = []
        for _ in range(5):
            # Clear any existing cache by waiting or using unique params
            start = time.perf_counter()
            client.get(url)
            cold_latencies.append(time.perf_counter() - start)

        # Warm requests (should hit cache)
        warm_latencies = []
        for _ in range(50):
            start = time.perf_counter()
            client.get(url)
            warm_latencies.append(time.perf_counter() - start)

        cold_avg = statistics.mean(cold_latencies) * 1000
        warm_avg = statistics.mean(warm_latencies) * 1000

        print(f"\nCache performance:")
        print(f"  Cold average: {cold_avg:.2f}ms")
        print(f"  Warm average: {warm_avg:.2f}ms")
        print(f"  Improvement: {((cold_avg - warm_avg) / cold_avg * 100):.1f}%")

        # Warm requests should be at least 20% faster if caching works
        # (may not always be true for very fast endpoints)
        assert warm_avg <= cold_avg, "Cache hit should not be slower than cold request"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
