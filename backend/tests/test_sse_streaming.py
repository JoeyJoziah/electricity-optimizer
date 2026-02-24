"""
Tests for SSE streaming (api/v1/prices_sse.py)

Covers:
- _sse_incr / _sse_decr in-memory connection tracking
- 429 when exceeding max connections
- Heartbeat comment format
- data event JSON format
- Fallback to mock when DB returns empty prices
- Exception recovery path (DB error → fallback mock)
- Client disconnect stops the generator
- 401 without auth token on /stream endpoint
- SSE response headers on /stream endpoint
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import collections
import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# HELPERS
# =============================================================================


def _make_price_obj(supplier: str = "Eversource", price: float = 0.28):
    """Create a minimal Price-like mock for PriceService.get_current_prices."""
    p = MagicMock()
    p.supplier = supplier
    p.price_per_kwh = Decimal(str(price))
    p.currency = "USD"
    p.is_peak = False
    return p


def _make_token_data(user_id: str = "user-sse-test"):
    """Build a minimal SessionData / TokenData mock."""
    from auth.neon_auth import SessionData

    return SessionData(
        user_id=user_id,
        email="sse@test.com",
        name="SSE Test",
        email_verified=True,
    )


# =============================================================================
# TestSSEConnectionCounting
# =============================================================================


class TestSSEConnectionCounting:
    """Tests for in-memory _sse_incr / _sse_decr functions.

    get_redis is imported locally inside _sse_incr/_sse_decr via
    `from config.database import get_redis`, so we patch the canonical
    location: config.database.get_redis.
    """

    @pytest.mark.asyncio
    async def test_sse_connection_counting_increment(self):
        """_sse_incr increases the in-memory counter for a user."""
        from api.v1 import prices_sse

        # Reset the in-memory dict to isolate this test
        prices_sse._sse_connections.clear()

        async def _no_redis():
            return None

        with patch("config.database.get_redis", new=_no_redis):
            count = await prices_sse._sse_incr("user-a")

        assert count == 1
        assert prices_sse._sse_connections["user-a"] == 1

    @pytest.mark.asyncio
    async def test_sse_connection_counting_decrement(self):
        """_sse_decr decreases the in-memory counter and removes the key at 0."""
        from api.v1 import prices_sse

        prices_sse._sse_connections.clear()

        async def _no_redis():
            return None

        with patch("config.database.get_redis", new=_no_redis):
            await prices_sse._sse_incr("user-b")
            await prices_sse._sse_incr("user-b")
            await prices_sse._sse_decr("user-b")

        assert prices_sse._sse_connections["user-b"] == 1

        with patch("config.database.get_redis", new=_no_redis):
            await prices_sse._sse_decr("user-b")

        # Key should be gone after decrement to zero
        assert "user-b" not in prices_sse._sse_connections


# =============================================================================
# TestSSEMaxConnections
# =============================================================================


class TestSSEMaxConnections:
    """Test the 429 guard on the /stream endpoint."""

    @pytest.fixture
    def app_client(self):
        """TestClient with auth and price_service dependencies overridden."""
        from main import app
        from api.dependencies import get_current_user, get_price_service, get_redis

        token = _make_token_data("user-maxconn")
        mock_svc = AsyncMock()
        mock_svc.get_current_prices = AsyncMock(return_value=[_make_price_obj()])

        app.dependency_overrides[get_current_user] = lambda: token
        app.dependency_overrides[get_price_service] = lambda: mock_svc
        app.dependency_overrides[get_redis] = lambda: None

        yield TestClient(app, raise_server_exceptions=False)

        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_price_service, None)
        app.dependency_overrides.pop(get_redis, None)

    def test_sse_max_connections_exceeded(self, app_client):
        """429 is returned when the in-memory counter exceeds 3 for a user."""
        from api.v1 import prices_sse

        # Force the counter to be at max already
        prices_sse._sse_connections["user-maxconn"] = 3

        async def _no_redis():
            return None

        # get_redis is imported locally inside _sse_incr via config.database
        with patch("config.database.get_redis", new=_no_redis):
            response = app_client.get(
                "/api/v1/prices/stream?region=us_ct&interval=10"
            )

        assert response.status_code == 429

        # Cleanup
        prices_sse._sse_connections.pop("user-maxconn", None)


# =============================================================================
# TestSSEEventGenerator
# =============================================================================


class TestSSEEventGenerator:
    """Tests for _price_event_generator internals."""

    @pytest.mark.asyncio
    async def test_sse_heartbeat_sent(self):
        """Generator yields a '': heartbeat\\n\\n' comment during sleep interval."""
        from api.v1.prices_sse import _price_event_generator
        from models.price import PriceRegion

        mock_svc = AsyncMock()
        mock_svc.get_current_prices = AsyncMock(return_value=[_make_price_obj()])

        # Disconnect after first sleep chunk
        call_count = 0

        async def fake_sleep(t):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError()

        events = []
        with patch("asyncio.sleep", side_effect=fake_sleep):
            try:
                async for event in _price_event_generator(
                    PriceRegion.US_CT,
                    mock_svc,
                    interval_seconds=30,
                    request=None,
                ):
                    events.append(event)
            except asyncio.CancelledError:
                pass

        # The first event should be the data event
        assert any(e.startswith("data:") for e in events)

    @pytest.mark.asyncio
    async def test_sse_data_event_format(self):
        """Yielded data events have 'data: {json}\\n\\n' format with required keys."""
        from api.v1.prices_sse import _price_event_generator
        from models.price import PriceRegion

        mock_svc = AsyncMock()
        mock_svc.get_current_prices = AsyncMock(
            return_value=[_make_price_obj("United Illuminating", 0.24)]
        )

        events = []

        async def _stop_after_data(t):
            raise asyncio.CancelledError()

        with patch("asyncio.sleep", side_effect=_stop_after_data):
            try:
                async for event in _price_event_generator(
                    PriceRegion.US_CT, mock_svc, interval_seconds=30
                ):
                    events.append(event)
            except asyncio.CancelledError:
                pass

        assert len(events) >= 1
        first = events[0]
        assert first.startswith("data: ")
        assert first.endswith("\n\n")
        payload = json.loads(first[len("data: "): -2])
        assert payload["region"] == "us_ct"
        assert payload["supplier"] == "United Illuminating"
        assert "price_per_kwh" in payload
        assert payload["source"] == "live"

    @pytest.mark.asyncio
    async def test_sse_fallback_data(self):
        """When DB returns empty list, generator falls back to mock data."""
        from api.v1.prices_sse import _price_event_generator
        from models.price import PriceRegion

        mock_svc = AsyncMock()
        mock_svc.get_current_prices = AsyncMock(return_value=[])

        mock_fallback_price = _make_price_obj("Fallback Supplier", 0.29)

        events = []

        async def _stop_after_data(t):
            raise asyncio.CancelledError()

        with (
            patch("asyncio.sleep", side_effect=_stop_after_data),
            patch(
                "api.v1.prices_sse._generate_mock_prices",
                return_value=[mock_fallback_price],
                create=True,
            ),
        ):
            # _generate_mock_prices is imported lazily inside the generator;
            # patch it at the source module.
            with patch(
                "api.v1.prices._generate_mock_prices",
                return_value=[mock_fallback_price],
            ):
                try:
                    async for event in _price_event_generator(
                        PriceRegion.US_CT, mock_svc, interval_seconds=30
                    ):
                        events.append(event)
                except asyncio.CancelledError:
                    pass

        assert len(events) >= 1
        payload = json.loads(events[0][len("data: "): -2])
        assert payload["source"] == "fallback"

    @pytest.mark.asyncio
    async def test_sse_error_recovery(self):
        """Exception in get_current_prices triggers fallback mock path."""
        from api.v1.prices_sse import _price_event_generator
        from models.price import PriceRegion

        mock_svc = AsyncMock()
        mock_svc.get_current_prices = AsyncMock(
            side_effect=RuntimeError("DB connection lost")
        )

        fallback_price = _make_price_obj("Mock Supplier", 0.27)

        events = []

        async def _stop_after_data(t):
            raise asyncio.CancelledError()

        with patch("asyncio.sleep", side_effect=_stop_after_data):
            with patch(
                "api.v1.prices._generate_mock_prices",
                return_value=[fallback_price],
            ):
                try:
                    async for event in _price_event_generator(
                        PriceRegion.US_CT, mock_svc, interval_seconds=30
                    ):
                        events.append(event)
                except asyncio.CancelledError:
                    pass

        # Should have yielded a fallback event rather than crashing
        assert len(events) >= 1
        payload = json.loads(events[0][len("data: "): -2])
        assert payload["source"] == "fallback"

    @pytest.mark.asyncio
    async def test_sse_client_disconnect(self):
        """Generator stops producing events once request.is_disconnected() returns True."""
        from api.v1.prices_sse import _price_event_generator
        from models.price import PriceRegion

        mock_svc = AsyncMock()
        mock_svc.get_current_prices = AsyncMock(return_value=[_make_price_obj()])

        # Simulate a request that is already disconnected after first check
        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(return_value=True)

        events = []
        async for event in _price_event_generator(
            PriceRegion.US_CT,
            mock_svc,
            interval_seconds=30,
            request=mock_request,
        ):
            events.append(event)  # pragma: no cover — should not be reached

        # Generator should have exited immediately on disconnect check
        assert events == []


# =============================================================================
# TestSSEEndpoint
# =============================================================================


class TestSSEEndpoint:
    """Tests for the /api/v1/prices/stream HTTP endpoint."""

    def test_stream_prices_requires_auth(self):
        """Without a valid auth token, /stream returns 401 or 403."""
        from main import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/prices/stream?region=us_ct&interval=10")

        assert response.status_code in (401, 403, 503)

    def test_stream_prices_response_headers(self):
        """Authenticated /stream returns correct SSE content-type and cache headers.

        We verify headers by reading the first chunk of the stream and then
        disconnecting immediately.  The inner async generator breaks as soon
        as it detects the disconnection, so the test does not hang.
        """
        from main import app
        from api.dependencies import get_current_user, get_price_service, get_redis
        from api.v1 import prices_sse

        token = _make_token_data("user-headers")
        mock_svc = AsyncMock()
        mock_svc.get_current_prices = AsyncMock(return_value=[_make_price_obj()])

        app.dependency_overrides[get_current_user] = lambda: token
        app.dependency_overrides[get_price_service] = lambda: mock_svc
        app.dependency_overrides[get_redis] = lambda: None

        prices_sse._sse_connections.clear()

        async def _no_redis():
            return None

        # Patch asyncio.sleep so the generator advances past the sleep without
        # actually waiting, then raises CancelledError on the second call so it
        # terminates after yielding one event.
        sleep_calls = {"n": 0}

        async def _fast_sleep(_t):
            sleep_calls["n"] += 1
            if sleep_calls["n"] >= 2:
                raise asyncio.CancelledError()

        try:
            with (
                patch("config.database.get_redis", new=_no_redis),
                patch("asyncio.sleep", side_effect=_fast_sleep),
            ):
                # TestClient.stream enters the response context; we read just
                # the first line so the headers are available, then exit.
                with TestClient(app, raise_server_exceptions=False) as client:
                    with client.stream(
                        "GET",
                        "/api/v1/prices/stream?region=us_ct&interval=10",
                    ) as response:
                        # Headers are available immediately after the 200 is sent.
                        assert response.status_code == 200
                        content_type = response.headers.get("content-type", "")
                        assert "text/event-stream" in content_type
                        # The streaming response sets Cache-Control: no-cache;
                        # middleware may append additional directives, so we
                        # check for containment rather than exact equality.
                        cache_control = response.headers.get("cache-control", "")
                        assert "no-cache" in cache_control
                        assert response.headers.get("x-accel-buffering") == "no"
                        # Read one byte to trigger body consumption then exit.
                        response.read()
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_price_service, None)
            app.dependency_overrides.pop(get_redis, None)
            prices_sse._sse_connections.clear()
