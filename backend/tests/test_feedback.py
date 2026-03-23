"""
Tests for the Feedback API (backend/api/v1/feedback.py)

Coverage
--------
- POST /api/v1/feedback  — authenticated create (201)
- POST /api/v1/feedback  — unauthenticated (401)
- POST /api/v1/feedback  — validation: message too short (422)
- POST /api/v1/feedback  — validation: invalid type (422)
- POST /api/v1/feedback  — database unavailable (503)
- All three feedback types (bug / feature / general)

All tests use function-scoped TestClient to prevent rate-limiter state
accumulation across tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session

# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

TEST_USER_ID = "cccccccc-1111-1111-1111-000000000001"

# ---------------------------------------------------------------------------
# Mock DB session — simulates feedback table INSERT ... RETURNING
# ---------------------------------------------------------------------------


class _MockFeedbackDB:
    """
    Minimal async DB session that handles the INSERT INTO feedback ... RETURNING
    query used by the feedback endpoint.
    """

    def __init__(self, fail: bool = False):
        self._fail = fail
        self.commit = AsyncMock()

    async def execute(self, stmt, params=None):
        if self._fail:
            raise RuntimeError("DB connection error")

        params = params or {}
        now = datetime.now(tz=UTC)
        row = MagicMock()
        row.id = str(uuid4())
        row.type = params.get("type", "general")
        row.status = "new"
        row.created_at = now

        result = MagicMock()
        result.fetchone.return_value = row
        return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def authed_session() -> SessionData:
    return SessionData(user_id=TEST_USER_ID, email="tester@example.com", role="user")


@pytest.fixture
def mock_db():
    return _MockFeedbackDB()


@pytest.fixture
def client(authed_session, mock_db):
    """TestClient with auth + DB overrides."""
    from main import app

    app.dependency_overrides[get_current_user] = lambda: authed_session
    app.dependency_overrides[get_db_session] = lambda: mock_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def unauthed_client(mock_db):
    """TestClient with no auth override (exercises 401 path)."""
    from main import app

    # Remove any lingering auth override
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_db_session] = lambda: mock_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def unavailable_db_client(authed_session):
    """TestClient where DB raises on execute (simulates DB unavailable)."""
    from main import app

    broken_db = None  # None triggers 503 in the endpoint

    app.dependency_overrides[get_current_user] = lambda: authed_session
    app.dependency_overrides[get_db_session] = lambda: broken_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


# ---------------------------------------------------------------------------
# POST /api/v1/feedback — authenticated create
# ---------------------------------------------------------------------------


class TestCreateFeedback:
    URL = "/api/v1/feedback"

    def test_create_general_feedback_returns_201(self, client):
        resp = client.post(
            self.URL,
            json={"type": "general", "message": "This is a general feedback message."},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["type"] == "general"
        assert body["status"] == "new"
        assert "id" in body
        assert "created_at" in body

    def test_create_bug_feedback_returns_201(self, client):
        resp = client.post(
            self.URL,
            json={"type": "bug", "message": "The dashboard chart does not render on mobile."},
        )
        assert resp.status_code == 201
        assert resp.json()["type"] == "bug"

    def test_create_feature_feedback_returns_201(self, client):
        resp = client.post(
            self.URL,
            json={"type": "feature", "message": "Please add CSV export for price history."},
        )
        assert resp.status_code == 201
        assert resp.json()["type"] == "feature"

    def test_response_contains_required_fields(self, client):
        resp = client.post(
            self.URL,
            json={"type": "general", "message": "Testing the response schema fields."},
        )
        body = resp.json()
        assert "id" in body
        assert "type" in body
        assert "status" in body
        assert "created_at" in body

    # -----------------------------------------------------------------------
    # Validation errors
    # -----------------------------------------------------------------------

    def test_message_too_short_returns_422(self, client):
        resp = client.post(
            self.URL,
            json={"type": "general", "message": "Too short"},  # < 10 chars
        )
        assert resp.status_code == 422

    def test_message_exactly_at_minimum_length_accepted(self, client):
        resp = client.post(
            self.URL,
            json={"type": "general", "message": "1234567890"},  # exactly 10 chars
        )
        assert resp.status_code == 201

    def test_invalid_type_returns_422(self, client):
        resp = client.post(
            self.URL,
            json={"type": "complaint", "message": "This type is not allowed."},
        )
        assert resp.status_code == 422

    def test_missing_message_returns_422(self, client):
        resp = client.post(self.URL, json={"type": "general"})
        assert resp.status_code == 422

    def test_missing_type_returns_422(self, client):
        resp = client.post(self.URL, json={"message": "Feedback without a type field."})
        assert resp.status_code == 422

    def test_empty_body_returns_422(self, client):
        resp = client.post(self.URL, json={})
        assert resp.status_code == 422

    # -----------------------------------------------------------------------
    # Authentication guard
    # -----------------------------------------------------------------------

    def test_unauthenticated_returns_401(self, unauthed_client):
        resp = unauthed_client.post(
            self.URL,
            json={"type": "general", "message": "This should be rejected."},
        )
        assert resp.status_code == 401

    # -----------------------------------------------------------------------
    # Database unavailable
    # -----------------------------------------------------------------------

    def test_db_unavailable_returns_503(self, unavailable_db_client):
        resp = unavailable_db_client.post(
            self.URL,
            json={"type": "general", "message": "Testing the DB unavailable path."},
        )
        assert resp.status_code == 503
