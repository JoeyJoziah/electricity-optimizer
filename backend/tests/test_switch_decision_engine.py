"""
Tests for SwitchDecisionEngine

Covers all 7 rules in isolation plus full pipeline integration tests.
50 tests total, grouped by rule.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from services.switch_decision_engine import (
    PlanDetails,
    SwitchDecisionEngine,
    UserContext,
)

# =============================================================================
# Helpers
# =============================================================================


def _make_db() -> AsyncMock:
    """Return a minimal mock AsyncSession."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


def _make_engine() -> SwitchDecisionEngine:
    return SwitchDecisionEngine(_make_db())


def _now() -> datetime:
    return datetime.now(UTC)


def _current_plan(
    rate_kwh: str = "0.15",
    fixed_charge: str = "10.00",
    etf_amount: str = "0",
    contract_end: datetime | None = None,
) -> PlanDetails:
    return PlanDetails(
        plan_id="current-1",
        plan_name="Current Basic",
        provider_name="Grid Co",
        rate_kwh=Decimal(rate_kwh),
        fixed_charge=Decimal(fixed_charge),
        etf_amount=Decimal(etf_amount),
        contract_end=contract_end,
    )


def _available_plan(
    plan_id: str = "plan-A",
    rate_kwh: str = "0.10",
    fixed_charge: str = "10.00",
    etf_amount: str = "0",
) -> dict:
    return {
        "id": plan_id,
        "plan_name": "Better Plan",
        "provider_name": "Green Energy",
        "rate_kwh": rate_kwh,
        "fixed_charge": fixed_charge,
        "etf_amount": etf_amount,
    }


def _base_ctx(**overrides) -> UserContext:
    """Return a fully enabled UserContext that would pass all 7 rules."""
    ctx = UserContext(
        user_id="user-123",
        tier="business",
        agent_enabled=True,
        loa_signed=True,
        loa_revoked=False,
        paused_until=None,
        savings_threshold_pct=Decimal("5.0"),
        savings_threshold_min=Decimal("5.00"),
        cooldown_days=5,
        current_plan=_current_plan(),
        available_plans=[_available_plan()],
        last_switch_enacted_at=None,
        pending_switch_exists=False,
        rescission_ends=None,
        monthly_kwh=Decimal("800"),
        data_source="manual",
        months_of_data=6,
    )
    for key, value in overrides.items():
        setattr(ctx, key, value)
    return ctx


# =============================================================================
# Rule 1: Kill Switch — 8 tests
# =============================================================================


class TestKillSwitch:
    """Rule 1 — agent disabled / LOA absent or revoked / paused."""

    @pytest.mark.asyncio
    async def test_01_agent_disabled_returns_hold(self):
        """Agent disabled → HOLD immediately."""
        engine = _make_engine()
        ctx = _base_ctx(agent_enabled=False)

        decision = await engine.evaluate(ctx)

        assert decision.action == "hold"
        assert decision.rule_stopped_at == "kill_switch"

    @pytest.mark.asyncio
    async def test_02_loa_not_signed_returns_hold(self):
        """LOA not signed → HOLD."""
        engine = _make_engine()
        ctx = _base_ctx(loa_signed=False)

        decision = await engine.evaluate(ctx)

        assert decision.action == "hold"
        assert decision.rule_stopped_at == "kill_switch"

    @pytest.mark.asyncio
    async def test_03_loa_revoked_returns_hold(self):
        """LOA explicitly revoked → HOLD."""
        engine = _make_engine()
        ctx = _base_ctx(loa_revoked=True)

        decision = await engine.evaluate(ctx)

        assert decision.action == "hold"
        assert decision.rule_stopped_at == "kill_switch"

    @pytest.mark.asyncio
    async def test_04_agent_paused_returns_hold_with_days(self):
        """Agent paused until future date → HOLD with remaining days."""
        engine = _make_engine()
        paused_until = _now() + timedelta(days=3)
        ctx = _base_ctx(paused_until=paused_until)

        decision = await engine.evaluate(ctx)

        assert decision.action == "hold"
        assert decision.rule_stopped_at == "kill_switch"
        assert "3" in decision.reason or "2" in decision.reason  # timedelta day boundary

    @pytest.mark.asyncio
    async def test_05_fully_enabled_passes_rule_1(self):
        """Fully enabled agent passes kill switch (rule does not trigger)."""
        engine = _make_engine()
        ctx = _base_ctx()

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at != "kill_switch"

    @pytest.mark.asyncio
    async def test_06_pause_expired_passes_rule_1(self):
        """Pause that expired in the past does not block."""
        engine = _make_engine()
        expired_pause = _now() - timedelta(seconds=1)
        ctx = _base_ctx(paused_until=expired_pause)

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at != "kill_switch"

    @pytest.mark.asyncio
    async def test_07_disabled_reason_message(self):
        """Agent disabled reason message is user-friendly."""
        engine = _make_engine()
        ctx = _base_ctx(agent_enabled=False)

        decision = await engine.evaluate(ctx)

        assert "disabled" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_08_loa_revoked_reason_message(self):
        """LOA revoked reason references Letter of Authorization."""
        engine = _make_engine()
        ctx = _base_ctx(loa_revoked=True)

        decision = await engine.evaluate(ctx)

        assert "Letter of Authorization" in decision.reason or "LOA" in decision.reason


# =============================================================================
# Rule 2: Cooldown — 8 tests
# =============================================================================


class TestCooldown:
    """Rule 2 — pending switch / rescission / post-enactment cooldown."""

    @pytest.mark.asyncio
    async def test_09_pending_switch_returns_monitor(self):
        """Pending switch in flight → MONITOR."""
        engine = _make_engine()
        ctx = _base_ctx(pending_switch_exists=True)

        decision = await engine.evaluate(ctx)

        assert decision.action == "monitor"
        assert decision.rule_stopped_at == "cooldown"

    @pytest.mark.asyncio
    async def test_10_within_rescission_returns_hold(self):
        """Active rescission period → HOLD."""
        engine = _make_engine()
        ctx = _base_ctx(rescission_ends=_now() + timedelta(days=4))

        decision = await engine.evaluate(ctx)

        assert decision.action == "hold"
        assert decision.rule_stopped_at == "cooldown"

    @pytest.mark.asyncio
    async def test_11_within_cooldown_returns_monitor_with_days(self):
        """Post-enactment cooldown → MONITOR with days remaining."""
        engine = _make_engine()
        enacted_at = _now() - timedelta(days=2)
        ctx = _base_ctx(last_switch_enacted_at=enacted_at, cooldown_days=5)

        decision = await engine.evaluate(ctx)

        assert decision.action == "monitor"
        assert decision.rule_stopped_at == "cooldown"
        assert decision.cooldown_remaining_days >= 2  # 3 days remain (5 - 2)

    @pytest.mark.asyncio
    async def test_12_cooldown_expired_passes_rule_2(self):
        """Cooldown that has fully elapsed does not block."""
        engine = _make_engine()
        enacted_at = _now() - timedelta(days=10)
        ctx = _base_ctx(last_switch_enacted_at=enacted_at, cooldown_days=5)

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at != "cooldown"

    @pytest.mark.asyncio
    async def test_13_rescission_expired_passes_rule_2(self):
        """Rescission window that has closed does not block."""
        engine = _make_engine()
        ctx = _base_ctx(rescission_ends=_now() - timedelta(seconds=1))

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at != "cooldown"

    @pytest.mark.asyncio
    async def test_14_no_previous_switch_passes_rule_2(self):
        """No prior switch history passes Rule 2 cleanly."""
        engine = _make_engine()
        ctx = _base_ctx(
            last_switch_enacted_at=None,
            pending_switch_exists=False,
            rescission_ends=None,
        )

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at != "cooldown"

    @pytest.mark.asyncio
    async def test_15_cooldown_remaining_days_correct(self):
        """Cooldown remaining days is approximately correct."""
        engine = _make_engine()
        enacted_at = _now() - timedelta(days=2)
        ctx = _base_ctx(last_switch_enacted_at=enacted_at, cooldown_days=7)

        decision = await engine.evaluate(ctx)

        # 7 - 2 = 5 days remain (allow ±1 for day boundary)
        assert 4 <= decision.cooldown_remaining_days <= 5

    @pytest.mark.asyncio
    async def test_16_rescission_remaining_days_correct(self):
        """Rescission remaining days is approximately correct."""
        engine = _make_engine()
        ctx = _base_ctx(rescission_ends=_now() + timedelta(days=6))

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at == "cooldown"
        assert 5 <= decision.cooldown_remaining_days <= 6


# =============================================================================
# Rule 3: Plan Comparison — 8 tests
# =============================================================================


class TestPlanComparison:
    """Rule 3 — finding the best available plan."""

    @pytest.mark.asyncio
    async def test_17_no_current_plan_returns_hold(self):
        """No current plan data → HOLD via plan_comparison."""
        engine = _make_engine()
        ctx = _base_ctx(current_plan=None)

        decision = await engine.evaluate(ctx)

        assert decision.action == "hold"
        assert decision.rule_stopped_at == "plan_comparison"

    @pytest.mark.asyncio
    async def test_18_no_available_plans_returns_hold(self):
        """No market plans available → HOLD via plan_comparison."""
        engine = _make_engine()
        ctx = _base_ctx(available_plans=[])

        decision = await engine.evaluate(ctx)

        assert decision.action == "hold"
        assert decision.rule_stopped_at == "plan_comparison"

    @pytest.mark.asyncio
    async def test_19_all_plans_more_expensive_returns_hold(self):
        """All plans cost more than current → HOLD, no switch."""
        engine = _make_engine()
        # Current: $0.10/kWh + $0 fixed. Plans: $0.20/kWh — all worse.
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.10", fixed_charge="0"),
            available_plans=[
                _available_plan(rate_kwh="0.20"),
                _available_plan(plan_id="plan-B", rate_kwh="0.25"),
            ],
        )

        decision = await engine.evaluate(ctx)

        assert decision.action == "hold"
        assert decision.rule_stopped_at == "plan_comparison"

    @pytest.mark.asyncio
    async def test_20_better_plan_found_returns_plan_details(self):
        """When a better plan exists, proposed_plan is populated."""
        engine = _make_engine()
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0"),
            available_plans=[_available_plan(rate_kwh="0.12", fixed_charge="0")],
            monthly_kwh=Decimal("500"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.proposed_plan is not None
        assert decision.proposed_plan.plan_id == "plan-A"

    @pytest.mark.asyncio
    async def test_21_multiple_plans_selects_cheapest(self):
        """With multiple better plans, the engine selects the cheapest one."""
        engine = _make_engine()
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0"),
            available_plans=[
                _available_plan(plan_id="ok", rate_kwh="0.15"),
                _available_plan(plan_id="best", rate_kwh="0.09"),  # cheapest
                _available_plan(plan_id="mid", rate_kwh="0.12"),
            ],
            monthly_kwh=Decimal("500"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.proposed_plan is not None
        assert decision.proposed_plan.plan_id == "best"

    @pytest.mark.asyncio
    async def test_22_same_price_plan_is_not_a_switch(self):
        """Plan at identical cost to current is NOT selected (zero savings)."""
        engine = _make_engine()
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.15", fixed_charge="10"),
            available_plans=[
                _available_plan(rate_kwh="0.15", fixed_charge="10"),
            ],
        )

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at == "plan_comparison"

    @pytest.mark.asyncio
    async def test_23_lower_rate_but_higher_fixed_correct_math(self):
        """Lower per-kWh but higher fixed charge — net cost computed correctly."""
        engine = _make_engine()
        # Current: 800 kWh * $0.15 + $10 fixed = $130/month
        # Plan:    800 kWh * $0.10 + $50 fixed = $130/month  → zero savings
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.15", fixed_charge="10"),
            available_plans=[
                _available_plan(rate_kwh="0.10", fixed_charge="50"),
            ],
            monthly_kwh=Decimal("800"),
        )

        decision = await engine.evaluate(ctx)

        # Zero net savings → falls through to hold at plan_comparison
        assert decision.rule_stopped_at == "plan_comparison"

    @pytest.mark.asyncio
    async def test_24_annual_savings_is_monthly_times_12(self):
        """Annual savings is exactly monthly savings * 12."""
        engine = _make_engine()
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0"),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("100"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.projected_savings_annual == decision.projected_savings_monthly * 12


# =============================================================================
# Rule 4: Savings Floor — 7 tests
# =============================================================================


class TestSavingsFloor:
    """Rule 4 — minimum savings threshold (percentage OR absolute)."""

    @pytest.mark.asyncio
    async def test_25_savings_below_both_thresholds_returns_hold(self):
        """Savings below both pct and min → HOLD at savings_floor."""
        engine = _make_engine()
        # Current: 800 * $0.15 + $10 = $130. Plan: 800 * $0.148 + $10 = $128.40 → $1.60 savings
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.15", fixed_charge="10"),
            available_plans=[_available_plan(rate_kwh="0.148", fixed_charge="10")],
            monthly_kwh=Decimal("800"),
            savings_threshold_pct=Decimal("10.0"),
            savings_threshold_min=Decimal("10.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.action == "hold"
        assert decision.rule_stopped_at == "savings_floor"

    @pytest.mark.asyncio
    async def test_26_savings_above_pct_threshold_passes(self):
        """Savings above percentage threshold passes even if below absolute min."""
        engine = _make_engine()
        # Current: 100 * $0.20 + $0 = $20. Plan: $0.10 → $10 savings = 50%
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0"),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("100"),
            savings_threshold_pct=Decimal("30.0"),  # 50% > 30% — passes pct
            savings_threshold_min=Decimal("50.00"),  # $10 < $50 — fails abs
        )

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at != "savings_floor"

    @pytest.mark.asyncio
    async def test_27_savings_above_min_threshold_passes(self):
        """Savings above absolute minimum passes even if below pct threshold."""
        engine = _make_engine()
        # Current: 1000 * $0.20 + $0 = $200. Plan: $0.19 → $10 savings = 5%
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0"),
            available_plans=[_available_plan(rate_kwh="0.19", fixed_charge="0")],
            monthly_kwh=Decimal("1000"),
            savings_threshold_pct=Decimal("20.0"),  # 5% < 20% — fails pct
            savings_threshold_min=Decimal("8.00"),  # $10 > $8 — passes abs
        )

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at != "savings_floor"

    @pytest.mark.asyncio
    async def test_28_savings_above_both_thresholds_passes(self):
        """Savings above both thresholds continues to next rule."""
        engine = _make_engine()
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0"),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("1000"),
            savings_threshold_pct=Decimal("10.0"),
            savings_threshold_min=Decimal("10.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at != "savings_floor"

    @pytest.mark.asyncio
    async def test_29_savings_exactly_at_minimum_passes(self):
        """Savings precisely at minimum threshold edge case passes."""
        engine = _make_engine()
        # 1000 kWh * ($0.20 - $0.19) = $10.00 savings exactly
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0"),
            available_plans=[_available_plan(rate_kwh="0.19", fixed_charge="0")],
            monthly_kwh=Decimal("1000"),
            savings_threshold_pct=Decimal("99.0"),  # fails pct
            savings_threshold_min=Decimal("10.00"),  # exactly meets absolute
        )

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at != "savings_floor"

    @pytest.mark.asyncio
    async def test_30_custom_threshold_respected(self):
        """Custom high threshold blocks a low-savings plan."""
        engine = _make_engine()
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.15", fixed_charge="0"),
            available_plans=[_available_plan(rate_kwh="0.14", fixed_charge="0")],
            monthly_kwh=Decimal("500"),
            savings_threshold_pct=Decimal("50.0"),  # $5 savings / $75 = 6.7% — fails
            savings_threshold_min=Decimal("100.00"),  # $5 < $100 — fails
        )

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at == "savings_floor"

    @pytest.mark.asyncio
    async def test_31_zero_current_cost_edge_case(self):
        """When current cost is $0, percentage is 0% — only absolute threshold matters."""
        engine = _make_engine()
        # current_plan has rate=0 and fixed=0, plan saves $0 — no better plan found
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0", fixed_charge="0"),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("500"),
        )

        # All plans are MORE expensive than $0 → no better plan at comparison step
        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at == "plan_comparison"


# =============================================================================
# Rule 5: ETF Guard — 7 tests
# =============================================================================


class TestEtfGuard:
    """Rule 5 — early termination fee evaluation."""

    @pytest.mark.asyncio
    async def test_32_no_etf_passes(self):
        """Plan with no ETF passes Rule 5 without triggering it."""
        engine = _make_engine()
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0", etf_amount="0"),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("500"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at != "etf_guard"

    @pytest.mark.asyncio
    async def test_33_etf_but_net_savings_above_threshold_passes(self):
        """ETF present but year-1 net savings still above annual floor → passes."""
        engine = _make_engine()
        # Savings: 500 * ($0.20 - $0.10) = $50/month → $600/year
        # ETF: $100. Net year-1 = $500. Annual min = $5 * 12 = $60. $500 > $60 → passes.
        far_future = datetime.now(UTC) + timedelta(days=365)
        ctx = _base_ctx(
            current_plan=_current_plan(
                rate_kwh="0.20", fixed_charge="0", etf_amount="100", contract_end=far_future
            ),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("500"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("5.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at != "etf_guard"

    @pytest.mark.asyncio
    async def test_34_etf_negates_savings_returns_monitor(self):
        """ETF wipes out year-1 savings and no free window → MONITOR."""
        engine = _make_engine()
        # Savings: 100 * ($0.20 - $0.18) = $2/month → $24/year
        # ETF: $500. Net year-1 = -$476. Annual min = $10 * 12 = $120 → blocked.
        far_contract = datetime.now(UTC) + timedelta(days=300)
        ctx = _base_ctx(
            current_plan=_current_plan(
                rate_kwh="0.20", fixed_charge="0", etf_amount="500", contract_end=far_contract
            ),
            available_plans=[_available_plan(rate_kwh="0.18", fixed_charge="0")],
            monthly_kwh=Decimal("100"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("10.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.action == "monitor"
        assert decision.rule_stopped_at == "etf_guard"

    @pytest.mark.asyncio
    async def test_35_contract_expiring_within_45_days_passes_despite_etf(self):
        """Contract expiring within 45 days → free switch window, ETF guard lifted."""
        engine = _make_engine()
        soon = datetime.now(UTC) + timedelta(days=30)  # 30 days — in free window
        ctx = _base_ctx(
            current_plan=_current_plan(
                rate_kwh="0.20", fixed_charge="0", etf_amount="999", contract_end=soon
            ),
            available_plans=[_available_plan(rate_kwh="0.15", fixed_charge="0")],
            monthly_kwh=Decimal("200"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at != "etf_guard"

    @pytest.mark.asyncio
    async def test_36_contract_expiring_beyond_45_days_with_etf_returns_monitor(self):
        """Contract expiring in 60 days (outside free window) with ETF → MONITOR."""
        engine = _make_engine()
        later = datetime.now(UTC) + timedelta(days=60)  # outside free window
        ctx = _base_ctx(
            current_plan=_current_plan(
                rate_kwh="0.20", fixed_charge="0", etf_amount="999", contract_end=later
            ),
            available_plans=[_available_plan(rate_kwh="0.18", fixed_charge="0")],
            monthly_kwh=Decimal("100"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.action == "monitor"
        assert decision.rule_stopped_at == "etf_guard"

    @pytest.mark.asyncio
    async def test_37_zero_etf_passes(self):
        """ETF of exactly $0 passes Rule 5 (treated as no ETF)."""
        engine = _make_engine()
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0", etf_amount="0.00"),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("500"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at != "etf_guard"

    @pytest.mark.asyncio
    async def test_38_large_etf_large_savings_passes(self):
        """Large ETF but very large savings produces positive net → passes."""
        engine = _make_engine()
        # Savings: 10000 kWh * ($0.30 - $0.10) = $2000/month → $24000/year
        # ETF: $1000. Net year-1 = $23000 >> annual_min. Passes.
        far = datetime.now(UTC) + timedelta(days=730)
        ctx = _base_ctx(
            current_plan=_current_plan(
                rate_kwh="0.30", fixed_charge="0", etf_amount="1000", contract_end=far
            ),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("10000"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("5.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.rule_stopped_at != "etf_guard"


# =============================================================================
# Rule 6: Contract Window — 4 tests
# =============================================================================


class TestContractWindow:
    """Rule 6 — contract expiry within 45-day window (informational only)."""

    def _engine(self) -> SwitchDecisionEngine:
        return _make_engine()

    def test_39_no_contract_end_not_expiring(self):
        """No contract_end date → contract_expiring_soon is False."""
        engine = self._engine()
        current = _current_plan(contract_end=None)

        result = engine._check_contract_window(_base_ctx(current_plan=current))

        assert result is False

    def test_40_contract_ends_in_30_days_is_expiring(self):
        """Contract ending in 30 days → expiring soon."""
        engine = self._engine()
        current = _current_plan(contract_end=_now() + timedelta(days=30))

        result = engine._check_contract_window(_base_ctx(current_plan=current))

        assert result is True

    def test_41_contract_ends_in_60_days_not_expiring(self):
        """Contract ending in 60 days → not expiring soon."""
        engine = self._engine()
        current = _current_plan(contract_end=_now() + timedelta(days=60))

        result = engine._check_contract_window(_base_ctx(current_plan=current))

        assert result is False

    def test_42_contract_already_expired_not_expiring_soon(self):
        """Expired contract → not in the expiry-soon window."""
        engine = self._engine()
        current = _current_plan(contract_end=_now() - timedelta(days=1))

        result = engine._check_contract_window(_base_ctx(current_plan=current))

        assert result is False


# =============================================================================
# Rule 7: Tier Gate — 4 tests
# =============================================================================


class TestTierGate:
    """Rule 7 — action depends on subscription tier."""

    @pytest.mark.asyncio
    async def test_43_business_tier_action_is_switch(self):
        """Business tier → action == 'switch'."""
        engine = _make_engine()
        ctx = _base_ctx(
            tier="business",
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0"),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("500"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.action == "switch"
        assert decision.rule_stopped_at == "tier_gate"

    @pytest.mark.asyncio
    async def test_44_pro_tier_action_is_recommend(self):
        """Pro tier → action == 'recommend'."""
        engine = _make_engine()
        ctx = _base_ctx(
            tier="pro",
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0"),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("500"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.action == "recommend"
        assert decision.rule_stopped_at == "tier_gate"

    @pytest.mark.asyncio
    async def test_43b_switch_decision_has_plan_details(self):
        """Switch decision carries proposed_plan and current_plan."""
        engine = _make_engine()
        ctx = _base_ctx(
            tier="business",
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0"),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("500"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.current_plan is not None
        assert decision.proposed_plan is not None

    @pytest.mark.asyncio
    async def test_44b_recommend_carries_savings_data(self):
        """Recommend decision carries monthly and annual savings."""
        engine = _make_engine()
        ctx = _base_ctx(
            tier="pro",
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0"),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("500"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
        )

        decision = await engine.evaluate(ctx)

        # 500 * ($0.20 - $0.10) = $50/month savings
        assert decision.projected_savings_monthly == Decimal("50.00")
        assert decision.projected_savings_annual == Decimal("600.00")


# =============================================================================
# Full Pipeline — 9 tests
# =============================================================================


class TestFullPipeline:
    """End-to-end pipeline tests covering combinations of rules."""

    @pytest.mark.asyncio
    async def test_45_business_happy_path_returns_switch(self):
        """Business tier with a good plan and no blockers → switch."""
        engine = _make_engine()
        ctx = _base_ctx(tier="business")

        decision = await engine.evaluate(ctx)

        assert decision.action == "switch"
        assert decision.proposed_plan is not None
        assert decision.projected_savings_monthly > 0
        assert decision.rule_stopped_at == "tier_gate"

    @pytest.mark.asyncio
    async def test_46_pro_happy_path_returns_recommend(self):
        """Pro tier with a good plan and no blockers → recommend."""
        engine = _make_engine()
        ctx = _base_ctx(tier="pro")

        decision = await engine.evaluate(ctx)

        assert decision.action == "recommend"
        assert decision.rule_stopped_at == "tier_gate"

    @pytest.mark.asyncio
    async def test_47_no_data_agent_enabled_returns_hold(self):
        """Agent enabled but no current plan → hold at plan_comparison."""
        engine = _make_engine()
        ctx = _base_ctx(current_plan=None)

        decision = await engine.evaluate(ctx)

        assert decision.action == "hold"
        assert decision.rule_stopped_at == "plan_comparison"

    @pytest.mark.asyncio
    async def test_48_expired_plan_zero_etf_good_savings_returns_switch(self):
        """Plan with expired contract, zero ETF, and good savings → switch."""
        engine = _make_engine()
        expired = _now() - timedelta(days=30)
        ctx = _base_ctx(
            tier="business",
            current_plan=_current_plan(
                rate_kwh="0.20", fixed_charge="0", etf_amount="0", contract_end=expired
            ),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("500"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.action == "switch"

    @pytest.mark.asyncio
    async def test_49_cooldown_active_returns_monitor(self):
        """Active cooldown stops evaluation at rule 2 → monitor."""
        engine = _make_engine()
        ctx = _base_ctx(
            last_switch_enacted_at=_now() - timedelta(days=1),
            cooldown_days=5,
        )

        decision = await engine.evaluate(ctx)

        assert decision.action == "monitor"
        assert decision.rule_stopped_at == "cooldown"

    @pytest.mark.asyncio
    async def test_50_multiple_plans_picks_best_savings(self):
        """Full pipeline with 3 available plans selects the one with max savings."""
        engine = _make_engine()
        ctx = _base_ctx(
            tier="business",
            current_plan=_current_plan(rate_kwh="0.25", fixed_charge="0"),
            available_plans=[
                _available_plan(plan_id="ok", rate_kwh="0.20"),
                _available_plan(plan_id="best", rate_kwh="0.08"),  # highest savings
                _available_plan(plan_id="mid", rate_kwh="0.15"),
            ],
            monthly_kwh=Decimal("1000"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.action == "switch"
        assert decision.proposed_plan is not None
        assert decision.proposed_plan.plan_id == "best"

    @pytest.mark.asyncio
    async def test_51_confidence_from_arcadia_data(self):
        """High-quality Arcadia interval data produces high confidence."""
        engine = _make_engine()
        ctx = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0"),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("500"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
            data_source="arcadia_15min",
            months_of_data=12,
        )

        decision = await engine.evaluate(ctx)

        # arcadia_15min base = 0.95, full months_factor → confidence near 0.95
        assert decision.confidence >= Decimal("0.90")

    @pytest.mark.asyncio
    async def test_52_manual_data_produces_lower_confidence(self):
        """Manual data source produces lower confidence than interval data."""
        engine_manual = _make_engine()
        engine_arcadia = _make_engine()

        ctx_manual = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0"),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("500"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
            data_source="manual",
            months_of_data=6,
        )
        ctx_arcadia = _base_ctx(
            current_plan=_current_plan(rate_kwh="0.20", fixed_charge="0"),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("500"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
            data_source="arcadia_15min",
            months_of_data=6,
        )

        d_manual = await engine_manual.evaluate(ctx_manual)
        d_arcadia = await engine_arcadia.evaluate(ctx_arcadia)

        assert d_manual.confidence < d_arcadia.confidence

    @pytest.mark.asyncio
    async def test_53_contract_expiring_flag_set_in_switch_decision(self):
        """When contract expiring within 45 days, flag is set on the decision."""
        engine = _make_engine()
        soon = _now() + timedelta(days=20)
        ctx = _base_ctx(
            tier="business",
            current_plan=_current_plan(
                rate_kwh="0.20", fixed_charge="0", etf_amount="0", contract_end=soon
            ),
            available_plans=[_available_plan(rate_kwh="0.10", fixed_charge="0")],
            monthly_kwh=Decimal("500"),
            savings_threshold_pct=Decimal("1.0"),
            savings_threshold_min=Decimal("1.00"),
        )

        decision = await engine.evaluate(ctx)

        assert decision.contract_expiring_soon is True
        assert decision.action == "switch"
