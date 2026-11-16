"""
Tests for services.switch_context_builder.build_user_context.

The DB session is mocked and routes on the SQL text; the supplier-offers
repository is injected.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.supplier_offer import SupplierOffer
from services.switch_context_builder import (
    annotate_decision,
    build_user_context,
    market_data_is_estimate,
)
from services.switch_decision_engine import PlanDetails, SwitchDecisionEngine, UserContext

USER_ID = "11111111-1111-1111-1111-111111111111"
PLAN_ID = "22222222-2222-2222-2222-222222222222"

SETTINGS = {
    "enabled": True,
    "savings_threshold_pct": 12.5,
    "savings_threshold_min": 8,
    "cooldown_days": 7,
    "paused_until": None,
    "loa_signed_at": datetime(2026, 1, 1, tzinfo=UTC),
    "loa_revoked_at": None,
}

PLAN_ROW = {
    "id": PLAN_ID,
    "plan_name": "Standard Offer",
    "provider_name": "Incumbent Utility",
    "rate_kwh": "0.200000",
    "fixed_charge": "9.95",
    "term_months": 12,
    "etf_amount": "50.00",
    "contract_end": datetime(2027, 3, 1),  # naive, as some drivers return
}

USAGE_ROW = {
    "source": "arcadia",
    "interval_minutes": 60,
    "total_kwh": "2000",
    "first_reading": datetime(2026, 9, 1, tzinfo=UTC),
    "last_reading": datetime(2026, 10, 31, tzinfo=UTC),
}


def _result(*, first=None, all_=None) -> MagicMock:
    result = MagicMock()
    result.mappings.return_value.first.return_value = first
    result.mappings.return_value.all.return_value = all_ or []
    return result


def _make_db(*, plan=None, usage=None, executions=None, user=None, settings=None) -> AsyncMock:
    db = AsyncMock()

    async def _execute(statement, params=None):
        sql = str(statement)
        if "FROM public.user_plans" in sql:
            return _result(first=plan)
        if "FROM public.meter_readings" in sql:
            return _result(first=usage)
        if "FROM public.switch_executions" in sql:
            return _result(all_=executions)
        if "FROM public.users" in sql:
            return _result(first=user)
        if "FROM public.user_agent_settings" in sql:
            return _result(first=settings)
        raise AssertionError(f"unexpected SQL: {sql}")

    db.execute = AsyncMock(side_effect=_execute)
    return db


def _offer_repo(*offers: SupplierOffer) -> MagicMock:
    repo = MagicMock()
    repo.cheapest_available_by_supplier = AsyncMock(
        return_value={(o.supplier_id or o.supplier_name): o for o in offers}
    )
    return repo


def _real_offer(**overrides) -> SupplierOffer:
    values = {
        "supplier_name": "Cheaper Co",
        "supplier_id": "sup-1",
        "rate_per_kwh": 0.12,
        "source": "ct_rate_board",
        "source_ref": "offer-123",
        "standing_charge": 60.0,
        "intro_term_months": 12,
        "cancellation_fee": 25.0,
        "region": "us_ct",
    }
    values.update(overrides)
    return SupplierOffer(**values)


async def _build(db, repo, **kwargs):
    kwargs.setdefault("settings", SETTINGS)
    kwargs.setdefault("tier", "pro")
    kwargs.setdefault("region", "us_ct")
    return await build_user_context(db, USER_ID, offer_repo=repo, **kwargs)


class TestPlanPresent:
    @pytest.mark.asyncio
    async def test_full_context_is_built_from_db(self):
        db = _make_db(plan=PLAN_ROW, usage=USAGE_ROW)
        repo = _offer_repo(_real_offer())

        ctx = await _build(db, repo)

        # settings
        assert ctx.user_id == USER_ID
        assert ctx.tier == "pro"
        assert ctx.agent_enabled is True
        assert ctx.loa_signed is True and ctx.loa_revoked is False
        assert ctx.savings_threshold_pct == Decimal("12.5")
        assert ctx.savings_threshold_min == Decimal("8")
        assert ctx.cooldown_days == 7
        # current plan
        assert ctx.current_plan is not None
        assert ctx.current_plan.plan_id == PLAN_ID
        assert ctx.current_plan.rate_kwh == Decimal("0.200000")
        assert ctx.current_plan.fixed_charge == Decimal("9.95")
        assert ctx.current_plan.etf_amount == Decimal("50.00")
        assert ctx.current_plan.contract_end.tzinfo is not None
        # market plans, in the shape the engine documents
        repo.cheapest_available_by_supplier.assert_awaited_once_with("us_ct")
        assert ctx.available_plans == [
            {
                "id": "offer-123",
                "plan_name": "Cheaper Co (fixed)",
                "provider_name": "Cheaper Co",
                "rate_kwh": Decimal("0.12"),
                "fixed_charge": Decimal("5.00"),  # 60/yr -> monthly
                "term_months": 12,
                "etf_amount": Decimal("25.0"),
                "is_estimate": False,
                "source": "ct_rate_board",
                "enroll_url": None,
            }
        ]
        # usage: 2000 kWh over 60 days + 1h
        assert ctx.data_source == "arcadia_60min"
        assert ctx.months_of_data == 2
        assert Decimal("1013") < ctx.monthly_kwh < Decimal("1015")
        # no history
        assert ctx.pending_switch_exists is False
        assert ctx.last_switch_status is None
        assert ctx.last_switch_enacted_at is None
        assert ctx.rescission_ends is None

    @pytest.mark.asyncio
    async def test_engine_recommends_from_built_context(self):
        db = _make_db(plan=PLAN_ROW, usage=USAGE_ROW)
        ctx = await _build(db, _offer_repo(_real_offer()))

        decision = await SwitchDecisionEngine(db).evaluate(ctx)

        assert decision.action == "recommend"
        assert decision.proposed_plan.plan_id == "offer-123"
        assert decision.data_source == "arcadia_60min"

    @pytest.mark.asyncio
    async def test_estimate_offers_are_carried_through(self):
        db = _make_db(plan=PLAN_ROW, usage=USAGE_ROW)
        estimate = SupplierOffer(
            supplier_name="Some Supplier",
            supplier_id="sup-9",
            rate_per_kwh=0.12,
            source="regional_estimate",
            is_estimate=True,
            region="us_ct",
        )
        ctx = await _build(db, _offer_repo(estimate))

        assert market_data_is_estimate(ctx) is True
        assert ctx.available_plans[0]["is_estimate"] is True
        assert ctx.available_plans[0]["plan_name"] == "Some Supplier (regional estimate)"
        assert ctx.data_source == "arcadia_60min+market_estimate"

        decision = await SwitchDecisionEngine(db).evaluate(ctx)
        annotate_decision(decision, ctx)
        assert decision.data_source == "arcadia_60min+market_estimate"
        assert decision.confidence <= Decimal("0.40")
        # Estimates only -> hold with no proposed plan, saving kept as an estimate.
        assert decision.action == "hold"
        assert decision.proposed_plan is None
        assert decision.rule_stopped_at == "estimates_only"
        assert decision.reason.startswith("Only estimated regional rates are available")
        assert "Estimated potential saving versus the regional estimate" in decision.reason
        assert "Some Supplier" not in decision.reason
        assert decision.projected_savings_monthly > 0

    @pytest.mark.asyncio
    async def test_one_real_cheaper_offer_still_recommends(self):
        """A real offer beside an estimate is recommended exactly as before."""
        db = _make_db(plan=PLAN_ROW, usage=USAGE_ROW)
        estimate = SupplierOffer(
            supplier_name="Some Supplier",
            supplier_id="sup-9",
            rate_per_kwh=0.15,
            source="regional_estimate",
            is_estimate=True,
            region="us_ct",
        )
        ctx = await _build(db, _offer_repo(estimate, _real_offer()))
        assert market_data_is_estimate(ctx) is False

        decision = await SwitchDecisionEngine(db).evaluate(ctx)
        annotate_decision(decision, ctx)

        assert decision.action == "recommend"
        assert decision.proposed_plan.plan_id == "offer-123"
        assert decision.rule_stopped_at == "tier_gate"
        assert "Proposed:" in decision.reason
        assert "estimated" not in decision.reason.lower()


class TestEstimatesOnlyGuard:
    """annotate_decision on contexts whose market plans are all estimates."""

    @staticmethod
    def _ctx(**overrides) -> UserContext:
        base = {
            "user_id": USER_ID,
            "tier": "business",
            "agent_enabled": True,
            "loa_signed": True,
            "current_plan": PlanDetails(
                plan_id=PLAN_ID,
                plan_name="Standard Offer",
                provider_name="Incumbent Utility",
                rate_kwh=Decimal("0.20"),
            ),
            "available_plans": [
                {
                    "id": "est-1",
                    "plan_name": "Some Supplier (regional estimate)",
                    "provider_name": "Some Supplier",
                    "rate_kwh": Decimal("0.12"),
                    "is_estimate": True,
                }
            ],
            "monthly_kwh": Decimal("900"),
            "data_source": "arcadia_60min+market_estimate",
        }
        return UserContext(**{**base, **overrides})

    @pytest.mark.asyncio
    async def test_business_tier_switch_becomes_hold(self):
        ctx = self._ctx()
        decision = await SwitchDecisionEngine(MagicMock()).evaluate(ctx)
        assert decision.action == "switch"  # the engine itself is unchanged

        annotate_decision(decision, ctx)

        assert decision.action == "hold"
        assert decision.proposed_plan is None
        assert "Only estimated regional rates are available" in decision.reason
        assert "~$72.00/month" in decision.reason
        assert decision.projected_savings_monthly == Decimal("72.00")

    @pytest.mark.asyncio
    async def test_below_threshold_hold_drops_the_named_plan(self):
        # saving $0.80/month: under both the $10 floor and the 50% threshold
        ctx = self._ctx(monthly_kwh=Decimal("10"), savings_threshold_pct=Decimal("50"))
        decision = await SwitchDecisionEngine(MagicMock()).evaluate(ctx)
        assert decision.rule_stopped_at == "savings_floor"

        annotate_decision(decision, ctx)

        assert decision.action == "hold"
        assert decision.proposed_plan is None
        assert "Only estimated regional rates are available" in decision.reason
        assert "below threshold" in decision.reason

    @pytest.mark.asyncio
    async def test_kill_switch_hold_is_left_alone(self):
        ctx = self._ctx(agent_enabled=False)
        decision = await SwitchDecisionEngine(MagicMock()).evaluate(ctx)

        annotate_decision(decision, ctx)

        assert decision.reason == "Auto Rate Switcher is disabled."
        assert decision.rule_stopped_at == "kill_switch"

    @pytest.mark.asyncio
    async def test_loads_user_and_settings_when_not_supplied(self):
        db = _make_db(
            plan=PLAN_ROW,
            usage=USAGE_ROW,
            user={"subscription_tier": "business", "region": "us_tx"},
            settings=SETTINGS,
        )
        repo = _offer_repo()

        ctx = await build_user_context(db, USER_ID, offer_repo=repo)

        assert ctx.tier == "business"
        assert ctx.cooldown_days == 7
        repo.cheapest_available_by_supplier.assert_awaited_once_with("us_tx")


class TestPlanMissing:
    @pytest.mark.asyncio
    async def test_missing_data_is_left_empty_not_fabricated(self):
        db = _make_db(plan=None, usage=None)

        ctx = await _build(db, _offer_repo())

        assert ctx.current_plan is None
        assert ctx.available_plans == []
        assert ctx.monthly_kwh == Decimal("0")
        assert ctx.data_source == "none"
        assert ctx.months_of_data == 0
        assert market_data_is_estimate(ctx) is False

    @pytest.mark.asyncio
    async def test_plan_without_rate_is_not_usable(self):
        db = _make_db(plan={**PLAN_ROW, "rate_kwh": None}, usage=USAGE_ROW)

        ctx = await _build(db, _offer_repo(_real_offer()))

        assert ctx.current_plan is None

    @pytest.mark.asyncio
    async def test_no_region_means_no_market_lookup(self):
        db = _make_db(plan=PLAN_ROW, usage=USAGE_ROW)
        repo = _offer_repo(_real_offer())

        ctx = await _build(db, repo, region="")

        assert ctx.available_plans == []
        repo.cheapest_available_by_supplier.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_less_than_a_day_of_readings_is_not_extrapolated(self):
        start = datetime(2026, 10, 1, tzinfo=UTC)
        usage = {**USAGE_ROW, "first_reading": start, "last_reading": start + timedelta(hours=3)}
        db = _make_db(plan=PLAN_ROW, usage=usage)

        ctx = await _build(db, _offer_repo())

        assert ctx.monthly_kwh == Decimal("0")
        assert ctx.data_source == "none"

    @pytest.mark.asyncio
    async def test_db_errors_propagate(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("connection lost"))

        with pytest.raises(RuntimeError, match="connection lost"):
            await _build(db, _offer_repo())


class TestSwitchHistory:
    @pytest.mark.asyncio
    async def test_pending_execution_sets_pending_switch_exists(self):
        """pending_switch_exists was read by the engine but never assigned before."""
        executions = [{"status": "submitted", "enacted_at": None, "rescission_ends": None}]
        db = _make_db(plan=PLAN_ROW, usage=USAGE_ROW, executions=executions)

        ctx = await _build(db, _offer_repo(_real_offer()))

        assert ctx.pending_switch_exists is True
        assert ctx.last_switch_status == "submitted"

        decision = await SwitchDecisionEngine(db).evaluate(ctx)
        assert decision.action == "monitor"
        assert decision.rule_stopped_at == "cooldown"

    @pytest.mark.asyncio
    async def test_history_query_excludes_advisory_records(self):
        db = _make_db(plan=PLAN_ROW, usage=USAGE_ROW)

        await _build(db, _offer_repo())

        call = next(
            c for c in db.execute.call_args_list if "FROM public.switch_executions" in str(c[0][0])
        )
        assert "executor_type <> :advisory" in str(call[0][0])
        assert call[0][1] == {"user_id": USER_ID, "advisory": "advisory_only"}

    @pytest.mark.asyncio
    async def test_enacted_switch_populates_cooldown_and_rescission(self):
        enacted = datetime.now(UTC) - timedelta(days=1)
        rescission = datetime.now(UTC) + timedelta(days=2)
        executions = [
            {"status": "active", "enacted_at": enacted, "rescission_ends": rescission},
            {"status": "failed", "enacted_at": None, "rescission_ends": None},
        ]
        db = _make_db(plan=PLAN_ROW, usage=USAGE_ROW, executions=executions)

        ctx = await _build(db, _offer_repo(_real_offer()))

        assert ctx.pending_switch_exists is False
        assert ctx.last_switch_status == "active"
        assert ctx.last_switch_enacted_at == enacted
        assert ctx.rescission_ends == rescission
