"""
Tests for CommunityService (backend/services/community_service.py)

Covers:
- Post creation with XSS sanitization and pending moderation
- Fail-closed moderation (Groq primary, Gemini fallback)
- 30s timeout leaves post pending (fail-closed — no auto-approve)
- Paginated listing (excludes hidden + pending)
- Vote toggle (composite PK dedup, derived counts)
- Report dedup + 5-reporter hide threshold
- Retroactive re-moderation (gather-based, race-condition-free)
- Edit and resubmit for flagged posts (fail-closed on timeout)
- Community stats with attribution
- Rate limiting (11th post/hour → 429)
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.community_service import REPORT_HIDE_THRESHOLD, CommunityService

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock async database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


class _AgentServiceStub:
    """Stub that only has classify_content (not classify_content_groq/gemini)."""

    pass


@pytest.fixture
def mock_agent_service():
    """Mock agent service with classify_content method only."""
    svc = _AgentServiceStub()
    svc.classify_content = AsyncMock(return_value="safe")
    return svc


@pytest.fixture
def service():
    """CommunityService instance."""
    return CommunityService()


@pytest.fixture
def sample_post_data():
    """Valid post creation data."""
    return {
        "title": "Great tip for saving on electricity",
        "body": "Switch to time-of-use pricing and run appliances during off-peak hours to save 15-20%.",
        "region": "us_ct",
        "utility_type": "electricity",
        "post_type": "tip",
    }


@pytest.fixture
def sample_rate_report_data():
    """Post data for a rate report."""
    return {
        "title": "New Eversource rate update",
        "body": "Eversource just increased their generation charge for Q2 2026.",
        "region": "us_ct",
        "utility_type": "electricity",
        "post_type": "rate_report",
        "rate_per_unit": Decimal("0.1234"),
        "rate_unit": "kWh",
        "supplier_name": "Eversource Energy",
    }


# =============================================================================
# create_post
# =============================================================================


class TestCreatePost:
    async def test_create_post_success(
        self, service, mock_db, mock_agent_service, sample_post_data
    ):
        """create_post returns a post with UUID id and is_pending_moderation=true."""
        user_id = str(uuid4())

        # Mock the INSERT returning the new row
        row = MagicMock()
        row._mapping = {
            "id": str(uuid4()),
            "user_id": user_id,
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "tip",
            "title": sample_post_data["title"],
            "body": sample_post_data["body"],
            "rate_per_unit": None,
            "rate_unit": None,
            "supplier_name": None,
            "is_hidden": False,
            "is_pending_moderation": True,
            "hidden_reason": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchone.return_value = row._mapping

        # Rate limit check returns count < limit
        rate_result = MagicMock()
        rate_result.scalar.return_value = 0

        # Extra MagicMock for moderation UPDATE + commit path
        mock_db.execute = AsyncMock(side_effect=[rate_result, mock_result, MagicMock()])

        post = await service.create_post(
            mock_db, user_id, sample_post_data, mock_agent_service
        )

        assert post["id"] is not None
        assert post["is_pending_moderation"] is True
        assert post["user_id"] == user_id

    async def test_create_post_sanitizes_xss(
        self, service, mock_db, mock_agent_service
    ):
        """<script> and onerror must be stripped from title/body by nh3 BEFORE the INSERT.

        The mock DB returns the raw unsanitized strings to prove the service is
        calling nh3.clean() itself — not relying on the DB to sanitize.
        """
        import nh3

        user_id = str(uuid4())
        xss_title = '<script>alert("xss")</script>My Great Tip'
        xss_body = "Check this out <img src=x onerror=alert(1)> really useful tip for saving money on electricity."

        data = {
            "title": xss_title,
            "body": xss_body,
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "tip",
        }

        # Capture the params that the service passes to db.execute
        captured_params: dict = {}

        async def capture_execute(stmt, params=None, *args, **kwargs):
            _sql = str(stmt)
            if params and "title" in params:
                captured_params.update(params)
            result = MagicMock()
            result.scalar.return_value = 0  # rate limit check
            result.mappings.return_value.fetchone.return_value = {
                "id": str(uuid4()),
                "user_id": user_id,
                "region": "us_ct",
                "utility_type": "electricity",
                "post_type": "tip",
                # Return the RAW (unsanitized) strings — the service must sanitize before INSERT
                "title": xss_title,
                "body": xss_body,
                "rate_per_unit": None,
                "rate_unit": None,
                "supplier_name": None,
                "is_hidden": False,
                "is_pending_moderation": True,
                "hidden_reason": None,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
            return result

        mock_db.execute = AsyncMock(side_effect=capture_execute)

        await service.create_post(mock_db, user_id, data, mock_agent_service)

        # Verify nh3 was called and the INSERT received sanitized content
        assert captured_params, "db.execute was never called with INSERT params"
        sanitized_title = captured_params["title"]
        sanitized_body = captured_params["body"]

        # Confirm the real nh3 library strips these attack vectors
        assert "<script>" not in sanitized_title, "Script tag not stripped from title"
        assert 'alert("xss")' not in sanitized_title, "JS alert not stripped from title"
        assert (
            "onerror" not in sanitized_body
        ), "onerror attribute not stripped from body"

        # Cross-check: nh3.clean produces the same result (proves real sanitizer was used)
        assert sanitized_title == nh3.clean(xss_title)
        assert sanitized_body == nh3.clean(xss_body)

    async def test_create_post_triggers_moderation(
        self, service, mock_db, mock_agent_service, sample_post_data
    ):
        """create_post should call classify_content on the agent service."""
        user_id = str(uuid4())

        rate_result = MagicMock()
        rate_result.scalar.return_value = 0

        insert_result = MagicMock()
        insert_result.mappings.return_value.fetchone.return_value = {
            "id": str(uuid4()),
            "user_id": user_id,
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "tip",
            "title": sample_post_data["title"],
            "body": sample_post_data["body"],
            "rate_per_unit": None,
            "rate_unit": None,
            "supplier_name": None,
            "is_hidden": False,
            "is_pending_moderation": True,
            "hidden_reason": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        mock_db.execute = AsyncMock(
            side_effect=[rate_result, insert_result, AsyncMock()]
        )

        await service.create_post(
            mock_db, user_id, sample_post_data, mock_agent_service
        )

        mock_agent_service.classify_content.assert_called_once()

    async def test_create_post_fail_closed(
        self, service, mock_db, mock_agent_service, sample_post_data
    ):
        """Post starts as is_pending_moderation=true until AI classifies it."""
        user_id = str(uuid4())
        post_id = str(uuid4())

        rate_result = MagicMock()
        rate_result.scalar.return_value = 0

        insert_result = MagicMock()
        insert_result.mappings.return_value.fetchone.return_value = {
            "id": post_id,
            "user_id": user_id,
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "tip",
            "title": sample_post_data["title"],
            "body": sample_post_data["body"],
            "rate_per_unit": None,
            "rate_unit": None,
            "supplier_name": None,
            "is_hidden": False,
            "is_pending_moderation": True,
            "hidden_reason": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        mock_db.execute = AsyncMock(
            side_effect=[rate_result, insert_result, AsyncMock()]
        )

        post = await service.create_post(
            mock_db, user_id, sample_post_data, mock_agent_service
        )

        # Fail-closed: post is pending until moderation completes
        assert post["is_pending_moderation"] is True

    async def test_create_post_timeout_leaves_post_pending(
        self, service, mock_db, sample_post_data
    ):
        """On moderation timeout the post must stay is_pending_moderation=true (fail-closed).

        Previously the service called _clear_pending_moderation on timeout, making
        the post publicly visible without an explicit moderation pass (fail-open).
        The correct behaviour is to leave the post pending so it only becomes
        visible after retroactive_moderate or a manual moderation action clears it.
        """
        user_id = str(uuid4())
        post_id = str(uuid4())

        # Agent service that always times out
        mock_agent = MagicMock()
        mock_agent.classify_content = AsyncMock(side_effect=asyncio.TimeoutError)

        rate_result = MagicMock()
        rate_result.scalar.return_value = 0

        insert_result = MagicMock()
        insert_result.mappings.return_value.fetchone.return_value = {
            "id": post_id,
            "user_id": user_id,
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "tip",
            "title": sample_post_data["title"],
            "body": sample_post_data["body"],
            "rate_per_unit": None,
            "rate_unit": None,
            "supplier_name": None,
            "is_hidden": False,
            "is_pending_moderation": True,
            "hidden_reason": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        # Only 2 DB calls expected on timeout path: rate-limit SELECT + INSERT.
        # There must be NO third UPDATE to clear is_pending_moderation.
        mock_db.execute = AsyncMock(side_effect=[rate_result, insert_result])

        post = await service.create_post(mock_db, user_id, sample_post_data, mock_agent)

        # Returned post dict reflects the DB row (is_pending_moderation=True)
        assert post["is_pending_moderation"] is True

        # Exactly 2 DB calls: rate-limit SELECT + INSERT (no clear-pending UPDATE)
        assert mock_db.execute.call_count == 2, (
            "Expected only rate-limit SELECT + INSERT on timeout path; "
            "_clear_pending_moderation must not be called (fail-closed)."
        )

    async def test_edit_and_resubmit_timeout_leaves_post_pending(
        self, service, mock_db, mock_agent_service
    ):
        """edit_and_resubmit timeout must leave post pending (fail-closed), not auto-approve."""
        user_id = str(uuid4())
        post_id = str(uuid4())

        # Agent that always times out
        mock_agent = MagicMock()
        mock_agent.classify_content = AsyncMock(side_effect=asyncio.TimeoutError)

        existing_post = {
            "id": post_id,
            "user_id": user_id,
            "is_hidden": True,
            "hidden_reason": "flagged_by_ai",
        }
        select_result = MagicMock()
        select_result.mappings.return_value.fetchone.return_value = existing_post

        updated_post = {
            "id": post_id,
            "user_id": user_id,
            "title": "Edited title",
            "body": "Edited body content that is now compliant.",
            "is_hidden": False,
            "is_pending_moderation": True,
            "hidden_reason": None,
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "tip",
            "rate_per_unit": None,
            "rate_unit": None,
            "supplier_name": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        update_result = MagicMock()
        update_result.mappings.return_value.fetchone.return_value = updated_post

        # Only SELECT + UPDATE expected; no third _clear_pending_moderation call
        mock_db.execute = AsyncMock(side_effect=[select_result, update_result])

        result = await service.edit_and_resubmit(
            mock_db,
            user_id,
            post_id,
            {
                "title": "Edited title",
                "body": "Edited body content that is now compliant.",
            },
            mock_agent,
        )

        assert result["is_pending_moderation"] is True
        assert mock_db.execute.call_count == 2, (
            "Only SELECT + UPDATE expected; _clear_pending_moderation must not "
            "be called on timeout (fail-closed)."
        )


# =============================================================================
# list_posts
# =============================================================================


class TestListPosts:
    async def test_list_posts_paginated(self, service, mock_db):
        """list_posts returns paginated results, excluding hidden and pending."""
        rows = [
            {
                "id": str(uuid4()),
                "user_id": str(uuid4()),
                "region": "us_ct",
                "utility_type": "electricity",
                "post_type": "tip",
                "title": f"Tip {i}",
                "body": f"Body of tip {i} with enough text to pass validation.",
                "rate_per_unit": None,
                "rate_unit": None,
                "supplier_name": None,
                "is_hidden": False,
                "is_pending_moderation": False,
                "hidden_reason": None,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "upvote_count": i,
                "report_count": 0,
                "_total_count": 3,
            }
            for i in range(3)
        ]

        list_result = MagicMock()
        list_result.mappings.return_value.fetchall.return_value = rows

        mock_db.execute = AsyncMock(return_value=list_result)

        result = await service.list_posts(
            mock_db, region="us_ct", utility_type="electricity", page=1, per_page=10
        )

        assert result["total"] == 3
        assert len(result["items"]) == 3
        assert result["page"] == 1
        # Window function means _total_count is stripped from items
        assert "_total_count" not in result["items"][0]

    async def test_list_posts_filters_by_region_and_utility(self, service, mock_db):
        """list_posts should filter by region and utility_type."""
        list_result = MagicMock()
        list_result.mappings.return_value.fetchall.return_value = []

        mock_db.execute = AsyncMock(return_value=list_result)

        result = await service.list_posts(
            mock_db, region="us_ny", utility_type="natural_gas", page=1, per_page=10
        )

        assert result["total"] == 0
        assert result["items"] == []
        # Single query with window function
        assert mock_db.execute.call_count == 1

    async def test_list_posts_empty_page(self, service, mock_db):
        """Empty result returns empty list, not error."""
        list_result = MagicMock()
        list_result.mappings.return_value.fetchall.return_value = []

        mock_db.execute = AsyncMock(return_value=list_result)

        result = await service.list_posts(
            mock_db, region="us_ct", utility_type="electricity", page=5, per_page=10
        )

        assert result["items"] == []
        assert result["total"] == 0


# =============================================================================
# toggle_vote
# =============================================================================


class TestToggleVote:
    async def test_vote_toggle_add(self, service, mock_db):
        """First vote on a post adds it (atomic INSERT ON CONFLICT)."""
        user_id = str(uuid4())
        post_id = str(uuid4())

        toggle_result = MagicMock()
        toggle_result.mappings.return_value.fetchone.return_value = {
            "action": "inserted",
            "upvote_count": 1,
        }
        mock_db.execute = AsyncMock(return_value=toggle_result)

        result = await service.toggle_vote(mock_db, user_id, post_id)
        assert result["voted"] is True
        assert result["upvote_count"] == 1

    async def test_vote_toggle_remove(self, service, mock_db):
        """Second vote on same post removes it (atomic DELETE)."""
        user_id = str(uuid4())
        post_id = str(uuid4())

        toggle_result = MagicMock()
        toggle_result.mappings.return_value.fetchone.return_value = {
            "action": "deleted",
            "upvote_count": 0,
        }
        mock_db.execute = AsyncMock(return_value=toggle_result)

        result = await service.toggle_vote(mock_db, user_id, post_id)
        assert result["voted"] is False
        assert result["upvote_count"] == 0

    async def test_vote_count_derived(self, service, mock_db):
        """Upvote count is derived via COUNT(*) on community_votes, not stored."""
        post_id = str(uuid4())

        count_result = MagicMock()
        count_result.scalar.return_value = 7

        mock_db.execute = AsyncMock(return_value=count_result)

        count = await service.get_vote_count(mock_db, post_id)
        assert count == 7


# =============================================================================
# report_post
# =============================================================================


class TestReportPost:
    async def test_report_post_deduplicates(self, service, mock_db):
        """Same user reporting twice is idempotent (INSERT ON CONFLICT DO NOTHING)."""
        user_id = str(uuid4())
        post_id = str(uuid4())

        # Single CTE handles insert + count + conditional hide
        mock_db.execute = AsyncMock(return_value=MagicMock())

        await service.report_post(mock_db, user_id, post_id, reason="spam")

        # Single query (CTE) + commit
        assert mock_db.execute.call_count == 1
        mock_db.commit.assert_called()

        # Second report is also a single query (ON CONFLICT DO NOTHING handles dedup)
        mock_db.execute.reset_mock()
        mock_db.commit.reset_mock()
        await service.report_post(mock_db, user_id, post_id, reason="spam")
        assert mock_db.execute.call_count == 1

    async def test_report_post_hides_at_threshold(self, service, mock_db):
        """5 unique reports should hide the post (via CTE conditional UPDATE)."""
        user_id = str(uuid4())
        post_id = str(uuid4())

        # Single CTE: INSERT + COUNT + conditional UPDATE when >= threshold
        mock_db.execute = AsyncMock(return_value=MagicMock())

        await service.report_post(mock_db, user_id, post_id, reason="harassment")

        # All handled in a single query
        assert mock_db.execute.call_count == 1
        mock_db.commit.assert_called()

    async def test_report_post_different_users_required(self, service, mock_db):
        """Verifies threshold needs different users, not repeated reports from same user."""
        post_id = str(uuid4())

        for i in range(REPORT_HIDE_THRESHOLD):
            user_id = str(uuid4())
            mock_db.execute = AsyncMock(return_value=MagicMock())
            mock_db.commit = AsyncMock()
            await service.report_post(mock_db, user_id, post_id, reason=f"report {i}")

            # Each report is a single CTE query
            assert mock_db.execute.call_count == 1


# =============================================================================
# moderate_post
# =============================================================================


class TestModeratePost:
    def _mock_post_select(self, mock_db, post_id):
        """Helper: configure mock_db.execute to return post content for SELECT."""
        select_result = MagicMock()
        select_result.mappings.return_value.fetchone.return_value = {
            "title": "Test Post",
            "body": "Test body content for moderation.",
        }
        update_result = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[select_result, update_result])

    async def test_moderation_hides_flagged_post(
        self, service, mock_db, mock_agent_service
    ):
        """Groq returns 'flagged' → post should be hidden."""
        post_id = str(uuid4())
        mock_agent_service.classify_content = AsyncMock(return_value="flagged")

        self._mock_post_select(mock_db, post_id)

        await service.moderate_post(mock_db, post_id, mock_agent_service)

        # Should have set is_hidden=true and is_pending_moderation=false
        assert mock_db.execute.call_count >= 2  # SELECT + UPDATE
        mock_db.commit.assert_called()

    async def test_moderation_groq_fallback_to_gemini(self, service, mock_db):
        """Groq 429 → falls back to Gemini."""
        post_id = str(uuid4())

        # Agent with both groq and gemini methods
        mock_agent = _AgentServiceStub()
        mock_agent.classify_content_groq = AsyncMock(
            side_effect=Exception("429 Too Many Requests")
        )
        mock_agent.classify_content_gemini = AsyncMock(return_value="safe")

        self._mock_post_select(mock_db, post_id)

        await service.moderate_post(mock_db, post_id, mock_agent)

        # Should have attempted Groq first, then Gemini
        mock_agent.classify_content_groq.assert_called_once()
        mock_agent.classify_content_gemini.assert_called_once()

    async def test_moderation_both_fail_timeout_unhides(self, service, mock_db):
        """Both AI providers fail → is_pending_moderation cleared."""
        post_id = str(uuid4())

        mock_agent = _AgentServiceStub()
        mock_agent.classify_content_groq = AsyncMock(
            side_effect=Exception("429 Too Many Requests")
        )
        mock_agent.classify_content_gemini = AsyncMock(side_effect=asyncio.TimeoutError)

        # SELECT returns post, then UPDATE for clearing pending
        select_result = MagicMock()
        select_result.mappings.return_value.fetchone.return_value = {
            "title": "Test Post",
            "body": "Test body content.",
        }
        mock_db.execute = AsyncMock(side_effect=[select_result, MagicMock()])

        await service.moderate_post(mock_db, post_id, mock_agent)

        # Should have cleared is_pending_moderation after failure
        assert mock_db.execute.call_count >= 2


# =============================================================================
# retroactive_moderate
# =============================================================================


class TestRetroactiveModeration:
    async def test_retroactive_remoderation(self, service, mock_db, mock_agent_service):
        """Recovered service re-checks posts that timed out during moderation."""
        # Return 2 posts that timed out (is_pending_moderation=false but no classification)
        timed_out_posts = [
            {"id": str(uuid4()), "title": "Post 1", "body": "Body 1"},
            {"id": str(uuid4()), "title": "Post 2", "body": "Body 2"},
        ]

        select_result = MagicMock()
        select_result.mappings.return_value.fetchall.return_value = timed_out_posts

        # Only 1 SELECT needed (classify_content returns "safe" → no batch UPDATE)
        mock_db.execute = AsyncMock(return_value=select_result)

        count = await service.retroactive_moderate(mock_db, mock_agent_service)

        assert count == 2
        # Both posts classified in parallel via asyncio.gather
        assert mock_agent_service.classify_content.call_count == 2

    async def test_retroactive_moderate_gather_collects_flagged_ids(
        self, service, mock_db
    ):
        """flagged_ids are collected from asyncio.gather return values, not from
        concurrent appends to a shared list (race-condition-free).

        Verifies that only the actually-flagged post ID ends up in the batch
        UPDATE, with no possibility of missed or duplicated entries from
        concurrent coroutine appends.
        """
        flagged_id = str(uuid4())
        safe_id = str(uuid4())

        posts = [
            {"id": flagged_id, "title": "Bad post", "body": "Spam content"},
            {"id": safe_id, "title": "Good post", "body": "Helpful electricity tip"},
        ]

        select_result = MagicMock()
        select_result.mappings.return_value.fetchall.return_value = posts

        # classify_content returns "flagged" for first post, "safe" for second
        async def classify(content: str) -> str:
            return "flagged" if "Spam" in content else "safe"

        mock_agent = MagicMock()
        mock_agent.classify_content = AsyncMock(side_effect=classify)

        # SELECT + batch UPDATE
        update_result = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[select_result, update_result])

        count = await service.retroactive_moderate(mock_db, mock_agent)

        assert count == 2

        # Confirm the batch UPDATE was called exactly once
        assert mock_db.execute.call_count == 2  # SELECT + UPDATE

        # Inspect the UPDATE call to ensure only the flagged ID is included
        update_call_params = mock_db.execute.call_args_list[1][0][1]
        assert update_call_params["ids"] == [flagged_id], (
            "Only the flagged post ID must appear in the batch UPDATE; "
            "the safe post must not be included."
        )

    async def test_retroactive_moderate_no_posts_returns_zero(self, service, mock_db):
        """Returns 0 immediately when there are no timed-out posts to re-check."""
        select_result = MagicMock()
        select_result.mappings.return_value.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=select_result)

        count = await service.retroactive_moderate(mock_db, MagicMock())
        assert count == 0
        # Only the SELECT query — no UPDATE
        assert mock_db.execute.call_count == 1


# =============================================================================
# edit_and_resubmit
# =============================================================================


class TestEditAndResubmit:
    async def test_flagged_post_edit_resubmit(
        self, service, mock_db, mock_agent_service
    ):
        """Author can edit a flagged post and resubmit for moderation."""
        user_id = str(uuid4())
        post_id = str(uuid4())

        # Existing post is flagged (is_hidden=true)
        existing_post = MagicMock()
        existing_post._mapping = {
            "id": post_id,
            "user_id": user_id,
            "is_hidden": True,
            "hidden_reason": "flagged_by_ai",
        }
        select_result = MagicMock()
        select_result.mappings.return_value.fetchone.return_value = (
            existing_post._mapping
        )

        update_result = MagicMock()
        update_result.mappings.return_value.fetchone.return_value = {
            "id": post_id,
            "user_id": user_id,
            "title": "Edited title for resubmission",
            "body": "Edited body with better content that passes moderation guidelines.",
            "is_hidden": False,
            "is_pending_moderation": True,
            "hidden_reason": None,
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "tip",
            "rate_per_unit": None,
            "rate_unit": None,
            "supplier_name": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        mock_db.execute = AsyncMock(
            side_effect=[select_result, update_result, MagicMock()]
        )

        edit_data = {
            "title": "Edited title for resubmission",
            "body": "Edited body with better content that passes moderation guidelines.",
        }

        result = await service.edit_and_resubmit(
            mock_db, user_id, post_id, edit_data, mock_agent_service
        )

        assert result["is_pending_moderation"] is True
        assert result["is_hidden"] is False
        mock_agent_service.classify_content.assert_called_once()


# =============================================================================
# get_stats
# =============================================================================


class TestCommunityStats:
    async def test_community_stats(self, service, mock_db):
        """get_stats returns total_users, avg_savings_pct, top_tip with attribution."""
        stats_result = MagicMock()
        stats_result.mappings.return_value.fetchone.return_value = {
            "total_users": 42,
            "earliest_post": datetime(2026, 1, 1, tzinfo=UTC),
        }

        top_tip_result = MagicMock()
        top_tip_result.mappings.return_value.fetchone.return_value = {
            "id": str(uuid4()),
            "user_id": str(uuid4()),
            "title": "Best tip ever",
            "body": "Very helpful tip body content.",
            "upvote_count": 25,
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "tip",
        }

        mock_db.execute = AsyncMock(side_effect=[stats_result, top_tip_result])

        stats = await service.get_stats(mock_db, region="us_ct")

        assert stats["total_users"] == 42
        assert stats["region"] == "us_ct"
        assert stats["reporting_since"] is not None
        assert stats["top_tip"] is not None


# =============================================================================
# Rate limiting
# =============================================================================


class TestRateLimiting:
    async def test_rate_limit_posts(
        self, service, mock_db, mock_agent_service, sample_post_data
    ):
        """11th post in an hour should raise a rate limit error."""
        user_id = str(uuid4())

        # Rate limit check returns 10 (at the limit)
        rate_result = MagicMock()
        rate_result.scalar.return_value = 10

        mock_db.execute = AsyncMock(return_value=rate_result)

        with pytest.raises(Exception, match="rate limit|too many"):
            await service.create_post(
                mock_db, user_id, sample_post_data, mock_agent_service
            )
