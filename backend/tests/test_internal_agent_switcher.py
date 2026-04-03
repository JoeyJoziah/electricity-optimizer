"""
Tests for the Internal Agent-Switcher API endpoints.

Covers:
- POST /internal/agent-switcher/scan             — trigger decision engine for enrolled users
- POST /internal/agent-switcher/sync-plans       — refresh available-plans cache per zip
- POST /internal/agent-switcher/cleanup-meter-data — drop/create meter_readings partitions

Note: internal router uses lazy imports (inside endpoint functions), so patches
target the service modules directly rather than api.v1.internal.
"""

from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session, get_redis, verify_api_key

BASE_URL = "/api/v1/internal/agent-switcher"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock async database session."""
    return AsyncMock()


@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    return AsyncMock()


@pytest.fixture
def auth_client(mock_db, mock_redis_client):
    """TestClient with API key verified and mocked DB/Redis sessions."""
    from main import app

    app.dependency_overrides[verify_api_key] = lambda: True
    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis_client

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_redis, None)


@pytest.fixture
def unauth_client(mock_db, mock_redis_client):
    """TestClient without API key override (auth not bypassed)."""
    from main import app

    # Remove the verify_api_key override so real validation runs
    app.dependency_overrides.pop(verify_api_key, None)
    # Still mock DB/Redis to avoid real connection attempts
    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis_client

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_redis, None)


# =============================================================================
# Auth Tests (shared across all 3 endpoints)
# =============================================================================


class TestAgentSwitcherAuth:
    """Auth enforcement is shared across all 3 endpoints."""

    def test_scan_no_api_key_rejected(self, unauth_client):
        """POST /scan without X-API-Key must be rejected with 401."""
        response = unauth_client.post(f"{BASE_URL}/scan")
        assert response.status_code == 401

    def test_sync_plans_no_api_key_rejected(self, unauth_client):
        """POST /sync-plans without X-API-Key must be rejected with 401."""
        response = unauth_client.post(f"{BASE_URL}/sync-plans")
        assert response.status_code == 401

    def test_cleanup_no_api_key_rejected(self, unauth_client):
        """POST /cleanup-meter-data without X-API-Key must be rejected with 401."""
        response = unauth_client.post(f"{BASE_URL}/cleanup-meter-data")
        assert response.status_code == 401


# =============================================================================
# POST /internal/agent-switcher/scan
# =============================================================================


class TestAgentSwitcherScan:
    """Tests for POST /api/v1/internal/agent-switcher/scan."""

    # ------------------------------------------------------------------
    # Helper: build a fake row for user_agent_settings JOIN users
    # ------------------------------------------------------------------

    @staticmethod
    def _make_settings_row(
        user_id: str = "user-uuid-1",
        subscription_tier: str = "pro",
        savings_threshold_pct: float = 10.0,
        savings_threshold_min: float = 10.0,
        cooldown_days: int = 5,
        paused_until=None,
    ):
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "user_id": user_id,
            "enabled": True,
            "loa_signed_at": "2026-01-01T00:00:00",
            "loa_revoked_at": None,
            "savings_threshold_pct": savings_threshold_pct,
            "savings_threshold_min": savings_threshold_min,
            "cooldown_days": cooldown_days,
            "paused_until": paused_until,
            "subscription_tier": subscription_tier,
        }[key]
        return row

    # ------------------------------------------------------------------
    # No enrolled users → returns all zeros
    # ------------------------------------------------------------------

    def test_scan_no_enrolled_users_returns_zeros(self, auth_client, mock_db):
        """When no users have enabled=True with active LOA, all counts are 0."""
        # Simulate the DB query returning an empty result set
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        response = auth_client.post(f"{BASE_URL}/scan")

        assert response.status_code == 200
        data = response.json()
        assert data == {
            "scanned": 0,
            "switches_initiated": 0,
            "recommendations_sent": 0,
            "holds": 0,
        }

    # ------------------------------------------------------------------
    # One user — decision engine evaluates but produces no switch
    # ------------------------------------------------------------------

    @patch("services.switch_execution_service.SwitchExecutionService")
    @patch("services.switch_decision_engine.SwitchDecisionEngine")
    def test_scan_one_user_evaluate_called(
        self, mock_engine_cls, mock_exec_cls, auth_client, mock_db
    ):
        """One enrolled user triggers evaluate(); hold decision = 0 switches."""
        from decimal import Decimal

        from services.switch_decision_engine import SwitchDecision

        # DB row for the user query
        row = self._make_settings_row()
        user_result = MagicMock()
        user_result.mappings.return_value.all.return_value = [row]

        # Audit log insert returns a plain mock
        audit_result = MagicMock()

        mock_db.execute = AsyncMock(side_effect=[user_result, audit_result])
        mock_db.commit = AsyncMock()

        # Decision engine returns hold
        hold_decision = SwitchDecision(
            action="hold",
            reason="No better plan found.",
            projected_savings_monthly=Decimal("0"),
            projected_savings_annual=Decimal("0"),
            confidence=Decimal("0.5"),
            data_source="manual",
        )
        mock_engine = MagicMock()
        mock_engine.evaluate = AsyncMock(return_value=hold_decision)
        mock_engine_cls.return_value = mock_engine

        mock_exec = MagicMock()
        mock_exec_cls.return_value = mock_exec

        response = auth_client.post(f"{BASE_URL}/scan")

        assert response.status_code == 200
        data = response.json()
        assert data["scanned"] == 1
        assert data["switches_initiated"] == 0
        assert data["holds"] == 1
        mock_engine.evaluate.assert_awaited_once()

    # ------------------------------------------------------------------
    # Switch decision → execute_switch() is called
    # ------------------------------------------------------------------

    @patch("services.switch_execution_service.SwitchExecutionService")
    @patch("services.switch_decision_engine.SwitchDecisionEngine")
    def test_scan_switch_decision_triggers_execution(
        self, mock_engine_cls, mock_exec_cls, auth_client, mock_db
    ):
        """When decision.action == 'switch', execute_switch() must be called."""
        from decimal import Decimal

        from services.switch_decision_engine import PlanDetails, SwitchDecision

        row = self._make_settings_row(subscription_tier="business")
        user_result = MagicMock()
        user_result.mappings.return_value.all.return_value = [row]
        audit_result = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[user_result, audit_result])
        mock_db.commit = AsyncMock()

        switch_decision = SwitchDecision(
            action="switch",
            reason="Found a better plan saving ~$15.00/month.",
            proposed_plan=PlanDetails(
                plan_id="plan-abc",
                plan_name="Best Value 12M",
                provider_name="AcmePower",
                rate_kwh=Decimal("0.08"),
            ),
            projected_savings_monthly=Decimal("15.00"),
            projected_savings_annual=Decimal("180.00"),
            confidence=Decimal("0.90"),
            data_source="utilityapi_60min",
        )

        mock_engine = MagicMock()
        mock_engine.evaluate = AsyncMock(return_value=switch_decision)
        mock_engine_cls.return_value = mock_engine

        mock_exec = MagicMock()
        mock_exec.execute_switch = AsyncMock(
            return_value={"execution_id": "exec-1", "status": "initiated", "enrollment_id": "enr-1"}
        )
        mock_exec_cls.return_value = mock_exec

        response = auth_client.post(f"{BASE_URL}/scan")

        assert response.status_code == 200
        data = response.json()
        assert data["scanned"] == 1
        assert data["switches_initiated"] == 1
        assert data["recommendations_sent"] == 0
        assert data["holds"] == 0
        mock_exec.execute_switch.assert_awaited_once()

    # ------------------------------------------------------------------
    # Recommend decision → only audit logged, no execution
    # ------------------------------------------------------------------

    @patch("services.switch_execution_service.SwitchExecutionService")
    @patch("services.switch_decision_engine.SwitchDecisionEngine")
    def test_scan_recommend_decision_no_execution(
        self, mock_engine_cls, mock_exec_cls, auth_client, mock_db
    ):
        """When decision.action == 'recommend', execute_switch() must NOT be called."""
        from decimal import Decimal

        from services.switch_decision_engine import PlanDetails, SwitchDecision

        row = self._make_settings_row(subscription_tier="pro")
        user_result = MagicMock()
        user_result.mappings.return_value.all.return_value = [row]
        audit_result = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[user_result, audit_result])
        mock_db.commit = AsyncMock()

        recommend_decision = SwitchDecision(
            action="recommend",
            reason="Found a better plan saving ~$12.00/month.",
            proposed_plan=PlanDetails(
                plan_id="plan-xyz",
                plan_name="EcoRate 6M",
                provider_name="GreenEnergy",
                rate_kwh=Decimal("0.09"),
            ),
            projected_savings_monthly=Decimal("12.00"),
            projected_savings_annual=Decimal("144.00"),
            confidence=Decimal("0.80"),
            data_source="bills",
        )

        mock_engine = MagicMock()
        mock_engine.evaluate = AsyncMock(return_value=recommend_decision)
        mock_engine_cls.return_value = mock_engine

        mock_exec = MagicMock()
        mock_exec.execute_switch = AsyncMock()
        mock_exec_cls.return_value = mock_exec

        response = auth_client.post(f"{BASE_URL}/scan")

        assert response.status_code == 200
        data = response.json()
        assert data["scanned"] == 1
        assert data["switches_initiated"] == 0
        assert data["recommendations_sent"] == 1
        assert data["holds"] == 0
        mock_exec.execute_switch.assert_not_awaited()

    # ------------------------------------------------------------------
    # Error on one user continues to the next
    # ------------------------------------------------------------------

    @patch("services.switch_execution_service.SwitchExecutionService")
    @patch("services.switch_decision_engine.SwitchDecisionEngine")
    def test_scan_evaluation_error_continues_to_next_user(
        self, mock_engine_cls, mock_exec_cls, auth_client, mock_db
    ):
        """An exception during evaluate() for user-1 must not abort user-2."""
        from decimal import Decimal

        from services.switch_decision_engine import SwitchDecision

        row1 = self._make_settings_row(user_id="user-bad")
        row2 = self._make_settings_row(user_id="user-good")

        user_result = MagicMock()
        user_result.mappings.return_value.all.return_value = [row1, row2]
        audit_result = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[user_result, audit_result])
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()

        hold_decision = SwitchDecision(
            action="hold",
            reason="Paused.",
            projected_savings_monthly=Decimal("0"),
            projected_savings_annual=Decimal("0"),
            confidence=Decimal("0.4"),
            data_source="manual",
        )

        call_count = 0

        async def evaluate_side_effect(ctx):
            nonlocal call_count
            call_count += 1
            if ctx.user_id == "user-bad":
                raise RuntimeError("DB connection lost")
            return hold_decision

        mock_engine = MagicMock()
        mock_engine.evaluate = AsyncMock(side_effect=evaluate_side_effect)
        mock_engine_cls.return_value = mock_engine

        mock_exec_cls.return_value = MagicMock()

        response = auth_client.post(f"{BASE_URL}/scan")

        assert response.status_code == 200
        data = response.json()
        # Both users counted: user-bad errored (counts as hold) + user-good evaluated
        assert data["scanned"] == 2
        # user-bad error → hold; user-good hold decision → hold
        assert data["holds"] == 2
        assert data["switches_initiated"] == 0


# =============================================================================
# POST /internal/agent-switcher/sync-plans
# =============================================================================


class TestAgentSwitcherSyncPlans:
    """Tests for POST /api/v1/internal/agent-switcher/sync-plans."""

    # ------------------------------------------------------------------
    # No active zip codes → returns zeros
    # ------------------------------------------------------------------

    def test_sync_plans_no_zip_codes_returns_zeros(self, auth_client, mock_db):
        """When no active enrolled users have a zip code, return zeros."""
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        response = auth_client.post(f"{BASE_URL}/sync-plans")

        assert response.status_code == 200
        data = response.json()
        assert data == {"zip_codes_synced": 0, "plans_fetched": 0}

    # ------------------------------------------------------------------
    # One zip code — plans fetched successfully
    # ------------------------------------------------------------------

    @patch("services.energybot_service.EnergyBotService")
    def test_sync_plans_one_zip_fetched(self, mock_svc_cls, auth_client, mock_db):
        """A single zip returns 2 plans — summary reflects that."""
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [("10001",)]
        mock_db.execute = AsyncMock(return_value=result_mock)

        mock_svc = MagicMock()
        mock_svc.fetch_plans = AsyncMock(
            return_value=[
                {"id": "plan-1", "plan_name": "Budget 12M", "rate_kwh": 0.09},
                {"id": "plan-2", "plan_name": "Green 6M", "rate_kwh": 0.10},
            ]
        )
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/sync-plans")

        assert response.status_code == 200
        data = response.json()
        assert data["zip_codes_synced"] == 1
        assert data["plans_fetched"] == 2
        mock_svc.fetch_plans.assert_awaited_once_with("10001")

    # ------------------------------------------------------------------
    # Multiple zip codes all succeed
    # ------------------------------------------------------------------

    @patch("services.energybot_service.EnergyBotService")
    def test_sync_plans_multiple_zips(self, mock_svc_cls, auth_client, mock_db):
        """Three zip codes each fetch 1 plan — totals = 3 synced, 3 fetched."""
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [("10001",), ("77002",), ("60601",)]
        mock_db.execute = AsyncMock(return_value=result_mock)

        mock_svc = MagicMock()
        mock_svc.fetch_plans = AsyncMock(
            return_value=[{"id": "p1", "plan_name": "Plan A", "rate_kwh": 0.08}]
        )
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/sync-plans")

        assert response.status_code == 200
        data = response.json()
        assert data["zip_codes_synced"] == 3
        assert data["plans_fetched"] == 3
        assert mock_svc.fetch_plans.await_count == 3

    # ------------------------------------------------------------------
    # Fetch error on one zip — others continue
    # ------------------------------------------------------------------

    @patch("services.energybot_service.EnergyBotService")
    def test_sync_plans_fetch_error_continues(self, mock_svc_cls, auth_client, mock_db):
        """An API error for one zip must not abort the others."""
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [("10001",), ("bad-zip",)]
        mock_db.execute = AsyncMock(return_value=result_mock)

        call_count = 0

        async def fetch_side_effect(zip_code):
            nonlocal call_count
            call_count += 1
            if zip_code == "bad-zip":
                raise RuntimeError("EnergyBot API error")
            return [{"id": "p1", "plan_name": "Plan A", "rate_kwh": 0.08}]

        mock_svc = MagicMock()
        mock_svc.fetch_plans = AsyncMock(side_effect=fetch_side_effect)
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/sync-plans")

        assert response.status_code == 200
        data = response.json()
        # Only "10001" succeeded
        assert data["zip_codes_synced"] == 1
        assert data["plans_fetched"] == 1


# =============================================================================
# POST /internal/agent-switcher/cleanup-meter-data
# =============================================================================


class TestAgentSwitcherCleanupMeterData:
    """Tests for POST /api/v1/internal/agent-switcher/cleanup-meter-data."""

    # ------------------------------------------------------------------
    # Old partitions are identified and dropped
    # ------------------------------------------------------------------

    def test_cleanup_drops_old_partitions(self, auth_client, mock_db):
        """Partitions older than 90 days must be dropped."""
        from datetime import datetime, timedelta

        # Create a partition name for 6 months ago — definitely older than 90 days
        old_date = datetime.now(UTC) - timedelta(days=180)
        old_partition = f"meter_readings_{old_date.year:04d}_{old_date.month:02d}"

        # pg_inherits query returns the old partition
        discover_result = MagicMock()
        discover_result.fetchall.return_value = [(old_partition,)]

        # DROP and subsequent CREATE/GRANT calls all succeed
        generic_result = MagicMock()

        mock_db.execute = AsyncMock(side_effect=[discover_result] + [generic_result] * 10)
        mock_db.commit = AsyncMock()

        response = auth_client.post(f"{BASE_URL}/cleanup-meter-data")

        assert response.status_code == 200
        data = response.json()
        assert old_partition in data["dropped"]

    # ------------------------------------------------------------------
    # New partitions are created for current + 3 months ahead
    # ------------------------------------------------------------------

    def test_cleanup_creates_future_partitions(self, auth_client, mock_db):
        """Partitions for current month and next 3 months must be created."""
        from datetime import datetime

        now = datetime.now(UTC)

        # pg_inherits returns empty — no existing partitions
        discover_result = MagicMock()
        discover_result.fetchall.return_value = []

        generic_result = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[discover_result] + [generic_result] * 20)
        mock_db.commit = AsyncMock()

        response = auth_client.post(f"{BASE_URL}/cleanup-meter-data")

        assert response.status_code == 200
        data = response.json()
        # Should have created 4 partitions (current + 3 months ahead)
        assert len(data["created"]) == 4
        # Current month must be in the created list
        current_partition = f"meter_readings_{now.year:04d}_{now.month:02d}"
        assert current_partition in data["created"]

    # ------------------------------------------------------------------
    # No old partitions — nothing dropped
    # ------------------------------------------------------------------

    def test_cleanup_no_old_partitions_nothing_dropped(self, auth_client, mock_db):
        """When no partitions are old enough to drop, dropped list is empty."""
        from datetime import datetime

        now = datetime.now(UTC)

        # Return only a recent partition (current month, well under 90 days)
        current_partition = f"meter_readings_{now.year:04d}_{now.month:02d}"

        discover_result = MagicMock()
        discover_result.fetchall.return_value = [(current_partition,)]

        generic_result = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[discover_result] + [generic_result] * 20)
        mock_db.commit = AsyncMock()

        response = auth_client.post(f"{BASE_URL}/cleanup-meter-data")

        assert response.status_code == 200
        data = response.json()
        # Nothing should be dropped
        assert data["dropped"] == []
        # Current partition already exists — only future ones created
        for partition in data["created"]:
            assert partition != current_partition
