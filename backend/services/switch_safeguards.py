"""
Switch Safeguards — Pre-Switch Validation Checks

Standalone safeguard checks callable from the decision engine.
Each check returns a SafeguardResult indicating whether the check passed
and the reason for the outcome.

Checks:
1. kill_switch   — agent enabled, LOA active, not paused
2. cooldown      — no active cooldown from a recent switch
3. savings_floor — savings meet at least one configured threshold (OR logic)
4. etf_guard     — early-termination fee covered by year-1 savings
5. rescission    — no active rescission window from a prior switch

Usage:
    service = SwitchSafeguardsService(db)
    result = await service.check_kill_switch(user_id)
    results = await service.run_all_safeguards(user_id, monthly_savings, savings_pct, ...)
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from lib.tracing import traced

logger = structlog.get_logger(__name__)

# Default thresholds
DEFAULT_COOLDOWN_DAYS = 5
# Minimum year-1 net savings as a fraction of annual savings (50%)
ETF_COVERAGE_THRESHOLD_FRACTION = Decimal("0.5")
# Contract days remaining below which ETF is waived (free-switch window)
ETF_FREE_SWITCH_WINDOW_DAYS = 45


@dataclass
class SafeguardResult:
    """Result of a single safeguard check.

    Attributes:
        passed: True if the safeguard passed (no blocking condition found).
        reason: Human-readable explanation of the outcome.
    """

    passed: bool
    reason: str


class SwitchSafeguardsService:
    """Standalone safeguard checks for the auto-rate-switcher decision engine.

    All checks are independently callable or can be run together via
    ``run_all_safeguards()``.

    Args:
        db: An async SQLAlchemy session used for DB queries.

    Example:
        safeguards = SwitchSafeguardsService(db)
        result = await safeguards.check_kill_switch(user_id)
        if not result.passed:
            logger.info("blocked", reason=result.reason)
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def check_kill_switch(self, user_id: str) -> SafeguardResult:
        """Check agent-level kill switch conditions.

        Queries ``user_agent_settings`` for enabled flag, LOA status, and pause state.

        Blocking conditions (checked in order):
        - Agent not enabled
        - LOA explicitly revoked
        - LOA not yet signed
        - Pause window is active (paused_until > now)

        Args:
            user_id: The user's UUID string.

        Returns:
            SafeguardResult with passed=True when all kill-switch conditions are clear.
        """
        async with traced(
            "safeguards.check_kill_switch",
            attributes={"safeguard.user_id": user_id},
        ):
            result = await self._db.execute(
                text("""
                    SELECT enabled, loa_signed_at, loa_revoked_at, paused_until
                    FROM user_agent_settings
                    WHERE user_id = :uid
                """),
                {"uid": user_id},
            )
            row = result.mappings().first()

            # No settings row — treat as agent disabled
            if not row:
                logger.info(
                    "safeguard.kill_switch.no_settings",
                    user_id=user_id,
                )
                return SafeguardResult(passed=False, reason="Agent disabled")

            if not row["enabled"]:
                logger.info("safeguard.kill_switch.disabled", user_id=user_id)
                return SafeguardResult(passed=False, reason="Agent disabled")

            if row["loa_revoked_at"] is not None:
                logger.info("safeguard.kill_switch.loa_revoked", user_id=user_id)
                return SafeguardResult(passed=False, reason="LOA revoked")

            if row["loa_signed_at"] is None:
                logger.info("safeguard.kill_switch.loa_not_signed", user_id=user_id)
                return SafeguardResult(passed=False, reason="LOA not signed")

            paused_until = row["paused_until"]
            if paused_until is not None:
                now = datetime.now(UTC)
                # Ensure paused_until is timezone-aware for comparison
                if paused_until.tzinfo is None:
                    # Treat naive datetimes as UTC

                    paused_until = paused_until.replace(tzinfo=UTC)
                if paused_until > now:
                    pause_date = paused_until.strftime("%Y-%m-%d")
                    logger.info(
                        "safeguard.kill_switch.paused",
                        user_id=user_id,
                        paused_until=pause_date,
                    )
                    return SafeguardResult(
                        passed=False,
                        reason=f"Paused until {pause_date}",
                    )

            logger.info("safeguard.kill_switch.clear", user_id=user_id)
            return SafeguardResult(passed=True, reason="Kill switch clear")

    async def check_cooldown(self, user_id: str) -> SafeguardResult:
        """Check whether the post-switch cooldown period has elapsed.

        Queries ``switch_executions`` for the most recent active switch and
        ``user_agent_settings`` for the configured cooldown window.

        Args:
            user_id: The user's UUID string.

        Returns:
            SafeguardResult with passed=True when no cooldown is active.
        """
        async with traced(
            "safeguards.check_cooldown",
            attributes={"safeguard.user_id": user_id},
        ):
            # Get most recent active switch
            switch_result = await self._db.execute(
                text("""
                    SELECT enacted_at
                    FROM switch_executions
                    WHERE user_id = :uid AND status = 'active'
                    ORDER BY enacted_at DESC
                    LIMIT 1
                """),
                {"uid": user_id},
            )
            switch_row = switch_result.mappings().first()

            if not switch_row or switch_row["enacted_at"] is None:
                logger.info("safeguard.cooldown.no_previous_switch", user_id=user_id)
                return SafeguardResult(passed=True, reason="No previous switch")

            # Get cooldown_days from settings (default 5)
            settings_result = await self._db.execute(
                text("""
                    SELECT cooldown_days
                    FROM user_agent_settings
                    WHERE user_id = :uid
                """),
                {"uid": user_id},
            )
            settings_row = settings_result.mappings().first()
            cooldown_days = (
                settings_row["cooldown_days"]
                if (settings_row and settings_row["cooldown_days"] is not None)
                else DEFAULT_COOLDOWN_DAYS
            )

            now = datetime.now(UTC)
            enacted_at = switch_row["enacted_at"]
            # Ensure timezone-aware
            if enacted_at.tzinfo is None:
                enacted_at = enacted_at.replace(tzinfo=UTC)

            from datetime import timedelta

            cooldown_end = enacted_at + timedelta(days=cooldown_days)

            if cooldown_end > now:
                days_remaining = (cooldown_end - now).days
                # Ensure at least 1 day reported when still in cooldown
                if days_remaining == 0:
                    days_remaining = 1
                logger.info(
                    "safeguard.cooldown.active",
                    user_id=user_id,
                    days_remaining=days_remaining,
                )
                return SafeguardResult(
                    passed=False,
                    reason=f"Cooldown active, {days_remaining} days remaining",
                )

            logger.info("safeguard.cooldown.clear", user_id=user_id)
            return SafeguardResult(passed=True, reason="No previous switch")

    def check_savings_floor(
        self,
        monthly_savings: Decimal,
        savings_pct: Decimal,
        threshold_min: Decimal,
        threshold_pct: Decimal,
    ) -> SafeguardResult:
        """Check whether projected savings meet at least one configured threshold.

        Pure logic — no DB access. Uses logical OR: either threshold passing
        is sufficient for the check to pass.

        Args:
            monthly_savings: Projected absolute monthly savings in dollars.
            savings_pct: Projected savings as a percentage (e.g. 15.0 for 15%).
            threshold_min: Minimum absolute monthly savings threshold in dollars.
            threshold_pct: Minimum savings percentage threshold.

        Returns:
            SafeguardResult with passed=True when at least one threshold is met.
        """
        pct_passes = savings_pct >= threshold_pct
        min_passes = monthly_savings >= threshold_min

        if pct_passes or min_passes:
            logger.info(
                "safeguard.savings_floor.pass",
                monthly_savings=str(monthly_savings),
                savings_pct=str(savings_pct),
            )
            return SafeguardResult(passed=True, reason="Savings floor met")

        logger.info(
            "safeguard.savings_floor.fail",
            monthly_savings=str(monthly_savings),
            savings_pct=str(savings_pct),
            threshold_min=str(threshold_min),
            threshold_pct=str(threshold_pct),
        )
        return SafeguardResult(
            passed=False,
            reason=(
                f"Savings of ${monthly_savings:.2f}/month ({savings_pct}%) "
                f"below threshold "
                f"(${threshold_min:.2f}/month or {threshold_pct}%)"
            ),
        )

    def check_etf_guard(
        self,
        etf_amount: Decimal,
        annual_savings: Decimal,
        contract_days_remaining: int,
    ) -> SafeguardResult:
        """Check whether the early-termination fee is justified by year-1 savings.

        Pure logic — no DB access. Passes if any of these conditions hold:
        - No ETF (etf_amount <= 0)
        - Free-switch window: contract expires within 45 days
        - ETF covered: annual_savings - etf_amount >= annual_savings * 0.5

        Args:
            etf_amount: Early-termination fee in dollars.
            annual_savings: Projected year-1 annual savings in dollars.
            contract_days_remaining: Days until current contract expires.

        Returns:
            SafeguardResult with passed=True when ETF is not a blocking concern.
        """
        if etf_amount <= Decimal("0"):
            return SafeguardResult(passed=True, reason="No ETF")

        if contract_days_remaining <= ETF_FREE_SWITCH_WINDOW_DAYS:
            return SafeguardResult(passed=True, reason="Free switch window open")

        # ETF covered check: net year-1 savings must be >= 50% of annual savings
        net_year1 = annual_savings - etf_amount
        threshold = annual_savings * ETF_COVERAGE_THRESHOLD_FRACTION

        if net_year1 >= threshold:
            return SafeguardResult(passed=True, reason="ETF covered by savings")

        logger.info(
            "safeguard.etf_guard.fail",
            etf_amount=str(etf_amount),
            annual_savings=str(annual_savings),
            net_year1=str(net_year1),
        )
        return SafeguardResult(
            passed=False,
            reason=(f"ETF of ${etf_amount:.2f} exceeds net year-1 savings"),
        )

    async def check_rescission(self, user_id: str) -> SafeguardResult:
        """Check whether a rescission window from a prior switch is still active.

        Queries ``switch_executions`` for the most recent record with a
        ``rescission_ends`` value set.

        Args:
            user_id: The user's UUID string.

        Returns:
            SafeguardResult with passed=True when no rescission window is active.
        """
        async with traced(
            "safeguards.check_rescission",
            attributes={"safeguard.user_id": user_id},
        ):
            result = await self._db.execute(
                text("""
                    SELECT rescission_ends
                    FROM switch_executions
                    WHERE user_id = :uid
                      AND rescission_ends IS NOT NULL
                    ORDER BY rescission_ends DESC
                    LIMIT 1
                """),
                {"uid": user_id},
            )
            row = result.mappings().first()

            if not row or row["rescission_ends"] is None:
                logger.info("safeguard.rescission.no_record", user_id=user_id)
                return SafeguardResult(passed=True, reason="No rescission record")

            rescission_ends = row["rescission_ends"]
            now = datetime.now(UTC)

            # Ensure timezone-aware
            if rescission_ends.tzinfo is None:
                rescission_ends = rescission_ends.replace(tzinfo=UTC)

            if rescission_ends <= now:
                logger.info("safeguard.rescission.complete", user_id=user_id)
                return SafeguardResult(passed=True, reason="Rescission period complete")

            days_remaining = (rescission_ends - now).days
            if days_remaining == 0:
                days_remaining = 1
            logger.info(
                "safeguard.rescission.active",
                user_id=user_id,
                days_remaining=days_remaining,
            )
            return SafeguardResult(
                passed=False,
                reason=f"Rescission active, {days_remaining} days remaining",
            )

    async def run_all_safeguards(
        self,
        user_id: str,
        monthly_savings: Decimal,
        savings_pct: Decimal,
        threshold_min: Decimal,
        threshold_pct: Decimal,
        etf_amount: Decimal,
        annual_savings: Decimal,
        contract_days_remaining: int,
    ) -> list[SafeguardResult]:
        """Run all 5 safeguards in sequence, short-circuiting on first failure.

        Checks are evaluated in order:
        1. Kill switch
        2. Cooldown
        3. Savings floor
        4. ETF guard
        5. Rescission

        Short-circuits on the first failing check — subsequent checks are not
        run. Returns all results evaluated up to (and including) the failing one.

        Args:
            user_id: The user's UUID string.
            monthly_savings: Projected absolute monthly savings in dollars.
            savings_pct: Projected savings percentage (e.g. 15.0 for 15%).
            threshold_min: Minimum absolute monthly savings threshold.
            threshold_pct: Minimum savings percentage threshold.
            etf_amount: Early-termination fee in dollars.
            annual_savings: Projected year-1 annual savings in dollars.
            contract_days_remaining: Days until current contract expires.

        Returns:
            List of SafeguardResult objects for each check that was evaluated.
            If all checks pass, contains 5 results. On failure, contains results
            up to and including the first failing check.
        """
        async with traced(
            "safeguards.run_all",
            attributes={"safeguard.user_id": user_id},
        ):
            results: list[SafeguardResult] = []

            # 1. Kill switch
            kill_switch_result = await self.check_kill_switch(user_id)
            results.append(kill_switch_result)
            if not kill_switch_result.passed:
                return results

            # 2. Cooldown
            cooldown_result = await self.check_cooldown(user_id)
            results.append(cooldown_result)
            if not cooldown_result.passed:
                return results

            # 3. Savings floor (pure logic — no DB)
            savings_result = self.check_savings_floor(
                monthly_savings, savings_pct, threshold_min, threshold_pct
            )
            results.append(savings_result)
            if not savings_result.passed:
                return results

            # 4. ETF guard (pure logic — no DB)
            etf_result = self.check_etf_guard(etf_amount, annual_savings, contract_days_remaining)
            results.append(etf_result)
            if not etf_result.passed:
                return results

            # 5. Rescission
            rescission_result = await self.check_rescission(user_id)
            results.append(rescission_result)

            return results
