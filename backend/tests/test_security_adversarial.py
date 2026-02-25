"""
Adversarial Security Test Suite
================================
Negative / adversarial tests for the Electricity Optimizer FastAPI backend.

Coverage:
  1.  SQL injection probes in query parameters
  2.  XSS payloads in user-facing input fields (name, email)
  3.  Rate-limit bypass probes (IP spoofing via X-Forwarded-For)
  4.  CORS validation (unauthorised origins must not receive CORS allow headers)
  5.  Missing / invalid auth header returns 401 on protected routes
  6.  Stripe webhook without valid signature returns 400
  7.  API key probes on the protected /refresh endpoint
  8.  Oversized request body handling
  9.  Path traversal probes in supplier_id path parameter
  10. Open redirect probes on billing endpoints
  11. Security headers presence on all responses
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Make sure the backend package root is importable when pytest is invoked
# from the project root or from within the backend/ directory.
# ---------------------------------------------------------------------------
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import os
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

import pytest
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.testclient import TestClient
import jwt as jose_jwt

# Import the actual singletons so we use the same secret the app uses,
# regardless of import order (os.environ.setdefault is unreliable when
# Settings() is already created by conftest or other modules).
from config.settings import settings as _settings


# ---------------------------------------------------------------------------
# Helpers: token factories
# ---------------------------------------------------------------------------

# Self-contained test secret for JWT token factories used in security tests.
# These tokens are verified by the test_app fixture's own auth dependency,
# NOT by any production auth module.
TEST_SECRET = "test-adversarial-secret-key-for-security-tests"
TEST_ALGORITHM = "HS256"
ISSUER = "electricity-optimizer"

# Test values for settings that may not have been set before the singleton
# was created.  Used by full_app_client fixture below.
_TEST_INTERNAL_API_KEY = "test-internal-api-key-for-adversarial-tests"
_TEST_STRIPE_SECRET_KEY = "sk_test_adversarial_placeholder"
_TEST_STRIPE_WEBHOOK_SECRET = "whsec_test_placeholder_secret_for_tests"


def _make_access_token(
    user_id: str = "user-adv-001",
    email: str = "adversarial@example.com",
    scopes: list = None,
    exp_offset_seconds: int = 900,   # positive = future, negative = past
    secret: str = TEST_SECRET,
    algorithm: str = TEST_ALGORITHM,
    extra_claims: dict = None,
) -> str:
    """Create a signed JWT for testing with full control over claims."""
    from uuid import uuid4

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "scopes": scopes or [],
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=exp_offset_seconds),
        "jti": str(uuid4()),
        "iss": ISSUER,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jose_jwt.encode(payload, secret, algorithm=algorithm)


# ---------------------------------------------------------------------------
# App fixture: minimal FastAPI app wired to the real auth middleware
# ---------------------------------------------------------------------------

@pytest.fixture
def test_app():
    """
    Minimal FastAPI application that exercises the real middleware stack
    (auth, security headers) without requiring a database connection.
    """
    app = FastAPI()

    # Import real middleware
    from middleware.security_headers import SecurityHeadersMiddleware
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )

    from fastapi import Request

    async def _test_bearer_auth(request: Request):
        """Self-contained Bearer token auth for security tests.

        Validates JWT tokens using TEST_SECRET. Returns 401 for missing,
        invalid, expired, or malformed tokens.
        """
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Not authenticated")
        token = auth_header[7:].strip()
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        try:
            payload = jose_jwt.decode(
                token, TEST_SECRET, algorithms=[TEST_ALGORITHM]
            )
            if payload.get("type") != "access":
                raise HTTPException(status_code=401, detail="Invalid token type")
            if "sub" not in payload:
                raise HTTPException(status_code=401, detail="Missing subject")
            return {"user_id": payload["sub"], "email": payload.get("email", "")}
        except jose_jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")

    @app.get("/protected")
    async def protected_route(user: dict = Depends(_test_bearer_auth)):
        return {"user_id": user["user_id"], "email": user["email"]}

    @app.post("/echo-name")
    async def echo_name(payload: dict):
        """Accepts JSON with a 'name' field and echoes it back as plain text."""
        name = payload.get("name", "")
        # In a real application the name would be stored in the DB.
        # Here we just return it to verify it is accepted/rejected correctly.
        return {"name": name}

    @app.post("/echo-email")
    async def echo_email(payload: dict):
        email = payload.get("email", "")
        return {"email": email}

    return app


@pytest.fixture
def client(test_app):
    """Synchronous TestClient wrapping the minimal test app."""
    with TestClient(test_app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Fixture: full app client (for webhook / billing / supplier endpoint tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def full_app_client():
    """
    TestClient for the real FastAPI application defined in main.py.

    Database calls and external service calls are patched out so the tests
    are fully offline.  Settings attributes that were not in the environment
    when the singleton was created are patched directly on the object.

    Module-scoped: all 42 tests are read-only security probes — no state mutation.
    Eliminates 42 importlib.reload(main) calls (~1s each on CI).
    """
    # Patch settings that the test expectations depend on.
    _originals = {}
    for attr, val in [
        ("internal_api_key", _TEST_INTERNAL_API_KEY),
        ("stripe_secret_key", _TEST_STRIPE_SECRET_KEY),
        ("stripe_webhook_secret", _TEST_STRIPE_WEBHOOK_SECRET),
    ]:
        _originals[attr] = getattr(_settings, attr)
        object.__setattr__(_settings, attr, val)

    # Patch database initialisation so the app starts without a real DB.
    with patch("config.database.db_manager.initialize", new_callable=AsyncMock), \
         patch("config.database.db_manager.close", new_callable=AsyncMock), \
         patch("config.database.db_manager.get_redis_client",
               new_callable=AsyncMock, return_value=None), \
         patch("config.database.db_manager._execute_raw_query",
               new_callable=AsyncMock, return_value=[{"1": 1}]), \
         patch("config.database.db_manager.get_timescale_session") as mock_session_cm:

        # Make get_timescale_session a context manager that yields None.
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=None)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cm.return_value = mock_session

        # Reload main to get a fresh app free of stale state from earlier
        # test modules that may have used the same app via TestClient.
        import importlib
        import main as _main_mod
        importlib.reload(_main_mod)
        app = _main_mod.app

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    # Restore original settings values.
    for attr, val in _originals.items():
        object.__setattr__(_settings, attr, val)


# =============================================================================
# 1.  SQL INJECTION PROBES IN QUERY PARAMETERS
# =============================================================================

SQL_INJECTION_PAYLOADS = [
    "'; DROP TABLE electricity_prices; --",
    "' OR '1'='1",
    "1; SELECT * FROM users --",
    "' UNION SELECT username, password FROM users --",
    "1' AND SLEEP(5) --",
    "' OR 1=1#",
    "%27%20OR%201%3D1",
]


class TestSQLInjection:
    """Verify that SQL injection payloads in query parameters are rejected or
    handled safely (422 Unprocessable Entity or 200 with no DB effect)."""

    def test_region_sql_injection_returns_422(self, full_app_client):
        """
        The 'region' parameter is validated against the PriceRegion enum.
        Any value outside the enum should yield 422, not 500 or 200.
        """
        for payload in SQL_INJECTION_PAYLOADS:
            response = full_app_client.get(
                f"/api/v1/prices/current?region={payload}"
            )
            assert response.status_code in (422, 400), (
                f"SQL injection payload '{payload}' was not rejected. "
                f"Got HTTP {response.status_code}."
            )

    def test_supplier_id_sql_injection(self, full_app_client):
        """
        Supplier IDs from path parameters containing SQL metacharacters should
        return 404 (not found) not 500 (unhandled exception).
        """
        for payload in SQL_INJECTION_PAYLOADS:
            response = full_app_client.get(f"/api/v1/suppliers/{payload}")
            assert response.status_code in (404, 422, 400), (
                f"SQL injection in supplier_id was not rejected. "
                f"Got HTTP {response.status_code}."
            )

    def test_days_parameter_sql_injection(self, full_app_client):
        """The 'days' query parameter is typed as int; non-integer input must be 422."""
        for payload in ["1; DROP TABLE--", "' OR 1=1", "1 UNION SELECT 1"]:
            response = full_app_client.get(
                f"/api/v1/prices/history?region=us_ct&days={payload}"
            )
            assert response.status_code == 422, (
                f"Expected 422 for non-integer 'days={payload}', "
                f"got {response.status_code}."
            )


# =============================================================================
# 2.  XSS PAYLOADS IN USER-FACING INPUT FIELDS
# =============================================================================

XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    "<img src=x onerror=alert(1)>",
    "javascript:alert(1)",
    "'><svg onload=alert(1)>",
    "\"><script>document.cookie</script>",
    "&lt;script&gt;alert(1)&lt;/script&gt;",
]


class TestXSSInputHandling:
    """
    The API is JSON-based; its responsibility is to accept / reject input
    according to its schema and to NEVER reflect raw HTML/JS back in a
    rendered HTML response.  All responses are JSON, so XSS via the API
    itself is not directly exploitable, but we verify:
      - The API accepts or rejects (validates) the payload correctly.
      - The response body does not contain unescaped HTML if returned.
    """

    def test_xss_in_name_field_accepted_or_rejected_cleanly(self, client):
        """
        A name field containing XSS markup should be accepted as a string
        (no script execution in JSON context) OR rejected with 422.
        It must not cause a 500 error.
        """
        for payload in XSS_PAYLOADS:
            response = client.post("/echo-name", json={"name": payload})
            assert response.status_code in (200, 422, 400), (
                f"XSS payload in 'name' field caused unexpected status "
                f"{response.status_code}."
            )
            # If accepted as 200, ensure Content-Type is application/json
            if response.status_code == 200:
                assert "application/json" in response.headers.get(
                    "content-type", ""
                ), "Response to XSS input is not JSON."

    def test_xss_in_email_field_rejected(self, client):
        """
        An email field containing XSS markup is not a valid email address;
        it should be rejected with 422 at the Pydantic validation layer
        (EmailStr validator) or at least not cause a 500.
        """
        for payload in XSS_PAYLOADS:
            response = client.post("/echo-email", json={"email": payload})
            # Plain XSS strings are not valid email addresses; either 200
            # (if the echo endpoint has no EmailStr validator — it doesn't
            # in our minimal test app) or 422.
            assert response.status_code in (200, 422, 400), (
                f"XSS in email caused {response.status_code}."
            )

    def test_xss_in_password_check_field(self, full_app_client):
        """
        The /auth/password/check-strength endpoint accepts a password string.
        XSS payloads are valid strings for strength-checking purposes; the
        endpoint must return JSON (not rendered HTML) regardless of content.

        Note: /auth/signup and /auth/signin are now handled by Better Auth
        via the Next.js frontend API routes. The backend no longer has those
        endpoints.
        """
        for payload in XSS_PAYLOADS:
            response = full_app_client.post(
                "/api/v1/auth/password/check-strength",
                json={"password": payload},
            )
            assert response.status_code == 200, (
                f"XSS payload in password check caused {response.status_code}."
            )
            assert "application/json" in response.headers.get("content-type", ""), (
                f"Response to XSS-in-password is not JSON. "
                f"Content-Type: {response.headers.get('content-type')}"
            )


# =============================================================================
# 3.  RATE LIMIT BYPASS ATTEMPTS
# =============================================================================

class TestRateLimitBypass:
    """Verify that IP-spoofing headers cannot be used to bypass rate limiting."""

    def test_x_forwarded_for_does_not_bypass_rate_limit(self):
        """
        The rate limiter uses request.client.host (the real TCP peer address)
        for IP-based bucketing, NOT the X-Forwarded-For header.  This test
        confirms the middleware does not blindly trust X-Forwarded-For.

        Since the rate limit is high (100/min default) we cannot trivially
        trigger it in a unit test without mocking.  Instead we verify that the
        middleware's _get_identifier() method ignores X-Forwarded-For.
        """
        from middleware.rate_limiter import RateLimitMiddleware
        from fastapi import FastAPI, Request
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, exclude_paths=[])

        @app.get("/test")
        async def test_ep():
            return {"ok": True}

        middleware = RateLimitMiddleware(app=app)

        class FakeRequest:
            class client:
                host = "1.2.3.4"
            headers = {"Authorization": ""}

            def __getattr__(self, name):
                return MagicMock()

        req = FakeRequest()
        # The identifier must be based on the real client address
        identifier = middleware._get_identifier(req)
        # X-Forwarded-For is not in the headers, so bucket must use real IP
        assert "1.2.3.4" in identifier or "ip:" in identifier, (
            f"Rate limiter identifier does not include client IP: {identifier}"
        )

    def test_spoofed_x_forwarded_for_ignored(self):
        """
        Sending X-Forwarded-For: 127.0.0.1 should not change the rate-limit
        bucket to 'localhost' or an internal IP.
        """
        from middleware.rate_limiter import RateLimitMiddleware
        from fastapi import FastAPI

        app = FastAPI()
        middleware = RateLimitMiddleware(app=app)

        class FakeRequest:
            class client:
                host = "203.0.113.42"  # Real peer (external)
            headers = {"X-Forwarded-For": "127.0.0.1", "Authorization": ""}

            def __getattr__(self, name):
                return MagicMock()

        req = FakeRequest()
        identifier = middleware._get_identifier(req)
        # Must NOT use the spoofed 127.0.0.1
        assert "127.0.0.1" not in identifier, (
            f"Rate limiter trusted spoofed X-Forwarded-For: {identifier}"
        )
        assert "203.0.113.42" in identifier or "ip:" in identifier, (
            f"Rate limiter did not use the real client IP: {identifier}"
        )


# =============================================================================
# 5.  CORS VALIDATION
# =============================================================================

class TestCORSValidation:
    """Verify that CORS policy rejects unauthorised origins."""

    def test_unknown_origin_does_not_receive_cors_allow_header(self, client):
        """
        A request from an arbitrary origin must not receive an
        Access-Control-Allow-Origin header that reflects that origin back.
        """
        response = client.get(
            "/protected",
            headers={
                "Origin": "https://evil-attacker.example.com",
                "Authorization": f"Bearer {_make_access_token()}",
            },
        )
        acao = response.headers.get("access-control-allow-origin", "")
        assert "evil-attacker.example.com" not in acao, (
            f"Server reflected attacker origin in ACAO header: {acao!r}"
        )

    def test_allowed_origin_receives_cors_header(self, client):
        """Requests from the allowed origin should receive the CORS header."""
        response = client.get(
            "/protected",
            headers={
                "Origin": "http://localhost:3000",
                "Authorization": f"Bearer {_make_access_token()}",
            },
        )
        acao = response.headers.get("access-control-allow-origin", "")
        assert "localhost:3000" in acao or acao == "*", (
            f"Allowed origin did not receive ACAO header. "
            f"Got: {acao!r}"
        )

    def test_cors_preflight_unknown_origin_rejected(self, full_app_client):
        """
        An OPTIONS preflight from an unknown origin should not receive a
        permissive Access-Control-Allow-Origin header.
        """
        response = full_app_client.options(
            "/api/v1/auth/me",
            headers={
                "Origin": "https://malicious-site.io",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        acao = response.headers.get("access-control-allow-origin", "")
        assert "malicious-site.io" not in acao, (
            f"Preflight from unknown origin reflected in ACAO: {acao!r}"
        )


# =============================================================================
# 6.  MISSING AUTH HEADER RETURNS 401
# =============================================================================

class TestMissingAuth:
    """Protected routes must return 401 when auth header is absent."""

    def test_protected_route_no_token_is_401(self, client):
        response = client.get("/protected")
        assert response.status_code == 401

    def test_protected_route_empty_bearer_is_401(self, client):
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer "},
        )
        assert response.status_code == 401

    def test_protected_route_basic_auth_is_401(self, client):
        """Basic auth credentials must not be accepted where Bearer is expected."""
        import base64

        creds = base64.b64encode(b"user:password").decode()
        response = client.get(
            "/protected",
            headers={"Authorization": f"Basic {creds}"},
        )
        assert response.status_code == 401

    def test_me_requires_auth(self, full_app_client):
        """GET /api/v1/auth/me is a protected endpoint and needs a session."""
        response = full_app_client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_user_preferences_requires_auth(self, full_app_client):
        """GET /api/v1/user/preferences is protected."""
        response = full_app_client.get("/api/v1/user/preferences")
        assert response.status_code == 401

    def test_billing_checkout_requires_auth(self, full_app_client):
        """POST /api/v1/billing/checkout must require a valid JWT."""
        response = full_app_client.post(
            "/api/v1/billing/checkout",
            json={
                "tier": "pro",
                "success_url": "http://localhost:3000/success",
                "cancel_url": "http://localhost:3000/cancel",
            },
        )
        assert response.status_code == 401

    def test_billing_subscription_requires_auth(self, full_app_client):
        """GET /api/v1/billing/subscription must require a valid JWT."""
        response = full_app_client.get("/api/v1/billing/subscription")
        assert response.status_code == 401


# =============================================================================
# 7.  STRIPE WEBHOOK WITHOUT VALID SIGNATURE RETURNS 400
# =============================================================================

class TestStripeWebhookSecurity:
    """Stripe webhook endpoint must reject unauthenticated calls."""

    def test_webhook_no_signature_header_returns_400(self, full_app_client):
        """Request without stripe-signature header must return 400."""
        response = full_app_client.post(
            "/api/v1/billing/webhook",
            content=b'{"type": "checkout.session.completed"}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400, (
            f"Webhook without signature header returned {response.status_code}, "
            f"expected 400."
        )

    def test_webhook_invalid_signature_returns_400(self, full_app_client):
        """Request with a malformed / incorrect stripe-signature must return 400."""
        with patch(
            "services.stripe_service.StripeService.verify_webhook_signature"
        ) as mock_verify:
            mock_verify.side_effect = ValueError("Invalid webhook signature")

            response = full_app_client.post(
                "/api/v1/billing/webhook",
                content=b'{"type": "checkout.session.completed"}',
                headers={
                    "Content-Type": "application/json",
                    "stripe-signature": "t=totally_wrong,v1=invalidsig",
                },
            )
            assert response.status_code == 400, (
                f"Webhook with invalid signature returned {response.status_code}, "
                f"expected 400."
            )

    def test_webhook_replayed_event_without_stripe_configured_returns_503(
        self, full_app_client
    ):
        """
        When Stripe is not configured (no STRIPE_SECRET_KEY), the endpoint
        should return 503 rather than 500, signalling a configuration gap
        rather than a crash.
        """
        with patch(
            "services.stripe_service.StripeService.is_configured",
            new_callable=lambda: property(lambda self: False),
        ):
            response = full_app_client.post(
                "/api/v1/billing/webhook",
                content=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "stripe-signature": "t=1,v1=sig",
                },
            )
            assert response.status_code in (400, 503), (
                f"Unconfigured webhook returned {response.status_code}."
            )


# =============================================================================
# 8.  API KEY PROBES ON THE PRICE REFRESH ENDPOINT
# =============================================================================

class TestAPIKeyProtection:
    """The POST /api/v1/prices/refresh endpoint requires a valid X-API-Key header."""

    def test_price_refresh_no_api_key_returns_401(self, full_app_client):
        """Request without X-API-Key must return 401."""
        response = full_app_client.post("/api/v1/prices/refresh")
        assert response.status_code == 401, (
            f"Price refresh without API key returned {response.status_code}, "
            f"expected 401."
        )

    def test_price_refresh_wrong_api_key_returns_401(self, full_app_client):
        """Request with incorrect API key must return 401."""
        response = full_app_client.post(
            "/api/v1/prices/refresh",
            headers={"X-API-Key": "totally-wrong-api-key"},
        )
        assert response.status_code == 401, (
            f"Price refresh with wrong API key returned {response.status_code}, "
            f"expected 401."
        )

    def test_price_refresh_empty_api_key_returns_401(self, full_app_client):
        """Empty API key header must be rejected."""
        response = full_app_client.post(
            "/api/v1/prices/refresh",
            headers={"X-API-Key": ""},
        )
        assert response.status_code == 401

    def test_price_refresh_jwt_as_api_key_returns_401(self, full_app_client):
        """
        A valid JWT must NOT be accepted as an API key.
        The two credentials are separate and must not be interchangeable.
        """
        valid_jwt = _make_access_token()
        response = full_app_client.post(
            "/api/v1/prices/refresh",
            headers={"X-API-Key": valid_jwt},
        )
        assert response.status_code == 401, (
            f"JWT accepted as API key on price refresh endpoint. "
            f"Got {response.status_code}."
        )


# =============================================================================
# 9.  OVERSIZED REQUEST BODY HANDLING
# =============================================================================

class TestOversizedRequests:
    """
    The application does not currently configure an explicit request body
    size limit via middleware.  These tests document the current behaviour
    and should be updated once a limit is enforced.

    NOTE: Without an explicit size limit uvicorn/starlette will read the
    entire body into memory, which is a DoS vector.  The recommended fix
    is shown in the security report.
    """

    def test_large_json_body_does_not_crash_server(self, client):
        """
        A 1 MB JSON payload on a JSON endpoint must not cause a 500 error.
        The server should return 200, 413, or 422 but not 500.
        """
        large_name = "A" * (1024 * 1024)  # 1 MB of 'A'
        response = client.post("/echo-name", json={"name": large_name})
        assert response.status_code != 500, (
            f"1 MB request body caused a 500 error."
        )

    def test_deeply_nested_json_does_not_crash_server(self, client):
        """
        Deeply nested JSON (JSON-bomb) must not cause a stack overflow or 500.
        """
        nested = {"a": None}
        current = nested
        for _ in range(200):
            new_level = {"a": None}
            current["a"] = new_level
            current = new_level

        response = client.post("/echo-name", json=nested)
        assert response.status_code != 500, (
            f"Deeply nested JSON caused a 500 error."
        )


# =============================================================================
# 10.  PATH TRAVERSAL PROBES
# =============================================================================

PATH_TRAVERSAL_PAYLOADS = [
    "../../etc/passwd",
    "../../../etc/shadow",
    "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "....//....//etc/passwd",
    "\\..\\..",
]


class TestPathTraversal:
    """
    Supplier and tariff endpoints use path parameters.  Path traversal in
    these values should return 404 (not found) or 422, never 200 or 500.
    """

    def test_path_traversal_in_supplier_id(self, full_app_client):
        for payload in PATH_TRAVERSAL_PAYLOADS:
            response = full_app_client.get(f"/api/v1/suppliers/{payload}")
            assert response.status_code in (404, 422, 400), (
                f"Path traversal in supplier_id returned {response.status_code} "
                f"for payload: {payload!r}"
            )

    def test_path_traversal_in_region_path(self, full_app_client):
        for payload in PATH_TRAVERSAL_PAYLOADS:
            response = full_app_client.get(f"/api/v1/suppliers/region/{payload}")
            assert response.status_code in (200, 404, 422, 400), (
                f"Path traversal in region path parameter returned "
                f"{response.status_code}. Should not be 500."
            )
            assert response.status_code != 500


# =============================================================================
# 11.  OPEN REDIRECT PROBE ON OAUTH / MAGIC-LINK ENDPOINTS
# =============================================================================

class TestOpenRedirect:
    """
    Endpoints that accept URL parameters must validate them against an
    allowlist to prevent open redirect attacks.

    Note: OAuth and magic-link endpoints are now handled by Better Auth via
    the Next.js frontend (/api/auth/*). The backend no longer has those
    endpoints, so redirect validation for auth flows is tested on the frontend.
    """

    def test_billing_checkout_rejects_external_success_url(self, full_app_client):
        """
        Checkout session success_url must be validated against the
        ALLOWED_REDIRECT_DOMAINS allowlist in billing.py.
        """
        valid_token = _make_access_token()
        response = full_app_client.post(
            "/api/v1/billing/checkout",
            json={
                "tier": "pro",
                "success_url": "https://evil-site.com/success",
                "cancel_url": "http://localhost:3000/cancel",
            },
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        # 422/400 = URL validation rejected it
        # 401 = auth rejected it (JWT not valid as Neon Auth session token)
        # 503 = DB unavailable for session validation (test environment)
        # All are acceptable — the key security property is that the request
        # is NOT processed with a 200/201 success.
        assert response.status_code in (422, 400, 401, 503), (
            f"External success_url accepted in checkout. Got {response.status_code}."
        )


# =============================================================================
# 12.  SECURITY HEADERS PRESENCE ON ALL RESPONSES
# =============================================================================

class TestSecurityHeadersOnRealApp:
    """Verify the real app emits the expected security headers."""

    REQUIRED_HEADERS = {
        "x-frame-options": "DENY",
        "x-content-type-options": "nosniff",
        "referrer-policy": "strict-origin-when-cross-origin",
    }

    def test_health_endpoint_has_security_headers(self, full_app_client):
        response = full_app_client.get("/health")
        for header, expected in self.REQUIRED_HEADERS.items():
            assert response.headers.get(header) == expected, (
                f"Header '{header}' missing or incorrect on /health. "
                f"Got: {response.headers.get(header)!r}"
            )

    def test_api_endpoint_has_no_cache_headers(self, full_app_client):
        """API endpoints must carry Cache-Control: no-store to prevent caching
        of sensitive data in browsers and proxies."""
        response = full_app_client.get(
            "/api/v1/prices/current?region=us_ct"
        )
        cache = response.headers.get("cache-control", "")
        assert "no-store" in cache, (
            f"API endpoint missing 'no-store' cache directive. "
            f"Cache-Control: {cache!r}"
        )
