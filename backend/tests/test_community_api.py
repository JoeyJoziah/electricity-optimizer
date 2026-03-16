"""
Tests for Community API routes (backend/api/v1/community.py)

Covers:
- POST /community/posts — create (auth, validation, rate limit)
- GET  /community/posts — list with filters and pagination
- POST /community/posts/{id}/vote — toggle upvote (auth)
- POST /community/posts/{id}/report — flag post (auth)
- PUT  /community/posts/{id} — edit/resubmit flagged post (auth)
- GET  /community/stats — public aggregate stats

All tests use function-scoped TestClient to prevent rate-limiter state
accumulation across tests.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_db_session, SessionData

# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

TEST_USER_ID = "aaaaaaaa-0000-0000-0000-000000000001"
OTHER_USER_ID = "bbbbbbbb-0000-0000-0000-000000000002"


# ---------------------------------------------------------------------------
# In-memory mock DB for community tables
# ---------------------------------------------------------------------------


class _MockCommunityDB:
    """
    In-memory DB session that routes text() SQL to community operations.

    Tables simulated:
      - community_posts
      - community_votes
      - community_reports
    """

    def __init__(self):
        self._posts: list[dict] = []
        self._votes: list[dict] = []
        self._reports: list[dict] = []
        self.commit = AsyncMock()

    async def execute(self, stmt, params=None):
        sql = self._sql(stmt)
        params = params or {}
        return self._dispatch(sql, params)

    @staticmethod
    def _sql(stmt) -> str:
        return str(stmt.text if hasattr(stmt, "text") else stmt).strip().upper()

    def _dispatch(self, sql: str, params: dict) -> MagicMock:
        # --- Rate limit check (has CREATED_AT + user_id) ---
        if "COMMUNITY_POSTS" in sql and "COUNT(*)" in sql and "CREATED_AT" in sql and "USER_ID" in sql:
            return self._rate_count(params)

        # --- INSERT post ---
        if "INSERT INTO COMMUNITY_POSTS" in sql:
            return self._insert_post(params)

        # --- CTE: toggle_vote (INSERT + DELETE + COUNT on community_votes) ---
        if "INSERT INTO COMMUNITY_VOTES" in sql and "DELETE FROM COMMUNITY_VOTES" in sql:
            return self._toggle_vote(params)

        # --- CTE: report_post (INSERT community_reports + UPDATE community_posts) ---
        if "INSERT INTO COMMUNITY_REPORTS" in sql and "UPDATE COMMUNITY_POSTS" in sql:
            return self._report_cte(params)

        # --- UPDATE post (moderation / edit / hide) ---
        if "UPDATE COMMUNITY_POSTS" in sql:
            return self._update_post(sql, params)

        # --- SELECT post (moderate / edit) ---
        if "FROM COMMUNITY_POSTS" in sql and "WHERE" in sql and "ID" in sql and "LIMIT" not in sql:
            return self._select_post(params)

        # --- List posts (with window function COUNT(*) OVER()) ---
        if "FROM COMMUNITY_POSTS" in sql and "LIMIT" in sql:
            return self._list_posts(params)

        # --- INSERT vote (standalone, no CTE) ---
        if "INSERT INTO COMMUNITY_VOTES" in sql:
            return self._insert_vote(params)

        # --- DELETE vote (standalone) ---
        if "DELETE FROM COMMUNITY_VOTES" in sql:
            return self._delete_vote(params)

        # --- SELECT vote (check existence) ---
        if "FROM COMMUNITY_VOTES" in sql and "COUNT" not in sql:
            return self._check_vote(params)

        # --- COUNT votes ---
        if "FROM COMMUNITY_VOTES" in sql and "COUNT" in sql:
            return self._count_votes(params)

        # --- INSERT report (standalone) ---
        if "INSERT INTO COMMUNITY_REPORTS" in sql:
            return self._insert_report(params)

        # --- COUNT reports ---
        if "FROM COMMUNITY_REPORTS" in sql and "COUNT" in sql:
            return self._count_reports(params)

        # --- Stats ---
        if "COMMUNITY_POSTS" in sql and "COUNT(DISTINCT" in sql:
            return self._stats(params)

        return self._empty_result()

    # --- Post operations ---

    def _rate_count(self, params: dict) -> MagicMock:
        uid = params.get("user_id", "")
        count = sum(1 for p in self._posts if str(p["user_id"]) == str(uid))
        result = MagicMock()
        result.scalar.return_value = min(count, 10)  # cap at limit
        return result

    def _list_count(self, params: dict) -> MagicMock:
        region = params.get("region", "")
        utype = params.get("utility_type", "")
        count = sum(
            1 for p in self._posts
            if not p["is_hidden"]
            and not p["is_pending_moderation"]
            and str(p["region"]) == str(region)
            and str(p["utility_type"]) == str(utype)
        )
        result = MagicMock()
        result.scalar.return_value = count
        return result

    def _insert_post(self, params: dict) -> MagicMock:
        now = datetime.now(tz=timezone.utc)
        post = {
            "id": params.get("id", str(uuid4())),
            "user_id": params.get("user_id"),
            "region": params.get("region", "us_ct"),
            "utility_type": params.get("utility_type", "electricity"),
            "post_type": params.get("post_type", "tip"),
            "title": params.get("title", ""),
            "body": params.get("body", ""),
            "rate_per_unit": params.get("rate_per_unit"),
            "rate_unit": params.get("rate_unit"),
            "supplier_name": params.get("supplier_name"),
            "is_hidden": False,
            "is_pending_moderation": True,
            "hidden_reason": None,
            "created_at": now,
            "updated_at": now,
        }
        self._posts.append(post)
        result = MagicMock()
        result.mappings.return_value.fetchone.return_value = post
        return result

    def _update_post(self, sql: str, params: dict) -> MagicMock:
        pid = params.get("post_id") or params.get("id")
        post = next((p for p in self._posts if str(p["id"]) == str(pid)), None)
        if post:
            for key in ("is_hidden", "is_pending_moderation", "hidden_reason",
                        "title", "body", "supplier_name"):
                if key in params:
                    post[key] = params[key]
        return MagicMock()

    def _select_post(self, params: dict) -> MagicMock:
        pid = params.get("post_id") or params.get("id")
        post = next((p for p in self._posts if str(p["id"]) == str(pid)), None)
        result = MagicMock()
        result.mappings.return_value.fetchone.return_value = post
        return result

    def _list_posts(self, params: dict) -> MagicMock:
        region = params.get("region", "")
        utype = params.get("utility_type", "")
        visible = [
            p for p in self._posts
            if not p["is_hidden"]
            and not p["is_pending_moderation"]
            and str(p["region"]) == str(region)
            and str(p["utility_type"]) == str(utype)
        ]
        limit = params.get("limit", 20)
        offset = params.get("offset", 0)
        page = visible[offset:offset + limit]
        total = len(visible)
        # Add derived counts + window function total
        for p in page:
            p["upvote_count"] = sum(
                1 for v in self._votes if str(v["post_id"]) == str(p["id"])
            )
            p["report_count"] = sum(
                1 for r in self._reports if str(r["post_id"]) == str(p["id"])
            )
            p["_total_count"] = total
        result = MagicMock()
        result.mappings.return_value.fetchall.return_value = page
        return result

    # --- Vote operations ---

    def _check_vote(self, params: dict) -> MagicMock:
        uid = params.get("user_id", "")
        pid = params.get("post_id", "")
        match = [
            v for v in self._votes
            if str(v["user_id"]) == str(uid) and str(v["post_id"]) == str(pid)
        ]
        result = MagicMock()
        result.mappings.return_value.fetchone.return_value = match[0] if match else None
        return result

    def _insert_vote(self, params: dict) -> MagicMock:
        self._votes.append({
            "user_id": params.get("user_id"),
            "post_id": params.get("post_id"),
            "created_at": datetime.now(tz=timezone.utc),
        })
        return MagicMock()

    def _delete_vote(self, params: dict) -> MagicMock:
        uid = params.get("user_id", "")
        pid = params.get("post_id", "")
        self._votes = [
            v for v in self._votes
            if not (str(v["user_id"]) == str(uid) and str(v["post_id"]) == str(pid))
        ]
        result = MagicMock()
        result.rowcount = 1
        return result

    def _toggle_vote(self, params: dict) -> MagicMock:
        """Atomic toggle_vote CTE: insert or delete, return action + count."""
        uid = params.get("user_id", "")
        pid = params.get("post_id", "")
        match = [
            v for v in self._votes
            if str(v["user_id"]) == str(uid) and str(v["post_id"]) == str(pid)
        ]
        if match:
            # Vote exists → delete it
            self._votes = [
                v for v in self._votes
                if not (str(v["user_id"]) == str(uid) and str(v["post_id"]) == str(pid))
            ]
            action = "deleted"
        else:
            # Vote doesn't exist → insert it
            self._votes.append({
                "user_id": uid,
                "post_id": pid,
                "created_at": datetime.now(tz=timezone.utc),
            })
            action = "inserted"
        count = sum(1 for v in self._votes if str(v["post_id"]) == str(pid))
        result = MagicMock()
        result.mappings.return_value.fetchone.return_value = {
            "action": action,
            "upvote_count": count,
        }
        return result

    def _count_votes(self, params: dict) -> MagicMock:
        pid = params.get("post_id", "")
        count = sum(1 for v in self._votes if str(v["post_id"]) == str(pid))
        result = MagicMock()
        result.scalar.return_value = count
        return result

    # --- Report operations ---

    def _report_cte(self, params: dict) -> MagicMock:
        """CTE report: insert + count + conditional hide."""
        uid = params.get("user_id", "")
        pid = params.get("post_id", "")
        threshold = params.get("threshold", 5)
        # Deduplicate insert
        exists = any(
            str(r["user_id"]) == str(uid) and str(r["post_id"]) == str(pid)
            for r in self._reports
        )
        if not exists:
            self._reports.append({
                "user_id": uid,
                "post_id": pid,
                "reason": params.get("reason"),
                "created_at": datetime.now(tz=timezone.utc),
            })
        # Count + conditional hide
        count = sum(1 for r in self._reports if str(r["post_id"]) == str(pid))
        if count >= threshold:
            post = next((p for p in self._posts if str(p["id"]) == str(pid)), None)
            if post and not post["is_hidden"]:
                post["is_hidden"] = True
                post["hidden_reason"] = "reported_by_users"
        return MagicMock()

    def _insert_report(self, params: dict) -> MagicMock:
        uid = params.get("user_id", "")
        pid = params.get("post_id", "")
        # Deduplicate
        exists = any(
            str(r["user_id"]) == str(uid) and str(r["post_id"]) == str(pid)
            for r in self._reports
        )
        if not exists:
            self._reports.append({
                "user_id": uid,
                "post_id": pid,
                "reason": params.get("reason"),
                "created_at": datetime.now(tz=timezone.utc),
            })
        return MagicMock()

    def _count_reports(self, params: dict) -> MagicMock:
        pid = params.get("post_id", "")
        count = sum(1 for r in self._reports if str(r["post_id"]) == str(pid))
        result = MagicMock()
        result.scalar.return_value = count
        return result

    # --- Stats ---

    def _stats(self, params: dict) -> MagicMock:
        region = params.get("region", "")
        posts = [p for p in self._posts if str(p["region"]) == str(region)]
        users = set(p["user_id"] for p in posts)
        result = MagicMock()
        result.mappings.return_value.fetchone.return_value = {
            "total_users": len(users),
            "total_posts": len(posts),
            "avg_savings_pct": 12.5 if posts else 0,
            "top_tip_title": posts[0]["title"] if posts else None,
            "top_tip_user_id": posts[0]["user_id"] if posts else None,
        }
        return result

    # --- Helpers ---

    @staticmethod
    def _empty_result() -> MagicMock:
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        result.scalar.return_value = 0
        result.mappings.return_value.fetchone.return_value = None
        result.mappings.return_value.fetchall.return_value = []
        return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    return _MockCommunityDB()


@pytest.fixture
def auth_client(mock_db):
    """TestClient with authenticated user."""
    from main import app

    test_user = SessionData(user_id=TEST_USER_ID, email="test@example.com")
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db_session] = lambda: mock_db

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def unauth_client(mock_db):
    """TestClient without authentication but with mock DB."""
    from main import app

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_db_session] = lambda: mock_db

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_db_session, None)


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------

VALID_POST = {
    "title": "Great tip for saving",
    "body": "Switch to off-peak usage to reduce your bill.",
    "utility_type": "electricity",
    "region": "us_ct",
    "post_type": "tip",
}


# =============================================================================
# POST /community/posts
# =============================================================================


class TestCreatePost:
    def test_create_post_authenticated(self, auth_client):
        """201 with valid payload when authenticated."""
        resp = auth_client.post("/api/v1/community/posts", json=VALID_POST)
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["is_pending_moderation"] is True

    def test_create_post_unauthenticated(self, unauth_client):
        """401 when not authenticated."""
        resp = unauth_client.post("/api/v1/community/posts", json=VALID_POST)
        assert resp.status_code in (401, 403)

    def test_create_post_invalid_type(self, auth_client):
        """422 when post_type is invalid."""
        bad = {**VALID_POST, "post_type": "invalid_type"}
        resp = auth_client.post("/api/v1/community/posts", json=bad)
        assert resp.status_code == 422

    def test_create_post_missing_title(self, auth_client):
        """422 when title is missing."""
        bad = {k: v for k, v in VALID_POST.items() if k != "title"}
        resp = auth_client.post("/api/v1/community/posts", json=bad)
        assert resp.status_code == 422


# =============================================================================
# GET /community/posts
# =============================================================================


class TestListPosts:
    def test_list_posts_with_filters(self, auth_client, mock_db):
        """200 with region + utility_type query params."""
        # Seed a visible post
        mock_db._posts.append({
            "id": str(uuid4()),
            "user_id": TEST_USER_ID,
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "tip",
            "title": "Visible post",
            "body": "Body text",
            "rate_per_unit": None,
            "rate_unit": None,
            "supplier_name": None,
            "is_hidden": False,
            "is_pending_moderation": False,
            "hidden_reason": None,
            "created_at": datetime.now(tz=timezone.utc),
            "updated_at": datetime.now(tz=timezone.utc),
        })

        resp = auth_client.get(
            "/api/v1/community/posts",
            params={"region": "us_ct", "utility_type": "electricity"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "posts" in data
        assert len(data["posts"]) >= 1

    def test_list_posts_pagination(self, auth_client):
        """Page=2 returns empty when no posts."""
        resp = auth_client.get(
            "/api/v1/community/posts",
            params={"region": "us_ct", "utility_type": "electricity", "page": 2},
        )
        assert resp.status_code == 200
        assert resp.json()["posts"] == []


# =============================================================================
# POST /community/posts/{id}/vote
# =============================================================================


class TestVote:
    def test_vote_toggle(self, auth_client, mock_db):
        """200, toggles vote on a post."""
        post_id = str(uuid4())
        mock_db._posts.append({
            "id": post_id,
            "user_id": OTHER_USER_ID,
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "tip",
            "title": "Votable",
            "body": "Body",
            "rate_per_unit": None,
            "rate_unit": None,
            "supplier_name": None,
            "is_hidden": False,
            "is_pending_moderation": False,
            "hidden_reason": None,
            "created_at": datetime.now(tz=timezone.utc),
            "updated_at": datetime.now(tz=timezone.utc),
        })

        resp = auth_client.post(f"/api/v1/community/posts/{post_id}/vote")
        assert resp.status_code == 200

    def test_vote_unauthenticated(self, unauth_client):
        """401 when not authenticated."""
        post_id = str(uuid4())
        resp = unauth_client.post(f"/api/v1/community/posts/{post_id}/vote")
        assert resp.status_code in (401, 403)


# =============================================================================
# POST /community/posts/{id}/report
# =============================================================================


class TestReport:
    def test_report_post(self, auth_client, mock_db):
        """200, inserts report."""
        post_id = str(uuid4())
        mock_db._posts.append({
            "id": post_id,
            "user_id": OTHER_USER_ID,
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "discussion",
            "title": "Reportable",
            "body": "Body",
            "rate_per_unit": None,
            "rate_unit": None,
            "supplier_name": None,
            "is_hidden": False,
            "is_pending_moderation": False,
            "hidden_reason": None,
            "created_at": datetime.now(tz=timezone.utc),
            "updated_at": datetime.now(tz=timezone.utc),
        })

        resp = auth_client.post(
            f"/api/v1/community/posts/{post_id}/report",
            json={"reason": "spam"},
        )
        assert resp.status_code == 200

    def test_report_post_duplicate(self, auth_client, mock_db):
        """200 idempotent — same user reporting twice doesn't error."""
        post_id = str(uuid4())
        mock_db._posts.append({
            "id": post_id,
            "user_id": OTHER_USER_ID,
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "discussion",
            "title": "Report twice",
            "body": "Body",
            "rate_per_unit": None,
            "rate_unit": None,
            "supplier_name": None,
            "is_hidden": False,
            "is_pending_moderation": False,
            "hidden_reason": None,
            "created_at": datetime.now(tz=timezone.utc),
            "updated_at": datetime.now(tz=timezone.utc),
        })

        auth_client.post(f"/api/v1/community/posts/{post_id}/report", json={"reason": "spam"})
        resp = auth_client.post(f"/api/v1/community/posts/{post_id}/report", json={"reason": "spam"})
        assert resp.status_code == 200


# =============================================================================
# PUT /community/posts/{id}
# =============================================================================


class TestEditResubmit:
    def test_edit_resubmit_flagged_post(self, auth_client, mock_db):
        """200, author can edit flagged post."""
        post_id = str(uuid4())
        mock_db._posts.append({
            "id": post_id,
            "user_id": TEST_USER_ID,
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "tip",
            "title": "Flagged",
            "body": "Bad content",
            "rate_per_unit": None,
            "rate_unit": None,
            "supplier_name": None,
            "is_hidden": True,
            "is_pending_moderation": False,
            "hidden_reason": "flagged",
            "created_at": datetime.now(tz=timezone.utc),
            "updated_at": datetime.now(tz=timezone.utc),
        })

        resp = auth_client.put(
            f"/api/v1/community/posts/{post_id}",
            json={"title": "Fixed title", "body": "Fixed content"},
        )
        assert resp.status_code == 200


# =============================================================================
# GET /community/stats
# =============================================================================


class TestCommunityStats:
    def test_community_stats(self, auth_client, mock_db):
        """200 with aggregated data."""
        mock_db._posts.append({
            "id": str(uuid4()),
            "user_id": TEST_USER_ID,
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "tip",
            "title": "Top tip",
            "body": "Body",
            "rate_per_unit": None,
            "rate_unit": None,
            "supplier_name": None,
            "is_hidden": False,
            "is_pending_moderation": False,
            "hidden_reason": None,
            "created_at": datetime.now(tz=timezone.utc),
            "updated_at": datetime.now(tz=timezone.utc),
        })

        resp = auth_client.get("/api/v1/community/stats", params={"region": "us_ct"})
        assert resp.status_code == 200
        data = resp.json()
        assert "total_users" in data or "stats" in data
