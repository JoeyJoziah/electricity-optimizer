"""
Phase 4: UtilityAPI Integration Tests

Covers:
  - UtilityAPIClient unit tests (mocked HTTP)
  - ConnectionSyncService unit tests (mocked DB + UtilityAPIClient)
  - API endpoint integration tests:
      POST /connections/{id}/sync
      GET  /connections/{id}/sync-status
      GET  /connections/direct/callback
  - Error handling (timeout, bad response, extraction failure, missing auth)
  - At least 25 tests total

All database calls and HTTP calls are fully mocked.
No real Postgres or UtilityAPI connections are made.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Stable test constants
# ---------------------------------------------------------------------------

TEST_USER_ID = "cccccccc-0000-0000-0000-000000000003"
TEST_CONNECTION_ID = str(uuid4())
TEST_AUTH_UID = "auth_utilityapi_abc123"
TEST_METER_UID = "meter_utilityapi_xyz789"
TEST_SUPPLIER_NAME = "Eversource Energy"

# ---------------------------------------------------------------------------
# Shared sample data
# ---------------------------------------------------------------------------

SAMPLE_BILL = {
    "uid": "b_001",
    "meter_uid": TEST_METER_UID,
    "base": {
        "bill_start_date": "2025-12-01",
        "bill_end_date": "2025-12-31",
        "total_kwh": 800.0,
        "total_cost": 180.0,
        "rate_name": "Standard Rate",
    },
}

SAMPLE_BILL_NO_LABEL = {
    "uid": "b_002",
    "meter_uid": TEST_METER_UID,
    "base": {
        "bill_start_date": "2025-11-01",
        "total_kwh": 600.0,
        "total_cost": 120.0,
    },
}

SAMPLE_METER = {"uid": TEST_METER_UID, "utility": "Eversource", "status": "active"}

SAMPLE_AUTH_STATUS_ACTIVE = {
    "uid": TEST_AUTH_UID,
    "status": "active",
    "utility": "Eversource",
}

SAMPLE_AUTH_STATUS_INACTIVE = {
    "uid": TEST_AUTH_UID,
    "status": "revoked",
    "utility": "Eversource",
}


# ===========================================================================
# Part 1 — UtilityAPIClient unit tests
# ===========================================================================


class TestUtilityAPIClientAuthForm:
    """Tests for UtilityAPIClient.create_authorization_form()."""

    @pytest.mark.asyncio
    async def test_create_form_returns_url_with_utility(self):
        """Form URL includes the supplier name as a query param."""
        from integrations.utilityapi import UtilityAPIClient

        client = UtilityAPIClient(api_key="test-key")
        url = await client.create_authorization_form(TEST_SUPPLIER_NAME)

        assert "utilityapi.com/authorize" in url
        assert "Eversource+Energy" in url or "Eversource%20Energy" in url

    @pytest.mark.asyncio
    async def test_create_form_includes_state(self):
        """state parameter is echoed into the form URL."""
        from integrations.utilityapi import UtilityAPIClient

        client = UtilityAPIClient(api_key="test-key")
        url = await client.create_authorization_form(
            TEST_SUPPLIER_NAME, state=TEST_CONNECTION_ID
        )

        assert TEST_CONNECTION_ID in url

    @pytest.mark.asyncio
    async def test_create_form_includes_redirect_url(self):
        """redirect_url appears in the form URL when provided."""
        from integrations.utilityapi import UtilityAPIClient

        redirect = "https://app.example.com/callback"
        client = UtilityAPIClient(api_key="test-key")
        url = await client.create_authorization_form(
            TEST_SUPPLIER_NAME, redirect_url=redirect
        )

        assert "callback" in url


class TestUtilityAPIClientAuthStatus:
    """Tests for UtilityAPIClient.get_authorization_status()."""

    @pytest.mark.asyncio
    async def test_get_auth_status_success(self):
        """Returns the authorization dict on 200 response."""
        import httpx
        from integrations.utilityapi import UtilityAPIClient

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_AUTH_STATUS_ACTIVE

        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.request = AsyncMock(return_value=mock_resp)

        client = UtilityAPIClient(api_key="test-key", http_client=mock_http)
        result = await client.get_authorization_status(TEST_AUTH_UID)

        assert result["status"] == "active"
        assert result["uid"] == TEST_AUTH_UID

    @pytest.mark.asyncio
    async def test_get_auth_status_404_raises(self):
        """HTTP 404 raises UtilityAPIError with status_code=404."""
        import httpx
        from integrations.utilityapi import UtilityAPIClient, UtilityAPIError

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"error": "not found"}

        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.request = AsyncMock(return_value=mock_resp)

        client = UtilityAPIClient(api_key="test-key", http_client=mock_http)

        with pytest.raises(UtilityAPIError) as exc_info:
            await client.get_authorization_status("bad-uid")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_auth_status_timeout_raises(self):
        """Network timeout raises UtilityAPIError."""
        import httpx
        from integrations.utilityapi import UtilityAPIClient, UtilityAPIError

        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.request = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )

        client = UtilityAPIClient(api_key="test-key", http_client=mock_http)

        with pytest.raises(UtilityAPIError):
            await client.get_authorization_status(TEST_AUTH_UID)


class TestUtilityAPIClientMeters:
    """Tests for UtilityAPIClient.get_meters()."""

    @pytest.mark.asyncio
    async def test_get_meters_returns_list(self):
        """Returns a list of meter dicts on success."""
        import httpx
        from integrations.utilityapi import UtilityAPIClient

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"meters": [SAMPLE_METER]}

        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.request = AsyncMock(return_value=mock_resp)

        client = UtilityAPIClient(api_key="test-key", http_client=mock_http)
        meters = await client.get_meters(TEST_AUTH_UID)

        assert len(meters) == 1
        assert meters[0]["uid"] == TEST_METER_UID

    @pytest.mark.asyncio
    async def test_get_meters_empty_list(self):
        """Returns an empty list when no meters are found."""
        import httpx
        from integrations.utilityapi import UtilityAPIClient

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"meters": []}

        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.request = AsyncMock(return_value=mock_resp)

        client = UtilityAPIClient(api_key="test-key", http_client=mock_http)
        meters = await client.get_meters(TEST_AUTH_UID)

        assert meters == []

    @pytest.mark.asyncio
    async def test_get_meters_network_error_raises(self):
        """Network error raises UtilityAPIError."""
        import httpx
        from integrations.utilityapi import UtilityAPIClient, UtilityAPIError

        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.request = AsyncMock(
            side_effect=httpx.RequestError("connection refused")
        )

        client = UtilityAPIClient(api_key="test-key", http_client=mock_http)

        with pytest.raises(UtilityAPIError):
            await client.get_meters(TEST_AUTH_UID)


class TestUtilityAPIClientBills:
    """Tests for UtilityAPIClient.get_bills()."""

    @pytest.mark.asyncio
    async def test_get_bills_returns_list(self):
        """Returns a list of bill dicts on success."""
        import httpx
        from integrations.utilityapi import UtilityAPIClient

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"bills": [SAMPLE_BILL]}

        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.request = AsyncMock(return_value=mock_resp)

        client = UtilityAPIClient(api_key="test-key", http_client=mock_http)
        bills = await client.get_bills(TEST_METER_UID)

        assert len(bills) == 1
        assert bills[0]["uid"] == "b_001"

    @pytest.mark.asyncio
    async def test_get_bills_with_since_filter(self):
        """``since`` datetime is passed as a query parameter."""
        import httpx
        from integrations.utilityapi import UtilityAPIClient

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"bills": []}

        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.request = AsyncMock(return_value=mock_resp)

        since = datetime(2025, 11, 1, tzinfo=timezone.utc)
        client = UtilityAPIClient(api_key="test-key", http_client=mock_http)
        await client.get_bills(TEST_METER_UID, since=since)

        call_kwargs = mock_http.request.call_args[1]
        params = call_kwargs.get("params", {})
        assert "start" in params


class TestRateExtraction:
    """Tests for UtilityAPIClient.extract_rate_from_bill()."""

    def test_extract_standard_bill(self):
        """Standard bill extracts correct rate_per_kwh."""
        from integrations.utilityapi import UtilityAPIClient

        client = UtilityAPIClient(api_key="test-key")
        rate = client.extract_rate_from_bill(SAMPLE_BILL)

        # 180.0 / 800.0 = 0.225
        assert abs(rate["rate_per_kwh"] - 0.225) < 1e-5
        assert rate["source"] == "api_pull"
        assert rate["raw_label"] == "Standard Rate"
        assert isinstance(rate["effective_date"], datetime)

    def test_extract_bill_no_label(self):
        """Bill without rate_name sets raw_label to None."""
        from integrations.utilityapi import UtilityAPIClient

        client = UtilityAPIClient(api_key="test-key")
        rate = client.extract_rate_from_bill(SAMPLE_BILL_NO_LABEL)

        assert rate["raw_label"] is None

    def test_extract_bill_missing_total_kwh_raises(self):
        """Missing total_kwh raises UtilityAPIError."""
        from integrations.utilityapi import UtilityAPIClient, UtilityAPIError

        bad_bill = {"uid": "b_bad", "base": {"total_cost": 100.0}}
        client = UtilityAPIClient(api_key="test-key")

        with pytest.raises(UtilityAPIError):
            client.extract_rate_from_bill(bad_bill)

    def test_extract_bill_zero_kwh_raises(self):
        """Zero total_kwh raises UtilityAPIError (division by zero guard)."""
        from integrations.utilityapi import UtilityAPIClient, UtilityAPIError

        zero_kwh_bill = {
            "uid": "b_zero",
            "base": {"total_kwh": 0, "total_cost": 50.0},
        }
        client = UtilityAPIClient(api_key="test-key")

        with pytest.raises(UtilityAPIError):
            client.extract_rate_from_bill(zero_kwh_bill)

    def test_extract_bill_missing_base_raises(self):
        """Bill with no ``base`` key raises UtilityAPIError."""
        from integrations.utilityapi import UtilityAPIClient, UtilityAPIError

        bill_no_base = {"uid": "b_nobase"}
        client = UtilityAPIClient(api_key="test-key")

        with pytest.raises(UtilityAPIError):
            client.extract_rate_from_bill(bill_no_base)

    def test_extract_bill_iso_datetime_effective_date(self):
        """ISO datetime bill_start_date is parsed into a UTC datetime."""
        from integrations.utilityapi import UtilityAPIClient

        bill = {
            "uid": "b_dt",
            "base": {
                "bill_start_date": "2025-10-15T14:30:00Z",
                "total_kwh": 500.0,
                "total_cost": 100.0,
            },
        }
        client = UtilityAPIClient(api_key="test-key")
        rate = client.extract_rate_from_bill(bill)

        assert rate["effective_date"].year == 2025
        assert rate["effective_date"].month == 10
        assert rate["effective_date"].tzinfo is not None

    def test_extract_bill_uses_end_date_fallback(self):
        """Uses bill_end_date when bill_start_date is absent."""
        from integrations.utilityapi import UtilityAPIClient

        bill = {
            "uid": "b_end",
            "base": {
                "bill_end_date": "2025-09-30",
                "total_kwh": 400.0,
                "total_cost": 80.0,
            },
        }
        client = UtilityAPIClient(api_key="test-key")
        rate = client.extract_rate_from_bill(bill)

        assert rate["effective_date"].month == 9


# ===========================================================================
# Part 2 — ConnectionSyncService unit tests
# ===========================================================================


def _mock_db_with_connection(
    auth_uid_encrypted: bytes = b"encrypted_uid",
    status: str = "active",
    last_sync_at=None,
):
    """
    Build a mock DB session that returns a connection row on the first execute
    call, then allows unlimited subsequent calls to succeed.

    The ``execute`` side_effect is a function so it can return a fresh
    MagicMock on every call after the first (no subscript issues).
    """
    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    # Connection row returned for the first DB call (_fetch_connection)
    conn_row = {
        "id": TEST_CONNECTION_ID,
        "status": status,
        "utilityapi_auth_uid_encrypted": auth_uid_encrypted,
        "last_sync_at": last_sync_at,
        "last_sync_error": None,
        "sync_frequency_hours": 24,
    }

    class _DictRow(dict):
        pass

    fetch_result = MagicMock()
    fetch_result.mappings.return_value.first.return_value = _DictRow(conn_row)
    fetch_result.fetchall.return_value = []

    _call_count = {"n": 0}

    async def _execute_side_effect(*args, **kwargs):
        _call_count["n"] += 1
        if _call_count["n"] == 1:
            return fetch_result
        # All subsequent calls (inserts / updates) return a generic mock
        return MagicMock()

    db.execute = AsyncMock(side_effect=_execute_side_effect)
    return db


class TestConnectionSyncServiceSyncConnection:
    """Tests for ConnectionSyncService.sync_connection()."""

    @pytest.mark.asyncio
    async def test_sync_connection_success(self):
        """Successful sync returns success=True and correct new_rates_found count."""
        from services.connection_sync_service import ConnectionSyncService
        from integrations.utilityapi import UtilityAPIClient

        # _mock_db_with_connection returns fetch on call 1, generic mocks after
        db = _mock_db_with_connection()

        mock_client = AsyncMock(spec=UtilityAPIClient)
        mock_client.get_meters = AsyncMock(return_value=[SAMPLE_METER])
        mock_client.get_bills = AsyncMock(return_value=[SAMPLE_BILL, SAMPLE_BILL_NO_LABEL])
        mock_client.extract_rate_from_bill = MagicMock(
            side_effect=[
                {
                    "rate_per_kwh": 0.225,
                    "effective_date": datetime.now(timezone.utc),
                    "source": "api_pull",
                    "raw_label": "Standard Rate",
                },
                {
                    "rate_per_kwh": 0.20,
                    "effective_date": datetime.now(timezone.utc),
                    "source": "api_pull",
                    "raw_label": None,
                },
            ]
        )

        with patch("services.connection_sync_service.decrypt_field", return_value=TEST_AUTH_UID):
            svc = ConnectionSyncService(db, utilityapi_client=mock_client)
            result = await svc.sync_connection(TEST_CONNECTION_ID)

        assert result["success"] is True
        assert result["new_rates_found"] == 2
        assert result["error"] is None
        assert result["connection_id"] == TEST_CONNECTION_ID

    @pytest.mark.asyncio
    async def test_sync_connection_not_found(self):
        """Returns failure when connection_id is not in the DB."""
        from services.connection_sync_service import ConnectionSyncService
        from integrations.utilityapi import UtilityAPIClient

        db = AsyncMock()
        db.commit = AsyncMock()

        # Return None for the connection fetch
        none_result = MagicMock()
        none_result.mappings.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=none_result)

        svc = ConnectionSyncService(db)
        result = await svc.sync_connection("nonexistent-id")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_sync_connection_no_auth_uid(self):
        """Returns failure when the connection has no stored auth UID."""
        from services.connection_sync_service import ConnectionSyncService

        db = _mock_db_with_connection(auth_uid_encrypted=None)
        svc = ConnectionSyncService(db)
        result = await svc.sync_connection(TEST_CONNECTION_ID)

        assert result["success"] is False
        assert "authorized" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_sync_connection_meters_api_error(self):
        """Returns failure when UtilityAPI meters fetch fails."""
        from services.connection_sync_service import ConnectionSyncService
        from integrations.utilityapi import UtilityAPIClient, UtilityAPIError

        db = _mock_db_with_connection()

        mock_client = AsyncMock(spec=UtilityAPIClient)
        mock_client.get_meters = AsyncMock(
            side_effect=UtilityAPIError("API error", status_code=500)
        )

        with patch("services.connection_sync_service.decrypt_field", return_value=TEST_AUTH_UID):
            svc = ConnectionSyncService(db, utilityapi_client=mock_client)
            result = await svc.sync_connection(TEST_CONNECTION_ID)

        assert result["success"] is False
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_sync_connection_no_meters(self):
        """Returns failure when no meters are associated with the authorization."""
        from services.connection_sync_service import ConnectionSyncService
        from integrations.utilityapi import UtilityAPIClient

        db = _mock_db_with_connection()

        mock_client = AsyncMock(spec=UtilityAPIClient)
        mock_client.get_meters = AsyncMock(return_value=[])

        with patch("services.connection_sync_service.decrypt_field", return_value=TEST_AUTH_UID):
            svc = ConnectionSyncService(db, utilityapi_client=mock_client)
            result = await svc.sync_connection(TEST_CONNECTION_ID)

        assert result["success"] is False
        assert "meters" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_sync_connection_rate_extraction_error_continues(self):
        """Rate extraction failure for one bill does not abort the whole sync."""
        from services.connection_sync_service import ConnectionSyncService
        from integrations.utilityapi import UtilityAPIClient, UtilityAPIError

        db = _mock_db_with_connection()

        mock_client = AsyncMock(spec=UtilityAPIClient)
        mock_client.get_meters = AsyncMock(return_value=[SAMPLE_METER])
        mock_client.get_bills = AsyncMock(return_value=[SAMPLE_BILL, SAMPLE_BILL_NO_LABEL])

        # First bill fails extraction, second succeeds
        good_rate = {
            "rate_per_kwh": 0.225,
            "effective_date": datetime.now(timezone.utc),
            "source": "api_pull",
            "raw_label": None,
        }
        mock_client.extract_rate_from_bill = MagicMock(
            side_effect=[
                UtilityAPIError("bad bill"),
                good_rate,
            ]
        )

        with patch("services.connection_sync_service.decrypt_field", return_value=TEST_AUTH_UID):
            svc = ConnectionSyncService(db, utilityapi_client=mock_client)
            result = await svc.sync_connection(TEST_CONNECTION_ID)

        # One rate was successfully extracted, so overall success=True
        assert result["new_rates_found"] == 1
        assert result["success"] is True


class TestConnectionSyncServiceSyncAllDue:
    """Tests for ConnectionSyncService.sync_all_due()."""

    @pytest.mark.asyncio
    async def test_sync_all_due_empty(self):
        """Returns empty list when no connections are due for sync."""
        from services.connection_sync_service import ConnectionSyncService

        db = AsyncMock()
        due_result = MagicMock()
        due_result.fetchall.return_value = []
        db.execute = AsyncMock(return_value=due_result)

        svc = ConnectionSyncService(db)
        results = await svc.sync_all_due()

        assert results == []

    @pytest.mark.asyncio
    async def test_sync_all_due_handles_missing_columns(self):
        """Gracefully returns empty list when migration-009 columns don't exist."""
        from services.connection_sync_service import ConnectionSyncService

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("column does not exist"))

        svc = ConnectionSyncService(db)
        results = await svc.sync_all_due()

        assert results == []

    @pytest.mark.asyncio
    async def test_sync_all_due_syncs_each_connection(self):
        """Each due connection is synced."""
        from services.connection_sync_service import ConnectionSyncService

        conn_id_1 = str(uuid4())
        conn_id_2 = str(uuid4())

        db = AsyncMock()
        due_result = MagicMock()
        due_result.fetchall.return_value = [(conn_id_1,), (conn_id_2,)]

        db.execute = AsyncMock(return_value=due_result)
        db.commit = AsyncMock()

        sync_results = [
            {"connection_id": conn_id_1, "success": True, "new_rates_found": 1, "error": None, "synced_at": datetime.now(timezone.utc)},
            {"connection_id": conn_id_2, "success": False, "new_rates_found": 0, "error": "No meters", "synced_at": datetime.now(timezone.utc)},
        ]

        svc = ConnectionSyncService(db)
        with patch.object(svc, "sync_connection", side_effect=sync_results):
            results = await svc.sync_all_due()

        assert len(results) == 2
        assert results[0]["connection_id"] == conn_id_1
        assert results[1]["connection_id"] == conn_id_2


class TestConnectionSyncServiceGetSyncStatus:
    """Tests for ConnectionSyncService.get_sync_status()."""

    @pytest.mark.asyncio
    async def test_get_sync_status_with_last_sync(self):
        """Returns correct next_sync_at when last_sync_at is set."""
        from services.connection_sync_service import ConnectionSyncService

        last_sync = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        class _DictRow(dict):
            pass

        row = _DictRow({
            "id": TEST_CONNECTION_ID,
            "last_sync_at": last_sync,
            "last_sync_error": None,
            "sync_frequency_hours": 24,
        })

        db = AsyncMock()
        result = MagicMock()
        result.mappings.return_value.first.return_value = row
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionSyncService(db)
        status = await svc.get_sync_status(TEST_CONNECTION_ID)

        assert status is not None
        assert status["last_sync_at"] == last_sync
        expected_next = last_sync + timedelta(hours=24)
        assert status["next_sync_at"] == expected_next
        assert status["sync_frequency_hours"] == 24

    @pytest.mark.asyncio
    async def test_get_sync_status_never_synced(self):
        """Returns None for next_sync_at when last_sync_at is None."""
        from services.connection_sync_service import ConnectionSyncService

        class _DictRow(dict):
            pass

        row = _DictRow({
            "id": TEST_CONNECTION_ID,
            "last_sync_at": None,
            "last_sync_error": None,
            "sync_frequency_hours": 24,
        })

        db = AsyncMock()
        result = MagicMock()
        result.mappings.return_value.first.return_value = row
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionSyncService(db)
        status = await svc.get_sync_status(TEST_CONNECTION_ID)

        assert status["next_sync_at"] is None

    @pytest.mark.asyncio
    async def test_get_sync_status_not_found(self):
        """Returns None when the connection does not exist."""
        from services.connection_sync_service import ConnectionSyncService

        db = AsyncMock()
        result = MagicMock()
        result.mappings.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionSyncService(db)
        status = await svc.get_sync_status("nonexistent-id")

        assert status is None


# ===========================================================================
# Part 3 — API endpoint integration tests
# ===========================================================================

# --- Helpers (copied pattern from test_connections.py) ----------------------


def _session_data(user_id: str = TEST_USER_ID, tier: str = "pro"):
    from auth.neon_auth import SessionData

    return SessionData(
        user_id=user_id,
        email=f"{user_id[:8]}@example.com",
        name="Test User",
        email_verified=True,
        role="user",
    )


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


class _DictRow(dict):
    pass


def _mapping_result(rows: list) -> MagicMock:
    result = MagicMock()
    mock_rows = [_DictRow(r) for r in rows]
    result.mappings.return_value.all.return_value = mock_rows
    result.mappings.return_value.first.return_value = mock_rows[0] if mock_rows else None
    result.fetchone.return_value = mock_rows[0] if mock_rows else None
    return result


def _empty_result() -> MagicMock:
    result = MagicMock()
    result.mappings.return_value.all.return_value = []
    result.mappings.return_value.first.return_value = None
    result.fetchone.return_value = None
    return result


def _scalar_result(value) -> MagicMock:
    result = MagicMock()
    row = MagicMock()
    row.__getitem__ = lambda self, k: value
    result.fetchone.return_value = row
    result.scalar_one_or_none.return_value = value
    return result


@pytest.fixture()
def client():
    """
    Function-scoped TestClient.

    Resets the rate limiter before and after each test so that the
    in-memory counter doesn't accumulate across the test suite.
    """
    from main import app, _app_rate_limiter

    _app_rate_limiter.reset()

    with TestClient(app) as c:
        yield c

    _app_rate_limiter.reset()


@pytest.fixture(autouse=True)
def _clean_overrides():
    """Clear dependency_overrides and reset the rate limiter between tests."""
    from main import app, _app_rate_limiter

    _app_rate_limiter.reset()
    yield
    for dep in list(app.dependency_overrides.keys()):
        app.dependency_overrides.pop(dep, None)
    _app_rate_limiter.reset()


def _install_auth(tier: str = "pro", user_id: str = TEST_USER_ID):
    from main import app
    from api.dependencies import get_current_user, get_db_session
    from api.v1.connections import require_paid_tier

    session = _session_data(user_id=user_id, tier=tier)
    db = _mock_db()

    if tier in ("pro", "business"):
        app.dependency_overrides[require_paid_tier] = lambda: session
    else:
        app.dependency_overrides[get_current_user] = lambda: session
        db.execute = AsyncMock(return_value=_scalar_result(tier))

    app.dependency_overrides[get_current_user] = lambda: session
    app.dependency_overrides[get_db_session] = lambda: db
    return db


BASE = "/api/v1/connections"


class TestManualSyncEndpoint:
    """Tests for POST /connections/{id}/sync."""

    def test_sync_returns_success(self, client):
        """Successful sync returns 200 with success=True and new_rates_found."""
        db = _install_auth()

        # Ownership check → found
        ownership_result = MagicMock()
        ownership_result.fetchone.return_value = MagicMock()

        sync_result = {
            "connection_id": TEST_CONNECTION_ID,
            "success": True,
            "new_rates_found": 3,
            "error": None,
            "synced_at": datetime.now(timezone.utc),
        }

        with patch(
            "services.connection_sync_service.ConnectionSyncService.sync_connection",
            new_callable=AsyncMock,
            return_value=sync_result,
        ):
            db.execute = AsyncMock(return_value=ownership_result)
            response = client.post(f"{BASE}/{TEST_CONNECTION_ID}/sync")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["new_rates_found"] == 3
        assert data["connection_id"] == TEST_CONNECTION_ID

    def test_sync_connection_not_found(self, client):
        """Non-existent connection_id returns 404."""
        db = _install_auth()

        not_found = MagicMock()
        not_found.fetchone.return_value = None
        db.execute = AsyncMock(return_value=not_found)

        response = client.post(f"{BASE}/{uuid4()}/sync")
        assert response.status_code == 404

    def test_sync_requires_paid_tier(self, client):
        """Free-tier user receives 403 on sync endpoint."""
        from main import app
        from api.dependencies import get_current_user, get_db_session
        from api.v1.connections import require_paid_tier

        app.dependency_overrides.pop(require_paid_tier, None)

        session = _session_data(tier="free")
        db = _mock_db()
        db.execute = AsyncMock(return_value=_scalar_result("free"))

        app.dependency_overrides[get_current_user] = lambda: session
        app.dependency_overrides[get_db_session] = lambda: db

        response = client.post(f"{BASE}/{TEST_CONNECTION_ID}/sync")
        assert response.status_code == 403

    def test_sync_returns_error_on_failure(self, client):
        """Sync returning success=False still returns 200 with error message."""
        db = _install_auth()

        ownership_result = MagicMock()
        ownership_result.fetchone.return_value = MagicMock()

        sync_result = {
            "connection_id": TEST_CONNECTION_ID,
            "success": False,
            "new_rates_found": 0,
            "error": "No meters found for this authorization.",
            "synced_at": datetime.now(timezone.utc),
        }

        with patch(
            "services.connection_sync_service.ConnectionSyncService.sync_connection",
            new_callable=AsyncMock,
            return_value=sync_result,
        ):
            db.execute = AsyncMock(return_value=ownership_result)
            response = client.post(f"{BASE}/{TEST_CONNECTION_ID}/sync")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "meters" in data["error"].lower()


class TestSyncStatusEndpoint:
    """Tests for GET /connections/{id}/sync-status."""

    def test_sync_status_returns_data(self, client):
        """Sync status endpoint returns correct fields."""
        db = _install_auth()

        ownership_result = MagicMock()
        ownership_result.fetchone.return_value = MagicMock()

        last_sync = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
        status_data = {
            "connection_id": TEST_CONNECTION_ID,
            "last_sync_at": last_sync,
            "last_sync_error": None,
            "next_sync_at": last_sync + timedelta(hours=24),
            "sync_frequency_hours": 24,
        }

        with patch(
            "services.connection_sync_service.ConnectionSyncService.get_sync_status",
            new_callable=AsyncMock,
            return_value=status_data,
        ):
            db.execute = AsyncMock(return_value=ownership_result)
            response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/sync-status")

        assert response.status_code == 200
        data = response.json()
        assert data["connection_id"] == TEST_CONNECTION_ID
        assert data["sync_frequency_hours"] == 24
        assert data["last_sync_at"] is not None

    def test_sync_status_not_found(self, client):
        """Non-existent connection_id returns 404."""
        db = _install_auth()

        not_found = MagicMock()
        not_found.fetchone.return_value = None
        db.execute = AsyncMock(return_value=not_found)

        response = client.get(f"{BASE}/{uuid4()}/sync-status")
        assert response.status_code == 404

    def test_sync_status_never_synced(self, client):
        """Never-synced connection returns null last_sync_at and next_sync_at."""
        db = _install_auth()

        ownership_result = MagicMock()
        ownership_result.fetchone.return_value = MagicMock()

        status_data = {
            "connection_id": TEST_CONNECTION_ID,
            "last_sync_at": None,
            "last_sync_error": None,
            "next_sync_at": None,
            "sync_frequency_hours": 24,
        }

        with patch(
            "services.connection_sync_service.ConnectionSyncService.get_sync_status",
            new_callable=AsyncMock,
            return_value=status_data,
        ):
            db.execute = AsyncMock(return_value=ownership_result)
            response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/sync-status")

        assert response.status_code == 200
        data = response.json()
        assert data["last_sync_at"] is None
        assert data["next_sync_at"] is None


class TestAuthorizationCallbackEndpoint:
    """Tests for GET /connections/direct/callback."""

    # HMAC test key used for signing callback state parameters
    _HMAC_TEST_KEY = "test-hmac-key-for-callback-state"

    def _sign_state(self, connection_id: str, user_id: str = None) -> str:
        """Sign a connection_id + user_id using the test HMAC key."""
        from api.v1.connections import sign_callback_state

        if user_id is None:
            user_id = TEST_USER_ID
        with patch("api.v1.connections.settings") as mock_settings:
            mock_settings.internal_api_key = self._HMAC_TEST_KEY
            return sign_callback_state(connection_id, user_id)

    def _setup_callback_db(self, db, connection_found: bool = True, status: str = "pending", user_id: str = None):
        """Configure DB mock for callback tests."""
        if user_id is None:
            user_id = TEST_USER_ID
        if connection_found:
            conn_row = _DictRow({"id": TEST_CONNECTION_ID, "user_id": user_id, "status": status})
            conn_result = MagicMock()
            conn_result.mappings.return_value.first.return_value = conn_row
            conn_result.fetchone.return_value = conn_row
        else:
            conn_result = MagicMock()
            conn_result.mappings.return_value.first.return_value = None
            conn_result.fetchone.return_value = None

        update_result = MagicMock()
        db.execute = AsyncMock(side_effect=[conn_result, update_result])

    def test_callback_activates_connection(self, client):
        """Valid callback with HMAC-signed state activates connection."""
        from main import app
        from api.dependencies import get_db_session

        db = _mock_db()
        self._setup_callback_db(db)
        app.dependency_overrides[get_db_session] = lambda: db

        signed_state = self._sign_state(TEST_CONNECTION_ID)
        mock_auth_status = {"uid": TEST_AUTH_UID, "status": "active"}

        with patch(
            "integrations.utilityapi.UtilityAPIClient.get_authorization_status",
            new_callable=AsyncMock,
            return_value=mock_auth_status,
        ), patch(
            "integrations.utilityapi.UtilityAPIClient.close",
            new_callable=AsyncMock,
        ), patch(
            "utils.encryption.encrypt_field",
            return_value=b"encrypted_uid",
        ), patch(
            "services.connection_sync_service.ConnectionSyncService.sync_connection",
            new_callable=AsyncMock,
            return_value={
                "connection_id": TEST_CONNECTION_ID,
                "success": True,
                "new_rates_found": 0,
                "error": None,
                "synced_at": datetime.now(timezone.utc),
            },
        ), patch(
            "api.v1.connections.settings"
        ) as mock_settings:
            mock_settings.internal_api_key = self._HMAC_TEST_KEY
            response = client.get(
                f"{BASE}/direct/callback",
                params={
                    "authorization_uid": TEST_AUTH_UID,
                    "state": signed_state,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"
        assert data["connection_id"] == TEST_CONNECTION_ID

    def test_callback_rejects_unsigned_state(self, client):
        """Callback with raw (unsigned) connection_id as state returns 400."""
        from main import app
        from api.dependencies import get_db_session

        db = _mock_db()
        app.dependency_overrides[get_db_session] = lambda: db

        with patch("api.v1.connections.settings") as mock_settings:
            mock_settings.internal_api_key = self._HMAC_TEST_KEY
            response = client.get(
                f"{BASE}/direct/callback",
                params={
                    "authorization_uid": TEST_AUTH_UID,
                    "state": TEST_CONNECTION_ID,  # unsigned
                },
            )

        assert response.status_code == 400

    def test_callback_rejects_tampered_hmac(self, client):
        """Callback with tampered HMAC signature returns 400."""
        from main import app
        from api.dependencies import get_db_session

        db = _mock_db()
        app.dependency_overrides[get_db_session] = lambda: db

        tampered_state = f"{TEST_CONNECTION_ID}:deadbeef0000"

        with patch("api.v1.connections.settings") as mock_settings:
            mock_settings.internal_api_key = self._HMAC_TEST_KEY
            response = client.get(
                f"{BASE}/direct/callback",
                params={
                    "authorization_uid": TEST_AUTH_UID,
                    "state": tampered_state,
                },
            )

        assert response.status_code == 400

    def test_callback_connection_not_found(self, client):
        """Callback for unknown connection_id returns 404."""
        from main import app
        from api.dependencies import get_db_session

        db = _mock_db()
        self._setup_callback_db(db, connection_found=False)
        app.dependency_overrides[get_db_session] = lambda: db

        unknown_id = str(uuid4())
        signed_state = self._sign_state(unknown_id)

        with patch("api.v1.connections.settings") as mock_settings:
            mock_settings.internal_api_key = self._HMAC_TEST_KEY
            response = client.get(
                f"{BASE}/direct/callback",
                params={
                    "authorization_uid": TEST_AUTH_UID,
                    "state": signed_state,
                },
            )

        assert response.status_code == 404

    def test_callback_inactive_authorization_returns_error_status(self, client):
        """Revoked UtilityAPI authorization sets connection status to error."""
        from main import app
        from api.dependencies import get_db_session

        db = _mock_db()
        conn_row = _DictRow({"id": TEST_CONNECTION_ID, "user_id": TEST_USER_ID, "status": "pending"})
        conn_result = MagicMock()
        conn_result.mappings.return_value.first.return_value = conn_row
        conn_result.fetchone.return_value = conn_row
        update_result = MagicMock()
        db.execute = AsyncMock(side_effect=[conn_result, update_result])
        app.dependency_overrides[get_db_session] = lambda: db

        signed_state = self._sign_state(TEST_CONNECTION_ID)

        with patch(
            "integrations.utilityapi.UtilityAPIClient.get_authorization_status",
            new_callable=AsyncMock,
            return_value={"uid": TEST_AUTH_UID, "status": "revoked"},
        ), patch(
            "integrations.utilityapi.UtilityAPIClient.close",
            new_callable=AsyncMock,
        ), patch(
            "api.v1.connections.settings"
        ) as mock_settings:
            mock_settings.internal_api_key = self._HMAC_TEST_KEY
            response = client.get(
                f"{BASE}/direct/callback",
                params={
                    "authorization_uid": TEST_AUTH_UID,
                    "state": signed_state,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

    def test_callback_utilityapi_error_sets_error_status(self, client):
        """UtilityAPI verification failure returns error status (not 500)."""
        from main import app
        from api.dependencies import get_db_session
        from integrations.utilityapi import UtilityAPIError

        db = _mock_db()
        conn_row = _DictRow({"id": TEST_CONNECTION_ID, "user_id": TEST_USER_ID, "status": "pending"})
        conn_result = MagicMock()
        conn_result.mappings.return_value.first.return_value = conn_row
        conn_result.fetchone.return_value = conn_row
        update_result = MagicMock()
        db.execute = AsyncMock(side_effect=[conn_result, update_result])
        app.dependency_overrides[get_db_session] = lambda: db

        signed_state = self._sign_state(TEST_CONNECTION_ID)

        with patch(
            "integrations.utilityapi.UtilityAPIClient.get_authorization_status",
            new_callable=AsyncMock,
            side_effect=UtilityAPIError("Service unavailable", status_code=503),
        ), patch(
            "integrations.utilityapi.UtilityAPIClient.close",
            new_callable=AsyncMock,
        ), patch(
            "api.v1.connections.settings"
        ) as mock_settings:
            mock_settings.internal_api_key = self._HMAC_TEST_KEY
            response = client.get(
                f"{BASE}/direct/callback",
                params={
                    "authorization_uid": TEST_AUTH_UID,
                    "state": signed_state,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

    def test_callback_missing_authorization_uid_returns_422(self, client):
        """Missing required authorization_uid query param → 422."""
        from main import app
        from api.dependencies import get_db_session

        db = _mock_db()
        app.dependency_overrides[get_db_session] = lambda: db

        signed_state = self._sign_state(TEST_CONNECTION_ID)

        response = client.get(
            f"{BASE}/direct/callback",
            params={"state": signed_state},
            # authorization_uid intentionally omitted
        )
        assert response.status_code == 422

    def test_callback_missing_state_returns_422(self, client):
        """Missing required state query param → 422."""
        from main import app
        from api.dependencies import get_db_session

        db = _mock_db()
        app.dependency_overrides[get_db_session] = lambda: db

        response = client.get(
            f"{BASE}/direct/callback",
            params={"authorization_uid": TEST_AUTH_UID},
            # state intentionally omitted
        )
        assert response.status_code == 422


# ===========================================================================
# Part 4 — Pydantic model validation tests
# ===========================================================================


class TestSyncModels:
    """Pure Pydantic model validation for Phase 4 models."""

    def test_sync_status_response_defaults(self):
        """SyncStatusResponse populates correctly with minimal fields."""
        from models.connections import SyncStatusResponse

        model = SyncStatusResponse(connection_id=TEST_CONNECTION_ID)
        assert model.connection_id == TEST_CONNECTION_ID
        assert model.last_sync_at is None
        assert model.sync_frequency_hours == 24
        assert model.next_sync_at is None
        assert model.last_sync_error is None

    def test_sync_result_response_success(self):
        """SyncResultResponse serializes correctly for a successful sync."""
        from models.connections import SyncResultResponse

        now = datetime.now(timezone.utc)
        model = SyncResultResponse(
            connection_id=TEST_CONNECTION_ID,
            success=True,
            new_rates_found=5,
            synced_at=now,
        )
        d = model.model_dump()
        assert d["success"] is True
        assert d["new_rates_found"] == 5
        assert d["error"] is None

    def test_sync_result_response_failure(self):
        """SyncResultResponse serializes correctly for a failed sync."""
        from models.connections import SyncResultResponse

        now = datetime.now(timezone.utc)
        model = SyncResultResponse(
            connection_id=TEST_CONNECTION_ID,
            success=False,
            new_rates_found=0,
            error="No meters found.",
            synced_at=now,
        )
        d = model.model_dump()
        assert d["success"] is False
        assert d["error"] == "No meters found."

    def test_authorization_callback_response(self):
        """AuthorizationCallbackResponse serializes correctly."""
        from models.connections import AuthorizationCallbackResponse

        model = AuthorizationCallbackResponse(
            connection_id=TEST_CONNECTION_ID,
            status="active",
            message="Authorization successful.",
        )
        d = model.model_dump()
        assert d["status"] == "active"
        assert d["connection_id"] == TEST_CONNECTION_ID
