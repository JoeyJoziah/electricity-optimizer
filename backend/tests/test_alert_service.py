"""Tests for the Price Alert Service."""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, call, patch

from services.alert_service import AlertService, AlertThreshold, PriceAlert


class MockPrice:
    """Mock price object for testing."""

    def __init__(self, region, supplier, price_per_kwh, timestamp=None):
        self.region = region
        self.supplier = supplier
        self.price_per_kwh = Decimal(str(price_per_kwh))
        self.timestamp = timestamp or datetime.now(timezone.utc)


class TestAlertThreshold:
    def test_create_threshold(self):
        t = AlertThreshold(
            user_id="user-1",
            email="test@example.com",
            price_below=Decimal("0.20"),
            region="us_ct",
        )
        assert t.user_id == "user-1"
        assert t.price_below == Decimal("0.20")
        assert t.notify_optimal_windows is True

    def test_default_values(self):
        t = AlertThreshold(user_id="u1", email="a@b.com")
        assert t.price_below is None
        assert t.price_above is None
        assert t.region == ""
        assert t.currency == "USD"


class TestAlertService:
    def setup_method(self):
        self.mock_email = MagicMock()
        self.mock_email.send = AsyncMock(return_value=True)
        self.mock_email.render_template = MagicMock(return_value="<html>alert</html>")
        self.service = AlertService(email_service=self.mock_email)

    def test_check_thresholds_price_drop(self):
        prices = [MockPrice("us_ct", "Eversource Energy", 0.18)]
        thresholds = [
            AlertThreshold(
                user_id="u1",
                email="test@example.com",
                price_below=Decimal("0.20"),
                region="us_ct",
            )
        ]

        triggered = self.service.check_thresholds(prices, thresholds)
        assert len(triggered) == 1
        threshold, alert = triggered[0]
        assert alert.alert_type == "price_drop"
        assert alert.current_price == Decimal("0.18")

    def test_check_thresholds_price_spike(self):
        prices = [MockPrice("us_ct", "Eversource Energy", 0.35)]
        thresholds = [
            AlertThreshold(
                user_id="u1",
                email="test@example.com",
                price_above=Decimal("0.30"),
                region="us_ct",
            )
        ]

        triggered = self.service.check_thresholds(prices, thresholds)
        assert len(triggered) == 1
        _, alert = triggered[0]
        assert alert.alert_type == "price_spike"

    def test_check_thresholds_no_trigger(self):
        prices = [MockPrice("us_ct", "Eversource Energy", 0.25)]
        thresholds = [
            AlertThreshold(
                user_id="u1",
                email="test@example.com",
                price_below=Decimal("0.20"),
                region="us_ct",
            )
        ]

        triggered = self.service.check_thresholds(prices, thresholds)
        assert len(triggered) == 0

    def test_check_thresholds_region_mismatch(self):
        prices = [MockPrice("us_ny", "ConEd", 0.15)]
        thresholds = [
            AlertThreshold(
                user_id="u1",
                email="test@example.com",
                price_below=Decimal("0.20"),
                region="us_ct",
            )
        ]

        triggered = self.service.check_thresholds(prices, thresholds)
        assert len(triggered) == 0

    def test_check_optimal_windows(self):
        now = datetime.now(timezone.utc)
        # Create 6 hours of prices: first 2 cheap, rest expensive
        prices = [
            MockPrice("us_ct", "Eversource", 0.12, now + timedelta(hours=0)),
            MockPrice("us_ct", "Eversource", 0.13, now + timedelta(hours=1)),
            MockPrice("us_ct", "Eversource", 0.28, now + timedelta(hours=2)),
            MockPrice("us_ct", "Eversource", 0.30, now + timedelta(hours=3)),
            MockPrice("us_ct", "Eversource", 0.29, now + timedelta(hours=4)),
            MockPrice("us_ct", "Eversource", 0.27, now + timedelta(hours=5)),
        ]

        thresholds = [
            AlertThreshold(
                user_id="u1",
                email="test@example.com",
                notify_optimal_windows=True,
                region="us_ct",
            )
        ]

        triggered = self.service.check_optimal_windows(prices, thresholds, window_hours=2)
        assert len(triggered) == 1
        _, alert = triggered[0]
        assert alert.alert_type == "optimal_window"
        assert alert.current_price == Decimal("0.125")  # avg of 0.12, 0.13

    def test_check_optimal_windows_not_opted_in(self):
        prices = [MockPrice("us_ct", "Eversource", 0.12) for _ in range(6)]
        thresholds = [
            AlertThreshold(
                user_id="u1",
                email="test@example.com",
                notify_optimal_windows=False,
            )
        ]

        triggered = self.service.check_optimal_windows(prices, thresholds)
        assert len(triggered) == 0

    @pytest.mark.asyncio
    async def test_send_alerts(self):
        threshold = AlertThreshold(user_id="u1", email="test@example.com")
        alert = PriceAlert(
            alert_type="price_drop",
            current_price=Decimal("0.18"),
            threshold=Decimal("0.20"),
            region="us_ct",
            supplier="Eversource Energy",
            timestamp=datetime.now(timezone.utc),
        )

        sent = await self.service.send_alerts([(threshold, alert)])
        assert sum(sent) == 1
        self.mock_email.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_alerts_email_failure(self):
        self.mock_email.send = AsyncMock(return_value=False)
        threshold = AlertThreshold(user_id="u1", email="test@example.com")
        alert = PriceAlert(
            alert_type="price_spike",
            current_price=Decimal("0.35"),
            threshold=Decimal("0.30"),
            region="us_ct",
            supplier="Eversource Energy",
            timestamp=datetime.now(timezone.utc),
        )

        sent = await self.service.send_alerts([(threshold, alert)])
        assert sum(sent) == 0

    def test_get_alert_subject_price_drop(self):
        alert = PriceAlert(
            alert_type="price_drop",
            current_price=Decimal("0.18"),
            threshold=Decimal("0.20"),
            region="us_ct",
            supplier="Eversource",
            timestamp=datetime.now(timezone.utc),
        )
        subject = self.service._get_alert_subject(alert)
        assert "Price Drop" in subject
        assert "0.18" in subject

    def test_get_alert_subject_optimal_window(self):
        alert = PriceAlert(
            alert_type="optimal_window",
            current_price=Decimal("0.15"),
            threshold=None,
            region="us_ct",
            supplier="Eversource",
            timestamp=datetime.now(timezone.utc),
            optimal_window_start=datetime(2026, 2, 12, 2, 0, tzinfo=timezone.utc),
        )
        subject = self.service._get_alert_subject(alert)
        assert "Optimal" in subject


# =============================================================================
# TestAlertServiceWithDispatcher — dispatcher integration
# =============================================================================


class TestAlertServiceWithDispatcher:
    """Tests for AlertService.send_alerts() when a NotificationDispatcher is wired in."""

    def _make_threshold(self, user_id="u1", email="test@example.com", region="us_ct"):
        return AlertThreshold(
            user_id=user_id,
            email=email,
            price_below=Decimal("0.20"),
            region=region,
        )

    def _make_alert(self, alert_type="price_drop", region="us_ct"):
        return PriceAlert(
            alert_type=alert_type,
            current_price=Decimal("0.18"),
            threshold=Decimal("0.20"),
            region=region,
            supplier="Eversource Energy",
            timestamp=datetime.now(timezone.utc),
        )

    def _make_dispatcher(self, send_return=None):
        """Build a mock dispatcher; send_return defaults to all-channel success."""
        if send_return is None:
            send_return = {
                "skipped_dedup": False,
                "channels": {"in_app": True, "push": True, "email": True},
            }
        dispatcher = MagicMock()
        dispatcher.send = AsyncMock(return_value=send_return)
        return dispatcher

    @pytest.mark.asyncio
    async def test_dispatcher_called_instead_of_email_service(self):
        """When a dispatcher is configured, it should be called instead of the email service."""
        mock_email = MagicMock()
        mock_email.send = AsyncMock(return_value=True)
        mock_email.render_template = MagicMock(return_value="<html>alert</html>")
        dispatcher = self._make_dispatcher()

        service = AlertService(email_service=mock_email, dispatcher=dispatcher)
        threshold = self._make_threshold()
        alert = self._make_alert()

        sent = await service.send_alerts([(threshold, alert)])

        assert sum(sent) == 1
        dispatcher.send.assert_awaited_once()
        # EmailService.send should NOT be called directly when dispatcher succeeds
        mock_email.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatcher_send_uses_all_three_channels(self):
        """send_alerts() via dispatcher should request IN_APP, PUSH, and EMAIL channels."""
        from services.notification_dispatcher import NotificationChannel

        mock_email = MagicMock()
        mock_email.render_template = MagicMock(return_value="<html>alert</html>")
        dispatcher = self._make_dispatcher()

        service = AlertService(email_service=mock_email, dispatcher=dispatcher)
        threshold = self._make_threshold()
        alert = self._make_alert()

        await service.send_alerts([(threshold, alert)])

        call_kwargs = dispatcher.send.call_args.kwargs
        channels = call_kwargs.get("channels", [])
        assert NotificationChannel.IN_APP in channels
        assert NotificationChannel.PUSH in channels
        assert NotificationChannel.EMAIL in channels

    @pytest.mark.asyncio
    async def test_dispatcher_passes_email_address(self):
        """The user's email should be forwarded as email_to to the dispatcher."""
        mock_email = MagicMock()
        mock_email.render_template = MagicMock(return_value="<html>alert</html>")
        dispatcher = self._make_dispatcher()

        service = AlertService(email_service=mock_email, dispatcher=dispatcher)
        threshold = self._make_threshold(email="user@example.com")
        alert = self._make_alert()

        await service.send_alerts([(threshold, alert)])

        call_kwargs = dispatcher.send.call_args.kwargs
        assert call_kwargs.get("email_to") == "user@example.com"

    @pytest.mark.asyncio
    async def test_dispatcher_dedup_skipped_counts_as_not_sent(self):
        """When the dispatcher deduplicates a send, the alert should NOT count as sent."""
        mock_email = MagicMock()
        mock_email.render_template = MagicMock(return_value="<html>alert</html>")
        dispatcher = self._make_dispatcher(
            send_return={"skipped_dedup": True, "channels": {}}
        )

        service = AlertService(email_service=mock_email, dispatcher=dispatcher)
        threshold = self._make_threshold()
        alert = self._make_alert()

        sent = await service.send_alerts([(threshold, alert)])

        assert sum(sent) == 0

    @pytest.mark.asyncio
    async def test_dispatcher_failure_falls_back_to_email_service(self):
        """When the dispatcher raises, the service should fall back to direct email."""
        mock_email = MagicMock()
        mock_email.send = AsyncMock(return_value=True)
        mock_email.render_template = MagicMock(return_value="<html>alert</html>")

        dispatcher = MagicMock()
        dispatcher.send = AsyncMock(side_effect=Exception("Dispatcher unavailable"))

        service = AlertService(email_service=mock_email, dispatcher=dispatcher)
        threshold = self._make_threshold()
        alert = self._make_alert()

        sent = await service.send_alerts([(threshold, alert)])

        # Fallback email send succeeded → counted as sent
        assert sum(sent) == 1
        mock_email.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_dispatcher_uses_legacy_email_path(self):
        """When no dispatcher is provided, direct EmailService.send() should be used."""
        mock_email = MagicMock()
        mock_email.send = AsyncMock(return_value=True)
        mock_email.render_template = MagicMock(return_value="<html>alert</html>")

        service = AlertService(email_service=mock_email)  # no dispatcher
        threshold = self._make_threshold()
        alert = self._make_alert()

        sent = await service.send_alerts([(threshold, alert)])

        assert sum(sent) == 1
        mock_email.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatcher_all_channels_fail_counts_zero(self):
        """When all dispatcher channels return False, the alert should not count as sent."""
        mock_email = MagicMock()
        mock_email.render_template = MagicMock(return_value="<html>alert</html>")
        dispatcher = self._make_dispatcher(
            send_return={
                "skipped_dedup": False,
                "channels": {"in_app": False, "push": False, "email": False},
            }
        )

        service = AlertService(email_service=mock_email, dispatcher=dispatcher)
        threshold = self._make_threshold()
        alert = self._make_alert()

        sent = await service.send_alerts([(threshold, alert)])

        assert sum(sent) == 0

    @pytest.mark.asyncio
    async def test_dispatcher_dedup_key_includes_user_alert_and_region(self):
        """The dedup_key should embed user_id, alert_type, and region."""
        mock_email = MagicMock()
        mock_email.render_template = MagicMock(return_value="<html>alert</html>")
        dispatcher = self._make_dispatcher()

        service = AlertService(email_service=mock_email, dispatcher=dispatcher)
        threshold = self._make_threshold(user_id="user-42", region="us_ma")
        alert = self._make_alert(alert_type="price_spike", region="us_ma")

        await service.send_alerts([(threshold, alert)])

        call_kwargs = dispatcher.send.call_args.kwargs
        dedup_key = call_kwargs.get("dedup_key", "")
        assert "user-42" in dedup_key
        assert "price_spike" in dedup_key
        assert "us_ma" in dedup_key
