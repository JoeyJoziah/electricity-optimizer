"""
Tests for Feature Flag system.

Coverage:
  - FeatureFlagService unit tests:
      is_enabled: flag not found, disabled, tier gating, percentage rollout
      get_all_flags: empty and populated
      update_flag: single field, multiple fields, no-op (returns False)
  - GET  /internal/flags   — admin list (API key required)
  - PUT  /internal/flags/{name} — update flag (API key required, no-op → 404)
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.dependencies import verify_api_key, get_db_session

BASE = "/api/v1/internal"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


def _row_result(*cols) -> MagicMock:
    """Mock for result.fetchone() returning a sequence-like row."""
    result = MagicMock()
    # Pydantic-free row: support indexing by position
    row = MagicMock()
    for i, v in enumerate(cols):
        row.__getitem__ = MagicMock(side_effect=lambda k, _c=cols: _c[k])
    result.fetchone.return_value = row
    result.fetchall.return_value = []
    return result


def _none_result() -> MagicMock:
    result = MagicMock()
    result.fetchone.return_value = None
    result.fetchall.return_value = []
    return result


def _fetchall_result(rows: list) -> MagicMock:
    result = MagicMock()
    result.fetchone.return_value = None
    result.fetchall.return_value = rows
    return result


# ---------------------------------------------------------------------------
# TestClient fixture — function-scoped
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    from main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_overrides():
    from main import app, _app_rate_limiter

    _app_rate_limiter.reset()
    yield
    for dep in list(app.dependency_overrides.keys()):
        app.dependency_overrides.pop(dep, None)
    _app_rate_limiter.reset()


@pytest.fixture
def mock_db():
    return _mock_db()


@pytest.fixture
def auth_client(mock_db):
    from main import app

    app.dependency_overrides[verify_api_key] = lambda: True
    app.dependency_overrides[get_db_session] = lambda: mock_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def unauth_client(mock_db):
    from main import app

    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides[get_db_session] = lambda: mock_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db_session, None)


# ===========================================================================
# 1. FeatureFlagService.is_enabled
# ===========================================================================


class TestFeatureFlagServiceIsEnabled:
    """Unit tests for FeatureFlagService.is_enabled()."""

    @pytest.mark.asyncio
    async def test_unknown_flag_returns_false(self):
        from services.feature_flag_service import FeatureFlagService

        db = _mock_db()
        db.execute.return_value = _none_result()
        svc = FeatureFlagService(db)

        result = await svc.is_enabled("nonexistent_flag")
        assert result is False

    @pytest.mark.asyncio
    async def test_disabled_flag_returns_false(self):
        from services.feature_flag_service import FeatureFlagService

        db = _mock_db()
        row = MagicMock()
        # (enabled, tier_required, percentage)
        row.__getitem__ = MagicMock(side_effect=lambda k: [False, None, 100][k])
        result = MagicMock()
        result.fetchone.return_value = row
        db.execute.return_value = result
        svc = FeatureFlagService(db)

        assert await svc.is_enabled("connections") is False

    @pytest.mark.asyncio
    async def test_enabled_no_tier_returns_true(self):
        from services.feature_flag_service import FeatureFlagService

        db = _mock_db()
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda k: [True, None, 100][k])
        result = MagicMock()
        result.fetchone.return_value = row
        db.execute.return_value = result
        svc = FeatureFlagService(db)

        assert await svc.is_enabled("connections") is True

    @pytest.mark.asyncio
    async def test_tier_gate_blocks_free_user(self):
        from services.feature_flag_service import FeatureFlagService

        db = _mock_db()
        row = MagicMock()
        # enabled=True, tier_required='pro', percentage=100
        row.__getitem__ = MagicMock(side_effect=lambda k: [True, "pro", 100][k])
        result = MagicMock()
        result.fetchone.return_value = row
        db.execute.return_value = result
        svc = FeatureFlagService(db)

        assert await svc.is_enabled("connections", user_tier="free") is False

    @pytest.mark.asyncio
    async def test_tier_gate_allows_pro_user(self):
        from services.feature_flag_service import FeatureFlagService

        db = _mock_db()
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda k: [True, "pro", 100][k])
        result = MagicMock()
        result.fetchone.return_value = row
        db.execute.return_value = result
        svc = FeatureFlagService(db)

        assert await svc.is_enabled("connections", user_tier="pro") is True

    @pytest.mark.asyncio
    async def test_tier_gate_allows_business_for_pro_flag(self):
        from services.feature_flag_service import FeatureFlagService

        db = _mock_db()
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda k: [True, "pro", 100][k])
        result = MagicMock()
        result.fetchone.return_value = row
        db.execute.return_value = result
        svc = FeatureFlagService(db)

        assert await svc.is_enabled("connections", user_tier="business") is True

    @pytest.mark.asyncio
    async def test_tier_check_skipped_when_no_user_tier(self):
        """When user_tier is not provided the tier gate must not block."""
        from services.feature_flag_service import FeatureFlagService

        db = _mock_db()
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda k: [True, "pro", 100][k])
        result = MagicMock()
        result.fetchone.return_value = row
        db.execute.return_value = result
        svc = FeatureFlagService(db)

        # No user_tier supplied — tier gate is skipped
        assert await svc.is_enabled("connections") is True

    @pytest.mark.asyncio
    async def test_zero_percent_always_excluded(self):
        """percentage=0 means nobody gets in (hash % 100 >= 0 always)."""
        from services.feature_flag_service import FeatureFlagService

        db = _mock_db()
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda k: [True, None, 0][k])
        result = MagicMock()
        result.fetchone.return_value = row
        db.execute.return_value = result
        svc = FeatureFlagService(db)

        assert await svc.is_enabled("optimization_schedule", user_id=str(uuid4())) is False

    @pytest.mark.asyncio
    async def test_hundred_percent_always_included(self):
        """percentage=100 means the hash check is skipped entirely."""
        from services.feature_flag_service import FeatureFlagService

        db = _mock_db()
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda k: [True, None, 100][k])
        result = MagicMock()
        result.fetchone.return_value = row
        db.execute.return_value = result
        svc = FeatureFlagService(db)

        assert await svc.is_enabled("bill_upload", user_id=str(uuid4())) is True

    @pytest.mark.asyncio
    async def test_percentage_rollout_deterministic(self):
        """Same flag+user combo must always return the same decision."""
        import hashlib
        from services.feature_flag_service import FeatureFlagService

        user_id = "deterministic-user-id"
        flag_name = "beta_feature"

        db = _mock_db()
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda k: [True, None, 50][k])
        result = MagicMock()
        result.fetchone.return_value = row
        db.execute.return_value = result
        svc = FeatureFlagService(db)

        # Compute expected result
        hash_val = int(
            hashlib.md5(f"{flag_name}:{user_id}".encode()).hexdigest()[:8], 16
        )
        expected = (hash_val % 100) < 50

        # Call twice — DB mock returns same result each time
        first = await svc.is_enabled(flag_name, user_id=user_id)
        db.execute.return_value = result  # reset side-effect
        second = await svc.is_enabled(flag_name, user_id=user_id)

        assert first == expected
        assert second == expected


# ===========================================================================
# 2. FeatureFlagService.get_all_flags
# ===========================================================================


class TestFeatureFlagServiceGetAllFlags:
    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        from services.feature_flag_service import FeatureFlagService

        db = _mock_db()
        db.execute.return_value = _fetchall_result([])
        svc = FeatureFlagService(db)

        flags = await svc.get_all_flags()
        assert flags == []

    @pytest.mark.asyncio
    async def test_maps_rows_to_dicts(self):
        from services.feature_flag_service import FeatureFlagService

        # Each row: (name, enabled, tier_required, percentage, description)
        rows = [
            ("connections", True, "pro", 100, "Utility connection feature"),
            ("optimization_schedule", False, None, 0, "Appliance scheduling"),
        ]
        db = _mock_db()
        db.execute.return_value = _fetchall_result(rows)
        svc = FeatureFlagService(db)

        flags = await svc.get_all_flags()
        assert len(flags) == 2
        assert flags[0]["name"] == "connections"
        assert flags[0]["enabled"] is True
        assert flags[0]["tier_required"] == "pro"
        assert flags[1]["enabled"] is False
        assert flags[1]["percentage"] == 0


# ===========================================================================
# 3. FeatureFlagService.update_flag
# ===========================================================================


class TestFeatureFlagServiceUpdateFlag:
    @pytest.mark.asyncio
    async def test_update_enabled_only(self):
        from services.feature_flag_service import FeatureFlagService

        db = _mock_db()
        svc = FeatureFlagService(db)

        result = await svc.update_flag("connections", enabled=True)
        assert result is True
        db.execute.assert_awaited_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self):
        from services.feature_flag_service import FeatureFlagService

        db = _mock_db()
        svc = FeatureFlagService(db)

        result = await svc.update_flag(
            "connections", enabled=False, tier_required="business", percentage=50
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_no_fields_returns_false(self):
        from services.feature_flag_service import FeatureFlagService

        db = _mock_db()
        svc = FeatureFlagService(db)

        result = await svc.update_flag("connections")
        assert result is False
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_percentage_only(self):
        from services.feature_flag_service import FeatureFlagService

        db = _mock_db()
        svc = FeatureFlagService(db)

        result = await svc.update_flag("bill_upload", percentage=75)
        assert result is True


# ===========================================================================
# 4. GET /internal/flags  (admin list)
# ===========================================================================


class TestGetFeatureFlags:
    def test_list_flags_returns_data(self, auth_client, mock_db):
        rows = [
            ("connections", True, "pro", 100, "Utility connection feature"),
        ]
        mock_db.execute.return_value = _fetchall_result(rows)

        resp = auth_client.get(f"{BASE}/flags")
        assert resp.status_code == 200
        data = resp.json()
        assert "flags" in data
        assert data["flags"][0]["name"] == "connections"

    def test_list_flags_empty(self, auth_client, mock_db):
        mock_db.execute.return_value = _fetchall_result([])

        resp = auth_client.get(f"{BASE}/flags")
        assert resp.status_code == 200
        assert resp.json()["flags"] == []

    def test_list_flags_requires_api_key(self, unauth_client):
        resp = unauth_client.get(f"{BASE}/flags")
        assert resp.status_code == 401


# ===========================================================================
# 5. PUT /internal/flags/{name}
# ===========================================================================


class TestUpdateFeatureFlag:
    def test_update_enabled_succeeds(self, auth_client, mock_db):
        # Service returns True when a field is supplied
        mock_db.execute.return_value = MagicMock()

        resp = auth_client.put(f"{BASE}/flags/connections", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_update_percentage_succeeds(self, auth_client, mock_db):
        mock_db.execute.return_value = MagicMock()

        resp = auth_client.put(
            f"{BASE}/flags/bill_upload", json={"percentage": 50}
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_update_all_fields(self, auth_client, mock_db):
        mock_db.execute.return_value = MagicMock()

        resp = auth_client.put(
            f"{BASE}/flags/optimization_schedule",
            json={"enabled": True, "tier_required": "pro", "percentage": 25},
        )
        assert resp.status_code == 200

    def test_empty_body_returns_404(self, auth_client, mock_db):
        """Sending no recognised fields → service returns False → 404."""
        resp = auth_client.put(f"{BASE}/flags/connections", json={})
        assert resp.status_code == 404

    def test_requires_api_key(self, unauth_client):
        resp = unauth_client.put(
            f"{BASE}/flags/connections", json={"enabled": True}
        )
        assert resp.status_code == 401

    def test_percentage_boundary_zero(self, auth_client, mock_db):
        mock_db.execute.return_value = MagicMock()

        resp = auth_client.put(
            f"{BASE}/flags/optimization_schedule", json={"percentage": 0}
        )
        assert resp.status_code == 200

    def test_percentage_boundary_hundred(self, auth_client, mock_db):
        mock_db.execute.return_value = MagicMock()

        resp = auth_client.put(
            f"{BASE}/flags/connections", json={"percentage": 100}
        )
        assert resp.status_code == 200

    def test_percentage_above_hundred_is_rejected(self, auth_client, mock_db):
        """percentage > 100 violates Pydantic constraint → 422."""
        resp = auth_client.put(
            f"{BASE}/flags/connections", json={"percentage": 101}
        )
        assert resp.status_code == 422

    def test_percentage_below_zero_is_rejected(self, auth_client, mock_db):
        """percentage < 0 violates Pydantic constraint → 422."""
        resp = auth_client.put(
            f"{BASE}/flags/connections", json={"percentage": -1}
        )
        assert resp.status_code == 422
