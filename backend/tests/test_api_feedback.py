"""Tests for the Feedback API (backend/api/v1/feedback.py).

Covers:
- POST /feedback  (valid bug/feature/general; message length bounds;
                   invalid type; missing fields; auth-wall)
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session

_USER_ID = str(uuid.uuid4())
_TEST_USER = SessionData(user_id=_USER_ID, email="feedback@example.com")

_BASE = "/api/v1/feedback"


def _db_with_feedback_row(fb_type: str = "bug") -> AsyncMock:
    """Return a DB mock that emits a feedback INSERT result row."""
    row = MagicMock()
    row.id = uuid.uuid4()
    row.type = fb_type
    row.status = "new"
    row.created_at = datetime.now(UTC)

    result = MagicMock()
    result.fetchone.return_value = row

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


@pytest.fixture
def auth_client():
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db_session] = lambda: _db_with_feedback_row()
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
# POST /feedback
# ---------------------------------------------------------------------------


class TestCreateFeedback:
    def test_submits_bug_report_returns_201(self, auth_client):
        resp = auth_client.post(
            _BASE, json={"type": "bug", "message": "Something is broken on the dashboard"}
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["type"] == "bug"
        assert body["status"] == "new"
        assert "id" in body
        assert "created_at" in body

    def test_submits_feature_request_returns_201(self):
        from main import app

        app.dependency_overrides[get_current_user] = lambda: _TEST_USER
        app.dependency_overrides[get_db_session] = lambda: _db_with_feedback_row("feature")
        with TestClient(app) as c:
            resp = c.post(
                _BASE,
                json={"type": "feature", "message": "Please add CSV export for savings history"},
            )
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db_session, None)
        assert resp.status_code == 201
        assert resp.json()["type"] == "feature"

    def test_submits_general_feedback_returns_201(self):
        from main import app

        app.dependency_overrides[get_current_user] = lambda: _TEST_USER
        app.dependency_overrides[get_db_session] = lambda: _db_with_feedback_row("general")
        with TestClient(app) as c:
            resp = c.post(
                _BASE, json={"type": "general", "message": "Love the rate comparison feature!"}
            )
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db_session, None)
        assert resp.status_code == 201

    def test_message_too_short_returns_422(self, auth_client):
        resp = auth_client.post(_BASE, json={"type": "bug", "message": "short"})
        assert resp.status_code == 422

    def test_message_exact_min_length_10_accepted(self, auth_client):
        resp = auth_client.post(_BASE, json={"type": "general", "message": "1234567890"})
        assert resp.status_code == 201

    def test_message_at_max_length_5000_accepted(self, auth_client):
        resp = auth_client.post(_BASE, json={"type": "bug", "message": "x" * 5000})
        assert resp.status_code == 201

    def test_message_over_max_length_returns_422(self, auth_client):
        resp = auth_client.post(_BASE, json={"type": "bug", "message": "x" * 5001})
        assert resp.status_code == 422

    def test_invalid_type_returns_422(self, auth_client):
        resp = auth_client.post(
            _BASE, json={"type": "complaint", "message": "This is a complaint message"}
        )
        assert resp.status_code == 422

    def test_missing_type_returns_422(self, auth_client):
        resp = auth_client.post(_BASE, json={"message": "This has no type field"})
        assert resp.status_code == 422

    def test_missing_message_returns_422(self, auth_client):
        resp = auth_client.post(_BASE, json={"type": "bug"})
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.post(
            _BASE, json={"type": "bug", "message": "Unauthenticated bug report"}
        )
        assert resp.status_code in (401, 403)
