"""
Tests for User Supplier Management API endpoints.

Tests cover:
- PUT /user/supplier — set current supplier
- GET /user/supplier — get current supplier
- DELETE /user/supplier — remove current supplier
- POST /user/supplier/link — link supplier account
- GET /user/supplier/accounts — get linked accounts
- DELETE /user/supplier/accounts/{id} — unlink account
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_data(user_id="test-user-123", email="test@example.com"):
    """Create a mock SessionData for auth."""
    from auth.neon_auth import SessionData
    return SessionData(user_id=user_id, email=email, name="Test User", email_verified=True)


def _mock_db():
    """Create a mock async DB session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Module-scoped fixture: single TestClient avoids stale event-loop / Redis
# middleware issues that surface when many TestClient instances are created
# across the full test suite.
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """Function-scoped TestClient so the rate limiter resets cleanly between tests."""
    from main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _override_auth_and_db(request):
    """
    Per-test fixture that injects auth + db dependency overrides.
    Tests store their mock_db on the class/module via `request.instance`.
    Cleans up only its own overrides (not conftest's).
    """
    from main import app
    from api.dependencies import get_current_user, get_db_session

    db = _mock_db()
    session_data = _make_session_data()

    app.dependency_overrides[get_current_user] = lambda: session_data
    app.dependency_overrides[get_db_session] = lambda: db

    # Stash mock_db so tests can configure side_effects
    if request.instance is not None:
        request.instance._db = db

    yield

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


# ---------------------------------------------------------------------------
# Tests: PUT /user/supplier
# ---------------------------------------------------------------------------

class TestSetCurrentSupplier:
    """Tests for PUT /api/v1/user/supplier."""

    def test_set_supplier_success(self, client):
        """Setting a valid, active supplier should succeed."""
        # Combined user check + region query (single round-trip)
        user_check_result = MagicMock()
        user_check_result.mappings.return_value.first.return_value = {
            "id": "test-user-123",
            "region": "us_ct",
        }

        supplier_result = MagicMock()
        supplier_result.mappings.return_value.first.return_value = {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "Eversource",
            "regions": ["us_ct", "us_ma"],
            "rating": 4.2,
            "green_energy": True,
            "website": "https://eversource.com",
            "is_active": True,
        }

        update_result = MagicMock()

        self._db.execute = AsyncMock(side_effect=[
            user_check_result,
            supplier_result,
            update_result,
        ])

        response = client.put(
            "/api/v1/user/supplier",
            json={"supplier_id": "00000000-0000-0000-0000-000000000001"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["supplier_name"] == "Eversource"
        assert data["green_energy"] is True

    def test_set_supplier_not_found(self, client):
        """Setting a non-existent supplier should return 404."""
        user_check_result = MagicMock()
        user_check_result.mappings.return_value.first.return_value = {
            "id": "test-user-123",
            "region": "us_ct",
        }

        supplier_result = MagicMock()
        supplier_result.mappings.return_value.first.return_value = None

        self._db.execute = AsyncMock(side_effect=[user_check_result, supplier_result])

        response = client.put(
            "/api/v1/user/supplier",
            json={"supplier_id": "00000000-0000-0000-0000-000000000099"},
        )

        assert response.status_code == 404

    def test_set_supplier_inactive(self, client):
        """Setting an inactive supplier should return 400."""
        user_check_result = MagicMock()
        user_check_result.mappings.return_value.first.return_value = {
            "id": "test-user-123",
            "region": "us_ct",
        }

        supplier_result = MagicMock()
        supplier_result.mappings.return_value.first.return_value = {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "Old Supplier",
            "regions": ["us_ct"],
            "rating": 3.0,
            "green_energy": False,
            "website": None,
            "is_active": False,
        }

        self._db.execute = AsyncMock(side_effect=[user_check_result, supplier_result])

        response = client.put(
            "/api/v1/user/supplier",
            json={"supplier_id": "00000000-0000-0000-0000-000000000001"},
        )

        assert response.status_code == 400
        assert "not currently active" in response.json()["detail"]

    def test_set_supplier_wrong_region(self, client):
        """Setting a supplier not in user's region should return 400."""
        user_check_result = MagicMock()
        user_check_result.mappings.return_value.first.return_value = {
            "id": "test-user-123",
            "region": "us_ct",
        }

        supplier_result = MagicMock()
        supplier_result.mappings.return_value.first.return_value = {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "Texas Only",
            "regions": ["us_tx"],
            "rating": 4.5,
            "green_energy": False,
            "website": None,
            "is_active": True,
        }

        self._db.execute = AsyncMock(side_effect=[
            user_check_result, supplier_result,
        ])

        response = client.put(
            "/api/v1/user/supplier",
            json={"supplier_id": "00000000-0000-0000-0000-000000000001"},
        )

        assert response.status_code == 400
        assert "not available in your region" in response.json()["detail"]

    def test_set_supplier_unauthenticated(self):
        """Unauthenticated request should return 401 or 503."""
        from main import app
        from api.dependencies import get_current_user, get_db_session

        # Remove auth override for this test only
        saved_auth = app.dependency_overrides.pop(get_current_user, None)
        saved_db = app.dependency_overrides.pop(get_db_session, None)

        try:
            with TestClient(app) as c:
                response = c.put(
                    "/api/v1/user/supplier",
                    json={"supplier_id": "00000000-0000-0000-0000-000000000001"},
                )
            assert response.status_code in (401, 503)
        finally:
            if saved_auth:
                app.dependency_overrides[get_current_user] = saved_auth
            if saved_db:
                app.dependency_overrides[get_db_session] = saved_db


# ---------------------------------------------------------------------------
# Tests: GET /user/supplier
# ---------------------------------------------------------------------------

class TestGetCurrentSupplier:
    """Tests for GET /api/v1/user/supplier."""

    def test_get_supplier_with_supplier_set(self, client):
        """Should return supplier details when one is set."""
        result = MagicMock()
        result.mappings.return_value.first.return_value = {
            "current_supplier_id": "00000000-0000-0000-0000-000000000001",
            "current_supplier": "Eversource",
            "sr_id": "00000000-0000-0000-0000-000000000001",
            "name": "Eversource",
            "regions": ["us_ct"],
            "rating": 4.2,
            "green_energy": True,
            "website": "https://eversource.com",
        }
        self._db.execute = AsyncMock(return_value=result)

        response = client.get("/api/v1/user/supplier")

        assert response.status_code == 200
        data = response.json()
        assert data["supplier"] is not None
        assert data["supplier"]["supplier_name"] == "Eversource"

    def test_get_supplier_none_set(self, client):
        """Should return null supplier when none is set."""
        result = MagicMock()
        result.mappings.return_value.first.return_value = {
            "current_supplier_id": None,
            "current_supplier": None,
            "sr_id": None,
            "name": None,
            "regions": None,
            "rating": None,
            "green_energy": None,
            "website": None,
        }
        self._db.execute = AsyncMock(return_value=result)

        response = client.get("/api/v1/user/supplier")

        assert response.status_code == 200
        assert response.json()["supplier"] is None


# ---------------------------------------------------------------------------
# Tests: DELETE /user/supplier
# ---------------------------------------------------------------------------

class TestRemoveSupplier:
    """Tests for DELETE /api/v1/user/supplier."""

    def test_remove_supplier(self, client):
        """Should clear the user's current supplier."""
        self._db.execute = AsyncMock(return_value=MagicMock())

        response = client.delete("/api/v1/user/supplier")

        assert response.status_code == 200
        assert response.json()["message"] == "Supplier removed"


# ---------------------------------------------------------------------------
# Tests: POST /user/supplier/link
# ---------------------------------------------------------------------------

class TestLinkAccount:
    """Tests for POST /api/v1/user/supplier/link."""

    def test_link_account_success(self, client):
        """Linking with valid data and consent should succeed."""
        user_check = MagicMock()
        user_check.scalar_one_or_none.return_value = "test-user-123"

        supplier_result = MagicMock()
        supplier_result.mappings.return_value.first.return_value = {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "Eversource",
            "regions": ["us_ct"],
            "rating": 4.2,
            "green_energy": True,
            "website": None,
            "is_active": True,
        }

        insert_result = MagicMock()

        self._db.execute = AsyncMock(side_effect=[user_check, supplier_result, insert_result])

        with patch("api.v1.user_supplier.encrypt_field", return_value=b"encrypted"):
            response = client.post(
                "/api/v1/user/supplier/link",
                json={
                    "supplier_id": "00000000-0000-0000-0000-000000000001",
                    "account_number": "1234567890",
                    "consent_given": True,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["supplier_name"] == "Eversource"
            assert data["account_number_masked"] == "******7890"

    def test_link_account_no_consent(self, client):
        """Linking without consent should return 422."""
        response = client.post(
            "/api/v1/user/supplier/link",
            json={
                "supplier_id": "00000000-0000-0000-0000-000000000001",
                "account_number": "1234567890",
                "consent_given": False,
            },
        )

        assert response.status_code == 422

    def test_link_account_invalid_format(self, client):
        """Account number with special chars should return 422."""
        response = client.post(
            "/api/v1/user/supplier/link",
            json={
                "supplier_id": "00000000-0000-0000-0000-000000000001",
                "account_number": "abc@#$!",
                "consent_given": True,
            },
        )

        assert response.status_code == 422

    def test_link_account_too_short(self, client):
        """Account number shorter than 4 chars should return 422."""
        response = client.post(
            "/api/v1/user/supplier/link",
            json={
                "supplier_id": "00000000-0000-0000-0000-000000000001",
                "account_number": "AB",
                "consent_given": True,
            },
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Tests: GET /user/supplier/accounts
# ---------------------------------------------------------------------------

class TestGetLinkedAccounts:
    """Tests for GET /api/v1/user/supplier/accounts."""

    def test_get_accounts_empty(self, client):
        """Should return empty list when no accounts linked."""
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        self._db.execute = AsyncMock(return_value=result)

        response = client.get("/api/v1/user/supplier/accounts")

        assert response.status_code == 200
        assert response.json()["accounts"] == []


# ---------------------------------------------------------------------------
# Tests: DELETE /user/supplier/accounts/{supplier_id}
# ---------------------------------------------------------------------------

class TestUnlinkAccount:
    """Tests for DELETE /api/v1/user/supplier/accounts/{supplier_id}."""

    def test_unlink_success(self, client):
        """Should delete the linked account."""
        result = MagicMock()
        result.scalar_one_or_none.return_value = "some-id"
        self._db.execute = AsyncMock(return_value=result)

        response = client.delete(
            "/api/v1/user/supplier/accounts/00000000-0000-0000-0000-000000000001"
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Account unlinked"

    def test_unlink_not_found(self, client):
        """Should return 404 when account not found."""
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        self._db.execute = AsyncMock(return_value=result)

        response = client.delete(
            "/api/v1/user/supplier/accounts/00000000-0000-0000-0000-000000000001"
        )

        assert response.status_code == 404
