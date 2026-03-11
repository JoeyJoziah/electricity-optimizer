"""
Tests for Utility Accounts API endpoints.

Tests cover:
- GET /utility-accounts — list current user's accounts
- POST /utility-accounts — create account
- GET /utility-accounts/{id} — get single account
- PUT /utility-accounts/{id} — update account (ownership enforced)
- DELETE /utility-accounts/{id} — delete account (ownership enforced)
- GET /utility-accounts/types — list utility types
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER_ID = "test-user-123"
OTHER_USER_ID = "other-user-456"
ACCOUNT_ID = "00000000-0000-0000-0000-000000000001"

NOW = datetime(2026, 3, 11, 12, 0, 0, tzinfo=timezone.utc)


def _make_session_data(user_id=USER_ID, email="test@example.com"):
    from auth.neon_auth import SessionData
    return SessionData(user_id=user_id, email=email, name="Test User", email_verified=True)


def _mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _account_row(
    id=ACCOUNT_ID,
    user_id=USER_ID,
    utility_type="electricity",
    region="us_ct",
    provider_name="Eversource",
    is_primary=False,
    metadata=None,
):
    return {
        "id": id,
        "user_id": user_id,
        "utility_type": utility_type,
        "region": region,
        "provider_name": provider_name,
        "is_primary": is_primary,
        "metadata": metadata or {},
        "created_at": NOW,
        "updated_at": NOW,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _override_deps(request):
    from main import app
    from api.dependencies import get_current_user, get_db_session

    db = _mock_db()
    session_data = _make_session_data()

    app.dependency_overrides[get_current_user] = lambda: session_data
    app.dependency_overrides[get_db_session] = lambda: db

    if request.instance is not None:
        request.instance._db = db

    yield

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


# ---------------------------------------------------------------------------
# Tests: GET /utility-accounts/types
# ---------------------------------------------------------------------------

class TestListUtilityTypes:
    def test_returns_utility_types(self, client):
        resp = client.get("/api/v1/utility-accounts/types")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # Each item should have value and label
        for item in data:
            assert "value" in item
            assert "label" in item
        # electricity should be in the list
        values = [item["value"] for item in data]
        assert "electricity" in values


# ---------------------------------------------------------------------------
# Tests: GET /utility-accounts
# ---------------------------------------------------------------------------

class TestListAccounts:
    def test_list_empty(self, client):
        """No accounts returns empty list."""
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        self._db.execute.return_value = result

        resp = client.get("/api/v1/utility-accounts/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_accounts(self, client):
        """Accounts are returned for current user."""
        result = MagicMock()
        result.mappings.return_value.all.return_value = [_account_row()]
        self._db.execute.return_value = result

        resp = client.get("/api/v1/utility-accounts/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == ACCOUNT_ID
        assert data[0]["utility_type"] == "electricity"
        assert data[0]["provider_name"] == "Eversource"

    def test_list_filter_by_type(self, client):
        """Filter by utility_type query param."""
        result = MagicMock()
        result.mappings.return_value.all.return_value = [
            _account_row(utility_type="natural_gas", provider_name="CNG"),
        ]
        self._db.execute.return_value = result

        resp = client.get("/api/v1/utility-accounts/?utility_type=natural_gas")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["utility_type"] == "natural_gas"


# ---------------------------------------------------------------------------
# Tests: POST /utility-accounts
# ---------------------------------------------------------------------------

class TestCreateAccount:
    def test_create_success(self, client):
        """Valid payload creates account."""
        result = MagicMock()
        result.mappings.return_value.first.return_value = _account_row()
        self._db.execute.return_value = result

        resp = client.post("/api/v1/utility-accounts/", json={
            "utility_type": "electricity",
            "region": "us_ct",
            "provider_name": "Eversource",
            "is_primary": False,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider_name"] == "Eversource"
        assert data["utility_type"] == "electricity"
        assert data["region"] == "us_ct"
        # Should not contain encrypted account_number
        assert "account_number_encrypted" not in data

    def test_create_with_account_number(self, client):
        """Optional account_number is accepted."""
        result = MagicMock()
        result.mappings.return_value.first.return_value = _account_row()
        self._db.execute.return_value = result

        resp = client.post("/api/v1/utility-accounts/", json={
            "utility_type": "electricity",
            "region": "us_ct",
            "provider_name": "Eversource",
            "account_number": "12345",
        })
        assert resp.status_code == 201

    def test_create_missing_required_fields(self, client):
        """Missing required fields returns 422."""
        resp = client.post("/api/v1/utility-accounts/", json={
            "provider_name": "Eversource",
        })
        assert resp.status_code == 422

    def test_create_invalid_region_too_short(self, client):
        """Region must be at least 2 chars."""
        resp = client.post("/api/v1/utility-accounts/", json={
            "utility_type": "electricity",
            "region": "x",
            "provider_name": "Eversource",
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests: GET /utility-accounts/{id}
# ---------------------------------------------------------------------------

class TestGetAccount:
    def test_get_own_account(self, client):
        """Get an account that belongs to the current user."""
        result = MagicMock()
        result.mappings.return_value.first.return_value = _account_row()
        self._db.execute.return_value = result

        resp = client.get(f"/api/v1/utility-accounts/{ACCOUNT_ID}")
        assert resp.status_code == 200
        assert resp.json()["id"] == ACCOUNT_ID

    def test_get_nonexistent_account(self, client):
        """404 for missing account."""
        result = MagicMock()
        result.mappings.return_value.first.return_value = None
        self._db.execute.return_value = result

        resp = client.get("/api/v1/utility-accounts/nonexistent-id")
        assert resp.status_code == 404

    def test_get_other_users_account(self, client):
        """403 when trying to access another user's account."""
        result = MagicMock()
        result.mappings.return_value.first.return_value = _account_row(user_id=OTHER_USER_ID)
        self._db.execute.return_value = result

        resp = client.get(f"/api/v1/utility-accounts/{ACCOUNT_ID}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: PUT /utility-accounts/{id}
# ---------------------------------------------------------------------------

class TestUpdateAccount:
    def test_update_provider_name(self, client):
        """Update provider_name on own account."""
        existing_row = _account_row()
        updated_row = {**existing_row, "provider_name": "UI"}

        result_existing = MagicMock()
        result_existing.mappings.return_value.first.return_value = existing_row

        result_updated = MagicMock()
        result_updated.mappings.return_value.first.return_value = updated_row

        self._db.execute.side_effect = [result_existing, result_updated]

        resp = client.put(f"/api/v1/utility-accounts/{ACCOUNT_ID}", json={
            "provider_name": "UI",
        })
        assert resp.status_code == 200
        assert resp.json()["provider_name"] == "UI"

    def test_update_nonexistent(self, client):
        """404 for updating missing account."""
        result = MagicMock()
        result.mappings.return_value.first.return_value = None
        self._db.execute.return_value = result

        resp = client.put("/api/v1/utility-accounts/nonexistent-id", json={
            "provider_name": "Test",
        })
        assert resp.status_code == 404

    def test_update_other_users_account(self, client):
        """403 when trying to update another user's account."""
        result = MagicMock()
        result.mappings.return_value.first.return_value = _account_row(user_id=OTHER_USER_ID)
        self._db.execute.return_value = result

        resp = client.put(f"/api/v1/utility-accounts/{ACCOUNT_ID}", json={
            "provider_name": "Hacked",
        })
        assert resp.status_code == 403

    def test_update_is_primary(self, client):
        """Toggle is_primary flag."""
        existing_row = _account_row()
        updated_row = {**existing_row, "is_primary": True}

        result_existing = MagicMock()
        result_existing.mappings.return_value.first.return_value = existing_row

        result_updated = MagicMock()
        result_updated.mappings.return_value.first.return_value = updated_row

        self._db.execute.side_effect = [result_existing, result_updated]

        resp = client.put(f"/api/v1/utility-accounts/{ACCOUNT_ID}", json={
            "is_primary": True,
        })
        assert resp.status_code == 200
        assert resp.json()["is_primary"] is True


# ---------------------------------------------------------------------------
# Tests: DELETE /utility-accounts/{id}
# ---------------------------------------------------------------------------

class TestDeleteAccount:
    def test_delete_own_account(self, client):
        """Delete own account returns 204."""
        # First call: get_by_id (ownership check)
        result_get = MagicMock()
        result_get.mappings.return_value.first.return_value = _account_row()

        # Second call: DELETE returns rowcount > 0
        result_delete = MagicMock()
        result_delete.rowcount = 1

        self._db.execute.side_effect = [result_get, result_delete]

        resp = client.delete(f"/api/v1/utility-accounts/{ACCOUNT_ID}")
        assert resp.status_code == 204

    def test_delete_nonexistent(self, client):
        """404 for deleting missing account."""
        result = MagicMock()
        result.mappings.return_value.first.return_value = None
        self._db.execute.return_value = result

        resp = client.delete("/api/v1/utility-accounts/nonexistent-id")
        assert resp.status_code == 404

    def test_delete_other_users_account(self, client):
        """403 when trying to delete another user's account."""
        result = MagicMock()
        result.mappings.return_value.first.return_value = _account_row(user_id=OTHER_USER_ID)
        self._db.execute.return_value = result

        resp = client.delete(f"/api/v1/utility-accounts/{ACCOUNT_ID}")
        assert resp.status_code == 403
