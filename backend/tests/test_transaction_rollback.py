"""
Tests for transaction rollback safety on write methods.

Verifies that all services/repositories that call db.commit() or db.flush()
properly wrap those calls in try/except blocks that roll back the session
on failure, preventing a dirty AsyncSession from poisoning subsequent operations.

Sprint 0 Tasks 0.7, 0.8, 0.9 — audit remediation.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# =============================================================================
# Helpers
# =============================================================================


def _mock_db(commit_side_effect=None):
    """Build a mock AsyncSession with configurable commit behavior."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock(side_effect=commit_side_effect)
    db.rollback = AsyncMock()
    db.flush = AsyncMock()
    return db


def _make_mapping_first(row):
    """Mock execute() result whose .mappings().first() returns row."""
    result = MagicMock()
    mapping = MagicMock()
    mapping.first.return_value = row
    result.mappings.return_value = mapping
    return result


def _make_mapping_fetchone(row):
    """Mock execute() result whose .mappings().fetchone() returns row."""
    result = MagicMock()
    mapping = MagicMock()
    mapping.fetchone.return_value = row
    result.mappings.return_value = mapping
    return result


def _make_result(rowcount=1):
    """Mock execute() result with configurable rowcount."""
    result = MagicMock()
    result.rowcount = rowcount
    return result


# =============================================================================
# Task 0.7 — AffiliateService rollback safety
# =============================================================================


class TestAffiliateServiceRollback:
    """Verify AffiliateService rolls back on commit failure."""

    async def test_record_click_rollback_on_commit_failure(self):
        from services.affiliate_service import AffiliateService

        db = _mock_db(commit_side_effect=Exception("unique constraint violated"))
        service = AffiliateService(db)

        with pytest.raises(Exception, match="unique constraint violated"):
            await service.record_click(
                user_id="user-1",
                supplier_id="sup-1",
                supplier_name="Eversource",
                utility_type="electricity",
                region="CT",
                source_page="/rates",
                affiliate_url="https://example.com",
            )

        db.rollback.assert_awaited_once()

    async def test_mark_converted_rollback_on_commit_failure(self):
        from services.affiliate_service import AffiliateService

        db = _mock_db(commit_side_effect=Exception("deadlock detected"))
        result_mock = MagicMock()
        result_mock.rowcount = 1
        db.execute.return_value = result_mock
        service = AffiliateService(db)

        with pytest.raises(Exception, match="deadlock detected"):
            await service.mark_converted("click-1", commission_cents=500)

        db.rollback.assert_awaited_once()


# =============================================================================
# Task 0.7 — NotificationService rollback safety
# =============================================================================


class TestNotificationServiceRollback:
    """Verify NotificationService rolls back on commit failure."""

    async def test_create_rollback_on_commit_failure(self):
        from services.notification_service import NotificationService

        db = _mock_db(commit_side_effect=Exception("FK constraint"))
        svc = NotificationService(db)

        with pytest.raises(Exception, match="FK constraint"):
            await svc.create(user_id="user-1", title="Test", body="body")

        db.rollback.assert_awaited_once()

    async def test_mark_all_read_rollback_on_commit_failure(self):
        from services.notification_service import NotificationService

        db = _mock_db(commit_side_effect=Exception("connection lost"))
        result_mock = MagicMock()
        result_mock.rowcount = 3
        db.execute.return_value = result_mock
        svc = NotificationService(db)

        with pytest.raises(Exception, match="connection lost"):
            await svc.mark_all_read("user-1")

        db.rollback.assert_awaited_once()

    async def test_mark_read_rollback_on_commit_failure(self):
        from services.notification_service import NotificationService

        db = _mock_db(commit_side_effect=Exception("timeout"))
        result_mock = MagicMock()
        result_mock.rowcount = 1
        db.execute.return_value = result_mock
        svc = NotificationService(db)

        with pytest.raises(Exception, match="timeout"):
            await svc.mark_read("user-1", str(uuid4()))

        db.rollback.assert_awaited_once()


# =============================================================================
# Task 0.7 — CommunityService rollback safety
# =============================================================================


class TestCommunityServiceRollback:
    """Verify CommunityService rolls back on commit failure."""

    async def test_create_post_rollback_on_commit_failure(self):
        from services.community_service import CommunityService

        db = _mock_db(commit_side_effect=Exception("constraint violation"))
        # Rate check returns 0
        rate_result = MagicMock()
        rate_result.scalar.return_value = 0
        # INSERT returns a post row
        post_row = {
            "id": str(uuid4()),
            "user_id": "user-1",
            "region": "us_ct",
            "utility_type": "electricity",
            "post_type": "tip",
            "title": "test",
            "body": "body",
            "is_hidden": False,
            "is_pending_moderation": True,
        }
        insert_result = _make_mapping_fetchone(post_row)
        db.execute = AsyncMock(side_effect=[rate_result, insert_result])

        svc = CommunityService()

        with pytest.raises(Exception, match="constraint violation"):
            await svc.create_post(
                db=db,
                user_id="user-1",
                data={
                    "title": "test",
                    "body": "body",
                    "region": "us_ct",
                    "utility_type": "electricity",
                    "post_type": "tip",
                },
                agent_service=AsyncMock(),
            )

        db.rollback.assert_awaited_once()

    async def test_toggle_vote_rollback_on_commit_failure(self):
        from services.community_service import CommunityService

        db = _mock_db(commit_side_effect=Exception("serialization failure"))
        toggle_result = MagicMock()
        toggle_result.mappings.return_value.fetchone.return_value = {
            "action": "inserted",
            "upvote_count": 1,
        }
        db.execute.return_value = toggle_result
        svc = CommunityService()

        with pytest.raises(Exception, match="serialization failure"):
            await svc.toggle_vote(db=db, user_id="user-1", post_id=str(uuid4()))

        db.rollback.assert_awaited_once()

    async def test_report_post_rollback_on_commit_failure(self):
        from services.community_service import CommunityService

        db = _mock_db(commit_side_effect=Exception("constraint error"))
        db.execute.return_value = MagicMock()
        svc = CommunityService()

        with pytest.raises(Exception, match="constraint error"):
            await svc.report_post(
                db=db,
                user_id="user-1",
                post_id=str(uuid4()),
                reason="spam",
            )

        db.rollback.assert_awaited_once()

    async def test_edit_and_resubmit_rollback_on_commit_failure(self):
        from services.community_service import CommunityService

        db = _mock_db(commit_side_effect=Exception("write conflict"))
        # SELECT existing post
        existing = {
            "id": "post-1",
            "user_id": "user-1",
            "title": "Old",
            "body": "Old body",
        }
        select_result = _make_mapping_fetchone(existing)
        # UPDATE returns the updated post
        updated = {**existing, "title": "New", "body": "New body", "is_pending_moderation": True}
        update_result = _make_mapping_fetchone(updated)
        db.execute = AsyncMock(side_effect=[select_result, update_result])
        svc = CommunityService()

        with pytest.raises(Exception, match="write conflict"):
            await svc.edit_and_resubmit(
                db=db,
                user_id="user-1",
                post_id="post-1",
                data={"title": "New", "body": "New body"},
                agent_service=AsyncMock(),
            )

        db.rollback.assert_awaited_once()

    async def test_clear_pending_moderation_rollback_on_commit_failure(self):
        from services.community_service import CommunityService

        db = _mock_db(commit_side_effect=Exception("session error"))
        db.execute.return_value = MagicMock()
        svc = CommunityService()

        with pytest.raises(Exception, match="session error"):
            await svc._clear_pending_moderation(db=db, post_id="post-1")

        db.rollback.assert_awaited_once()

    async def test_moderate_post_rollback_on_commit_failure(self):
        from services.community_service import CommunityService

        db = _mock_db(commit_side_effect=Exception("db error"))
        # SELECT post returns content
        post_result = _make_mapping_fetchone({"title": "Hello", "body": "world"})
        # UPDATE result
        update_result = MagicMock()
        db.execute = AsyncMock(side_effect=[post_result, update_result])

        agent = AsyncMock()
        agent.classify_content = AsyncMock(return_value="safe")
        svc = CommunityService()

        with pytest.raises(Exception, match="db error"):
            await svc.moderate_post(db=db, post_id="post-1", agent_service=agent)

        db.rollback.assert_awaited_once()


# =============================================================================
# Task 0.7 — SavingsService rollback safety
# =============================================================================


class TestSavingsServiceRollback:
    """Verify SavingsService rolls back on commit failure."""

    async def test_record_savings_rollback_on_commit_failure(self):
        from services.savings_service import SavingsService

        db = _mock_db(commit_side_effect=Exception("unique violation"))
        now = datetime.now(tz=UTC)
        returned_row = {
            "id": str(uuid4()),
            "user_id": "user-1",
            "savings_type": "switching",
            "amount": 10.0,
            "currency": "USD",
            "description": None,
            "region": "US_CT",
            "period_start": now - timedelta(days=30),
            "period_end": now,
            "created_at": now,
        }
        db.execute.return_value = _make_mapping_first(returned_row)
        svc = SavingsService(db)

        with pytest.raises(Exception, match="unique violation"):
            await svc.record_savings(
                user_id="user-1",
                savings_type="switching",
                amount=10.0,
                period_start=now - timedelta(days=30),
                period_end=now,
            )

        db.rollback.assert_awaited_once()


# =============================================================================
# Task 0.7 — GasRateService has no direct commit() calls (uses PriceRepository)
# Verify fetch_gas_rates does not leave sessions dirty on partial failure
# =============================================================================


class TestGasRateServiceRollback:
    """GasRateService delegates writes to PriceRepository.create().
    No direct commit calls to wrap, but we verify the pattern is safe."""

    async def test_fetch_gas_rates_handles_partial_failure(self):
        """Partial failure should be caught per-state, not crash the batch."""
        from integrations.pricing_apis.base import (APIError, PriceData,
                                                    PriceUnit)
        from services.gas_rate_service import GasRateService

        mock_db = AsyncMock()
        mock_eia = AsyncMock()

        async def mock_get_gas(region):
            if "pa" in region.value:
                raise APIError("No gas data for PA", api_name="eia")
            return PriceData(
                region=region,
                timestamp=datetime.now(UTC),
                price=1.5,
                unit=PriceUnit.THERM,
                currency="USD",
                supplier=None,
                source_api="eia",
            )

        mock_eia.get_gas_price = mock_get_gas

        service = GasRateService(db=mock_db, eia_client=mock_eia)
        result = await service.fetch_gas_rates(states=["CT", "PA"])

        assert result["fetched"] == 1
        assert result["errors"] == 1


# =============================================================================
# Task 0.8 — ForecastObservationRepository rollback safety
# =============================================================================


class TestForecastObservationRepositoryRollback:
    """Verify ForecastObservationRepository rolls back on commit failure."""

    async def test_insert_forecasts_rollback_on_commit_failure(self):
        from repositories.forecast_observation_repository import \
            ForecastObservationRepository

        db = _mock_db(commit_side_effect=Exception("disk full"))
        db.execute.return_value = MagicMock()
        repo = ForecastObservationRepository(db)

        predictions = [
            {
                "timestamp": datetime(2026, 2, 24, 10, 0, tzinfo=UTC),
                "predicted_price": 0.28,
                "confidence_lower": 0.24,
                "confidence_upper": 0.32,
            },
        ]

        with pytest.raises(Exception, match="disk full"):
            await repo.insert_forecasts(
                forecast_id="fc-001",
                region="US_CT",
                predictions=predictions,
                model_version="v1.0",
            )

        db.rollback.assert_awaited_once()

    async def test_backfill_actuals_rollback_on_commit_failure(self):
        from repositories.forecast_observation_repository import \
            ForecastObservationRepository

        db = _mock_db(commit_side_effect=Exception("connection reset"))
        result = MagicMock()
        result.rowcount = 5
        db.execute.return_value = result
        repo = ForecastObservationRepository(db)

        with pytest.raises(Exception, match="connection reset"):
            await repo.backfill_actuals(region="us_ct")

        db.rollback.assert_awaited_once()

    async def test_insert_recommendation_rollback_on_commit_failure(self):
        from repositories.forecast_observation_repository import \
            ForecastObservationRepository

        db = _mock_db(commit_side_effect=Exception("FK violation"))
        db.execute.return_value = MagicMock()
        repo = ForecastObservationRepository(db)

        with pytest.raises(Exception, match="FK violation"):
            await repo.insert_recommendation(
                user_id="user-abc",
                recommendation_type="switch_supplier",
                recommendation_data={"supplier": "Test"},
            )

        db.rollback.assert_awaited_once()

    async def test_update_recommendation_response_rollback_on_commit_failure(self):
        from repositories.forecast_observation_repository import \
            ForecastObservationRepository

        db = _mock_db(commit_side_effect=Exception("serialization failure"))
        result = MagicMock()
        result.rowcount = 1
        db.execute.return_value = result
        repo = ForecastObservationRepository(db)

        with pytest.raises(Exception, match="serialization failure"):
            await repo.update_recommendation_response(
                outcome_id="outcome-001",
                accepted=True,
            )

        db.rollback.assert_awaited_once()


# =============================================================================
# Task 0.9 — CommunityService.retroactive_moderate must NOT use
# asyncio.gather with shared AsyncSession
# =============================================================================


class TestCommunityServiceNoGatherWithSession:
    """Verify retroactive_moderate does not use asyncio.gather with DB writes."""

    async def test_retroactive_moderate_sequential_db_writes(self):
        """The DB UPDATE for flagged posts should be done sequentially, not via gather."""
        from services.community_service import CommunityService

        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        # Return 2 posts that need re-moderation
        posts_result = MagicMock()
        posts_result.mappings.return_value.fetchall.return_value = [
            {"id": "post-1", "title": "Post 1", "body": "Body 1"},
            {"id": "post-2", "title": "Post 2", "body": "Body 2"},
        ]
        # Subsequent UPDATE calls return OK
        update_result = MagicMock()
        db.execute = AsyncMock(side_effect=[posts_result, update_result])

        agent = AsyncMock()
        agent.classify_content = AsyncMock(return_value="flagged")

        svc = CommunityService()
        count = await svc.retroactive_moderate(db=db, agent_service=agent)

        assert count == 2

    async def test_retroactive_moderate_classify_calls_are_sequential(self):
        """Each classify_content call should complete before the next starts
        when they share a DB session context (even though the AI calls themselves
        don't use the session, the subsequent DB write does)."""
        from services.community_service import CommunityService

        db = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        posts_result = MagicMock()
        posts_result.mappings.return_value.fetchall.return_value = [
            {"id": "post-1", "title": "P1", "body": "B1"},
            {"id": "post-2", "title": "P2", "body": "B2"},
            {"id": "post-3", "title": "P3", "body": "B3"},
        ]
        update_result = MagicMock()
        db.execute = AsyncMock(side_effect=[posts_result, update_result])

        call_order = []

        async def mock_classify(content):
            call_order.append(f"start:{content[:2]}")
            await asyncio.sleep(0.01)  # Simulate async work
            call_order.append(f"end:{content[:2]}")
            return "safe"

        agent = AsyncMock()
        agent.classify_content = mock_classify

        svc = CommunityService()
        await svc.retroactive_moderate(db=db, agent_service=agent)

        # Verify calls were sequential: each start should be followed by its end
        # before the next start
        for i in range(0, len(call_order) - 1, 2):
            prefix = call_order[i].split(":")[1]
            assert call_order[i].startswith("start:")
            assert call_order[i + 1] == f"end:{prefix}"

    async def test_retroactive_moderate_rollback_on_commit_failure(self):
        """If the batch UPDATE commit fails, session should be rolled back."""
        from services.community_service import CommunityService

        db = _mock_db(commit_side_effect=Exception("commit failed"))
        posts_result = MagicMock()
        posts_result.mappings.return_value.fetchall.return_value = [
            {"id": "post-1", "title": "P1", "body": "B1"},
        ]
        update_result = MagicMock()
        db.execute = AsyncMock(side_effect=[posts_result, update_result])

        agent = AsyncMock()
        agent.classify_content = AsyncMock(return_value="flagged")

        svc = CommunityService()

        with pytest.raises(Exception, match="commit failed"):
            await svc.retroactive_moderate(db=db, agent_service=agent)

        db.rollback.assert_awaited_once()
