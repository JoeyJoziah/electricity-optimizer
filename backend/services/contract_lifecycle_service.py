"""
Contract Lifecycle Service

Tracks contract state per user: active plan details, cooldown windows,
rescission periods, and free-switch windows (within 45 days of contract end).

State-specific rescission periods are provided as a static lookup by
2-letter state code (TX=14, OH=7, PA=3, MA=3, IL=10, NY=3, default=3).
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from lib.tracing import traced

logger = structlog.get_logger(__name__)

# Days before contract expiry at which the free-switch window opens
_FREE_SWITCH_WINDOW_DAYS = 45

# Default cooldown period in days if not configured per-user
_DEFAULT_COOLDOWN_DAYS = 5

# State rescission periods (days) indexed by uppercase 2-letter state code
_RESCISSION_DAYS: dict[str, int] = {
    "TX": 14,
    "OH": 7,
    "PA": 3,
    "MA": 3,
    "IL": 10,
    "NY": 3,
}


class ContractLifecycleService:
    """Service that tracks electricity contract state for a user.

    All public methods accept a ``user_id`` string and query the database
    directly via raw SQL (``text()``). The session is injected at
    construction time following the project-standard pattern.

    Args:
        db: An async SQLAlchemy session scoped to the current request.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def get_contract_status(self, user_id: str) -> dict:
        """Return the current contract status for a user.

        Queries ``user_plans`` for the active plan, ``switch_executions``
        for the most recent enacted switch, and ``user_agent_settings``
        for cooldown configuration.

        Returns:
            dict with keys:
            - ``has_active_plan`` (bool)
            - ``plan_name`` (str | None)
            - ``provider_name`` (str | None)
            - ``contract_start`` (datetime | None)
            - ``contract_end`` (datetime | None)
            - ``days_remaining`` (int | None)
            - ``is_month_to_month`` (bool)
            - ``etf_amount`` (Decimal)
        """
        async with traced(
            "contract_lifecycle.get_contract_status",
            attributes={"contract.user_id": user_id},
        ):
            plan_result = await self._db.execute(
                text("""
                    SELECT
                        up.plan_name,
                        up.provider_name,
                        up.contract_start,
                        up.contract_end,
                        up.etf_amount
                    FROM user_plans up
                    WHERE up.user_id = :uid
                      AND up.status = 'active'
                    ORDER BY up.created_at DESC
                    LIMIT 1
                """),
                {"uid": user_id},
            )
            plan_row = plan_result.mappings().first()

            if not plan_row:
                logger.info("contract_status_no_active_plan", user_id=user_id)
                return {
                    "has_active_plan": False,
                    "plan_name": None,
                    "provider_name": None,
                    "contract_start": None,
                    "contract_end": None,
                    "days_remaining": None,
                    "is_month_to_month": False,
                    "etf_amount": Decimal("0"),
                }

            contract_end = plan_row["contract_end"]
            is_month_to_month = contract_end is None

            days_remaining: int | None = None
            if contract_end is not None:
                now = datetime.now(UTC)
                # Normalise to UTC-aware if the DB returns a naive datetime
                if contract_end.tzinfo is None:
                    contract_end = contract_end.replace(tzinfo=UTC)
                delta = contract_end - now
                days_remaining = max(0, delta.days)

            etf_raw = plan_row["etf_amount"]
            etf_amount = Decimal(str(etf_raw)) if etf_raw is not None else Decimal("0")

            logger.info(
                "contract_status_found",
                user_id=user_id,
                plan_name=plan_row["plan_name"],
                days_remaining=days_remaining,
                is_month_to_month=is_month_to_month,
            )

            return {
                "has_active_plan": True,
                "plan_name": plan_row["plan_name"],
                "provider_name": plan_row["provider_name"],
                "contract_start": plan_row["contract_start"],
                "contract_end": contract_end,
                "days_remaining": days_remaining,
                "is_month_to_month": is_month_to_month,
                "etf_amount": etf_amount,
            }

    async def is_in_cooldown(self, user_id: str) -> tuple[bool, int]:
        """Check whether the user is within their post-switch cooldown period.

        Reads ``switch_executions`` for the most recent enacted switch and
        ``user_agent_settings`` for the configured ``cooldown_days``
        (defaults to 5 if not set).

        Returns:
            Tuple of (in_cooldown: bool, days_remaining: int).
            ``days_remaining`` is 0 when not in cooldown.
        """
        async with traced(
            "contract_lifecycle.is_in_cooldown",
            attributes={"contract.user_id": user_id},
        ):
            # Fetch the most recent enacted switch
            exec_result = await self._db.execute(
                text("""
                    SELECT enacted_at
                    FROM switch_executions
                    WHERE user_id = :uid
                      AND status = 'enacted'
                    ORDER BY enacted_at DESC
                    LIMIT 1
                """),
                {"uid": user_id},
            )
            exec_row = exec_result.mappings().first()

            if not exec_row or exec_row["enacted_at"] is None:
                logger.debug("is_in_cooldown_no_prior_switch", user_id=user_id)
                return False, 0

            # Fetch cooldown_days from user_agent_settings
            settings_result = await self._db.execute(
                text("""
                    SELECT cooldown_days
                    FROM user_agent_settings
                    WHERE user_id = :uid
                    LIMIT 1
                """),
                {"uid": user_id},
            )
            settings_row = settings_result.mappings().first()
            cooldown_days = (
                int(settings_row["cooldown_days"])
                if settings_row and settings_row["cooldown_days"] is not None
                else _DEFAULT_COOLDOWN_DAYS
            )

            enacted_at = exec_row["enacted_at"]
            if enacted_at.tzinfo is None:
                enacted_at = enacted_at.replace(tzinfo=UTC)

            cooldown_end = enacted_at + timedelta(days=cooldown_days)
            now = datetime.now(UTC)

            if cooldown_end > now:
                days_left = max(1, (cooldown_end - now).days)
                logger.info(
                    "is_in_cooldown_active",
                    user_id=user_id,
                    days_remaining=days_left,
                )
                return True, days_left

            logger.debug("is_in_cooldown_expired", user_id=user_id)
            return False, 0

    async def is_in_rescission(self, user_id: str) -> tuple[bool, int]:
        """Check whether the user is within the rescission window of their last switch.

        Reads ``rescission_ends`` from the most recent ``switch_executions``
        row for this user.

        Returns:
            Tuple of (in_rescission: bool, days_remaining: int).
            ``days_remaining`` is 0 when not in rescission.
        """
        async with traced(
            "contract_lifecycle.is_in_rescission",
            attributes={"contract.user_id": user_id},
        ):
            result = await self._db.execute(
                text("""
                    SELECT rescission_ends
                    FROM switch_executions
                    WHERE user_id = :uid
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"uid": user_id},
            )
            row = result.mappings().first()

            if not row or row["rescission_ends"] is None:
                logger.debug("is_in_rescission_no_data", user_id=user_id)
                return False, 0

            rescission_ends = row["rescission_ends"]
            if rescission_ends.tzinfo is None:
                rescission_ends = rescission_ends.replace(tzinfo=UTC)

            now = datetime.now(UTC)
            if rescission_ends > now:
                days_left = max(1, (rescission_ends - now).days)
                logger.info(
                    "is_in_rescission_active",
                    user_id=user_id,
                    days_remaining=days_left,
                )
                return True, days_left

            logger.debug("is_in_rescission_expired", user_id=user_id)
            return False, 0

    async def get_free_switch_window(self, user_id: str) -> dict:
        """Determine whether the free-switch window (no ETF) is currently open.

        The window opens when the active contract expires within 45 days.
        Month-to-month plans are always considered to have the window open
        (no ETF applies).

        Returns:
            dict with keys:
            - ``window_open`` (bool)
            - ``days_until_expiry`` (int | None) — None for month-to-month
            - ``etf_waived`` (bool) — True if within the free-switch window
            - ``recommended_action`` (str) — human-readable guidance
        """
        async with traced(
            "contract_lifecycle.get_free_switch_window",
            attributes={"contract.user_id": user_id},
        ):
            plan_result = await self._db.execute(
                text("""
                    SELECT contract_end, etf_amount, status
                    FROM user_plans
                    WHERE user_id = :uid
                      AND status = 'active'
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"uid": user_id},
            )
            plan_row = plan_result.mappings().first()

            # No active plan at all
            if not plan_row:
                logger.info("free_switch_window_no_plan", user_id=user_id)
                return {
                    "window_open": True,
                    "days_until_expiry": None,
                    "etf_waived": True,
                    "recommended_action": "No active plan — you are free to switch at any time.",
                }

            contract_end = plan_row["contract_end"]

            # Month-to-month: window always open
            if contract_end is None:
                logger.info("free_switch_window_month_to_month", user_id=user_id)
                return {
                    "window_open": True,
                    "days_until_expiry": None,
                    "etf_waived": True,
                    "recommended_action": (
                        "Month-to-month plan — you can switch at any time with no ETF."
                    ),
                }

            if contract_end.tzinfo is None:
                contract_end = contract_end.replace(tzinfo=UTC)

            now = datetime.now(UTC)
            delta = contract_end - now
            days_until_expiry = max(0, delta.days)

            # Contract already expired
            if days_until_expiry == 0:
                logger.info("free_switch_window_expired_contract", user_id=user_id)
                return {
                    "window_open": True,
                    "days_until_expiry": 0,
                    "etf_waived": True,
                    "recommended_action": (
                        "Your contract has expired — switch now for maximum savings."
                    ),
                }

            within_window = days_until_expiry <= _FREE_SWITCH_WINDOW_DAYS

            if within_window:
                action = (
                    f"Your contract expires in {days_until_expiry} days — "
                    "switch now to avoid the ETF."
                )
            else:
                action = (
                    f"Your contract has {days_until_expiry} days remaining. "
                    f"The free-switch window opens in "
                    f"{days_until_expiry - _FREE_SWITCH_WINDOW_DAYS} days."
                )

            logger.info(
                "free_switch_window_evaluated",
                user_id=user_id,
                days_until_expiry=days_until_expiry,
                window_open=within_window,
            )

            return {
                "window_open": within_window,
                "days_until_expiry": days_until_expiry,
                "etf_waived": within_window,
                "recommended_action": action,
            }

    @staticmethod
    def get_rescission_period_days(state_code: str) -> int:
        """Return the rescission period in days for the given US state.

        Args:
            state_code: 2-letter uppercase state code (e.g. ``"TX"``).
                        Case-insensitive; normalised internally.

        Returns:
            Rescission period in days. Defaults to 3 for unknown states.
        """
        return _RESCISSION_DAYS.get(state_code.upper(), 3)
