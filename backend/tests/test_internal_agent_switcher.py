"""
Tests for the Internal Agent-Switcher API endpoints.

Covers:
- POST /internal/agent-switcher/scan             — trigger decision engine for enrolled users
- POST /internal/agent-switcher/cleanup-meter-data — drop/create meter_readings partitions

Note: internal router uses lazy imports (inside endpoint functions), so patches
target the service modules directly rather than api.v1.internal.
"""

from datetime import UTC, datetime
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

    def test_sync_plans_endpoint_removed(self, auth_client):
        """The EnergyBot plan-sync endpoint no longer exists."""
        response = auth_client.post(f"{BASE_URL}/sync-plans")
        assert response.status_code == 404

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
            "region": "us_ct",
        }[key]
        return row

    @pytest.fixture(autouse=True)
    def _stub_context_builder(self):
        """These tests mock the engine; stub the DB-backed context builder too."""
        from services.switch_decision_engine import UserContext

        async def _build(db, user_id, **kwargs):
            return UserContext(user_id=user_id, tier=kwargs.get("tier") or "free")

        with patch(
            "services.switch_context_builder.build_user_context", side_effect=_build
        ) as stub:
            yield stub

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
            "users_without_plan_data": 0,
            "users_without_market_data": 0,
            "users_without_usage_data": 0,
            "users_with_estimates_only": 0,
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
        # A (future) real executor reports executed=True.
        mock_exec.execute_switch = AsyncMock(
            return_value={
                "execution_id": "exec-1",
                "status": "initiated",
                "enrollment_id": "enr-1",
                "executed": True,
            }
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
        # The scan's own audit row is reused rather than duplicated.
        kwargs = mock_exec.execute_switch.await_args.kwargs
        assert kwargs["audit_log_id"]
        assert kwargs["trigger_type"] == "market_scan"

    @patch("services.switch_decision_engine.SwitchDecisionEngine")
    def test_scan_advisory_switch_is_counted_as_recommendation(
        self, mock_engine_cls, auth_client, mock_db
    ):
        """Advisory-only: a 'switch' decision must never be reported as a switch.

        Uses the real SwitchExecutionService, whose only executor is advisory.
        """
        from decimal import Decimal

        from services.switch_decision_engine import PlanDetails, SwitchDecision

        row = self._make_settings_row(subscription_tier="business")
        user_result = MagicMock()
        user_result.mappings.return_value.all.return_value = [row]

        async def _execute(statement, params=None):
            sql = str(statement)
            result = MagicMock()
            if "FROM user_agent_settings uas" in sql:
                return user_result
            if "WHERE idempotency_key" in sql:
                result.mappings.return_value.first.return_value = None
            return result

        mock_db.execute = AsyncMock(side_effect=_execute)
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()

        mock_engine = MagicMock()
        mock_engine.evaluate = AsyncMock(
            return_value=SwitchDecision(
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
        )
        mock_engine_cls.return_value = mock_engine

        response = auth_client.post(f"{BASE_URL}/scan")

        assert response.status_code == 200
        data = response.json()
        assert data["switches_initiated"] == 0
        assert data["recommendations_sent"] == 1
        statuses = [
            c[0][1]["status"]
            for c in mock_db.execute.call_args_list
            if "UPDATE switch_executions" in str(c[0][0])
        ]
        assert statuses == ["advisory_only"]

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
# POST /internal/agent-switcher/scan — real context builder + real engine
# =============================================================================


class TestAgentSwitcherScanEndToEnd:
    """Scan with the real builder and engine; only the DB and offers are faked."""

    USER_ID = "11111111-1111-1111-1111-111111111111"
    PLAN_ID = "22222222-2222-2222-2222-222222222222"

    def _settings_row(self, tier: str = "pro") -> dict:
        return {
            "user_id": self.USER_ID,
            "enabled": True,
            "loa_signed_at": datetime(2026, 1, 1, tzinfo=UTC),
            "loa_revoked_at": None,
            "savings_threshold_pct": 10.0,
            "savings_threshold_min": 10.0,
            "cooldown_days": 5,
            "paused_until": None,
            "subscription_tier": tier,
            "region": "us_ct",
        }

    def _wire_db(self, mock_db, *, plan: dict | None, usage: dict | None, rows=None):
        def _result(*, first=None, all_=None):
            result = MagicMock()
            result.mappings.return_value.first.return_value = first
            result.mappings.return_value.all.return_value = all_ or []
            return result

        async def _execute(statement, params=None):
            sql = str(statement)
            if "FROM user_agent_settings uas" in sql:
                return _result(all_=rows if rows is not None else [self._settings_row()])
            if "FROM public.user_plans" in sql:
                return _result(first=plan)
            if "FROM public.meter_readings" in sql:
                return _result(first=usage)
            if "FROM public.switch_executions" in sql:
                return _result(all_=[])
            return MagicMock()

        mock_db.execute = AsyncMock(side_effect=_execute)
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()

    def _plan(self) -> dict:
        return {
            "id": self.PLAN_ID,
            "plan_name": "Standard Offer",
            "provider_name": "Incumbent Utility",
            "rate_kwh": "0.20",
            "fixed_charge": "0",
            "term_months": None,
            "etf_amount": "0",
            "contract_end": None,
        }

    @staticmethod
    def _usage() -> dict:
        # 60 days of hourly Arcadia data, 2000 kWh -> ~1014 kWh/month.
        return {
            "source": "arcadia",
            "interval_minutes": 60,
            "total_kwh": "2000",
            "first_reading": datetime(2026, 9, 1, tzinfo=UTC),
            "last_reading": datetime(2026, 10, 31, tzinfo=UTC),
        }

    @staticmethod
    def _offer_repo(offers: dict):
        repo = MagicMock()
        repo.cheapest_available_by_supplier = AsyncMock(return_value=offers)
        return MagicMock(return_value=repo)

    def _audit_params(self, mock_db) -> dict:
        calls = [
            c
            for c in mock_db.execute.call_args_list
            if "INSERT INTO switch_audit_log" in str(c[0][0])
        ]
        assert len(calls) == 1
        return calls[0][0][1]

    def test_current_plan_and_cheaper_offer_yields_recommendation(self, auth_client, mock_db):
        """Fails on the old code, which never loaded a plan or offers (always hold)."""
        from models.supplier_offer import SupplierOffer

        self._wire_db(mock_db, plan=self._plan(), usage=self._usage())
        offers = {
            "sup-1": SupplierOffer(
                supplier_name="Cheaper Co",
                supplier_id="sup-1",
                rate_per_kwh=0.12,
                source="ct_rate_board",
                source_ref="offer-123",
                region="us_ct",
            )
        }

        with patch(
            "services.switch_context_builder.SupplierOfferRepository", self._offer_repo(offers)
        ):
            response = auth_client.post(f"{BASE_URL}/scan")

        assert response.status_code == 200
        data = response.json()
        assert data["scanned"] == 1
        assert data["recommendations_sent"] == 1
        assert data["holds"] == 0
        assert data["switches_initiated"] == 0
        assert data["users_without_plan_data"] == 0
        assert data["users_without_market_data"] == 0
        assert data["users_without_usage_data"] == 0
        assert data["users_with_estimates_only"] == 0

        params = self._audit_params(mock_db)
        assert params["decision"] == "recommend"
        assert params["current_plan_id"] == self.PLAN_ID
        assert params["tier"] == "pro"
        assert params["savings_monthly"] > 10
        assert params["data_source"] == "arcadia_60min"
        assert "Proposed: Cheaper Co (fixed) at $0.12/kWh." in params["reason"]
        assert "estimate" not in params["reason"]

    def test_estimates_only_is_a_hold_naming_no_supplier(self, auth_client, mock_db):
        """Estimates only: hold, counted separately, no supplier or plan named.

        Fails on the old code, which sent a recommendation naming the supplier.
        """
        from models.supplier_offer import SupplierOffer

        self._wire_db(mock_db, plan=self._plan(), usage=self._usage())
        offers = {
            "sup-1": SupplierOffer(
                supplier_name="Some Supplier",
                supplier_id="sup-1",
                rate_per_kwh=0.12,
                source="regional_estimate",
                is_estimate=True,
                region="us_ct",
            )
        }

        with patch(
            "services.switch_context_builder.SupplierOfferRepository", self._offer_repo(offers)
        ):
            response = auth_client.post(f"{BASE_URL}/scan")

        data = response.json()
        assert data["recommendations_sent"] == 0
        assert data["switches_initiated"] == 0
        assert data["holds"] == 1
        assert data["users_with_estimates_only"] == 1
        params = self._audit_params(mock_db)
        assert params["decision"] == "hold"
        assert params["data_source"] == "arcadia_60min+market_estimate"
        assert "Only estimated regional rates are available" in params["reason"]
        assert "Estimated potential saving versus the regional estimate" in params["reason"]
        assert "Some Supplier" not in params["reason"]
        assert "Proposed:" not in params["reason"]
        # The engine's saving is still reported, as an estimate.
        assert params["savings_monthly"] > 10
        # Unknown data_source -> engine's lowest base confidence (0.40), not arcadia's 0.90.
        assert params["confidence_score"] <= 0.40

    def test_counts_missing_data_and_warns_when_no_user_has_a_plan(self, auth_client, mock_db):
        self._wire_db(mock_db, plan=None, usage=None)

        with (
            patch("services.switch_context_builder.SupplierOfferRepository", self._offer_repo({})),
            patch("api.v1.internal.agent_switcher.logger") as mock_logger,
        ):
            response = auth_client.post(f"{BASE_URL}/scan")

        data = response.json()
        assert data["scanned"] == 1
        assert data["holds"] == 1
        assert data["recommendations_sent"] == 0
        assert data["users_without_plan_data"] == 1
        assert data["users_without_market_data"] == 1
        assert data["users_without_usage_data"] == 1
        warning_events = [c[0][0] for c in mock_logger.warning.call_args_list]
        assert "agent_switcher_scan_no_plan_data_for_any_user" in warning_events
        assert self._audit_params(mock_db)["data_source"] == "none"

    def test_no_warning_when_a_user_has_plan_data(self, auth_client, mock_db):
        self._wire_db(mock_db, plan=self._plan(), usage=self._usage())

        with (
            patch("services.switch_context_builder.SupplierOfferRepository", self._offer_repo({})),
            patch("api.v1.internal.agent_switcher.logger") as mock_logger,
        ):
            response = auth_client.post(f"{BASE_URL}/scan")

        data = response.json()
        assert data["users_without_plan_data"] == 0
        assert data["users_without_market_data"] == 1
        assert mock_logger.warning.call_args_list == []


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
