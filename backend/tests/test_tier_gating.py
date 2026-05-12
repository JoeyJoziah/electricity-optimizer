"""
Tests for subscription tier gating (backend/api/dependencies.py require_tier).

Coverage:
  - require_tier("pro") on GET /prices/forecast
  - require_tier("pro") on GET /savings/summary, GET /savings/history
  - require_tier("pro") on GET /recommendations/switching, /usage, /daily
  - require_tier("business") on GET /prices/stream
  - Free-tier alert limit on POST /alerts (1 max)

Each test overrides get_current_user and get_db_session so that require_tier
runs its real logic against a mock DB that returns the appropriate tier.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session

# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

TEST_USER_ID = "dddddddd-0000-0000-0000-000000000004"


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _scalar_result(value):
    """Mock execute() result whose scalar_one_or_none() returns value."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar.return_value = value
    # Also support fetchone for connections-style usage
    row = MagicMock()
    row.__getitem__ = lambda self, k: value
    result.fetchone.return_value = row
    return result


def _count_result(count: int):
    """Mock execute() result whose scalar() returns a count."""
    result = MagicMock()
    result.scalar.return_value = count
    result.scalar_one_or_none.return_value = count
    return result


def _make_db(tier: str, alert_count: int = 0):
    """
    Build an AsyncMock DB session that returns the given tier for
    subscription_tier queries and the given count for COUNT(*) queries.

    The execute dispatcher checks the SQL text to decide which mock to return.
    """
    db = AsyncMock()

    async def _execute(stmt, params=None):
        sql = str(stmt.text if hasattr(stmt, "text") else stmt).upper()
        if "SUBSCRIPTION_TIER" in sql:
            return _scalar_result(tier)
        if "COUNT(*)" in sql:
            return _count_result(alert_count)
        # Default fallback: empty mapping result for alert service create etc.
        return _mapping_result()

    db.execute = AsyncMock(side_effect=_execute)
    db.commit = AsyncMock()
    return db


def _mapping_result():
    """Generic empty mapping result for INSERT ... RETURNING etc."""
    result = MagicMock()
    mapping = MagicMock()
    mapping.first.return_value = {
        "id": "new-alert-id",
        "user_id": TEST_USER_ID,
        "region": "us_ct",
        "currency": "USD",
        "price_below": 0.20,
        "price_above": None,
        "notify_optimal_windows": True,
        "is_active": True,
        "created_at": "2026-03-06T00:00:00Z",
        "updated_at": "2026-03-06T00:00:00Z",
    }
    mapping.all.return_value = []
    result.mappings.return_value = mapping
    result.rowcount = 1
    result.scalar.return_value = 0
    result.scalar_one_or_none.return_value = None
    return result


def _session():
    return SessionData(
        user_id=TEST_USER_ID,
        email="test@example.com",
        name="Test User",
        email_verified=True,
        role="user",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_overrides():
    """Clear dependency overrides after each test."""
    from main import _app_rate_limiter, app

    _app_rate_limiter.reset()
    yield
    for dep in list(app.dependency_overrides.keys()):
        app.dependency_overrides.pop(dep, None)
    _app_rate_limiter.reset()


def _install(tier: str, alert_count: int = 0):
    """Install auth + DB dependency overrides for the given tier."""
    from main import app

    session = _session()
    db = _make_db(tier, alert_count=alert_count)
    app.dependency_overrides[get_current_user] = lambda: session
    app.dependency_overrides[get_db_session] = lambda: db
    return db


def _client():
    from main import app

    return TestClient(app, raise_server_exceptions=False)


# =============================================================================
# 1. GET /api/v1/prices/forecast — require_tier("pro")
# =============================================================================


class TestPriceForecastTierGating:
    """require_tier('pro') on GET /prices/forecast."""

    def test_free_user_gets_403(self):
        _install("free")
        client = _client()
        resp = client.get("/api/v1/prices/forecast?region=us_ct")
        assert resp.status_code == 403

    def test_pro_user_allowed(self):
        _install("pro")
        client = _client()
        resp = client.get("/api/v1/prices/forecast?region=us_ct")
        # Pro user should pass tier check (may get 404/503 from service, not 403)
        assert resp.status_code != 403

    def test_business_user_allowed(self):
        _install("business")
        client = _client()
        resp = client.get("/api/v1/prices/forecast?region=us_ct")
        assert resp.status_code != 403

    def test_none_tier_gets_403(self):
        _install(None)
        client = _client()
        resp = client.get("/api/v1/prices/forecast?region=us_ct")
        assert resp.status_code == 403


# =============================================================================
# 2. GET /api/v1/savings/summary — require_tier("pro")
# =============================================================================


class TestSavingsSummaryTierGating:
    def test_free_user_gets_403(self):
        _install("free")
        client = _client()
        resp = client.get("/api/v1/savings/summary")
        assert resp.status_code == 403

    def test_pro_user_allowed(self):
        _install("pro")
        client = _client()
        resp = client.get("/api/v1/savings/summary")
        assert resp.status_code != 403


# =============================================================================
# 3. GET /api/v1/savings/history — require_tier("pro")
# =============================================================================


class TestSavingsHistoryTierGating:
    def test_free_user_gets_403(self):
        _install("free")
        client = _client()
        resp = client.get("/api/v1/savings/history")
        assert resp.status_code == 403

    def test_pro_user_allowed(self):
        _install("pro")
        client = _client()
        resp = client.get("/api/v1/savings/history")
        assert resp.status_code != 403


# =============================================================================
# 4. GET /api/v1/recommendations/switching — require_tier("pro")
# =============================================================================


class TestRecommendationsSwitchingTierGating:
    def test_free_user_gets_403(self):
        _install("free")
        client = _client()
        resp = client.get("/api/v1/recommendations/switching")
        assert resp.status_code == 403

    def test_pro_user_allowed(self):
        from api.dependencies import get_recommendation_service
        from main import app

        _install("pro")
        mock_svc = AsyncMock()
        mock_svc.get_switching_recommendation.return_value = None
        app.dependency_overrides[get_recommendation_service] = lambda: mock_svc

        client = _client()
        resp = client.get("/api/v1/recommendations/switching")
        assert resp.status_code != 403


# =============================================================================
# 5. GET /api/v1/recommendations/usage — require_tier("pro")
# =============================================================================


class TestRecommendationsUsageTierGating:
    def test_free_user_gets_403(self):
        _install("free")
        client = _client()
        resp = client.get(
            "/api/v1/recommendations/usage?appliance=washer&duration_hours=1"
        )
        assert resp.status_code == 403

    def test_pro_user_allowed(self):
        from api.dependencies import get_recommendation_service
        from main import app

        _install("pro")
        mock_svc = AsyncMock()
        mock_svc.get_usage_recommendation.return_value = None
        app.dependency_overrides[get_recommendation_service] = lambda: mock_svc

        client = _client()
        resp = client.get(
            "/api/v1/recommendations/usage?appliance=washer&duration_hours=1"
        )
        assert resp.status_code != 403


# =============================================================================
# 6. GET /api/v1/recommendations/daily — require_tier("pro")
# =============================================================================


class TestRecommendationsDailyTierGating:
    def test_free_user_gets_403(self):
        _install("free")
        client = _client()
        resp = client.get("/api/v1/recommendations/daily")
        assert resp.status_code == 403

    def test_business_user_allowed(self):
        from api.dependencies import get_recommendation_service
        from main import app

        _install("business")
        mock_svc = AsyncMock()
        mock_svc.get_daily_recommendations.return_value = None
        app.dependency_overrides[get_recommendation_service] = lambda: mock_svc

        client = _client()
        resp = client.get("/api/v1/recommendations/daily")
        assert resp.status_code != 403


# =============================================================================
# 7. GET /api/v1/prices/stream — require_tier("business")
# =============================================================================


class TestPriceStreamTierGating:
    """require_tier('business') on GET /prices/stream."""

    def test_free_user_gets_403(self):
        _install("free")
        client = _client()
        resp = client.get("/api/v1/prices/stream?region=us_ct")
        assert resp.status_code == 403

    def test_pro_user_gets_403(self):
        _install("pro")
        client = _client()
        resp = client.get("/api/v1/prices/stream?region=us_ct")
        assert resp.status_code == 403

    def test_business_user_allowed(self):
        """Business user passes the tier gate.

        We patch the SSE generator to yield one event then stop, so the
        TestClient doesn't hang on the infinite generator loop.
        """
        from unittest.mock import patch

        from api.dependencies import get_price_service
        from main import app

        _install("business")
        mock_svc = AsyncMock()
        mock_svc.get_current_prices.return_value = []
        app.dependency_overrides[get_price_service] = lambda: mock_svc

        async def _one_event(*args, **kwargs):
            yield 'data: {"test": true}\n\n'

        with patch("api.v1.prices_sse._price_event_generator", _one_event):
            client = _client()
            resp = client.get("/api/v1/prices/stream?region=us_ct")
            # Business user should pass the tier check (200 from SSE).
            # 500 is also acceptable when prior async tests leave the event
            # loop in a closed state — the important assertion is NOT 403.
            assert resp.status_code != 403


# =============================================================================
# 8. POST /api/v1/alerts — free-tier alert limit
# =============================================================================


class TestAlertFreeTierLimit:
    """Free users can create 1 alert max; pro/business have no limit."""

    def test_free_user_can_create_first_alert(self):
        _install("free", alert_count=0)
        client = _client()
        resp = client.post(
            "/api/v1/alerts",
            json={"price_below": 0.20, "region": "us_ct"},
        )
        # Should not be 403 (count is 0, under limit)
        assert resp.status_code != 403

    def test_free_user_blocked_on_second_alert(self):
        _install("free", alert_count=1)
        client = _client()
        resp = client.post(
            "/api/v1/alerts",
            json={"price_below": 0.18, "region": "us_ct"},
        )
        assert resp.status_code == 403
        assert "Alert limit reached" in resp.json()["detail"]

    def test_pro_user_unlimited_alerts(self):
        _install("pro", alert_count=10)
        client = _client()
        resp = client.post(
            "/api/v1/alerts",
            json={"price_below": 0.18, "region": "us_ct"},
        )
        # Pro users skip the limit check entirely
        assert resp.status_code != 403

    def test_business_user_unlimited_alerts(self):
        _install("business", alert_count=50)
        client = _client()
        resp = client.post(
            "/api/v1/alerts",
            json={"price_below": 0.15, "region": "us_ny"},
        )
        assert resp.status_code != 403

    def test_none_tier_treated_as_free(self):
        _install(None, alert_count=1)
        client = _client()
        resp = client.post(
            "/api/v1/alerts",
            json={"price_below": 0.20, "region": "us_ct"},
        )
        assert resp.status_code == 403
        assert "Alert limit reached" in resp.json()["detail"]
