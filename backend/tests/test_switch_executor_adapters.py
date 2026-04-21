"""
Tests for Switch Executor adapters.

Covers Protocol compliance, EnergyBotExecutor, AdvisoryOnlyFallback,
and the get_executor() factory for all meaningful code paths.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.switch_executor import (AdvisoryOnlyFallback, EnergyBotExecutor,
                                      EnrollmentRequest, EnrollmentResult,
                                      EnrollmentStatus, SwitchExecutor,
                                      get_executor)

# =============================================================================
# Helpers
# =============================================================================


def _make_traced_mock():
    """Return an async context manager mock for lib.tracing.traced."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=ctx)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


def _make_enrollment_request(**overrides) -> EnrollmentRequest:
    """Build a minimal EnrollmentRequest for testing."""
    defaults = {
        "plan_id": "plan_abc",
        "user_id": "user_123",
        "user_name": "Jane Doe",
        "service_address": "123 Main St",
        "zip_code": "10001",
        "utility_account_number": "ACC-9999",
        "idempotency_key": "idem-key-uuid",
    }
    defaults.update(overrides)
    return EnrollmentRequest(**defaults)


@pytest.fixture
def mock_energybot_service():
    """A fully mocked EnergyBotService."""
    svc = AsyncMock()
    return svc


@pytest.fixture
def energybot_executor(mock_energybot_service):
    return EnergyBotExecutor(mock_energybot_service)


@pytest.fixture
def advisory_executor():
    return AdvisoryOnlyFallback()


# =============================================================================
# 1 & 2 — Protocol compliance checks
# =============================================================================


class TestSwitchExecutorProtocolCompliance:
    def test_energybot_executor_satisfies_protocol(self, energybot_executor):
        """EnergyBotExecutor must satisfy the SwitchExecutor runtime-checkable Protocol."""
        assert isinstance(energybot_executor, SwitchExecutor)

    def test_advisory_fallback_satisfies_protocol(self, advisory_executor):
        """AdvisoryOnlyFallback must satisfy the SwitchExecutor runtime-checkable Protocol."""
        assert isinstance(advisory_executor, SwitchExecutor)


# =============================================================================
# 3, 4, 5 — EnergyBotExecutor.check_plan_available
# =============================================================================


class TestEnergyBotCheckPlanAvailable:
    @pytest.mark.asyncio
    async def test_returns_true_when_plan_available(
        self, energybot_executor, mock_energybot_service
    ):
        """Returns True when the upstream service reports status='available'."""
        mock_energybot_service.get_plan_details.return_value = {"status": "available"}

        with patch("services.switch_executor.traced", return_value=_make_traced_mock()):
            result = await energybot_executor.check_plan_available("plan_abc")

        assert result is True
        mock_energybot_service.get_plan_details.assert_awaited_once_with("plan_abc")

    @pytest.mark.asyncio
    async def test_returns_false_when_plan_unavailable(
        self, energybot_executor, mock_energybot_service
    ):
        """Returns False when the upstream service reports any non-available status."""
        mock_energybot_service.get_plan_details.return_value = {"status": "expired"}

        with patch("services.switch_executor.traced", return_value=_make_traced_mock()):
            result = await energybot_executor.check_plan_available("plan_expired")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_api_error(self, energybot_executor, mock_energybot_service):
        """Returns False (never raises) when the upstream call raises an exception."""
        mock_energybot_service.get_plan_details.side_effect = RuntimeError("timeout")

        with patch("services.switch_executor.traced", return_value=_make_traced_mock()):
            result = await energybot_executor.check_plan_available("plan_boom")

        assert result is False


# =============================================================================
# 6, 7 — EnergyBotExecutor.execute_enrollment
# =============================================================================


class TestEnergyBotExecuteEnrollment:
    @pytest.mark.asyncio
    async def test_execute_enrollment_success(self, energybot_executor, mock_energybot_service):
        """Returns EnrollmentResult with success=True on a happy-path enrollment."""
        switch_date = datetime(2026, 5, 1, tzinfo=UTC)
        eb_result = MagicMock(
            enrollment_id="eb-enroll-001",
            status="submitted",
            estimated_switch_date=switch_date,
            message="Enrollment submitted successfully",
        )
        mock_energybot_service.create_enrollment.return_value = eb_result

        # Stub out the EBRequest import inside the method
        mock_eb_request_cls = MagicMock()
        with (
            patch("services.switch_executor.traced", return_value=_make_traced_mock()),
            patch.dict(
                "sys.modules",
                {"services.energybot_service": MagicMock(EnrollmentRequest=mock_eb_request_cls)},
            ),
        ):
            result = await energybot_executor.execute_enrollment(_make_enrollment_request())

        assert result.success is True
        assert result.enrollment_id == "eb-enroll-001"
        assert result.status == "submitted"
        assert result.estimated_switch_date == switch_date
        assert result.provider == "energybot"

    @pytest.mark.asyncio
    async def test_execute_enrollment_failure_returns_failed_result(
        self, energybot_executor, mock_energybot_service
    ):
        """Returns EnrollmentResult with success=False when upstream call raises."""
        mock_energybot_service.create_enrollment.side_effect = ValueError("account not found")

        mock_eb_request_cls = MagicMock()
        with (
            patch("services.switch_executor.traced", return_value=_make_traced_mock()),
            patch.dict(
                "sys.modules",
                {"services.energybot_service": MagicMock(EnrollmentRequest=mock_eb_request_cls)},
            ),
        ):
            result = await energybot_executor.execute_enrollment(_make_enrollment_request())

        assert result.success is False
        assert result.status == "failed"
        assert "account not found" in result.message
        assert result.provider == "energybot"
        assert result.enrollment_id is None


# =============================================================================
# 8 — EnergyBotExecutor.check_enrollment_status
# =============================================================================


class TestEnergyBotCheckEnrollmentStatus:
    @pytest.mark.asyncio
    async def test_maps_service_result_to_enrollment_status(
        self, energybot_executor, mock_energybot_service
    ):
        """Correctly maps the upstream service response to EnrollmentStatus."""
        switch_date = datetime(2026, 5, 1, tzinfo=UTC)
        svc_result = MagicMock(
            enrollment_id="eb-enroll-001",
            status="accepted",
            switch_date=switch_date,
            rejection_reason=None,
        )
        mock_energybot_service.check_enrollment_status.return_value = svc_result

        with patch("services.switch_executor.traced", return_value=_make_traced_mock()):
            status = await energybot_executor.check_enrollment_status("eb-enroll-001")

        assert isinstance(status, EnrollmentStatus)
        assert status.enrollment_id == "eb-enroll-001"
        assert status.status == "accepted"
        assert status.switch_date == switch_date
        assert status.rejection_reason is None
        mock_energybot_service.check_enrollment_status.assert_awaited_once_with("eb-enroll-001")


# =============================================================================
# 9, 10 — EnergyBotExecutor.cancel_enrollment
# =============================================================================


class TestEnergyBotCancelEnrollment:
    @pytest.mark.asyncio
    async def test_cancel_returns_true_on_success(self, energybot_executor, mock_energybot_service):
        """Propagates True from the underlying service on successful cancellation."""
        mock_energybot_service.cancel_enrollment.return_value = True

        with patch("services.switch_executor.traced", return_value=_make_traced_mock()):
            result = await energybot_executor.cancel_enrollment("eb-enroll-001")

        assert result is True
        mock_energybot_service.cancel_enrollment.assert_awaited_once_with("eb-enroll-001")

    @pytest.mark.asyncio
    async def test_cancel_returns_false_when_service_returns_false(
        self, energybot_executor, mock_energybot_service
    ):
        """Propagates False from the underlying service (e.g. already cancelled)."""
        mock_energybot_service.cancel_enrollment.return_value = False

        with patch("services.switch_executor.traced", return_value=_make_traced_mock()):
            result = await energybot_executor.cancel_enrollment("eb-enroll-already")

        assert result is False


# =============================================================================
# 11 — AdvisoryOnlyFallback.check_plan_available
# =============================================================================


class TestAdvisoryCheckPlanAvailable:
    @pytest.mark.asyncio
    async def test_always_returns_true(self, advisory_executor):
        """Advisory mode can always recommend any plan."""
        result = await advisory_executor.check_plan_available("any-plan-id")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_for_any_plan_id(self, advisory_executor):
        """Consistent True regardless of plan_id value."""
        for plan_id in ("", "unknown", "plan_xyz_9999"):
            result = await advisory_executor.check_plan_available(plan_id)
            assert result is True


# =============================================================================
# 12 — AdvisoryOnlyFallback.execute_enrollment
# =============================================================================


class TestAdvisoryExecuteEnrollment:
    @pytest.mark.asyncio
    async def test_returns_advisory_only_status(self, advisory_executor):
        """Advisory mode must return success=False with status='advisory_only'."""
        result = await advisory_executor.execute_enrollment(_make_enrollment_request())

        assert isinstance(result, EnrollmentResult)
        assert result.success is False
        assert result.status == "advisory_only"
        assert result.enrollment_id is None
        assert result.provider == "advisory_only"
        assert "recommendation" in result.message.lower()

    @pytest.mark.asyncio
    async def test_message_explains_manual_action_needed(self, advisory_executor):
        """Returned message should guide the user to act manually."""
        result = await advisory_executor.execute_enrollment(
            _make_enrollment_request(plan_id="plan_manual")
        )
        assert "manually" in result.message.lower()


# =============================================================================
# 13 — AdvisoryOnlyFallback.check_enrollment_status
# =============================================================================


class TestAdvisoryCheckEnrollmentStatus:
    @pytest.mark.asyncio
    async def test_returns_advisory_only_status(self, advisory_executor):
        """Advisory status check reflects that no real enrollment exists."""
        status = await advisory_executor.check_enrollment_status("fake-id-999")

        assert isinstance(status, EnrollmentStatus)
        assert status.enrollment_id == "fake-id-999"
        assert status.status == "advisory_only"
        assert status.rejection_reason is not None
        assert "advisory" in status.rejection_reason.lower()


# =============================================================================
# 14 — AdvisoryOnlyFallback.cancel_enrollment
# =============================================================================


class TestAdvisoryCancelEnrollment:
    @pytest.mark.asyncio
    async def test_always_returns_true(self, advisory_executor):
        """Nothing to cancel in advisory mode — always succeeds."""
        result = await advisory_executor.cancel_enrollment("fake-enroll-id")
        assert result is True


# =============================================================================
# 15–19 — get_executor() factory
# =============================================================================


class TestGetExecutorFactory:
    def test_returns_energybot_for_tx(self):
        """Texas (us_tx) is a deregulated state — should return EnergyBotExecutor."""
        svc = MagicMock()
        executor = get_executor("us_tx", energybot_service=svc)
        assert isinstance(executor, EnergyBotExecutor)
        assert executor._service is svc

    def test_returns_energybot_for_pa(self):
        """Pennsylvania (us_pa) is a deregulated state — should return EnergyBotExecutor."""
        svc = MagicMock()
        executor = get_executor("us_pa", energybot_service=svc)
        assert isinstance(executor, EnergyBotExecutor)

    def test_returns_advisory_for_non_deregulated_state(self):
        """California (us_ca) is not deregulated — should return AdvisoryOnlyFallback."""
        svc = MagicMock()
        executor = get_executor("us_ca", energybot_service=svc)
        assert isinstance(executor, AdvisoryOnlyFallback)

    def test_returns_advisory_when_no_service_provided(self):
        """No service provided — always fall back to advisory regardless of region."""
        executor = get_executor("us_tx", energybot_service=None)
        assert isinstance(executor, AdvisoryOnlyFallback)

    def test_returns_advisory_for_unknown_region(self):
        """Completely unknown region string — falls back to advisory."""
        svc = MagicMock()
        executor = get_executor("xx_unknown", energybot_service=svc)
        assert isinstance(executor, AdvisoryOnlyFallback)

    def test_region_lookup_is_case_insensitive(self):
        """Region matching should be case-insensitive (US_TX == us_tx)."""
        svc = MagicMock()
        executor = get_executor("US_TX", energybot_service=svc)
        assert isinstance(executor, EnergyBotExecutor)


# =============================================================================
# 20 — Dataclass creation and field defaults
# =============================================================================


class TestDataclasses:
    def test_enrollment_request_fields(self):
        """EnrollmentRequest stores all required fields correctly."""
        req = EnrollmentRequest(
            plan_id="plan_1",
            user_id="u_1",
            user_name="Alice",
            service_address="1 Energy Lane",
            zip_code="90210",
            utility_account_number="UTIL-001",
            idempotency_key="idem-001",
        )
        assert req.plan_id == "plan_1"
        assert req.user_id == "u_1"
        assert req.user_name == "Alice"
        assert req.service_address == "1 Energy Lane"
        assert req.zip_code == "90210"
        assert req.utility_account_number == "UTIL-001"
        assert req.idempotency_key == "idem-001"

    def test_enrollment_result_defaults(self):
        """EnrollmentResult optional fields default to safe values."""
        result = EnrollmentResult(success=True)
        assert result.enrollment_id is None
        assert result.status == "unknown"
        assert result.estimated_switch_date is None
        assert result.message == ""
        assert result.provider == ""

    def test_enrollment_result_full_construction(self):
        """EnrollmentResult accepts all fields explicitly."""
        switch_date = datetime(2026, 6, 1, tzinfo=UTC)
        result = EnrollmentResult(
            success=True,
            enrollment_id="enroll-xyz",
            status="submitted",
            estimated_switch_date=switch_date,
            message="All good",
            provider="energybot",
        )
        assert result.enrollment_id == "enroll-xyz"
        assert result.estimated_switch_date == switch_date

    def test_enrollment_status_defaults(self):
        """EnrollmentStatus optional fields default to None."""
        status = EnrollmentStatus(enrollment_id="e1", status="active")
        assert status.switch_date is None
        assert status.rejection_reason is None

    def test_enrollment_status_full_construction(self):
        """EnrollmentStatus accepts all fields explicitly."""
        switch_date = datetime(2026, 6, 15, tzinfo=UTC)
        status = EnrollmentStatus(
            enrollment_id="e2",
            status="rejected",
            switch_date=switch_date,
            rejection_reason="Credit check failed",
        )
        assert status.rejection_reason == "Credit check failed"
        assert status.switch_date == switch_date
