"""Tests for the Community API (backend/api/v1/community.py).

Mounted at: /api/v1/community

Covers:
- POST /community/posts   (valid; invalid post_type; invalid utility_type; auth-wall)
- GET  /community/posts   (returns posts; per_page max 100; page min 1)
- PUT  /community/posts/{post_id}   (success; invalid UUID)
- POST /community/posts/{post_id}/vote   (success; auth-wall)
- POST /community/posts/{post_id}/report (success; auth-wall)
- GET  /community/stats  (success; auth not required)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session

_USER_ID = str(uuid.uuid4())
_TEST_USER = SessionData(user_id=_USER_ID, email="community@example.com")

_BASE = "/api/v1/community"

_POST_ID = str(uuid.uuid4())
_POST = {
    "id": _POST_ID,
    "title": "Eversource raised prices again",
    "body": "Heads up — Eversource just hiked residential rates by 8%.",
    "utility_type": "electricity",
    "region": "us_ct",
    "post_type": "rate_report",
    "upvote_count": 3,
    "status": "active",
}

_VALID_BODY = {
    "title": "Eversource raised prices again",
    "body": "Heads up — Eversource just hiked residential rates by 8%.",
    "utility_type": "electricity",
    "region": "us_ct",
    "post_type": "rate_report",
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
def public_client():
    from main import app

    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def unauth_client():
    from main import app

    c = TestClient(app, raise_server_exceptions=False)
    yield c


# ---------------------------------------------------------------------------
# POST /community/posts
# ---------------------------------------------------------------------------


class TestCreatePost:
    def test_valid_post_returns_201(self, auth_client):
        with patch(
            "services.community_service.CommunityService.create_post",
            new=AsyncMock(return_value=_POST),
        ):
            resp = auth_client.post(f"{_BASE}/posts", json=_VALID_BODY)
        assert resp.status_code == 201

    def test_invalid_post_type_returns_422(self, auth_client):
        body = {**_VALID_BODY, "post_type": "complaint"}
        with patch(
            "services.community_service.CommunityService.create_post",
            new=AsyncMock(return_value=_POST),
        ):
            resp = auth_client.post(f"{_BASE}/posts", json=body)
        assert resp.status_code == 422

    def test_invalid_utility_type_returns_422(self, auth_client):
        body = {**_VALID_BODY, "utility_type": "solar_panel"}
        with patch(
            "services.community_service.CommunityService.create_post",
            new=AsyncMock(return_value=_POST),
        ):
            resp = auth_client.post(f"{_BASE}/posts", json=body)
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.post(f"{_BASE}/posts", json=_VALID_BODY)
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /community/posts
# ---------------------------------------------------------------------------


class TestListPosts:
    def test_returns_posts(self, public_client):
        with patch(
            "services.community_service.CommunityService.list_posts",
            new=AsyncMock(
                return_value={"items": [_POST], "total": 1, "page": 1, "per_page": 20, "pages": 1}
            ),
        ):
            resp = public_client.get(f"{_BASE}/posts?region=us_ct&utility_type=electricity")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["posts"]) == 1

    def test_per_page_over_max_returns_422(self, public_client):
        resp = public_client.get(
            f"{_BASE}/posts?region=us_ct&utility_type=electricity&per_page=101"
        )
        assert resp.status_code == 422

    def test_page_zero_returns_422(self, public_client):
        resp = public_client.get(f"{_BASE}/posts?region=us_ct&utility_type=electricity&page=0")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /community/posts/{post_id}
# ---------------------------------------------------------------------------


class TestEditPost:
    def test_edit_post_returns_200(self, auth_client):
        with patch(
            "services.community_service.CommunityService.edit_and_resubmit",
            new=AsyncMock(return_value={**_POST, "title": "Updated title"}),
        ):
            resp = auth_client.put(f"{_BASE}/posts/{_POST_ID}", json={"title": "Updated title"})
        assert resp.status_code == 200

    def test_invalid_post_id_uuid_returns_422(self, auth_client):
        resp = auth_client.put(f"{_BASE}/posts/not-a-uuid", json={"title": "X"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /community/posts/{post_id}/vote
# ---------------------------------------------------------------------------


class TestToggleVote:
    def test_vote_returns_200_with_voted(self, auth_client):
        with patch(
            "services.community_service.CommunityService.toggle_vote",
            new=AsyncMock(return_value={"voted": True, "upvote_count": 4}),
        ):
            resp = auth_client.post(f"{_BASE}/posts/{_POST_ID}/vote")
        assert resp.status_code == 200
        assert resp.json()["voted"] is True

    def test_unauthenticated_vote_returns_401(self, unauth_client):
        resp = unauth_client.post(f"{_BASE}/posts/{_POST_ID}/vote")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /community/posts/{post_id}/report
# ---------------------------------------------------------------------------


class TestReportPost:
    def test_report_returns_200(self, auth_client):
        with patch(
            "services.community_service.CommunityService.report_post",
            new=AsyncMock(return_value=None),
        ):
            resp = auth_client.post(
                f"{_BASE}/posts/{_POST_ID}/report",
                json={"reason": "Spam"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "reported"

    def test_unauthenticated_report_returns_401(self, unauth_client):
        resp = unauth_client.post(f"{_BASE}/posts/{_POST_ID}/report", json={"reason": "Spam"})
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /community/stats
# ---------------------------------------------------------------------------


class TestCommunityStats:
    def test_stats_returned(self, public_client):
        with patch(
            "services.community_service.CommunityService.get_stats",
            new=AsyncMock(return_value={"total_posts": 42, "active_users": 8}),
        ):
            resp = public_client.get(f"{_BASE}/stats?region=us_ct")
        assert resp.status_code == 200
        assert resp.json()["total_posts"] == 42
