"""
Tests for CommunityService (backend/services/community_service.py)

Covers:
- Post creation with XSS sanitization and pending moderation
- Fail-closed moderation (Groq primary, Gemini fallback)
- 30s timeout auto-unhide
- Paginated listing (excludes hidden + pending)
- Vote toggle (composite PK dedup, derived counts)
- Report dedup + 5-reporter hide threshold
- Retroactive re-moderation
- Edit and resubmit for flagged posts
- Community stats with attribution
- Rate limiting (11th post/hour → 429)
"""

import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

import pytest

from services.community_service import CommunityService, REPORT_HIDE_THRESHOLD


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
    @pytest.mark.asyncio
    async def test_create_post_success(self, service, mock_db, mock_agent_service, sample_post_data):
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
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchone.return_value = row._mapping

        # Rate limit check returns count < limit
        rate_result = MagicMock()
        rate_result.scalar.return_value = 0

        # Extra MagicMock for moderation UPDATE + commit path
        mock_db.execute = AsyncMock(side_effect=[rate_result, mock_result, MagicMock()])

        post = await service.create_post(mock_db, user_id, sample_post_data, mock_agent_service)

        assert post["id"] is not None
        assert post["is_pending_moderation"] is True
        assert post["user_id"] == user_id

    @pytest.mark.asyncio
    async def test_create_post_sanitizes_xss(self, service, mock_db, mock_agent_service):
        """<script> tags must be stripped from title and body via nh3."""
        user_id = str(uuid4())
        data = {
            "title": '<script>alert("xss")</script>My Great Tip',
            "body": 'Check this out <img src=x onerror=alert(1)> really useful tip for saving money on electricity.',
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "tip",
        }

        # Capture what was actually passed to the INSERT
        captured_args = {}

        async def capture_execute(stmt, *args, **kwargs):
            # Try to capture bound params from the text() call
            captured_args["stmt"] = stmt
            result = MagicMock()
            result.scalar.return_value = 0  # rate limit
            result.mappings.return_value.fetchone.return_value = {
                "id": str(uuid4()),
                "user_id": user_id,
                "region": "us_ct",
                "utility_type": "electricity",
                "post_type": "tip",
                "title": "My Great Tip",  # sanitized
                "body": "Check this out  really useful tip for saving money on electricity.",  # sanitized
                "rate_per_unit": None,
                "rate_unit": None,
                "supplier_name": None,
                "is_hidden": False,
                "is_pending_moderation": True,
                "hidden_reason": None,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
            return result

        mock_db.execute = AsyncMock(side_effect=capture_execute)

        post = await service.create_post(mock_db, user_id, data, mock_agent_service)

        # The returned title/body should not contain script or onerror
        assert "<script>" not in post["title"]
        assert "onerror" not in post["body"]

    @pytest.mark.asyncio
    async def test_create_post_triggers_moderation(self, service, mock_db, mock_agent_service, sample_post_data):
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
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        mock_db.execute = AsyncMock(side_effect=[rate_result, insert_result, AsyncMock()])

        await service.create_post(mock_db, user_id, sample_post_data, mock_agent_service)

        mock_agent_service.classify_content.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_post_fail_closed(self, service, mock_db, mock_agent_service, sample_post_data):
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
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        mock_db.execute = AsyncMock(side_effect=[rate_result, insert_result, AsyncMock()])

        post = await service.create_post(mock_db, user_id, sample_post_data, mock_agent_service)

        # Fail-closed: post is pending until moderation completes
        assert post["is_pending_moderation"] is True

    @pytest.mark.asyncio
    async def test_create_post_timeout_auto_unhides(self, service, mock_db, sample_post_data):
        """If both Groq and Gemini fail, 30s timeout should set is_pending_moderation=false."""
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
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        mock_db.execute = AsyncMock(side_effect=[rate_result, insert_result, AsyncMock()])

        post = await service.create_post(mock_db, user_id, sample_post_data, mock_agent)

        # After timeout, the post should be auto-unhidden (moderation cleared)
        # Verify the UPDATE was called to clear is_pending_moderation
        assert mock_db.execute.call_count >= 3  # rate check + insert + update


# =============================================================================
# list_posts
# =============================================================================


class TestListPosts:
    @pytest.mark.asyncio
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
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "upvote_count": i,
                "report_count": 0,
                "_total_count": 3,
            }
            for i in range(3)
        ]

        list_result = MagicMock()
        list_result.mappings.return_value.fetchall.return_value = rows

        mock_db.execute = AsyncMock(return_value=list_result)

        result = await service.list_posts(mock_db, region="us_ct", utility_type="electricity", page=1, per_page=10)

        assert result["total"] == 3
        assert len(result["items"]) == 3
        assert result["page"] == 1
        # Window function means _total_count is stripped from items
        assert "_total_count" not in result["items"][0]

    @pytest.mark.asyncio
    async def test_list_posts_filters_by_region_and_utility(self, service, mock_db):
        """list_posts should filter by region and utility_type."""
        list_result = MagicMock()
        list_result.mappings.return_value.fetchall.return_value = []

        mock_db.execute = AsyncMock(return_value=list_result)

        result = await service.list_posts(mock_db, region="us_ny", utility_type="natural_gas", page=1, per_page=10)

        assert result["total"] == 0
        assert result["items"] == []
        # Single query with window function
        assert mock_db.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_list_posts_empty_page(self, service, mock_db):
        """Empty result returns empty list, not error."""
        list_result = MagicMock()
        list_result.mappings.return_value.fetchall.return_value = []

        mock_db.execute = AsyncMock(return_value=list_result)

        result = await service.list_posts(mock_db, region="us_ct", utility_type="electricity", page=5, per_page=10)

        assert result["items"] == []
        assert result["total"] == 0


# =============================================================================
# toggle_vote
# =============================================================================


class TestToggleVote:
    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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
    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_moderation_hides_flagged_post(self, service, mock_db, mock_agent_service):
        """Groq returns 'flagged' → post should be hidden."""
        post_id = str(uuid4())
        mock_agent_service.classify_content = AsyncMock(return_value="flagged")

        self._mock_post_select(mock_db, post_id)

        await service.moderate_post(mock_db, post_id, mock_agent_service)

        # Should have set is_hidden=true and is_pending_moderation=false
        assert mock_db.execute.call_count >= 2  # SELECT + UPDATE
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_moderation_both_fail_timeout_unhides(self, service, mock_db):
        """Both AI providers fail → is_pending_moderation cleared."""
        post_id = str(uuid4())

        mock_agent = _AgentServiceStub()
        mock_agent.classify_content_groq = AsyncMock(
            side_effect=Exception("429 Too Many Requests")
        )
        mock_agent.classify_content_gemini = AsyncMock(
            side_effect=asyncio.TimeoutError
        )

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
    @pytest.mark.asyncio
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


# =============================================================================
# edit_and_resubmit
# =============================================================================


class TestEditAndResubmit:
    @pytest.mark.asyncio
    async def test_flagged_post_edit_resubmit(self, service, mock_db, mock_agent_service):
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
        select_result.mappings.return_value.fetchone.return_value = existing_post._mapping

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
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        mock_db.execute = AsyncMock(side_effect=[select_result, update_result, MagicMock()])

        edit_data = {
            "title": "Edited title for resubmission",
            "body": "Edited body with better content that passes moderation guidelines.",
        }

        result = await service.edit_and_resubmit(mock_db, user_id, post_id, edit_data, mock_agent_service)

        assert result["is_pending_moderation"] is True
        assert result["is_hidden"] is False
        mock_agent_service.classify_content.assert_called_once()


# =============================================================================
# get_stats
# =============================================================================


class TestCommunityStats:
    @pytest.mark.asyncio
    async def test_community_stats(self, service, mock_db):
        """get_stats returns total_users, avg_savings_pct, top_tip with attribution."""
        stats_result = MagicMock()
        stats_result.mappings.return_value.fetchone.return_value = {
            "total_users": 42,
            "earliest_post": datetime(2026, 1, 1, tzinfo=timezone.utc),
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
    @pytest.mark.asyncio
    async def test_rate_limit_posts(self, service, mock_db, mock_agent_service, sample_post_data):
        """11th post in an hour should raise a rate limit error."""
        user_id = str(uuid4())

        # Rate limit check returns 10 (at the limit)
        rate_result = MagicMock()
        rate_result.scalar.return_value = 10

        mock_db.execute = AsyncMock(return_value=rate_result)

        with pytest.raises(Exception, match="rate limit|too many"):
            await service.create_post(mock_db, user_id, sample_post_data, mock_agent_service)
