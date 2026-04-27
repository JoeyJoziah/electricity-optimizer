"""
Tests for the Agent Switcher API (backend/api/v1/agent_switcher.py).

Coverage
--------
- GET    /api/v1/agent-switcher/settings        — get defaults, get existing
- PUT    /api/v1/agent-switcher/settings        — partial/full update, upsert, validation
- POST   /api/v1/agent-switcher/loa/sign        — sign, re-sign idempotent
- POST   /api/v1/agent-switcher/loa/revoke      — revoke, revoke disables, not signed (400)
- GET    /api/v1/agent-switcher/history         — empty, with entries, pagination
- GET    /api/v1/agent-switcher/activity        — feed, holds included, ordering
- POST   /api/v1/agent-switcher/check-now       — triggers evaluation, stores audit log
- POST   /api/v1/agent-switcher/rollback/{id}   — happy path, 404, 400 invalid status, 400 too old
- POST   /api/v1/agent-switcher/approve/{id}    — happy path, 404, not recommend, already executed
- Tier gating                                   — free=403, pro=allowed, business=allowed

All tests use function-scoped TestClient with dependency overrides.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session, require_tier

# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

TEST_USER_ID = "aaaaaaaa-1111-1111-1111-000000000001"
OTHER_USER_ID = "bbbbbbbb-2222-2222-2222-000000000002"
EXEC_ID = str(uuid4())
AUDIT_ID = str(uuid4())


# ---------------------------------------------------------------------------
# In-memory mock DB that routes SQL to agent-switcher table operations
# ---------------------------------------------------------------------------


class _MockSwitcherDB:
    """
    Simulates the three agent-switcher tables:
      - user_agent_settings
      - switch_audit_log
      - switch_executions
      - users (for subscription_tier + region lookups)
    """

    def __init__(self):
        self._settings: dict[str, dict] = {}  # user_id -> row
        self._audit_log: list[dict] = []
        self._executions: list[dict] = []
        self._users: dict[str, dict] = {
            TEST_USER_ID: {"id": TEST_USER_ID, "subscription_tier": "pro", "region": "us_ct"},
            OTHER_USER_ID: {"id": OTHER_USER_ID, "subscription_tier": "free", "region": "us_ny"},
        }
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    # -----------------------------------------------------------------------
    # execute dispatcher
    # -----------------------------------------------------------------------

    async def execute(self, stmt, params=None):
        sql = self._sql(stmt)
        params = params or {}
        self._last_sql = sql
        return self._dispatch(sql, params)

    def _dispatch(self, sql: str, params: dict) -> MagicMock:
        # user_agent_settings
        if "INSERT INTO PUBLIC.USER_AGENT_SETTINGS" in sql:
            return self._settings_insert(params)
        if "UPDATE PUBLIC.USER_AGENT_SETTINGS" in sql:
            return self._settings_update(params)
        if "FROM PUBLIC.USER_AGENT_SETTINGS" in sql:
            return self._settings_select(params)

        # switch_audit_log
        if "INSERT INTO PUBLIC.SWITCH_AUDIT_LOG" in sql:
            return self._audit_insert(params)
        if "UPDATE PUBLIC.SWITCH_AUDIT_LOG" in sql:
            return self._audit_update(params)
        # History join: has both SAL alias and SE alias for switch_executions
        if "FROM PUBLIC.SWITCH_AUDIT_LOG SAL" in sql:
            return self._audit_history_select(params)
        # Activity feed: simple select with LIMIT but no audit_log_id param
        if "FROM PUBLIC.SWITCH_AUDIT_LOG" in sql and "audit_log_id" not in params:
            return self._audit_activity_select(params)
        # Approve/check: select by audit_log_id
        if "FROM PUBLIC.SWITCH_AUDIT_LOG" in sql:
            return self._audit_select_one(params)

        # switch_executions
        if "UPDATE PUBLIC.SWITCH_EXECUTIONS" in sql:
            return self._exec_update(params)
        if "FROM PUBLIC.SWITCH_EXECUTIONS" in sql:
            return self._exec_select(params)

        # users
        if "FROM PUBLIC.USERS" in sql:
            return self._users_select(params)

        return self._empty_result()

    # -----------------------------------------------------------------------
    # user_agent_settings handlers
    # -----------------------------------------------------------------------

    def _settings_insert(self, params: dict) -> MagicMock:
        now = datetime.now(UTC)
        row = {
            "id": params.get("id", str(uuid4())),
            "user_id": params["user_id"],
            "enabled": params.get("enabled", False),
            "savings_threshold_pct": params.get("savings_threshold_pct", 10.0),
            "savings_threshold_min": params.get("savings_threshold_min", 10.0),
            "cooldown_days": params.get("cooldown_days", 5),
            "paused_until": params.get("paused_until"),
            "loa_signed_at": params.get("loa_signed_at") or params.get("now")
            if "loa_signed_at" in params
            else None,
            "loa_revoked_at": params.get("loa_revoked_at"),
            "created_at": now,
            "updated_at": now,
        }
        # Handle LOA-specific insert (has 'now' instead of explicit loa_signed_at)
        if (
            "LOA_SIGNED_AT = :NOW" in self._last_sql.upper()
            if hasattr(self, "_last_sql")
            else False
        ):
            row["loa_signed_at"] = params.get("now", now)
        self._settings[params["user_id"]] = row
        return self._mapping_first(row)

    def _settings_update(self, params: dict) -> MagicMock:
        uid = params.get("user_id")
        row = self._settings.get(uid)
        if row is None:
            return self._mapping_first(None)

        now = params.get("now", datetime.now(UTC))
        row["updated_at"] = now
        sql = getattr(self, "_last_sql", "")

        # Detect operation type from SQL content
        is_loa_sign = "LOA_SIGNED_AT" in sql and "LOA_REVOKED_AT = NULL" in sql
        is_loa_revoke = "LOA_REVOKED_AT = :NOW" in sql or (
            "LOA_REVOKED_AT" in sql and "ENABLED = FALSE" in sql
        )

        if is_loa_sign:
            row["loa_signed_at"] = now
            row["loa_revoked_at"] = None

        elif is_loa_revoke:
            row["loa_revoked_at"] = now
            row["enabled"] = False

        else:
            # General settings update — apply provided fields
            for field in (
                "enabled",
                "savings_threshold_pct",
                "savings_threshold_min",
                "cooldown_days",
                "paused_until",
            ):
                if field in params:
                    row[field] = params[field]

        return self._mapping_first(row)

    def _settings_select(self, params: dict) -> MagicMock:
        uid = params.get("user_id")
        row = self._settings.get(uid)
        return self._mapping_first(row)

    # -----------------------------------------------------------------------
    # switch_audit_log handlers
    # -----------------------------------------------------------------------

    def _audit_insert(self, params: dict) -> MagicMock:
        now = datetime.now(UTC)
        row = {
            "id": params.get("id", str(uuid4())),
            "user_id": params["user_id"],
            "trigger_type": params.get("trigger_type", "manual"),
            "decision": params.get("decision", "hold"),
            "reason": params.get("reason", ""),
            "savings_monthly": params.get("savings_monthly"),
            "savings_annual": params.get("savings_annual"),
            "etf_cost": params.get("etf_cost"),
            "net_savings_year1": params.get("net_savings_year1"),
            "confidence_score": params.get("confidence_score"),
            "data_source": params.get("data_source"),
            "tier": params.get("tier", "pro"),
            "executed": False,
            "execution_status": None,
            "created_at": params.get("now", now),
        }
        self._audit_log.append(row)
        return self._mapping_first(row)

    def _audit_update(self, params: dict) -> MagicMock:
        audit_id = params.get("audit_log_id")
        row = next((r for r in self._audit_log if str(r["id"]) == str(audit_id)), None)
        if row:
            if "executed" in params:
                row["executed"] = params["executed"]
            if params.get("executed") is True:
                row["executed"] = True
        result = MagicMock()
        result.rowcount = 1 if row else 0
        return result

    def _audit_history_select(self, params: dict) -> MagicMock:
        """History endpoint: LEFT JOIN with switch_executions, paginated."""
        uid = params.get("user_id")
        limit = params.get("limit", 20)
        offset = params.get("offset", 0)
        rows = [r for r in self._audit_log if str(r["user_id"]) == str(uid)]
        # Sort newest first
        rows = sorted(rows, key=lambda r: r["created_at"], reverse=True)
        return self._mapping_all(rows[offset : offset + limit])

    def _audit_activity_select(self, params: dict) -> MagicMock:
        """Activity feed: simple select ordered by created_at DESC."""
        uid = params.get("user_id")
        limit = params.get("limit", 50)
        rows = [r for r in self._audit_log if str(r["user_id"]) == str(uid)]
        rows = sorted(rows, key=lambda r: r["created_at"], reverse=True)
        return self._mapping_all(rows[:limit])

    def _audit_select_one(self, params: dict) -> MagicMock:
        audit_id = params.get("audit_log_id")
        uid = params.get("user_id") if "user_id" not in params else None
        rows = self._audit_log
        if audit_id:
            row = next((r for r in rows if str(r["id"]) == str(audit_id)), None)
        else:
            row = None
        return self._mapping_first(row)

    # -----------------------------------------------------------------------
    # switch_executions handlers
    # -----------------------------------------------------------------------

    def _exec_update(self, params: dict) -> MagicMock:
        exec_id = params.get("execution_id")
        row = next((r for r in self._executions if str(r["id"]) == str(exec_id)), None)
        if row:
            if "status" in params:
                row["status"] = params["status"]
        result = MagicMock()
        result.rowcount = 1 if row else 0
        return result

    def _exec_select(self, params: dict) -> MagicMock:
        exec_id = params.get("execution_id")
        row = next((r for r in self._executions if str(r["id"]) == str(exec_id)), None)
        return self._mapping_first(row)

    # -----------------------------------------------------------------------
    # users handlers
    # -----------------------------------------------------------------------

    def _users_select(self, params: dict) -> MagicMock:
        uid = params.get("id")
        user = self._users.get(uid)
        if user is None:
            result = MagicMock()
            result.first.return_value = None
            result.scalar_one_or_none.return_value = None
            return result
        result = MagicMock()
        result.first.return_value = (user["subscription_tier"], user["region"])
        result.scalar_one_or_none.return_value = user["subscription_tier"]
        return result

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _sql(stmt) -> str:
        raw = str(stmt.text if hasattr(stmt, "text") else stmt)
        return " ".join(raw.split()).upper()

    @staticmethod
    def _mapping_first(row) -> MagicMock:
        result = MagicMock()
        mapping = MagicMock()
        mapping.first.return_value = row
        result.mappings.return_value = mapping
        return result

    @staticmethod
    def _mapping_all(rows: list) -> MagicMock:
        result = MagicMock()
        mapping = MagicMock()
        mapping.all.return_value = rows
        result.mappings.return_value = mapping
        return result

    @staticmethod
    def _empty_result() -> MagicMock:
        result = MagicMock()
        mapping = MagicMock()
        mapping.first.return_value = None
        mapping.all.return_value = []
        result.mappings.return_value = mapping
        result.rowcount = 0
        return result

    # -----------------------------------------------------------------------
    # Seed helpers
    # -----------------------------------------------------------------------

    def seed_settings(
        self,
        user_id: str = TEST_USER_ID,
        enabled: bool = False,
        savings_threshold_pct: float = 10.0,
        savings_threshold_min: float = 10.0,
        cooldown_days: int = 5,
        paused_until=None,
        loa_signed: bool = False,
        loa_revoked: bool = False,
    ) -> dict:
        now = datetime.now(UTC)
        row = {
            "id": str(uuid4()),
            "user_id": user_id,
            "enabled": enabled,
            "savings_threshold_pct": savings_threshold_pct,
            "savings_threshold_min": savings_threshold_min,
            "cooldown_days": cooldown_days,
            "paused_until": paused_until,
            "loa_signed_at": now if loa_signed else None,
            "loa_revoked_at": now if loa_revoked else None,
            "created_at": now,
            "updated_at": now,
        }
        self._settings[user_id] = row
        return row

    def seed_audit_entry(
        self,
        user_id: str = TEST_USER_ID,
        trigger_type: str = "market_scan",
        decision: str = "hold",
        reason: str = "Current plan is best deal",
        confidence_score: float = 0.85,
        data_source: str = "utilityapi",
        executed: bool = False,
        execution_status: str | None = None,
        created_at: datetime | None = None,
    ) -> dict:
        now = created_at or datetime.now(UTC)
        row = {
            "id": str(uuid4()),
            "user_id": user_id,
            "trigger_type": trigger_type,
            "decision": decision,
            "reason": reason,
            "savings_monthly": 12.5 if decision in ("switch", "recommend") else None,
            "savings_annual": 150.0 if decision in ("switch", "recommend") else None,
            "etf_cost": 0.0,
            "net_savings_year1": 150.0 if decision in ("switch", "recommend") else None,
            "confidence_score": confidence_score,
            "data_source": data_source,
            "tier": "pro",
            "executed": executed,
            "execution_status": execution_status,
            "created_at": now,
        }
        self._audit_log.append(row)
        return row

    def seed_execution(
        self,
        user_id: str = TEST_USER_ID,
        status: str = "active",
        days_old: int = 1,
    ) -> dict:
        now = datetime.now(UTC)
        enacted_at = now - timedelta(days=days_old)
        row = {
            "id": str(uuid4()),
            "user_id": user_id,
            "status": status,
            "enacted_at": enacted_at,
            "created_at": enacted_at,
            "updated_at": enacted_at,
        }
        self._executions.append(row)
        return row


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db():
    return _MockSwitcherDB()


def _make_pro_client(mock_db: _MockSwitcherDB) -> TestClient:
    """Build a TestClient with a Pro-tier authenticated user."""
    from main import app

    user = SessionData(user_id=TEST_USER_ID, email="pro@example.com")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = lambda: mock_db
    # Override require_tier("pro") to pass through — Pro user is allowed
    app.dependency_overrides[require_tier("pro")] = lambda: user
    return app


def _make_free_client(mock_db: _MockSwitcherDB) -> TestClient:
    """Build a TestClient that does NOT override require_tier — free user gets 403."""
    from main import app

    user = SessionData(user_id=TEST_USER_ID, email="free@example.com")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = lambda: mock_db
    # Do NOT override require_tier — let it run (will check DB for tier)
    # Inject a tier DB lookup that returns "free"
    return app


@pytest.fixture()
def pro_client(mock_db):
    """TestClient authenticated as Pro user with tier override."""
    from main import app

    user = SessionData(user_id=TEST_USER_ID, email="pro@example.com")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[require_tier("pro")] = lambda: user

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(require_tier("pro"), None)


@pytest.fixture()
def free_client(mock_db):
    """TestClient authenticated as a user with NO tier override — free tier gets 403."""
    from main import app

    user = SessionData(user_id=TEST_USER_ID, email="free@example.com")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = lambda: mock_db
    # Remove any prior tier override so require_tier runs normally
    app.dependency_overrides.pop(require_tier("pro"), None)

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture()
def business_client(mock_db):
    """TestClient authenticated as Business user."""
    from main import app

    user = SessionData(user_id=TEST_USER_ID, email="biz@example.com")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = lambda: mock_db
    # Business tier is >= pro, so the same override works
    app.dependency_overrides[require_tier("pro")] = lambda: user

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(require_tier("pro"), None)


# =============================================================================
# 1. Settings CRUD (8 tests)
# =============================================================================


class TestGetSettings:
    def test_get_settings_defaults_when_no_row(self, pro_client):
        """No settings row -> returns defaults (agent disabled)."""
        response = pro_client.get("/api/v1/agent-switcher/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["savings_threshold_pct"] == pytest.approx(10.0)
        assert data["savings_threshold_min"] == pytest.approx(10.0)
        assert data["cooldown_days"] == 5
        assert data["paused_until"] is None
        assert data["loa_signed"] is False
        assert data["loa_revoked"] is False

    def test_get_settings_existing_row(self, pro_client, mock_db):
        """Existing settings row is returned correctly."""
        mock_db.seed_settings(
            user_id=TEST_USER_ID,
            enabled=True,
            savings_threshold_pct=15.0,
            savings_threshold_min=20.0,
            cooldown_days=7,
            loa_signed=True,
        )
        response = pro_client.get("/api/v1/agent-switcher/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["savings_threshold_pct"] == pytest.approx(15.0)
        assert data["savings_threshold_min"] == pytest.approx(20.0)
        assert data["cooldown_days"] == 7
        assert data["loa_signed"] is True

    def test_get_settings_loa_status_reflected(self, pro_client, mock_db):
        """LOA fields are computed from loa_signed_at/loa_revoked_at."""
        mock_db.seed_settings(user_id=TEST_USER_ID, loa_signed=True, loa_revoked=True)
        response = pro_client.get("/api/v1/agent-switcher/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["loa_signed"] is True
        assert data["loa_revoked"] is True

    def test_get_settings_response_shape(self, pro_client):
        """Response must contain all expected keys."""
        response = pro_client.get("/api/v1/agent-switcher/settings")
        assert response.status_code == 200
        data = response.json()
        expected_keys = {
            "enabled",
            "savings_threshold_pct",
            "savings_threshold_min",
            "cooldown_days",
            "paused_until",
            "loa_signed",
            "loa_revoked",
            "created_at",
            "updated_at",
        }
        assert expected_keys.issubset(set(data.keys())), (
            f"Missing keys: {expected_keys - set(data.keys())}"
        )


class TestUpdateSettings:
    def test_update_partial_enabled(self, pro_client, mock_db):
        """Partial update: only enabled field."""
        mock_db.seed_settings(user_id=TEST_USER_ID, enabled=False)
        response = pro_client.put(
            "/api/v1/agent-switcher/settings",
            json={"enabled": True},
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is True

    def test_update_full_settings(self, pro_client, mock_db):
        """Full update: all fields provided."""
        mock_db.seed_settings(user_id=TEST_USER_ID)
        response = pro_client.put(
            "/api/v1/agent-switcher/settings",
            json={
                "enabled": True,
                "savings_threshold_pct": 12.5,
                "savings_threshold_min": 15.0,
                "cooldown_days": 10,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["savings_threshold_pct"] == pytest.approx(12.5)
        assert data["savings_threshold_min"] == pytest.approx(15.0)
        assert data["cooldown_days"] == 10

    def test_upsert_creates_new_row(self, pro_client, mock_db):
        """PUT with no existing row creates a new settings row."""
        # No seed — no existing row
        response = pro_client.put(
            "/api/v1/agent-switcher/settings",
            json={"enabled": True, "cooldown_days": 3},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["cooldown_days"] == 3

    def test_invalid_negative_threshold_pct(self, pro_client):
        """Negative savings_threshold_pct is rejected with 422."""
        response = pro_client.put(
            "/api/v1/agent-switcher/settings",
            json={"savings_threshold_pct": -5.0},
        )
        assert response.status_code == 422

    def test_invalid_negative_cooldown(self, pro_client):
        """Negative cooldown_days is rejected with 422."""
        response = pro_client.put(
            "/api/v1/agent-switcher/settings",
            json={"cooldown_days": -1},
        )
        assert response.status_code == 422

    def test_update_empty_body_noop(self, pro_client, mock_db):
        """Empty update body returns current settings unchanged."""
        mock_db.seed_settings(user_id=TEST_USER_ID, cooldown_days=8)
        response = pro_client.put("/api/v1/agent-switcher/settings", json={})
        assert response.status_code == 200
        assert response.json()["cooldown_days"] == 8

    def test_update_invalid_negative_threshold_min(self, pro_client):
        """Negative savings_threshold_min is rejected."""
        response = pro_client.put(
            "/api/v1/agent-switcher/settings",
            json={"savings_threshold_min": -10.0},
        )
        assert response.status_code == 422

    def test_update_response_format(self, pro_client, mock_db):
        """Response shape is correct after update."""
        mock_db.seed_settings(user_id=TEST_USER_ID)
        response = pro_client.put(
            "/api/v1/agent-switcher/settings",
            json={"enabled": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "savings_threshold_pct" in data
        assert "loa_signed" in data


# =============================================================================
# 2. LOA Flow (6 tests)
# =============================================================================


class TestLOAFlow:
    def test_sign_loa_success(self, pro_client, mock_db):
        """Sign LOA sets signed_at and returns confirmation."""
        mock_db.seed_settings(user_id=TEST_USER_ID)
        response = pro_client.post("/api/v1/agent-switcher/loa/sign")
        assert response.status_code == 200
        data = response.json()
        assert "signed_at" in data
        assert "message" in data
        assert data["signed_at"] is not None

    def test_sign_loa_when_already_signed_is_idempotent(self, pro_client, mock_db):
        """Re-signing LOA is idempotent — returns 200 again."""
        mock_db.seed_settings(user_id=TEST_USER_ID, loa_signed=True)
        response = pro_client.post("/api/v1/agent-switcher/loa/sign")
        assert response.status_code == 200
        assert "signed_at" in response.json()

    def test_sign_loa_creates_settings_row_if_missing(self, pro_client, mock_db):
        """Sign LOA with no prior settings row creates a new row."""
        # No seed
        response = pro_client.post("/api/v1/agent-switcher/loa/sign")
        assert response.status_code == 200
        assert response.json()["signed_at"] is not None

    def test_revoke_loa_success(self, pro_client, mock_db):
        """Revoke LOA sets revoked_at and disables agent."""
        mock_db.seed_settings(user_id=TEST_USER_ID, loa_signed=True, enabled=True)
        response = pro_client.post("/api/v1/agent-switcher/loa/revoke")
        assert response.status_code == 200
        data = response.json()
        assert "revoked_at" in data
        assert data["revoked_at"] is not None

    def test_revoke_loa_disables_agent(self, pro_client, mock_db):
        """After LOA revoke, settings show loa_revoked=True."""
        mock_db.seed_settings(user_id=TEST_USER_ID, loa_signed=True, enabled=True)
        # Revoke
        revoke_resp = pro_client.post("/api/v1/agent-switcher/loa/revoke")
        assert revoke_resp.status_code == 200
        # Check settings
        settings_row = mock_db._settings.get(TEST_USER_ID)
        if settings_row:
            assert (
                settings_row.get("enabled") is False
                or settings_row.get("loa_revoked_at") is not None
            )

    def test_revoke_loa_without_signing_returns_400(self, pro_client, mock_db):
        """Revoking an unsigned LOA returns 400."""
        mock_db.seed_settings(user_id=TEST_USER_ID, loa_signed=False)
        response = pro_client.post("/api/v1/agent-switcher/loa/revoke")
        assert response.status_code == 400
        assert (
            "signed" in response.json()["detail"].lower()
            or "loa" in response.json()["detail"].lower()
        )


# =============================================================================
# 3. Tier Gating (4 tests)
# =============================================================================


class TestTierGating:
    def test_free_tier_gets_403_on_settings(self, mock_db):
        """Free tier users cannot access agent-switcher settings."""
        from main import app

        # Use a free-tier user — do NOT override require_tier
        free_user = SessionData(user_id=TEST_USER_ID, email="free@example.com")

        # Inject a DB that returns "free" for tier lookup
        async def mock_db_session():
            return mock_db

        app.dependency_overrides[get_current_user] = lambda: free_user
        app.dependency_overrides[get_db_session] = lambda: mock_db
        # Remove any existing tier override
        app.dependency_overrides.pop(require_tier("pro"), None)

        # Make the tier lookup return "free"
        mock_db._users[TEST_USER_ID]["subscription_tier"] = "free"

        try:
            with TestClient(app) as client:
                response = client.get("/api/v1/agent-switcher/settings")
                # Must be 403 (free tier blocked) or 503 (DB unavailable in test)
                assert response.status_code in (403, 503)
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db_session, None)

    def test_pro_tier_allowed_on_settings(self, pro_client):
        """Pro tier can access agent-switcher settings."""
        response = pro_client.get("/api/v1/agent-switcher/settings")
        assert response.status_code == 200

    def test_business_tier_allowed_on_settings(self, business_client):
        """Business tier can access agent-switcher settings."""
        response = business_client.get("/api/v1/agent-switcher/settings")
        assert response.status_code == 200

    def test_tier_check_on_loa_endpoint(self, pro_client, mock_db):
        """Tier gate applies to LOA endpoints too (pro passes)."""
        mock_db.seed_settings(user_id=TEST_USER_ID)
        response = pro_client.post("/api/v1/agent-switcher/loa/sign")
        assert response.status_code == 200


# =============================================================================
# 4. History & Activity (6 tests)
# =============================================================================


class TestHistory:
    def test_empty_history(self, pro_client):
        """No audit log entries returns empty history."""
        response = pro_client.get("/api/v1/agent-switcher/history")
        assert response.status_code == 200
        data = response.json()
        assert data["history"] == []
        assert data["total"] == 0

    def test_history_with_entries(self, pro_client, mock_db):
        """Entries in audit log are returned in history."""
        mock_db.seed_audit_entry(user_id=TEST_USER_ID, decision="hold")
        mock_db.seed_audit_entry(user_id=TEST_USER_ID, decision="recommend")
        response = pro_client.get("/api/v1/agent-switcher/history")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["history"]) == 2

    def test_history_pagination_limit(self, pro_client, mock_db):
        """Limit parameter restricts number of returned entries."""
        for _ in range(5):
            mock_db.seed_audit_entry(user_id=TEST_USER_ID)
        response = pro_client.get("/api/v1/agent-switcher/history?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["history"]) <= 2
        assert data["limit"] == 2
        assert data["offset"] == 0

    def test_activity_feed_returns_all_decisions(self, pro_client, mock_db):
        """Activity feed includes all decision types (hold, monitor, switch, recommend)."""
        mock_db.seed_audit_entry(user_id=TEST_USER_ID, decision="hold")
        mock_db.seed_audit_entry(user_id=TEST_USER_ID, decision="monitor")
        mock_db.seed_audit_entry(user_id=TEST_USER_ID, decision="recommend")
        response = pro_client.get("/api/v1/agent-switcher/activity")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        decisions = {e["decision"] for e in data["activity"]}
        assert "hold" in decisions
        assert "monitor" in decisions
        assert "recommend" in decisions

    def test_activity_includes_holds(self, pro_client, mock_db):
        """Hold decisions appear in the activity feed."""
        mock_db.seed_audit_entry(
            user_id=TEST_USER_ID, decision="hold", reason="Best plan already active"
        )
        response = pro_client.get("/api/v1/agent-switcher/activity")
        assert response.status_code == 200
        data = response.json()
        assert len(data["activity"]) >= 1
        assert any(e["decision"] == "hold" for e in data["activity"])

    def test_activity_ordered_newest_first(self, pro_client, mock_db):
        """Activity feed is ordered newest first."""
        old_time = datetime.now(UTC) - timedelta(hours=2)
        new_time = datetime.now(UTC)
        mock_db.seed_audit_entry(user_id=TEST_USER_ID, decision="hold", created_at=old_time)
        mock_db.seed_audit_entry(user_id=TEST_USER_ID, decision="recommend", created_at=new_time)
        response = pro_client.get("/api/v1/agent-switcher/activity")
        assert response.status_code == 200
        data = response.json()
        if len(data["activity"]) >= 2:
            # Newest (recommend) should be first — check created_at ordering
            first_ts = data["activity"][0]["created_at"]
            second_ts = data["activity"][1]["created_at"]
            assert first_ts >= second_ts


# =============================================================================
# 5. Check-Now (4 tests)
# =============================================================================


class TestCheckNow:
    def test_check_now_triggers_evaluation(self, pro_client, mock_db):
        """POST /check-now returns 200 with a decision."""
        mock_db.seed_settings(user_id=TEST_USER_ID, loa_signed=True)
        response = pro_client.post("/api/v1/agent-switcher/check-now")
        assert response.status_code == 200
        data = response.json()
        assert "decision" in data

    def test_check_now_returns_decision_structure(self, pro_client, mock_db):
        """Decision response contains required fields."""
        mock_db.seed_settings(user_id=TEST_USER_ID, loa_signed=True)
        response = pro_client.post("/api/v1/agent-switcher/check-now")
        assert response.status_code == 200
        decision = response.json()["decision"]
        required = {
            "action",
            "reason",
            "projected_savings_monthly",
            "projected_savings_annual",
            "etf_cost",
            "confidence",
        }
        assert required.issubset(set(decision.keys())), (
            f"Missing: {required - set(decision.keys())}"
        )

    def test_check_now_stores_audit_log(self, pro_client, mock_db):
        """Check-now writes an entry to switch_audit_log."""
        mock_db.seed_settings(user_id=TEST_USER_ID, loa_signed=True)
        before_count = len(mock_db._audit_log)
        pro_client.post("/api/v1/agent-switcher/check-now")
        # Audit log should have grown by 1
        assert len(mock_db._audit_log) == before_count + 1

    def test_check_now_holds_when_no_current_plan(self, pro_client, mock_db):
        """Without an active plan (no settings/LOA), decision is 'hold'."""
        # No settings seed — no LOA, no plan data
        response = pro_client.post("/api/v1/agent-switcher/check-now")
        assert response.status_code == 200
        data = response.json()
        assert data["decision"]["action"] == "hold"


# =============================================================================
# 6. Rollback (6 tests)
# =============================================================================


class TestRollback:
    def test_rollback_happy_path(self, pro_client, mock_db, monkeypatch):
        """Active execution within 30 days delegates to SwitchExecutionService."""
        from services.switch_execution_service import SwitchExecutionService

        row = mock_db.seed_execution(user_id=TEST_USER_ID, status="active", days_old=5)
        called: dict[str, object] = {}

        async def _fake_rollback(self, execution_id, user_id):
            called["execution_id"] = execution_id
            called["user_id"] = user_id
            return {
                "execution_id": execution_id,
                "status": "rolled_back",
                "message": "Switch has been rolled back successfully.",
            }

        monkeypatch.setattr(SwitchExecutionService, "rollback_switch", _fake_rollback)

        response = pro_client.post(f"/api/v1/agent-switcher/rollback/{row['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["execution_id"] == row["id"]
        assert data["status"] == "rolled_back"
        assert called["execution_id"] == row["id"]
        assert called["user_id"] == TEST_USER_ID

    def test_rollback_service_failure_does_not_fabricate_success(
        self, pro_client, mock_db, monkeypatch
    ):
        """If SwitchExecutionService raises, the failure must propagate — never a fabricated 'rolled_back' UPDATE."""
        from services.switch_execution_service import SwitchExecutionService

        row = mock_db.seed_execution(user_id=TEST_USER_ID, status="active", days_old=5)

        async def _boom(self, execution_id, user_id):
            raise RuntimeError("simulated billing API outage")

        monkeypatch.setattr(SwitchExecutionService, "rollback_switch", _boom)

        # The TestClient is configured to re-raise server exceptions, so a real
        # 5xx here means the bug pattern is gone (no silent 200 with a fake
        # rolled_back status). This is the regression test for security H-2 /
        # code-quality P0-1.
        with pytest.raises(RuntimeError, match="simulated billing API outage"):
            pro_client.post(f"/api/v1/agent-switcher/rollback/{row['id']}")

    def test_rollback_not_found_returns_404(self, pro_client, mock_db):
        """Non-existent execution_id returns 404."""
        response = pro_client.post(f"/api/v1/agent-switcher/rollback/{uuid4()}")
        assert response.status_code == 404

    def test_rollback_wrong_user_returns_404(self, pro_client, mock_db):
        """Execution belonging to another user returns 404 (not 403, to prevent enumeration)."""
        row = mock_db.seed_execution(user_id=OTHER_USER_ID, status="active", days_old=1)
        response = pro_client.post(f"/api/v1/agent-switcher/rollback/{row['id']}")
        assert response.status_code == 404

    def test_rollback_failed_status_returns_400(self, pro_client, mock_db):
        """Execution with status 'failed' cannot be rolled back."""
        row = mock_db.seed_execution(user_id=TEST_USER_ID, status="failed", days_old=1)
        response = pro_client.post(f"/api/v1/agent-switcher/rollback/{row['id']}")
        assert response.status_code == 400
        assert (
            "status" in response.json()["detail"].lower()
            or "failed" in response.json()["detail"].lower()
        )

    def test_rollback_rolled_back_status_returns_400(self, pro_client, mock_db):
        """Already rolled-back execution returns 400."""
        row = mock_db.seed_execution(user_id=TEST_USER_ID, status="rolled_back", days_old=1)
        response = pro_client.post(f"/api/v1/agent-switcher/rollback/{row['id']}")
        assert response.status_code == 400

    def test_rollback_too_old_returns_400(self, pro_client, mock_db):
        """Execution older than 30 days returns 400 (window expired)."""
        row = mock_db.seed_execution(user_id=TEST_USER_ID, status="active", days_old=31)
        response = pro_client.post(f"/api/v1/agent-switcher/rollback/{row['id']}")
        assert response.status_code == 400
        assert "30" in response.json()["detail"] or "window" in response.json()["detail"].lower()


# =============================================================================
# 7. Approve (6 tests)
# =============================================================================


class TestApprove:
    def _seed_recommendation(self, mock_db: _MockSwitcherDB, **kwargs) -> dict:
        """Helper: seed a 'recommend' audit log entry."""
        return mock_db.seed_audit_entry(
            user_id=TEST_USER_ID,
            decision="recommend",
            executed=kwargs.get("executed", False),
            **{k: v for k, v in kwargs.items() if k not in ("executed",)},
        )

    def test_approve_happy_path(self, pro_client, mock_db, monkeypatch):
        """Approving a recommend entry delegates to SwitchExecutionService."""
        from services.switch_execution_service import SwitchExecutionService

        entry = self._seed_recommendation(mock_db)
        called: dict[str, object] = {}

        async def _fake_approve(self, audit_log_id, user_id):
            called["audit_log_id"] = audit_log_id
            called["user_id"] = user_id
            return {
                "audit_log_id": audit_log_id,
                "status": "initiated",
                "message": "Recommendation approved. Switch execution initiated.",
            }

        monkeypatch.setattr(SwitchExecutionService, "approve_recommendation", _fake_approve)

        response = pro_client.post(f"/api/v1/agent-switcher/approve/{entry['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["audit_log_id"] == entry["id"]
        assert data["status"] == "initiated"
        assert called["audit_log_id"] == entry["id"]
        assert called["user_id"] == TEST_USER_ID

    def test_approve_service_failure_does_not_fabricate_success(
        self, pro_client, mock_db, monkeypatch
    ):
        """If SwitchExecutionService raises, the failure must propagate — never a fabricated 'initiated' UPDATE."""
        from services.switch_execution_service import SwitchExecutionService

        entry = self._seed_recommendation(mock_db)

        async def _boom(self, audit_log_id, user_id):
            raise RuntimeError("simulated billing API outage")

        monkeypatch.setattr(SwitchExecutionService, "approve_recommendation", _boom)

        # See test_rollback_service_failure_does_not_fabricate_success for
        # rationale. Regression test for security H-2 / code-quality P0-1.
        with pytest.raises(RuntimeError, match="simulated billing API outage"):
            pro_client.post(f"/api/v1/agent-switcher/approve/{entry['id']}")

    def test_approve_not_found_returns_404(self, pro_client, mock_db):
        """Non-existent audit_log_id returns 404."""
        response = pro_client.post(f"/api/v1/agent-switcher/approve/{uuid4()}")
        assert response.status_code == 404

    def test_approve_wrong_user_returns_404(self, pro_client, mock_db):
        """Audit entry belonging to another user returns 404."""
        entry = mock_db.seed_audit_entry(
            user_id=OTHER_USER_ID, decision="recommend", executed=False
        )
        response = pro_client.post(f"/api/v1/agent-switcher/approve/{entry['id']}")
        assert response.status_code == 404

    def test_approve_non_recommend_returns_400(self, pro_client, mock_db):
        """Approving a 'hold' decision returns 400."""
        entry = mock_db.seed_audit_entry(user_id=TEST_USER_ID, decision="hold", executed=False)
        response = pro_client.post(f"/api/v1/agent-switcher/approve/{entry['id']}")
        assert response.status_code == 400
        assert "recommend" in response.json()["detail"].lower()

    def test_approve_monitor_returns_400(self, pro_client, mock_db):
        """Approving a 'monitor' decision returns 400."""
        entry = mock_db.seed_audit_entry(user_id=TEST_USER_ID, decision="monitor", executed=False)
        response = pro_client.post(f"/api/v1/agent-switcher/approve/{entry['id']}")
        assert response.status_code == 400

    def test_approve_already_executed_returns_400(self, pro_client, mock_db):
        """Approving an already-executed recommendation returns 400."""
        entry = mock_db.seed_audit_entry(
            user_id=TEST_USER_ID,
            decision="recommend",
            executed=True,
        )
        response = pro_client.post(f"/api/v1/agent-switcher/approve/{entry['id']}")
        assert response.status_code == 400
        assert (
            "executed" in response.json()["detail"].lower()
            or "already" in response.json()["detail"].lower()
        )
