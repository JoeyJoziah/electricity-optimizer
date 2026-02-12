"""Tests for the Price Alert Service."""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

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
        assert t.region == "us_ct"
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
        assert sent == 1
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
        assert sent == 0

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
