"""
Tests for DunningService (backend/services/dunning_service.py)

Covers:
- record_payment_failure creates row
- get_retry_count correct / zero for unknown
- should_send_dunning true/false (cooldown)
- send_dunning_email soft/final template selection
- escalate_if_needed downgrades / no-op if already free
- handle_payment_failure full flow / dedup blocks
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from services.dunning_service import DunningService, DUNNING_COOLDOWN_HOURS


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock async database session."""
    db = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_email_service():
    """Mock EmailService."""
    svc = MagicMock()
    svc.render_template = MagicMock(return_value="<html>test</html>")
    svc.send = AsyncMock(return_value=True)
    return svc


@pytest.fixture
def mock_user_repo():
    """Mock UserRepository."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.name = "Test User"
    user.subscription_tier = "pro"

    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=user)
    repo.update = AsyncMock()
    return repo


@pytest.fixture
def dunning(mock_db, mock_email_service):
    """DunningService with mocked dependencies."""
    return DunningService(mock_db, email_service=mock_email_service)


# =============================================================================
# record_payment_failure
# =============================================================================


class TestRecordPaymentFailure:

    @pytest.mark.asyncio
    async def test_creates_row(self, dunning, mock_db):
        """record_payment_failure should INSERT a row (commit managed by orchestrator)."""
        row = MagicMock()
        row.__getitem__ = lambda self, key: {
            "id": str(uuid4()),
            "user_id": "user-1",
            "stripe_invoice_id": "inv_123",
            "stripe_customer_id": "cus_123",
            "retry_count": 1,
            "retry_type": "soft",
            "amount_owed": 4.99,
            "currency": "USD",
            "email_sent": False,
            "email_sent_at": None,
            "escalation_action": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }[key]
        row.keys = lambda: [
            "id", "user_id", "stripe_invoice_id", "stripe_customer_id",
            "retry_count", "retry_type", "amount_owed", "currency",
            "email_sent", "email_sent_at", "escalation_action",
            "created_at", "updated_at",
        ]

        # get_retry_count returns 0 (first failure)
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        # INSERT returning row
        insert_result = MagicMock()
        insert_result.mappings.return_value.first.return_value = row

        mock_db.execute = AsyncMock(side_effect=[count_result, insert_result])

        result = await dunning.record_payment_failure(
            user_id="user-1",
            stripe_invoice_id="inv_123",
            stripe_customer_id="cus_123",
            amount_owed=4.99,
        )

        assert mock_db.execute.await_count == 2  # COUNT + INSERT


# =============================================================================
# get_retry_count
# =============================================================================


class TestGetRetryCount:

    @pytest.mark.asyncio
    async def test_returns_count(self, dunning, mock_db):
        """Should return the count for a known invoice."""
        result = MagicMock()
        result.scalar.return_value = 3
        mock_db.execute = AsyncMock(return_value=result)

        count = await dunning.get_retry_count("inv_123")
        assert count == 3

    @pytest.mark.asyncio
    async def test_returns_zero_for_unknown(self, dunning, mock_db):
        """Should return 0 for an invoice with no retries."""
        result = MagicMock()
        result.scalar.return_value = 0
        mock_db.execute = AsyncMock(return_value=result)

        count = await dunning.get_retry_count("inv_unknown")
        assert count == 0


# =============================================================================
# should_send_dunning
# =============================================================================


class TestShouldSendDunning:

    @pytest.mark.asyncio
    async def test_true_when_no_recent_email(self, dunning, mock_db):
        """Should return True when no email was sent in the cooldown window."""
        result = MagicMock()
        result.first.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        should_send = await dunning.should_send_dunning("user-1", "inv_123")
        assert should_send is True

    @pytest.mark.asyncio
    async def test_false_when_recent_email_exists(self, dunning, mock_db):
        """Should return False when an email was sent within cooldown."""
        recent = MagicMock()
        recent.email_sent_at = datetime.now(timezone.utc) - timedelta(hours=1)
        result = MagicMock()
        result.first.return_value = recent
        mock_db.execute = AsyncMock(return_value=result)

        should_send = await dunning.should_send_dunning("user-1", "inv_123")
        assert should_send is False


# =============================================================================
# send_dunning_email
# =============================================================================


class TestSendDunningEmail:

    @pytest.mark.asyncio
    async def test_soft_template_when_under_3(self, dunning, mock_email_service):
        """retry_count < 3 should use dunning_soft.html template."""
        result = await dunning.send_dunning_email(
            user_email="test@example.com",
            user_name="Test User",
            retry_count=1,
            amount=4.99,
        )

        assert result is True
        mock_email_service.render_template.assert_called_once()
        template_arg = mock_email_service.render_template.call_args[0][0]
        assert template_arg == "dunning_soft.html"

    @pytest.mark.asyncio
    async def test_final_template_when_3_or_more(self, dunning, mock_email_service):
        """retry_count >= 3 should use dunning_final.html template."""
        result = await dunning.send_dunning_email(
            user_email="test@example.com",
            user_name="Test User",
            retry_count=3,
            amount=4.99,
        )

        assert result is True
        template_arg = mock_email_service.render_template.call_args[0][0]
        assert template_arg == "dunning_final.html"

    @pytest.mark.asyncio
    async def test_returns_false_on_email_failure(self, dunning, mock_email_service):
        """Should return False when email send fails."""
        mock_email_service.send = AsyncMock(return_value=False)

        result = await dunning.send_dunning_email(
            user_email="test@example.com",
            user_name="Test",
            retry_count=1,
        )

        assert result is False


# =============================================================================
# escalate_if_needed
# =============================================================================


class TestEscalateIfNeeded:

    @pytest.mark.asyncio
    async def test_downgrades_after_3_failures(self, dunning, mock_user_repo):
        """User on paid tier should be downgraded after 3 failures."""
        action = await dunning.escalate_if_needed("user-1", 3, mock_user_repo)
        assert action == "downgraded_to_free"
        mock_user_repo.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_op_if_already_free(self, dunning, mock_user_repo):
        """Already-free users should not be modified."""
        user = mock_user_repo.get_by_id.return_value
        user.subscription_tier = "free"

        action = await dunning.escalate_if_needed("user-1", 3, mock_user_repo)
        assert action is None
        mock_user_repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_escalation_under_3(self, dunning, mock_user_repo):
        """retry_count < 3 should not trigger escalation."""
        action = await dunning.escalate_if_needed("user-1", 2, mock_user_repo)
        assert action is None


# =============================================================================
# handle_payment_failure (full orchestrator)
# =============================================================================


class TestHandlePaymentFailure:

    @pytest.mark.asyncio
    async def test_full_flow(self, mock_db, mock_email_service, mock_user_repo):
        """Full flow: record → check cooldown → send email → no escalation (first failure)."""
        # Mock get_retry_count → 0
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        # Mock INSERT returning row
        row_data = {
            "id": str(uuid4()),
            "retry_count": 1,
        }
        row = MagicMock()
        row.__getitem__ = lambda self, key: row_data[key]
        row.get = lambda key, default=None: row_data.get(key, default)
        row.keys = lambda: list(row_data.keys())

        insert_result = MagicMock()
        insert_result.mappings.return_value.first.return_value = row

        # Mock should_send_dunning → True (no recent email)
        cooldown_result = MagicMock()
        cooldown_result.first.return_value = None

        # Mock UPDATE for email_sent
        update_result = MagicMock()

        mock_db.execute = AsyncMock(
            side_effect=[count_result, insert_result, cooldown_result, update_result]
        )

        dunning = DunningService(mock_db, email_service=mock_email_service)
        result = await dunning.handle_payment_failure(
            user_id="user-1",
            stripe_invoice_id="inv_123",
            stripe_customer_id="cus_123",
            amount_owed=4.99,
            currency="USD",
            user_email="test@example.com",
            user_name="Test",
            user_repo=mock_user_repo,
        )

        assert result["recorded"] is True
        assert result["email_sent"] is True
        assert result["escalation_action"] is None

    @pytest.mark.asyncio
    async def test_dedup_blocks_email(self, mock_db, mock_email_service, mock_user_repo):
        """When cooldown is active, email should not be sent."""
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        row_data = {"id": str(uuid4()), "retry_count": 1}
        row = MagicMock()
        row.__getitem__ = lambda self, key: row_data[key]
        row.get = lambda key, default=None: row_data.get(key, default)
        row.keys = lambda: list(row_data.keys())

        insert_result = MagicMock()
        insert_result.mappings.return_value.first.return_value = row

        # Recent email exists → cooldown active
        cooldown_row = MagicMock()
        cooldown_result = MagicMock()
        cooldown_result.first.return_value = cooldown_row

        mock_db.execute = AsyncMock(
            side_effect=[count_result, insert_result, cooldown_result]
        )

        dunning = DunningService(mock_db, email_service=mock_email_service)
        result = await dunning.handle_payment_failure(
            user_id="user-1",
            stripe_invoice_id="inv_123",
            stripe_customer_id="cus_123",
            amount_owed=4.99,
            currency="USD",
            user_email="test@example.com",
            user_name="Test",
            user_repo=mock_user_repo,
        )

        assert result["recorded"] is True
        assert result["email_sent"] is False
        mock_email_service.send.assert_not_awaited()


# =============================================================================
# TestDunningServiceWithDispatcher — dispatcher integration
# =============================================================================


class TestDunningServiceWithDispatcher:
    """Tests for DunningService.send_dunning_email() when a NotificationDispatcher is wired in."""

    def _make_dispatcher(self, send_return=None, skipped=False):
        """Build a mock dispatcher."""
        if send_return is None:
            send_return = {
                "skipped_dedup": skipped,
                "channels": {"email": not skipped, "push": not skipped},
            }
        dispatcher = MagicMock()
        dispatcher.send = AsyncMock(return_value=send_return)
        return dispatcher

    @pytest.mark.asyncio
    async def test_dispatcher_called_when_user_id_provided(self, mock_db, mock_email_service):
        """When a dispatcher and user_id are supplied, dispatcher.send() should be called."""
        dispatcher = self._make_dispatcher()
        svc = DunningService(mock_db, email_service=mock_email_service, dispatcher=dispatcher)

        result = await svc.send_dunning_email(
            user_email="test@example.com",
            user_name="Test User",
            retry_count=1,
            amount=4.99,
            user_id="user-1",
        )

        assert result is True
        dispatcher.send.assert_awaited_once()
        # Direct email service should NOT be called
        mock_email_service.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatcher_uses_email_and_push_channels(self, mock_db, mock_email_service):
        """The dispatcher call should include EMAIL and PUSH channels."""
        from services.notification_dispatcher import NotificationChannel

        dispatcher = self._make_dispatcher()
        svc = DunningService(mock_db, email_service=mock_email_service, dispatcher=dispatcher)

        await svc.send_dunning_email(
            user_email="test@example.com",
            user_name="Test User",
            retry_count=2,
            amount=4.99,
            user_id="user-1",
        )

        call_kwargs = dispatcher.send.call_args.kwargs
        channels = call_kwargs.get("channels", [])
        assert NotificationChannel.EMAIL in channels
        assert NotificationChannel.PUSH in channels

    @pytest.mark.asyncio
    async def test_dispatcher_dedup_skip_returns_true(self, mock_db, mock_email_service):
        """When the dispatcher deduplicates a dunning send, the method should return True."""
        dispatcher = self._make_dispatcher(skipped=True)
        svc = DunningService(mock_db, email_service=mock_email_service, dispatcher=dispatcher)

        result = await svc.send_dunning_email(
            user_email="test@example.com",
            user_name="Test User",
            retry_count=1,
            amount=4.99,
            user_id="user-1",
        )

        # Dedup-skipped is treated as success (no re-send needed)
        assert result is True
        mock_email_service.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatcher_failure_falls_back_to_email_service(self, mock_db, mock_email_service):
        """When the dispatcher raises, DunningService should fall back to direct email."""
        dispatcher = MagicMock()
        dispatcher.send = AsyncMock(side_effect=Exception("Dispatcher down"))

        svc = DunningService(mock_db, email_service=mock_email_service, dispatcher=dispatcher)

        result = await svc.send_dunning_email(
            user_email="test@example.com",
            user_name="Test User",
            retry_count=1,
            amount=4.99,
            user_id="user-1",
        )

        assert result is True
        mock_email_service.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_dispatcher_path_unchanged(self, dunning, mock_email_service):
        """Without a dispatcher, the legacy email path should still work."""
        result = await dunning.send_dunning_email(
            user_email="test@example.com",
            user_name="Test User",
            retry_count=1,
            amount=4.99,
            # user_id intentionally omitted
        )

        assert result is True
        mock_email_service.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatcher_skipped_when_no_user_id(self, mock_db, mock_email_service):
        """Dispatcher should be skipped when user_id is not provided (legacy callers)."""
        dispatcher = self._make_dispatcher()
        svc = DunningService(mock_db, email_service=mock_email_service, dispatcher=dispatcher)

        result = await svc.send_dunning_email(
            user_email="test@example.com",
            user_name="Test User",
            retry_count=1,
            amount=4.99,
            # user_id intentionally omitted
        )

        assert result is True
        # Dispatcher not called because user_id was missing
        dispatcher.send.assert_not_awaited()
        mock_email_service.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatcher_dedup_key_includes_user_and_template(self, mock_db, mock_email_service):
        """The dedup_key should embed user_id and the template name."""
        dispatcher = self._make_dispatcher()
        svc = DunningService(mock_db, email_service=mock_email_service, dispatcher=dispatcher)

        await svc.send_dunning_email(
            user_email="test@example.com",
            user_name="Test User",
            retry_count=1,
            amount=4.99,
            user_id="user-42",
        )

        call_kwargs = dispatcher.send.call_args.kwargs
        dedup_key = call_kwargs.get("dedup_key", "")
        assert "user-42" in dedup_key
        assert "dunning_soft.html" in dedup_key

    @pytest.mark.asyncio
    async def test_dispatcher_cooldown_is_24_hours(self, mock_db, mock_email_service):
        """The dispatcher cooldown_seconds should match DUNNING_COOLDOWN_HOURS * 3600."""
        dispatcher = self._make_dispatcher()
        svc = DunningService(mock_db, email_service=mock_email_service, dispatcher=dispatcher)

        await svc.send_dunning_email(
            user_email="test@example.com",
            user_name="Test User",
            retry_count=1,
            amount=4.99,
            user_id="user-1",
        )

        call_kwargs = dispatcher.send.call_args.kwargs
        assert call_kwargs.get("cooldown_seconds") == DUNNING_COOLDOWN_HOURS * 3600
