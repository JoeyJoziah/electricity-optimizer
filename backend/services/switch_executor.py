"""
Switch Executor — Adapter Pattern for Plan Enrollment

Protocol + adapters for executing electricity plan switches through various providers.
- EnergyBotExecutor: Primary adapter (13 deregulated US states)
- AdvisoryOnlyFallback: Degrades to recommendation when no executor available

The SwitchExecutor interface prevents single-provider lock-in.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

import structlog

from lib.tracing import traced

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


class EnergyBotExecutor:
    """Adapter: executes enrollments via EnergyBot API.

    Delegates to EnergyBotService for actual API calls.
    Handles mapping between internal and EnergyBot data formats.
    """

    def __init__(self, energybot_service: Any) -> None:
        self._service = energybot_service
        self.provider = "energybot"

    async def check_plan_available(self, plan_id: str) -> bool:
        """Check if plan is still available via EnergyBot."""
        async with traced(
            "executor.check_plan",
            attributes={"executor.plan_id": plan_id},
        ):
            try:
                details = await self._service.get_plan_details(plan_id)
                available = details.get("status") == "available"
                logger.info(
                    "executor_plan_check",
                    plan_id=plan_id,
                    available=available,
                    provider=self.provider,
                )
                return available
            except Exception as e:
                logger.error(
                    "executor_plan_check_failed",
                    plan_id=plan_id,
                    error=str(e),
                )
                return False

    async def execute_enrollment(self, request: EnrollmentRequest) -> EnrollmentResult:
        """Execute enrollment via EnergyBot API."""
        async with traced(
            "executor.execute_enrollment",
            attributes={
                "executor.plan_id": request.plan_id,
                "executor.provider": self.provider,
            },
        ):
            try:
                # Import here to avoid circular dependency
                from services.energybot_service import \
                    EnrollmentRequest as EBRequest

                eb_request = EBRequest(
                    plan_id=request.plan_id,
                    user_name=request.user_name,
                    service_address=request.service_address,
                    zip_code=request.zip_code,
                    utility_account_number=request.utility_account_number,
                    idempotency_key=request.idempotency_key,
                )

                result = await self._service.create_enrollment(
                    eb_request, request.idempotency_key
                )

                return EnrollmentResult(
                    success=True,
                    enrollment_id=result.enrollment_id,
                    status=result.status,
                    estimated_switch_date=result.estimated_switch_date,
                    message=result.message,
                    provider=self.provider,
                )
            except Exception as e:
                logger.error(
                    "executor_enrollment_failed",
                    plan_id=request.plan_id,
                    error=str(e),
                    provider=self.provider,
                )
                return EnrollmentResult(
                    success=False,
                    status="failed",
                    message=str(e),
                    provider=self.provider,
                )

    async def check_enrollment_status(self, enrollment_id: str) -> EnrollmentStatus:
        """Check enrollment status via EnergyBot."""
        async with traced(
            "executor.check_status",
            attributes={"executor.enrollment_id": enrollment_id},
        ):
            result = await self._service.check_enrollment_status(enrollment_id)
            return EnrollmentStatus(
                enrollment_id=result.enrollment_id,
                status=result.status,
                switch_date=result.switch_date,
                rejection_reason=result.rejection_reason,
            )

    async def cancel_enrollment(self, enrollment_id: str) -> bool:
        """Cancel enrollment via EnergyBot."""
        async with traced(
            "executor.cancel",
            attributes={"executor.enrollment_id": enrollment_id},
        ):
            return await self._service.cancel_enrollment(enrollment_id)


class AdvisoryOnlyFallback:
    """Fallback executor: degrades to recommendation-only mode.

    Used when no real executor is available for a region/utility.
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
                "No enrollment executor available for this region. "
                "A recommendation has been logged for the user to act on manually."
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


def get_executor(
    region: str,
    energybot_service: Any | None = None,
) -> SwitchExecutor:
    """Factory: get the appropriate executor for a region.

    Returns EnergyBotExecutor if service is available, else AdvisoryOnlyFallback.

    Args:
        region: Region string from the Region enum (e.g. "us_tx").
        energybot_service: Optional EnergyBotService instance. When None,
            always returns AdvisoryOnlyFallback regardless of region.

    Returns:
        An instance satisfying the SwitchExecutor protocol.
    """
    # EnergyBot supported states (deregulated markets)
    ENERGYBOT_STATES = {
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
    }

    if energybot_service and region.lower() in ENERGYBOT_STATES:
        logger.info("executor_selected", executor="energybot", region=region)
        return EnergyBotExecutor(energybot_service)

    logger.info("executor_selected", executor="advisory_only", region=region)
    return AdvisoryOnlyFallback()
