"""
Switch Executor — Adapter Pattern for Plan Enrollment

Protocol + adapters for executing electricity plan switches.

The product is advisory-only: the single adapter is ``AdvisoryOnlyFallback``,
which never enrolls anyone and only reports that a recommendation was recorded.
The ``SwitchExecutor`` protocol and ``get_executor`` factory remain so a real
enrollment provider can be added later without changing callers.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class EnrollmentRequest:
    """Data needed to execute a plan enrollment."""

    plan_id: str
    user_id: str
    user_name: str
    service_address: str
    zip_code: str
    utility_account_number: str
    idempotency_key: str  # UUID, written to DB BEFORE calling executor


@dataclass
class EnrollmentResult:
    """Result of an enrollment attempt."""

    success: bool
    enrollment_id: str | None = None
    status: str = "unknown"  # submitted, accepted, rejected, advisory_only
    estimated_switch_date: datetime | None = None
    message: str = ""
    provider: str = ""


@dataclass
class EnrollmentStatus:
    """Current status of a previously-created enrollment."""

    enrollment_id: str
    status: str  # submitted, accepted, active, rejected, cancelled
    switch_date: datetime | None = None
    rejection_reason: str | None = None


@runtime_checkable
class SwitchExecutor(Protocol):
    """Protocol for plan enrollment execution.

    Any provider adapter must implement these 4 methods.
    """

    async def check_plan_available(self, plan_id: str) -> bool:
        """Check if a plan is still available for enrollment."""
        ...

    async def execute_enrollment(self, request: EnrollmentRequest) -> EnrollmentResult:
        """Execute an enrollment. Idempotency key MUST already be in DB."""
        ...

    async def check_enrollment_status(self, enrollment_id: str) -> EnrollmentStatus:
        """Check the current status of an enrollment."""
        ...

    async def cancel_enrollment(self, enrollment_id: str) -> bool:
        """Cancel a pending enrollment. Returns True if cancelled."""
        ...


class AdvisoryOnlyFallback:
    """Fallback executor: degrades to recommendation-only mode.

    The only executor today (the product is advisory-only).
    Never actually enrolls — just records the recommendation.
    """

    def __init__(self) -> None:
        self.provider = "advisory_only"

    async def check_plan_available(self, plan_id: str) -> bool:
        """Always returns True — we can always recommend."""
        logger.info(
            "advisory_plan_check",
            plan_id=plan_id,
            message="Advisory mode — plan availability not verified",
        )
        return True

    async def execute_enrollment(self, request: EnrollmentRequest) -> EnrollmentResult:
        """Does not execute — returns advisory-only result."""
        logger.info(
            "advisory_enrollment",
            plan_id=request.plan_id,
            user_id=request.user_id,
            message="Advisory mode — enrollment not executed, recommendation logged",
        )
        return EnrollmentResult(
            success=False,
            enrollment_id=None,
            status="advisory_only",
            message=(
                "RateShift does not enroll on your behalf. "
                "A recommendation has been logged for you to act on manually."
            ),
            provider=self.provider,
        )

    async def check_enrollment_status(self, enrollment_id: str) -> EnrollmentStatus:
        """Advisory mode has no real enrollments."""
        return EnrollmentStatus(
            enrollment_id=enrollment_id,
            status="advisory_only",
            rejection_reason="Advisory mode — no real enrollment exists",
        )

    async def cancel_enrollment(self, enrollment_id: str) -> bool:
        """Nothing to cancel in advisory mode."""
        logger.info("advisory_cancel", enrollment_id=enrollment_id)
        return True


def get_executor(region: str) -> SwitchExecutor:
    """Factory: get the executor for a region.

    RateShift is advisory-only: no enrollment provider is integrated, so every
    region resolves to ``AdvisoryOnlyFallback``. The factory and the
    ``SwitchExecutor`` protocol are kept so a real executor can be registered
    here later without touching callers.

    Args:
        region: Region string from the Region enum (e.g. "us_tx").

    Returns:
        An instance satisfying the SwitchExecutor protocol.
    """
    logger.info("executor_selected", executor="advisory_only", region=region)
    return AdvisoryOnlyFallback()
