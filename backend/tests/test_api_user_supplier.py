"""Tests for the User Supplier API (backend/api/v1/user_supplier.py).

Mounted at: /api/v1/user  (auth required for all endpoints)

Covers:
- PUT    /user/supplier              (supplier not found → 404; auth-wall)
- GET    /user/supplier              (no supplier → null; auth-wall)
- DELETE /user/supplier              (removes supplier; auth-wall)
- POST   /user/supplier/link         (valid; missing consent → 422; auth-wall)
- GET    /user/supplier/accounts     (returns accounts list; auth-wall)
- DELETE /user/supplier/accounts/{supplier_id}  (found; not found → 404)
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session

_USER_ID = str(uuid.uuid4())
_TEST_USER = SessionData(user_id=_USER_ID, email="supplier_user@example.com")
_SUPPLIER_ID = str(uuid.uuid4())

_BASE = "/api/v1/user"


def _db_no_supplier() -> AsyncMock:
    """DB mock where user has no current_supplier_id."""
    row = MagicMock()
    row.__getitem__ = lambda s, k: None  # all fields None
    row.__contains__ = lambda s, k: True
    mapping = MagicMock()
    mapping.first.return_value = None
    result = MagicMock()
    result.mappings.return_value = mapping
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


def _db_commit_only() -> AsyncMock:
    """DB mock for DELETE/UPDATE that just commits."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = str(uuid.uuid4())
    result.mappings.return_value.first.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def auth_client():
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db_session] = lambda: _db_no_supplier()
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
# GET /user/supplier
# ---------------------------------------------------------------------------


class TestGetCurrentSupplier:
    def test_no_supplier_returns_null(self, auth_client):
        resp = auth_client.get(f"{_BASE}/supplier")
        assert resp.status_code == 200
        assert resp.json()["supplier"] is None

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get(f"{_BASE}/supplier")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# PUT /user/supplier
# ---------------------------------------------------------------------------


class TestSetCurrentSupplier:
    def test_supplier_not_found_returns_404(self, auth_client):
        """User row found but supplier_registry lookup returns None → 404."""
        user_row = MagicMock()
        user_row.__getitem__ = lambda s, k: {"id": _USER_ID, "region": "us_ct"}.get(k)
        user_mapping = MagicMock()
        user_mapping.first.return_value = user_row

        supplier_mapping = MagicMock()
        supplier_mapping.first.return_value = None

        results = iter(
            [
                MagicMock(mappings=lambda: user_mapping),
                MagicMock(mappings=lambda: supplier_mapping),
            ]
        )
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=lambda *a, **kw: next(results))
        db.commit = AsyncMock()

        from main import app

        app.dependency_overrides[get_current_user] = lambda: _TEST_USER
        app.dependency_overrides[get_db_session] = lambda: db
        c = TestClient(app)
        resp = c.put(f"{_BASE}/supplier", json={"supplier_id": str(uuid.uuid4())})
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db_session, None)

        assert resp.status_code == 404

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.put(f"{_BASE}/supplier", json={"supplier_id": str(uuid.uuid4())})
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# DELETE /user/supplier
# ---------------------------------------------------------------------------


class TestRemoveCurrentSupplier:
    def test_removes_supplier_returns_200(self):
        db = _db_commit_only()
        from main import app

        app.dependency_overrides[get_current_user] = lambda: _TEST_USER
        app.dependency_overrides[get_db_session] = lambda: db
        c = TestClient(app)
        resp = c.delete(f"{_BASE}/supplier")
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db_session, None)

        assert resp.status_code == 200
        assert "removed" in resp.json()["message"].lower()

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.delete(f"{_BASE}/supplier")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /user/supplier/link
# ---------------------------------------------------------------------------

_VALID_LINK_BODY = {
    "supplier_id": str(uuid.uuid4()),
    "account_number": "ACC-12345",
    "consent_given": True,
}


class TestLinkSupplierAccount:
    def test_missing_consent_returns_422(self, auth_client):
        body = {**_VALID_LINK_BODY, "consent_given": False}
        resp = auth_client.post(f"{_BASE}/supplier/link", json=body)
        assert resp.status_code == 422

    def test_account_number_too_short_returns_422(self, auth_client):
        body = {**_VALID_LINK_BODY, "account_number": "AB"}
        resp = auth_client.post(f"{_BASE}/supplier/link", json=body)
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.post(f"{_BASE}/supplier/link", json=_VALID_LINK_BODY)
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /user/supplier/accounts
# ---------------------------------------------------------------------------


class TestGetLinkedAccounts:
    def test_returns_accounts_list(self, auth_client):
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)

        from main import app

        app.dependency_overrides[get_current_user] = lambda: _TEST_USER
        app.dependency_overrides[get_db_session] = lambda: db
        c = TestClient(app)
        resp = c.get(f"{_BASE}/supplier/accounts")
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db_session, None)

        assert resp.status_code == 200
        assert "accounts" in resp.json()

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get(f"{_BASE}/supplier/accounts")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# DELETE /user/supplier/accounts/{supplier_id}
# ---------------------------------------------------------------------------


class TestUnlinkSupplierAccount:
    def test_not_found_returns_404(self, auth_client):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()

        from main import app

        app.dependency_overrides[get_current_user] = lambda: _TEST_USER
        app.dependency_overrides[get_db_session] = lambda: db
        c = TestClient(app)
        resp = c.delete(f"{_BASE}/supplier/accounts/{_SUPPLIER_ID}")
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db_session, None)

        assert resp.status_code == 404

    def test_invalid_uuid_returns_422(self, auth_client):
        resp = auth_client.delete(f"{_BASE}/supplier/accounts/not-a-uuid")
        assert resp.status_code == 422
