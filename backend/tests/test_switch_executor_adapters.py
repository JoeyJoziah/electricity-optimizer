"""
Tests for Switch Executor adapters.

Covers Protocol compliance, AdvisoryOnlyFallback,
and the get_executor() factory for all meaningful code paths.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.switch_executor import (
    AdvisoryOnlyFallback,
    EnrollmentRequest,
    EnrollmentResult,
    EnrollmentStatus,
    SwitchExecutor,
    get_executor,
)

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
def advisory_executor():
    return AdvisoryOnlyFallback()


# =============================================================================
# 1 & 2 — Protocol compliance checks
# =============================================================================


class TestSwitchExecutorProtocolCompliance:
    def test_advisory_fallback_satisfies_protocol(self, advisory_executor):
        """AdvisoryOnlyFallback must satisfy the SwitchExecutor runtime-checkable Protocol."""
        assert isinstance(advisory_executor, SwitchExecutor)


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
    """The product is advisory-only: every region resolves to the advisory executor."""

    @pytest.mark.parametrize("region", ["us_tx", "US_TX", "us_pa", "us_ct", "us_ca", "xx_unknown"])
    def test_every_region_gets_advisory_executor(self, region):
        assert isinstance(get_executor(region), AdvisoryOnlyFallback)

    def test_factory_takes_no_provider_service(self):
        """The EnergyBot service parameter is gone."""
        with pytest.raises(TypeError):
            get_executor("us_tx", energybot_service=object())

    def test_no_energybot_adapter_exported(self):
        import services.switch_executor as module

        assert not hasattr(module, "EnergyBotExecutor")


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
