"""
Tests for SwitchExecutionService

30 tests covering execute_switch, check_pending_switches,
rollback_switch, and approve_recommendation.

All executor calls are mocked — no real API calls are made.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.switch_decision_engine import PlanDetails, SwitchDecision
from services.switch_execution_service import (
    PENDING_STATUSES,
    SwitchExecutionService,
    build_idempotency_key,
)
from services.switch_executor import (
    AdvisoryOnlyFallback,
    EnrollmentResult,
    EnrollmentStatus,
    SwitchExecutor,
)

# =============================================================================
# Helpers / Factories
# =============================================================================


def _make_db(
    *,
    existing_execution: dict | None = None,
    insert_conflicts: bool = False,
    audit_row: dict | None = None,
    claim_succeeds: bool = True,
) -> AsyncMock:
    """Build a mock AsyncSession that routes on the SQL text.

    - lookup by idempotency key  -> ``existing_execution`` (None = no prior row)
    - INSERT INTO switch_executions -> RETURNING row, or nothing on conflict
    - SELECT ... FROM switch_audit_log -> ``audit_row``
    """
    db = AsyncMock()

    async def _execute(statement, params=None):
        sql = str(statement)
        if "WHERE idempotency_key" in sql:
            return _make_mapping_result(existing_execution)
        if "INSERT INTO switch_executions" in sql:
            result = MagicMock()
            result.first.return_value = None if insert_conflicts else ("exec-id",)
            return result
        if "FROM switch_audit_log" in sql and "SELECT" in sql:
            return _make_mapping_result(audit_row)
        if "SET status = 'initiating'" in sql:
            # Guarded claim of a failed row for a retry.
            result = MagicMock()
            result.first.return_value = ("exec-id",) if claim_succeeds else None
            return result
        return MagicMock()

    db.execute = AsyncMock(side_effect=_execute)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _sql_calls(db: AsyncMock, fragment: str) -> list:
    """All db.execute calls whose SQL contains ``fragment``."""
    return [c for c in db.execute.call_args_list if fragment in str(c[0][0])]


def _make_executor(
    *,
    available: bool = True,
    enrollment_id: str = "enr_123",
    enrollment_status: str = "initiated",
    cancel_result: bool = True,
    executor_status: str = "active",
) -> AsyncMock:
    """Build a mock SwitchExecutor satisfying the required interface."""
    mock = AsyncMock(spec=SwitchExecutor)
    mock.check_plan_available = AsyncMock(return_value=available)
    mock.execute_enrollment = AsyncMock(
        return_value=EnrollmentResult(
            success=True,
            enrollment_id=enrollment_id,
            status=enrollment_status,
            provider="test_provider",
        )
    )
    mock.check_enrollment_status = AsyncMock(
        return_value=EnrollmentStatus(
            enrollment_id=enrollment_id,
            status=executor_status,
        )
    )
    mock.cancel_enrollment = AsyncMock(return_value=cancel_result)
    return mock


def _make_decision(
    *,
    action: str = "switch",
    plan_id: str = "plan_abc",
    plan_name: str = "Green Rate",
    provider_name: str = "EcoEnergy",
    rate_kwh: str = "0.10",
    savings_monthly: str = "25.00",
    savings_annual: str = "300.00",
    confidence: str = "0.85",
    reason: str = "Found a better plan",
    data_source: str = "arcadia_15min",
) -> SwitchDecision:
    """Build a SwitchDecision suitable for tests."""
    plan = PlanDetails(
        plan_id=plan_id,
        plan_name=plan_name,
        provider_name=provider_name,
        rate_kwh=Decimal(rate_kwh),
    )
    return SwitchDecision(
        action=action,
        reason=reason,
        proposed_plan=plan,
        projected_savings_monthly=Decimal(savings_monthly),
        projected_savings_annual=Decimal(savings_annual),
        confidence=Decimal(confidence),
        data_source=data_source,
    )


def _make_mapping_result(row_dict: dict | None) -> MagicMock:
    """Build a mock SQLAlchemy result whose .mappings().first() returns row_dict."""
    mock_result = MagicMock()
    mock_mappings = MagicMock()
    mock_mappings.first.return_value = row_dict
    mock_mappings.all.return_value = [row_dict] if row_dict else []
    mock_result.mappings.return_value = mock_mappings
    return mock_result


def _make_list_result(rows: list[dict]) -> MagicMock:
    """Build a mock SQLAlchemy result whose .mappings().all() returns rows."""
    mock_result = MagicMock()
    mock_mappings = MagicMock()
    mock_mappings.all.return_value = rows
    mock_mappings.first.return_value = rows[0] if rows else None
    mock_result.mappings.return_value = mock_mappings
    return mock_result


def _make_service(db: AsyncMock | None = None) -> SwitchExecutionService:
    return SwitchExecutionService(db or _make_db())


# =============================================================================
# execute_switch — 8 tests
# =============================================================================


class TestExecuteSwitch:
    """Tests for SwitchExecutionService.execute_switch."""

    @pytest.mark.asyncio
    async def test_01_happy_path_returns_execution_dict(self):
        """Happy path returns execution_id, status, enrollment_id."""
        db = _make_db()
        svc = _make_service(db)
        mock_executor = _make_executor()
        decision = _make_decision()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            result = await svc.execute_switch("user_1", decision, state_code="TX")

        assert "execution_id" in result
        assert result["status"] == "initiated"
        assert result["enrollment_id"] == "enr_123"

    @pytest.mark.asyncio
    async def test_02_plan_unavailable_sets_status_failed(self):
        """When plan is not available, execution status is set to 'failed'."""
        db = _make_db()
        svc = _make_service(db)
        mock_executor = _make_executor(available=False)
        decision = _make_decision()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            with pytest.raises(RuntimeError, match="not available"):
                await svc.execute_switch("user_1", decision)

        # Verify the status update to 'failed' was attempted — the UPDATE call
        # passes a dict with a 'reason' key containing the error message.
        execute_calls = db.execute.call_args_list
        assert len(execute_calls) >= 3
        # The last execute call's params dict contains 'reason' (failure_reason)
        last_params = execute_calls[-1][0][1]  # positional arg[1] of the last call
        assert "reason" in last_params or "not available" in str(last_params)

    @pytest.mark.asyncio
    async def test_03_enrollment_api_error_sets_failure_reason(self):
        """When execute_enrollment raises, failure_reason is stored."""
        db = _make_db()
        svc = _make_service(db)
        mock_executor = _make_executor()
        mock_executor.execute_enrollment = AsyncMock(side_effect=RuntimeError("Provider timeout"))
        decision = _make_decision()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            with pytest.raises(RuntimeError, match="Provider timeout"):
                await svc.execute_switch("user_1", decision)

        # The UPDATE to 'failed' passes params dict containing 'reason'
        # with the exception message.
        execute_calls = db.execute.call_args_list
        assert len(execute_calls) >= 3
        last_params = execute_calls[-1][0][1]
        assert "Provider timeout" in str(last_params)

    @pytest.mark.asyncio
    async def test_04_advisory_only_executor_never_reports_a_switch(self):
        """AdvisoryOnlyFallback ends in the terminal 'advisory_only' status.

        It must not look initiated/submitted/pending: nothing was enrolled.
        """
        db = _make_db()
        svc = _make_service(db)
        advisory_executor = AdvisoryOnlyFallback()
        decision = _make_decision()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=advisory_executor,
        ):
            result = await svc.execute_switch("user_1", decision)

        assert result["status"] == "advisory_only"
        assert result["status"] not in PENDING_STATUSES
        assert result["executed"] is False
        assert result["enrollment_id"] is None
        assert "has not switched" in result["message"]
        update = _sql_calls(db, "UPDATE switch_executions")[-1]
        assert update[0][1]["status"] == "advisory_only"
        insert = _sql_calls(db, "INSERT INTO switch_executions")[0]
        assert insert[0][1]["executor_type"] == "advisory_only"

    @pytest.mark.asyncio
    async def test_05_idempotency_key_is_generated(self):
        """An idempotency key UUID is inserted into the DB."""
        db = _make_db()
        svc = _make_service(db)
        mock_executor = _make_executor()
        decision = _make_decision()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            await svc.execute_switch("user_1", decision)

        # The execution INSERT call passes a params dict that contains
        # 'idempotency_key' as a key.
        execute_calls = db.execute.call_args_list
        all_param_keys = set()
        for call in execute_calls:
            if len(call[0]) > 1 and isinstance(call[0][1], dict):
                all_param_keys.update(call[0][1].keys())
        assert "idempotency_key" in all_param_keys

    @pytest.mark.asyncio
    async def test_06_audit_log_row_is_created(self):
        """An audit log INSERT is made before the execution INSERT."""
        db = _make_db()
        svc = _make_service(db)
        mock_executor = _make_executor()
        decision = _make_decision()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            await svc.execute_switch("user_1", decision)

        # The audit log INSERT params dict contains 'decision' key (not present
        # in the executions INSERT). At least 3 execute() calls are expected:
        # audit_log INSERT, executions INSERT, status UPDATE.
        execute_calls = db.execute.call_args_list
        assert len(execute_calls) >= 3
        audit_inserts = _sql_calls(db, "INSERT INTO switch_audit_log")
        assert len(audit_inserts) == 1
        params = audit_inserts[0][0][1]
        assert params["decision"] == "switch"
        # Columns that exist in migration 066 and are NOT NULL there.
        assert params["trigger_type"] == "manual"
        assert "tier" in params
        # The snapshot precedes the execution row that references it.
        order = [str(c[0][0]) for c in execute_calls]
        audit_idx = next(i for i, q in enumerate(order) if "INSERT INTO switch_audit_log" in q)
        exec_idx = next(i for i, q in enumerate(order) if "INSERT INTO switch_executions" in q)
        assert audit_idx < exec_idx

    @pytest.mark.asyncio
    async def test_07_db_commit_is_called(self):
        """db.commit() is called on a successful execution."""
        db = _make_db()
        svc = _make_service(db)
        mock_executor = _make_executor()
        decision = _make_decision()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            await svc.execute_switch("user_1", decision)

        assert db.commit.called

    @pytest.mark.asyncio
    async def test_08_db_rollback_on_error(self):
        """db.rollback() is called when an exception occurs."""
        db = _make_db()
        svc = _make_service(db)
        mock_executor = _make_executor()
        mock_executor.execute_enrollment = AsyncMock(side_effect=Exception("Unexpected error"))
        decision = _make_decision()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            with pytest.raises(Exception, match="Unexpected error"):
                await svc.execute_switch("user_1", decision)

        assert db.rollback.called


# =============================================================================
# check_pending_switches — 6 tests
# =============================================================================


class TestCheckPendingSwitches:
    """Tests for SwitchExecutionService.check_pending_switches."""

    @pytest.mark.asyncio
    async def test_09_no_pending_returns_empty_list(self):
        """No pending executions → empty list returned."""
        db = _make_db()
        svc = _make_service(db)
        db.execute = AsyncMock(return_value=_make_list_result([]))

        result = await svc.check_pending_switches("user_1")

        assert result == []

    @pytest.mark.asyncio
    async def test_10_pending_execution_updated_to_active(self):
        """Executor reports 'active' → DB row updated and new status returned."""
        db = _make_db()
        svc = _make_service(db)

        pending_row = {
            "id": "exec_1",
            "status": "initiated",
            "enrollment_id": "enr_abc",
            "plan_id": "plan_1",
            "plan_name": "Plan A",
            "provider_name": "Prov",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        db.execute = AsyncMock(return_value=_make_list_result([pending_row]))
        mock_executor = _make_executor(executor_status="active")

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            result = await svc.check_pending_switches("user_1")

        assert len(result) == 1
        assert result[0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_11_multiple_pending_mixed_statuses(self):
        """Multiple executions: each gets its status refreshed independently."""
        db = _make_db()
        svc = _make_service(db)

        rows = [
            {
                "id": "exec_1",
                "status": "initiated",
                "enrollment_id": "enr_1",
                "plan_id": "p1",
                "plan_name": "Plan 1",
                "provider_name": "P",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
            {
                "id": "exec_2",
                "status": "submitted",
                "enrollment_id": "enr_2",
                "plan_id": "p2",
                "plan_name": "Plan 2",
                "provider_name": "P",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        ]

        list_result = _make_list_result(rows)
        db.execute = AsyncMock(return_value=list_result)

        mock_executor = _make_executor(executor_status="accepted")

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            result = await svc.check_pending_switches("user_1")

        assert len(result) == 2
        for item in result:
            assert item["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_12_enrollment_check_error_leaves_status_unchanged(self):
        """When check_enrollment_status raises, row status stays as-is."""
        db = _make_db()
        svc = _make_service(db)

        pending_row = {
            "id": "exec_1",
            "status": "initiated",
            "enrollment_id": "enr_abc",
            "plan_id": "p1",
            "plan_name": "Plan",
            "provider_name": "P",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        db.execute = AsyncMock(return_value=_make_list_result([pending_row]))

        mock_executor = _make_executor()
        mock_executor.check_enrollment_status = AsyncMock(
            side_effect=RuntimeError("Executor unavailable")
        )

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            result = await svc.check_pending_switches("user_1")

        assert len(result) == 1
        assert result[0]["status"] == "initiated"

    @pytest.mark.asyncio
    async def test_13_no_enrollment_id_skips_status_check(self):
        """Row without enrollment_id is returned as-is without calling executor."""
        db = _make_db()
        svc = _make_service(db)

        pending_row = {
            "id": "exec_1",
            "status": "initiating",
            "enrollment_id": None,
            "plan_id": "p1",
            "plan_name": "Plan",
            "provider_name": "P",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        db.execute = AsyncMock(return_value=_make_list_result([pending_row]))
        mock_executor = _make_executor()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            result = await svc.check_pending_switches("user_1")

        mock_executor.check_enrollment_status.assert_not_called()
        assert result[0]["status"] == "initiating"

    @pytest.mark.asyncio
    async def test_14_returns_empty_list_when_no_rows(self):
        """Explicit empty DB result maps to empty list (no error)."""
        db = _make_db()
        svc = _make_service(db)
        db.execute = AsyncMock(return_value=_make_list_result([]))

        result = await svc.check_pending_switches("user_999")

        assert result == []
        assert isinstance(result, list)


# =============================================================================
# rollback_switch — 8 tests
# =============================================================================


class TestRollbackSwitch:
    """Tests for SwitchExecutionService.rollback_switch."""

    def _active_row(self, enacted_at: datetime | None = None) -> dict:
        return {
            "id": "exec_1",
            "user_id": "user_1",
            "status": "active",
            "enrollment_id": "enr_abc",
            "enacted_at": enacted_at or datetime.now(UTC) - timedelta(days=1),
        }

    @pytest.mark.asyncio
    async def test_15_happy_path_returns_rolled_back(self):
        """Active switch within window rolls back successfully."""
        db = _make_db()
        svc = _make_service(db)
        db.execute = AsyncMock(return_value=_make_mapping_result(self._active_row()))
        mock_executor = _make_executor()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            result = await svc.rollback_switch("exec_1", "user_1")

        assert result["status"] == "rolled_back"
        assert "rolled back" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_16_execution_not_found_raises_value_error(self):
        """Missing execution row raises ValueError."""
        db = _make_db()
        svc = _make_service(db)
        db.execute = AsyncMock(return_value=_make_mapping_result(None))

        with pytest.raises(ValueError, match="not found"):
            await svc.rollback_switch("exec_missing", "user_1")

    @pytest.mark.asyncio
    async def test_17_wrong_user_raises_value_error(self):
        """Execution belonging to different user raises ValueError."""
        db = _make_db()
        svc = _make_service(db)
        row = self._active_row()
        row["user_id"] = "other_user"
        db.execute = AsyncMock(return_value=_make_mapping_result(row))

        with pytest.raises(ValueError, match="does not belong"):
            await svc.rollback_switch("exec_1", "user_1")

    @pytest.mark.asyncio
    async def test_18_status_not_active_raises_value_error(self):
        """Non-active execution status raises ValueError."""
        db = _make_db()
        svc = _make_service(db)
        row = self._active_row()
        row["status"] = "initiated"
        db.execute = AsyncMock(return_value=_make_mapping_result(row))

        with pytest.raises(ValueError, match="initiated"):
            await svc.rollback_switch("exec_1", "user_1")

    @pytest.mark.asyncio
    async def test_19_enacted_over_30_days_ago_raises_value_error(self):
        """Switch enacted more than 30 days ago raises ValueError."""
        db = _make_db()
        svc = _make_service(db)
        old_enacted = datetime.now(UTC) - timedelta(days=31)
        db.execute = AsyncMock(
            return_value=_make_mapping_result(self._active_row(enacted_at=old_enacted))
        )

        with pytest.raises(ValueError, match="[Rr]ollback window expired"):
            await svc.rollback_switch("exec_1", "user_1")

    @pytest.mark.asyncio
    async def test_20_cancel_enrollment_fails_but_still_marks_rolled_back(self):
        """cancel_enrollment failure is logged but DB still marks rolled_back."""
        db = _make_db()
        svc = _make_service(db)
        db.execute = AsyncMock(return_value=_make_mapping_result(self._active_row()))
        mock_executor = _make_executor()
        mock_executor.cancel_enrollment = AsyncMock(side_effect=RuntimeError("Cancellation failed"))

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            result = await svc.rollback_switch("exec_1", "user_1")

        assert result["status"] == "rolled_back"

    @pytest.mark.asyncio
    async def test_21_enrollment_id_is_passed_to_cancel(self):
        """The enrollment_id from the DB row is forwarded to cancel_enrollment."""
        db = _make_db()
        svc = _make_service(db)
        row = self._active_row()
        row["enrollment_id"] = "enr_xyz_999"
        db.execute = AsyncMock(return_value=_make_mapping_result(row))
        mock_executor = _make_executor()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            await svc.rollback_switch("exec_1", "user_1")

        mock_executor.cancel_enrollment.assert_called_once_with("enr_xyz_999")

    @pytest.mark.asyncio
    async def test_22_no_executor_still_marks_rolled_back(self):
        """When no enrollment_id, executor cancel is skipped but row is updated."""
        db = _make_db()
        svc = _make_service(db)
        row = self._active_row()
        row["enrollment_id"] = None
        db.execute = AsyncMock(return_value=_make_mapping_result(row))
        mock_executor = _make_executor()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            result = await svc.rollback_switch("exec_1", "user_1")

        mock_executor.cancel_enrollment.assert_not_called()
        assert result["status"] == "rolled_back"


# =============================================================================
# approve_recommendation — 8 tests
# =============================================================================


class TestApproveRecommendation:
    """Tests for SwitchExecutionService.approve_recommendation."""

    def _audit_row(
        self,
        *,
        user_id: str = "user_1",
        decision: str = "recommend",
        executed: bool = False,
        plan_id: str = "plan_1",
    ) -> dict:
        return {
            "id": "log_1",
            "user_id": user_id,
            "decision": decision,
            "proposed_plan_id": plan_id,
            "savings_monthly": "25.00",
            "savings_annual": "300.00",
            "etf_cost": "0",
            "net_savings_year1": "300.00",
            "confidence_score": "0.85",
            "reason": "Better plan found",
            "data_source": "arcadia_15min",
            "tier": "pro",
            "executed": executed,
        }

    @pytest.mark.asyncio
    async def test_23_happy_path_returns_execution_result(self):
        """Approving a valid recommendation returns execution result dict."""
        db = _make_db(audit_row=self._audit_row())
        svc = _make_service(db)
        mock_executor = _make_executor()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            result = await svc.approve_recommendation("log_1", "user_1")

        assert "execution_id" in result
        assert result["enrollment_id"] == "enr_123"

    @pytest.mark.asyncio
    async def test_24_audit_log_not_found_raises_value_error(self):
        """Missing audit log raises ValueError."""
        db = _make_db()
        svc = _make_service(db)
        db.execute = AsyncMock(return_value=_make_mapping_result(None))

        with pytest.raises(ValueError, match="not found"):
            await svc.approve_recommendation("log_missing", "user_1")

    @pytest.mark.asyncio
    async def test_25_wrong_user_raises_value_error(self):
        """Audit log belonging to different user raises ValueError."""
        db = _make_db()
        svc = _make_service(db)
        db.execute = AsyncMock(
            return_value=_make_mapping_result(self._audit_row(user_id="other_user"))
        )

        with pytest.raises(ValueError, match="does not belong"):
            await svc.approve_recommendation("log_1", "user_1")

    @pytest.mark.asyncio
    async def test_26_not_a_recommendation_raises_value_error(self):
        """Audit log with action='switch' (not 'recommend') raises ValueError."""
        db = _make_db()
        svc = _make_service(db)
        db.execute = AsyncMock(
            return_value=_make_mapping_result(self._audit_row(decision="switch"))
        )

        with pytest.raises(ValueError, match="recommend"):
            await svc.approve_recommendation("log_1", "user_1")

    @pytest.mark.asyncio
    async def test_27_already_executed_raises_value_error(self):
        """Already-executed audit log raises ValueError."""
        db = _make_db()
        svc = _make_service(db)
        db.execute = AsyncMock(return_value=_make_mapping_result(self._audit_row(executed=True)))

        with pytest.raises(ValueError, match="already been executed"):
            await svc.approve_recommendation("log_1", "user_1")

    @pytest.mark.asyncio
    async def test_28_triggers_execute_switch(self):
        """approve_recommendation delegates to execute_switch internally."""
        db = _make_db(audit_row=self._audit_row())
        svc = _make_service(db)
        mock_executor = _make_executor()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            await svc.approve_recommendation("log_1", "user_1")

        # execute_enrollment was called — confirms execute_switch ran
        mock_executor.execute_enrollment.assert_called_once()

    @pytest.mark.asyncio
    async def test_29_updates_audit_log_executed_true(self):
        """After execution the audit log row is updated with executed=TRUE."""
        db = _make_db(audit_row=self._audit_row())
        svc = _make_service(db)
        mock_executor = _make_executor()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            await svc.approve_recommendation("log_1", "user_1")

        # The UPDATE to switch_audit_log passes a params dict with
        # 'enrollment_id' and 'id' keys. Verify that call was made.
        execute_calls = db.execute.call_args_list
        audit_update_calls = [
            c
            for c in execute_calls
            if len(c[0]) > 1
            and isinstance(c[0][1], dict)
            and "enrollment_id" in c[0][1]
            and c[0][1].get("id") == "log_1"
        ]
        assert len(audit_update_calls) >= 1

    @pytest.mark.asyncio
    async def test_30_returns_execution_result_from_execute_switch(self):
        """The dict returned by approve_recommendation mirrors execute_switch output."""
        db = _make_db(audit_row=self._audit_row())
        svc = _make_service(db)
        mock_executor = _make_executor(enrollment_id="enr_unique_999")

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            result = await svc.approve_recommendation("log_1", "user_1")

        assert result["enrollment_id"] == "enr_unique_999"
        assert result["status"] == "initiated"
        assert result["executed"] is True

    @pytest.mark.asyncio
    async def test_31_advisory_approval_does_not_mark_executed(self):
        """Approving in advisory mode records nothing as executed/enrolled."""
        db = _make_db(audit_row=self._audit_row())
        svc = _make_service(db)

        result = await svc.approve_recommendation("log_1", "user_1")

        assert result["status"] == "advisory_only"
        assert result["executed"] is False
        assert _sql_calls(db, "UPDATE switch_audit_log") == []

    @pytest.mark.asyncio
    async def test_32_approval_reuses_existing_audit_row(self):
        """No second audit snapshot is written when approving a recommendation."""
        db = _make_db(audit_row=self._audit_row())
        svc = _make_service(db)

        await svc.approve_recommendation("log_1", "user_1")

        assert _sql_calls(db, "INSERT INTO switch_audit_log") == []
        insert = _sql_calls(db, "INSERT INTO switch_executions")[0]
        assert insert[0][1]["audit_log_id"] == "log_1"


# =============================================================================
# Idempotency
# =============================================================================


class TestIdempotency:
    """execute_switch uses a deterministic key and repeats are no-ops."""

    def test_key_is_deterministic_per_user_plan_and_utc_day(self):
        from datetime import date

        day = date(2026, 11, 16)
        key = build_idempotency_key("user_1", "plan_abc", day)

        assert key == build_idempotency_key("user_1", "plan_abc", day)
        assert key != build_idempotency_key("user_2", "plan_abc", day)
        assert key != build_idempotency_key("user_1", "plan_xyz", day)
        assert key != build_idempotency_key("user_1", "plan_abc", date(2026, 11, 17))
        # switch_executions.idempotency_key is a UUID column.
        import uuid

        assert str(uuid.UUID(key)) == key

    @pytest.mark.asyncio
    async def test_two_attempts_use_the_same_key(self):
        """Old code used uuid4, so two attempts never shared a key."""
        keys = []
        for _ in range(2):
            db = _make_db()
            await _make_service(db).execute_switch("user_1", _make_decision())
            keys.append(_sql_calls(db, "INSERT INTO switch_executions")[0][0][1]["idempotency_key"])

        assert keys[0] == keys[1]
        assert keys[0] == build_idempotency_key("user_1", "plan_abc")

    @pytest.mark.asyncio
    async def test_second_attempt_is_a_noop_returning_existing_execution(self):
        existing = {"id": "exec-existing", "status": "advisory_only", "enrollment_id": None}
        db = _make_db(existing_execution=existing)
        svc = _make_service(db)
        mock_executor = _make_executor()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            result = await svc.execute_switch("user_1", _make_decision())

        assert result["execution_id"] == "exec-existing"
        assert result["status"] == "advisory_only"
        assert result["idempotent_replay"] is True
        assert result["executed"] is False
        # Nothing written, executor never called.
        assert _sql_calls(db, "INSERT INTO") == []
        mock_executor.execute_enrollment.assert_not_called()
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_after_failed_execution_reruns_on_the_same_row(self):
        """Old code returned the failed row forever for the rest of the UTC day."""
        existing = {"id": "exec-failed", "status": "failed", "enrollment_id": None}
        db = _make_db(existing_execution=existing)
        svc = _make_service(db)
        mock_executor = _make_executor()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            result = await svc.execute_switch("user_1", _make_decision())

        # Same row, re-run to a non-failed status.
        assert result["execution_id"] == "exec-failed"
        assert result["status"] == "initiated"
        assert result["idempotent_replay"] is False
        mock_executor.execute_enrollment.assert_awaited_once()
        # Row was claimed with a status guard, not re-inserted or re-snapshotted.
        claim = _sql_calls(db, "SET status = 'initiating'")
        assert len(claim) == 1
        assert "AND status = 'failed'" in str(claim[0][0][0])
        assert claim[0][0][1] == {"id": "exec-failed"}
        assert _sql_calls(db, "INSERT INTO") == []
        final = _sql_calls(db, "SET status = :status")
        assert final[0][0][1]["id"] == "exec-failed"
        assert final[0][0][1]["status"] == "initiated"

    @pytest.mark.asyncio
    async def test_retry_that_loses_the_claim_race_replays_instead(self):
        existing = {"id": "exec-failed", "status": "failed", "enrollment_id": None}
        db = _make_db(existing_execution=existing, claim_succeeds=False)
        svc = _make_service(db)
        mock_executor = _make_executor()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            result = await svc.execute_switch("user_1", _make_decision())

        assert result["idempotent_replay"] is True
        mock_executor.execute_enrollment.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status",
        ["initiating", "initiated", "submitted", "accepted", "active", "rolled_back"],
    )
    async def test_in_flight_and_completed_rows_are_returned_untouched(self, status):
        existing = {"id": "exec-existing", "status": status, "enrollment_id": "enr_1"}
        db = _make_db(existing_execution=existing)
        svc = _make_service(db)
        mock_executor = _make_executor()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            result = await svc.execute_switch("user_1", _make_decision())

        assert result["execution_id"] == "exec-existing"
        assert result["status"] == status
        assert result["idempotent_replay"] is True
        assert _sql_calls(db, "UPDATE") == []
        mock_executor.execute_enrollment.assert_not_called()
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_insert_uses_on_conflict_do_nothing(self):
        db = _make_db()
        await _make_service(db).execute_switch("user_1", _make_decision())

        sql = str(_sql_calls(db, "INSERT INTO switch_executions")[0][0][0])
        assert "ON CONFLICT (idempotency_key) DO NOTHING" in sql

    @pytest.mark.asyncio
    async def test_concurrent_conflict_rolls_back_and_does_not_call_executor(self):
        """Losing the insert race must not reach the executor."""
        db = _make_db(insert_conflicts=True)
        svc = _make_service(db)
        mock_executor = _make_executor()

        with patch(
            "services.switch_execution_service.get_executor",
            return_value=mock_executor,
        ):
            with pytest.raises(RuntimeError, match="conflicted"):
                await svc.execute_switch("user_1", _make_decision())

        db.rollback.assert_called()
        mock_executor.execute_enrollment.assert_not_called()
