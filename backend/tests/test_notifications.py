"""
Tests for Notifications API and NotificationService.

Coverage:
  - GET /notifications — list unread (authenticated, unauthenticated)
  - GET /notifications/count — unread count
  - PUT /notifications/{id}/read — mark read (success, not-found, wrong user)
  - NotificationService unit tests (create, get_unread, get_unread_count, mark_read)
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

TEST_USER_ID = "cccccccc-0000-0000-0000-000000000001"
BASE = "/api/v1/notifications"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _session_data(user_id: str = TEST_USER_ID):
    from auth.neon_auth import SessionData

    return SessionData(
        user_id=user_id,
        email=f"{user_id[:8]}@example.com",
        name="Notif User",
        email_verified=True,
        role="user",
    )


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


def _scalar_result(value) -> MagicMock:
    result = MagicMock()
    result.scalar.return_value = value
    result.fetchall.return_value = []
    result.rowcount = 0
    return result


def _rows_result(rows: list) -> MagicMock:
    """Mock execute() result that returns a list of tuples via fetchall()."""
    result = MagicMock()
    result.fetchall.return_value = rows
    result.scalar.return_value = None
    result.rowcount = 0
    return result


# ---------------------------------------------------------------------------
# TestClient fixture — function-scoped to avoid rate-limiter accumulation
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    from main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_overrides():
    from main import app, _app_rate_limiter

    _app_rate_limiter.reset()
    yield
    for dep in list(app.dependency_overrides.keys()):
        app.dependency_overrides.pop(dep, None)
    _app_rate_limiter.reset()


def _install_auth(db: AsyncMock = None, user_id: str = TEST_USER_ID):
    from main import app
    from api.dependencies import get_current_user, get_db_session

    session = _session_data(user_id=user_id)
    if db is None:
        db = _mock_db()
    app.dependency_overrides[get_current_user] = lambda: session
    app.dependency_overrides[get_db_session] = lambda: db
    return db


# ===========================================================================
# 1. GET /notifications
# ===========================================================================


class TestGetNotifications:
    """List unread notifications endpoint."""

    def test_returns_empty_list_when_no_notifications(self, client):
        db = _mock_db()
        db.execute.return_value = _rows_result([])
        _install_auth(db)

        resp = client.get(BASE)
        assert resp.status_code == 200
        data = resp.json()
        assert data["notifications"] == []
        assert data["total"] == 0

    def test_returns_notifications(self, client):
        notif_id = str(uuid4())
        # Row: (id, type, title, body, created_at)
        row = (notif_id, "info", "Price alert", "Your price is high", "2026-01-01T00:00:00+00:00")
        db = _mock_db()
        db.execute.return_value = _rows_result([row])
        _install_auth(db)

        resp = client.get(BASE)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        n = data["notifications"][0]
        assert n["id"] == notif_id
        assert n["type"] == "info"
        assert n["title"] == "Price alert"
        assert n["body"] == "Your price is high"

    def test_requires_authentication(self, client):
        resp = client.get(BASE)
        assert resp.status_code in (401, 503)


# ===========================================================================
# 2. GET /notifications/count
# ===========================================================================


class TestGetNotificationCount:
    """Unread count endpoint."""

    def test_returns_zero_when_none(self, client):
        db = _mock_db()
        db.execute.return_value = _scalar_result(0)
        _install_auth(db)

        resp = client.get(f"{BASE}/count")
        assert resp.status_code == 200
        assert resp.json()["unread"] == 0

    def test_returns_correct_count(self, client):
        db = _mock_db()
        db.execute.return_value = _scalar_result(7)
        _install_auth(db)

        resp = client.get(f"{BASE}/count")
        assert resp.status_code == 200
        assert resp.json()["unread"] == 7

    def test_requires_authentication(self, client):
        resp = client.get(f"{BASE}/count")
        assert resp.status_code in (401, 503)


# ===========================================================================
# 3. PUT /notifications/{id}/read
# ===========================================================================


class TestMarkNotificationRead:
    """Mark notification read endpoint."""

    def test_marks_read_successfully(self, client):
        notif_id = str(uuid4())
        db = _mock_db()
        result = MagicMock()
        result.rowcount = 1
        db.execute.return_value = result
        _install_auth(db)

        resp = client.put(f"{BASE}/{notif_id}/read")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_returns_404_when_not_found(self, client):
        notif_id = str(uuid4())
        db = _mock_db()
        result = MagicMock()
        result.rowcount = 0
        db.execute.return_value = result
        _install_auth(db)

        resp = client.put(f"{BASE}/{notif_id}/read")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_requires_authentication(self, client):
        resp = client.put(f"{BASE}/{str(uuid4())}/read")
        assert resp.status_code in (401, 503)

    def test_wrong_user_cannot_mark_read(self, client):
        """Row owned by a different user should return rowcount=0 → 404."""
        notif_id = str(uuid4())
        db = _mock_db()
        result = MagicMock()
        result.rowcount = 0  # DB WHERE clause filters by user_id, so no match
        db.execute.return_value = result
        _install_auth(db, user_id="other-user-0000-0000-0000-000000000002")

        resp = client.put(f"{BASE}/{notif_id}/read")
        assert resp.status_code == 404


# ===========================================================================
# 4. NotificationService unit tests
# ===========================================================================


class TestNotificationService:
    """Direct unit tests for NotificationService methods."""

    @pytest.mark.asyncio
    async def test_create_executes_insert_and_commits(self):
        from services.notification_service import NotificationService

        db = _mock_db()
        db.execute.return_value = MagicMock()
        svc = NotificationService(db)

        await svc.create(
            user_id=TEST_USER_ID,
            title="Test notif",
            body="Some body",
            type="warning",
        )

        db.execute.assert_awaited_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_default_type_is_info(self):
        from services.notification_service import NotificationService

        db = _mock_db()
        db.execute.return_value = MagicMock()
        svc = NotificationService(db)

        await svc.create(user_id=TEST_USER_ID, title="Hello")
        # Inspect the params passed to execute
        call_args = db.execute.call_args
        params = call_args[0][1] if call_args[0] else call_args.args[1]
        assert params["type"] == "info"

    @pytest.mark.asyncio
    async def test_get_unread_returns_mapped_list(self):
        from services.notification_service import NotificationService

        nid = str(uuid4())
        row = (nid, "info", "Title", "Body", "2026-01-01T00:00:00+00:00")
        db = _mock_db()
        db.execute.return_value = _rows_result([row])
        svc = NotificationService(db)

        result = await svc.get_unread(TEST_USER_ID)

        assert len(result) == 1
        assert result[0]["id"] == nid
        assert result[0]["type"] == "info"
        assert result[0]["title"] == "Title"
        assert result[0]["body"] == "Body"

    @pytest.mark.asyncio
    async def test_get_unread_empty(self):
        from services.notification_service import NotificationService

        db = _mock_db()
        db.execute.return_value = _rows_result([])
        svc = NotificationService(db)

        result = await svc.get_unread(TEST_USER_ID)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_unread_count_returns_integer(self):
        from services.notification_service import NotificationService

        db = _mock_db()
        db.execute.return_value = _scalar_result(5)
        svc = NotificationService(db)

        count = await svc.get_unread_count(TEST_USER_ID)
        assert count == 5

    @pytest.mark.asyncio
    async def test_get_unread_count_none_returns_zero(self):
        from services.notification_service import NotificationService

        db = _mock_db()
        db.execute.return_value = _scalar_result(None)
        svc = NotificationService(db)

        count = await svc.get_unread_count(TEST_USER_ID)
        assert count == 0

    @pytest.mark.asyncio
    async def test_mark_read_returns_true_on_match(self):
        from services.notification_service import NotificationService

        db = _mock_db()
        result = MagicMock()
        result.rowcount = 1
        db.execute.return_value = result
        svc = NotificationService(db)

        ok = await svc.mark_read(TEST_USER_ID, str(uuid4()))
        assert ok is True
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mark_read_returns_false_on_no_match(self):
        from services.notification_service import NotificationService

        db = _mock_db()
        result = MagicMock()
        result.rowcount = 0
        db.execute.return_value = result
        svc = NotificationService(db)

        ok = await svc.mark_read(TEST_USER_ID, str(uuid4()))
        assert ok is False
