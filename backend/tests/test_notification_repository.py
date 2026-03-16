"""
Tests for NotificationRepository (backend/repositories/notification_repository.py)

Coverage:
  1. Migration 032 SQL structural checks — error_message column and channel+created_at index.
  2. Notification model — error_message field present with None default.
  3. NotificationDeliveryUpdate — error_message accepted in schema.
  4. NotificationRepository.get_by_id — found and not-found cases.
  5. NotificationRepository.get_by_delivery_status — queries by user+status.
  6. NotificationRepository.get_by_channel — queries by user+channel.
  7. NotificationRepository.update_delivery — partial update, full update, not-found.
  8. NotificationDispatcher delivery tracking — channel set in IN_APP INSERT,
     push/email outcomes persisted via update_delivery.
"""

import json
import os
import re
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Helpers for mock DB results
# ---------------------------------------------------------------------------

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "migrations")
MIGRATION_PREFIX = "032"


def _read_migration_032() -> str:
    """Return the raw SQL content of migration 032."""
    for filename in os.listdir(MIGRATIONS_DIR):
        if filename.startswith(MIGRATION_PREFIX) and filename.endswith(".sql"):
            path = os.path.join(MIGRATIONS_DIR, filename)
            with open(path) as fh:
                return fh.read()
    raise FileNotFoundError(
        f"No migration file starting with '{MIGRATION_PREFIX}' found in {MIGRATIONS_DIR}"
    )


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


def _scalar_result(value) -> MagicMock:
    result = MagicMock()
    result.scalar.return_value = value
    result.rowcount = 0
    return result


def _mapping_result(rows: list) -> MagicMock:
    """
    Mock for db.execute() that simulates result.mappings().fetchall() / .first()
    returning a list of dict-like objects (Mapping interface).
    """
    result = MagicMock()
    mappings_obj = MagicMock()
    mappings_obj.fetchall.return_value = [_dict_row(r) for r in rows]
    mappings_obj.first.return_value = _dict_row(rows[0]) if rows else None
    result.mappings.return_value = mappings_obj
    result.rowcount = len(rows)
    return result


def _rowcount_result(count: int) -> MagicMock:
    """Mock for an UPDATE execute result."""
    result = MagicMock()
    result.rowcount = count
    return result


def _dict_row(d: dict):
    """Return a MagicMock that supports key-based access like a DB row Mapping."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: d[key]
    row.get = lambda key, default=None: d.get(key, default)
    return row


def _notification_row(
    nid: str = None,
    user_id: str = None,
    delivery_status: str = "pending",
    delivery_channel: str = None,
    retry_count: int = 0,
    error_message: str = None,
) -> dict:
    """Build a minimal notifications table row dict."""
    return {
        "id": nid or str(uuid4()),
        "user_id": user_id or str(uuid4()),
        "type": "info",
        "title": "Test notification",
        "body": None,
        "read_at": None,
        "created_at": datetime.now(timezone.utc),
        "metadata": None,
        "delivery_channel": delivery_channel,
        "delivery_status": delivery_status,
        "delivered_at": None,
        "delivery_metadata": {},
        "retry_count": retry_count,
        "error_message": error_message,
    }


# ===========================================================================
# 1. Migration 032 SQL structural checks
# ===========================================================================


class TestMigration032Structure:
    """Parse migration 032 SQL for correctness without executing it."""

    def test_migration_file_exists(self):
        sql = _read_migration_032()
        assert sql.strip(), "Migration 032 file is empty"

    def test_targets_notifications_table(self):
        sql = _read_migration_032()
        assert "notifications" in sql.lower()

    def test_alter_table_uses_if_not_exists(self):
        sql = _read_migration_032()
        for i, line in enumerate(sql.splitlines(), 1):
            stripped = line.strip().upper()
            if stripped.startswith("--"):
                continue
            if "ADD COLUMN" in stripped and "IF NOT EXISTS" not in stripped:
                pytest.fail(f"ADD COLUMN without IF NOT EXISTS at line {i}: {line.strip()}")

    def test_error_message_column_present(self):
        sql = _read_migration_032()
        assert "error_message" in sql.lower(), (
            "Migration 032 must add the error_message column"
        )

    def test_error_message_is_text_type(self):
        sql = _read_migration_032()
        # Must have: ADD COLUMN IF NOT EXISTS error_message TEXT
        normalised = re.sub(r"\s+", " ", sql.lower())
        assert re.search(r"add column if not exists error_message text", normalised), (
            "error_message must be defined as TEXT"
        )

    def test_index_on_channel_created_at(self):
        sql = _read_migration_032()
        normalised = re.sub(r"\s+", " ", sql.lower())
        # Must have a CREATE INDEX covering delivery_channel and created_at
        assert "delivery_channel" in normalised, (
            "Migration 032 must reference delivery_channel in an index"
        )
        assert "created_at" in normalised, (
            "Migration 032 must include created_at in an index"
        )
        assert re.search(
            r"create index if not exists\s+\w+\s+on notifications\s*\(",
            normalised,
        ), "Migration 032 must CREATE INDEX IF NOT EXISTS on the notifications table"

    def test_index_uses_if_not_exists(self):
        sql = _read_migration_032()
        for i, line in enumerate(sql.splitlines(), 1):
            stripped = line.strip().upper()
            if stripped.startswith("--"):
                continue
            if (
                stripped.startswith("CREATE INDEX")
                and "IF NOT EXISTS" not in stripped
            ):
                pytest.fail(f"CREATE INDEX without IF NOT EXISTS at line {i}: {line.strip()}")

    def test_no_serial_columns(self):
        sql = _read_migration_032()
        assert "SERIAL" not in sql.upper()

    def test_contains_grant_to_neondb_owner(self):
        sql = _read_migration_032()
        assert "neondb_owner" in sql


# ===========================================================================
# 2. Notification model — error_message field
# ===========================================================================


class TestNotificationModelErrorMessage:
    """Verify the error_message field is present in Notification and related schemas."""

    def test_model_has_error_message(self):
        from models.notification import Notification
        assert "error_message" in Notification.model_fields

    def test_error_message_defaults_to_none(self):
        from models.notification import Notification
        n = Notification(user_id="u1", title="T")
        assert n.error_message is None

    def test_error_message_accepts_string(self):
        from models.notification import Notification
        n = Notification(user_id="u1", title="T", error_message="SMTP timeout")
        assert n.error_message == "SMTP timeout"

    def test_delivery_update_has_error_message(self):
        from models.notification import NotificationDeliveryUpdate
        upd = NotificationDeliveryUpdate(
            delivery_status="failed",
            error_message="Connection refused",
        )
        assert upd.error_message == "Connection refused"

    def test_delivery_update_error_message_optional(self):
        from models.notification import NotificationDeliveryUpdate
        upd = NotificationDeliveryUpdate(delivery_status="sent")
        assert upd.error_message is None


# ===========================================================================
# 3. NotificationRepository.get_by_id
# ===========================================================================


class TestNotificationRepositoryGetById:

    @pytest.mark.asyncio
    async def test_get_by_id_returns_notification(self):
        from repositories.notification_repository import NotificationRepository
        nid = str(uuid4())
        uid = str(uuid4())
        db = _mock_db()
        db.execute.return_value = _mapping_result([_notification_row(nid=nid, user_id=uid)])
        repo = NotificationRepository(db)

        result = await repo.get_by_id(nid, user_id=uid)

        assert result is not None
        assert result.id == nid
        assert result.user_id == uid

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_when_not_found(self):
        from repositories.notification_repository import NotificationRepository
        db = _mock_db()
        db.execute.return_value = _mapping_result([])
        repo = NotificationRepository(db)

        result = await repo.get_by_id(str(uuid4()), user_id=str(uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_raises_repository_error_on_db_failure(self):
        from repositories.notification_repository import NotificationRepository
        from repositories.base import RepositoryError
        db = _mock_db()
        db.execute.side_effect = Exception("DB down")
        repo = NotificationRepository(db)

        with pytest.raises(RepositoryError):
            await repo.get_by_id(str(uuid4()), user_id=str(uuid4()))

    @pytest.mark.asyncio
    async def test_get_by_id_maps_error_message(self):
        from repositories.notification_repository import NotificationRepository
        nid = str(uuid4())
        uid = str(uuid4())
        db = _mock_db()
        db.execute.return_value = _mapping_result([
            _notification_row(nid=nid, user_id=uid, error_message="Push token expired")
        ])
        repo = NotificationRepository(db)

        result = await repo.get_by_id(nid, user_id=uid)
        assert result.error_message == "Push token expired"

    @pytest.mark.asyncio
    async def test_get_by_id_rejects_wrong_user(self):
        """IDOR protection: querying with a different user_id returns None."""
        from repositories.notification_repository import NotificationRepository
        nid = str(uuid4())
        owner_uid = str(uuid4())
        attacker_uid = str(uuid4())
        db = _mock_db()
        # The SQL WHERE clause filters by user_id, so DB returns no rows for wrong user
        db.execute.return_value = _mapping_result([])
        repo = NotificationRepository(db)

        result = await repo.get_by_id(nid, user_id=attacker_uid)
        assert result is None

        # Verify the query included user_id parameter
        call_args = db.execute.call_args
        params = call_args.args[1] if call_args.args else call_args.kwargs
        assert params["uid"] == attacker_uid


# ===========================================================================
# 4. NotificationRepository.get_by_delivery_status
# ===========================================================================


class TestNotificationRepositoryGetByDeliveryStatus:

    @pytest.mark.asyncio
    async def test_returns_notifications_for_status(self):
        from repositories.notification_repository import NotificationRepository
        uid = str(uuid4())
        rows = [
            _notification_row(user_id=uid, delivery_status="failed"),
            _notification_row(user_id=uid, delivery_status="failed"),
        ]
        db = _mock_db()
        db.execute.return_value = _mapping_result(rows)
        repo = NotificationRepository(db)

        results = await repo.get_by_delivery_status(uid, "failed")
        assert len(results) == 2
        assert all(r.delivery_status == "failed" for r in results)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none_match(self):
        from repositories.notification_repository import NotificationRepository
        db = _mock_db()
        db.execute.return_value = _mapping_result([])
        repo = NotificationRepository(db)

        results = await repo.get_by_delivery_status(str(uuid4()), "bounced")
        assert results == []

    @pytest.mark.asyncio
    async def test_query_includes_user_id_and_status_params(self):
        from repositories.notification_repository import NotificationRepository
        uid = str(uuid4())
        db = _mock_db()
        db.execute.return_value = _mapping_result([])
        repo = NotificationRepository(db)

        await repo.get_by_delivery_status(uid, "pending", limit=10)

        call_args = db.execute.call_args
        params = call_args.args[1] if call_args.args else call_args.kwargs
        assert params["uid"] == uid
        assert params["status"] == "pending"
        assert params["lim"] == 10

    @pytest.mark.asyncio
    async def test_raises_repository_error_on_failure(self):
        from repositories.notification_repository import NotificationRepository
        from repositories.base import RepositoryError
        db = _mock_db()
        db.execute.side_effect = Exception("timeout")
        repo = NotificationRepository(db)

        with pytest.raises(RepositoryError):
            await repo.get_by_delivery_status(str(uuid4()), "sent")

    @pytest.mark.parametrize("status", ["pending", "sent", "delivered", "failed", "bounced"])
    @pytest.mark.asyncio
    async def test_all_valid_statuses_accepted(self, status):
        from repositories.notification_repository import NotificationRepository
        db = _mock_db()
        db.execute.return_value = _mapping_result([])
        repo = NotificationRepository(db)
        # Should not raise
        results = await repo.get_by_delivery_status(str(uuid4()), status)
        assert isinstance(results, list)


# ===========================================================================
# 5. NotificationRepository.get_by_channel
# ===========================================================================


class TestNotificationRepositoryGetByChannel:

    @pytest.mark.asyncio
    async def test_returns_notifications_for_channel(self):
        from repositories.notification_repository import NotificationRepository
        uid = str(uuid4())
        rows = [
            _notification_row(user_id=uid, delivery_channel="email"),
        ]
        db = _mock_db()
        db.execute.return_value = _mapping_result(rows)
        repo = NotificationRepository(db)

        results = await repo.get_by_channel(uid, "email")
        assert len(results) == 1
        assert results[0].delivery_channel == "email"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_match(self):
        from repositories.notification_repository import NotificationRepository
        db = _mock_db()
        db.execute.return_value = _mapping_result([])
        repo = NotificationRepository(db)

        results = await repo.get_by_channel(str(uuid4()), "push")
        assert results == []

    @pytest.mark.asyncio
    async def test_query_includes_user_id_and_channel_params(self):
        from repositories.notification_repository import NotificationRepository
        uid = str(uuid4())
        db = _mock_db()
        db.execute.return_value = _mapping_result([])
        repo = NotificationRepository(db)

        await repo.get_by_channel(uid, "in_app", limit=25)

        call_args = db.execute.call_args
        params = call_args.args[1] if call_args.args else call_args.kwargs
        assert params["uid"] == uid
        assert params["channel"] == "in_app"
        assert params["lim"] == 25

    @pytest.mark.asyncio
    async def test_raises_repository_error_on_failure(self):
        from repositories.notification_repository import NotificationRepository
        from repositories.base import RepositoryError
        db = _mock_db()
        db.execute.side_effect = Exception("connection refused")
        repo = NotificationRepository(db)

        with pytest.raises(RepositoryError):
            await repo.get_by_channel(str(uuid4()), "push")

    @pytest.mark.parametrize("channel", ["email", "push", "in_app"])
    @pytest.mark.asyncio
    async def test_all_valid_channels_accepted(self, channel):
        from repositories.notification_repository import NotificationRepository
        db = _mock_db()
        db.execute.return_value = _mapping_result([])
        repo = NotificationRepository(db)
        results = await repo.get_by_channel(str(uuid4()), channel)
        assert isinstance(results, list)


# ===========================================================================
# 6. NotificationRepository.update_delivery
# ===========================================================================


class TestNotificationRepositoryUpdateDelivery:

    @pytest.mark.asyncio
    async def test_update_delivery_status_only(self):
        from repositories.notification_repository import NotificationRepository
        from models.notification import NotificationDeliveryUpdate
        nid = str(uuid4())
        db = _mock_db()
        db.execute.return_value = _rowcount_result(1)
        repo = NotificationRepository(db)

        upd = NotificationDeliveryUpdate(delivery_status="sent")
        ok = await repo.update_delivery(nid, upd)

        assert ok is True
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_with_all_fields(self):
        from repositories.notification_repository import NotificationRepository
        from models.notification import NotificationDeliveryUpdate
        nid = str(uuid4())
        now = datetime.now(timezone.utc)
        db = _mock_db()
        db.execute.return_value = _rowcount_result(1)
        repo = NotificationRepository(db)

        upd = NotificationDeliveryUpdate(
            delivery_status="delivered",
            delivery_channel="email",
            delivered_at=now,
            delivery_metadata={"message_id": "msg_abc123"},
            retry_count=2,
            error_message=None,
        )
        ok = await repo.update_delivery(nid, upd)

        assert ok is True
        call_args = db.execute.call_args
        # Check that all fields are in the params
        params = call_args.args[1] if call_args.args else call_args.kwargs
        assert params["delivery_status"] == "delivered"
        assert params["delivery_channel"] == "email"
        assert params["delivered_at"] == now
        assert params["retry_count"] == 2

    @pytest.mark.asyncio
    async def test_update_with_error_message(self):
        from repositories.notification_repository import NotificationRepository
        from models.notification import NotificationDeliveryUpdate
        nid = str(uuid4())
        db = _mock_db()
        db.execute.return_value = _rowcount_result(1)
        repo = NotificationRepository(db)

        upd = NotificationDeliveryUpdate(
            delivery_status="failed",
            error_message="SMTP connection timeout",
        )
        ok = await repo.update_delivery(nid, upd)

        assert ok is True
        call_args = db.execute.call_args
        params = call_args.args[1] if call_args.args else call_args.kwargs
        assert params["error_message"] == "SMTP connection timeout"

    @pytest.mark.asyncio
    async def test_update_returns_false_when_not_found(self):
        from repositories.notification_repository import NotificationRepository
        from models.notification import NotificationDeliveryUpdate
        db = _mock_db()
        db.execute.return_value = _rowcount_result(0)
        repo = NotificationRepository(db)

        upd = NotificationDeliveryUpdate(delivery_status="sent")
        ok = await repo.update_delivery(str(uuid4()), upd)

        assert ok is False

    @pytest.mark.asyncio
    async def test_update_raises_repository_error_on_failure(self):
        from repositories.notification_repository import NotificationRepository
        from models.notification import NotificationDeliveryUpdate
        from repositories.base import RepositoryError
        db = _mock_db()
        db.execute.side_effect = Exception("DB locked")
        repo = NotificationRepository(db)

        upd = NotificationDeliveryUpdate(delivery_status="failed")
        with pytest.raises(RepositoryError):
            await repo.update_delivery(str(uuid4()), upd)

    @pytest.mark.asyncio
    async def test_only_non_none_fields_included_in_update(self):
        """None fields must NOT produce SET clauses (partial update semantics)."""
        from repositories.notification_repository import NotificationRepository
        from models.notification import NotificationDeliveryUpdate
        nid = str(uuid4())
        db = _mock_db()
        db.execute.return_value = _rowcount_result(1)
        repo = NotificationRepository(db)

        upd = NotificationDeliveryUpdate(delivery_status="sent")
        await repo.update_delivery(nid, upd)

        call_args = db.execute.call_args
        sql = str(call_args.args[0]).upper()
        # These optional columns must NOT appear in the SET clause
        assert "DELIVERY_CHANNEL" not in sql
        assert "DELIVERED_AT" not in sql
        assert "DELIVERY_METADATA" not in sql
        assert "RETRY_COUNT" not in sql
        assert "ERROR_MESSAGE" not in sql


# ===========================================================================
# 7. NotificationDispatcher — delivery tracking integration
# ===========================================================================


TEST_USER_ID = str(uuid4())


def _insert_result() -> MagicMock:
    result = MagicMock()
    result.rowcount = 1
    return result


def _update_result() -> MagicMock:
    result = MagicMock()
    result.rowcount = 1
    return result


@pytest.fixture
def mock_db_for_dispatcher():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_insert_result())
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_push_service():
    svc = AsyncMock()
    svc.is_configured = True
    svc.send_push = AsyncMock(return_value=True)
    return svc


@pytest.fixture
def mock_email_service():
    svc = AsyncMock()
    svc.send = AsyncMock(return_value=True)
    return svc


@pytest.fixture
def mock_notification_service():
    svc = AsyncMock()
    svc.create = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def dispatcher_with_tracking(
    mock_db_for_dispatcher,
    mock_notification_service,
    mock_push_service,
    mock_email_service,
):
    from services.notification_dispatcher import NotificationDispatcher
    return NotificationDispatcher(
        db=mock_db_for_dispatcher,
        notification_service=mock_notification_service,
        push_service=mock_push_service,
        email_service=mock_email_service,
    )


class TestDispatcherDeliveryTracking:
    """Verify that NotificationDispatcher persists delivery tracking correctly."""

    @pytest.mark.asyncio
    async def test_in_app_insert_includes_delivery_channel(
        self, dispatcher_with_tracking, mock_db_for_dispatcher
    ):
        """The IN_APP INSERT should set delivery_channel='in_app' and delivery_status='sent'."""
        from services.notification_dispatcher import NotificationChannel

        await dispatcher_with_tracking.send(
            user_id=TEST_USER_ID,
            type="info",
            title="In-app tracking test",
            channels=[NotificationChannel.IN_APP],
        )

        # The INSERT call should have been executed
        mock_db_for_dispatcher.execute.assert_awaited()
        insert_call = mock_db_for_dispatcher.execute.call_args_list[0]
        sql = str(insert_call.args[0]).lower()
        assert "insert" in sql
        assert "delivery_channel" in sql
        assert "delivery_status" in sql

    @pytest.mark.asyncio
    async def test_notification_id_returned_for_in_app_channel(
        self, dispatcher_with_tracking
    ):
        """send() should return a non-None notification_id when IN_APP is included."""
        from services.notification_dispatcher import NotificationChannel

        result = await dispatcher_with_tracking.send(
            user_id=TEST_USER_ID,
            type="info",
            title="ID test",
            channels=[NotificationChannel.IN_APP],
        )

        assert result["notification_id"] is not None

    @pytest.mark.asyncio
    async def test_notification_id_none_without_in_app_channel(
        self, dispatcher_with_tracking
    ):
        """send() should return notification_id=None when IN_APP is not in channels."""
        from services.notification_dispatcher import NotificationChannel

        result = await dispatcher_with_tracking.send(
            user_id=TEST_USER_ID,
            type="info",
            title="No in-app",
            channels=[NotificationChannel.EMAIL],
            email_to="user@example.com",
        )

        assert result["notification_id"] is None

    @pytest.mark.asyncio
    async def test_push_failure_records_error_on_in_app_row(
        self, dispatcher_with_tracking, mock_db_for_dispatcher, mock_push_service
    ):
        """When push fails and IN_APP is included, the failure is persisted via UPDATE."""
        from services.notification_dispatcher import NotificationChannel

        mock_push_service.send_push.return_value = False
        # Execute calls: 1 INSERT (in-app) + 1 UPDATE (push failure tracking)
        mock_db_for_dispatcher.execute.return_value = _update_result()

        result = await dispatcher_with_tracking.send(
            user_id=TEST_USER_ID,
            type="info",
            title="Push fail tracking",
            channels=[NotificationChannel.IN_APP, NotificationChannel.PUSH],
        )

        assert result["channels"]["push"] is False
        # Two execute calls expected: INSERT then UPDATE
        assert mock_db_for_dispatcher.execute.await_count == 2
        update_call_sql = str(
            mock_db_for_dispatcher.execute.call_args_list[1].args[0]
        ).upper()
        assert "UPDATE" in update_call_sql

    @pytest.mark.asyncio
    async def test_push_success_records_sent_on_in_app_row(
        self, dispatcher_with_tracking, mock_db_for_dispatcher, mock_push_service
    ):
        """When push succeeds and IN_APP is included, the outcome is persisted."""
        from services.notification_dispatcher import NotificationChannel

        mock_push_service.send_push.return_value = True
        mock_db_for_dispatcher.execute.return_value = _update_result()

        result = await dispatcher_with_tracking.send(
            user_id=TEST_USER_ID,
            type="info",
            title="Push success tracking",
            channels=[NotificationChannel.IN_APP, NotificationChannel.PUSH],
        )

        assert result["channels"]["push"] is True
        # INSERT + UPDATE
        assert mock_db_for_dispatcher.execute.await_count == 2
        update_params = mock_db_for_dispatcher.execute.call_args_list[1].args[1]
        assert update_params["delivery_status"] == "sent"

    @pytest.mark.asyncio
    async def test_email_failure_records_error_message_on_in_app_row(
        self, dispatcher_with_tracking, mock_db_for_dispatcher, mock_email_service
    ):
        """Email failure error_message should be persisted to the in-app row."""
        from services.notification_dispatcher import NotificationChannel

        mock_email_service.send.side_effect = Exception("SMTP auth failed")
        mock_db_for_dispatcher.execute.return_value = _update_result()

        result = await dispatcher_with_tracking.send(
            user_id=TEST_USER_ID,
            type="info",
            title="Email fail error message",
            channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
            email_to="user@example.com",
        )

        assert result["channels"]["email"] is False
        # INSERT + UPDATE
        assert mock_db_for_dispatcher.execute.await_count == 2
        update_params = mock_db_for_dispatcher.execute.call_args_list[1].args[1]
        assert update_params["delivery_status"] == "failed"
        assert "SMTP auth failed" in update_params["error_message"]

    @pytest.mark.asyncio
    async def test_dedup_skip_returns_none_notification_id(
        self, dispatcher_with_tracking, mock_db_for_dispatcher
    ):
        """A dedup skip must return notification_id=None (no row was created)."""
        from services.notification_dispatcher import NotificationChannel

        # First execute call: dedup SELECT returns a match
        dup_result = MagicMock()
        dup_result.first.return_value = MagicMock()
        mock_db_for_dispatcher.execute.return_value = dup_result

        result = await dispatcher_with_tracking.send(
            user_id=TEST_USER_ID,
            type="info",
            title="Dedup test",
            channels=[NotificationChannel.IN_APP],
            dedup_key="test_dedup_key",
            cooldown_seconds=3600,
        )

        assert result["skipped_dedup"] is True
        assert result["notification_id"] is None
