"""
Tests for tier gating on premium analytics endpoints.

Coverage:
  - GET /api/v1/forecast/{utility_type} — require_tier("pro")
  - GET /api/v1/forecast — require_tier("pro")
  - GET /api/v1/reports/optimization — require_tier("business")
  - GET /api/v1/export/rates — require_tier("business")
  - GET /api/v1/export/types — require_tier("business")
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session

# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

TEST_USER_ID = "dddddddd-0000-0000-0000-000000000099"


# ---------------------------------------------------------------------------
# Mock helpers (same pattern as test_tier_gating.py)
# ---------------------------------------------------------------------------


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar.return_value = value
    row = MagicMock()
    row.__getitem__ = lambda self, k: value
    result.fetchone.return_value = row
    return result


def _mapping_result(rows=None):
    result = MagicMock()
    mapping = MagicMock()
    mapping.all.return_value = rows or []
    mapping.first.return_value = None
    result.mappings.return_value = mapping
    result.rowcount = 0
    result.scalar.return_value = 0
    result.scalar_one_or_none.return_value = None
    return result


def _make_db(tier: str):
    db = AsyncMock()

    async def _execute(stmt, params=None):
        sql = str(stmt.text if hasattr(stmt, "text") else stmt).upper()
        if "SUBSCRIPTION_TIER" in sql:
            return _scalar_result(tier)
        return _mapping_result()

    db.execute = AsyncMock(side_effect=_execute)
    db.commit = AsyncMock()
    return db


def _session():
    return SessionData(
        user_id=TEST_USER_ID,
        email="premium@example.com",
        name="Premium Test",
        email_verified=True,
        role="user",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_overrides():
    from main import _app_rate_limiter, app

    _app_rate_limiter.reset()
    yield
    for dep in list(app.dependency_overrides.keys()):
        app.dependency_overrides.pop(dep, None)
    _app_rate_limiter.reset()


def _install(tier: str):
    from main import app

    session = _session()
    db = _make_db(tier)
    app.dependency_overrides[get_current_user] = lambda: session
    app.dependency_overrides[get_db_session] = lambda: db
    return db


def _client():
    from main import app

    return TestClient(app, raise_server_exceptions=False)


# =============================================================================
# 1. GET /api/v1/forecast/{utility_type} — require_tier("pro")
# =============================================================================


class TestForecastEndpointTierGating:
    """require_tier('pro') on GET /forecast/{utility_type}."""

    def test_free_user_gets_403(self):
        _install("free")
        resp = _client().get("/api/v1/forecast/electricity?state=CT")
        assert resp.status_code == 403

    def test_pro_user_allowed(self):
        _install("pro")
        resp = _client().get("/api/v1/forecast/electricity?state=CT")
        assert resp.status_code != 403

    def test_business_user_allowed(self):
        _install("business")
        resp = _client().get("/api/v1/forecast/electricity?state=CT")
        assert resp.status_code != 403

    def test_none_tier_gets_403(self):
        _install(None)
        resp = _client().get("/api/v1/forecast/electricity?state=CT")
        assert resp.status_code == 403


# =============================================================================
# 2. GET /api/v1/forecast — require_tier("pro")
# =============================================================================


class TestForecastListTierGating:
    """require_tier('pro') on GET /forecast (list types)."""

    def test_free_user_gets_403(self):
        _install("free")
        resp = _client().get("/api/v1/forecast")
        assert resp.status_code == 403

    def test_pro_user_gets_list(self):
        _install("pro")
        resp = _client().get("/api/v1/forecast")
        assert resp.status_code == 200
        data = resp.json()
        assert "supported_types" in data


# =============================================================================
# 3. GET /api/v1/reports/optimization — require_tier("business")
# =============================================================================


class TestReportsOptimizationTierGating:
    """require_tier('business') on GET /reports/optimization."""

    def test_free_user_gets_403(self):
        _install("free")
        resp = _client().get("/api/v1/reports/optimization?state=CT")
        assert resp.status_code == 403

    def test_pro_user_gets_403(self):
        _install("pro")
        resp = _client().get("/api/v1/reports/optimization?state=CT")
        assert resp.status_code == 403

    def test_business_user_allowed(self):
        _install("business")
        resp = _client().get("/api/v1/reports/optimization?state=CT")
        assert resp.status_code != 403

    def test_none_tier_gets_403(self):
        _install(None)
        resp = _client().get("/api/v1/reports/optimization?state=CT")
        assert resp.status_code == 403


# =============================================================================
# 4. GET /api/v1/export/rates — require_tier("business")
# =============================================================================


class TestExportRatesTierGating:
    """require_tier('business') on GET /export/rates."""

    def test_free_user_gets_403(self):
        _install("free")
        resp = _client().get("/api/v1/export/rates?utility_type=electricity")
        assert resp.status_code == 403

    def test_pro_user_gets_403(self):
        _install("pro")
        resp = _client().get("/api/v1/export/rates?utility_type=electricity")
        assert resp.status_code == 403

    def test_business_user_allowed(self):
        _install("business")
        resp = _client().get("/api/v1/export/rates?utility_type=electricity")
        assert resp.status_code != 403


# =============================================================================
# 5. GET /api/v1/export/types — require_tier("business")
# =============================================================================


class TestExportTypesTierGating:
    """require_tier('business') on GET /export/types."""

    def test_free_user_gets_403(self):
        _install("free")
        resp = _client().get("/api/v1/export/types")
        assert resp.status_code == 403

    def test_business_user_gets_list(self):
        _install("business")
        resp = _client().get("/api/v1/export/types")
        assert resp.status_code == 200
        data = resp.json()
        assert "supported_types" in data
        assert "formats" in data
