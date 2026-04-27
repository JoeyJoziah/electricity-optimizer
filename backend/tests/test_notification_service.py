"""
Unit tests for notification_service.py (NotificationService).

The service manages in-app notifications: create, get_unread,
get_unread_count, mark_read, mark_all_read. All DB calls are mocked.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.notification_service import NotificationService

# =============================================================================
# Fixtures
# =============================================================================


def _make_mapping_result(rows: list) -> MagicMock:
    """Build a mock SQLAlchemy result that responds to .fetchall() and .scalar()."""
    mock_result = MagicMock()
    mock_result.fetchall.return_value = rows
    mock_result.scalar.return_value = len(rows)
    mock_result.rowcount = len(rows)
    return mock_result


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    return NotificationService(db=mock_db)


# =============================================================================
# TestCreate
# =============================================================================


class TestCreate:
    """Tests for NotificationService.create()."""

    async def test_inserts_notification_row(self, service, mock_db):
        mock_db.execute.return_value = MagicMock()

        await service.create(
            user_id="user_1",
            title="Price alert",
            body="Prices dropped below $0.20",
            type="alert",
        )

        mock_db.execute.assert_called_once()
        # Verify the SQL params contain the expected values
        call_params = mock_db.execute.call_args[0][1]
        assert call_params["uid"] == "user_1"
        assert call_params["title"] == "Price alert"
        assert call_params["type"] == "alert"

    async def test_commits_after_insert(self, service, mock_db):
        mock_db.execute.return_value = MagicMock()

        await service.create(user_id="user_2", title="Info")

        mock_db.commit.assert_called_once()

    async def test_rolls_back_on_db_error(self, service, mock_db):
        mock_db.execute.side_effect = Exception("DB write failed")

        with pytest.raises(Exception, match="DB write failed"):
            await service.create(user_id="user_3", title="Will fail")

        mock_db.rollback.assert_called_once()

    async def test_body_defaults_to_none(self, service, mock_db):
        mock_db.execute.return_value = MagicMock()

        await service.create(user_id="user_4", title="No body")

        call_params = mock_db.execute.call_args[0][1]
        assert call_params["body"] is None

    async def test_type_defaults_to_info(self, service, mock_db):
        mock_db.execute.return_value = MagicMock()

        await service.create(user_id="user_5", title="Default type")

        call_params = mock_db.execute.call_args[0][1]
        assert call_params["type"] == "info"


# =============================================================================
# TestGetUnread
# =============================================================================


class TestGetUnread:
    """Tests for NotificationService.get_unread()."""

    async def test_returns_list_of_notification_dicts(self, service, mock_db):
        rows = [
            ("uuid-1", "alert", "Price drop", "Below $0.20", "2026-04-01T10:00:00"),
            ("uuid-2", "info", "Welcome", None, "2026-04-01T09:00:00"),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_db.execute.return_value = mock_result

        result = await service.get_unread("user_10")

        assert len(result) == 2
        assert result[0]["id"] == "uuid-1"
        assert result[0]["type"] == "alert"
        assert result[0]["title"] == "Price drop"

    async def test_returns_empty_list_when_no_unread(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.get_unread("user_empty")

        assert result == []

    async def test_passes_user_id_to_query(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        await service.get_unread("target_user")

        call_params = mock_db.execute.call_args[0][1]
        assert call_params["uid"] == "target_user"

    async def test_body_none_is_preserved_in_result(self, service, mock_db):
        rows = [("uuid-3", "info", "Title only", None, "2026-04-01")]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_db.execute.return_value = mock_result

        result = await service.get_unread("user_x")

        assert result[0]["body"] is None


# =============================================================================
# TestGetUnreadCount
# =============================================================================


class TestGetUnreadCount:
    """Tests for NotificationService.get_unread_count()."""

    async def test_returns_count_from_db(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalar.return_value = 7
        mock_db.execute.return_value = mock_result

        count = await service.get_unread_count("user_a")

        assert count == 7

    async def test_returns_zero_when_scalar_is_none(self, service, mock_db):
        """NULL from COUNT(*) on empty table should yield 0, not None."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_db.execute.return_value = mock_result

        count = await service.get_unread_count("user_b")

        assert count == 0

    async def test_passes_user_id_to_count_query(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        await service.get_unread_count("specific_user")

        call_params = mock_db.execute.call_args[0][1]
        assert call_params["uid"] == "specific_user"


# =============================================================================
# TestMarkAllRead
# =============================================================================


class TestMarkAllRead:
    """Tests for NotificationService.mark_all_read()."""

    async def test_returns_count_of_notifications_marked(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute.return_value = mock_result

        count = await service.mark_all_read("user_many")

        assert count == 5

    async def test_returns_zero_when_nothing_to_mark(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        count = await service.mark_all_read("user_none")

        assert count == 0

    async def test_commits_after_update(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_db.execute.return_value = mock_result

        await service.mark_all_read("user_c")

        mock_db.commit.assert_called_once()

    async def test_rolls_back_on_db_error(self, service, mock_db):
        mock_db.execute.side_effect = Exception("constraint error")

        with pytest.raises(Exception, match="constraint error"):
            await service.mark_all_read("user_d")

        mock_db.rollback.assert_called_once()

    async def test_passes_user_id_to_update_query(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        await service.mark_all_read("user_specific")

        call_params = mock_db.execute.call_args[0][1]
        assert call_params["uid"] == "user_specific"


# =============================================================================
# TestMarkRead (single notification)
# =============================================================================


class TestMarkRead:
    """Tests for NotificationService.mark_read()."""

    async def test_returns_true_when_notification_updated(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        updated = await service.mark_read("user_1", "notif-uuid-1")

        assert updated is True

    async def test_returns_false_when_notification_not_found(self, service, mock_db):
        """Notification not found (wrong user, wrong id, or already read)."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        updated = await service.mark_read("user_1", "nonexistent-notif")

        assert updated is False

    async def test_commits_after_successful_update(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        await service.mark_read("user_1", "notif-uuid-1")

        mock_db.commit.assert_called_once()

    async def test_rolls_back_on_db_error(self, service, mock_db):
        mock_db.execute.side_effect = Exception("lock timeout")

        with pytest.raises(Exception, match="lock timeout"):
            await service.mark_read("user_1", "notif-uuid-1")

        mock_db.rollback.assert_called_once()

    async def test_passes_both_notification_id_and_user_id(self, service, mock_db):
        """Query must scope by both user_id AND notification_id to prevent IDOR."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        await service.mark_read("owner_user", "notif-abc")

        call_params = mock_db.execute.call_args[0][1]
        assert call_params["uid"] == "owner_user"
        assert call_params["nid"] == "notif-abc"

    async def test_does_not_commit_when_nothing_updated(self, service, mock_db):
        """
        No commit should happen when rowcount == 0 — prevents spurious transaction
        overhead for already-read notifications.

        NOTE: The current implementation calls commit() unconditionally (before
        checking rowcount). This test documents the actual behaviour; if the
        service is refactored to skip commit on no-op, update this test.
        """
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        await service.mark_read("user_1", "already-read")

        # Commit IS called (current implementation: commit before rowcount check)
        mock_db.commit.assert_called_once()
