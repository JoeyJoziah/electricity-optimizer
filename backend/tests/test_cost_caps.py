"""
Tests for POST /api/v1/internal/cost-caps/check

Mocks the four async collector functions to avoid hitting the DB.
Verifies: response shape, breach detection, error handling per collector.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session, verify_api_key
from app_factory import create_app

# ---------------------------------------------------------------------------
# App + client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def app():
    fastapi_app, _ = create_app()
    # Bypass DB and API-key dependencies globally for this test module
    fastapi_app.dependency_overrides[get_db_session] = lambda: MagicMock()
    fastapi_app.dependency_overrides[verify_api_key] = lambda: True
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def client(app):
    return TestClient(app)


# ---------------------------------------------------------------------------
# Canned service payloads
# ---------------------------------------------------------------------------

_CLEAN_SERVICES = [
    {
        "service": "resend",
        "metric": 1000,
        "unit": "emails",
        "monthly_limit": 50_000,
        "fraction": 0.02,
        "estimated_cost_usd": 0.40,
        "budget_cap_usd": 20.00,
        "breach_level": None,
    },
    {
        "service": "neon",
        "metric": {"size_mb": 50.0, "active_connections": 2},
        "unit": "storage_mb + active_conns",
        "monthly_limit": {"storage_mb": 512, "max_active_conns": 30},
        "fraction": 0.10,
        "estimated_cost_usd": 5.86,
        "budget_cap_usd": 30.00,
        "breach_level": None,
        "note": "Proxy metric — verify against Neon dashboard for exact billing",
    },
    {
        "service": "cf_worker",
        "metric": 200_000,
        "unit": "requests",
        "monthly_limit": 10_000_000,
        "fraction": 0.02,
        "estimated_cost_usd": 0.40,
        "budget_cap_usd": 20.00,
        "breach_level": None,
        "note": "Verify against CF dashboard — gateway_request_logs table found",
    },
    {
        "service": "render",
        "metric": 0.40,
        "unit": "fraction_of_billing_month_elapsed",
        "monthly_limit": 1.0,
        "fraction": 0.40,
        "estimated_cost_usd": 2.80,
        "budget_cap_usd": 7.00,
        "breach_level": None,
        "note": "Flat-rate $7/mo. Monitor CPU via Render dashboard. No threshold breach on time proxy.",
    },
]

_BREACH_RESEND = {
    **_CLEAN_SERVICES[0],
    "fraction": 0.85,
    "estimated_cost_usd": 17.00,
    "breach_level": "warning_high",
}

_BREACH_NEON_CRITICAL = {
    **_CLEAN_SERVICES[1],
    "fraction": 1.05,
    "estimated_cost_usd": 30.00,
    "breach_level": "critical",
}

_URL = "/api/v1/internal/cost-caps/check"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_collectors(r_val, n_val, c_val, rd_val):
    """Context manager that patches all four collector functions."""
    return (
        patch(
            "api.v1.internal.cost_caps._resend_usage", new_callable=AsyncMock, return_value=r_val
        ),
        patch("api.v1.internal.cost_caps._neon_usage", new_callable=AsyncMock, return_value=n_val),
        patch(
            "api.v1.internal.cost_caps._cf_worker_usage", new_callable=AsyncMock, return_value=c_val
        ),
        patch(
            "api.v1.internal.cost_caps._render_usage", new_callable=AsyncMock, return_value=rd_val
        ),
    )


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


class TestCostCapsShape:
    def test_returns_checked_at_and_services_and_breaches(self, client):
        s = _CLEAN_SERVICES
        with (
            patch(
                "api.v1.internal.cost_caps._resend_usage", new_callable=AsyncMock, return_value=s[0]
            ),
            patch(
                "api.v1.internal.cost_caps._neon_usage", new_callable=AsyncMock, return_value=s[1]
            ),
            patch(
                "api.v1.internal.cost_caps._cf_worker_usage",
                new_callable=AsyncMock,
                return_value=s[2],
            ),
            patch(
                "api.v1.internal.cost_caps._render_usage", new_callable=AsyncMock, return_value=s[3]
            ),
        ):
            resp = client.post(_URL)

        assert resp.status_code == 200
        body = resp.json()
        assert "checked_at" in body
        assert "services" in body
        assert "breaches" in body
        assert len(body["services"]) == 4

    def test_no_breaches_when_all_clean(self, client):
        s = _CLEAN_SERVICES
        with (
            patch(
                "api.v1.internal.cost_caps._resend_usage", new_callable=AsyncMock, return_value=s[0]
            ),
            patch(
                "api.v1.internal.cost_caps._neon_usage", new_callable=AsyncMock, return_value=s[1]
            ),
            patch(
                "api.v1.internal.cost_caps._cf_worker_usage",
                new_callable=AsyncMock,
                return_value=s[2],
            ),
            patch(
                "api.v1.internal.cost_caps._render_usage", new_callable=AsyncMock, return_value=s[3]
            ),
        ):
            resp = client.post(_URL)

        assert resp.json()["breaches"] == []

    def test_breach_appears_in_breaches_list(self, client):
        s = _CLEAN_SERVICES
        with (
            patch(
                "api.v1.internal.cost_caps._resend_usage",
                new_callable=AsyncMock,
                return_value=_BREACH_RESEND,
            ),
            patch(
                "api.v1.internal.cost_caps._neon_usage", new_callable=AsyncMock, return_value=s[1]
            ),
            patch(
                "api.v1.internal.cost_caps._cf_worker_usage",
                new_callable=AsyncMock,
                return_value=s[2],
            ),
            patch(
                "api.v1.internal.cost_caps._render_usage", new_callable=AsyncMock, return_value=s[3]
            ),
        ):
            resp = client.post(_URL)

        body = resp.json()
        assert len(body["breaches"]) == 1
        breach = body["breaches"][0]
        assert breach["service"] == "resend"
        assert breach["level"] == "warning_high"
        assert breach["fraction"] == pytest.approx(0.85)

    def test_multiple_breaches(self, client):
        s = _CLEAN_SERVICES
        with (
            patch(
                "api.v1.internal.cost_caps._resend_usage",
                new_callable=AsyncMock,
                return_value=_BREACH_RESEND,
            ),
            patch(
                "api.v1.internal.cost_caps._neon_usage",
                new_callable=AsyncMock,
                return_value=_BREACH_NEON_CRITICAL,
            ),
            patch(
                "api.v1.internal.cost_caps._cf_worker_usage",
                new_callable=AsyncMock,
                return_value=s[2],
            ),
            patch(
                "api.v1.internal.cost_caps._render_usage", new_callable=AsyncMock, return_value=s[3]
            ),
        ):
            resp = client.post(_URL)

        body = resp.json()
        assert len(body["breaches"]) == 2
        levels = {b["service"]: b["level"] for b in body["breaches"]}
        assert levels["resend"] == "warning_high"
        assert levels["neon"] == "critical"


# ---------------------------------------------------------------------------
# Breach levels
# ---------------------------------------------------------------------------


class TestBreachedLevel:
    """Unit tests for the _breached_level helper."""

    def test_below_50_is_none(self):
        from api.v1.internal.cost_caps import _breached_level

        assert _breached_level(0.49) is None

    def test_exactly_50_is_warning_low(self):
        from api.v1.internal.cost_caps import _breached_level

        assert _breached_level(0.50) == "warning_low"

    def test_between_50_and_80_is_warning_low(self):
        from api.v1.internal.cost_caps import _breached_level

        assert _breached_level(0.75) == "warning_low"

    def test_exactly_80_is_warning_high(self):
        from api.v1.internal.cost_caps import _breached_level

        assert _breached_level(0.80) == "warning_high"

    def test_between_80_and_100_is_warning_high(self):
        from api.v1.internal.cost_caps import _breached_level

        assert _breached_level(0.95) == "warning_high"

    def test_exactly_100_is_critical(self):
        from api.v1.internal.cost_caps import _breached_level

        assert _breached_level(1.00) == "critical"

    def test_over_100_is_critical(self):
        from api.v1.internal.cost_caps import _breached_level

        assert _breached_level(1.20) == "critical"


# ---------------------------------------------------------------------------
# Error resilience
# ---------------------------------------------------------------------------


class TestCollectorErrors:
    def test_collector_error_does_not_abort_response(self, client):
        """A single collector failure returns an error entry, not a 500."""
        s = _CLEAN_SERVICES
        with (
            patch(
                "api.v1.internal.cost_caps._resend_usage",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB timeout"),
            ),
            patch(
                "api.v1.internal.cost_caps._neon_usage", new_callable=AsyncMock, return_value=s[1]
            ),
            patch(
                "api.v1.internal.cost_caps._cf_worker_usage",
                new_callable=AsyncMock,
                return_value=s[2],
            ),
            patch(
                "api.v1.internal.cost_caps._render_usage", new_callable=AsyncMock, return_value=s[3]
            ),
        ):
            resp = client.post(_URL)

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["services"]) == 4
        error_entry = next(s for s in body["services"] if s.get("error"))
        assert "timeout" in error_entry["error"].lower() or "db" in error_entry["error"].lower()
        assert error_entry["breach_level"] is None

    def test_all_collectors_error_returns_empty_breaches(self, client):
        exc = RuntimeError("all down")
        with (
            patch(
                "api.v1.internal.cost_caps._resend_usage", new_callable=AsyncMock, side_effect=exc
            ),
            patch("api.v1.internal.cost_caps._neon_usage", new_callable=AsyncMock, side_effect=exc),
            patch(
                "api.v1.internal.cost_caps._cf_worker_usage",
                new_callable=AsyncMock,
                side_effect=exc,
            ),
            patch(
                "api.v1.internal.cost_caps._render_usage", new_callable=AsyncMock, side_effect=exc
            ),
        ):
            resp = client.post(_URL)

        assert resp.status_code == 200
        assert resp.json()["breaches"] == []


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


class TestAuthGuard:
    def test_missing_api_key_returns_4xx(self):
        """Without overriding verify_api_key, a missing key should be rejected."""
        fastapi_app, _ = create_app()
        fastapi_app.dependency_overrides[get_db_session] = lambda: MagicMock()
        # Do NOT override verify_api_key — exercise the real guard
        client_no_auth = TestClient(fastapi_app, raise_server_exceptions=False)
        resp = client_no_auth.post(_URL)
        assert resp.status_code in (401, 403)
