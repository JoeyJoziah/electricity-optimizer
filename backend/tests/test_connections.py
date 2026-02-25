"""
Tests for Connection Feature API endpoints.

Coverage:
  - Paid-tier gate (401 / 403 enforcement)
  - List connections (empty, multiple, ownership scoping)
  - Create direct connection (success, bad supplier, no consent, duplicate, encryption)
  - Create email connection (Gmail, Outlook, invalid provider, no consent)
  - Upload stub (creation, consent required, response shape)
  - Get single connection (success, not found, wrong user)
  - Delete connection (success, not found, wrong user)
  - Get rates (empty, all, current)
  - Pydantic model validation + serialisation

All async tests are decorated with ``@pytest.mark.asyncio``.
Database calls are fully mocked via ``AsyncMock``; no real Postgres connection
is used.  Auth is injected by overriding ``get_current_user`` and
``get_db_session`` in ``app.dependency_overrides``.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Stable test IDs
# ---------------------------------------------------------------------------

TEST_USER_ID = "aaaaaaaa-0000-0000-0000-000000000001"
TEST_OTHER_USER_ID = "bbbbbbbb-0000-0000-0000-000000000002"
TEST_CONNECTION_ID = str(uuid4())
TEST_SUPPLIER_ID = str(uuid4())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_data(user_id: str = TEST_USER_ID, tier: str = "pro"):
    """Build a SessionData-compatible object for dependency injection."""
    from auth.neon_auth import SessionData

    sd = SessionData(
        user_id=user_id,
        email=f"{user_id[:8]}@example.com",
        name="Test User",
        email_verified=True,
        role="user",
    )
    # Attach tier so tests can inspect it; not a real field on SessionData.
    sd._tier = tier
    return sd


def _mock_db() -> AsyncMock:
    """Return a fresh mock async DB session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


class _DictRow(dict):
    """
    A dict subclass that behaves like a SQLAlchemy RowMapping.

    ``dict(row)`` works because it is already a dict.
    ``row["key"]`` works via normal dict __getitem__.
    ``row.items()`` works as a standard dict method.
    This avoids all MagicMock protocol issues.
    """


def _row(**kwargs) -> "_DictRow":
    """Build a dict-like row that supports dict(row), row['key'], and row.items()."""
    return _DictRow(kwargs)


def _mapping_result(rows: list) -> MagicMock:
    """Wrap a list of plain dicts into a mock execute() result.

    Uses _DictRow so that ``dict(row)`` in the router works correctly.
    """
    result = MagicMock()
    mock_rows = [_DictRow(r) for r in rows]
    result.mappings.return_value.all.return_value = mock_rows
    result.mappings.return_value.first.return_value = mock_rows[0] if mock_rows else None
    result.fetchone.return_value = mock_rows[0] if mock_rows else None
    return result


def _empty_mapping_result() -> MagicMock:
    """Mock execute() result for queries that return no rows."""
    result = MagicMock()
    result.mappings.return_value.all.return_value = []
    result.mappings.return_value.first.return_value = None
    result.fetchone.return_value = None
    return result


def _scalar_result(value) -> MagicMock:
    """Mock execute() result for scalar queries (subscription_tier)."""
    result = MagicMock()
    row = MagicMock()
    row.__getitem__ = lambda self, k: value
    result.fetchone.return_value = row
    result.scalar_one_or_none.return_value = value
    return result


# ---------------------------------------------------------------------------
# Module-scoped TestClient to avoid event-loop / middleware issues
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Function-scoped TestClient so the rate limiter resets cleanly between tests."""
    from main import app

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Per-test auth + DB override fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_overrides():
    """
    Guarantee dependency_overrides are cleared after every test and reset the
    in-memory rate limiter store so no test is throttled by a prior test's
    requests.  Mirrors the conftest.py ``reset_rate_limiter`` fixture.
    """
    from main import app, _app_rate_limiter

    # Reset BEFORE the test (pick up any state left by previous tests)
    _app_rate_limiter.reset()

    yield

    # Clear all dependency_overrides set by this test
    for dep in list(app.dependency_overrides.keys()):
        app.dependency_overrides.pop(dep, None)

    # Reset AFTER the test so the next test starts clean
    _app_rate_limiter.reset()


def _install_auth(tier: str = "pro", user_id: str = TEST_USER_ID):
    """
    Install auth + DB overrides so that require_paid_tier succeeds.

    Returns (db_mock,) so callers can configure side_effects.
    The ``require_paid_tier`` dependency is overridden directly because it
    performs its own DB query; overriding it avoids the need for every test
    to mock two separate execute() calls just for the tier check.
    """
    from main import app
    from api.dependencies import get_current_user, get_db_session
    from api.v1.connections import require_paid_tier

    session = _session_data(user_id=user_id, tier=tier)
    db = _mock_db()

    if tier in ("pro", "business"):
        # Override require_paid_tier so it returns the session directly
        app.dependency_overrides[require_paid_tier] = lambda: session
    else:
        # For free / None tier, let require_paid_tier run so it returns 403.
        # We must provide get_current_user and a DB that returns the tier.
        app.dependency_overrides[get_current_user] = lambda: session
        tier_result = _scalar_result(tier)
        db.execute = AsyncMock(return_value=tier_result)

    app.dependency_overrides[get_current_user] = lambda: session
    app.dependency_overrides[get_db_session] = lambda: db

    return db


def _remove_auth():
    """Remove all auth-related overrides."""
    from main import app
    from api.dependencies import get_current_user, get_db_session
    from api.v1.connections import require_paid_tier

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(require_paid_tier, None)


BASE = "/api/v1/connections"


# ===========================================================================
# 1. Paid-Tier Gate
# ===========================================================================


class TestPaidTierGate:
    """Verify that the paid-tier gate enforces authentication and subscription."""

    def test_connections_requires_auth(self, client):
        """No auth token/cookie → 401 (or 503 when DB unavailable)."""
        _remove_auth()
        response = client.get(BASE)
        assert response.status_code in (401, 503)

    def test_connections_requires_paid_tier_free_user(self, client):
        """Free-tier user must be rejected with 403."""
        from main import app
        from api.dependencies import get_current_user, get_db_session
        from api.v1.connections import require_paid_tier

        # Remove any pro override so require_paid_tier runs the real logic
        app.dependency_overrides.pop(require_paid_tier, None)

        session = _session_data(tier="free")
        db = _mock_db()

        # Return "free" when querying subscription_tier
        db.execute = AsyncMock(return_value=_scalar_result("free"))

        app.dependency_overrides[get_current_user] = lambda: session
        app.dependency_overrides[get_db_session] = lambda: db

        response = client.get(BASE)
        assert response.status_code == 403

    def test_connections_allows_pro_tier(self, client):
        """Pro-tier user must be allowed through the gate."""
        db = _install_auth(tier="pro")
        db.execute = AsyncMock(return_value=_mapping_result([]))
        response = client.get(BASE)
        assert response.status_code == 200

    def test_connections_allows_business_tier(self, client):
        """Business-tier user must be allowed through the gate."""
        db = _install_auth(tier="business")
        db.execute = AsyncMock(return_value=_mapping_result([]))
        response = client.get(BASE)
        assert response.status_code == 200

    def test_connections_rejects_null_tier(self, client):
        """User with no subscription_tier row must be rejected with 403."""
        from main import app
        from api.dependencies import get_current_user, get_db_session
        from api.v1.connections import require_paid_tier

        app.dependency_overrides.pop(require_paid_tier, None)

        session = _session_data(tier=None)
        db = _mock_db()
        db.execute = AsyncMock(return_value=_scalar_result(None))

        app.dependency_overrides[get_current_user] = lambda: session
        app.dependency_overrides[get_db_session] = lambda: db

        response = client.get(BASE)
        assert response.status_code == 403


# ===========================================================================
# 2. List Connections
# ===========================================================================


class TestListConnections:
    """Tests for GET /connections."""

    def test_list_connections_empty(self, client):
        """New user with no connections returns an empty list."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=_mapping_result([]))

        response = client.get(BASE)

        assert response.status_code == 200
        data = response.json()
        assert data["connections"] == []
        assert data["total"] == 0

    def test_list_connections_returns_all(self, client):
        """Multiple connections are returned correctly."""
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            {
                "id": str(uuid4()),
                "user_id": TEST_USER_ID,
                "connection_type": "direct",
                "supplier_id": TEST_SUPPLIER_ID,
                "supplier_name": "Eversource",
                "status": "active",
                "account_number_masked": "******1234",
                "email_provider": None,
                "label": None,
                "created_at": now,
            },
            {
                "id": str(uuid4()),
                "user_id": TEST_USER_ID,
                "connection_type": "email_import",
                "supplier_id": None,
                "supplier_name": None,
                "status": "pending",
                "account_number_masked": None,
                "email_provider": "gmail",
                "label": None,
                "created_at": now,
            },
        ]
        db = _install_auth()
        db.execute = AsyncMock(return_value=_mapping_result(rows))

        response = client.get(BASE)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["connections"]) == 2

    def test_list_connections_only_own(self, client):
        """Connections belonging to another user must not appear in the list."""
        db = _install_auth(user_id=TEST_USER_ID)
        # DB returns empty — simulating that the other user's rows are filtered
        db.execute = AsyncMock(return_value=_mapping_result([]))

        response = client.get(BASE)

        assert response.status_code == 200
        assert response.json()["connections"] == []
        # Verify the query was called with the correct user_id param
        call_args = db.execute.call_args
        assert call_args is not None
        # The second positional arg is the params dict
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
        # params may be passed as second positional or keyword
        if isinstance(params, dict):
            assert params.get("uid") == TEST_USER_ID


# ===========================================================================
# 3. Create Direct Connection
# ===========================================================================


class TestCreateDirectConnection:
    """Tests for POST /connections/direct."""

    def _make_supplier_result(self, supplier_id=None, name="Eversource"):
        """Mock DB row for supplier lookup (returns a _DictRow so dict(row) works)."""
        sid = supplier_id or TEST_SUPPLIER_ID
        supplier_row = _DictRow({"id": sid, "name": name})
        result = MagicMock()
        result.mappings.return_value.first.return_value = supplier_row
        result.fetchone.return_value = None  # no duplicate
        return result

    def test_create_direct_connection_success(self, client):
        """Valid payload with consent creates a direct connection (201)."""
        db = _install_auth()

        supplier_result = self._make_supplier_result()
        no_dup_result = _empty_mapping_result()
        insert_result = MagicMock()

        db.execute = AsyncMock(
            side_effect=[supplier_result, no_dup_result, insert_result]
        )

        # encrypt_field / mask_account_number are imported locally inside the
        # route handler, so we patch at the source module level.
        with patch("utils.encryption.encrypt_field", return_value=b"encrypted"), \
             patch("utils.encryption.mask_account_number", return_value="******5678"):
            response = client.post(
                f"{BASE}/direct",
                json={
                    "supplier_id": TEST_SUPPLIER_ID,
                    "account_number": "ACC5678",
                    "consent_given": True,
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["connection_type"] == "direct"
        assert data["supplier_id"] == TEST_SUPPLIER_ID
        assert data["status"] == "active"
        assert data["account_number_masked"] == "******5678"

    def test_create_direct_connection_invalid_supplier(self, client):
        """Non-existent supplier_id returns 404."""
        db = _install_auth()

        missing_supplier = MagicMock()
        missing_supplier.mappings.return_value.first.return_value = None

        db.execute = AsyncMock(return_value=missing_supplier)

        response = client.post(
            f"{BASE}/direct",
            json={
                "supplier_id": str(uuid4()),
                "account_number": "ACC1234",
                "consent_given": True,
            },
        )

        assert response.status_code == 404

    def test_create_direct_connection_no_consent(self, client):
        """Missing consent (consent_given=false) returns 422."""
        _install_auth()

        response = client.post(
            f"{BASE}/direct",
            json={
                "supplier_id": TEST_SUPPLIER_ID,
                "account_number": "ACC1234",
                "consent_given": False,
            },
        )

        assert response.status_code == 422

    def test_create_direct_connection_duplicate_check(self, client):
        """Already-active direct connection to the same supplier returns 409."""
        db = _install_auth()

        supplier_result = self._make_supplier_result()

        dup_row = MagicMock()
        dup_result = MagicMock()
        dup_result.fetchone.return_value = dup_row  # duplicate found

        db.execute = AsyncMock(side_effect=[supplier_result, dup_result])

        with patch("utils.encryption.encrypt_field", return_value=b"encrypted"), \
             patch("utils.encryption.mask_account_number", return_value="******1234"):
            response = client.post(
                f"{BASE}/direct",
                json={
                    "supplier_id": TEST_SUPPLIER_ID,
                    "account_number": "ACC1234",
                    "consent_given": True,
                },
            )

        assert response.status_code == 409

    def test_create_direct_connection_stores_encrypted(self, client):
        """Verify that encrypt_field is called with the raw account number."""
        db = _install_auth()

        supplier_result = self._make_supplier_result()
        no_dup = _empty_mapping_result()
        insert_result = MagicMock()

        db.execute = AsyncMock(side_effect=[supplier_result, no_dup, insert_result])

        # Patch at source module so the locally-imported name is intercepted.
        with patch("utils.encryption.encrypt_field") as mock_encrypt, \
             patch("utils.encryption.mask_account_number", return_value="******9999"):
            mock_encrypt.return_value = b"super-encrypted"

            client.post(
                f"{BASE}/direct",
                json={
                    "supplier_id": TEST_SUPPLIER_ID,
                    "account_number": "ACC9999",
                    "consent_given": True,
                },
            )

        mock_encrypt.assert_called_once_with("ACC9999")


# ===========================================================================
# 4. Create Email Connection
# ===========================================================================


class TestCreateEmailConnection:
    """Tests for POST /connections/email."""

    def test_create_email_connection_gmail(self, client):
        """Gmail provider returns a redirect_url containing accounts.google.com."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=MagicMock())

        response = client.post(
            f"{BASE}/email",
            json={"provider": "gmail", "consent_given": True},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["provider"] == "gmail"
        assert "accounts.google.com" in data["redirect_url"]
        assert "connection_id" in data

    def test_create_email_connection_outlook(self, client):
        """Outlook provider returns a redirect_url containing login.microsoftonline.com."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=MagicMock())

        response = client.post(
            f"{BASE}/email",
            json={"provider": "outlook", "consent_given": True},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["provider"] == "outlook"
        assert "microsoftonline.com" in data["redirect_url"]

    def test_create_email_connection_invalid_provider(self, client):
        """Unsupported provider value must fail Pydantic validation (422)."""
        _install_auth()

        response = client.post(
            f"{BASE}/email",
            json={"provider": "yahoo", "consent_given": True},
        )

        assert response.status_code == 422

    def test_create_email_connection_no_consent(self, client):
        """Missing consent for email connection returns 422."""
        _install_auth()

        response = client.post(
            f"{BASE}/email",
            json={"provider": "gmail", "consent_given": False},
        )

        assert response.status_code == 422


# ===========================================================================
# 5. Upload Stub
# ===========================================================================


class TestUploadConnectionStub:
    """Tests for POST /connections/upload."""

    def test_upload_stub_creates_connection(self, client):
        """Valid upload stub request creates a manual_upload connection (201)."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=MagicMock())

        response = client.post(
            f"{BASE}/upload",
            json={"label": "January Bill", "consent_given": True},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["connection_type"] == "manual_upload"
        assert data["status"] == "active"
        assert data["label"] == "January Bill"

    def test_upload_stub_requires_consent(self, client):
        """Upload stub without consent returns 422."""
        _install_auth()

        response = client.post(
            f"{BASE}/upload",
            json={"label": "No consent bill", "consent_given": False},
        )

        assert response.status_code == 422

    def test_upload_stub_returns_connection_response(self, client):
        """Upload stub response must contain all required ConnectionResponse fields."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=MagicMock())

        response = client.post(
            f"{BASE}/upload",
            json={"consent_given": True},
        )

        assert response.status_code == 201
        data = response.json()
        # All required ConnectionResponse fields must be present
        assert "id" in data
        assert "user_id" in data
        assert "connection_type" in data
        assert "status" in data
        assert "created_at" in data
        assert data["connection_type"] == "manual_upload"
        assert data["user_id"] == TEST_USER_ID


# ===========================================================================
# 6. Get Single Connection
# ===========================================================================


class TestGetConnection:
    """Tests for GET /connections/{connection_id}."""

    def _connection_row(self, user_id=TEST_USER_ID):
        now = datetime.now(timezone.utc).isoformat()
        return {
            "id": TEST_CONNECTION_ID,
            "user_id": user_id,
            "connection_type": "direct",
            "supplier_id": TEST_SUPPLIER_ID,
            "supplier_name": "Eversource",
            "status": "active",
            "account_number_masked": "******1234",
            "email_provider": None,
            "label": None,
            "created_at": now,
        }

    def test_get_connection_success(self, client):
        """Owner can retrieve their own connection by ID."""
        db = _install_auth()

        row_data = _DictRow(self._connection_row())
        result = MagicMock()
        result.mappings.return_value.first.return_value = row_data

        db.execute = AsyncMock(return_value=result)

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == TEST_CONNECTION_ID
        assert data["connection_type"] == "direct"

    def test_get_connection_not_found(self, client):
        """Non-existent connection_id returns 404."""
        db = _install_auth()

        result = MagicMock()
        result.mappings.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=result)

        response = client.get(f"{BASE}/{uuid4()}")

        assert response.status_code == 404

    def test_get_connection_wrong_user(self, client):
        """Connection owned by another user returns 404 (not 403, to avoid enumeration)."""
        # Install auth for TEST_USER_ID, but the DB returns no row
        # because the WHERE clause filters by user_id
        db = _install_auth(user_id=TEST_USER_ID)

        result = MagicMock()
        result.mappings.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=result)

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}")

        assert response.status_code == 404


# ===========================================================================
# 7. Delete Connection
# ===========================================================================


class TestDeleteConnection:
    """Tests for DELETE /connections/{connection_id}."""

    def test_delete_connection_success(self, client):
        """Owner can delete their own connection (returns 200 with message)."""
        db = _install_auth()

        # First execute: ownership check → found
        ownership_row = MagicMock()
        ownership_result = MagicMock()
        ownership_result.fetchone.return_value = ownership_row

        # Second execute: UPDATE
        update_result = MagicMock()

        db.execute = AsyncMock(side_effect=[ownership_result, update_result])

        response = client.delete(f"{BASE}/{TEST_CONNECTION_ID}")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Connection deleted"
        assert data["connection_id"] == TEST_CONNECTION_ID

    def test_delete_connection_not_found(self, client):
        """Non-existent connection_id returns 404."""
        db = _install_auth()

        not_found_result = MagicMock()
        not_found_result.fetchone.return_value = None
        db.execute = AsyncMock(return_value=not_found_result)

        response = client.delete(f"{BASE}/{uuid4()}")

        assert response.status_code == 404

    def test_delete_connection_wrong_user(self, client):
        """Deleting another user's connection returns 404."""
        db = _install_auth(user_id=TEST_USER_ID)

        # DB returns None because WHERE user_id = :uid filters it out
        not_found_result = MagicMock()
        not_found_result.fetchone.return_value = None
        db.execute = AsyncMock(return_value=not_found_result)

        response = client.delete(f"{BASE}/{TEST_CONNECTION_ID}")

        assert response.status_code == 404


# ===========================================================================
# 8. Get Rates
# ===========================================================================


class TestGetRates:
    """Tests for GET /connections/{id}/rates and GET /connections/{id}/rates/current."""

    def _install_with_ownership(self, found: bool = True):
        """Return a db mock wired for ownership check + optional rate rows."""
        db = _install_auth()

        ownership_result = MagicMock()
        if found:
            ownership_result.fetchone.return_value = MagicMock()
        else:
            ownership_result.fetchone.return_value = None

        return db, ownership_result

    def test_get_rates_empty(self, client):
        """No extracted rates → returns an empty list."""
        db, ownership_result = self._install_with_ownership(found=True)

        empty_rates_result = MagicMock()
        empty_rates_result.mappings.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[ownership_result, empty_rates_result])

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/rates")

        assert response.status_code == 200
        assert response.json() == []

    def test_get_rates_returns_all(self, client):
        """Multiple extracted rates are all returned."""
        db, ownership_result = self._install_with_ownership(found=True)

        now = datetime.now(timezone.utc).isoformat()
        rate_rows = [
            {
                "id": str(uuid4()),
                "connection_id": TEST_CONNECTION_ID,
                "rate_per_kwh": 0.2145,
                "effective_date": now,
                "source": "bill_parse",
                "raw_label": "Standard Rate",
            },
            {
                "id": str(uuid4()),
                "connection_id": TEST_CONNECTION_ID,
                "rate_per_kwh": 0.1987,
                "effective_date": now,
                "source": "api_pull",
                "raw_label": None,
            },
        ]

        rates_result = MagicMock()
        rates_result.mappings.return_value.all.return_value = [_DictRow(r) for r in rate_rows]

        db.execute = AsyncMock(side_effect=[ownership_result, rates_result])

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/rates")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["rate_per_kwh"] == 0.2145
        assert data[1]["source"] == "api_pull"

    def test_get_current_rate(self, client):
        """GET .../rates/current returns only the most recent rate."""
        db, ownership_result = self._install_with_ownership(found=True)

        now = datetime.now(timezone.utc).isoformat()
        rate_row_data = {
            "id": str(uuid4()),
            "connection_id": TEST_CONNECTION_ID,
            "rate_per_kwh": 0.2301,
            "effective_date": now,
            "source": "bill_parse",
            "raw_label": "Peak Rate",
        }

        current_result = MagicMock()
        current_result.mappings.return_value.first.return_value = _DictRow(rate_row_data)

        db.execute = AsyncMock(side_effect=[ownership_result, current_result])

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/rates/current")

        assert response.status_code == 200
        data = response.json()
        assert data["rate_per_kwh"] == 0.2301
        assert data["source"] == "bill_parse"
        assert data["raw_label"] == "Peak Rate"


# ===========================================================================
# 9. Model Validation
# ===========================================================================


class TestModelValidation:
    """Pure Pydantic model validation tests — no HTTP client needed."""

    def test_create_direct_request_validation(self):
        """Valid CreateDirectConnectionRequest constructs without error."""
        from models.connections import CreateDirectConnectionRequest

        req = CreateDirectConnectionRequest(
            supplier_id=uuid4(),
            account_number="ACC12345",
            consent_given=True,
        )
        assert str(req.supplier_id) != ""
        assert req.account_number == "ACC12345"
        assert req.consent_given is True

    def test_create_email_request_validation(self):
        """Valid CreateEmailConnectionRequest constructs without error."""
        from models.connections import CreateEmailConnectionRequest

        req = CreateEmailConnectionRequest(provider="gmail", consent_given=True)
        assert req.provider == "gmail"

        req2 = CreateEmailConnectionRequest(provider="outlook", consent_given=True)
        assert req2.provider == "outlook"

    def test_connection_response_serialization(self):
        """ConnectionResponse serializes to JSON without error."""
        from models.connections import ConnectionResponse

        now = datetime.now(timezone.utc)
        conn = ConnectionResponse(
            id=str(uuid4()),
            user_id=TEST_USER_ID,
            connection_type="direct",
            supplier_id=TEST_SUPPLIER_ID,
            supplier_name="Eversource",
            status="active",
            account_number_masked="******1234",
            created_at=now,
        )
        dumped = conn.model_dump()
        assert dumped["connection_type"] == "direct"
        assert dumped["status"] == "active"
        assert dumped["account_number_masked"] == "******1234"

    def test_extracted_rate_response_serialization(self):
        """ExtractedRateResponse serializes to JSON without error."""
        from models.connections import ExtractedRateResponse

        now = datetime.now(timezone.utc)
        rate = ExtractedRateResponse(
            id=str(uuid4()),
            connection_id=TEST_CONNECTION_ID,
            rate_per_kwh=0.2145,
            effective_date=now,
            source="bill_parse",
            raw_label="Standard Rate",
        )
        dumped = rate.model_dump()
        assert dumped["rate_per_kwh"] == 0.2145
        assert dumped["source"] == "bill_parse"
        assert dumped["raw_label"] == "Standard Rate"
        assert dumped["connection_id"] == TEST_CONNECTION_ID
