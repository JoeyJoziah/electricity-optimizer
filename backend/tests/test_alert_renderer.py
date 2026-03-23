"""Tests for the AlertRenderer service."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.alert_renderer import AlertRenderer
from services.alert_service import AlertThreshold, PriceAlert


def _make_alert(
    alert_type: str = "price_drop",
    current_price: float = 0.18,
    threshold: float = 0.20,
    region: str = "us_ct",
    supplier: str = "Eversource",
    timestamp: datetime = None,
    optimal_window_start: datetime = None,
    optimal_window_end: datetime = None,
    estimated_savings: float = None,
) -> PriceAlert:
    return PriceAlert(
        alert_type=alert_type,
        current_price=Decimal(str(current_price)),
        threshold=Decimal(str(threshold)) if threshold is not None else None,
        region=region,
        supplier=supplier,
        timestamp=timestamp or datetime(2024, 6, 15, 14, 30, tzinfo=UTC),
        optimal_window_start=optimal_window_start,
        optimal_window_end=optimal_window_end,
        estimated_savings=Decimal(str(estimated_savings))
        if estimated_savings is not None
        else None,
    )


def _make_threshold(currency: str = "USD") -> AlertThreshold:
    return AlertThreshold(
        user_id="user-1",
        email="test@example.com",
        price_below=Decimal("0.20"),
        region="us_ct",
        currency=currency,
    )


class TestGetAlertSubject:
    def setup_method(self):
        self.email_svc = MagicMock()
        self.renderer = AlertRenderer(self.email_svc)

    def test_price_drop_subject_includes_price(self):
        alert = _make_alert(alert_type="price_drop", current_price=0.18)
        subject = self.renderer.get_alert_subject(alert)
        assert "Price Drop Alert" in subject
        assert "0.18" in subject

    def test_price_spike_subject_includes_price(self):
        alert = _make_alert(alert_type="price_spike", current_price=0.45)
        subject = self.renderer.get_alert_subject(alert)
        assert "Price Spike Warning" in subject
        assert "0.45" in subject

    def test_optimal_window_subject_with_start_time(self):
        start = datetime(2024, 6, 15, 22, 0, tzinfo=UTC)
        alert = _make_alert(alert_type="optimal_window", optimal_window_start=start)
        subject = self.renderer.get_alert_subject(alert)
        assert "Optimal Usage Window" in subject
        assert "10:00 PM" in subject

    def test_optimal_window_subject_without_start_time(self):
        alert = _make_alert(alert_type="optimal_window")
        subject = self.renderer.get_alert_subject(alert)
        assert subject == "Optimal Usage Window Detected"

    def test_unknown_alert_type_returns_generic_subject(self):
        alert = _make_alert(alert_type="unknown_type")
        subject = self.renderer.get_alert_subject(alert)
        assert subject == "Electricity Price Alert"


class TestRenderAlertEmail:
    def setup_method(self):
        self.email_svc = MagicMock()
        self.threshold = _make_threshold()
        self.renderer = AlertRenderer(self.email_svc)

    def test_uses_template_when_available(self):
        self.email_svc.render_template.return_value = "<html>templated</html>"
        alert = _make_alert()
        html = self.renderer.render_alert_email(self.threshold, alert)
        assert html == "<html>templated</html>"
        self.email_svc.render_template.assert_called_once()

    def test_calls_template_with_correct_alert_type(self):
        self.email_svc.render_template.return_value = "<html></html>"
        alert = _make_alert(alert_type="price_spike", current_price=0.40)
        self.renderer.render_alert_email(self.threshold, alert)
        call_kwargs = self.email_svc.render_template.call_args[1]
        assert call_kwargs["alert_type"] == "price_spike"
        assert float(call_kwargs["current_price"]) == pytest.approx(0.40)

    def test_falls_back_to_inline_html_when_template_raises(self):
        self.email_svc.render_template.side_effect = FileNotFoundError("template not found")
        alert = _make_alert()
        html = self.renderer.render_alert_email(self.threshold, alert)
        assert "<h2>" in html
        assert "Eversource" in html

    def test_template_receives_formatted_timestamp(self):
        self.email_svc.render_template.return_value = "<html></html>"
        ts = datetime(2024, 6, 15, 14, 30, tzinfo=UTC)
        alert = _make_alert(timestamp=ts)
        self.renderer.render_alert_email(self.threshold, alert)
        call_kwargs = self.email_svc.render_template.call_args[1]
        assert "June 15, 2024" in call_kwargs["timestamp"]

    def test_template_receives_none_optimal_times_when_not_set(self):
        self.email_svc.render_template.return_value = "<html></html>"
        alert = _make_alert(alert_type="price_drop")
        self.renderer.render_alert_email(self.threshold, alert)
        call_kwargs = self.email_svc.render_template.call_args[1]
        assert call_kwargs["optimal_start"] is None
        assert call_kwargs["optimal_end"] is None

    def test_template_receives_formatted_optimal_times_when_set(self):
        self.email_svc.render_template.return_value = "<html></html>"
        start = datetime(2024, 6, 15, 22, 0, tzinfo=UTC)
        end = datetime(2024, 6, 16, 0, 0, tzinfo=UTC)
        alert = _make_alert(
            alert_type="optimal_window",
            optimal_window_start=start,
            optimal_window_end=end,
            estimated_savings=0.05,
        )
        self.renderer.render_alert_email(self.threshold, alert)
        call_kwargs = self.email_svc.render_template.call_args[1]
        assert call_kwargs["optimal_start"] == "10:00 PM"
        assert call_kwargs["optimal_end"] == "12:00 AM"
        assert call_kwargs["estimated_savings"] == "0.05"

    def test_region_formatted_for_display(self):
        self.email_svc.render_template.return_value = "<html></html>"
        alert = _make_alert(region="us_new_england")
        self.renderer.render_alert_email(self.threshold, alert)
        call_kwargs = self.email_svc.render_template.call_args[1]
        assert call_kwargs["region"] == "US NEW ENGLAND"


class TestRenderFallbackAlert:
    def setup_method(self):
        self.renderer = AlertRenderer(MagicMock())

    def test_price_drop_fallback_contains_key_info(self):
        alert = _make_alert(alert_type="price_drop", current_price=0.18, threshold=0.20)
        html = self.renderer.render_fallback_alert(alert, "USD")
        assert "Price Drop Alert" in html
        assert "0.18" in html
        assert "0.2" in html  # Decimal("0.20") renders as "0.2"
        assert "Eversource" in html

    def test_price_spike_fallback_contains_warning(self):
        alert = _make_alert(alert_type="price_spike", current_price=0.45)
        html = self.renderer.render_fallback_alert(alert, "USD")
        assert "Price Spike Warning" in html
        assert "0.45" in html

    def test_optimal_window_fallback_shows_times(self):
        start = datetime(2024, 6, 15, 22, 0, tzinfo=UTC)
        end = datetime(2024, 6, 16, 0, 0, tzinfo=UTC)
        alert = _make_alert(
            alert_type="optimal_window",
            optimal_window_start=start,
            optimal_window_end=end,
            estimated_savings=0.03,
        )
        html = self.renderer.render_fallback_alert(alert, "USD")
        assert "Optimal Usage Window" in html
        assert "10:00 PM" in html
        assert "12:00 AM" in html
        assert "0.03" in html

    def test_optimal_window_fallback_handles_none_times(self):
        alert = _make_alert(alert_type="optimal_window")
        html = self.renderer.render_fallback_alert(alert, "USD")
        assert "Optimal Usage Window" in html
        assert "N/A" in html

    def test_fallback_html_is_non_empty_string(self):
        alert = _make_alert()
        html = self.renderer.render_fallback_alert(alert, "USD")
        assert isinstance(html, str)
        assert len(html) > 50
