"""
Tests for Sprint 2 audit remediation: Webhook & Payment Data Integrity

Covers:
- Task 2.1: Webhook idempotency race fix — idempotency row deleted on failure
- Task 2.3: New handlers — invoice.payment_succeeded, charge.refunded,
            charge.dispute.created
- Task 2.4: Dunning reversibility — payment_succeeded restores tier
- Task 2.5: stripe.api_key set at module level (not per-request)
- Task 2.6: MRR prices sourced from settings, not hardcoded literals

Reference: .audit-2026-03-19/REMEDIATION-PLAN.md, Sprint 2
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.dependencies import SessionData, get_current_user, get_db_session

TEST_USER = SessionData(user_id="user-payment-1", email="payment@test.com")
BASE_URL = "/api/v1/billing"


# =============================================================================
# Fixtures
# =============================================================================


def _make_mock_user(tier="pro", customer_id="cus_test_123"):
    user = MagicMock()
    user.email = TEST_USER.email
    user.name = "Test User"
    user.stripe_customer_id = customer_id
    user.subscription_tier = tier
    return user


def _make_mock_user_repo(user=None):
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=user)
    repo.get_by_stripe_customer_id = AsyncMock(return_value=user)
    repo.update = AsyncMock(return_value=user)
    return repo


def _make_mock_db(rowcount=1):
    """
    Build a mock DB session that models the execute/commit/rollback cycle.
    rowcount controls what insert_result.rowcount returns (1=new row, 0=duplicate).
    """
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.rowcount = rowcount
    db.execute = AsyncMock(return_value=execute_result)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def mock_db():
    return _make_mock_db(rowcount=1)


@pytest.fixture
def auth_client(mock_db):
    from main import app

    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    app.dependency_overrides[get_db_session] = lambda: mock_db

    from fastapi.testclient import TestClient

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


# =============================================================================
# Task 2.1 — Webhook idempotency race fix
# =============================================================================


class TestWebhookIdempotencyRaceFix:
    """
    [14-P0-1] The idempotency row must only be committed AFTER business logic
    succeeds.  On failure the row must be deleted so Stripe can retry.
    """

    def test_idempotency_row_committed_on_success(self, mock_db):
        """
        On successful processing: INSERT row, run business logic, then commit.
        db.commit() must be called exactly once after business logic succeeds.
        """
        from main import app

        mock_event = {
            "id": "evt_idem_success",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"user_id": "user-payment-1", "tier": "pro"},
                    "customer": "cus_idem_ok",
                }
            },
        }
        mock_user = _make_mock_user()

        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        app.dependency_overrides[get_db_session] = lambda: mock_db

        from fastapi.testclient import TestClient

        client = TestClient(app)
        try:
            with (
                patch("api.v1.billing.UserRepository") as MockRepo,
                patch("api.v1.billing.StripeService") as MockStripe,
                patch("api.dependencies.invalidate_tier_cache", AsyncMock()),
            ):
                MockRepo.return_value = _make_mock_user_repo(mock_user)

                stripe_instance = MockStripe.return_value
                stripe_instance.is_configured = True
                stripe_instance.verify_webhook_signature = MagicMock(
                    return_value=mock_event
                )
                stripe_instance.handle_webhook_event = AsyncMock(
                    return_value={
                        "handled": True,
                        "action": "activate_subscription",
                        "user_id": "user-payment-1",
                        "tier": "pro",
                        "customer_id": "cus_idem_ok",
                    }
                )

                response = client.post(
                    f"{BASE_URL}/webhook",
                    content=b"{}",
                    headers={"stripe-signature": "t=1,v1=sig"},
                )

            assert response.status_code == 200
            # commit() must be called (idempotency row finalised)
            mock_db.commit.assert_awaited()
            # rollback() must NOT have been called
            mock_db.rollback.assert_not_awaited()
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db_session, None)

    def test_idempotency_row_deleted_on_processing_failure(self):
        """
        [14-P0-1 core fix] If handle_webhook_event raises, the idempotency row
        must be deleted (not committed) so Stripe's retry can reprocess.
        """
        from main import app

        mock_event = {
            "id": "evt_idem_fail",
            "type": "checkout.session.completed",
            "data": {"object": {}},
        }
        failure_db = _make_mock_db(rowcount=1)

        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        app.dependency_overrides[get_db_session] = lambda: failure_db

        from fastapi.testclient import TestClient

        client = TestClient(app)
        try:
            with patch("api.v1.billing.StripeService") as MockStripe:
                stripe_instance = MockStripe.return_value
                stripe_instance.is_configured = True
                stripe_instance.verify_webhook_signature = MagicMock(
                    return_value=mock_event
                )
                # Business logic fails
                stripe_instance.handle_webhook_event = AsyncMock(
                    side_effect=RuntimeError("DB connection lost")
                )

                response = client.post(
                    f"{BASE_URL}/webhook",
                    content=b"{}",
                    headers={"stripe-signature": "t=1,v1=sig"},
                )

            # Must still return 200 (so Stripe doesn't flood with retries)
            assert response.status_code == 200
            # rollback() must be called to undo the uncommitted INSERT
            failure_db.rollback.assert_awaited()
            # A second execute() call must be made to DELETE the guard row
            # (execute is called twice: once for INSERT, once for DELETE)
            assert failure_db.execute.await_count >= 2
            # Verify the DELETE was issued — TextClause objects store SQL as
            # their `text` attribute; str(clause) also renders the SQL text.
            delete_call_found = any(
                "DELETE" in str(call.args[0]).upper()
                for call in failure_db.execute.await_args_list
                if call.args
            )
            assert delete_call_found, "Expected DELETE statement in db.execute calls"
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db_session, None)

    def test_duplicate_webhook_skipped_without_processing(self):
        """
        If the INSERT returns rowcount=0 (event already processed), business
        logic must NOT run and 200 must be returned immediately.
        """
        from main import app

        mock_event = {
            "id": "evt_duplicate",
            "type": "checkout.session.completed",
            "data": {"object": {}},
        }
        dup_db = _make_mock_db(rowcount=0)  # Simulate duplicate

        app.dependency_overrides[get_current_user] = lambda: TEST_USER
        app.dependency_overrides[get_db_session] = lambda: dup_db

        from fastapi.testclient import TestClient

        client = TestClient(app)
        try:
            with patch("api.v1.billing.StripeService") as MockStripe:
                stripe_instance = MockStripe.return_value
                stripe_instance.is_configured = True
                stripe_instance.verify_webhook_signature = MagicMock(
                    return_value=mock_event
                )
                process_mock = AsyncMock(
                    return_value={"handled": False, "action": None, "user_id": None}
                )
                stripe_instance.handle_webhook_event = process_mock

                response = client.post(
                    f"{BASE_URL}/webhook",
                    content=b"{}",
                    headers={"stripe-signature": "t=1,v1=sig"},
                )

            assert response.status_code == 200
            assert response.json()["event_id"] == "evt_duplicate"
            # handle_webhook_event must NOT have been called for duplicates
            process_mock.assert_not_awaited()
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db_session, None)


# =============================================================================
# Task 2.3 — New webhook handlers
# =============================================================================


class TestHandleWebhookEventNewHandlers:
    """
    [14-P1-1, 14-P1-2] Tests for invoice.payment_succeeded, charge.refunded,
    charge.dispute.created handlers in StripeService.handle_webhook_event.
    """

    async def test_invoice_payment_succeeded_handled(self):
        """invoice.payment_succeeded must be handled and action=payment_succeeded."""
        from services.stripe_service import StripeService

        svc = StripeService.__new__(StripeService)
        svc._configured = True
        svc._db = None

        event = {
            "id": "evt_pay_ok",
            "type": "invoice.payment_succeeded",
            "data": {
                "object": {
                    "id": "in_abc123",
                    "customer": "cus_pay_ok",
                    "subscription": "sub_pay_ok",
                    "billing_reason": "subscription_cycle",
                }
            },
        }

        result = await svc.handle_webhook_event(event)

        assert result["handled"] is True
        assert result["action"] == "payment_succeeded"
        assert result["customer_id"] == "cus_pay_ok"
        assert result["subscription_id"] == "sub_pay_ok"
        assert result["billing_reason"] == "subscription_cycle"
        assert result["invoice_id"] == "in_abc123"

    async def test_charge_refunded_handled(self):
        """charge.refunded must be handled and action=charge_refunded."""
        from services.stripe_service import StripeService

        svc = StripeService.__new__(StripeService)
        svc._configured = True
        svc._db = None

        event = {
            "id": "evt_refund",
            "type": "charge.refunded",
            "data": {
                "object": {
                    "id": "ch_refund_123",
                    "customer": "cus_refund_cust",
                    "amount_refunded": 499,
                    "currency": "usd",
                }
            },
        }

        result = await svc.handle_webhook_event(event)

        assert result["handled"] is True
        assert result["action"] == "charge_refunded"
        assert result["customer_id"] == "cus_refund_cust"
        assert result["charge_id"] == "ch_refund_123"
        # Amount should be converted from cents to dollars
        assert result["amount_refunded"] == Decimal("4.99")
        assert result["currency"] == "USD"

    async def test_charge_dispute_created_handled(self):
        """charge.dispute.created must be handled and action=dispute_created."""
        from services.stripe_service import StripeService

        svc = StripeService.__new__(StripeService)
        svc._configured = True
        svc._db = None

        event = {
            "id": "evt_dispute",
            "type": "charge.dispute.created",
            "data": {
                "object": {
                    "id": "dp_dispute_001",
                    "charge": "ch_disputed_001",
                    "customer": None,  # Not always present on disputes
                    "reason": "fraudulent",
                    "amount": 1499,
                    "currency": "usd",
                }
            },
        }

        result = await svc.handle_webhook_event(event)

        assert result["handled"] is True
        assert result["action"] == "dispute_created"
        assert result["dispute_id"] == "dp_dispute_001"
        assert result["charge_id"] == "ch_disputed_001"
        assert result["dispute_reason"] == "fraudulent"
        # Amount converted from cents to dollars
        assert result["dispute_amount"] == Decimal("14.99")
        assert result["currency"] == "USD"

    async def test_unknown_event_not_handled(self):
        """Events with no handler must return handled=False."""
        from services.stripe_service import StripeService

        svc = StripeService.__new__(StripeService)
        svc._configured = True
        svc._db = None

        event = {
            "id": "evt_unknown",
            "type": "payment_method.attached",
            "data": {"object": {}},
        }

        result = await svc.handle_webhook_event(event)
        assert result["handled"] is False
        assert result["action"] is None


# =============================================================================
# Task 2.4 — Dunning reversibility via invoice.payment_succeeded
# =============================================================================


class TestApplyWebhookActionPaymentSucceeded:
    """
    [14-P1-4] invoice.payment_succeeded must restore the user's paid tier.
    """

    async def test_payment_succeeded_restores_tier(self):
        """
        apply_webhook_action with action=payment_succeeded must query Stripe
        for the subscription tier and restore it on the user record.
        """
        from services.stripe_service import apply_webhook_action

        mock_user = _make_mock_user(tier="free", customer_id="cus_restore")
        mock_repo = _make_mock_user_repo(mock_user)

        # Stripe returns an active subscription with tier=pro
        mock_subscription = MagicMock()
        mock_subscription.metadata = {"tier": "pro"}
        mock_subscription.status = "active"

        with (
            patch("services.stripe_service.asyncio.to_thread") as mock_to_thread,
            patch("api.dependencies.invalidate_tier_cache", AsyncMock()),
        ):
            # asyncio.to_thread wraps stripe.Subscription.retrieve
            mock_to_thread.return_value = mock_subscription

            result_data = {
                "handled": True,
                "action": "payment_succeeded",
                "user_id": "user-payment-1",
                "customer_id": "cus_restore",
                "subscription_id": "sub_restored",
                "invoice_id": "in_restored",
            }

            db = AsyncMock()
            applied = await apply_webhook_action(result_data, mock_repo, db=db)

        assert applied is True
        assert mock_user.subscription_tier == "pro"
        mock_repo.update.assert_awaited_once()

    async def test_payment_succeeded_skips_inactive_subscription(self):
        """
        If the Stripe subscription is not active/trialing, do not restore tier.
        Avoids re-activating a subscription that was also canceled.
        """
        from services.stripe_service import apply_webhook_action

        mock_user = _make_mock_user(tier="free", customer_id="cus_canceled")
        mock_repo = _make_mock_user_repo(mock_user)

        mock_subscription = MagicMock()
        mock_subscription.metadata = {"tier": "pro"}
        mock_subscription.status = "canceled"  # Terminal state

        with (
            patch("services.stripe_service.asyncio.to_thread") as mock_to_thread,
            patch("api.dependencies.invalidate_tier_cache", AsyncMock()),
        ):
            mock_to_thread.return_value = mock_subscription

            result_data = {
                "handled": True,
                "action": "payment_succeeded",
                "user_id": "user-payment-1",
                "customer_id": "cus_canceled",
                "subscription_id": "sub_canceled",
                "invoice_id": "in_canceled",
            }

            db = AsyncMock()
            applied = await apply_webhook_action(result_data, mock_repo, db=db)

        # Result is True (handled) but tier must NOT be changed
        assert applied is True
        # subscription_tier stays "free" because Stripe says status=canceled
        assert mock_user.subscription_tier == "free"
        mock_repo.update.assert_not_awaited()

    async def test_payment_succeeded_handles_stripe_lookup_failure(self):
        """
        If the Stripe API call to retrieve the subscription fails, log and
        continue without raising.  Do not crash the webhook handler.
        """
        import stripe

        from services.stripe_service import apply_webhook_action

        mock_user = _make_mock_user(tier="free", customer_id="cus_lookup_fail")
        mock_repo = _make_mock_user_repo(mock_user)

        with (
            patch("services.stripe_service.asyncio.to_thread") as mock_to_thread,
            patch("api.dependencies.invalidate_tier_cache", AsyncMock()),
        ):
            mock_to_thread.side_effect = stripe.StripeError("API timeout")

            result_data = {
                "handled": True,
                "action": "payment_succeeded",
                "user_id": "user-payment-1",
                "customer_id": "cus_lookup_fail",
                "subscription_id": "sub_timeout",
                "invoice_id": "in_timeout",
            }

            db = AsyncMock()
            # Must not raise
            applied = await apply_webhook_action(result_data, mock_repo, db=db)

        assert applied is True
        # No tier change since we couldn't determine it
        assert mock_user.subscription_tier == "free"


# =============================================================================
# Task 2.3 — apply_webhook_action: charge_refunded and dispute_created logging
# =============================================================================


class TestApplyWebhookActionNewActions:
    """
    charge_refunded and dispute_created should log structured warnings
    and return True without crashing.
    """

    async def test_charge_refunded_logs_and_returns_true(self):
        """charge_refunded must return True (handled) and not raise."""
        from services.stripe_service import apply_webhook_action

        mock_user = _make_mock_user(tier="pro")
        mock_repo = _make_mock_user_repo(mock_user)

        result_data = {
            "handled": True,
            "action": "charge_refunded",
            "user_id": "user-payment-1",
            "customer_id": "cus_refund",
            "charge_id": "ch_refund_001",
            "amount_refunded": Decimal("4.99"),
            "currency": "USD",
        }

        db = AsyncMock()
        applied = await apply_webhook_action(result_data, mock_repo, db=db)

        assert applied is True
        # Tier must NOT be automatically changed — ops review needed
        assert mock_user.subscription_tier == "pro"
        mock_repo.update.assert_not_awaited()

    async def test_dispute_created_logs_and_returns_true(self):
        """dispute_created must return True (handled) and not raise."""
        from services.stripe_service import apply_webhook_action

        mock_user = _make_mock_user(tier="business")
        mock_repo = _make_mock_user_repo(mock_user)

        result_data = {
            "handled": True,
            "action": "dispute_created",
            "user_id": "user-payment-1",
            "customer_id": "cus_dispute",
            "charge_id": "ch_disputed",
            "dispute_id": "dp_001",
            "dispute_reason": "fraudulent",
            "dispute_amount": Decimal("14.99"),
            "currency": "USD",
        }

        db = AsyncMock()
        applied = await apply_webhook_action(result_data, mock_repo, db=db)

        assert applied is True
        # Tier must NOT be automatically changed — ops review needed
        assert mock_user.subscription_tier == "business"
        mock_repo.update.assert_not_awaited()


# =============================================================================
# Task 2.5 — stripe.api_key set at module level
# =============================================================================


class TestStripeApiKeyModuleLevel:
    """
    [14-P1-3] stripe.api_key must be set once at import time, not per-request.
    StripeService.__init__ must NOT write to stripe.api_key.
    """

    def test_init_does_not_set_stripe_api_key(self):
        """
        Constructing a StripeService instance must not modify stripe.api_key.
        This verifies the fix: key is set at module level, not per-request.
        """
        import stripe

        from services.stripe_service import StripeService

        original_key = stripe.api_key
        try:
            # Override key to a known sentinel; init must NOT touch it
            stripe.api_key = "sk_test_sentinel_do_not_overwrite"

            with patch("services.stripe_service.settings") as mock_settings:
                mock_settings.stripe_secret_key = "sk_test_new_key_from_init"
                # Constructing service instance
                svc = StripeService()

            # Key must remain the sentinel — not replaced by the new key
            assert stripe.api_key == "sk_test_sentinel_do_not_overwrite", (
                "StripeService.__init__ must not mutate stripe.api_key. "
                "Set it once at module load time instead."
            )
        finally:
            stripe.api_key = original_key

    def test_unconfigured_service_is_not_configured(self):
        """
        StripeService without a key must report is_configured=False.
        """
        from services.stripe_service import StripeService

        with patch("services.stripe_service.settings") as mock_settings:
            mock_settings.stripe_secret_key = None
            svc = StripeService()

        assert svc.is_configured is False


# =============================================================================
# Task 2.6 — MRR prices externalized to settings
# =============================================================================


class TestMRRPricesFromSettings:
    """
    [14-P1-5] KPIReportService._calculate_mrr must use settings values
    rather than hardcoded 4.99 / 14.99 literals.
    """

    def test_mrr_uses_settings_prices(self):
        """
        _calculate_mrr must multiply by settings.stripe_mrr_price_pro and
        settings.stripe_mrr_price_business rather than hardcoded literals.
        """
        from services.kpi_report_service import KPIReportService

        with patch("services.kpi_report_service.settings") as mock_settings:
            mock_settings.stripe_mrr_price_pro = 9.99  # Override defaults
            mock_settings.stripe_mrr_price_business = 29.99

            mrr = KPIReportService._calculate_mrr({"pro": 10, "business": 5})

        # 10 × 9.99 + 5 × 29.99 = 99.90 + 149.95 = 249.85
        assert mrr == 249.85

    def test_mrr_default_prices_match_product_pricing(self):
        """
        Default prices must match the documented Pro/$4.99 + Business/$14.99
        product tier pricing.
        """
        from config.settings import settings

        assert settings.stripe_mrr_price_pro == pytest.approx(4.99)
        assert settings.stripe_mrr_price_business == pytest.approx(14.99)

    def test_mrr_calculation_no_subscribers(self):
        """Zero subscribers in all tiers should give MRR of 0.00."""
        from services.kpi_report_service import KPIReportService

        mrr = KPIReportService._calculate_mrr({"free": 100})
        assert mrr == 0.0

    def test_mrr_calculation_mixed(self):
        """MRR is computed as: pro_count * pro_price + business_count * biz_price."""
        from config.settings import settings
        from services.kpi_report_service import KPIReportService

        pro_count = 3
        biz_count = 2
        expected = round(
            pro_count * settings.stripe_mrr_price_pro
            + biz_count * settings.stripe_mrr_price_business,
            2,
        )
        mrr = KPIReportService._calculate_mrr({"pro": pro_count, "business": biz_count})
        assert mrr == expected


# =============================================================================
# Task 2.2 — Migration 056 SQL structure validation
# =============================================================================


class TestMigration056Structure:
    """
    Verify migration 056 file exists and contains the expected DDL.
    We don't execute it (no live DB in unit tests) but we validate the SQL.
    """

    def test_migration_056_file_exists(self):
        """Migration file must exist at the expected path."""
        import os

        migration_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "migrations",
            "056_stripe_customer_id_unique.sql",
        )
        assert os.path.isfile(migration_path), (
            "Migration 056_stripe_customer_id_unique.sql not found. "
            "Create it before marking Task 2.2 complete."
        )

    def test_migration_056_contains_unique_constraint(self):
        """Migration must add uq_users_stripe_customer_id UNIQUE constraint."""
        import os

        migration_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "migrations",
            "056_stripe_customer_id_unique.sql",
        )
        with open(migration_path) as f:
            sql = f.read()

        assert "uq_users_stripe_customer_id" in sql
        assert "UNIQUE" in sql.upper()
        assert "stripe_customer_id" in sql
        assert "neondb_owner" in sql

    def test_migration_056_is_safe_to_rerun(self):
        """Migration must guard against duplicate constraint creation (IF NOT EXISTS or DO block)."""
        import os

        migration_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "migrations",
            "056_stripe_customer_id_unique.sql",
        )
        with open(migration_path) as f:
            sql = f.read()

        # Safe-to-rerun pattern: either DO $$ BEGIN IF NOT EXISTS or similar guard
        has_guard = "IF NOT EXISTS" in sql.upper() or (
            "DO" in sql and "IF" in sql and "NOT EXISTS" in sql.upper()
        )
        assert (
            has_guard
        ), "Migration 056 must be safe to re-run (use IF NOT EXISTS or a DO block guard)"
