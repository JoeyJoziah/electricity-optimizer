"""
Switch Context Builder

Builds a complete ``UserContext`` for the auto rate switcher decision engine
from the database: the user's current plan (``user_plans``), market plans for
their region (vendor-neutral supplier-offers layer), usage (``meter_readings``)
and switch history (``switch_executions``).

Rules:
- Missing data stays missing. No plan, no offers or no usage leaves the
  corresponding field empty — nothing is fabricated or defaulted to look real.
- Estimated market data is labelled. When every market plan is a regional
  estimate (``SupplierOffer.is_estimate``) the context's ``data_source`` gets
  the ``+market_estimate`` suffix, so the decision carries it into the audit
  log and the engine falls back to its lowest base confidence.
- Estimates never name a supplier. With estimates only, every supplier carries
  the same regional rate, so ``annotate_decision`` turns any comparison
  outcome into a ``hold`` with no proposed plan (see there).
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.supplier_offer_repository import SupplierOfferRepository
from services.switch_decision_engine import PlanDetails, SwitchDecision, UserContext

logger = structlog.get_logger(__name__)

# Execution statuses that mean a real switch is still in flight.
PENDING_EXECUTION_STATUSES = ("initiating", "initiated", "submitted", "accepted")

# Executions recorded by the advisory executor are recommendations, not
# switches: they never count as pending, enacted or in rescission.
ADVISORY_EXECUTOR_TYPE = "advisory_only"

# data_source used when the user has no usable meter readings.
NO_USAGE_DATA_SOURCE = "none"

# Appended to data_source when the market plans are regional estimates.
MARKET_ESTIMATE_SUFFIX = "+market_estimate"

# Reason used when a comparison rests only on regional estimates. Every
# supplier then carries the same estimated rate, so naming one would be
# arbitrary: the decision is always a hold with no proposed plan.
ESTIMATES_ONLY_REASON = (
    "Only estimated regional rates are available for your area, so no specific "
    "supplier or plan is recommended."
)

# rule_stopped_at value for a decision replaced by the estimates-only hold.
ESTIMATES_ONLY_RULE = "estimates_only"

_ADVISE_ACTIONS = ("recommend", "switch")

_DAYS_PER_MONTH = Decimal("30.4375")
_INTERVAL_SOURCES = ("arcadia", "utilityapi")


def market_data_is_estimate(ctx: UserContext) -> bool:
    """True when the context has market plans and all of them are estimates."""
    return bool(ctx.available_plans) and all(
        plan.get("is_estimate") for plan in ctx.available_plans
    )


def annotate_decision(decision: SwitchDecision, ctx: UserContext) -> None:
    """Make a decision honest and self-describing before it is stored or shown.

    Called by both the daily scan and the user-facing check-now path.

    - Real offers: ``switch_audit_log`` has no columns for the proposed plan,
      so a recommendation names the plan in its reason.
    - Estimates only (``market_data_is_estimate``): any decision that reached
      plan comparison becomes a ``hold`` with no proposed plan whose reason
      says only estimated regional rates are available. The engine's savings
      figures are kept and reported as an estimate; thresholds and maths are
      untouched. Decisions stopped earlier (kill switch, cooldown) are left
      as they are — they say nothing about the market.
    """
    if market_data_is_estimate(ctx):
        _hold_on_estimates_only(decision)
        return
    plan = decision.proposed_plan
    if plan is not None and decision.action in _ADVISE_ACTIONS:
        decision.reason += f" Proposed: {plan.plan_name} at ${plan.rate_kwh}/kWh."


def _hold_on_estimates_only(decision: SwitchDecision) -> None:
    """Rewrite ``decision`` in place as the estimates-only hold (see above)."""
    if decision.proposed_plan is None and decision.rule_stopped_at != "plan_comparison":
        return

    reason = ESTIMATES_ONLY_REASON
    if decision.projected_savings_monthly > 0:
        reason += (
            " Estimated potential saving versus the regional estimate: "
            f"~${decision.projected_savings_monthly:.2f}/month."
        )
    if decision.proposed_plan is not None and decision.action not in _ADVISE_ACTIONS:
        # Savings-floor / ETF holds: keep the engine's explanation, which
        # names no supplier.
        reason += f" {decision.reason}"

    decision.action = "hold"
    decision.reason = reason
    decision.proposed_plan = None
    decision.rule_stopped_at = ESTIMATES_ONLY_RULE


def _aware(value: datetime | None) -> datetime | None:
    """Return ``value`` as a timezone-aware UTC datetime (None passes through)."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _decimal(value: Any, default: str) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal(default)


async def _load_user(db: AsyncSession, user_id: str) -> Mapping[str, Any]:
    result = await db.execute(
        text("SELECT subscription_tier, region FROM public.users WHERE id = :user_id"),
        {"user_id": user_id},
    )
    return result.mappings().first() or {}


async def _load_settings(db: AsyncSession, user_id: str) -> Mapping[str, Any]:
    result = await db.execute(
        text("""
            SELECT enabled, savings_threshold_pct, savings_threshold_min,
                   cooldown_days, paused_until, loa_signed_at, loa_revoked_at
            FROM public.user_agent_settings
            WHERE user_id = :user_id
        """),
        {"user_id": user_id},
    )
    return result.mappings().first() or {}


async def _load_current_plan(db: AsyncSession, user_id: str) -> PlanDetails | None:
    """Latest active ``user_plans`` row, or None when absent or unpriced."""
    result = await db.execute(
        text("""
            SELECT id, plan_name, provider_name, rate_kwh, fixed_charge,
                   term_months, etf_amount, contract_end
            FROM public.user_plans
            WHERE user_id = :user_id
              AND status = 'active'
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"user_id": user_id},
    )
    row = result.mappings().first()
    if row is None:
        return None
    if row["rate_kwh"] is None:
        # A plan without a rate cannot be compared; treating its cost as zero
        # would make every market plan look worse than it is.
        logger.info("switch_context_plan_without_rate", user_id=user_id, plan_id=str(row["id"]))
        return None
    return PlanDetails(
        plan_id=str(row["id"]),
        plan_name=row["plan_name"],
        provider_name=row["provider_name"],
        rate_kwh=Decimal(str(row["rate_kwh"])),
        fixed_charge=_decimal(row["fixed_charge"], "0"),
        term_months=row["term_months"],
        etf_amount=_decimal(row["etf_amount"], "0"),
        contract_end=_aware(row["contract_end"]),
    )


async def _load_market_plans(
    region: str | None,
    offer_repo: SupplierOfferRepository,
) -> list[dict[str, Any]]:
    """Market plans for the region, in the dict shape the engine documents."""
    if not region:
        return []
    offers = await offer_repo.cheapest_available_by_supplier(region)
    plans: list[dict[str, Any]] = []
    for key, offer in offers.items():
        label = "regional estimate" if offer.is_estimate else offer.tariff_type
        plans.append(
            {
                "id": offer.source_ref or key,
                "plan_name": f"{offer.supplier_name} ({label})",
                "provider_name": offer.supplier_name,
                "rate_kwh": Decimal(str(offer.rate_per_kwh)),
                # SupplierOffer.standing_charge is annualized; the engine wants monthly.
                "fixed_charge": (Decimal(str(offer.standing_charge or 0)) / Decimal("12")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ),
                "term_months": offer.intro_term_months,
                "etf_amount": Decimal(str(offer.cancellation_fee or 0)),
                "is_estimate": bool(offer.is_estimate),
                "source": offer.source,
                "enroll_url": offer.enroll_url,
            }
        )
    return plans


async def _load_usage(db: AsyncSession, user_id: str) -> tuple[Decimal, str, int]:
    """Average monthly kWh, data_source and full months of data from meter_readings.

    Uses the source with the most readings (mixing sources could double-count
    the same period). Returns ``(0, "none", 0)`` when there is less than one
    day of readings — usage is never guessed.
    """
    result = await db.execute(
        text("""
            SELECT source,
                   MIN(interval_minutes) AS interval_minutes,
                   SUM(kwh) AS total_kwh,
                   MIN(reading_time) AS first_reading,
                   MAX(reading_time) AS last_reading
            FROM public.meter_readings
            WHERE user_id = :user_id
            GROUP BY source
            ORDER BY COUNT(*) DESC
            LIMIT 1
        """),
        {"user_id": user_id},
    )
    row = result.mappings().first()
    empty = (Decimal("0"), NO_USAGE_DATA_SOURCE, 0)
    if row is None or row["total_kwh"] is None or row["first_reading"] is None:
        return empty

    interval_minutes = int(row["interval_minutes"] or 60)
    span_seconds = (row["last_reading"] - row["first_reading"]).total_seconds()
    span_days = Decimal(str(span_seconds)) / Decimal("86400") + Decimal(interval_minutes) / Decimal(
        "1440"
    )
    if span_days < 1:
        return empty

    monthly_kwh = (Decimal(str(row["total_kwh"])) / span_days * _DAYS_PER_MONTH).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    source = str(row["source"])
    if source in _INTERVAL_SOURCES and interval_minutes in (15, 60):
        source = f"{source}_{interval_minutes}min"
    return monthly_kwh, source, int(span_days // 30)


async def _load_switch_history(
    db: AsyncSession, user_id: str
) -> tuple[bool, str | None, datetime | None, datetime | None]:
    """(pending_switch_exists, last_status, last_enacted_at, rescission_ends)."""
    result = await db.execute(
        text("""
            SELECT status, enacted_at, rescission_ends
            FROM public.switch_executions
            WHERE user_id = :user_id
              AND executor_type <> :advisory
            ORDER BY created_at DESC
            LIMIT 20
        """),
        {"user_id": user_id, "advisory": ADVISORY_EXECUTOR_TYPE},
    )
    rows = result.mappings().all()
    if not rows:
        return False, None, None, None

    pending = any(row["status"] in PENDING_EXECUTION_STATUSES for row in rows)
    last = rows[0]
    last_enacted = next((row["enacted_at"] for row in rows if row["enacted_at"]), None)
    return pending, last["status"], _aware(last_enacted), _aware(last["rescission_ends"])


async def build_user_context(
    db: AsyncSession,
    user_id: str,
    *,
    settings: Mapping[str, Any] | None = None,
    tier: str | None = None,
    region: str | None = None,
    offer_repo: SupplierOfferRepository | None = None,
) -> UserContext:
    """Build a complete ``UserContext`` for ``user_id`` from the database.

    Args:
        db: Async SQLAlchemy session.
        user_id: UUID string of the user.
        settings: The user's ``user_agent_settings`` row if the caller already
            has it; loaded when omitted.
        tier: The user's subscription tier if already known.
        region: The user's region if already known. Tier and region are loaded
            from ``users`` when either is omitted.
        offer_repo: Supplier-offers repository (injectable for tests).

    Returns:
        A ``UserContext``. Fields without backing data are left empty:
        ``current_plan`` is None, ``available_plans`` is ``[]``, ``monthly_kwh``
        is 0 with ``data_source="none"``.

    Raises:
        Any database error — callers decide how to degrade.
    """
    if tier is None or region is None:
        user_row = await _load_user(db, user_id)
        tier = tier if tier is not None else user_row.get("subscription_tier")
        region = region if region is not None else user_row.get("region")
    if settings is None:
        settings = await _load_settings(db, user_id)

    current_plan = await _load_current_plan(db, user_id)
    available_plans = await _load_market_plans(region, offer_repo or SupplierOfferRepository(db))
    monthly_kwh, data_source, months_of_data = await _load_usage(db, user_id)
    pending, last_status, last_enacted_at, rescission_ends = await _load_switch_history(db, user_id)

    if available_plans and all(plan["is_estimate"] for plan in available_plans):
        data_source = f"{data_source}{MARKET_ESTIMATE_SUFFIX}"

    cooldown_days = settings.get("cooldown_days")
    return UserContext(
        user_id=user_id,
        tier=tier or "free",
        agent_enabled=bool(settings.get("enabled", False)),
        loa_signed=settings.get("loa_signed_at") is not None,
        loa_revoked=settings.get("loa_revoked_at") is not None,
        paused_until=_aware(settings.get("paused_until")),
        savings_threshold_pct=_decimal(settings.get("savings_threshold_pct"), "10.0"),
        savings_threshold_min=_decimal(settings.get("savings_threshold_min"), "10.0"),
        cooldown_days=int(cooldown_days) if cooldown_days is not None else 5,
        current_plan=current_plan,
        available_plans=available_plans,
        last_switch_enacted_at=last_enacted_at,
        last_switch_status=last_status,
        pending_switch_exists=pending,
        rescission_ends=rescission_ends,
        monthly_kwh=monthly_kwh,
        data_source=data_source,
        months_of_data=months_of_data,
    )
