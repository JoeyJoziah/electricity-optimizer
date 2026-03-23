"""
Tests for portal connection endpoints.

Coverage:
  POST /connections/portal        — create portal connection (success, validation,
                                    no consent, supplier not found, encryption)
  POST /connections/portal/{id}/scrape — trigger scrape (success, not found,
                                         decrypt error, scrape failure, rates persisted)

All async tests use the sync TestClient (FastAPI/Starlette converts them).
Database and service calls are fully mocked — no real Postgres connection is used.
Auth is injected by overriding ``require_paid_tier`` in dependency_overrides.
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Stable test IDs
# ---------------------------------------------------------------------------

TEST_USER_ID = "aaaaaaaa-1111-0000-0000-000000000001"
TEST_CONNECTION_ID = str(uuid4())
TEST_SUPPLIER_ID = str(uuid4())

BASE = "/api/v1/connections"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_data(user_id: str = TEST_USER_ID):
    """Build a SessionData-compatible object."""
    from auth.neon_auth import SessionData

    return SessionData(
        user_id=user_id,
        email=f"{user_id[:8]}@example.com",
        name="Test User",
        email_verified=True,
        role="user",
    )


def _mock_db() -> AsyncMock:
    """Return a fresh mock async DB session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _fetchone_result(row_tuple) -> MagicMock:
    """Mock execute() result whose fetchone() returns a tuple."""
    result = MagicMock()
    result.fetchone.return_value = row_tuple
    return result


def _empty_fetchone() -> MagicMock:
    """Mock execute() result whose fetchone() returns None."""
    result = MagicMock()
    result.fetchone.return_value = None
    return result


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Function-scoped TestClient with a clean rate limiter."""
    from main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_overrides():
    """Clear dependency_overrides and rate limiter after every test."""
    from main import _app_rate_limiter, app

    _app_rate_limiter.reset()
    yield
    for dep in list(app.dependency_overrides.keys()):
        app.dependency_overrides.pop(dep, None)
    _app_rate_limiter.reset()


def _install_auth(user_id: str = TEST_USER_ID):
    """Override require_paid_tier and get_db_session; return the db mock."""
    from api.dependencies import get_current_user, get_db_session
    from api.v1.connections import require_paid_tier
    from main import app

    session = _session_data(user_id=user_id)
    db = _mock_db()

    app.dependency_overrides[require_paid_tier] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: session
    app.dependency_overrides[get_db_session] = lambda: db

    return db


# ===========================================================================
# POST /connections/portal — create portal connection
# ===========================================================================


class TestCreatePortalConnection:
    """Tests for POST /api/v1/connections/portal."""

    def test_create_portal_connection_success(self, client):
        """Happy path: supplier found, credentials encrypted, 201 returned."""
        db = _install_auth()

        # Supplier lookup returns (id, name)
        supplier_row = (TEST_SUPPLIER_ID, "Duke Energy")

        # First execute call is the supplier lookup; second is the INSERT.
        db.execute = AsyncMock(
            side_effect=[
                _fetchone_result(supplier_row),
                AsyncMock(),  # INSERT
            ]
        )

        payload = {
            "supplier_id": TEST_SUPPLIER_ID,
            "portal_username": "user@example.com",
            "portal_password": "s3cr3t!",
            "portal_login_url": "https://www.duke-energy.com/sign-in",
            "consent_given": True,
        }

        # Patch encrypt_field in the portal_scrape module's namespace (where it was imported)
        with patch("api.v1.connections.portal_scrape.encrypt_field", return_value=b"\x00" * 28):
            response = client.post(f"{BASE}/portal", json=payload)

        assert response.status_code == 201
        body = response.json()
        assert body["supplier_id"] == TEST_SUPPLIER_ID
        assert body["portal_username"] == "user@example.com"
        assert body["portal_scrape_status"] == "pending"
        assert "connection_id" in body
        # Password must never be returned
        assert "portal_password" not in body
        assert "portal_password_encrypted" not in body

    def test_create_portal_connection_supplier_not_found(self, client):
        """Supplier missing in registry → 404."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=_empty_fetchone())

        payload = {
            "supplier_id": str(uuid4()),
            "portal_username": "user@example.com",
            "portal_password": "s3cr3t!",
            "consent_given": True,
        }

        response = client.post(f"{BASE}/portal", json=payload)
        assert response.status_code == 404

    def test_create_portal_connection_no_consent(self, client):
        """Missing consent → 422 validation error."""
        _install_auth()

        payload = {
            "supplier_id": TEST_SUPPLIER_ID,
            "portal_username": "user@example.com",
            "portal_password": "s3cr3t!",
            "consent_given": False,
        }

        response = client.post(f"{BASE}/portal", json=payload)
        assert response.status_code == 422

    def test_create_portal_connection_missing_password(self, client):
        """Empty password → 422 validation error (min_length=1)."""
        _install_auth()

        payload = {
            "supplier_id": TEST_SUPPLIER_ID,
            "portal_username": "user@example.com",
            "portal_password": "",
            "consent_given": True,
        }

        response = client.post(f"{BASE}/portal", json=payload)
        assert response.status_code == 422

    def test_create_portal_connection_password_encrypted_in_db(self, client):
        """Verify that encrypt_field is called with the plaintext password."""
        db = _install_auth()

        supplier_row = (TEST_SUPPLIER_ID, "PG&E")
        db.execute = AsyncMock(
            side_effect=[
                _fetchone_result(supplier_row),
                AsyncMock(),
            ]
        )

        payload = {
            "supplier_id": TEST_SUPPLIER_ID,
            "portal_username": "myuser",
            "portal_password": "mypassword123",
            "consent_given": True,
        }

        with patch("api.v1.connections.portal_scrape.encrypt_field") as mock_encrypt:
            mock_encrypt.return_value = b"\xde\xad\xbe\xef" * 7
            response = client.post(f"{BASE}/portal", json=payload)

        assert response.status_code == 201
        # encrypt_field is called for both password and username
        assert mock_encrypt.call_count == 2
        mock_encrypt.assert_any_call("mypassword123")
        mock_encrypt.assert_any_call("myuser")

    def test_create_portal_connection_without_login_url(self, client):
        """portal_login_url is optional — omitting it is valid."""
        db = _install_auth()

        supplier_row = (TEST_SUPPLIER_ID, "ComEd")
        db.execute = AsyncMock(
            side_effect=[
                _fetchone_result(supplier_row),
                AsyncMock(),
            ]
        )

        payload = {
            "supplier_id": TEST_SUPPLIER_ID,
            "portal_username": "user@comed.com",
            "portal_password": "pass",
            "consent_given": True,
            # portal_login_url deliberately omitted
        }

        with patch("api.v1.connections.portal_scrape.encrypt_field", return_value=b"\x00" * 28):
            response = client.post(f"{BASE}/portal", json=payload)

        assert response.status_code == 201
        assert response.json()["portal_login_url"] is None

    def test_create_portal_connection_requires_paid_tier(self, client):
        """Free-tier user must be rejected with 403."""
        from api.dependencies import get_current_user, get_db_session
        from api.v1.connections import require_paid_tier
        from main import app

        # Remove the pro override so real require_paid_tier runs
        app.dependency_overrides.pop(require_paid_tier, None)

        session = _session_data()
        db = _mock_db()

        # Return "free" when querying subscription_tier
        tier_result = MagicMock()
        tier_row = MagicMock()
        tier_row.__getitem__ = lambda self, k: "free"
        tier_result.fetchone.return_value = tier_row

        db.execute = AsyncMock(return_value=tier_result)

        app.dependency_overrides[get_current_user] = lambda: session
        app.dependency_overrides[get_db_session] = lambda: db

        payload = {
            "supplier_id": TEST_SUPPLIER_ID,
            "portal_username": "user@example.com",
            "portal_password": "pass",
            "consent_given": True,
        }
        response = client.post(f"{BASE}/portal", json=payload)
        assert response.status_code == 403


# ===========================================================================
# POST /connections/portal/{id}/scrape — trigger scrape
# ===========================================================================


class TestTriggerPortalScrape:
    """Tests for POST /api/v1/connections/portal/{connection_id}/scrape."""

    def _conn_row_tuple(
        self,
        connection_id: str = TEST_CONNECTION_ID,
        user_id: str = TEST_USER_ID,
        encrypted_b64: str | None = None,
        username_b64: str | None = None,
    ):
        """Return a mock DB row tuple for user_connections."""
        if encrypted_b64 is None:
            # Produce a valid base64-encoded AES-GCM ciphertext placeholder
            encrypted_b64 = base64.b64encode(b"\x00" * 40).decode("ascii")
        if username_b64 is None:
            username_b64 = base64.b64encode(b"\x00" * 40).decode("ascii")

        return (
            connection_id,  # id
            user_id,  # user_id
            TEST_SUPPLIER_ID,  # supplier_id
            username_b64,  # portal_username (encrypted+base64)
            encrypted_b64,  # portal_password_encrypted
            "https://duke-energy.com/sign-in",  # portal_login_url
            "pending",  # portal_scrape_status
        )

    def test_trigger_scrape_success(self, client):
        """Happy path: scrape succeeds, rates persisted, status → active."""
        db = _install_auth()

        conn_row = self._conn_row_tuple()
        db.execute = AsyncMock(
            side_effect=[
                _fetchone_result(conn_row),  # connection lookup
                AsyncMock(),  # INSERT rate
                AsyncMock(),  # UPDATE status
            ]
        )

        scrape_result = {
            "success": True,
            "rates": [{"rate_per_kwh": 0.12, "label": "portal_scrape"}],
            "error": None,
        }

        # PortalScraperService is imported lazily inside the endpoint function;
        # patch at the source module level so the import picks up the mock.
        with (
            patch("api.v1.connections.portal_scrape.decrypt_field", return_value="s3cr3t!"),
            patch(
                "services.portal_scraper_service.PortalScraperService",
                autospec=True,
            ) as MockSvc,
        ):
            instance = MockSvc.return_value.__aenter__.return_value
            instance.scrape_portal = AsyncMock(return_value=scrape_result)

            response = client.post(f"{BASE}/portal/{TEST_CONNECTION_ID}/scrape")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["rates_extracted"] == 1
        assert body["error"] is None
        assert body["connection_id"] == TEST_CONNECTION_ID

    def test_trigger_scrape_connection_not_found(self, client):
        """Connection missing or wrong user → 404."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=_empty_fetchone())

        response = client.post(f"{BASE}/portal/{TEST_CONNECTION_ID}/scrape")
        assert response.status_code == 404

    def test_trigger_scrape_decrypt_error(self, client):
        """Corrupt encrypted blob → 500."""
        db = _install_auth()

        conn_row = self._conn_row_tuple(encrypted_b64="not-valid-base64!!!")
        db.execute = AsyncMock(return_value=_fetchone_result(conn_row))

        # base64.b64decode will raise on invalid input
        response = client.post(f"{BASE}/portal/{TEST_CONNECTION_ID}/scrape")
        assert response.status_code == 500

    def test_trigger_scrape_failure_status(self, client):
        """When scrape service reports failure, status → 'failed' in response."""
        db = _install_auth()

        conn_row = self._conn_row_tuple()
        db.execute = AsyncMock(
            side_effect=[
                _fetchone_result(conn_row),
                AsyncMock(),  # UPDATE status
            ]
        )

        scrape_result = {
            "success": False,
            "rates": [],
            "error": "Login failed — credentials may be incorrect.",
        }

        with (
            patch("api.v1.connections.portal_scrape.decrypt_field", return_value="s3cr3t!"),
            patch(
                "services.portal_scraper_service.PortalScraperService",
                autospec=True,
            ) as MockSvc,
        ):
            instance = MockSvc.return_value.__aenter__.return_value
            instance.scrape_portal = AsyncMock(return_value=scrape_result)

            response = client.post(f"{BASE}/portal/{TEST_CONNECTION_ID}/scrape")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        assert body["rates_extracted"] == 0
        assert "Login failed" in body["error"]

    def test_trigger_scrape_no_rates_extracted(self, client):
        """Scrape succeeds but finds no rate data — rates_extracted = 0."""
        db = _install_auth()

        conn_row = self._conn_row_tuple()
        db.execute = AsyncMock(
            side_effect=[
                _fetchone_result(conn_row),
                AsyncMock(),  # UPDATE status
            ]
        )

        scrape_result = {
            "success": True,
            "rates": [],
            "error": None,
        }

        with (
            patch("api.v1.connections.portal_scrape.decrypt_field", return_value="s3cr3t!"),
            patch(
                "services.portal_scraper_service.PortalScraperService",
                autospec=True,
            ) as MockSvc,
        ):
            instance = MockSvc.return_value.__aenter__.return_value
            instance.scrape_portal = AsyncMock(return_value=scrape_result)

            response = client.post(f"{BASE}/portal/{TEST_CONNECTION_ID}/scrape")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["rates_extracted"] == 0

    def test_trigger_scrape_multiple_rates_persisted(self, client):
        """Multiple rates in the result → all inserted into connection_extracted_rates."""
        db = _install_auth()

        conn_row = self._conn_row_tuple()

        # Side effects: 1 lookup + 3 rate INSERTs + 1 status UPDATE
        execute_calls = [_fetchone_result(conn_row)] + [AsyncMock() for _ in range(4)]
        db.execute = AsyncMock(side_effect=execute_calls)

        scrape_result = {
            "success": True,
            "rates": [
                {"rate_per_kwh": 0.10, "label": "off-peak"},
                {"rate_per_kwh": 0.15, "label": "on-peak"},
                {"rate_per_kwh": 0.12, "label": "mid-peak"},
            ],
            "error": None,
        }

        with (
            patch("api.v1.connections.portal_scrape.decrypt_field", return_value="s3cr3t!"),
            patch(
                "services.portal_scraper_service.PortalScraperService",
                autospec=True,
            ) as MockSvc,
        ):
            instance = MockSvc.return_value.__aenter__.return_value
            instance.scrape_portal = AsyncMock(return_value=scrape_result)

            response = client.post(f"{BASE}/portal/{TEST_CONNECTION_ID}/scrape")

        assert response.status_code == 200
        body = response.json()
        assert body["rates_extracted"] == 3

    def test_trigger_scrape_requires_paid_tier(self, client):
        """Free-tier user cannot trigger a scrape."""
        from api.dependencies import get_current_user, get_db_session
        from api.v1.connections import require_paid_tier
        from main import app

        app.dependency_overrides.pop(require_paid_tier, None)

        session = _session_data()
        db = _mock_db()

        tier_result = MagicMock()
        tier_row = MagicMock()
        tier_row.__getitem__ = lambda self, k: "free"
        tier_result.fetchone.return_value = tier_row
        db.execute = AsyncMock(return_value=tier_result)

        app.dependency_overrides[get_current_user] = lambda: session
        app.dependency_overrides[get_db_session] = lambda: db

        response = client.post(f"{BASE}/portal/{TEST_CONNECTION_ID}/scrape")
        assert response.status_code == 403
