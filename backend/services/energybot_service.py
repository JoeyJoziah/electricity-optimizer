"""
EnergyBot API Service

Provides electricity plan comparison and enrollment across 13 deregulated US states.
Methods: fetch_plans, get_plan_details, create_enrollment, check_enrollment_status, cancel_enrollment.

External API — all calls mocked in tests until API contract in place.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from lib.tracing import traced

logger = structlog.get_logger(__name__)

ENERGYBOT_BASE_URL = "https://api.energybot.com/v1"
MAX_RETRIES = 3
RETRY_DELAY_BASE = 1.0


class EnergyBotError(Exception):
    """Base error for EnergyBot API failures."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class EnergyBotAuthError(EnergyBotError):
    """API key authentication failure."""

    pass


class EnergyBotRateLimitError(EnergyBotError):
    """Rate limit exceeded."""

    pass


class EnergyBotEnrollmentError(EnergyBotError):
    """Enrollment-specific error."""

    def __init__(
        self,
        message: str,
        enrollment_id: str | None = None,
        status_code: int | None = None,
    ):
        super().__init__(message, status_code)
        self.enrollment_id = enrollment_id


@dataclass
class EnrollmentRequest:
    """Request to enroll a user in a new electricity plan."""

    plan_id: str
    user_name: str
    service_address: str
    zip_code: str
    utility_account_number: str
    idempotency_key: str  # UUID string, MUST be generated before API call


@dataclass
class EnrollmentResult:
    """Result of an enrollment API call."""

    enrollment_id: str
    status: str  # submitted, accepted, rejected, processing
    estimated_switch_date: datetime | None = None
    message: str = ""


@dataclass
class EnrollmentStatus:
    """Current status of an enrollment."""

    enrollment_id: str
    status: str  # submitted, accepted, active, rejected, cancelled
    switch_date: datetime | None = None
    rejection_reason: str | None = None


class EnergyBotService:
    """Client for EnergyBot API — plan comparison and enrollment."""

    def __init__(self, db: AsyncSession):
        self._db = db
        self._api_key = getattr(settings, "energybot_api_key", None) or ""
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Return a reusable AsyncClient, creating it once (singleton per service instance)."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=ENERGYBOT_BASE_URL,
                headers={
                    "X-API-Key": self._api_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Make an API request with retry on 429/503.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: URL path relative to ENERGYBOT_BASE_URL.
            **kwargs: Additional arguments forwarded to httpx request.

        Returns:
            Parsed JSON response body.

        Raises:
            EnergyBotAuthError: On 401 — not retried.
            EnergyBotRateLimitError: On 429 after exhausting retries.
            EnergyBotError: On 5xx or network errors after exhausting retries.
        """
        client = await self._get_client()
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                response = await client.request(method, path, **kwargs)

                if response.status_code == 401:
                    raise EnergyBotAuthError("Invalid EnergyBot API key", status_code=401)
                if response.status_code == 429:
                    raise EnergyBotRateLimitError(
                        "EnergyBot API rate limit exceeded", status_code=429
                    )
                if response.status_code >= 500:
                    raise EnergyBotError(
                        f"EnergyBot server error: {response.status_code}",
                        status_code=response.status_code,
                    )

                response.raise_for_status()
                return response.json()

            except EnergyBotAuthError:
                # 401 is never retried — bad API key is a configuration problem.
                raise
            except (EnergyBotRateLimitError, EnergyBotError) as e:
                last_error = e
                if e.status_code in (429, 503) and attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY_BASE * (2**attempt)
                    logger.warning(
                        "energybot_retry",
                        attempt=attempt + 1,
                        delay=delay,
                        status_code=e.status_code,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY_BASE * (2**attempt)
                    logger.warning(
                        "energybot_timeout_retry",
                        attempt=attempt + 1,
                        delay=delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise EnergyBotError("EnergyBot API request timed out") from e
            except httpx.HTTPError as e:
                raise EnergyBotError(f"EnergyBot API request failed: {e}") from e

        raise last_error or EnergyBotError("Max retries exceeded")

    async def fetch_plans(
        self, zip_code: str, utility_code: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch available electricity plans for a zip code.

        Results are cached in the available_plans table per zip/utility
        combination. Any prior entries for the same zip/utility are deleted
        before the fresh results are inserted, keeping the cache current.

        Args:
            zip_code: 5-digit US zip code.
            utility_code: Optional utility provider code to narrow results.

        Returns:
            List of plan dicts returned by the EnergyBot API.
        """
        async with traced(
            "energybot.fetch_plans",
            attributes={"energybot.zip_code": zip_code},
        ):
            params: dict[str, str] = {"zip": zip_code}
            if utility_code:
                params["utility"] = utility_code

            result = await self._request("GET", "/plans", params=params)
            plans: list[dict[str, Any]] = result.get("plans", [])

            logger.info(
                "energybot_plans_fetched",
                zip_code=zip_code,
                utility_code=utility_code,
                count=len(plans),
            )

            if plans:
                await self._cache_plans(zip_code, utility_code, plans)

            return plans

    async def _cache_plans(
        self,
        zip_code: str,
        utility_code: str | None,
        plans: list[dict[str, Any]],
    ) -> None:
        """Cache fetched plans in the available_plans table.

        Deletes stale rows for the zip/utility pair before inserting fresh data
        so callers always see current pricing from the most recent API response.

        Args:
            zip_code: 5-digit US zip code.
            utility_code: Optional utility code used to scope the delete.
            plans: List of plan dicts from the API response.
        """
        delete_params: dict[str, Any] = {"zip": zip_code}
        delete_where = "zip_code = :zip"
        if utility_code:
            delete_where += " AND utility_code = :util"
            delete_params["util"] = utility_code

        await self._db.execute(
            text(f"DELETE FROM available_plans WHERE {delete_where}"),
            delete_params,
        )

        for plan in plans:
            await self._db.execute(
                text(
                    "INSERT INTO available_plans "
                    "(zip_code, utility_code, region, plan_name, provider_name, "
                    "rate_kwh, fixed_charge, term_months, etf_amount, renewable_pct, "
                    "plan_url, energybot_id, raw_plan_data, fetched_at) "
                    "VALUES (:zip, :util, :region, :name, :provider, "
                    ":rate, :fixed, :term, :etf, :renewable, "
                    ":url, :eb_id, :raw::jsonb, now())"
                ),
                {
                    "zip": zip_code,
                    "util": utility_code or plan.get("utility_code"),
                    "region": plan.get("state", "unknown"),
                    "name": plan.get("plan_name", "Unknown Plan"),
                    "provider": plan.get("provider_name", "Unknown Provider"),
                    "rate": plan.get("rate_kwh", 0),
                    "fixed": plan.get("fixed_charge", 0),
                    "term": plan.get("term_months"),
                    "etf": plan.get("etf_amount", 0),
                    "renewable": plan.get("renewable_pct", 0),
                    "url": plan.get("plan_url"),
                    "eb_id": plan.get("id"),
                    "raw": str(plan),
                },
            )
        await self._db.commit()

    async def get_plan_details(self, plan_id: str) -> dict[str, Any]:
        """Get detailed information about a specific plan.

        Args:
            plan_id: EnergyBot plan identifier.

        Returns:
            Full plan detail dict from the API.

        Raises:
            EnergyBotError: On API failure (including 404).
        """
        async with traced(
            "energybot.get_plan_details",
            attributes={"energybot.plan_id": plan_id},
        ):
            return await self._request("GET", f"/plans/{plan_id}")

    async def create_enrollment(
        self, request: EnrollmentRequest, idempotency_key: str
    ) -> EnrollmentResult:
        """Create a new enrollment (switch to a new plan).

        IMPORTANT: The caller MUST write the idempotency_key to switch_executions
        BEFORE calling this method. This prevents ghost switches if the network
        request succeeds but the response is lost before the DB write completes.

        Args:
            request: Enrollment details for the customer and plan.
            idempotency_key: Unique key to prevent duplicate enrollments.

        Returns:
            EnrollmentResult with enrollment_id and initial status.

        Raises:
            EnergyBotEnrollmentError: When the API rejects the enrollment.
            EnergyBotError: On other API failures.
        """
        async with traced(
            "energybot.create_enrollment",
            attributes={"energybot.plan_id": request.plan_id},
        ):
            result = await self._request(
                "POST",
                "/enrollments",
                json={
                    "plan_id": request.plan_id,
                    "customer_name": request.user_name,
                    "service_address": request.service_address,
                    "zip_code": request.zip_code,
                    "utility_account_number": request.utility_account_number,
                    "idempotency_key": idempotency_key,
                },
            )

            enrollment = EnrollmentResult(
                enrollment_id=result.get("enrollment_id", ""),
                status=result.get("status", "submitted"),
                estimated_switch_date=(
                    datetime.fromisoformat(result["estimated_switch_date"])
                    if result.get("estimated_switch_date")
                    else None
                ),
                message=result.get("message", ""),
            )

            logger.info(
                "energybot_enrollment_created",
                enrollment_id=enrollment.enrollment_id,
                status=enrollment.status,
            )
            return enrollment

    async def check_enrollment_status(self, enrollment_id: str) -> EnrollmentStatus:
        """Check the current status of an enrollment.

        Args:
            enrollment_id: EnergyBot enrollment identifier.

        Returns:
            EnrollmentStatus with current state and optional dates/reasons.

        Raises:
            EnergyBotError: On API failure.
        """
        async with traced(
            "energybot.check_enrollment_status",
            attributes={"energybot.enrollment_id": enrollment_id},
        ):
            result = await self._request("GET", f"/enrollments/{enrollment_id}")

            return EnrollmentStatus(
                enrollment_id=enrollment_id,
                status=result.get("status", "unknown"),
                switch_date=(
                    datetime.fromisoformat(result["switch_date"])
                    if result.get("switch_date")
                    else None
                ),
                rejection_reason=result.get("rejection_reason"),
            )

    async def cancel_enrollment(self, enrollment_id: str) -> bool:
        """Cancel a pending enrollment.

        Cancellation is best-effort: if the API returns an error the method
        logs the failure and returns False rather than raising. This is
        intentional — callers should treat False as a signal to surface a
        manual cancellation option to the user.

        Args:
            enrollment_id: EnergyBot enrollment identifier.

        Returns:
            True if the API confirmed the cancellation, False otherwise.
        """
        async with traced(
            "energybot.cancel_enrollment",
            attributes={"energybot.enrollment_id": enrollment_id},
        ):
            try:
                result = await self._request("POST", f"/enrollments/{enrollment_id}/cancel")
                cancelled: bool = result.get("cancelled", False)
                logger.info(
                    "energybot_enrollment_cancelled",
                    enrollment_id=enrollment_id,
                    success=cancelled,
                )
                return cancelled
            except EnergyBotError as e:
                logger.error(
                    "energybot_cancel_failed",
                    enrollment_id=enrollment_id,
                    error=str(e),
                )
                return False

    async def close(self) -> None:
        """Close the underlying HTTP client and release connections."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
