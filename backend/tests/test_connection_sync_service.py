"""Tests for ConnectionSyncService."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.connection_sync_service import (
    _DEFAULT_SYNC_FREQUENCY_HOURS,
    ConnectionSyncService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _AsyncNullCtx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _null_ctx():
    return _AsyncNullCtx()


def _make_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _make_row(**kwargs):
    row = MagicMock()
    row.__getitem__ = lambda self, key: kwargs[key]
    row.get = lambda key, default=None: kwargs.get(key, default)
    return row


def _mappings_first(row):
    result = MagicMock()
    result.mappings.return_value.first.return_value = row
    return result


def _fetchall(rows):
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


# ---------------------------------------------------------------------------
# get_sync_status
# ---------------------------------------------------------------------------


class TestGetSyncStatus:
    @pytest.mark.asyncio
    async def test_returns_none_when_connection_not_found(self):
        db = _make_db()
        db.execute.return_value = _mappings_first(None)
        svc = ConnectionSyncService(db)
        result = await svc.get_sync_status("cid-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_status_dict_with_fields(self):
        db = _make_db()
        last_sync = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
        row = _make_row(
            id="cid-1",
            last_sync_at=last_sync,
            last_sync_error=None,
            sync_frequency_hours=24,
        )
        db.execute.return_value = _mappings_first(row)
        svc = ConnectionSyncService(db)
        result = await svc.get_sync_status("cid-1")
        assert result is not None
        assert result["connection_id"] == "cid-1"
        assert result["last_sync_at"] == last_sync
        assert result["sync_frequency_hours"] == 24

    @pytest.mark.asyncio
    async def test_computes_next_sync_at_from_last_sync(self):
        db = _make_db()
        last_sync = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
        row = _make_row(
            id="cid-1",
            last_sync_at=last_sync,
            last_sync_error=None,
            sync_frequency_hours=12,
        )
        db.execute.return_value = _mappings_first(row)
        svc = ConnectionSyncService(db)
        result = await svc.get_sync_status("cid-1")
        expected_next = last_sync + timedelta(hours=12)
        assert result["next_sync_at"] == expected_next

    @pytest.mark.asyncio
    async def test_next_sync_at_is_none_when_no_last_sync(self):
        db = _make_db()
        row = _make_row(
            id="cid-1", last_sync_at=None, last_sync_error=None, sync_frequency_hours=24
        )
        db.execute.return_value = _mappings_first(row)
        svc = ConnectionSyncService(db)
        result = await svc.get_sync_status("cid-1")
        assert result["next_sync_at"] is None

    @pytest.mark.asyncio
    async def test_db_error_returns_fallback_dict(self):
        db = _make_db()
        db.execute.side_effect = Exception("column missing")
        svc = ConnectionSyncService(db)
        result = await svc.get_sync_status("cid-1")
        assert result is not None
        assert result["connection_id"] == "cid-1"
        assert result["last_sync_at"] is None
        assert result["sync_frequency_hours"] == _DEFAULT_SYNC_FREQUENCY_HOURS


# ---------------------------------------------------------------------------
# sync_all_due
# ---------------------------------------------------------------------------


class TestSyncAllDue:
    @pytest.mark.asyncio
    async def test_db_error_returns_empty_list(self):
        db = _make_db()
        db.execute.side_effect = Exception("column missing")
        svc = ConnectionSyncService(db)
        result = await svc.sync_all_due()
        assert result == []

    @pytest.mark.asyncio
    async def test_no_due_connections_returns_empty_list(self):
        db = _make_db()
        db.execute.return_value = _fetchall([])
        svc = ConnectionSyncService(db)
        result = await svc.sync_all_due()
        assert result == []

    @pytest.mark.asyncio
    async def test_calls_sync_connection_for_each_due_id(self):
        db = _make_db()
        # Two rows in fetchall
        row1 = MagicMock()
        row1.__getitem__ = lambda self, i: "cid-1"
        row2 = MagicMock()
        row2.__getitem__ = lambda self, i: "cid-2"
        db.execute.return_value = _fetchall([row1, row2])

        svc = ConnectionSyncService(db)
        fake_result = {"connection_id": "x", "success": True, "new_rates_found": 0, "error": None}
        svc.sync_connection = AsyncMock(return_value=fake_result)

        results = await svc.sync_all_due()
        assert svc.sync_connection.await_count == 2
        assert len(results) == 2


# ---------------------------------------------------------------------------
# sync_connection — early exit paths
# ---------------------------------------------------------------------------


class TestSyncConnectionEarlyExits:
    @pytest.mark.asyncio
    async def test_returns_error_when_connection_not_found(self):
        db = _make_db()
        svc = ConnectionSyncService(db)
        # _fetch_connection returns None
        svc._fetch_connection = AsyncMock(return_value=None)
        with patch("services.connection_sync_service.traced", return_value=_null_ctx()):
            result = await svc.sync_connection("cid-missing")
        assert result["success"] is False
        assert "not found" in result["error"].lower()
        assert result["connection_id"] == "cid-missing"
        assert result["new_rates_found"] == 0

    @pytest.mark.asyncio
    async def test_returns_error_when_no_auth_uid(self):
        db = _make_db()
        svc = ConnectionSyncService(db)
        svc._fetch_connection = AsyncMock(
            return_value={"id": "cid-1", "status": "active", "utilityapi_auth_uid_encrypted": None}
        )
        svc._persist_sync_result = AsyncMock()
        with patch("services.connection_sync_service.traced", return_value=_null_ctx()):
            result = await svc.sync_connection("cid-1")
        assert result["success"] is False
        assert "not yet authorized" in result["error"]

    @pytest.mark.asyncio
    async def test_returns_error_when_decrypt_fails(self):
        db = _make_db()
        svc = ConnectionSyncService(db)
        svc._fetch_connection = AsyncMock(
            return_value={
                "id": "cid-1",
                "status": "active",
                "utilityapi_auth_uid_encrypted": b"bad-ciphertext",
                "last_sync_at": None,
            }
        )
        svc._persist_sync_result = AsyncMock()
        with (
            patch("services.connection_sync_service.traced", return_value=_null_ctx()),
            patch(
                "services.connection_sync_service.decrypt_field", side_effect=ValueError("bad key")
            ),
        ):
            result = await svc.sync_connection("cid-1")
        assert result["success"] is False
        assert "decrypt" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_returns_error_when_meters_fetch_fails(self):
        from integrations.utilityapi import UtilityAPIError

        db = _make_db()
        client = AsyncMock()
        client.get_meters.side_effect = UtilityAPIError("503 Service Unavailable")
        svc = ConnectionSyncService(db, utilityapi_client=client)
        svc._fetch_connection = AsyncMock(
            return_value={
                "id": "cid-1",
                "status": "active",
                "utilityapi_auth_uid_encrypted": "encrypted",
                "last_sync_at": None,
            }
        )
        svc._persist_sync_result = AsyncMock()
        with (
            patch("services.connection_sync_service.traced", return_value=_null_ctx()),
            patch("services.connection_sync_service.decrypt_field", return_value="auth-uid-123"),
        ):
            result = await svc.sync_connection("cid-1")
        assert result["success"] is False
        assert "meters" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_returns_error_when_no_meters_returned(self):
        db = _make_db()
        client = AsyncMock()
        client.get_meters.return_value = []
        svc = ConnectionSyncService(db, utilityapi_client=client)
        svc._fetch_connection = AsyncMock(
            return_value={
                "id": "cid-1",
                "status": "active",
                "utilityapi_auth_uid_encrypted": "encrypted",
                "last_sync_at": None,
            }
        )
        svc._persist_sync_result = AsyncMock()
        with (
            patch("services.connection_sync_service.traced", return_value=_null_ctx()),
            patch("services.connection_sync_service.decrypt_field", return_value="auth-uid-123"),
        ):
            result = await svc.sync_connection("cid-1")
        assert result["success"] is False
        assert "No meters" in result["error"]


# ---------------------------------------------------------------------------
# _batch_insert_extracted_rates
# ---------------------------------------------------------------------------


class TestBatchInsertExtractedRates:
    @pytest.mark.asyncio
    async def test_noop_on_empty_list(self):
        db = _make_db()
        svc = ConnectionSyncService(db)
        await svc._batch_insert_extracted_rates("cid-1", [])
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_calls_execute_with_single_rate(self):
        db = _make_db()
        svc = ConnectionSyncService(db)
        rate = {
            "rate_per_kwh": 0.12,
            "effective_date": datetime(2026, 5, 1, tzinfo=UTC),
            "source": "bill",
            "raw_label": "Standard Rate",
        }
        await svc._batch_insert_extracted_rates("cid-1", [rate])
        db.execute.assert_awaited_once()
        call_args = db.execute.await_args
        sql = str(call_args[0][0])
        assert "INSERT INTO connection_extracted_rates" in sql
        params = call_args[0][1]
        assert params["rate0"] == 0.12
        assert params["cid0"] == "cid-1"

    @pytest.mark.asyncio
    async def test_builds_one_insert_for_multiple_rates(self):
        db = _make_db()
        svc = ConnectionSyncService(db)
        rates = [
            {
                "rate_per_kwh": 0.10,
                "effective_date": datetime(2026, 5, 1, tzinfo=UTC),
                "source": "bill",
            },
            {
                "rate_per_kwh": 0.11,
                "effective_date": datetime(2026, 5, 2, tzinfo=UTC),
                "source": "bill",
            },
            {
                "rate_per_kwh": 0.12,
                "effective_date": datetime(2026, 5, 3, tzinfo=UTC),
                "source": "bill",
            },
        ]
        await svc._batch_insert_extracted_rates("cid-1", rates)
        # Single execute call for all 3 rows
        assert db.execute.await_count == 1
        params = db.execute.await_args[0][1]
        assert params["rate0"] == 0.10
        assert params["rate1"] == 0.11
        assert params["rate2"] == 0.12

    @pytest.mark.asyncio
    async def test_raw_label_defaults_to_none_when_missing(self):
        db = _make_db()
        svc = ConnectionSyncService(db)
        rate = {
            "rate_per_kwh": 0.09,
            "effective_date": datetime(2026, 5, 1, tzinfo=UTC),
            "source": "bill",
            # no raw_label key
        }
        await svc._batch_insert_extracted_rates("cid-1", [rate])
        params = db.execute.await_args[0][1]
        assert params["label0"] is None
