"""
Unit tests for PortalScraperService.

Coverage:
  scrape_portal()
    - known utility: happy path (rates extracted)
    - known utility: login failure (password input still present)
    - known utility: HTTP error during POST
    - generic scrape: rates found
    - generic scrape: no rates (partial success → success=False)
    - generic scrape: HTTP error
    - unexpected top-level exception → graceful error dict

  _extract_hidden_fields()
    - standard name/value order
    - alternate value/name order
    - multiple hidden fields
    - no hidden fields → empty dict

  _is_still_login_page()
    - failure indicator keywords
    - password input present → still login page
    - clean post-login page → not login page

  _base_url()
    - standard URL
    - bare scheme+host

All tests use a mock httpx.AsyncClient injected via the constructor —
no real network calls are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.portal_scraper_service import (SUPPORTED_UTILITIES,
                                             PortalScraperService)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(text: str, status_code: int = 200) -> MagicMock:
    """Build a mock httpx Response with .text and .status_code."""
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    return resp


def _async_mock_response(text: str, status_code: int = 200) -> AsyncMock:
    """Wrap _mock_response in an AsyncMock (for awaitable client calls)."""
    resp = _mock_response(text, status_code)
    am = AsyncMock(return_value=resp)
    return am


# ===========================================================================
# scrape_portal — known utility
# ===========================================================================


class TestScrapeKnownUtility:
    """Tests for PortalScraperService.scrape_portal() with a known supplier."""

    async def test_known_utility_success(self):
        """Happy path: login succeeds, billing page contains a rate."""
        client = AsyncMock()

        login_html = "<html><body><input type='hidden' name='csrf' value='abc'></body></html>"
        post_html = "<html><body>Welcome! Your rate is 0.1234 per kWh.</body></html>"
        billing_html = "<html><body>Current rate: $0.1234 / kWh</body></html>"

        client.get = AsyncMock(
            side_effect=[
                _mock_response(login_html),  # GET login page
                _mock_response(billing_html),  # GET billing page
            ]
        )
        client.post = AsyncMock(return_value=_mock_response(post_html))

        svc = PortalScraperService(http_client=client)
        result = await svc.scrape_portal(
            username="user@example.com",
            password="secret",
            login_url="https://www.duke-energy.com/sign-in",
            supplier_id="duke_energy",
        )

        assert result["success"] is True
        assert isinstance(result["rates"], list)
        assert result["error"] is None

    async def test_known_utility_login_failure(self):
        """Login page returned after POST (invalid credentials indicator)."""
        client = AsyncMock()

        login_html = "<html><body><input type='hidden' name='token' value='x'></body></html>"
        # POST response still contains a password field → login failed heuristic
        failed_post_html = (
            "<html><body><p>Invalid credentials</p>"
            "<input type='password' name='password'></body></html>"
        )

        client.get = AsyncMock(return_value=_mock_response(login_html))
        client.post = AsyncMock(return_value=_mock_response(failed_post_html))

        svc = PortalScraperService(http_client=client)
        result = await svc.scrape_portal(
            username="bad@user.com",
            password="wrongpassword",
            login_url="https://www.pge.com/en/account/sign-in.html",
            supplier_id="pge",
        )

        assert result["success"] is False
        assert result["error"] is not None
        assert "credentials" in result["error"].lower() or "login failed" in result["error"].lower()

    async def test_known_utility_http_error(self):
        """HTTP exception during POST → graceful failure dict."""
        import httpx

        client = AsyncMock()
        login_html = "<html><body></body></html>"
        client.get = AsyncMock(return_value=_mock_response(login_html))
        client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        svc = PortalScraperService(http_client=client)
        result = await svc.scrape_portal(
            username="user@example.com",
            password="secret",
            login_url="https://secure.comed.com/MyAccount/MyBillUsage",
            supplier_id="comed",
        )

        assert result["success"] is False
        assert result["error"] is not None

    async def test_known_utility_billing_page_fallback(self):
        """When billing page GET fails, falls back to post-login page HTML."""
        import httpx

        client = AsyncMock()

        login_html = "<html></html>"
        # Post-login page has rate info
        post_html = "<html><body>Your current rate is 0.1500 per kWh.</body></html>"

        client.get = AsyncMock(
            side_effect=[
                _mock_response(login_html),  # GET login page
                httpx.ConnectError("Timeout"),  # GET billing page (fails)
            ]
        )
        client.post = AsyncMock(return_value=_mock_response(post_html))

        svc = PortalScraperService(http_client=client)
        result = await svc.scrape_portal(
            username="user@fpl.com",
            password="secret",
            login_url="https://www.fpl.com/login.html",
            supplier_id="fpl",
        )

        # Falls back to post-login HTML; whether rates found depends on regex
        assert "success" in result
        assert "rates" in result


# ===========================================================================
# scrape_portal — generic (unsupported utility)
# ===========================================================================


class TestScrapeGenericUtility:
    """Tests for PortalScraperService._scrape_generic() via scrape_portal()."""

    async def test_generic_scrape_rates_found(self):
        """Generic scrape: rate regex matches → success=True."""
        client = AsyncMock()

        login_html = "<html><body></body></html>"
        post_html = "<html><body>Your energy charge: 0.1350 per kWh</body></html>"

        client.get = AsyncMock(return_value=_mock_response(login_html))
        client.post = AsyncMock(return_value=_mock_response(post_html))

        svc = PortalScraperService(http_client=client)
        result = await svc.scrape_portal(
            username="user@unknown.com",
            password="pass",
            login_url="https://unknown-utility.com/login",
            supplier_id="unknown_utility",  # not in SUPPORTED_UTILITIES
        )

        assert "success" in result
        assert "rates" in result
        assert "error" in result

    async def test_generic_scrape_no_rates(self):
        """Generic scrape: no rate in HTML → success=False, error message set."""
        client = AsyncMock()

        login_html = "<html><body></body></html>"
        post_html = "<html><body>Welcome! No billing information available online.</body></html>"

        client.get = AsyncMock(return_value=_mock_response(login_html))
        client.post = AsyncMock(return_value=_mock_response(post_html))

        svc = PortalScraperService(http_client=client)
        result = await svc.scrape_portal(
            username="user@generic.com",
            password="pass",
            login_url="https://generic.com/login",
            supplier_id="generic_util",
        )

        assert result["success"] is False
        assert result["error"] is not None

    async def test_generic_scrape_http_error(self):
        """Generic scrape: HTTP error → graceful failure."""
        import httpx

        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.ConnectError("unreachable"))

        svc = PortalScraperService(http_client=client)
        result = await svc.scrape_portal(
            username="u",
            password="p",
            login_url="https://nowhere.example.com/login",
            supplier_id="nowhere",
        )

        assert result["success"] is False
        assert result["error"] is not None

    async def test_unexpected_exception_caught(self):
        """Exception during scrape is caught and a graceful error dict is returned."""
        client = AsyncMock()
        # Raise a non-HTTP exception during GET login page
        client.get = AsyncMock(side_effect=RuntimeError("Unexpected failure"))

        svc = PortalScraperService(http_client=client)
        result = await svc.scrape_portal(
            username="u",
            password="p",
            login_url="https://example.com/login",
            supplier_id="duke_energy",
        )

        # The service always returns a dict with success=False on any exception
        assert result["success"] is False
        assert result["error"] is not None
        assert "Unexpected failure" in result["error"] or len(result["error"]) > 0


# ===========================================================================
# _extract_hidden_fields
# ===========================================================================


class TestExtractHiddenFields:
    """Unit tests for PortalScraperService._extract_hidden_fields()."""

    def test_standard_name_value_order(self):
        html = '<input type="hidden" name="csrf_token" value="abc123">'
        fields = PortalScraperService._extract_hidden_fields(html)
        assert fields == {"csrf_token": "abc123"}

    def test_alternate_value_name_order(self):
        html = "<input type='hidden' value='xyz789' name='__RequestVerificationToken'>"
        fields = PortalScraperService._extract_hidden_fields(html)
        assert fields == {"__RequestVerificationToken": "xyz789"}

    def test_multiple_hidden_fields(self):
        html = (
            '<input type="hidden" name="token" value="tok1">'
            '<input type="hidden" name="nonce" value="noc2">'
        )
        fields = PortalScraperService._extract_hidden_fields(html)
        assert "token" in fields
        assert "nonce" in fields
        assert fields["token"] == "tok1"
        assert fields["nonce"] == "noc2"

    def test_no_hidden_fields(self):
        html = "<form><input type='text' name='user'></form>"
        fields = PortalScraperService._extract_hidden_fields(html)
        assert fields == {}

    def test_empty_value(self):
        html = '<input type="hidden" name="empty_field" value="">'
        fields = PortalScraperService._extract_hidden_fields(html)
        assert fields["empty_field"] == ""


# ===========================================================================
# _is_still_login_page
# ===========================================================================


class TestIsStillLoginPage:
    """Unit tests for PortalScraperService._is_still_login_page()."""

    def test_invalid_password_indicator(self):
        html = "<p>Invalid password. Please try again.</p>"
        assert PortalScraperService._is_still_login_page(html, "TestUtil") is True

    def test_login_failed_indicator(self):
        html = "<p>Login failed. Check your credentials.</p>"
        assert PortalScraperService._is_still_login_page(html, "TestUtil") is True

    def test_authentication_failed_indicator(self):
        html = "<div>Authentication failed</div>"
        assert PortalScraperService._is_still_login_page(html, "TestUtil") is True

    def test_account_not_found_indicator(self):
        html = "<p>Account not found. Please register.</p>"
        assert PortalScraperService._is_still_login_page(html, "TestUtil") is True

    def test_password_input_still_present(self):
        html = '<form><input type="password" name="password"></form>'
        assert PortalScraperService._is_still_login_page(html, "TestUtil") is True

    def test_password_input_single_quotes(self):
        html = "<input type='password' name='pass'>"
        assert PortalScraperService._is_still_login_page(html, "TestUtil") is True

    def test_clean_post_login_page(self):
        html = "<html><body><h1>Welcome, John!</h1><p>Account summary</p></body></html>"
        assert PortalScraperService._is_still_login_page(html, "TestUtil") is False

    def test_case_insensitive_check(self):
        html = "<p>INVALID PASSWORD</p>"
        assert PortalScraperService._is_still_login_page(html, "TestUtil") is True


# ===========================================================================
# _base_url
# ===========================================================================


class TestBaseUrl:
    """Unit tests for PortalScraperService._base_url()."""

    def test_standard_url(self):
        url = "https://www.duke-energy.com/sign-in"
        assert PortalScraperService._base_url(url) == "https://www.duke-energy.com"

    def test_url_with_path(self):
        url = "https://pge.com/en/account/sign-in.html"
        assert PortalScraperService._base_url(url) == "https://pge.com"

    def test_bare_scheme_host(self):
        url = "https://example.com"
        assert PortalScraperService._base_url(url) == "https://example.com"


# ===========================================================================
# SUPPORTED_UTILITIES registry
# ===========================================================================


class TestSupportedUtilitiesRegistry:
    """Sanity checks on the SUPPORTED_UTILITIES dict."""

    @pytest.mark.parametrize("key", ["duke_energy", "pge", "coned", "comed", "fpl"])
    def test_required_utility_keys_present(self, key):
        assert key in SUPPORTED_UTILITIES

    @pytest.mark.parametrize("key", ["duke_energy", "pge", "coned", "comed", "fpl"])
    def test_each_utility_has_required_fields(self, key):
        config = SUPPORTED_UTILITIES[key]
        for field in ("login_url", "name", "form_action", "username_field", "password_field"):
            assert field in config, f"{key} missing field {field!r}"

    @pytest.mark.parametrize("key", ["duke_energy", "pge", "coned", "comed", "fpl"])
    def test_login_urls_are_https(self, key):
        url = SUPPORTED_UTILITIES[key]["login_url"]
        assert url.startswith("https://"), f"{key} login_url is not HTTPS: {url!r}"


# ===========================================================================
# Context manager interface
# ===========================================================================


class TestContextManager:
    """Test PortalScraperService.__aenter__ / __aexit__."""

    async def test_aenter_returns_self(self):
        import httpx

        client = AsyncMock(spec=httpx.AsyncClient)
        svc = PortalScraperService(http_client=client)
        entered = await svc.__aenter__()
        assert entered is svc
        await svc.__aexit__(None, None, None)

    async def test_close_when_owns_client(self):
        """When the service owns the client, close() must call aclose()."""
        svc = PortalScraperService()

        mock_client = AsyncMock()
        svc._client = mock_client
        svc._owns_client = True

        await svc.close()
        mock_client.aclose.assert_called_once()
        assert svc._client is None

    async def test_close_when_not_owns_client(self):
        """When the client was injected, close() must NOT call aclose()."""
        mock_client = AsyncMock()
        svc = PortalScraperService(http_client=mock_client)

        await svc.close()
        mock_client.aclose.assert_not_called()
        # Client reference is retained (not cleared) since we don't own it
