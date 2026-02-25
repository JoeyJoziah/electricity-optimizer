"""
UtilityAPI Integration Client

Provides programmatic access to the UtilityAPI platform for direct utility
data synchronization. UtilityAPI acts as an intermediary between our app and
utility companies, enabling customers to authorize data access via an
OAuth-style flow.

API documentation: https://utilityapi.com/docs

Auth flow:
  1. Call create_authorization_form() to get a URL for the customer.
  2. Customer fills out the UtilityAPI authorization form.
  3. UtilityAPI calls our callback endpoint (GET /connections/direct/callback).
  4. We call get_authorization_status() to confirm authorization.
  5. We call get_meters() then get_bills() to fetch rate data.
  6. We normalize each bill via extract_rate_from_bill().

Design decisions:
  - httpx.AsyncClient is injected so tests can pass a mock client.
  - All public methods raise UtilityAPIError (a subclass of RuntimeError)
    on non-2xx responses so callers get a single exception type to handle.
  - Retry logic is handled externally by the sync service; this client is
    intentionally thin.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)

# Base URL for the UtilityAPI v2 REST API.
_BASE_URL = "https://utilityapi.com/api/v2"

# Default read timeout (seconds) for all UtilityAPI requests.
_DEFAULT_TIMEOUT = 30.0

# Number of bills to fetch per meter when syncing (most recent N).
_BILLS_FETCH_LIMIT = 12


class UtilityAPIError(RuntimeError):
    """
    Raised when the UtilityAPI returns a non-2xx response or when the
    response body cannot be parsed.
    """

    def __init__(self, message: str, status_code: int = 0, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class UtilityAPIClient:
    """
    Async client for the UtilityAPI v2 REST API.

    Usage (production):
        client = UtilityAPIClient()
        url = await client.create_authorization_form("Eversource Energy")
        # … customer authorizes …
        status = await client.get_authorization_status(auth_uid)
        meters = await client.get_meters(auth_uid)
        bills = await client.get_bills(meters[0]["uid"])
        rate = client.extract_rate_from_bill(bills[0])

    Usage (testing):
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        client = UtilityAPIClient(http_client=mock_http)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        """
        Args:
            api_key:     UtilityAPI server-side API key. Defaults to
                         ``settings.utilityapi_key``.
            http_client: Optional pre-built httpx.AsyncClient. Pass a mock
                         instance in tests to avoid real HTTP calls.
        """
        self._api_key = api_key or (settings.utilityapi_key or "")
        self._http_client = http_client
        self._owns_client = http_client is None

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        """Return the shared HTTP client, creating it lazily if needed."""
        if self._http_client is None or (
            hasattr(self._http_client, "is_closed") and self._http_client.is_closed
        ):
            self._http_client = httpx.AsyncClient(
                base_url=_BASE_URL,
                timeout=httpx.Timeout(_DEFAULT_TIMEOUT),
                headers={
                    "Authorization": f"Token {self._api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        return self._http_client

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._owns_client and self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def __aenter__(self) -> "UtilityAPIClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> dict:
        """
        Make an authenticated request to the UtilityAPI.

        Returns:
            Parsed JSON response body.

        Raises:
            UtilityAPIError: on HTTP error or JSON parse failure.
        """
        client = await self._get_client()
        try:
            response = await client.request(
                method,
                path,
                params=params,
                json=json,
                headers={
                    "Authorization": f"Token {self._api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        except httpx.TimeoutException as exc:
            logger.warning(
                "utilityapi_timeout",
                method=method,
                path=path,
                error=str(exc),
            )
            raise UtilityAPIError(
                f"Request to UtilityAPI timed out: {method} {path}"
            ) from exc
        except httpx.RequestError as exc:
            logger.warning(
                "utilityapi_request_error",
                method=method,
                path=path,
                error=str(exc),
            )
            raise UtilityAPIError(
                f"Network error calling UtilityAPI: {exc}"
            ) from exc

        if response.status_code >= 400:
            body: Any = None
            try:
                body = response.json()
            except Exception:
                body = response.text

            logger.error(
                "utilityapi_http_error",
                method=method,
                path=path,
                status_code=response.status_code,
                body=body,
            )
            raise UtilityAPIError(
                f"UtilityAPI returned {response.status_code} for {method} {path}",
                status_code=response.status_code,
                body=body,
            )

        try:
            return response.json()
        except Exception as exc:
            raise UtilityAPIError(
                f"Could not parse UtilityAPI JSON response: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Authorization form
    # ------------------------------------------------------------------

    async def create_authorization_form(
        self,
        supplier_name: str,
        *,
        state: Optional[str] = None,
        redirect_url: Optional[str] = None,
    ) -> str:
        """
        Generate a UtilityAPI authorization form URL for the customer.

        The customer visits this URL, selects their utility (pre-filled with
        ``supplier_name``), and grants data access.

        Args:
            supplier_name: Human-readable utility name (e.g. "Eversource Energy").
            state:         Opaque value echoed back in the callback ``?state=``
                           parameter. Used to bind the callback to a connection_id.
            redirect_url:  Where UtilityAPI should redirect after authorization.

        Returns:
            Absolute URL string the customer should be redirected to.
        """
        logger.info(
            "utilityapi_create_form",
            supplier_name=supplier_name,
            state=state,
        )

        params: dict[str, str] = {"utility": supplier_name}
        if state:
            params["state"] = state
        if redirect_url:
            params["redirect_url"] = redirect_url

        qs = urlencode(params)
        url = f"https://utilityapi.com/authorize?{qs}"
        logger.info("utilityapi_form_url_generated", url=url)
        return url

    # ------------------------------------------------------------------
    # Authorization status
    # ------------------------------------------------------------------

    async def get_authorization_status(self, authorization_uid: str) -> dict:
        """
        Retrieve the current status of a customer authorization.

        Args:
            authorization_uid: UID returned by UtilityAPI after the customer
                                completes the authorization form.

        Returns:
            Authorization object dict (keys: uid, status, utility, created, modified).

        Raises:
            UtilityAPIError: If the authorization UID is unknown or the request fails.
        """
        logger.info(
            "utilityapi_get_auth_status",
            authorization_uid=authorization_uid,
        )
        data = await self._request("GET", f"/authorizations/{authorization_uid}")
        return data

    # ------------------------------------------------------------------
    # Meters
    # ------------------------------------------------------------------

    async def get_meters(self, authorization_uid: str) -> list[dict]:
        """
        List all meters associated with an authorization.

        Args:
            authorization_uid: UID of the completed customer authorization.

        Returns:
            List of meter dicts. Each dict contains at minimum:
            ``uid``, ``utility``, ``service_identifier``, ``status``.

        Raises:
            UtilityAPIError: On API error or unexpected response shape.
        """
        logger.info(
            "utilityapi_get_meters",
            authorization_uid=authorization_uid,
        )
        data = await self._request(
            "GET",
            "/meters",
            params={"authorization_uid": authorization_uid},
        )

        meters: list[dict] = data.get("meters", [])
        logger.info(
            "utilityapi_meters_fetched",
            authorization_uid=authorization_uid,
            count=len(meters),
        )
        return meters

    # ------------------------------------------------------------------
    # Bills
    # ------------------------------------------------------------------

    async def get_bills(
        self,
        meter_uid: str,
        since: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Fetch billing history for a meter.

        Args:
            meter_uid: UID of the meter (from get_meters()).
            since:     Optional lower bound; only bills after this datetime
                       are returned. When None, fetches the most recent
                       ``_BILLS_FETCH_LIMIT`` bills.

        Returns:
            List of bill dicts, newest first.

        Raises:
            UtilityAPIError: On API error or unexpected response shape.
        """
        params: dict[str, Any] = {
            "meter_uid": meter_uid,
            "limit": _BILLS_FETCH_LIMIT,
        }
        if since is not None:
            params["start"] = since.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

        logger.info(
            "utilityapi_get_bills",
            meter_uid=meter_uid,
            since=since.isoformat() if since else None,
        )

        data = await self._request("GET", "/bills", params=params)
        bills: list[dict] = data.get("bills", [])

        logger.info(
            "utilityapi_bills_fetched",
            meter_uid=meter_uid,
            count=len(bills),
        )
        return bills

    # ------------------------------------------------------------------
    # Rate extraction
    # ------------------------------------------------------------------

    def extract_rate_from_bill(self, bill: dict) -> dict:
        """
        Normalize a UtilityAPI bill object into a rate data dict suitable
        for insertion into ``connection_extracted_rates``.

        UtilityAPI bill base structure (relevant fields):
          {
            "uid": "b_abc123",
            "meter_uid": "m_xyz789",
            "base": {
              "bill_start_date": "2025-01-01",
              "bill_end_date": "2025-02-01",
              "total_kwh": 850.5,
              "total_cost": 182.35,
              "rate_name": "Standard Rate"
            }
          }

        The rate ($/kWh) is derived from ``total_cost / total_kwh``.
        If either value is missing or the division is invalid (zero kWh),
        a UtilityAPIError is raised.

        Args:
            bill: Bill dict from get_bills().

        Returns:
            dict with keys:
              - rate_per_kwh  (float)
              - effective_date (datetime, UTC)
              - source        (str) — always "api_pull"
              - raw_label     (str or None)

        Raises:
            UtilityAPIError: If required fields are absent or rate is uncomputable.
        """
        base = bill.get("base") or {}
        uid = bill.get("uid", "<unknown>")

        total_kwh = base.get("total_kwh")
        total_cost = base.get("total_cost")

        if total_kwh is None or total_cost is None:
            raise UtilityAPIError(
                f"Bill {uid} is missing total_kwh or total_cost — cannot extract rate."
            )

        try:
            total_kwh_f = float(total_kwh)
            total_cost_f = float(total_cost)
        except (ValueError, TypeError) as exc:
            raise UtilityAPIError(
                f"Bill {uid} has non-numeric total_kwh/total_cost: {exc}"
            ) from exc

        if total_kwh_f <= 0:
            raise UtilityAPIError(
                f"Bill {uid} has zero or negative total_kwh ({total_kwh_f}) — cannot compute rate."
            )

        rate_per_kwh = total_cost_f / total_kwh_f

        # Parse effective date from bill_start_date (prefer) or bill_end_date.
        date_str = base.get("bill_start_date") or base.get("bill_end_date")
        if date_str:
            try:
                # Support ISO 8601 dates (YYYY-MM-DD) and datetimes
                effective_date = _parse_date(date_str)
            except ValueError:
                # Fall back to now if we cannot parse the date
                logger.warning(
                    "utilityapi_bill_bad_date",
                    bill_uid=uid,
                    date_str=date_str,
                )
                effective_date = datetime.now(timezone.utc)
        else:
            effective_date = datetime.now(timezone.utc)

        raw_label = base.get("rate_name") or None

        logger.debug(
            "utilityapi_rate_extracted",
            bill_uid=uid,
            rate_per_kwh=round(rate_per_kwh, 6),
            effective_date=effective_date.isoformat(),
        )

        return {
            "rate_per_kwh": round(rate_per_kwh, 6),
            "effective_date": effective_date,
            "source": "api_pull",
            "raw_label": raw_label,
        }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_date(date_str: str) -> datetime:
    """
    Parse a date/datetime string into a timezone-aware UTC datetime.

    Handles:
      - "YYYY-MM-DD"
      - "YYYY-MM-DDTHH:MM:SSZ"
      - "YYYY-MM-DDTHH:MM:SS+HH:MM"
    """
    # Strip trailing Z and replace with +00:00 for fromisoformat compat
    normalized = re.sub(r"Z$", "+00:00", date_str.strip())

    if "T" in normalized:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    # Date-only: treat as midnight UTC
    from datetime import date as _date  # noqa: F401 (avoid shadowing built-in)
    parts = normalized.split("-")
    if len(parts) != 3:
        raise ValueError(f"Unrecognized date format: {date_str!r}")
    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    return datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
