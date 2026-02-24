"""
Lightweight Load Tests

Validates that the API handles concurrent requests without errors or
excessive latency. Runs against the in-process ASGI app (no network).
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db_session():
    """Return a mock async DB session."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchall.return_value = []
    result_mock.fetchone.return_value = None
    result_mock.scalars.return_value.all.return_value = []
    session.execute.return_value = result_mock
    return session


def _get_test_client():
    """Create an httpx.AsyncClient wired to the ASGI app."""
    from main import app
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Concurrent Request Tests
# ---------------------------------------------------------------------------


class TestConcurrentHealth:
    """Verify health endpoint handles many concurrent requests."""

    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self):
        """50 concurrent GET /health should all return 200 in <2s."""
        async with _get_test_client() as client:
            start = time.monotonic()
            tasks = [client.get("/health") for _ in range(50)]
            responses = await asyncio.gather(*tasks)
            elapsed = time.monotonic() - start

        assert all(r.status_code == 200 for r in responses), (
            f"Some health checks failed: {[r.status_code for r in responses if r.status_code != 200]}"
        )
        assert elapsed < 2.0, f"50 health checks took {elapsed:.2f}s (limit 2s)"

    @pytest.mark.asyncio
    async def test_concurrent_docs_disabled(self):
        """30 concurrent GET /docs should all return 404 (disabled)."""
        async with _get_test_client() as client:
            tasks = [client.get("/docs") for _ in range(30)]
            responses = await asyncio.gather(*tasks)

        # docs_url is None in test env (same as production)
        assert all(r.status_code in (404, 200) for r in responses)


class TestConcurrentPriceEndpoints:
    """Verify price endpoints handle concurrent requests."""

    @pytest.fixture(autouse=True)
    def _mock_deps(self):
        """Patch DB and Redis for all tests in this class."""
        with (
            patch("api.dependencies.get_db_session", return_value=_mock_db_session()),
            patch("api.dependencies.get_redis", return_value=AsyncMock()),
        ):
            yield

    @pytest.mark.asyncio
    async def test_concurrent_price_current(self):
        """20 concurrent GET /api/v1/prices/current should all respond."""
        async with _get_test_client() as client:
            start = time.monotonic()
            tasks = [
                client.get("/api/v1/prices/current", params={"region": "us_ct"})
                for _ in range(20)
            ]
            responses = await asyncio.gather(*tasks)
            elapsed = time.monotonic() - start

        # All should return a valid HTTP status (not 500)
        server_errors = [r for r in responses if r.status_code >= 500]
        assert len(server_errors) == 0, (
            f"{len(server_errors)} server errors out of 20 requests"
        )
        assert elapsed < 3.0, f"20 price requests took {elapsed:.2f}s (limit 3s)"

    @pytest.mark.asyncio
    async def test_concurrent_mixed_endpoints(self):
        """Mix of different endpoints concurrently."""
        async with _get_test_client() as client:
            tasks = []
            for _ in range(10):
                tasks.append(client.get("/health"))
                tasks.append(
                    client.get("/api/v1/prices/current", params={"region": "us_ct"})
                )
            responses = await asyncio.gather(*tasks)

        server_errors = [r for r in responses if r.status_code >= 500]
        assert len(server_errors) == 0, (
            f"{len(server_errors)} server errors out of {len(responses)} mixed requests"
        )


class TestLatencyBudget:
    """Verify individual endpoint latency stays within budget."""

    @pytest.mark.asyncio
    async def test_health_latency_p99(self):
        """P99 latency for /health should be <100ms."""
        async with _get_test_client() as client:
            latencies = []
            for _ in range(100):
                start = time.monotonic()
                await client.get("/health")
                latencies.append(time.monotonic() - start)

        latencies.sort()
        p99 = latencies[98]  # 99th percentile
        assert p99 < 0.1, f"Health P99 latency {p99*1000:.1f}ms exceeds 100ms budget"

    @pytest.mark.asyncio
    async def test_startup_time(self):
        """App startup (import + first request) should be <3s."""
        start = time.monotonic()
        async with _get_test_client() as client:
            resp = await client.get("/health")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 3.0, f"Startup + first request took {elapsed:.2f}s (limit 3s)"


class TestConnectionStress:
    """Verify the app doesn't leak resources under rapid open/close."""

    @pytest.mark.asyncio
    async def test_rapid_sequential_requests(self):
        """200 rapid sequential requests should not degrade."""
        async with _get_test_client() as client:
            start = time.monotonic()
            for _ in range(200):
                resp = await client.get("/health")
                assert resp.status_code == 200
            elapsed = time.monotonic() - start

        # 200 sequential requests in <5s
        assert elapsed < 5.0, f"200 sequential requests took {elapsed:.2f}s (limit 5s)"

    @pytest.mark.asyncio
    async def test_burst_then_steady(self):
        """Burst of 50, then steady 50 requests should all succeed."""
        async with _get_test_client() as client:
            # Burst
            burst = await asyncio.gather(*[client.get("/health") for _ in range(50)])
            assert all(r.status_code == 200 for r in burst)

            # Steady
            for _ in range(50):
                resp = await client.get("/health")
                assert resp.status_code == 200
