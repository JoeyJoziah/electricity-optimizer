"""
Switch Decision Engine — The Brain

Evaluates 7 rules in strict order to produce a SwitchDecision.
Accepts data from any source (Arcadia, UtilityAPI, bills, manual) with confidence scoring.

Rules:
1. Kill switch check
2. Cooldown check
3. Plan comparison (via PlanScorer)
4. Savings floor
5. ETF guard
6. Contract window
7. Tier gate
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from lib.tracing import traced

logger = structlog.get_logger(__name__)


@dataclass
class PlanDetails:
    """Details about a plan (current or proposed).

    Attributes:
        plan_id: Unique identifier for the plan.
        plan_name: Human-readable plan name.
        provider_name: Name of the electricity provider.
        rate_kwh: Per-kWh supply charge in dollars.
        fixed_charge: Monthly fixed/service charge in dollars.
        term_months: Contract term length in months, or None for month-to-month.
        etf_amount: Early termination fee in dollars (0 if no ETF).
        contract_end: Date the current contract expires, or None if unknown.
    """

    plan_id: str
    plan_name: str
    provider_name: str
    rate_kwh: Decimal
    fixed_charge: Decimal = Decimal("0")
    term_months: int | None = None
    etf_amount: Decimal = Decimal("0")
    contract_end: datetime | None = None


@dataclass
class SwitchDecision:
    """Result of the decision engine evaluation.

    Attributes:
        action: What the engine recommends:
            - ``switch``: Business tier — initiate switch automatically.
            - ``recommend``: Pro tier — present as a recommendation.
            - ``hold``: No action; savings insufficient or agent disabled.
            - ``monitor``: Interesting opportunity blocked by cooldown/ETF;
              re-evaluate next cycle.
        reason: Human-readable explanation of the decision.
        current_plan: The user's active plan at decision time, if known.
        proposed_plan: The best plan found, if any better plan exists.
        projected_savings_monthly: Estimated monthly savings in dollars.
        projected_savings_annual: Estimated annual savings (monthly * 12).
        etf_cost: ETF that would be incurred by switching now.
        net_savings_year1: Annual savings minus ETF (year-1 net).
        confidence: Scoring confidence between 0 and 1.
        cooldown_remaining_days: Days until cooldown/rescission expires (0 if none).
        contract_days_remaining: Days until current contract expires (0 if none/unknown).
        data_source: Origin of usage data that drove the decision.
        rule_stopped_at: Which rule produced this decision.
        contract_expiring_soon: True if current contract expires within 45 days.
    """

    action: Literal["switch", "recommend", "hold", "monitor"]
    reason: str
    current_plan: PlanDetails | None = None
    proposed_plan: PlanDetails | None = None
    projected_savings_monthly: Decimal = Decimal("0")
    projected_savings_annual: Decimal = Decimal("0")
    etf_cost: Decimal = Decimal("0")
    net_savings_year1: Decimal = Decimal("0")
    confidence: Decimal = Decimal("0")
    cooldown_remaining_days: int = 0
    contract_days_remaining: int = 0
    data_source: str = "unknown"
    rule_stopped_at: str = ""
    contract_expiring_soon: bool = False


@dataclass
class UserContext:
    """All data needed to evaluate the 7 rules.

    Attributes:
        user_id: The user's UUID string.
        tier: Subscription tier — ``"pro"`` or ``"business"``.
        agent_enabled: Whether the auto-switcher is turned on.
        loa_signed: Whether the user has an active Letter of Authorization.
        loa_revoked: Whether a previously-signed LOA was explicitly revoked.
        paused_until: If set and in the future, the engine is paused until this
            UTC datetime.
        savings_threshold_pct: Minimum savings percentage required (default 10%).
        savings_threshold_min: Minimum absolute savings in dollars/month required
            (default $10). The savings floor passes if EITHER threshold is met.
        cooldown_days: Post-switch cooldown period in days (default 5).
        current_plan: The user's current active plan, if known.
        available_plans: Raw plan dicts from the market data layer. Each dict must
            contain at minimum: ``id``, ``plan_name``, ``provider_name``,
            ``rate_kwh``. Optional keys: ``fixed_charge``, ``term_months``,
            ``etf_amount``.
        last_switch_enacted_at: UTC datetime when the most recent switch was
            enacted, if any.
        last_switch_status: Status string of the most recent switch record
            (e.g. ``"initiating"``, ``"active"``).
        pending_switch_exists: True if there is an in-flight switch in a
            pre-active state.
        rescission_ends: UTC datetime when the rescission window closes, or None.
        monthly_kwh: Average monthly usage in kWh.
        peak_kwh_pct: Fraction of usage in peak hours (0–1).
        off_peak_kwh_pct: Fraction of usage in off-peak hours (0–1).
        data_source: Origin of usage data. Drives confidence scoring. One of:
            ``arcadia_15min``, ``arcadia_60min``, ``utilityapi_15min``,
            ``utilityapi_60min``, ``bills``, ``portal``, ``manual``.
        months_of_data: Number of full billing months represented in the profile.
    """

    user_id: str
    tier: str
    agent_enabled: bool = False
    loa_signed: bool = False
    loa_revoked: bool = False
    paused_until: datetime | None = None
    savings_threshold_pct: Decimal = Decimal("10.0")
    savings_threshold_min: Decimal = Decimal("10.0")
    cooldown_days: int = 5
    current_plan: PlanDetails | None = None
    available_plans: list[dict[str, Any]] = field(default_factory=list)
    last_switch_enacted_at: datetime | None = None
    last_switch_status: str | None = None
    pending_switch_exists: bool = False
    rescission_ends: datetime | None = None
    monthly_kwh: Decimal = Decimal("0")
    peak_kwh_pct: Decimal = Decimal("0.40")
    off_peak_kwh_pct: Decimal = Decimal("0.60")
    data_source: str = "manual"
    months_of_data: int = 1


class SwitchDecisionEngine:
    """Evaluates 7 rules in order to produce a SwitchDecision.

    Rules are evaluated in strict sequence. The first rule that triggers
    returns immediately — subsequent rules are not evaluated.

    Args:
        db: An async SQLAlchemy session. Currently reserved for future use
            (e.g. fetching plan data directly). Pass the request-scoped
            session for consistency with other services.

    Example:
        engine = SwitchDecisionEngine(db)
        decision = await engine.evaluate(ctx)
        if decision.action == "switch":
            await switch_service.initiate(ctx.user_id, decision.proposed_plan)
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def evaluate(self, ctx: UserContext) -> SwitchDecision:
        """Run all 7 rules in order. First rule that triggers stops evaluation.

        Args:
            ctx: Fully populated UserContext for the user being evaluated.

        Returns:
            A SwitchDecision with action, reason, and supporting financial data.
        """
        async with traced(
            "decision_engine.evaluate",
            attributes={
                "decision.user_id": ctx.user_id,
                "decision.tier": ctx.tier,
                "decision.data_source": ctx.data_source,
                "decision.monthly_kwh": float(ctx.monthly_kwh),
            },
        ):
            # Rule 1: Kill switch
            decision = self._check_kill_switch(ctx)
            if decision:
                logger.info(
                    "decision_engine.kill_switch",
                    user_id=ctx.user_id,
                    reason=decision.reason,
                )
                return decision

            # Rule 2: Cooldown
            decision = self._check_cooldown(ctx)
            if decision:
                logger.info(
                    "decision_engine.cooldown",
                    user_id=ctx.user_id,
                    action=decision.action,
                    cooldown_remaining_days=decision.cooldown_remaining_days,
                )
                return decision

            # Rule 3: Plan comparison
            best_plan, savings = self._compare_plans(ctx)
            if best_plan is None:
                logger.info(
                    "decision_engine.no_better_plan",
                    user_id=ctx.user_id,
                    available_plans=len(ctx.available_plans),
                )
                return SwitchDecision(
                    action="hold",
                    reason="No better plan found — your current plan is the best available deal.",
                    current_plan=ctx.current_plan,
                    data_source=ctx.data_source,
                    confidence=self._get_confidence(ctx),
                    rule_stopped_at="plan_comparison",
                )

            # Rule 4: Savings floor
            decision = self._check_savings_floor(ctx, best_plan, savings)
            if decision:
                logger.info(
                    "decision_engine.savings_floor",
                    user_id=ctx.user_id,
                    monthly_savings=str(savings["monthly"]),
                    reason=decision.reason,
                )
                return decision

            # Rule 5: ETF guard
            decision = self._check_etf_guard(ctx, best_plan, savings)
            if decision:
                logger.info(
                    "decision_engine.etf_guard",
                    user_id=ctx.user_id,
                    etf=str(ctx.current_plan.etf_amount if ctx.current_plan else 0),
                    reason=decision.reason,
                )
                return decision

            # Rule 6: Contract window — informational only, does not stop evaluation
            contract_expiring_soon = self._check_contract_window(ctx)

            # Rule 7: Tier gate — determines action
            action: Literal["switch", "recommend"] = (
                "switch" if ctx.tier == "business" else "recommend"
            )

            etf = ctx.current_plan.etf_amount if ctx.current_plan else Decimal("0")
            net_year1 = savings["annual"] - etf
            contract_days = 0
            if ctx.current_plan and ctx.current_plan.contract_end:
                delta = ctx.current_plan.contract_end - datetime.now(UTC)
                contract_days = max(0, delta.days)

            logger.info(
                "decision_engine.decision",
                user_id=ctx.user_id,
                action=action,
                monthly_savings=str(savings["monthly"]),
                annual_savings=str(savings["annual"]),
                proposed_plan_id=best_plan.plan_id,
                contract_expiring_soon=contract_expiring_soon,
            )

            return SwitchDecision(
                action=action,
                reason=f"Found a better plan saving ~${savings['monthly']:.2f}/month.",
                current_plan=ctx.current_plan,
                proposed_plan=best_plan,
                projected_savings_monthly=savings["monthly"],
                projected_savings_annual=savings["annual"],
                etf_cost=etf,
                net_savings_year1=net_year1,
                confidence=self._get_confidence(ctx),
                contract_days_remaining=contract_days,
                data_source=ctx.data_source,
                rule_stopped_at="tier_gate",
                contract_expiring_soon=contract_expiring_soon,
            )

    # -------------------------------------------------------------------------
    # Rule implementations
    # -------------------------------------------------------------------------

    def _check_kill_switch(self, ctx: UserContext) -> SwitchDecision | None:
        """Rule 1: Is the agent disabled, LOA absent/revoked, or paused?

        Args:
            ctx: User context.

        Returns:
            A HOLD SwitchDecision if any kill condition is active, else None.
        """
        if not ctx.agent_enabled:
            return SwitchDecision(
                action="hold",
                reason="Auto Rate Switcher is disabled.",
                current_plan=ctx.current_plan,
                rule_stopped_at="kill_switch",
                data_source=ctx.data_source,
            )

        if ctx.loa_revoked or not ctx.loa_signed:
            return SwitchDecision(
                action="hold",
                reason=(
                    "Letter of Authorization is not active. Please sign LOA to enable switching."
                ),
                current_plan=ctx.current_plan,
                rule_stopped_at="kill_switch",
                data_source=ctx.data_source,
            )

        if ctx.paused_until and ctx.paused_until > datetime.now(UTC):
            days_left = (ctx.paused_until - datetime.now(UTC)).days
            return SwitchDecision(
                action="hold",
                reason=f"Auto Rate Switcher is paused for {days_left} more days.",
                current_plan=ctx.current_plan,
                rule_stopped_at="kill_switch",
                data_source=ctx.data_source,
            )

        return None

    def _check_cooldown(self, ctx: UserContext) -> SwitchDecision | None:
        """Rule 2: Is there a pending switch, active rescission period, or cooldown?

        Cooldown priority:
        1. Pending switch (in-flight) → MONITOR
        2. Rescission period active → HOLD (legally cannot switch back yet)
        3. Post-enactment cooldown → MONITOR

        Args:
            ctx: User context.

        Returns:
            A MONITOR or HOLD SwitchDecision if a cooldown condition is active,
            else None.
        """
        now = datetime.now(UTC)

        # A switch is in-flight — wait for it to complete
        if ctx.pending_switch_exists:
            return SwitchDecision(
                action="monitor",
                reason="A switch is currently pending. Waiting for confirmation.",
                current_plan=ctx.current_plan,
                rule_stopped_at="cooldown",
                data_source=ctx.data_source,
            )

        # Within rescission period — hold hard
        if ctx.rescission_ends and ctx.rescission_ends > now:
            days_left = (ctx.rescission_ends - now).days
            return SwitchDecision(
                action="hold",
                reason=(
                    f"Within rescission period of last switch "
                    f"({days_left} days remaining). No switching allowed."
                ),
                current_plan=ctx.current_plan,
                cooldown_remaining_days=days_left,
                rule_stopped_at="cooldown",
                data_source=ctx.data_source,
            )

        # Post-enactment cooldown
        if ctx.last_switch_enacted_at:
            cooldown_end = ctx.last_switch_enacted_at + timedelta(
                days=ctx.cooldown_days
            )
            if cooldown_end > now:
                days_left = (cooldown_end - now).days
                return SwitchDecision(
                    action="monitor",
                    reason=(
                        f"Cooldown active ({days_left} days remaining). "
                        "Monitoring for opportunities."
                    ),
                    current_plan=ctx.current_plan,
                    cooldown_remaining_days=days_left,
                    rule_stopped_at="cooldown",
                    data_source=ctx.data_source,
                )

        return None

    def _compare_plans(
        self, ctx: UserContext
    ) -> tuple[PlanDetails | None, dict[str, Decimal]]:
        """Rule 3: Find the best available plan by projected monthly cost.

        Compares each available plan against the current plan using the user's
        monthly kWh and fixed charges. Selects the plan with the highest
        absolute monthly savings.

        Args:
            ctx: User context with current_plan, available_plans, and monthly_kwh.

        Returns:
            Tuple of (best_plan_or_None, savings_dict). The savings dict contains
            ``monthly`` and ``annual`` Decimal values. Returns (None, zero_savings)
            if no better plan is found or required data is missing.
        """
        _zero = {"monthly": Decimal("0"), "annual": Decimal("0")}

        if not ctx.current_plan:
            return None, _zero

        if not ctx.available_plans:
            return None, _zero

        current_monthly = ctx.monthly_kwh * (
            ctx.current_plan.rate_kwh or Decimal("0")
        ) + (ctx.current_plan.fixed_charge or Decimal("0"))

        best_plan: PlanDetails | None = None
        best_savings = Decimal("0")

        for plan_data in ctx.available_plans:
            plan_rate = Decimal(str(plan_data.get("rate_kwh", 0)))
            plan_fixed = Decimal(str(plan_data.get("fixed_charge", 0)))
            plan_monthly = ctx.monthly_kwh * plan_rate + plan_fixed
            savings = current_monthly - plan_monthly

            if savings > best_savings:
                best_savings = savings
                best_plan = PlanDetails(
                    plan_id=str(plan_data.get("id", "")),
                    plan_name=plan_data.get("plan_name", "Unknown"),
                    provider_name=plan_data.get("provider_name", "Unknown"),
                    rate_kwh=plan_rate,
                    fixed_charge=plan_fixed,
                    term_months=plan_data.get("term_months"),
                    etf_amount=Decimal(str(plan_data.get("etf_amount", 0))),
                )

        if best_plan is None or best_savings <= 0:
            return None, _zero

        return best_plan, {
            "monthly": best_savings.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "annual": (best_savings * 12).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
        }

    def _check_savings_floor(
        self,
        ctx: UserContext,
        best_plan: PlanDetails,
        savings: dict[str, Decimal],
    ) -> SwitchDecision | None:
        """Rule 4: Do savings meet the user's configured threshold?

        The savings floor is a logical OR:
        - Savings percentage >= savings_threshold_pct, OR
        - Absolute monthly savings >= savings_threshold_min

        Either condition passing allows the evaluation to continue.

        Args:
            ctx: User context with threshold settings.
            best_plan: Best plan found in Rule 3.
            savings: Monthly and annual savings dict from Rule 3.

        Returns:
            A HOLD SwitchDecision if savings fall below both thresholds,
            else None.
        """
        current_monthly = Decimal("0")
        if ctx.current_plan:
            current_monthly = ctx.monthly_kwh * (
                ctx.current_plan.rate_kwh or Decimal("0")
            ) + (ctx.current_plan.fixed_charge or Decimal("0"))

        if current_monthly > 0:
            savings_pct = (savings["monthly"] / current_monthly * 100).quantize(
                Decimal("0.01")
            )
        else:
            savings_pct = Decimal("0")

        pct_passes = savings_pct >= ctx.savings_threshold_pct
        min_passes = savings["monthly"] >= ctx.savings_threshold_min

        if pct_passes or min_passes:
            return None  # At least one threshold met — proceed

        etf = ctx.current_plan.etf_amount if ctx.current_plan else Decimal("0")
        return SwitchDecision(
            action="hold",
            reason=(
                f"Savings of ${savings['monthly']:.2f}/month ({savings_pct}%) "
                f"below threshold "
                f"(${ctx.savings_threshold_min}/month or {ctx.savings_threshold_pct}%)."
            ),
            current_plan=ctx.current_plan,
            proposed_plan=best_plan,
            projected_savings_monthly=savings["monthly"],
            projected_savings_annual=savings["annual"],
            etf_cost=etf,
            net_savings_year1=savings["annual"] - etf,
            confidence=self._get_confidence(ctx),
            rule_stopped_at="savings_floor",
            data_source=ctx.data_source,
        )

    def _check_etf_guard(
        self,
        ctx: UserContext,
        best_plan: PlanDetails,
        savings: dict[str, Decimal],
    ) -> SwitchDecision | None:
        """Rule 5: Does the ETF negate the year-1 savings?

        If the current plan has an ETF, the engine checks whether year-1 net
        savings (annual savings minus ETF) still exceed the annual floor. If
        not, the engine enters MONITOR mode — unless the contract is expiring
        within 45 days (the "free switch window"), in which case the ETF
        block is lifted and evaluation continues.

        Args:
            ctx: User context.
            best_plan: Best plan from Rule 3.
            savings: Monthly and annual savings from Rule 3.

        Returns:
            A MONITOR SwitchDecision if ETF negates savings and no free-switch
            window is imminent, else None.
        """
        etf = ctx.current_plan.etf_amount if ctx.current_plan else Decimal("0")

        if etf <= 0:
            return None  # No ETF — no guard needed

        net_year1 = savings["annual"] - etf
        annual_threshold = ctx.savings_threshold_min * 12

        if net_year1 >= annual_threshold:
            return None  # ETF present but year-1 still profitable

        # Check for free switch window
        contract_days = 0
        if ctx.current_plan and ctx.current_plan.contract_end:
            delta = ctx.current_plan.contract_end - datetime.now(UTC)
            contract_days = max(0, delta.days)

        if contract_days <= 45:
            # Contract expiring soon — switch window is open, don't block
            return None

        return SwitchDecision(
            action="monitor",
            reason=(
                f"ETF of ${etf:.2f} reduces year-1 savings to ${net_year1:.2f}. "
                f"Monitoring until contract expires in {contract_days} days."
            ),
            current_plan=ctx.current_plan,
            proposed_plan=best_plan,
            projected_savings_monthly=savings["monthly"],
            projected_savings_annual=savings["annual"],
            etf_cost=etf,
            net_savings_year1=net_year1,
            confidence=self._get_confidence(ctx),
            contract_days_remaining=contract_days,
            rule_stopped_at="etf_guard",
            data_source=ctx.data_source,
        )

    def _check_contract_window(self, ctx: UserContext) -> bool:
        """Rule 6: Is the current contract expiring within 45 days?

        This rule is informational — it does not stop evaluation. When True,
        the decision carries ``contract_expiring_soon=True`` to signal that
        priority should be elevated.

        Args:
            ctx: User context.

        Returns:
            True if the current contract ends within 45 days, False otherwise.
        """
        if not ctx.current_plan or not ctx.current_plan.contract_end:
            return False
        delta = ctx.current_plan.contract_end - datetime.now(UTC)
        return 0 < delta.days <= 45

    def _get_confidence(self, ctx: UserContext) -> Decimal:
        """Calculate decision confidence based on data source and volume.

        Delegates to the DATA_SOURCE_CONFIDENCE table from PlanScorer.
        Formula mirrors PlanScorer._calc_confidence:
            confidence = base * (0.7 + 0.3 * min(months / 6, 1.0))

        Args:
            ctx: User context.

        Returns:
            Confidence value between 0 and 1, rounded to 2 decimal places.
        """
        from services.plan_scorer import DATA_SOURCE_CONFIDENCE

        base = DATA_SOURCE_CONFIDENCE.get(ctx.data_source, Decimal("0.40"))
        months_factor = min(
            Decimal(str(ctx.months_of_data)) / Decimal("6"),
            Decimal("1.0"),
        )
        confidence = base * (Decimal("0.7") + Decimal("0.3") * months_factor)
        confidence = min(confidence, Decimal("1.0"))
        return confidence.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
