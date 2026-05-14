"""Tests for the Notifications API (backend/api/v1/notifications.py).

Covers:
- GET  /notifications              (list unread; empty; auth-wall)
- GET  /notifications/count        (count; auth-wall)
- PUT  /notifications/read-all     (marks N items; auth-wall)
- PUT  /notifications/{id}/read    (found; not-found 404; invalid UUID 422)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session

_USER_ID = str(uuid.uuid4())
_TEST_USER = SessionData(user_id=_USER_ID, email="notify@example.com")

_NOTIF_ID = str(uuid.uuid4())
_NOTIF = {
    "id": _NOTIF_ID,
    "type": "rate_alert",
    "message": "Electricity rate dropped 5% in your area",
    "created_at": "2026-05-14T10:00:00",
}


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
# GET /notifications
# ---------------------------------------------------------------------------


class TestGetNotifications:
    def test_returns_notifications_list(self, auth_client):
        with patch(
            "services.notification_service.NotificationService.get_unread",
            new=AsyncMock(return_value=[_NOTIF]),
        ):
            resp = auth_client.get("/api/v1/notifications")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["notifications"][0]["type"] == "rate_alert"

    def test_passes_user_id_to_service(self, auth_client):
        with patch(
            "services.notification_service.NotificationService.get_unread",
            new=AsyncMock(return_value=[]),
        ) as mock_svc:
            resp = auth_client.get("/api/v1/notifications")
        assert resp.status_code == 200
        mock_svc.assert_awaited_once_with(_USER_ID)

    def test_empty_notifications_returns_200(self, auth_client):
        with patch(
            "services.notification_service.NotificationService.get_unread",
            new=AsyncMock(return_value=[]),
        ):
            resp = auth_client.get("/api/v1/notifications")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["notifications"] == []

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get("/api/v1/notifications")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /notifications/count
# ---------------------------------------------------------------------------


class TestGetNotificationCount:
    def test_returns_unread_count(self, auth_client):
        with patch(
            "services.notification_service.NotificationService.get_unread_count",
            new=AsyncMock(return_value=5),
        ):
            resp = auth_client.get("/api/v1/notifications/count")
        assert resp.status_code == 200
        assert resp.json()["unread"] == 5

    def test_zero_count_returns_200(self, auth_client):
        with patch(
            "services.notification_service.NotificationService.get_unread_count",
            new=AsyncMock(return_value=0),
        ):
            resp = auth_client.get("/api/v1/notifications/count")
        assert resp.status_code == 200
        assert resp.json()["unread"] == 0

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get("/api/v1/notifications/count")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# PUT /notifications/read-all
# ---------------------------------------------------------------------------


class TestMarkAllRead:
    def test_marks_all_read_and_returns_count(self, auth_client):
        with patch(
            "services.notification_service.NotificationService.mark_all_read",
            new=AsyncMock(return_value=3),
        ):
            resp = auth_client.put("/api/v1/notifications/read-all")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["marked"] == 3

    def test_zero_unread_returns_zero_marked(self, auth_client):
        with patch(
            "services.notification_service.NotificationService.mark_all_read",
            new=AsyncMock(return_value=0),
        ):
            resp = auth_client.put("/api/v1/notifications/read-all")
        assert resp.status_code == 200
        assert resp.json()["marked"] == 0

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.put("/api/v1/notifications/read-all")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# PUT /notifications/{id}/read
# ---------------------------------------------------------------------------


class TestMarkOneRead:
    def test_marks_single_notification_read(self, auth_client):
        with patch(
            "services.notification_service.NotificationService.mark_read",
            new=AsyncMock(return_value=True),
        ):
            resp = auth_client.put(f"/api/v1/notifications/{_NOTIF_ID}/read")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    def test_not_found_returns_404(self, auth_client):
        with patch(
            "services.notification_service.NotificationService.mark_read",
            new=AsyncMock(return_value=False),
        ):
            resp = auth_client.put(f"/api/v1/notifications/{_NOTIF_ID}/read")
        assert resp.status_code == 404

    def test_invalid_uuid_returns_422(self, auth_client):
        resp = auth_client.put("/api/v1/notifications/not-a-uuid/read")
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.put(f"/api/v1/notifications/{_NOTIF_ID}/read")
        assert resp.status_code in (401, 403)
