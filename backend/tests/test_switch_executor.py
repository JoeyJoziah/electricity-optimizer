"""Tests for switch_executor — adapters + factory."""

from datetime import UTC

import pytest

from services.switch_executor import (
    AdvisoryOnlyFallback,
    EnrollmentRequest,
    EnrollmentResult,
    EnrollmentStatus,
    SwitchExecutor,
    get_executor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UTC = UTC


def _req(**overrides) -> EnrollmentRequest:
    base = {
        "plan_id": "plan-abc",
        "user_id": "user-1",
        "user_name": "Alice Smith",
        "service_address": "123 Main St",
        "zip_code": "10001",
        "utility_account_number": "ACC-999",
        "idempotency_key": "idem-key-001",
    }
    base.update(overrides)
    return EnrollmentRequest(**base)


class _AsyncNullCtx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _null_ctx():
    return _AsyncNullCtx()


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


def test_enrollment_request_fields():
    req = _req()
    assert req.plan_id == "plan-abc"
    assert req.idempotency_key == "idem-key-001"


def test_enrollment_result_defaults():
    result = EnrollmentResult(success=True)
    assert result.enrollment_id is None
    assert result.status == "unknown"
    assert result.message == ""
    assert result.provider == ""


def test_enrollment_status_fields():
    es = EnrollmentStatus(enrollment_id="enr-1", status="active")
    assert es.enrollment_id == "enr-1"
    assert es.status == "active"
    assert es.switch_date is None
    assert es.rejection_reason is None


# ---------------------------------------------------------------------------
# AdvisoryOnlyFallback
# ---------------------------------------------------------------------------


class TestAdvisoryOnlyFallback:
    @pytest.mark.asyncio
    async def test_check_plan_available_always_true(self):
        fb = AdvisoryOnlyFallback()
        assert await fb.check_plan_available("plan-anything") is True

    @pytest.mark.asyncio
    async def test_execute_enrollment_returns_advisory_only(self):
        fb = AdvisoryOnlyFallback()
        result = await fb.execute_enrollment(_req())
        assert result.success is False
        assert result.status == "advisory_only"
        assert result.provider == "advisory_only"
        assert "recommendation" in result.message.lower()

    @pytest.mark.asyncio
    async def test_execute_enrollment_has_no_enrollment_id(self):
        fb = AdvisoryOnlyFallback()
        result = await fb.execute_enrollment(_req())
        assert result.enrollment_id is None

    @pytest.mark.asyncio
    async def test_check_enrollment_status_returns_advisory_only(self):
        fb = AdvisoryOnlyFallback()
        status = await fb.check_enrollment_status("enr-fake")
        assert status.enrollment_id == "enr-fake"
        assert status.status == "advisory_only"
        assert "advisory" in (status.rejection_reason or "").lower()

    @pytest.mark.asyncio
    async def test_cancel_enrollment_always_true(self):
        fb = AdvisoryOnlyFallback()
        assert await fb.cancel_enrollment("enr-fake") is True


# ---------------------------------------------------------------------------
# get_executor factory
# ---------------------------------------------------------------------------


class TestGetExecutor:
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


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_advisory_fallback_satisfies_protocol():
    fb = AdvisoryOnlyFallback()
    assert isinstance(fb, SwitchExecutor)
