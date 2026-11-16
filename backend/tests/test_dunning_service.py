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

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from services.dunning_service import DUNNING_COOLDOWN_HOURS, DunningService

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
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }[key]
        row.keys = lambda: [
            "id",
            "user_id",
            "stripe_invoice_id",
            "stripe_customer_id",
            "retry_count",
            "retry_type",
            "amount_owed",
            "currency",
            "email_sent",
            "email_sent_at",
            "escalation_action",
            "created_at",
            "updated_at",
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
    async def test_returns_count(self, dunning, mock_db):
        """Should return the count for a known invoice."""
        result = MagicMock()
        result.scalar.return_value = 3
        mock_db.execute = AsyncMock(return_value=result)

        count = await dunning.get_retry_count("inv_123")
        assert count == 3

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
    async def test_true_when_no_recent_email(self, dunning, mock_db):
        """Should return True when no email was sent in the cooldown window."""
        result = MagicMock()
        result.first.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        should_send = await dunning.should_send_dunning("user-1", "inv_123")
        assert should_send is True

    async def test_false_when_recent_email_exists(self, dunning, mock_db):
        """Should return False when an email was sent within cooldown."""
        recent = MagicMock()
        recent.email_sent_at = datetime.now(UTC) - timedelta(hours=1)
        result = MagicMock()
        result.first.return_value = recent
        mock_db.execute = AsyncMock(return_value=result)

        should_send = await dunning.should_send_dunning("user-1", "inv_123")
        assert should_send is False


# =============================================================================
# send_dunning_email
# =============================================================================


class TestSendDunningEmail:
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
    async def test_downgrades_after_3_failures(self, dunning, mock_user_repo):
        """User on paid tier should be downgraded after 3 failures."""
        action = await dunning.escalate_if_needed("user-1", 3, mock_user_repo)
        assert action == "downgraded_to_free"
        mock_user_repo.update.assert_awaited_once()

    async def test_no_op_if_already_free(self, dunning, mock_user_repo):
        """Already-free users should not be modified."""
        user = mock_user_repo.get_by_id.return_value
        user.subscription_tier = "free"

        action = await dunning.escalate_if_needed("user-1", 3, mock_user_repo)
        assert action is None
        mock_user_repo.update.assert_not_awaited()

    async def test_no_escalation_under_3(self, dunning, mock_user_repo):
        """retry_count < 3 should not trigger escalation."""
        action = await dunning.escalate_if_needed("user-1", 2, mock_user_repo)
        assert action is None


# =============================================================================
# handle_payment_failure (full orchestrator)
# =============================================================================


class TestHandlePaymentFailure:
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

        mock_db.execute = AsyncMock(side_effect=[count_result, insert_result, cooldown_result])

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

    async def test_dispatcher_failure_falls_back_to_email_service(
        self, mock_db, mock_email_service
    ):
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

    async def test_dispatcher_dedup_key_includes_user_and_template(
        self, mock_db, mock_email_service
    ):
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


# =============================================================================
# TestSingleCommit — the failure flow must not commit mid-flow (D7)
# =============================================================================


def _failure_row():
    row_data = {"id": str(uuid4()), "retry_count": 1}
    row = MagicMock()
    row.__getitem__ = lambda self, key: row_data[key]
    row.get = lambda key, default=None: row_data.get(key, default)
    row.keys = lambda: list(row_data.keys())
    return row


class TestHandlePaymentFailureSingleCommit:
    """
    handle_payment_failure shares its session with the Stripe webhook handler,
    whose idempotency guard row sits in the same transaction.  A commit before
    the email/escalation steps would mark the event processed even if they
    crash, so the flow must commit exactly once, at its exit.
    """

    def _db(self, mock_db, cooldown_active: bool):
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        insert_result = MagicMock()
        insert_result.mappings.return_value.first.return_value = _failure_row()
        cooldown_result = MagicMock()
        cooldown_result.first.return_value = MagicMock() if cooldown_active else None
        mock_db.execute = AsyncMock(
            side_effect=[count_result, insert_result, cooldown_result, MagicMock(), MagicMock()]
        )
        return mock_db

    async def _run(self, dunning, mock_user_repo):
        return await dunning.handle_payment_failure(
            user_id="user-1",
            stripe_invoice_id="inv_123",
            stripe_customer_id="cus_123",
            amount_owed=4.99,
            currency="USD",
            user_email="test@example.com",
            user_name="Test",
            user_repo=mock_user_repo,
        )

    async def test_no_commit_before_email_is_sent(
        self, mock_db, mock_email_service, mock_user_repo
    ):
        """Nothing may be committed by the time the dunning email goes out."""
        db = self._db(mock_db, cooldown_active=False)
        commits_at_send: list[int] = []

        async def _send(**_kwargs):
            commits_at_send.append(db.commit.await_count)
            return True

        mock_email_service.send = AsyncMock(side_effect=_send)

        dunning = DunningService(db, email_service=mock_email_service)
        result = await self._run(dunning, mock_user_repo)

        assert result["email_sent"] is True
        assert commits_at_send == [0], "flow committed before the email step"
        assert db.commit.await_count == 1

    async def test_crash_after_record_leaves_nothing_committed(
        self, mock_db, mock_email_service, mock_user_repo
    ):
        """If escalation raises, the failure record must still be uncommitted."""
        db = self._db(mock_db, cooldown_active=False)
        mock_user_repo.get_by_id = AsyncMock(side_effect=RuntimeError("db gone"))

        count_result = MagicMock()
        count_result.scalar.return_value = 2  # third failure -> escalation runs
        row_data = {"id": str(uuid4()), "retry_count": 3}
        row = MagicMock()
        row.get = lambda key, default=None: row_data.get(key, default)
        row.keys = lambda: list(row_data.keys())
        row.__getitem__ = lambda self, key: row_data[key]
        insert_result = MagicMock()
        insert_result.mappings.return_value.first.return_value = row
        cooldown_result = MagicMock()
        cooldown_result.first.return_value = None
        db.execute = AsyncMock(
            side_effect=[count_result, insert_result, cooldown_result, MagicMock()]
        )

        dunning = DunningService(db, email_service=mock_email_service)
        with pytest.raises(RuntimeError, match="db gone"):
            await self._run(dunning, mock_user_repo)

        db.commit.assert_not_awaited()

    async def test_cooldown_exit_commits_once(self, mock_db, mock_email_service, mock_user_repo):
        """The cooldown early return still persists the failure record."""
        db = self._db(mock_db, cooldown_active=True)

        dunning = DunningService(db, email_service=mock_email_service)
        result = await self._run(dunning, mock_user_repo)

        assert result["email_sent"] is False
        assert db.commit.await_count == 1


# =============================================================================
# TestResolvedFailures — paid customers must not be treated as overdue (D1)
# =============================================================================


class TestResolvePaymentFailures:
    async def test_stamps_resolved_at_on_unresolved_rows(self, dunning, mock_db):
        update_result = MagicMock()
        update_result.rowcount = 3
        mock_db.execute = AsyncMock(return_value=update_result)

        resolved = await dunning.resolve_payment_failures("user-1")

        assert resolved == 3
        sql = str(mock_db.execute.await_args.args[0])
        assert "UPDATE payment_retry_history" in sql
        assert "resolved_at = NOW()" in sql
        assert "user_id = :user_id" in sql
        assert "resolved_at IS NULL" in sql
        assert mock_db.execute.await_args.args[1] == {"user_id": "user-1"}
        # Caller owns the transaction.
        mock_db.commit.assert_not_awaited()

    async def test_returns_zero_when_nothing_outstanding(self, dunning, mock_db):
        update_result = MagicMock()
        update_result.rowcount = 0
        mock_db.execute = AsyncMock(return_value=update_result)

        assert await dunning.resolve_payment_failures("user-1") == 0


class TestGetOverdueAccounts:
    async def test_query_requires_unresolved_latest_failure(self, dunning, mock_db):
        """The overdue query must ignore failures the customer has since paid."""
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        await dunning.get_overdue_accounts(grace_period_days=7)

        sql = " ".join(str(mock_db.execute.await_args.args[0]).split())
        assert "prh.resolved_at IS NULL" in sql
        # A user whose latest row is resolved is never overdue.
        assert "NOT EXISTS" in sql
        assert "newer.resolved_at IS NOT NULL" in sql
        assert "newer.created_at > prh.created_at" in sql

    async def test_unpaid_behaviour_unchanged(self, dunning, mock_db):
        """Grace-period cutoff, paid-tier and active filters are still applied."""
        row = {"user_id": "user-1", "retry_count": 3, "email": "a@example.com"}
        result = MagicMock()
        result.mappings.return_value.all.return_value = [row]
        mock_db.execute = AsyncMock(return_value=result)

        before = datetime.now(UTC)
        overdue = await dunning.get_overdue_accounts(grace_period_days=7)

        assert overdue == [row]
        sql = " ".join(str(mock_db.execute.await_args.args[0]).split())
        assert "SELECT DISTINCT ON (prh.user_id)" in sql
        assert "prh.created_at <= :cutoff" in sql
        assert "u.subscription_tier != 'free'" in sql
        assert "u.is_active = TRUE" in sql
        assert "ORDER BY prh.user_id, prh.created_at DESC" in sql
        cutoff = mock_db.execute.await_args.args[1]["cutoff"]
        assert abs((before - timedelta(days=7)) - cutoff) < timedelta(seconds=5)


class TestMigration070Structure:
    def _sql(self) -> str:
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent / "migrations"
        return (path / "070_payment_retry_resolved.sql").read_text()

    def test_adds_nullable_resolved_at_idempotently(self):
        sql = " ".join(self._sql().split())
        assert "ALTER TABLE payment_retry_history" in sql
        assert "ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;" in sql

    def test_partial_index_is_idempotent(self):
        sql = " ".join(self._sql().split())
        assert "CREATE INDEX IF NOT EXISTS idx_payment_retry_unresolved" in sql
        assert "WHERE resolved_at IS NULL" in sql
