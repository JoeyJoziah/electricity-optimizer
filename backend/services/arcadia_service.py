"""
Arcadia Arc API Service

Provides meter data access via Arcadia's Arc platform (95% US utility coverage).
Methods: connect_account, fetch_interval_data, fetch_bills, sync_meter_readings.

External API — all calls mocked in tests until API contract in place.
"""

import asyncio
from datetime import datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from lib.tracing import traced

logger = structlog.get_logger(__name__)

ARCADIA_BASE_URL = "https://arc.arcadia.com/api/v1"
MAX_RETRIES = 3
RETRY_DELAY_BASE = 1.0  # seconds


class ArcadiaError(Exception):
    """Base error for Arcadia API failures."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ArcadiaAuthError(ArcadiaError):
    """Authentication/authorization failure."""


class ArcadiaRateLimitError(ArcadiaError):
    """Rate limit exceeded."""


class ArcadiaService:
    """Client for Arcadia Arc API — meter data, bills, account connection.

    All methods are mocked in tests until the Arc API contract is in place.
    The service is production-ready: retries on 429/503, exponential back-off
    on timeouts, structured logging, and OTel tracing on every public method.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._api_key: str = getattr(settings, "arcadia_api_key", None) or ""
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Return the shared HTTP client, creating it if necessary."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=ARCADIA_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Make an API request with retry on 429 / 503 / timeout.

        Args:
            method: HTTP verb (GET, POST, …).
            path: URL path relative to ARCADIA_BASE_URL.
            **kwargs: Forwarded verbatim to ``httpx.AsyncClient.request``.

        Returns:
            Parsed JSON response body.

        Raises:
            ArcadiaAuthError: HTTP 401.
            ArcadiaRateLimitError: HTTP 429 after all retries exhausted.
            ArcadiaError: Any other non-2xx status or network failure.
        """
        client = await self._get_client()
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                response = await client.request(method, path, **kwargs)

                if response.status_code == 401:
                    raise ArcadiaAuthError(
                        "Invalid or expired Arcadia API credentials",
                        status_code=401,
                    )
                if response.status_code == 429:
                    raise ArcadiaRateLimitError(
                        "Arcadia API rate limit exceeded",
                        status_code=429,
                    )
                if response.status_code >= 500:
                    raise ArcadiaError(
                        f"Arcadia server error: {response.status_code}",
                        status_code=response.status_code,
                    )

                response.raise_for_status()
                return response.json()

            except (ArcadiaRateLimitError, ArcadiaError) as exc:
                last_error = exc
                if exc.status_code in (429, 503) and attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY_BASE * (2**attempt)
                    logger.warning(
                        "arcadia_retry",
                        attempt=attempt + 1,
                        delay=delay,
                        status_code=exc.status_code,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY_BASE * (2**attempt)
                    logger.warning(
                        "arcadia_timeout_retry",
                        attempt=attempt + 1,
                        delay=delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise ArcadiaError("Arcadia API request timed out") from exc

            except httpx.HTTPError as exc:
                raise ArcadiaError(f"Arcadia API request failed: {exc}") from exc

        raise last_error or ArcadiaError("Max retries exceeded")

    async def connect_account(
        self,
        user_id: str,
        auth_code: str,
    ) -> dict[str, Any]:
        """Connect a user's utility account via OAuth auth code.

        Args:
            user_id: Internal RateShift user ID passed as external reference.
            auth_code: OAuth authorisation code from Arcadia's OAuth flow.

        Returns:
            Arcadia account object containing at minimum ``account_id``.

        Raises:
            ArcadiaAuthError: Invalid or expired auth code (HTTP 401).
            ArcadiaError: Any other API failure.
        """
        async with traced(
            "arcadia.connect_account",
            attributes={"arcadia.user_id": user_id},
        ):
            result = await self._request(
                "POST",
                "/accounts/connect",
                json={"auth_code": auth_code, "external_user_id": user_id},
            )
            account_id = result.get("account_id", "")
            logger.info(
                "arcadia_account_connected",
                user_id=user_id,
                account_id=account_id,
            )
            return result

    async def fetch_interval_data(
        self,
        account_id: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch interval (15/30/60-min) meter data for an account.

        Args:
            account_id: Arcadia account identifier.
            start: Inclusive start of the date range (UTC).
            end: Exclusive end of the date range (UTC).

        Returns:
            List of interval records. Each record contains at minimum
            ``timestamp``, ``kwh``, and ``interval_minutes`` keys.

        Raises:
            ArcadiaAuthError: Credentials rejected.
            ArcadiaRateLimitError: Rate limit hit after retries.
            ArcadiaError: Other API failures.
        """
        async with traced(
            "arcadia.fetch_interval_data",
            attributes={"arcadia.account_id": account_id},
        ):
            result = await self._request(
                "GET",
                f"/accounts/{account_id}/intervals",
                params={
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                },
            )
            intervals: list[dict[str, Any]] = result.get("intervals", [])
            logger.info(
                "arcadia_intervals_fetched",
                account_id=account_id,
                count=len(intervals),
            )
            return intervals

    async def fetch_bills(self, account_id: str) -> list[dict[str, Any]]:
        """Fetch billing history for an account.

        Args:
            account_id: Arcadia account identifier.

        Returns:
            List of bill records ordered newest-first.

        Raises:
            ArcadiaAuthError: Credentials rejected.
            ArcadiaError: Other API failures.
        """
        async with traced(
            "arcadia.fetch_bills",
            attributes={"arcadia.account_id": account_id},
        ):
            result = await self._request(
                "GET",
                f"/accounts/{account_id}/bills",
            )
            bills: list[dict[str, Any]] = result.get("bills", [])
            logger.info(
                "arcadia_bills_fetched",
                account_id=account_id,
                count=len(bills),
            )
            return bills

    async def sync_meter_readings(self, user_id: str) -> int:
        """Sync meter readings from Arcadia into the ``meter_readings`` table.

        Performs an incremental sync: reads start from the most recent stored
        timestamp for the user rather than a fixed horizon. New readings are
        batch-inserted in 500-row chunks (``ON CONFLICT DO NOTHING`` so
        re-runs are safe).

        Args:
            user_id: Internal RateShift user ID.

        Returns:
            Number of new rows inserted. Returns ``0`` if the user has no
            active Arcadia connection or if no new data is available.
        """
        async with traced(
            "arcadia.sync_meter_readings",
            attributes={"arcadia.user_id": user_id},
        ):
            # Locate the user's active Arcadia direct connection.
            conn_result = await self._db.execute(
                text(
                    "SELECT id, metadata FROM user_connections "
                    "WHERE user_id = :uid "
                    "AND connection_type = 'direct' "
                    "AND status = 'active' "
                    "AND metadata->>'provider' = 'arcadia' "
                    "LIMIT 1"
                ),
                {"uid": user_id},
            )
            conn_row = conn_result.mappings().first()
            if not conn_row:
                logger.info("arcadia_no_connection", user_id=user_id)
                return 0

            account_id: str = (conn_row.get("metadata") or {}).get("arcadia_account_id", "")
            if not account_id:
                logger.info(
                    "arcadia_no_account_id",
                    user_id=user_id,
                    connection_id=str(conn_row["id"]),
                )
                return 0

            # Determine incremental start point.
            last_result = await self._db.execute(
                text(
                    "SELECT MAX(reading_time) AS last_time "
                    "FROM meter_readings "
                    "WHERE user_id = :uid AND source = 'arcadia'"
                ),
                {"uid": user_id},
            )
            last_row = last_result.mappings().first()
            start: datetime = (
                last_row["last_time"]
                if last_row and last_row["last_time"]
                else datetime(2024, 1, 1)
            )
            end: datetime = datetime.utcnow()

            intervals = await self.fetch_interval_data(account_id, start, end)
            if not intervals:
                return 0

            # Batch insert in 500-row chunks.
            inserted = 0
            chunk_size = 500
            for i in range(0, len(intervals), chunk_size):
                chunk = intervals[i : i + chunk_size]
                values_parts: list[str] = []
                params: dict[str, Any] = {
                    "uid": user_id,
                    "conn_id": str(conn_row["id"]),
                }
                for j, interval in enumerate(chunk):
                    key = f"r{j}"
                    values_parts.append(
                        f"(:uid, :conn_id, :{key}_time, :{key}_kwh, :{key}_interval, 'arcadia')"
                    )
                    params[f"{key}_time"] = interval.get("timestamp")
                    params[f"{key}_kwh"] = interval.get("kwh", 0)
                    params[f"{key}_interval"] = interval.get("interval_minutes", 60)

                sql = (
                    "INSERT INTO meter_readings "
                    "(user_id, connection_id, reading_time, kwh,"
                    " interval_minutes, source) "
                    f"VALUES {', '.join(values_parts)} "
                    "ON CONFLICT DO NOTHING"
                )
                await self._db.execute(text(sql), params)
                inserted += len(chunk)

            await self._db.commit()
            logger.info(
                "arcadia_readings_synced",
                user_id=user_id,
                count=inserted,
            )
            return inserted

    async def close(self) -> None:
        """Close the underlying HTTP client and release its connection pool."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
