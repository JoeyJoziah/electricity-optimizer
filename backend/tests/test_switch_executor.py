"""Tests for switch_executor — adapters + factory."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.switch_executor import (
    AdvisoryOnlyFallback,
    EnergyBotExecutor,
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
# EnergyBotExecutor — check_plan_available
# ---------------------------------------------------------------------------


class TestEnergyBotCheckPlanAvailable:
    def _exec(self):
        svc = AsyncMock()
        return EnergyBotExecutor(svc), svc

    @pytest.mark.asyncio
    async def test_returns_true_when_status_available(self):
        ex, svc = self._exec()
        svc.get_plan_details.return_value = {"status": "available"}
        with patch("services.switch_executor.traced", return_value=_null_ctx()):
            assert await ex.check_plan_available("plan-1") is True

    @pytest.mark.asyncio
    async def test_returns_false_when_status_not_available(self):
        ex, svc = self._exec()
        svc.get_plan_details.return_value = {"status": "expired"}
        with patch("services.switch_executor.traced", return_value=_null_ctx()):
            assert await ex.check_plan_available("plan-1") is False

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        ex, svc = self._exec()
        svc.get_plan_details.side_effect = RuntimeError("network error")
        with patch("services.switch_executor.traced", return_value=_null_ctx()):
            assert await ex.check_plan_available("plan-1") is False


# ---------------------------------------------------------------------------
# EnergyBotExecutor — execute_enrollment
# ---------------------------------------------------------------------------


class TestEnergyBotExecuteEnrollment:
    def _exec(self):
        svc = AsyncMock()
        return EnergyBotExecutor(svc), svc

    @pytest.mark.asyncio
    async def test_success_maps_result_fields(self):
        ex, svc = self._exec()
        switch_date = datetime(2026, 7, 1, tzinfo=_UTC)
        svc.create_enrollment.return_value = MagicMock(
            enrollment_id="enr-001",
            status="submitted",
            estimated_switch_date=switch_date,
            message="Enrollment submitted",
        )
        fake_eb_request = MagicMock()
        fake_eb_module = MagicMock()
        fake_eb_module.EnrollmentRequest.return_value = fake_eb_request

        with (
            patch("services.switch_executor.traced", return_value=_null_ctx()),
            patch.dict("sys.modules", {"services.energybot_service": fake_eb_module}),
        ):
            result = await ex.execute_enrollment(_req())

        assert result.success is True
        assert result.enrollment_id == "enr-001"
        assert result.status == "submitted"
        assert result.estimated_switch_date == switch_date
        assert result.provider == "energybot"

    @pytest.mark.asyncio
    async def test_exception_returns_failed_result(self):
        ex, svc = self._exec()
        svc.create_enrollment.side_effect = RuntimeError("API down")
        fake_eb_module = MagicMock()

        with (
            patch("services.switch_executor.traced", return_value=_null_ctx()),
            patch.dict("sys.modules", {"services.energybot_service": fake_eb_module}),
        ):
            result = await ex.execute_enrollment(_req())

        assert result.success is False
        assert result.status == "failed"
        assert "API down" in result.message
        assert result.provider == "energybot"


# ---------------------------------------------------------------------------
# EnergyBotExecutor — check_enrollment_status
# ---------------------------------------------------------------------------


class TestEnergyBotCheckEnrollmentStatus:
    @pytest.mark.asyncio
    async def test_maps_status_result(self):
        svc = AsyncMock()
        ex = EnergyBotExecutor(svc)
        svc.check_enrollment_status.return_value = MagicMock(
            enrollment_id="enr-123",
            status="active",
            switch_date=datetime(2026, 7, 1, tzinfo=_UTC),
            rejection_reason=None,
        )
        with patch("services.switch_executor.traced", return_value=_null_ctx()):
            status = await ex.check_enrollment_status("enr-123")

        assert status.enrollment_id == "enr-123"
        assert status.status == "active"
        assert status.rejection_reason is None


# ---------------------------------------------------------------------------
# EnergyBotExecutor — cancel_enrollment
# ---------------------------------------------------------------------------


class TestEnergyBotCancelEnrollment:
    @pytest.mark.asyncio
    async def test_delegates_to_service(self):
        svc = AsyncMock()
        ex = EnergyBotExecutor(svc)
        svc.cancel_enrollment.return_value = True
        with patch("services.switch_executor.traced", return_value=_null_ctx()):
            result = await ex.cancel_enrollment("enr-xyz")
        assert result is True
        svc.cancel_enrollment.assert_awaited_once_with("enr-xyz")


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
    def test_returns_energybot_for_supported_region_with_service(self):
        svc = MagicMock()
        ex = get_executor("us_tx", energybot_service=svc)
        assert isinstance(ex, EnergyBotExecutor)

    def test_returns_advisory_for_unsupported_region(self):
        svc = MagicMock()
        ex = get_executor("ca_on", energybot_service=svc)
        assert isinstance(ex, AdvisoryOnlyFallback)

    def test_returns_advisory_when_no_service(self):
        ex = get_executor("us_tx", energybot_service=None)
        assert isinstance(ex, AdvisoryOnlyFallback)

    def test_region_matching_is_case_insensitive(self):
        svc = MagicMock()
        ex = get_executor("US_TX", energybot_service=svc)
        assert isinstance(ex, EnergyBotExecutor)

    def test_all_supported_regions_get_energybot(self):
        svc = MagicMock()
        supported = [
            "us_tx",
            "us_pa",
            "us_oh",
            "us_il",
            "us_ny",
            "us_nj",
            "us_md",
            "us_ct",
            "us_ma",
            "us_me",
            "us_nh",
            "us_ri",
            "us_dc",
        ]
        for region in supported:
            ex = get_executor(region, energybot_service=svc)
            assert isinstance(ex, EnergyBotExecutor), f"Expected EnergyBot for {region}"


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_energybot_executor_satisfies_protocol():
    svc = MagicMock()
    ex = EnergyBotExecutor(svc)
    assert isinstance(ex, SwitchExecutor)


def test_advisory_fallback_satisfies_protocol():
    fb = AdvisoryOnlyFallback()
    assert isinstance(fb, SwitchExecutor)
