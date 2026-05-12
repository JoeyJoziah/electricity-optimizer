"""
Tests for the internal portal scanning endpoint.

Coverage:
  POST /internal/scrape-portals
    - no active portal connections → returns empty summary
    - single connection: success + rates persisted
    - single connection: decrypt failure → counted as failed
    - single connection: scrape service failure → counted as failed
    - multiple connections with mixed results → tally correct
    - unauthenticated request (missing X-API-Key) → 403

All DB calls are mocked — no real Postgres connection is used.
PortalScraperService is patched to avoid real HTTP calls.
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session, get_redis, verify_api_key

BASE_URL = "/api/v1/internal"

# Stable IDs for test rows
TEST_USER_ID = "aaaaaaaa-2222-0000-0000-000000000002"
TEST_SUPPLIER_ID = str(uuid4())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conn_row(
    connection_id: str | None = None,
    encrypted_b64: str | None = None,
    username_b64: str | None = None,
) -> tuple:
    """Build a user_connections row tuple matching the SELECT in portal_scan.py."""
    if connection_id is None:
        connection_id = str(uuid4())
    if encrypted_b64 is None:
        # Valid base64-encoded placeholder ciphertext
        encrypted_b64 = base64.b64encode(b"\x00" * 40).decode("ascii")
    if username_b64 is None:
        username_b64 = base64.b64encode(b"\x00" * 40).decode("ascii")

    return (
        connection_id,  # id
        TEST_USER_ID,  # user_id
        TEST_SUPPLIER_ID,  # supplier_id
        username_b64,  # portal_username (encrypted+base64)
        encrypted_b64,  # portal_password_encrypted
        "https://duke-energy.com/sign-in",  # portal_login_url
    )


def _fetchall_result(rows: list) -> MagicMock:
    """Mock execute() result whose fetchall() returns the given list."""
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


def _empty_fetchall() -> MagicMock:
    """Mock execute() result whose fetchall() returns empty list."""
    return _fetchall_result([])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Mock async database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    return AsyncMock()


@pytest.fixture
def auth_client(mock_db, mock_redis):
    """TestClient with API key verified and mocked DB/Redis."""
    from main import app

    app.dependency_overrides[verify_api_key] = lambda: True
    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_redis, None)


@pytest.fixture
def unauth_client(mock_db, mock_redis):
    """TestClient without API key override (real auth runs)."""
    from main import app

    # Ensure no prior verify_api_key override
    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_redis, None)


# ===========================================================================
# POST /internal/scrape-portals
# ===========================================================================


class TestScrapeAllPortals:
    """Tests for POST /api/v1/internal/scrape-portals."""

    # -----------------------------------------------------------------------
    # Authentication
    # -----------------------------------------------------------------------

    def test_unauthenticated_request_rejected(self, unauth_client):
        """Missing X-API-Key → 403 (or 401)."""
        response = unauth_client.post(f"{BASE_URL}/scrape-portals", json={})
        assert response.status_code in (401, 403)

    # -----------------------------------------------------------------------
    # No connections
    # -----------------------------------------------------------------------

    def test_no_active_portal_connections(self, auth_client, mock_db):
        """When no active portal connections exist, return empty summary."""
        mock_db.execute = AsyncMock(return_value=_empty_fetchall())

        response = auth_client.post(f"{BASE_URL}/scrape-portals", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["total"] == 0
        assert body["succeeded"] == 0
        assert body["failed"] == 0
        assert body["errors"] == []

    # -----------------------------------------------------------------------
    # Single connection — success
    # -----------------------------------------------------------------------

    def test_single_connection_success(self, auth_client, mock_db):
        """One active connection: scrape succeeds, rates persisted."""
        conn_row = _make_conn_row()

        # Call sequence for _scrape_one (per connection):
        #   1. fetchall for the main query
        #   2. INSERT into connection_extracted_rates (for each rate)
        #   3. UPDATE portal_scrape_status
        mock_db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([conn_row]),  # main SELECT
                AsyncMock(),  # INSERT rate
                AsyncMock(),  # UPDATE status
            ]
        )

        scrape_result = {
            "success": True,
            "rates": [{"rate_per_kwh": 0.1234, "label": "portal_scrape"}],
            "error": None,
        }

        with (
            patch("api.v1.internal.portal_scan.decrypt_field", return_value="s3cr3t!"),
            patch(
                "services.portal_scraper_service.PortalScraperService", autospec=True
            ) as MockSvc,
        ):
            instance = MockSvc.return_value.__aenter__.return_value
            instance.scrape_portal = AsyncMock(return_value=scrape_result)

            response = auth_client.post(f"{BASE_URL}/scrape-portals", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["total"] == 1
        assert body["succeeded"] == 1
        assert body["failed"] == 0

    # -----------------------------------------------------------------------
    # Single connection — decrypt error
    # -----------------------------------------------------------------------

    def test_single_connection_decrypt_failure(self, auth_client, mock_db):
        """Corrupt encrypted blob: decrypt error counted as failed."""
        conn_row = _make_conn_row(encrypted_b64="NOT-VALID-BASE64!!!")

        mock_db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([conn_row]),  # main SELECT
                AsyncMock(),  # UPDATE status (called even on error)
            ]
        )

        response = auth_client.post(f"{BASE_URL}/scrape-portals", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["failed"] == 1
        assert body["succeeded"] == 0
        assert len(body["errors"]) == 1

    # -----------------------------------------------------------------------
    # Single connection — service failure
    # -----------------------------------------------------------------------

    def test_single_connection_service_failure(self, auth_client, mock_db):
        """Scrape service reports failure → counted as failed."""
        conn_row = _make_conn_row()

        mock_db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([conn_row]),  # main SELECT
                AsyncMock(),  # UPDATE status
            ]
        )

        scrape_result = {
            "success": False,
            "rates": [],
            "error": "Login failed — credentials may be incorrect.",
        }

        with (
            patch("api.v1.internal.portal_scan.decrypt_field", return_value="s3cr3t!"),
            patch(
                "services.portal_scraper_service.PortalScraperService", autospec=True
            ) as MockSvc,
        ):
            instance = MockSvc.return_value.__aenter__.return_value
            instance.scrape_portal = AsyncMock(return_value=scrape_result)

            response = auth_client.post(f"{BASE_URL}/scrape-portals", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["failed"] == 1
        assert body["succeeded"] == 0
        # Error string should appear in the errors list
        assert any("Login failed" in err for err in body["errors"])

    # -----------------------------------------------------------------------
    # Multiple connections — mixed results
    # -----------------------------------------------------------------------

    def test_multiple_connections_mixed_results(self, auth_client, mock_db):
        """Two connections: one succeeds, one fails → tally is 1/1."""
        conn_row_ok = _make_conn_row()
        conn_row_bad = _make_conn_row(encrypted_b64="INVALID-BASE64!!!")

        # Main SELECT returns two rows; subsequent execute calls are per-connection
        mock_db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([conn_row_ok, conn_row_bad]),  # main SELECT
                AsyncMock(),  # INSERT rate (success conn)
                AsyncMock(),  # UPDATE status (success conn)
                AsyncMock(),  # UPDATE status (failed conn — decrypt error)
            ]
        )

        scrape_result_ok = {
            "success": True,
            "rates": [{"rate_per_kwh": 0.10, "label": "portal_scrape"}],
            "error": None,
        }

        with (
            patch(
                "api.v1.internal.portal_scan.decrypt_field",
                side_effect=["s3cr3t!", Exception("bad base64")],
            ),
            patch(
                "services.portal_scraper_service.PortalScraperService", autospec=True
            ) as MockSvc,
        ):
            instance = MockSvc.return_value.__aenter__.return_value
            instance.scrape_portal = AsyncMock(return_value=scrape_result_ok)

            response = auth_client.post(f"{BASE_URL}/scrape-portals", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert body["succeeded"] + body["failed"] == 2
        # At least one failure
        assert body["failed"] >= 1

    # -----------------------------------------------------------------------
    # Multiple connections — all succeed
    # -----------------------------------------------------------------------

    def test_multiple_connections_all_succeed(self, auth_client, mock_db):
        """Three connections, all succeed → succeeded=3, failed=0."""
        rows = [_make_conn_row() for _ in range(3)]

        # 1 main SELECT + (1 INSERT rate + 1 UPDATE status) * 3 connections
        side_effects = [_fetchall_result(rows)]
        for _ in range(3):
            side_effects.append(AsyncMock())  # INSERT rate
            side_effects.append(AsyncMock())  # UPDATE status
        mock_db.execute = AsyncMock(side_effect=side_effects)

        scrape_result = {
            "success": True,
            "rates": [{"rate_per_kwh": 0.11, "label": "portal_scrape"}],
            "error": None,
        }

        with (
            patch("api.v1.internal.portal_scan.decrypt_field", return_value="s3cr3t!"),
            patch(
                "services.portal_scraper_service.PortalScraperService", autospec=True
            ) as MockSvc,
        ):
            instance = MockSvc.return_value.__aenter__.return_value
            instance.scrape_portal = AsyncMock(return_value=scrape_result)

            response = auth_client.post(f"{BASE_URL}/scrape-portals", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert body["succeeded"] == 3
        assert body["failed"] == 0
        assert body["errors"] == []

    # -----------------------------------------------------------------------
    # Response shape
    # -----------------------------------------------------------------------

    def test_response_contains_required_fields(self, auth_client, mock_db):
        """Response always includes status, total, succeeded, failed, errors."""
        mock_db.execute = AsyncMock(return_value=_empty_fetchall())

        response = auth_client.post(f"{BASE_URL}/scrape-portals", json={})

        assert response.status_code == 200
        body = response.json()
        for field in ("status", "total", "succeeded", "failed", "errors"):
            assert field in body, f"Missing field: {field!r}"

    def test_accepts_empty_json_body(self, auth_client, mock_db):
        """Endpoint accepts empty {} body (no required payload)."""
        mock_db.execute = AsyncMock(return_value=_empty_fetchall())

        response = auth_client.post(f"{BASE_URL}/scrape-portals", json={})
        assert response.status_code == 200

    def test_accepts_no_body(self, auth_client, mock_db):
        """Endpoint accepts requests with no body at all."""
        mock_db.execute = AsyncMock(return_value=_empty_fetchall())

        response = auth_client.post(
            f"{BASE_URL}/scrape-portals",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200


# ===========================================================================
# Error sanitization — exception text must NEVER reach the client
# ===========================================================================


class TestPortalScanErrorSanitization:
    """Verify that exception details in _scrape_one are sanitized before
    they appear in the HTTP response.

    The ``errors`` list in the response body must NOT contain raw exception
    strings from decrypt failures or scrape exceptions — those can include
    AES key material, connection strings, or library internals.
    """

    def test_decrypt_error_in_response_is_generic(self, auth_client, mock_db):
        """Credential decrypt failure should produce a generic error message,
        not the raw exception string (which may include algorithm details)."""
        conn_row = _make_conn_row(encrypted_b64="NOT-VALID-BASE64!!!")

        mock_db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([conn_row]),  # main SELECT
                AsyncMock(),  # UPDATE status (called even on error)
            ]
        )

        response = auth_client.post(f"{BASE_URL}/scrape-portals", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["failed"] == 1

        # The errors list is returned by the endpoint and must not expose
        # raw exception internals (e.g. AES key details, C library paths,
        # internal method names prefixed with underscores).
        for err_str in body["errors"]:
            # Must not contain raw Python exception class paths
            assert "Traceback" not in err_str
            assert "__" not in err_str  # double-underscore == internal dunder

    def test_scrape_exception_error_in_response_is_generic(self, auth_client, mock_db):
        """When PortalScraperService raises an exception, the error string
        persisted into the response must not contain DATABASE_URL or secrets."""
        conn_row = _make_conn_row()

        mock_db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([conn_row]),  # main SELECT
                AsyncMock(),  # UPDATE status
            ]
        )

        sensitive_exc_msg = (
            "Connection failed: DATABASE_URL=postgresql://admin:hunter2@prod.db/app"
        )

        with (
            patch("api.v1.internal.portal_scan.decrypt_field", return_value="s3cr3t!"),
            patch(
                "services.portal_scraper_service.PortalScraperService", autospec=True
            ) as MockSvc,
        ):
            instance = MockSvc.return_value.__aenter__.return_value
            instance.scrape_portal = AsyncMock(side_effect=Exception(sensitive_exc_msg))

            response = auth_client.post(f"{BASE_URL}/scrape-portals", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["failed"] == 1

        # The full sensitive exception message must not leak into the HTTP response
        full_body = response.text
        assert "hunter2" not in full_body
        assert "postgresql://" not in full_body
        assert "DATABASE_URL" not in full_body

    def test_decrypt_error_message_is_sanitized_not_raw_exception(
        self, auth_client, mock_db
    ):
        """The error message for a decrypt failure must be a generic string,
        not contain the raw exception type or AES internals."""
        conn_row = _make_conn_row()

        mock_db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([conn_row]),  # main SELECT
                AsyncMock(),  # UPDATE status
            ]
        )

        sensitive_exc_msg = (
            "AES-256-GCM tag verification failed: HMAC mismatch at offset 32"
        )

        with patch(
            "api.v1.internal.portal_scan.decrypt_field",
            side_effect=Exception(sensitive_exc_msg),
        ):
            response = auth_client.post(f"{BASE_URL}/scrape-portals", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["failed"] == 1

        full_body = response.text
        assert "AES-256-GCM" not in full_body
        assert "HMAC mismatch" not in full_body
        assert "offset 32" not in full_body
