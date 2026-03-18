"""
Integration Tests — 5 Critical Missing Paths (Sprint 2, WS-C, S2-07)

1. Stripe E2E payment flow: invoice.payment_failed → dunning → email → escalation
2. Community rate limiting: >10 posts/hour returns 429-equivalent ValueError
3. Alert deduplication: same alert within cooldown is suppressed
4. Dunning escalation cycle: 7-day grace, soft → final → downgrade
5. Session/auth cache: cached sessions served from cache; expired cache forces DB re-query
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _row_mock(**kwargs):
    """Return a MagicMock that behaves like a SQLAlchemy RowMapping."""
    m = MagicMock()
    m.__getitem__ = lambda self, k: kwargs[k]
    m.get = lambda k, default=None: kwargs.get(k, default)
    m.__contains__ = lambda self, k: k in kwargs
    m._fields = list(kwargs.keys())
    # Make dict() work
    m.keys = MagicMock(return_value=list(kwargs.keys()))
    m.values = MagicMock(return_value=list(kwargs.values()))
    m.items = MagicMock(return_value=list(kwargs.items()))
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


def _execute_mock(scalar_value=None, first_value=None, mappings_rows=None):
    """
    Build an AsyncMock whose .execute() returns a result that supports
    .scalar(), .first(), .mappings().first(), .mappings().fetchone(),
    .scalar_one_or_none(), and .fetchall() / .mappings().all().
    """
    result = MagicMock()
    result.scalar = MagicMock(return_value=scalar_value)
    result.scalar_one_or_none = MagicMock(return_value=scalar_value)
    result.first = MagicMock(return_value=first_value)
    result.fetchall = MagicMock(return_value=mappings_rows or [])
    result.rowcount = 1

    mappings_obj = MagicMock()
    mappings_obj.first = MagicMock(return_value=mappings_rows[0] if mappings_rows else None)
    mappings_obj.fetchone = MagicMock(return_value=mappings_rows[0] if mappings_rows else None)
    mappings_obj.fetchall = MagicMock(return_value=mappings_rows or [])
    mappings_obj.all = MagicMock(return_value=mappings_rows or [])
    result.mappings = MagicMock(return_value=mappings_obj)

    execute = AsyncMock(return_value=result)
    return execute, result


# ===========================================================================
# 1. STRIPE E2E PAYMENT FLOW
# ===========================================================================
#
# Tests the full internal flow:
#   Webhook event dict (invoice.payment_failed)
#   → StripeService.handle_webhook_event (parses event, returns result dict)
#   → apply_webhook_action (resolves user via stripe_customer_id)
#   → DunningService.handle_payment_failure (records failure, sends email)
# All external I/O (Stripe API, email, DB) is mocked.
# ===========================================================================


class TestStripePaymentFailedFlow:
    """Integration: invoice.payment_failed → dunning service → email sent."""

    @pytest.fixture
    def stripe_event_payment_failed(self):
        """Minimal invoice.payment_failed webhook event dict."""
        return {
            "id": "evt_test_001",
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "id": "in_test_001",
                    "customer": "cus_test_abc",
                    "subscription": "sub_test_xyz",
                    "amount_due": 499,  # cents → $4.99
                    "currency": "usd",
                }
            },
        }

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.email = "user@example.com"
        user.name = "Test User"
        user.subscription_tier = "pro"
        return user

    @pytest.mark.asyncio
    async def test_handle_webhook_event_payment_failed_parses_correctly(
        self, stripe_event_payment_failed
    ):
        """StripeService.handle_webhook_event correctly parses invoice.payment_failed."""
        from services.stripe_service import StripeService

        with (
            patch("services.stripe_service.settings") as mock_settings,
            patch("services.stripe_service.traced") as mock_traced,
        ):
            mock_settings.stripe_secret_key = "sk_test_mock"
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_traced.return_value = mock_ctx

            svc = StripeService()
            svc._configured = True

            result = await svc.handle_webhook_event(stripe_event_payment_failed)

        assert result["handled"] is True
        assert result["action"] == "payment_failed"
        assert result["customer_id"] == "cus_test_abc"
        assert result["subscription_id"] == "sub_test_xyz"
        assert float(result["amount_due"]) == pytest.approx(4.99)
        assert result["currency"] == "USD"
        assert result["invoice_id"] == "in_test_001"

    @pytest.mark.asyncio
    async def test_apply_webhook_action_resolves_user_via_customer_id(
        self, stripe_event_payment_failed, mock_user
    ):
        """apply_webhook_action resolves user via stripe_customer_id when no user_id in event."""
        from services.stripe_service import apply_webhook_action

        payment_failed_result = {
            "handled": True,
            "action": "payment_failed",
            "user_id": None,  # invoices carry no user_id metadata
            "customer_id": "cus_test_abc",
            "invoice_id": "in_test_001",
            "amount_due": 4.99,
            "currency": "USD",
        }

        user_repo = AsyncMock()
        user_repo.get_by_stripe_customer_id = AsyncMock(return_value=mock_user)
        user_repo.get_by_id = AsyncMock(return_value=mock_user)

        # Mock the DB session and DunningService.
        # DunningService is imported locally inside apply_webhook_action; patch at its
        # definition module so the local import picks up the mock.
        mock_db = AsyncMock()

        dunning_mock = AsyncMock()
        dunning_mock.handle_payment_failure = AsyncMock(
            return_value={
                "recorded": True,
                "retry_count": 1,
                "email_sent": True,
                "escalation_action": None,
            }
        )

        import services.dunning_service  # ensure module loaded before patching

        with patch.object(services.dunning_service, "DunningService", return_value=dunning_mock):
            applied = await apply_webhook_action(payment_failed_result, user_repo, db=mock_db)

        assert applied is True
        user_repo.get_by_stripe_customer_id.assert_called_once_with("cus_test_abc")
        dunning_mock.handle_payment_failure.assert_called_once()

        call_kwargs = dunning_mock.handle_payment_failure.call_args.kwargs
        assert call_kwargs["user_id"] == str(mock_user.id)
        assert call_kwargs["stripe_invoice_id"] == "in_test_001"
        assert call_kwargs["amount_owed"] == pytest.approx(4.99)

    @pytest.mark.asyncio
    async def test_apply_webhook_action_returns_false_when_customer_not_found(self):
        """apply_webhook_action returns False when customer_id maps to no user."""
        from services.stripe_service import apply_webhook_action

        result = {
            "handled": True,
            "action": "payment_failed",
            "user_id": None,
            "customer_id": "cus_nonexistent",
            "invoice_id": "in_test_999",
            "amount_due": 4.99,
            "currency": "USD",
        }

        user_repo = AsyncMock()
        user_repo.get_by_stripe_customer_id = AsyncMock(return_value=None)

        applied = await apply_webhook_action(result, user_repo, db=AsyncMock())

        assert applied is False

    @pytest.mark.asyncio
    async def test_full_payment_failed_webhook_cycle(self, mock_user):
        """
        Full cycle: parse event → resolve user → record failure → send soft dunning email.
        Verifies the full internal chain fires in the right order.
        """
        from services.stripe_service import StripeService, apply_webhook_action

        event = {
            "id": "evt_full_cycle",
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "id": "in_full_cycle",
                    "customer": "cus_full_cycle",
                    "subscription": "sub_full_cycle",
                    "amount_due": 1499,
                    "currency": "usd",
                }
            },
        }

        call_log = []

        dunning_mock = AsyncMock()
        dunning_mock.handle_payment_failure = AsyncMock(
            side_effect=lambda **kw: (
                call_log.append(("dunning_called", kw))
                or {
                    "recorded": True,
                    "retry_count": 1,
                    "email_sent": True,
                    "escalation_action": None,
                }
            )
        )

        user_repo = AsyncMock()
        user_repo.get_by_stripe_customer_id = AsyncMock(return_value=mock_user)
        user_repo.get_by_id = AsyncMock(return_value=mock_user)
        mock_db = AsyncMock()

        import services.dunning_service  # ensure module loaded before patching

        with (
            patch("services.stripe_service.settings") as mock_settings,
            patch("services.stripe_service.traced") as mock_traced,
            patch.object(services.dunning_service, "DunningService", return_value=dunning_mock),
        ):
            mock_settings.stripe_secret_key = "sk_test_mock"
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_traced.return_value = mock_ctx

            svc = StripeService()
            svc._configured = True

            result = await svc.handle_webhook_event(event)
            applied = await apply_webhook_action(result, user_repo, db=mock_db)

        assert applied is True
        assert len(call_log) == 1
        _, kw = call_log[0]
        assert float(kw["amount_owed"]) == pytest.approx(14.99)
        assert kw["currency"] == "USD"


# ===========================================================================
# 2. COMMUNITY RATE LIMITING
# ===========================================================================
#
# Tests the 10-posts-per-hour limit in CommunityService.create_post.
# The service raises ValueError when the count >= POSTS_PER_HOUR_LIMIT.
# ===========================================================================


class TestCommunityRateLimiting:
    """Integration: >10 posts/hour raises ValueError (equiv. to 429)."""

    @pytest.fixture
    def service(self):
        from services.community_service import CommunityService

        return CommunityService()

    def _make_db(self, post_count: int) -> AsyncMock:
        """Return a mock db whose execute() reports post_count posts this hour."""
        db = AsyncMock()
        rate_result = MagicMock()
        rate_result.scalar = MagicMock(return_value=post_count)

        # The INSERT result for when rate limit is NOT exceeded
        post_row = _row_mock(
            id=str(uuid4()),
            user_id=str(uuid4()),
            region="US_CT",
            utility_type="electric",
            post_type="tip",
            title="Test post",
            body="Test body",
            rate_per_unit=None,
            rate_unit=None,
            supplier_name=None,
            is_hidden=False,
            is_pending_moderation=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        insert_result = MagicMock()
        insert_result.mappings = MagicMock(
            return_value=MagicMock(fetchone=MagicMock(return_value=post_row))
        )

        # First call = rate check, subsequent calls = insert + moderation updates
        db.execute = AsyncMock(
            side_effect=[
                rate_result,  # rate limit check
                insert_result,  # INSERT
                MagicMock(),  # moderation UPDATE
            ]
        )
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def post_data(self):
        return {
            "title": "Great tip",
            "body": "Switch to off-peak.",
            "region": "US_CT",
            "utility_type": "electric",
            "post_type": "tip",
        }

    @pytest.mark.asyncio
    async def test_post_below_limit_succeeds(self, service, post_data):
        """9 posts this hour — 10th post should succeed (no ValueError raised)."""
        db = self._make_db(post_count=9)
        agent = AsyncMock()
        agent.classify_content = AsyncMock(return_value="safe")

        # Should not raise; return value is the inserted row dict
        post = await service.create_post(db, "user-1", post_data, agent)
        assert post is not None
        assert "id" in post

    @pytest.mark.asyncio
    async def test_post_at_exact_limit_succeeds(self, service, post_data):
        """Exactly 10 posts this hour — the current post is the 10th, should succeed."""
        db = self._make_db(post_count=9)
        agent = AsyncMock()
        agent.classify_content = AsyncMock(return_value="safe")

        # count=9 means 9 existing posts this hour, 10th is allowed (< 10 check)
        post = await service.create_post(db, "user-1", post_data, agent)
        assert post is not None

    @pytest.mark.asyncio
    async def test_post_exceeds_limit_raises_value_error(self, service, post_data):
        """10 posts already this hour — 11th raises ValueError (rate limit exceeded)."""
        db = AsyncMock()
        rate_result = MagicMock()
        rate_result.scalar = MagicMock(return_value=10)  # already at limit
        db.execute = AsyncMock(return_value=rate_result)
        db.commit = AsyncMock()

        agent = AsyncMock()

        with pytest.raises(ValueError, match="Rate limit exceeded"):
            await service.create_post(db, "user-1", post_data, agent)

    @pytest.mark.asyncio
    async def test_rate_limit_per_user_independent(self, service, post_data):
        """Different users have independent rate limits (the db query is scoped by user_id)."""
        # User A is at the limit
        db_a = AsyncMock()
        rate_result_a = MagicMock()
        rate_result_a.scalar = MagicMock(return_value=10)
        db_a.execute = AsyncMock(return_value=rate_result_a)

        # User B has only 2 posts
        post_row = _row_mock(
            id=str(uuid4()),
            user_id="user-b",
            region="US_CT",
            utility_type="electric",
            post_type="tip",
            title="B tip",
            body="B body",
            rate_per_unit=None,
            rate_unit=None,
            supplier_name=None,
            is_hidden=False,
            is_pending_moderation=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        insert_result = MagicMock()
        insert_result.mappings = MagicMock(
            return_value=MagicMock(fetchone=MagicMock(return_value=post_row))
        )
        db_b = AsyncMock()
        rate_result_b = MagicMock()
        rate_result_b.scalar = MagicMock(return_value=2)
        db_b.execute = AsyncMock(side_effect=[rate_result_b, insert_result, MagicMock()])
        db_b.commit = AsyncMock()

        agent = AsyncMock()
        agent.classify_content = AsyncMock(return_value="safe")

        with pytest.raises(ValueError, match="Rate limit exceeded"):
            await service.create_post(db_a, "user-a", post_data, agent)

        # user-b should succeed
        result = await service.create_post(db_b, "user-b", post_data, agent)
        assert result is not None

    @pytest.mark.asyncio
    async def test_rate_limit_check_uses_correct_user_id(self, service, post_data):
        """The rate-limit SQL is parameterised with the correct user_id."""
        db = AsyncMock()
        rate_result = MagicMock()
        rate_result.scalar = MagicMock(return_value=11)
        db.execute = AsyncMock(return_value=rate_result)
        db.commit = AsyncMock()

        agent = AsyncMock()
        target_user = "target-user-uuid"

        with pytest.raises(ValueError):
            await service.create_post(db, target_user, post_data, agent)

        # Verify the execute call included the correct user_id
        call_args = db.execute.call_args_list[0]
        params = call_args[0][1]  # positional arg[1] is the params dict
        assert params["user_id"] == target_user


# ===========================================================================
# 3. ALERT DEDUPLICATION
# ===========================================================================
#
# Tests _should_send_alert and _batch_should_send_alerts:
# - A recent alert_history row within the cooldown window → skip
# - No recent row (or row outside window) → send
# Cooldowns: immediate/hourly=1h, daily=24h, weekly=7d
# ===========================================================================


class TestAlertDeduplication:
    """Integration: duplicate alerts within cooldown periods are suppressed."""

    @pytest.fixture
    def alert_service(self):
        from services.alert_service import AlertService

        mock_email = AsyncMock()
        mock_email.send = AsyncMock(return_value=True)
        mock_email.render_template = MagicMock(return_value="<html>test</html>")
        return AlertService(email_service=mock_email)

    # -----------------------------------------------------------------------
    # _should_send_alert
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_should_send_when_no_history(self, alert_service):
        """No prior alert → should_send returns True."""
        db = AsyncMock()
        result = MagicMock()
        result.first = MagicMock(return_value=None)  # no row found
        db.execute = AsyncMock(return_value=result)

        can_send = await alert_service._should_send_alert(
            user_id="user-1",
            alert_type="price_drop",
            region="US_CT",
            notification_frequency="immediate",
            db=db,
        )
        assert can_send is True

    @pytest.mark.asyncio
    async def test_should_not_send_within_immediate_cooldown(self, alert_service):
        """Alert sent <1h ago with 'immediate' frequency → suppressed."""
        db = AsyncMock()
        result = MagicMock()
        # Simulate a row found within the cooldown window
        result.first = MagicMock(return_value=MagicMock())
        db.execute = AsyncMock(return_value=result)

        can_send = await alert_service._should_send_alert(
            user_id="user-1",
            alert_type="price_drop",
            region="US_CT",
            notification_frequency="immediate",
            db=db,
        )
        assert can_send is False

    @pytest.mark.asyncio
    async def test_should_not_send_within_daily_cooldown(self, alert_service):
        """Alert sent <24h ago with 'daily' frequency → suppressed."""
        db = AsyncMock()
        result = MagicMock()
        result.first = MagicMock(return_value=MagicMock())
        db.execute = AsyncMock(return_value=result)

        can_send = await alert_service._should_send_alert(
            user_id="user-2",
            alert_type="price_spike",
            region="US_MA",
            notification_frequency="daily",
            db=db,
        )
        assert can_send is False

    @pytest.mark.asyncio
    async def test_should_not_send_within_weekly_cooldown(self, alert_service):
        """Alert sent <7d ago with 'weekly' frequency → suppressed."""
        db = AsyncMock()
        result = MagicMock()
        result.first = MagicMock(return_value=MagicMock())
        db.execute = AsyncMock(return_value=result)

        can_send = await alert_service._should_send_alert(
            user_id="user-3",
            alert_type="optimal_window",
            region="US_CA",
            notification_frequency="weekly",
            db=db,
        )
        assert can_send is False

    @pytest.mark.asyncio
    async def test_cooldown_cutoff_uses_correct_window_for_each_frequency(self, alert_service):
        """Verify that the cutoff parameter passed to the DB query matches the frequency."""

        for freq, expected_hours in [("immediate", 1), ("daily", 24), ("weekly", 168)]:
            db = AsyncMock()
            result = MagicMock()
            result.first = MagicMock(return_value=None)
            db.execute = AsyncMock(return_value=result)

            before = datetime.now(UTC)
            await alert_service._should_send_alert(
                user_id="u",
                alert_type="price_drop",
                region="US_CT",
                notification_frequency=freq,
                db=db,
            )
            _after = datetime.now(UTC)

            # Extract the cutoff value passed to execute
            call_params = db.execute.call_args[0][1]
            cutoff = call_params["cutoff"]

            expected_cutoff_approx = before - timedelta(hours=expected_hours)
            delta = abs((cutoff - expected_cutoff_approx).total_seconds())
            assert delta < 2, f"Cutoff for freq={freq!r} was off by {delta:.1f}s"

    # -----------------------------------------------------------------------
    # _batch_should_send_alerts
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_batch_dedup_returns_in_cooldown_set(self, alert_service):
        """_batch_should_send_alerts returns the set of (user, type, region) in cooldown."""

        user_id = str(uuid4())
        threshold = MagicMock()
        threshold.user_id = user_id

        alert = MagicMock()
        alert.alert_type = "price_drop"
        alert.region = "US_CT"

        triggered_pairs = [(threshold, alert)]
        freq_by_user = {user_id: "daily"}

        db = AsyncMock()
        # Simulate DB returning the row as in-cooldown
        cooldown_row = MagicMock()
        cooldown_row.__iter__ = MagicMock(return_value=iter([user_id, "price_drop", "US_CT"]))
        cooldown_row.__getitem__ = MagicMock(side_effect=[user_id, "price_drop", "US_CT"])

        # fetchall returns a list of rows with positional access [0], [1], [2]
        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(side_effect=lambda i: [user_id, "price_drop", "US_CT"][i])

        db_result = MagicMock()
        db_result.fetchall = MagicMock(return_value=[mock_row])
        db.execute = AsyncMock(return_value=db_result)

        in_cooldown = await alert_service._batch_should_send_alerts(
            triggered_pairs, freq_by_user, db
        )

        assert (user_id, "price_drop", "US_CT") in in_cooldown

    @pytest.mark.asyncio
    async def test_batch_dedup_empty_input_returns_empty_set(self, alert_service):
        """Empty triggered_pairs returns empty set without querying DB."""
        db = AsyncMock()
        result = await alert_service._batch_should_send_alerts([], {}, db)
        assert result == set()
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_batch_dedup_no_cooldown_when_db_returns_no_rows(self, alert_service):
        """When DB returns no rows, all alerts are outside cooldown (not suppressed)."""

        user_id = str(uuid4())
        threshold = MagicMock()
        threshold.user_id = user_id
        alert = MagicMock()
        alert.alert_type = "price_drop"
        alert.region = "US_CT"

        db_result = MagicMock()
        db_result.fetchall = MagicMock(return_value=[])
        db = AsyncMock()
        db.execute = AsyncMock(return_value=db_result)

        in_cooldown = await alert_service._batch_should_send_alerts(
            [(threshold, alert)], {user_id: "daily"}, db
        )
        assert len(in_cooldown) == 0


# ===========================================================================
# 4. DUNNING ESCALATION CYCLE
# ===========================================================================
#
# Tests the full 7-day grace period flow within DunningService:
#   1st failure → soft dunning email (retry_count=1, template=dunning_soft.html)
#   3rd failure → final dunning email (retry_count=3, template=dunning_final.html)
#   3rd failure → escalate_if_needed downgrades user to free
# ===========================================================================


class TestDunningEscalationCycle:
    """Integration: payment fails → soft dunning → final dunning → downgrade."""

    def _make_db_for_failure(self, existing_retries: int, email_in_cooldown: bool = False):
        """
        Build a mock db for DunningService that:
        - Returns `existing_retries` for COUNT(*) on payment_retry_history
        - Returns a row (or None) for the cooldown check
        - Accepts INSERT / UPDATE calls
        """
        db = AsyncMock()

        count_result = MagicMock()
        count_result.scalar = MagicMock(return_value=existing_retries)

        insert_row = {
            "id": str(uuid4()),
            "user_id": "user-dunning",
            "stripe_invoice_id": "in_test",
            "stripe_customer_id": "cus_test",
            "retry_count": existing_retries + 1,
            "retry_type": "soft" if (existing_retries + 1) < 3 else "final",
            "amount_owed": 4.99,
            "currency": "USD",
            "email_sent": False,
            "email_sent_at": None,
            "escalation_action": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        insert_result_row = _row_mock(**insert_row)
        insert_result = MagicMock()
        insert_result.mappings = MagicMock(
            return_value=MagicMock(first=MagicMock(return_value=insert_result_row))
        )

        cooldown_result = MagicMock()
        # If email_in_cooldown, return a row (meaning we recently sent) → skip email
        cooldown_result.first = MagicMock(return_value=MagicMock() if email_in_cooldown else None)

        update_result = MagicMock()
        update_result.rowcount = 1

        # Call sequence: COUNT, INSERT, cooldown SELECT, UPDATE email, UPDATE escalation
        db.execute = AsyncMock(
            side_effect=[
                count_result,  # get_retry_count
                insert_result,  # record_payment_failure INSERT
                cooldown_result,  # should_send_dunning SELECT
                update_result,  # mark email sent UPDATE
                update_result,  # escalation UPDATE (if needed)
            ]
        )
        db.commit = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_first_failure_sends_soft_dunning_email(self):
        """First payment failure sends soft dunning email (retry_count=1)."""
        from services.dunning_service import DunningService

        db = self._make_db_for_failure(existing_retries=0)
        email_service = AsyncMock()
        email_service.render_template = MagicMock(return_value="<html>soft</html>")
        email_service.send = AsyncMock(return_value=True)

        user_repo = AsyncMock()
        mock_user = MagicMock()
        mock_user.subscription_tier = "pro"
        user_repo.get_by_id = AsyncMock(return_value=mock_user)
        user_repo.update = AsyncMock()

        svc = DunningService(db, email_service=email_service)
        result = await svc.handle_payment_failure(
            user_id="user-dunning",
            stripe_invoice_id="in_test",
            stripe_customer_id="cus_test",
            amount_owed=4.99,
            currency="USD",
            user_email="user@example.com",
            user_name="Test User",
            user_repo=user_repo,
        )

        assert result["recorded"] is True
        assert result["retry_count"] == 1
        assert result["email_sent"] is True
        # First failure → no escalation
        assert result["escalation_action"] is None

        # Verify soft template used
        render_call = email_service.render_template.call_args
        assert render_call[0][0] == "dunning_soft.html"

    @pytest.mark.asyncio
    async def test_third_failure_sends_final_dunning_email(self):
        """Third payment failure sends final dunning email (retry_count=3)."""
        from services.dunning_service import DunningService

        db = self._make_db_for_failure(existing_retries=2)
        email_service = AsyncMock()
        email_service.render_template = MagicMock(return_value="<html>final</html>")
        email_service.send = AsyncMock(return_value=True)

        user_repo = AsyncMock()
        mock_user = MagicMock()
        mock_user.subscription_tier = "pro"
        user_repo.get_by_id = AsyncMock(return_value=mock_user)
        user_repo.update = AsyncMock()

        svc = DunningService(db, email_service=email_service)
        result = await svc.handle_payment_failure(
            user_id="user-dunning",
            stripe_invoice_id="in_test",
            stripe_customer_id="cus_test",
            amount_owed=4.99,
            currency="USD",
            user_email="user@example.com",
            user_name="Test User",
            user_repo=user_repo,
        )

        assert result["retry_count"] == 3
        assert result["email_sent"] is True
        # Third failure triggers escalation
        assert result["escalation_action"] == "downgraded_to_free"

        render_call = email_service.render_template.call_args
        assert render_call[0][0] == "dunning_final.html"

    @pytest.mark.asyncio
    async def test_escalation_downgrades_user_to_free_after_third_failure(self):
        """escalate_if_needed downgrades a pro user after 3 failures."""
        from services.dunning_service import DunningService

        db = AsyncMock()
        mock_user = MagicMock()
        mock_user.subscription_tier = "pro"

        user_repo = AsyncMock()
        user_repo.get_by_id = AsyncMock(return_value=mock_user)
        user_repo.update = AsyncMock()

        svc = DunningService(db)
        action = await svc.escalate_if_needed("user-1", retry_count=3, user_repo=user_repo)

        assert action == "downgraded_to_free"
        assert mock_user.subscription_tier == "free"
        user_repo.update.assert_called_once_with("user-1", mock_user)

    @pytest.mark.asyncio
    async def test_escalation_not_triggered_before_third_failure(self):
        """escalate_if_needed returns None for retry_count < 3."""
        from services.dunning_service import DunningService

        db = AsyncMock()
        user_repo = AsyncMock()
        svc = DunningService(db)

        for count in [1, 2]:
            action = await svc.escalate_if_needed("user-1", retry_count=count, user_repo=user_repo)
            assert action is None, f"Expected None for retry_count={count}"

        user_repo.get_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_escalation_skipped_for_already_free_user(self):
        """escalate_if_needed skips downgrade if user is already on free tier."""
        from services.dunning_service import DunningService

        db = AsyncMock()
        mock_user = MagicMock()
        mock_user.subscription_tier = "free"

        user_repo = AsyncMock()
        user_repo.get_by_id = AsyncMock(return_value=mock_user)
        user_repo.update = AsyncMock()

        svc = DunningService(db)
        action = await svc.escalate_if_needed("user-1", retry_count=3, user_repo=user_repo)

        assert action is None
        user_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_dunning_cooldown_prevents_duplicate_email(self):
        """
        If a dunning email was sent within 24h for this invoice, skip the second one.
        """
        from services.dunning_service import DunningService

        db = self._make_db_for_failure(existing_retries=0, email_in_cooldown=True)
        email_service = AsyncMock()
        email_service.render_template = MagicMock(return_value="<html>email</html>")
        email_service.send = AsyncMock(return_value=True)

        user_repo = AsyncMock()
        svc = DunningService(db, email_service=email_service)

        result = await svc.handle_payment_failure(
            user_id="user-dunning",
            stripe_invoice_id="in_test",
            stripe_customer_id="cus_test",
            amount_owed=4.99,
            currency="USD",
            user_email="user@example.com",
            user_name="Test User",
            user_repo=user_repo,
        )

        # Email should NOT have been sent (cooldown active)
        assert result["email_sent"] is False
        email_service.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_overdue_accounts_query_uses_grace_period_cutoff(self):
        """get_overdue_accounts filters by created_at <= cutoff (grace_period_days)."""
        from services.dunning_service import DunningService

        db = AsyncMock()
        db_result = MagicMock()
        db_result.mappings = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        db.execute = AsyncMock(return_value=db_result)

        svc = DunningService(db)
        before = datetime.now(UTC)
        await svc.get_overdue_accounts(grace_period_days=7)
        _after = datetime.now(UTC)

        call_params = db.execute.call_args[0][1]
        cutoff = call_params["cutoff"]
        expected = before - timedelta(days=7)
        delta = abs((cutoff - expected).total_seconds())
        assert delta < 2


# ===========================================================================
# 5. SESSION / AUTH CACHE
# ===========================================================================
#
# Tests _get_session_from_token in auth/neon_auth.py:
# - Cache HIT (Redis) returns cached SessionData without DB query
# - Cache MISS falls through to DB and populates cache
# - invalidate_session_cache removes the key from Redis
# The 60s TTL (Zenith P0 H-15-01) is validated via the setex call.
# ===========================================================================


class TestSessionAuthCache:
    """Integration: session cache serves from Redis; expired cache forces DB re-query."""

    def _token_cache_key(self, token: str) -> str:
        return f"session:{hashlib.sha256(token.encode()).hexdigest()[:32]}"

    @pytest.mark.asyncio
    async def test_cache_hit_returns_session_without_db_query(self):
        """Valid cached session data returned from Redis, DB is NOT queried."""
        from auth.neon_auth import _get_session_from_token

        token = "valid-session-token"
        cached_payload = json.dumps(
            {
                "user_id": "user-cached",
                "email": "cached@example.com",
                "name": "Cached User",
                "email_verified": True,
                "role": None,
            }
        )

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=cached_payload.encode())

        db = AsyncMock()

        result = await _get_session_from_token(token, db, redis)

        assert result is not None
        assert result.user_id == "user-cached"
        assert result.email == "cached@example.com"
        assert result.name == "Cached User"
        assert result.email_verified is True
        # DB should NOT have been queried
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_falls_through_to_db(self):
        """Cache miss: DB is queried and result is cached with 60s TTL."""
        from auth.neon_auth import _SESSION_CACHE_TTL, _get_session_from_token

        token = "uncached-session-token"

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)  # cache miss
        redis.setex = AsyncMock()

        db_row = MagicMock()
        db_row.user_id = "user-db"
        db_row.email = "db@example.com"
        db_row.name = "DB User"
        db_row.email_verified = True
        db_row.role = None

        db_result = MagicMock()
        db_result.fetchone = MagicMock(return_value=db_row)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=db_result)

        result = await _get_session_from_token(token, db, redis)

        assert result is not None
        assert result.user_id == "user-db"
        assert result.email == "db@example.com"

        # DB was queried
        db.execute.assert_called_once()

        # Result was cached with TTL = 60s (Zenith P0 H-15-01)
        redis.setex.assert_called_once()
        setex_args = redis.setex.call_args[0]
        assert setex_args[1] == _SESSION_CACHE_TTL  # TTL = 60
        assert _SESSION_CACHE_TTL == 60  # explicit assertion on the constant

    @pytest.mark.asyncio
    async def test_cache_miss_invalid_session_returns_none(self):
        """Cache miss + DB returns no row → None (session invalid/expired)."""
        from auth.neon_auth import _get_session_from_token

        token = "expired-session-token"

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)

        db_result = MagicMock()
        db_result.fetchone = MagicMock(return_value=None)  # no valid session in DB
        db = AsyncMock()
        db.execute = AsyncMock(return_value=db_result)

        result = await _get_session_from_token(token, db, redis)

        assert result is None
        # Nothing should be cached
        redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalidate_session_cache_removes_redis_key(self):
        """invalidate_session_cache deletes the hashed token key from Redis."""
        from auth.neon_auth import invalidate_session_cache

        token = "logout-token"
        redis = AsyncMock()
        redis.delete = AsyncMock(return_value=1)

        deleted = await invalidate_session_cache(token, redis)

        assert deleted is True
        expected_key = self._token_cache_key(token)
        redis.delete.assert_called_once_with(expected_key)

    @pytest.mark.asyncio
    async def test_invalidate_session_cache_returns_false_when_no_redis(self):
        """invalidate_session_cache returns False gracefully when Redis is None."""
        from auth.neon_auth import invalidate_session_cache

        deleted = await invalidate_session_cache("some-token", redis=None)
        assert deleted is False

    @pytest.mark.asyncio
    async def test_session_cache_key_uses_sha256_hash(self):
        """Cache key is sha256(token)[:32] — consistent across calls."""
        from auth.neon_auth import _get_session_from_token

        token = "deterministic-token"

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)

        db_row = MagicMock()
        db_row.user_id = "u1"
        db_row.email = "e@e.com"
        db_row.name = "N"
        db_row.email_verified = False
        db_row.role = None
        db_result = MagicMock()
        db_result.fetchone = MagicMock(return_value=db_row)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=db_result)

        await _get_session_from_token(token, db, redis)

        get_args = redis.get.call_args[0]
        expected_key = self._token_cache_key(token)
        assert get_args[0] == expected_key

    @pytest.mark.asyncio
    async def test_redis_error_falls_through_to_db_gracefully(self):
        """If Redis.get raises, fall through to DB without crashing."""
        from auth.neon_auth import _get_session_from_token

        token = "token-redis-fail"

        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=Exception("Redis connection refused"))

        db_row = MagicMock()
        db_row.user_id = "user-fallback"
        db_row.email = "fallback@example.com"
        db_row.name = "Fallback"
        db_row.email_verified = True
        db_row.role = None
        db_result = MagicMock()
        db_result.fetchone = MagicMock(return_value=db_row)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=db_result)

        # Should not raise
        result = await _get_session_from_token(token, db, redis)

        assert result is not None
        assert result.user_id == "user-fallback"
        db.execute.assert_called_once()
