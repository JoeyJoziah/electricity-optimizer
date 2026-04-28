"""
Portal Scraper Service — Phase 3

HTTP-based scraper for credential-protected utility account portals.

Design decisions
----------------
- Uses ``httpx`` for async HTTP rather than Playwright / Puppeteer.
  Playwright is heavyweight for a production server environment; most utility
  portals expose their login as a plain HTML form POST that httpx can handle.
- Credentials are never held in memory beyond the duration of a single scrape
  call and are never logged.
- Rate extraction reuses the ``extract_rate_per_kwh`` function from
  ``services.bill_parser`` (single source of truth for regex patterns).
- Each scrape attempt is idempotent: the caller is responsible for persisting
  results and updating ``portal_scrape_status``.

Supported utilities (initial set)
----------------------------------
- Duke Energy    (duke-energy.com)
- PG&E           (pge.com)
- Con Edison     (coned.com)
- ComEd          (comed.com)
- FPL            (fpl.com)

For unsupported utilities, the service falls back to a generic form-POST
strategy using the caller-supplied ``login_url``.  This may or may not succeed
depending on the portal's auth mechanism.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

import structlog

from lib.tracing import traced

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------

# Allowed domains for portal scraping (known utility portals only)
_ALLOWED_DOMAINS: set[str] = {
    "duke-energy.com",
    "www.duke-energy.com",
    "pge.com",
    "www.pge.com",
    "coned.com",
    "www.coned.com",
    "comed.com",
    "secure.comed.com",
    "fpl.com",
    "www.fpl.com",
}


def _validate_portal_url(url: str) -> None:
    """Validate a portal URL to prevent SSRF attacks.

    Raises ValueError if the URL is not safe to request.
    """
    if not url:
        return  # Empty URL is handled by caller

    parsed = urlparse(url)

    # Enforce HTTPS only
    if parsed.scheme != "https":
        raise ValueError(f"Portal URL must use HTTPS, got: {parsed.scheme}")

    hostname = parsed.hostname or ""

    # Block private/internal IP ranges
    try:
        addr = ipaddress.ip_address(hostname)
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_reserved
            or addr.is_link_local
        ):
            raise ValueError("Portal URL must not point to private/internal addresses")
    except ValueError as e:
        if "private" in str(e) or "internal" in str(e):
            raise
        # Not an IP address — it's a hostname, which is fine

    # Validate against allowlist (if caller supplied a custom URL)
    # Known utility URLs from the registry are already trusted
    if hostname and not any(
        hostname == d or hostname.endswith(f".{d}") for d in _ALLOWED_DOMAINS
    ):
        logger.warning(
            "portal_url_not_in_allowlist",
            hostname=hostname,
            url=url,
        )
        # Allow but log — generic scraping is a documented feature


# ---------------------------------------------------------------------------
# Utility registry
# ---------------------------------------------------------------------------

SUPPORTED_UTILITIES: dict[str, dict[str, str]] = {
    "duke_energy": {
        "login_url": "https://www.duke-energy.com/sign-in",
        "name": "Duke Energy",
        "form_action": "https://www.duke-energy.com/sign-in",
        "username_field": "username",
        "password_field": "password",
        "billing_path": "/home/account/billing",
    },
    "pge": {
        "login_url": "https://www.pge.com/en/account/sign-in.html",
        "name": "PG&E",
        "form_action": "https://www.pge.com/en/account/sign-in.html",
        "username_field": "email",
        "password_field": "password",
        "billing_path": "/en/account/billing-and-payments.html",
    },
    "coned": {
        "login_url": "https://www.coned.com/en/login",
        "name": "Con Edison",
        "form_action": "https://www.coned.com/en/login",
        "username_field": "username",
        "password_field": "password",
        "billing_path": "/en/accounts-billing/your-account/view-your-bill",
    },
    "comed": {
        "login_url": "https://secure.comed.com/MyAccount/MyBillUsage",
        "name": "ComEd",
        "form_action": "https://secure.comed.com/MyAccount/Login",
        "username_field": "username",
        "password_field": "password",
        "billing_path": "/MyAccount/MyBillUsage",
    },
    "fpl": {
        "login_url": "https://www.fpl.com/login.html",
        "name": "FPL",
        "form_action": "https://www.fpl.com/api/resources/login",
        "username_field": "username",
        "password_field": "password",
        "billing_path": "/billing.html",
    },
}

# ---------------------------------------------------------------------------
# HTTP client factory (injectable for testing)
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT = 30  # seconds
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; RateShift/1.0; +https://rateshift.app/bot)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ---------------------------------------------------------------------------
# HTML rate extractor (wraps bill_parser patterns)
# ---------------------------------------------------------------------------


def _extract_rates_from_html(html: str) -> list[dict[str, Any]]:
    """
    Extract rate-per-kWh values from an HTML page body.

    Delegates to ``extract_rate_per_kwh`` from ``bill_parser`` (single source
    of truth for the regex patterns) and additionally strips HTML tags before
    matching so that rate values split across tags are still captured.

    Returns a list of dicts: ``[{"rate_per_kwh": float, "label": str}]``.
    """
    from services.bill_parser import extract_rate_per_kwh

    # Strip HTML tags to get readable text
    text_body = re.sub(r"<[^>]+>", " ", html)
    # Collapse excess whitespace
    text_body = re.sub(r"\s+", " ", text_body)

    rate, confidence = extract_rate_per_kwh(text_body)
    if rate is not None and confidence >= 0.5:
        return [{"rate_per_kwh": rate, "label": "portal_scrape"}]
    return []


# ---------------------------------------------------------------------------
# PortalScraperService
# ---------------------------------------------------------------------------


class PortalScraperService:
    """
    Scrape utility account portals for current billing rate data.

    Uses ``httpx`` for asynchronous HTTP-based scraping (form POSTs + redirect
    following) rather than a headless browser.  This is production-friendly —
    no Playwright binary required on the server.

    Usage::

        svc = PortalScraperService()
        result = await svc.scrape_portal(
            username="user@example.com",
            password="<REDACTED>",
            login_url="https://www.duke-energy.com/sign-in",
            supplier_id="duke_energy",
        )
        # result = {"success": True, "rates": [...], "error": None}
        await svc.close()

    Or use as an async context manager::

        async with PortalScraperService() as svc:
            result = await svc.scrape_portal(...)
    """

    def __init__(self, http_client: Any = None, db: Any = None) -> None:
        """
        Args:
            http_client: Injected ``httpx.AsyncClient`` (optional).
                         When ``None``, a client is created lazily on first use
                         and closed by ``close()`` / ``__aexit__``.
            db: Optional database session (stored for callers that need it).
        """
        self._client = http_client
        self._owns_client = http_client is None
        self._db = db

    # ------------------------------------------------------------------
    # Context manager helpers
    # ------------------------------------------------------------------

    async def __aenter__(self) -> PortalScraperService:
        await self._ensure_client()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _ensure_client(self) -> Any:
        """Lazily create the httpx client."""
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(
                timeout=_DEFAULT_TIMEOUT,
                headers=_DEFAULT_HEADERS,
                follow_redirects=True,
            )
        return self._client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scrape_portal(
        self,
        username: str = "",
        password: str = "",
        login_url: str = "",
        supplier_id: str = "",
        connection_id: str | None = None,  # noqa: ARG002
        utility_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Attempt to log in to a utility portal and extract current rate data.

        Args:
            username:      Portal login username / email.
            password:      Portal login password (decrypted at call site).
            login_url:     Full URL of the login page (overrides registry default
                           when the caller supplies one, otherwise falls back).
            supplier_id:   Key into ``SUPPORTED_UTILITIES`` (may also be a raw
                           URL string for unsupported utilities).
            _connection_id: Optional connection UUID (used for DB-backed scrapes).
            utility_name:  Human-readable utility name (alias for display/tracing).

        Returns:
            dict with keys:
              - ``success``  (bool)
              - ``rates``    (list of ``{"rate_per_kwh": float, "label": str}``)
              - ``error``    (str | None)
        """
        # Allow utility_name to serve as supplier_id when supplier_id is blank
        effective_supplier = supplier_id or utility_name or ""
        effective_utility_name = utility_name or supplier_id or ""
        async with traced(
            "scraper.portal",
            attributes={
                "scraper.utility": effective_utility_name,
                "scraper.method": "portal",
            },
        ):
            log = logger.bind(supplier_id=effective_supplier)
            log.info("portal_scrape_start")

            # SSRF protection: validate any caller-supplied login URL
            if login_url:
                try:
                    _validate_portal_url(login_url)
                except ValueError as url_err:
                    log.warning("portal_url_validation_failed", error=str(url_err))
                    return {
                        "success": False,
                        "rates": [],
                        "error": f"Invalid portal URL: {url_err}",
                    }

            try:
                client = await self._ensure_client()
                utility_config = SUPPORTED_UTILITIES.get(effective_supplier)

                if utility_config:
                    result = await self._scrape_known_utility(
                        client, utility_config, username, password, login_url
                    )
                else:
                    result = await self._scrape_generic(
                        client, login_url, username, password
                    )

                log.info(
                    "portal_scrape_complete",
                    success=result["success"],
                    rates_count=len(result.get("rates", [])),
                )
                return result

            except Exception as exc:
                log.error("portal_scrape_unexpected_error", error=str(exc))
                return {
                    "success": False,
                    "rates": [],
                    "error": f"Unexpected error during portal scrape: {exc}",
                }

    # ------------------------------------------------------------------
    # Private: known utility scrape
    # ------------------------------------------------------------------

    async def _scrape_known_utility(
        self,
        client: Any,
        config: dict[str, str],
        username: str,
        password: str,
        caller_login_url: str,
    ) -> dict[str, Any]:
        """
        Attempt a form-POST login for a known/registered utility portal.

        Steps:
          1. GET the login page to collect any CSRF tokens / form fields.
          2. POST credentials to the form action URL.
          3. Check that the response is a post-login page (not still the login page).
          4. GET the billing path and extract rates from the HTML.
        """
        effective_login_url = caller_login_url or config["login_url"]
        form_action = config.get("form_action", effective_login_url)

        try:
            # Step 1: GET login page to harvest hidden form fields / CSRF token
            login_page_resp = await client.get(effective_login_url)
            hidden_fields = self._extract_hidden_fields(login_page_resp.text)

            # Step 2: POST credentials
            post_data = {
                **hidden_fields,
                config.get("username_field", "username"): username,
                config.get("password_field", "password"): password,
            }
            post_resp = await client.post(form_action, data=post_data)

            # Step 3: Detect login failure heuristics
            if self._is_still_login_page(post_resp.text, config["name"]):
                return {
                    "success": False,
                    "rates": [],
                    "error": "Login failed — credentials may be incorrect or the portal requires additional verification.",
                }

            # Step 4: Fetch billing page and extract rates
            billing_html = post_resp.text  # start with post-login landing page
            billing_path = config.get("billing_path")
            if billing_path:
                base_url = self._base_url(effective_login_url)
                billing_url = base_url + billing_path
                try:
                    billing_resp = await client.get(billing_url)
                    billing_html = billing_resp.text
                except Exception:
                    # If billing nav fails, fall back to post-login page HTML
                    pass

            rates = _extract_rates_from_html(billing_html)
            return {
                "success": True,
                "rates": rates,
                "error": None,
            }

        except Exception as exc:
            return {
                "success": False,
                "rates": [],
                "error": f"HTTP error during portal scrape: {exc}",
            }

    # ------------------------------------------------------------------
    # Private: generic (unsupported utility) scrape
    # ------------------------------------------------------------------

    async def _scrape_generic(
        self,
        client: Any,
        login_url: str,
        username: str,
        password: str,
    ) -> dict[str, Any]:
        """
        Generic HTTP-form scrape for utilities not in the registry.

        Attempts a simple form POST with common field names and extracts
        any rate data from the resulting page.  Success rate is lower than
        known-utility scraping.
        """
        try:
            # Harvest hidden fields / CSRF token from login page
            login_page_resp = await client.get(login_url)
            hidden_fields = self._extract_hidden_fields(login_page_resp.text)

            # Try common field name combinations
            post_data = {
                **hidden_fields,
                "username": username,
                "email": username,
                "password": password,
            }
            post_resp = await client.post(login_url, data=post_data)

            rates = _extract_rates_from_html(post_resp.text)
            # Mark as success if we found any rates; otherwise partial
            success = len(rates) > 0
            error = (
                None
                if success
                else (
                    "No rate data extracted. The portal may require JavaScript or "
                    "multi-factor authentication not supported by HTTP-based scraping."
                )
            )
            return {
                "success": success,
                "rates": rates,
                "error": error,
            }

        except Exception as exc:
            return {
                "success": False,
                "rates": [],
                "error": f"Generic portal scrape failed: {exc}",
            }

    # ------------------------------------------------------------------
    # Private: HTML parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_hidden_fields(html: str) -> dict[str, str]:
        """
        Parse ``<input type="hidden" name="..." value="...">`` tags.

        Used to collect CSRF tokens and other hidden form fields needed for
        a valid form POST.
        """
        pattern = re.compile(
            r'<input[^>]+type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']',
            re.IGNORECASE,
        )
        # Also match name/value in the other order
        pattern_alt = re.compile(
            r'<input[^>]+type=["\']hidden["\'][^>]*value=["\']([^"\']*)["\'][^>]*name=["\']([^"\']+)["\']',
            re.IGNORECASE,
        )
        fields: dict[str, str] = {}
        for match in pattern.finditer(html):
            fields[match.group(1)] = match.group(2)
        for match in pattern_alt.finditer(html):
            fields[match.group(2)] = match.group(1)
        return fields

    @staticmethod
    def _is_still_login_page(html: str, _utility_name: str) -> bool:
        """
        Heuristic check for a failed login redirect.

        Returns True if the HTML looks like the portal is still showing the
        login form (i.e., the POST failed to authenticate the user).
        """
        lower = html.lower()
        failure_indicators = [
            "invalid password",
            "incorrect password",
            "login failed",
            "sign in failed",
            "authentication failed",
            "invalid credentials",
            "incorrect username",
            "account not found",
        ]
        for indicator in failure_indicators:
            if indicator in lower:
                return True

        # If the page still has a password input, login likely failed
        if 'type="password"' in lower or "type='password'" in lower:
            return True

        return False

    @staticmethod
    def _base_url(url: str) -> str:
        """Extract scheme + host from a URL string."""
        parts = url.split("/")
        if len(parts) >= 3:
            return "/".join(parts[:3])
        return url

    # ------------------------------------------------------------------
    # Public: extract helper (exposed for testing)
    # ------------------------------------------------------------------

    async def _extract_from_response(self, html: str) -> list[dict[str, Any]]:
        """Extract rate data from an HTML response string."""
        return _extract_rates_from_html(html)
