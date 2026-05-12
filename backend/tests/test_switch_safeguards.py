"""Tests for SwitchSafeguardsService — all 5 safeguard checks."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.switch_safeguards import (
    DEFAULT_COOLDOWN_DAYS,
    ETF_FREE_SWITCH_WINDOW_DAYS,
    SafeguardResult,
    SwitchSafeguardsService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> tuple[SwitchSafeguardsService, AsyncMock]:
    db = AsyncMock()
    return SwitchSafeguardsService(db), db


def _make_row(**kwargs):
    """Return a MagicMock that behaves like a row mapping."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: kwargs[key]
    row.__contains__ = lambda self, key: key in kwargs
    # also support attribute access via .get
    row.get = lambda key, default=None: kwargs.get(key, default)
    return row


def _mappings_result(row):
    """Build the chain: db.execute() → result.mappings().first() == row."""
    result = MagicMock()
    result.mappings.return_value.first.return_value = row
    return result


# ---------------------------------------------------------------------------
# SafeguardResult dataclass
# ---------------------------------------------------------------------------


def test_safeguard_result_passed():
    r = SafeguardResult(passed=True, reason="OK")
    assert r.passed is True
    assert r.reason == "OK"


def test_safeguard_result_failed():
    r = SafeguardResult(passed=False, reason="Blocked")
    assert r.passed is False


# ---------------------------------------------------------------------------
# check_savings_floor (pure logic — no DB)
# ---------------------------------------------------------------------------


class TestCheckSavingsFloor:
    def _svc(self):
        svc, _ = _make_service()
        return svc

    def test_passes_when_pct_meets_threshold(self):
        svc = self._svc()
        result = svc.check_savings_floor(
            monthly_savings=Decimal("5"),
            savings_pct=Decimal("20"),
            threshold_min=Decimal("15"),  # not met
            threshold_pct=Decimal("10"),  # met
        )
        assert result.passed is True

    def test_passes_when_min_meets_threshold(self):
        svc = self._svc()
        result = svc.check_savings_floor(
            monthly_savings=Decimal("20"),
            savings_pct=Decimal("5"),
            threshold_min=Decimal("10"),  # met
            threshold_pct=Decimal("15"),  # not met
        )
        assert result.passed is True

    def test_passes_when_both_thresholds_met(self):
        svc = self._svc()
        result = svc.check_savings_floor(
            monthly_savings=Decimal("20"),
            savings_pct=Decimal("20"),
            threshold_min=Decimal("10"),
            threshold_pct=Decimal("10"),
        )
        assert result.passed is True

    def test_fails_when_neither_threshold_met(self):
        svc = self._svc()
        result = svc.check_savings_floor(
            monthly_savings=Decimal("5"),
            savings_pct=Decimal("3"),
            threshold_min=Decimal("10"),
            threshold_pct=Decimal("5"),
        )
        assert result.passed is False
        assert "below threshold" in result.reason

    def test_reason_includes_actual_values_on_fail(self):
        svc = self._svc()
        result = svc.check_savings_floor(
            monthly_savings=Decimal("4.50"),
            savings_pct=Decimal("2"),
            threshold_min=Decimal("10"),
            threshold_pct=Decimal("5"),
        )
        assert "4.50" in result.reason

    def test_passes_at_exact_pct_threshold(self):
        svc = self._svc()
        result = svc.check_savings_floor(
            monthly_savings=Decimal("0"),
            savings_pct=Decimal("10"),
            threshold_min=Decimal("999"),
            threshold_pct=Decimal("10"),
        )
        assert result.passed is True

    def test_passes_at_exact_min_threshold(self):
        svc = self._svc()
        result = svc.check_savings_floor(
            monthly_savings=Decimal("10"),
            savings_pct=Decimal("0"),
            threshold_min=Decimal("10"),
            threshold_pct=Decimal("999"),
        )
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_etf_guard (pure logic — no DB)
# ---------------------------------------------------------------------------


class TestCheckEtfGuard:
    def _svc(self):
        svc, _ = _make_service()
        return svc

    def test_passes_when_no_etf(self):
        svc = self._svc()
        result = svc.check_etf_guard(
            etf_amount=Decimal("0"),
            annual_savings=Decimal("200"),
            contract_days_remaining=100,
        )
        assert result.passed is True
        assert result.reason == "No ETF"

    def test_passes_when_etf_negative(self):
        svc = self._svc()
        result = svc.check_etf_guard(
            etf_amount=Decimal("-10"),
            annual_savings=Decimal("200"),
            contract_days_remaining=100,
        )
        assert result.passed is True

    def test_passes_in_free_switch_window(self):
        svc = self._svc()
        result = svc.check_etf_guard(
            etf_amount=Decimal("500"),
            annual_savings=Decimal("100"),
            contract_days_remaining=ETF_FREE_SWITCH_WINDOW_DAYS,
        )
        assert result.passed is True
        assert result.reason == "Free switch window open"

    def test_passes_just_inside_free_switch_window(self):
        svc = self._svc()
        result = svc.check_etf_guard(
            etf_amount=Decimal("500"),
            annual_savings=Decimal("100"),
            contract_days_remaining=ETF_FREE_SWITCH_WINDOW_DAYS - 1,
        )
        assert result.passed is True

    def test_passes_when_etf_covered_by_savings(self):
        # net_year1 = 240 - 50 = 190; threshold = 240 * 0.5 = 120 → 190 >= 120 passes
        svc = self._svc()
        result = svc.check_etf_guard(
            etf_amount=Decimal("50"),
            annual_savings=Decimal("240"),
            contract_days_remaining=200,
        )
        assert result.passed is True
        assert result.reason == "ETF covered by savings"

    def test_fails_when_etf_exceeds_savings_threshold(self):
        # net_year1 = 100 - 80 = 20; threshold = 100 * 0.5 = 50 → 20 < 50 fails
        svc = self._svc()
        result = svc.check_etf_guard(
            etf_amount=Decimal("80"),
            annual_savings=Decimal("100"),
            contract_days_remaining=200,
        )
        assert result.passed is False
        assert "80.00" in result.reason

    def test_etf_exactly_at_coverage_threshold_passes(self):
        # net_year1 = 200 - 100 = 100; threshold = 200 * 0.5 = 100 → 100 >= 100 passes
        svc = self._svc()
        result = svc.check_etf_guard(
            etf_amount=Decimal("100"),
            annual_savings=Decimal("200"),
            contract_days_remaining=200,
        )
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_kill_switch (DB-dependent)
# ---------------------------------------------------------------------------


class TestCheckKillSwitch:
    @pytest.mark.asyncio
    async def test_no_settings_row_returns_disabled(self):
        svc, db = _make_service()
        db.execute.return_value = _mappings_result(None)
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_kill_switch("uid-1")
        assert result.passed is False
        assert result.reason == "Agent disabled"

    @pytest.mark.asyncio
    async def test_disabled_agent(self):
        svc, db = _make_service()
        row = _make_row(enabled=False, loa_signed_at=None, loa_revoked_at=None, paused_until=None)
        db.execute.return_value = _mappings_result(row)
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_kill_switch("uid-1")
        assert result.passed is False
        assert result.reason == "Agent disabled"

    @pytest.mark.asyncio
    async def test_loa_revoked(self):
        svc, db = _make_service()
        row = _make_row(
            enabled=True,
            loa_signed_at=datetime(2026, 1, 1, tzinfo=UTC),
            loa_revoked_at=datetime(2026, 2, 1, tzinfo=UTC),
            paused_until=None,
        )
        db.execute.return_value = _mappings_result(row)
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_kill_switch("uid-1")
        assert result.passed is False
        assert result.reason == "LOA revoked"

    @pytest.mark.asyncio
    async def test_loa_not_signed(self):
        svc, db = _make_service()
        row = _make_row(
            enabled=True,
            loa_signed_at=None,
            loa_revoked_at=None,
            paused_until=None,
        )
        db.execute.return_value = _mappings_result(row)
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_kill_switch("uid-1")
        assert result.passed is False
        assert result.reason == "LOA not signed"

    @pytest.mark.asyncio
    async def test_paused_until_future(self):
        svc, db = _make_service()
        future = datetime.now(UTC) + timedelta(days=10)
        row = _make_row(
            enabled=True,
            loa_signed_at=datetime(2026, 1, 1, tzinfo=UTC),
            loa_revoked_at=None,
            paused_until=future,
        )
        db.execute.return_value = _mappings_result(row)
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_kill_switch("uid-1")
        assert result.passed is False
        assert "Paused until" in result.reason

    @pytest.mark.asyncio
    async def test_paused_until_naive_datetime_treated_as_utc(self):
        svc, db = _make_service()
        # naive datetime 10 days in the future
        future_naive = datetime.utcnow() + timedelta(days=10)
        row = _make_row(
            enabled=True,
            loa_signed_at=datetime(2026, 1, 1, tzinfo=UTC),
            loa_revoked_at=None,
            paused_until=future_naive,
        )
        db.execute.return_value = _mappings_result(row)
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_kill_switch("uid-1")
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_paused_until_past_is_clear(self):
        svc, db = _make_service()
        past = datetime.now(UTC) - timedelta(days=1)
        row = _make_row(
            enabled=True,
            loa_signed_at=datetime(2026, 1, 1, tzinfo=UTC),
            loa_revoked_at=None,
            paused_until=past,
        )
        db.execute.return_value = _mappings_result(row)
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_kill_switch("uid-1")
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_all_clear(self):
        svc, db = _make_service()
        row = _make_row(
            enabled=True,
            loa_signed_at=datetime(2026, 1, 1, tzinfo=UTC),
            loa_revoked_at=None,
            paused_until=None,
        )
        db.execute.return_value = _mappings_result(row)
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_kill_switch("uid-1")
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_cooldown (DB-dependent)
# ---------------------------------------------------------------------------


class TestCheckCooldown:
    @pytest.mark.asyncio
    async def test_no_previous_switch_passes(self):
        svc, db = _make_service()
        db.execute.return_value = _mappings_result(None)
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_cooldown("uid-1")
        assert result.passed is True
        assert "No previous switch" in result.reason

    @pytest.mark.asyncio
    async def test_active_cooldown_fails(self):
        svc, db = _make_service()
        # enacted 2 days ago, cooldown 5 days → 3 days remaining
        enacted = datetime.now(UTC) - timedelta(days=2)
        switch_row = _make_row(enacted_at=enacted)
        settings_row = _make_row(cooldown_days=DEFAULT_COOLDOWN_DAYS)
        db.execute.side_effect = [
            _mappings_result(switch_row),
            _mappings_result(settings_row),
        ]
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_cooldown("uid-1")
        assert result.passed is False
        assert "Cooldown active" in result.reason

    @pytest.mark.asyncio
    async def test_expired_cooldown_passes(self):
        svc, db = _make_service()
        # enacted 6 days ago, cooldown 5 days → elapsed
        enacted = datetime.now(UTC) - timedelta(days=6)
        switch_row = _make_row(enacted_at=enacted)
        settings_row = _make_row(cooldown_days=DEFAULT_COOLDOWN_DAYS)
        db.execute.side_effect = [
            _mappings_result(switch_row),
            _mappings_result(settings_row),
        ]
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_cooldown("uid-1")
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_uses_default_cooldown_when_settings_missing(self):
        svc, db = _make_service()
        # enacted 2 days ago; no settings row → default 5 days → still in cooldown
        enacted = datetime.now(UTC) - timedelta(days=2)
        switch_row = _make_row(enacted_at=enacted)
        db.execute.side_effect = [
            _mappings_result(switch_row),
            _mappings_result(None),
        ]
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_cooldown("uid-1")
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_naive_enacted_at_treated_as_utc(self):
        svc, db = _make_service()
        # naive, 2 days ago
        enacted_naive = datetime.utcnow() - timedelta(days=2)
        switch_row = _make_row(enacted_at=enacted_naive)
        settings_row = _make_row(cooldown_days=DEFAULT_COOLDOWN_DAYS)
        db.execute.side_effect = [
            _mappings_result(switch_row),
            _mappings_result(settings_row),
        ]
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_cooldown("uid-1")
        assert result.passed is False  # still in cooldown


# ---------------------------------------------------------------------------
# check_rescission (DB-dependent)
# ---------------------------------------------------------------------------


class TestCheckRescission:
    @pytest.mark.asyncio
    async def test_no_rescission_record_passes(self):
        svc, db = _make_service()
        db.execute.return_value = _mappings_result(None)
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_rescission("uid-1")
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_active_rescission_fails(self):
        svc, db = _make_service()
        future = datetime.now(UTC) + timedelta(days=5)
        row = _make_row(rescission_ends=future)
        db.execute.return_value = _mappings_result(row)
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_rescission("uid-1")
        assert result.passed is False
        assert "Rescission active" in result.reason

    @pytest.mark.asyncio
    async def test_expired_rescission_passes(self):
        svc, db = _make_service()
        past = datetime.now(UTC) - timedelta(days=1)
        row = _make_row(rescission_ends=past)
        db.execute.return_value = _mappings_result(row)
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_rescission("uid-1")
        assert result.passed is True
        assert "complete" in result.reason

    @pytest.mark.asyncio
    async def test_naive_rescission_ends_treated_as_utc(self):
        svc, db = _make_service()
        future_naive = datetime.utcnow() + timedelta(days=3)
        row = _make_row(rescission_ends=future_naive)
        db.execute.return_value = _mappings_result(row)
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            result = await svc.check_rescission("uid-1")
        assert result.passed is False


# ---------------------------------------------------------------------------
# run_all_safeguards (integration of all 5 checks)
# ---------------------------------------------------------------------------


class TestRunAllSafeguards:
    @pytest.mark.asyncio
    async def test_short_circuits_on_kill_switch_fail(self):
        svc, db = _make_service()
        # No settings row → kill switch fails immediately
        db.execute.return_value = _mappings_result(None)
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            results = await svc.run_all_safeguards(
                user_id="uid-1",
                monthly_savings=Decimal("20"),
                savings_pct=Decimal("15"),
                threshold_min=Decimal("10"),
                threshold_pct=Decimal("10"),
                etf_amount=Decimal("0"),
                annual_savings=Decimal("240"),
                contract_days_remaining=200,
            )
        assert len(results) == 1
        assert results[0].passed is False

    @pytest.mark.asyncio
    async def test_all_five_results_when_all_pass(self):
        svc, db = _make_service()

        # kill_switch: enabled, loa signed, not paused
        ks_row = _make_row(
            enabled=True,
            loa_signed_at=datetime(2026, 1, 1, tzinfo=UTC),
            loa_revoked_at=None,
            paused_until=None,
        )
        # cooldown: no previous switch
        cd_none = _mappings_result(None)
        # rescission: no record
        re_none = _mappings_result(None)

        db.execute.side_effect = [
            _mappings_result(ks_row),  # kill_switch query
            _mappings_result(None),  # cooldown — switch_executions (no row)
            _mappings_result(None),  # rescission query
        ]
        with patch("services.switch_safeguards.traced", return_value=_async_null_ctx()):
            results = await svc.run_all_safeguards(
                user_id="uid-1",
                monthly_savings=Decimal("20"),
                savings_pct=Decimal("20"),
                threshold_min=Decimal("10"),
                threshold_pct=Decimal("10"),
                etf_amount=Decimal("0"),
                annual_savings=Decimal("240"),
                contract_days_remaining=200,
            )
        assert len(results) == 5
        assert all(r.passed for r in results)


# ---------------------------------------------------------------------------
# Async context manager helper
# ---------------------------------------------------------------------------


class _AsyncNullCtx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _async_null_ctx():
    return _AsyncNullCtx()
