"""
Tests for SwitchSafeguardsService (backend/services/switch_safeguards.py)

30 tests across 6 categories:
1. check_kill_switch (6 tests)
2. check_cooldown (5 tests)
3. check_savings_floor (6 tests)
4. check_etf_guard (6 tests)
5. check_rescission (4 tests)
6. run_all_safeguards (3 tests)
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from services.switch_safeguards import SwitchSafeguardsService

USER_ID = "user-abc-123"


# =============================================================================
# Helpers
# =============================================================================


def _make_db_result(row: dict | None) -> MagicMock:
    """Build a mock DB result where .mappings().first() returns a dict-like object."""
    mock_row = None
    if row is not None:
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: row[key]
        mock_row.__contains__ = lambda self, key: key in row
        mock_row.get = lambda key, default=None: row.get(key, default)
        # Make attribute access mirror dict access for row["key"] style
        for k, v in row.items():
            setattr(mock_row, k, v)

    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = mock_row
    return mock_result


def _make_service(db: AsyncMock) -> SwitchSafeguardsService:
    return SwitchSafeguardsService(db)


# =============================================================================
# 1. check_kill_switch (6 tests)
# =============================================================================


class TestCheckKillSwitch:
    async def test_agent_disabled(self):
        """enabled=False → fail 'Agent disabled'."""
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=_make_db_result(
                {
                    "enabled": False,
                    "loa_signed_at": datetime.now(UTC),
                    "loa_revoked_at": None,
                    "paused_until": None,
                }
            )
        )
        svc = _make_service(db)
        result = await svc.check_kill_switch(USER_ID)
        assert result.passed is False
        assert "disabled" in result.reason.lower()

    async def test_loa_revoked(self):
        """loa_revoked_at set → fail 'LOA revoked'."""
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=_make_db_result(
                {
                    "enabled": True,
                    "loa_signed_at": datetime.now(UTC) - timedelta(days=10),
                    "loa_revoked_at": datetime.now(UTC) - timedelta(days=1),
                    "paused_until": None,
                }
            )
        )
        svc = _make_service(db)
        result = await svc.check_kill_switch(USER_ID)
        assert result.passed is False
        assert "revoked" in result.reason.lower()

    async def test_loa_not_signed(self):
        """loa_signed_at is None → fail 'LOA not signed'."""
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=_make_db_result(
                {
                    "enabled": True,
                    "loa_signed_at": None,
                    "loa_revoked_at": None,
                    "paused_until": None,
                }
            )
        )
        svc = _make_service(db)
        result = await svc.check_kill_switch(USER_ID)
        assert result.passed is False
        assert "not signed" in result.reason.lower()

    async def test_paused_until_future(self):
        """paused_until > now → fail with pause date in reason."""
        future = datetime.now(UTC) + timedelta(days=5)
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=_make_db_result(
                {
                    "enabled": True,
                    "loa_signed_at": datetime.now(UTC) - timedelta(days=10),
                    "loa_revoked_at": None,
                    "paused_until": future,
                }
            )
        )
        svc = _make_service(db)
        result = await svc.check_kill_switch(USER_ID)
        assert result.passed is False
        assert "paused" in result.reason.lower()
        # The reason should include the date
        assert future.strftime("%Y-%m-%d") in result.reason

    async def test_paused_until_past_passes(self):
        """paused_until <= now → check passes (pause has expired)."""
        past = datetime.now(UTC) - timedelta(days=1)
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=_make_db_result(
                {
                    "enabled": True,
                    "loa_signed_at": datetime.now(UTC) - timedelta(days=10),
                    "loa_revoked_at": None,
                    "paused_until": past,
                }
            )
        )
        svc = _make_service(db)
        result = await svc.check_kill_switch(USER_ID)
        assert result.passed is True
        assert "clear" in result.reason.lower()

    async def test_all_clear(self):
        """All conditions satisfied → passed=True, reason 'Kill switch clear'."""
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=_make_db_result(
                {
                    "enabled": True,
                    "loa_signed_at": datetime.now(UTC) - timedelta(days=30),
                    "loa_revoked_at": None,
                    "paused_until": None,
                }
            )
        )
        svc = _make_service(db)
        result = await svc.check_kill_switch(USER_ID)
        assert result.passed is True
        assert result.reason == "Kill switch clear"


# =============================================================================
# 2. check_cooldown (5 tests)
# =============================================================================


class TestCheckCooldown:
    async def test_no_previous_switch_passes(self):
        """No switch_executions row → passed=True."""
        db = AsyncMock()
        # First call: switch_executions → no row
        switch_result = _make_db_result(None)
        db.execute = AsyncMock(return_value=switch_result)
        svc = _make_service(db)
        result = await svc.check_cooldown(USER_ID)
        assert result.passed is True

    async def test_cooldown_active(self):
        """Switch enacted 2 days ago, cooldown_days=5 → fail with days remaining."""
        enacted = datetime.now(UTC) - timedelta(days=2)
        db = AsyncMock()

        switch_result = _make_db_result({"enacted_at": enacted})
        settings_result = _make_db_result({"cooldown_days": 5})
        db.execute = AsyncMock(side_effect=[switch_result, settings_result])

        svc = _make_service(db)
        result = await svc.check_cooldown(USER_ID)
        assert result.passed is False
        assert "cooldown active" in result.reason.lower()
        assert "days remaining" in result.reason.lower()

    async def test_cooldown_expired_passes(self):
        """Switch enacted 10 days ago, cooldown_days=5 → cooldown has elapsed → pass."""
        enacted = datetime.now(UTC) - timedelta(days=10)
        db = AsyncMock()

        switch_result = _make_db_result({"enacted_at": enacted})
        settings_result = _make_db_result({"cooldown_days": 5})
        db.execute = AsyncMock(side_effect=[switch_result, settings_result])

        svc = _make_service(db)
        result = await svc.check_cooldown(USER_ID)
        assert result.passed is True

    async def test_custom_cooldown_days(self):
        """Custom cooldown_days=14 is respected from user_agent_settings."""
        enacted = datetime.now(UTC) - timedelta(days=7)
        db = AsyncMock()

        switch_result = _make_db_result({"enacted_at": enacted})
        settings_result = _make_db_result({"cooldown_days": 14})
        db.execute = AsyncMock(side_effect=[switch_result, settings_result])

        svc = _make_service(db)
        result = await svc.check_cooldown(USER_ID)
        # 7 days in, 14 day cooldown → still active
        assert result.passed is False
        assert "days remaining" in result.reason.lower()

    async def test_no_settings_row_uses_default_5_days(self):
        """No user_agent_settings row → default cooldown_days=5 is applied."""
        enacted = datetime.now(UTC) - timedelta(days=2)
        db = AsyncMock()

        switch_result = _make_db_result({"enacted_at": enacted})
        # No settings row
        settings_result = _make_db_result(None)
        db.execute = AsyncMock(side_effect=[switch_result, settings_result])

        svc = _make_service(db)
        result = await svc.check_cooldown(USER_ID)
        # 2 days in, default 5 day cooldown → still active
        assert result.passed is False
        assert "cooldown active" in result.reason.lower()


# =============================================================================
# 3. check_savings_floor (6 tests)
# =============================================================================


class TestCheckSavingsFloor:
    """check_savings_floor is a pure sync method — no DB needed."""

    def _svc(self) -> SwitchSafeguardsService:
        return SwitchSafeguardsService(MagicMock())

    def test_both_thresholds_met(self):
        """Both pct and absolute thresholds met → pass."""
        svc = self._svc()
        result = svc.check_savings_floor(
            monthly_savings=Decimal("20"),
            savings_pct=Decimal("15"),
            threshold_min=Decimal("10"),
            threshold_pct=Decimal("10"),
        )
        assert result.passed is True

    def test_only_pct_threshold_met(self):
        """Pct threshold met, absolute below threshold → still pass (OR logic)."""
        svc = self._svc()
        result = svc.check_savings_floor(
            monthly_savings=Decimal("5"),
            savings_pct=Decimal("12"),
            threshold_min=Decimal("10"),
            threshold_pct=Decimal("10"),
        )
        assert result.passed is True

    def test_only_min_threshold_met(self):
        """Absolute threshold met, pct below → still pass (OR logic)."""
        svc = self._svc()
        result = svc.check_savings_floor(
            monthly_savings=Decimal("15"),
            savings_pct=Decimal("5"),
            threshold_min=Decimal("10"),
            threshold_pct=Decimal("10"),
        )
        assert result.passed is True

    def test_neither_threshold_met(self):
        """Both thresholds missed → fail with savings amounts in reason."""
        svc = self._svc()
        result = svc.check_savings_floor(
            monthly_savings=Decimal("3"),
            savings_pct=Decimal("2"),
            threshold_min=Decimal("10"),
            threshold_pct=Decimal("10"),
        )
        assert result.passed is False
        assert "3.00" in result.reason
        assert "2" in result.reason

    def test_zero_savings_fails(self):
        """Zero savings → both thresholds missed → fail."""
        svc = self._svc()
        result = svc.check_savings_floor(
            monthly_savings=Decimal("0"),
            savings_pct=Decimal("0"),
            threshold_min=Decimal("10"),
            threshold_pct=Decimal("10"),
        )
        assert result.passed is False

    def test_edge_case_exact_pct_threshold(self):
        """savings_pct exactly at threshold_pct → passes (>= comparison)."""
        svc = self._svc()
        result = svc.check_savings_floor(
            monthly_savings=Decimal("0"),  # absolute fails
            savings_pct=Decimal("10"),  # exactly at threshold
            threshold_min=Decimal("10"),
            threshold_pct=Decimal("10"),
        )
        assert result.passed is True


# =============================================================================
# 4. check_etf_guard (6 tests)
# =============================================================================


class TestCheckEtfGuard:
    """check_etf_guard is a pure sync method — no DB needed."""

    def _svc(self) -> SwitchSafeguardsService:
        return SwitchSafeguardsService(MagicMock())

    def test_no_etf_passes(self):
        """etf_amount=0 → passed=True 'No ETF'."""
        svc = self._svc()
        result = svc.check_etf_guard(
            etf_amount=Decimal("0"),
            annual_savings=Decimal("500"),
            contract_days_remaining=200,
        )
        assert result.passed is True
        assert result.reason == "No ETF"

    def test_free_switch_window_passes(self):
        """contract_days_remaining <= 45 → passed=True even with ETF."""
        svc = self._svc()
        result = svc.check_etf_guard(
            etf_amount=Decimal("200"),
            annual_savings=Decimal("100"),
            contract_days_remaining=30,
        )
        assert result.passed is True
        assert "free switch" in result.reason.lower()

    def test_etf_covered_by_savings_passes(self):
        """ETF is more than covered by savings → pass."""
        svc = self._svc()
        # annual_savings=600, etf=100 → net=500 >= 300 (50% of 600) → pass
        result = svc.check_etf_guard(
            etf_amount=Decimal("100"),
            annual_savings=Decimal("600"),
            contract_days_remaining=200,
        )
        assert result.passed is True
        assert "covered" in result.reason.lower()

    def test_etf_exceeds_net_savings_fails(self):
        """ETF wipes out most of year-1 savings → fail."""
        svc = self._svc()
        # annual_savings=200, etf=180 → net=20 < 100 (50% of 200) → fail
        result = svc.check_etf_guard(
            etf_amount=Decimal("180"),
            annual_savings=Decimal("200"),
            contract_days_remaining=200,
        )
        assert result.passed is False
        assert "180.00" in result.reason
        assert "etf" in result.reason.lower()

    def test_zero_annual_savings_with_etf_fails(self):
        """Zero annual savings with any ETF → fail (threshold = 0, net < 0)."""
        svc = self._svc()
        result = svc.check_etf_guard(
            etf_amount=Decimal("50"),
            annual_savings=Decimal("0"),
            contract_days_remaining=200,
        )
        assert result.passed is False

    def test_etf_equals_half_annual_savings_passes(self):
        """ETF exactly at the threshold boundary (50% of annual) → passes (>= comparison).

        net = annual - etf = 600 - 300 = 300 = 50% of annual = threshold → pass.
        """
        svc = self._svc()
        result = svc.check_etf_guard(
            etf_amount=Decimal("300"),
            annual_savings=Decimal("600"),
            contract_days_remaining=200,
        )
        assert result.passed is True


# =============================================================================
# 5. check_rescission (4 tests)
# =============================================================================


class TestCheckRescission:
    async def test_no_record_passes(self):
        """No switch_executions row with rescission_ends → pass."""
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_db_result(None))
        svc = _make_service(db)
        result = await svc.check_rescission(USER_ID)
        assert result.passed is True

    async def test_rescission_active_fails(self):
        """rescission_ends > now → fail with days remaining."""
        future = datetime.now(UTC) + timedelta(days=7)
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=_make_db_result({"rescission_ends": future})
        )
        svc = _make_service(db)
        result = await svc.check_rescission(USER_ID)
        assert result.passed is False
        assert "rescission active" in result.reason.lower()
        assert "days remaining" in result.reason.lower()

    async def test_rescission_expired_passes(self):
        """rescission_ends <= now → rescission complete → pass."""
        past = datetime.now(UTC) - timedelta(days=1)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_db_result({"rescission_ends": past}))
        svc = _make_service(db)
        result = await svc.check_rescission(USER_ID)
        assert result.passed is True
        assert "complete" in result.reason.lower()

    async def test_rescission_ends_null_in_row_passes(self):
        """Row exists but rescission_ends is NULL → treated as no record → pass."""
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_db_result({"rescission_ends": None}))
        svc = _make_service(db)
        result = await svc.check_rescission(USER_ID)
        assert result.passed is True


# =============================================================================
# 6. run_all_safeguards (3 tests)
# =============================================================================


class TestRunAllSafeguards:
    """Integration-style tests for the orchestrating run_all_safeguards method."""

    def _make_clear_kill_switch_result(self) -> MagicMock:
        return _make_db_result(
            {
                "enabled": True,
                "loa_signed_at": datetime.now(UTC) - timedelta(days=30),
                "loa_revoked_at": None,
                "paused_until": None,
            }
        )

    def _make_no_switch_result(self) -> MagicMock:
        return _make_db_result(None)

    def _make_no_rescission_result(self) -> MagicMock:
        return _make_db_result(None)

    async def test_all_safeguards_pass(self):
        """All 5 safeguards pass → list contains 5 results, all passed=True."""
        db = AsyncMock()

        kill_switch_row = self._make_clear_kill_switch_result()
        # No previous switch → cooldown skips second DB call
        no_switch_row = self._make_no_switch_result()
        # No rescission record
        no_rescission_row = self._make_no_rescission_result()

        db.execute = AsyncMock(
            side_effect=[kill_switch_row, no_switch_row, no_rescission_row]
        )

        svc = _make_service(db)
        results = await svc.run_all_safeguards(
            user_id=USER_ID,
            monthly_savings=Decimal("25"),
            savings_pct=Decimal("20"),
            threshold_min=Decimal("10"),
            threshold_pct=Decimal("10"),
            etf_amount=Decimal("0"),
            annual_savings=Decimal("300"),
            contract_days_remaining=365,
        )

        assert len(results) == 5
        assert all(r.passed for r in results)

    async def test_first_check_fails_kill_switch_short_circuits(self):
        """Kill switch fails → only 1 result returned (short-circuit)."""
        db = AsyncMock()

        # Agent disabled
        disabled_row = _make_db_result(
            {
                "enabled": False,
                "loa_signed_at": datetime.now(UTC),
                "loa_revoked_at": None,
                "paused_until": None,
            }
        )
        db.execute = AsyncMock(return_value=disabled_row)

        svc = _make_service(db)
        results = await svc.run_all_safeguards(
            user_id=USER_ID,
            monthly_savings=Decimal("25"),
            savings_pct=Decimal("20"),
            threshold_min=Decimal("10"),
            threshold_pct=Decimal("10"),
            etf_amount=Decimal("0"),
            annual_savings=Decimal("300"),
            contract_days_remaining=365,
        )

        assert len(results) == 1
        assert results[0].passed is False
        assert "disabled" in results[0].reason.lower()

    async def test_middle_check_fails_savings_floor_short_circuits(self):
        """Kill switch + cooldown pass, savings floor fails → 3 results returned."""
        db = AsyncMock()

        kill_switch_row = self._make_clear_kill_switch_result()
        # No previous switch → cooldown passes with single DB call
        no_switch_row = self._make_no_switch_result()

        db.execute = AsyncMock(side_effect=[kill_switch_row, no_switch_row])

        svc = _make_service(db)
        results = await svc.run_all_safeguards(
            user_id=USER_ID,
            monthly_savings=Decimal("1"),  # below threshold
            savings_pct=Decimal("1"),  # below threshold
            threshold_min=Decimal("10"),
            threshold_pct=Decimal("10"),
            etf_amount=Decimal("0"),
            annual_savings=Decimal("12"),
            contract_days_remaining=365,
        )

        # Kill switch (pass), cooldown (pass), savings floor (fail) → 3 results
        assert len(results) == 3
        assert results[0].passed is True  # kill switch
        assert results[1].passed is True  # cooldown
        assert results[2].passed is False  # savings floor
        assert "below threshold" in results[2].reason.lower()
