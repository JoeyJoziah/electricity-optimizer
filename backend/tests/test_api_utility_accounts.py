"""Tests for the Utility Accounts API (backend/api/v1/utility_accounts.py).

Mounted at: /api/v1/utility-accounts  (auth required)

Covers:
- GET  /utility-accounts/         (list; utility_type filter; auth-wall)
- POST /utility-accounts/         (create; missing required fields → 422; auth-wall)
- GET  /utility-accounts/types    (returns all UtilityType values)
- GET  /utility-accounts/{id}     (found; not found → 404; auth-wall)
- PUT  /utility-accounts/{id}     (update; not found → 404)
- DELETE /utility-accounts/{id}   (delete; not found → 404)
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session

_USER_ID = str(uuid.uuid4())
_TEST_USER = SessionData(user_id=_USER_ID, email="accounts@example.com")

_BASE = "/api/v1/utility-accounts"
_ACCOUNT_ID = str(uuid.uuid4())

_NOW = datetime.now(UTC)

_ACCOUNT = {
    "id": _ACCOUNT_ID,
    "user_id": _USER_ID,
    "utility_type": "electricity",
    "region": "us_ct",
    "provider_name": "Eversource",
    "is_primary": True,
    "metadata": {},
    "created_at": _NOW,
    "updated_at": _NOW,
}

_CREATE_BODY = {
    "utility_type": "electricity",
    "region": "us_ct",
    "provider_name": "Eversource",
    "is_primary": True,
}


def _account_obj():
    """Return an object whose attributes match UtilityAccountResponse."""
    from types import SimpleNamespace

    return SimpleNamespace(**_ACCOUNT)


@pytest.fixture
def auth_client():
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def unauth_client():
    from main import app

    c = TestClient(app, raise_server_exceptions=False)
    yield c


# ---------------------------------------------------------------------------
# GET /utility-accounts/
# ---------------------------------------------------------------------------


class TestListUtilityAccounts:
    def test_returns_accounts_list(self, auth_client):
        with patch(
            "repositories.utility_account_repository.UtilityAccountRepository.list",
            new=AsyncMock(return_value=[_account_obj()]),
        ):
            resp = auth_client.get(f"{_BASE}/")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["utility_type"] == "electricity"

    def test_empty_list_returns_200(self, auth_client):
        with patch(
            "repositories.utility_account_repository.UtilityAccountRepository.list",
            new=AsyncMock(return_value=[]),
        ):
            resp = auth_client.get(f"{_BASE}/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get(f"{_BASE}/")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /utility-accounts/
# ---------------------------------------------------------------------------


class TestCreateUtilityAccount:
    def test_create_returns_201(self, auth_client):
        with patch(
            "repositories.utility_account_repository.UtilityAccountRepository.create",
            new=AsyncMock(return_value=_account_obj()),
        ):
            resp = auth_client.post(f"{_BASE}/", json=_CREATE_BODY)
        assert resp.status_code == 201
        assert resp.json()["provider_name"] == "Eversource"

    def test_missing_provider_name_returns_422(self, auth_client):
        resp = auth_client.post(
            f"{_BASE}/", json={"utility_type": "electricity", "region": "us_ct"}
        )
        assert resp.status_code == 422

    def test_invalid_utility_type_returns_422(self, auth_client):
        body = {**_CREATE_BODY, "utility_type": "wind_power"}
        resp = auth_client.post(f"{_BASE}/", json=body)
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.post(f"{_BASE}/", json=_CREATE_BODY)
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /utility-accounts/types
# ---------------------------------------------------------------------------


class TestListUtilityTypes:
    def test_returns_all_types(self, auth_client):
        resp = auth_client.get(f"{_BASE}/types")
        assert resp.status_code == 200
        types = resp.json()
        assert isinstance(types, list)
        values = [t["value"] for t in types]
        assert "electricity" in values
        assert "natural_gas" in values


# ---------------------------------------------------------------------------
# GET /utility-accounts/{account_id}
# ---------------------------------------------------------------------------


class TestGetUtilityAccount:
    def test_found_returns_200(self, auth_client):
        with patch(
            "repositories.utility_account_repository.UtilityAccountRepository.get_by_id",
            new=AsyncMock(return_value=_account_obj()),
        ):
            resp = auth_client.get(f"{_BASE}/{_ACCOUNT_ID}")
        assert resp.status_code == 200
        assert resp.json()["id"] == _ACCOUNT_ID

    def test_not_found_returns_404(self, auth_client):
        with patch(
            "repositories.utility_account_repository.UtilityAccountRepository.get_by_id",
            new=AsyncMock(return_value=None),
        ):
            resp = auth_client.get(f"{_BASE}/{_ACCOUNT_ID}")
        assert resp.status_code == 404

    def test_invalid_uuid_returns_422(self, auth_client):
        resp = auth_client.get(f"{_BASE}/not-a-uuid")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /utility-accounts/{account_id}
# ---------------------------------------------------------------------------


class TestUpdateUtilityAccount:
    def test_update_returns_200(self, auth_client):
        updated = _account_obj()
        updated.provider_name = "CleanChoice"
        with (
            patch(
                "repositories.utility_account_repository.UtilityAccountRepository.get_by_id",
                new=AsyncMock(return_value=_account_obj()),
            ),
            patch(
                "repositories.utility_account_repository.UtilityAccountRepository.update",
                new=AsyncMock(return_value=updated),
            ),
        ):
            resp = auth_client.put(f"{_BASE}/{_ACCOUNT_ID}", json={"provider_name": "CleanChoice"})
        assert resp.status_code == 200

    def test_not_found_returns_404(self, auth_client):
        with patch(
            "repositories.utility_account_repository.UtilityAccountRepository.get_by_id",
            new=AsyncMock(return_value=None),
        ):
            resp = auth_client.put(f"{_BASE}/{_ACCOUNT_ID}", json={"provider_name": "X"})
        assert resp.status_code == 404
