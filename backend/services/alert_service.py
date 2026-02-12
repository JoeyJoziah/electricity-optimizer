"""
Price Alert Service

Monitors electricity prices and sends notifications when prices
drop below user-defined thresholds or enter optimal usage windows.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Optional

import structlog

from services.email_service import EmailService

logger = structlog.get_logger(__name__)


class AlertThreshold:
    """Represents a user's price alert configuration."""

    def __init__(
        self,
        user_id: str,
        email: str,
        price_below: Optional[Decimal] = None,
        price_above: Optional[Decimal] = None,
        notify_optimal_windows: bool = True,
        region: str = "us_ct",
        currency: str = "USD",
    ):
        self.user_id = user_id
        self.email = email
        self.price_below = price_below
        self.price_above = price_above
        self.notify_optimal_windows = notify_optimal_windows
        self.region = region
        self.currency = currency


class PriceAlert:
    """A triggered price alert."""

    def __init__(
        self,
        alert_type: str,
        current_price: Decimal,
        threshold: Optional[Decimal],
        region: str,
        supplier: str,
        timestamp: datetime,
        optimal_window_start: Optional[datetime] = None,
        optimal_window_end: Optional[datetime] = None,
        estimated_savings: Optional[Decimal] = None,
    ):
        self.alert_type = alert_type
        self.current_price = current_price
        self.threshold = threshold
        self.region = region
        self.supplier = supplier
        self.timestamp = timestamp
        self.optimal_window_start = optimal_window_start
        self.optimal_window_end = optimal_window_end
        self.estimated_savings = estimated_savings


class AlertService:
    """
    Service for checking price thresholds and sending alerts.

    Usage:
        service = AlertService()
        alerts = service.check_thresholds(current_prices, user_thresholds)
        await service.send_alerts(alerts)
    """

    def __init__(self, email_service: Optional[EmailService] = None):
        self._email_service = email_service or EmailService()

    def check_thresholds(
        self,
        prices: list,
        thresholds: List[AlertThreshold],
    ) -> List[tuple]:
        """
        Check current prices against user thresholds.

        Args:
            prices: List of current Price objects (region, supplier, price_per_kwh, timestamp)
            thresholds: List of user alert thresholds

        Returns:
            List of (AlertThreshold, PriceAlert) tuples for triggered alerts
        """
        triggered = []

        for threshold in thresholds:
            for price in prices:
                price_region = getattr(price, "region", None)
                if price_region and price_region != threshold.region:
                    continue

                current = Decimal(str(price.price_per_kwh))

                # Check price below threshold
                if threshold.price_below and current <= threshold.price_below:
                    alert = PriceAlert(
                        alert_type="price_drop",
                        current_price=current,
                        threshold=threshold.price_below,
                        region=threshold.region,
                        supplier=getattr(price, "supplier", "Unknown"),
                        timestamp=getattr(price, "timestamp", datetime.now(timezone.utc)),
                    )
                    triggered.append((threshold, alert))

                # Check price above threshold (spike warning)
                if threshold.price_above and current >= threshold.price_above:
                    alert = PriceAlert(
                        alert_type="price_spike",
                        current_price=current,
                        threshold=threshold.price_above,
                        region=threshold.region,
                        supplier=getattr(price, "supplier", "Unknown"),
                        timestamp=getattr(price, "timestamp", datetime.now(timezone.utc)),
                    )
                    triggered.append((threshold, alert))

        return triggered

    def check_optimal_windows(
        self,
        forecast_prices: list,
        thresholds: List[AlertThreshold],
        window_hours: int = 2,
    ) -> List[tuple]:
        """
        Identify optimal usage windows from forecast data and match to interested users.

        Args:
            forecast_prices: List of forecasted Price objects sorted by time
            thresholds: User thresholds that opted into optimal window alerts
            window_hours: Duration of optimal window to find

        Returns:
            List of (AlertThreshold, PriceAlert) tuples
        """
        if not forecast_prices or len(forecast_prices) < window_hours:
            return []

        # Find the cheapest consecutive window
        best_start = 0
        best_avg = Decimal("999999")

        for i in range(len(forecast_prices) - window_hours + 1):
            window = forecast_prices[i : i + window_hours]
            avg = sum(Decimal(str(p.price_per_kwh)) for p in window) / window_hours
            if avg < best_avg:
                best_avg = avg
                best_start = i

        window_start_price = forecast_prices[best_start]
        window_end_price = forecast_prices[best_start + window_hours - 1]

        # Calculate average price across all hours for savings estimate
        all_avg = sum(Decimal(str(p.price_per_kwh)) for p in forecast_prices) / len(
            forecast_prices
        )
        estimated_savings = (all_avg - best_avg) * window_hours

        triggered = []
        for threshold in thresholds:
            if not threshold.notify_optimal_windows:
                continue

            alert = PriceAlert(
                alert_type="optimal_window",
                current_price=best_avg,
                threshold=None,
                region=threshold.region,
                supplier=getattr(window_start_price, "supplier", "Unknown"),
                timestamp=datetime.now(timezone.utc),
                optimal_window_start=getattr(
                    window_start_price, "timestamp", datetime.now(timezone.utc)
                ),
                optimal_window_end=getattr(
                    window_end_price, "timestamp", datetime.now(timezone.utc)
                )
                + timedelta(hours=1),
                estimated_savings=max(estimated_savings, Decimal("0")),
            )
            triggered.append((threshold, alert))

        return triggered

    async def send_alerts(self, triggered: List[tuple]) -> int:
        """
        Send email alerts for triggered thresholds.

        Args:
            triggered: List of (AlertThreshold, PriceAlert) tuples

        Returns:
            Number of alerts successfully sent
        """
        sent = 0
        for threshold, alert in triggered:
            try:
                html = self._render_alert_email(threshold, alert)
                subject = self._get_alert_subject(alert)
                success = await self._email_service.send(
                    to=threshold.email,
                    subject=subject,
                    html_body=html,
                )
                if success:
                    sent += 1
                    logger.info(
                        "alert_sent",
                        user_id=threshold.user_id,
                        alert_type=alert.alert_type,
                        price=str(alert.current_price),
                    )
            except Exception as e:
                logger.error(
                    "alert_send_failed",
                    user_id=threshold.user_id,
                    error=str(e),
                )
        return sent

    def _get_alert_subject(self, alert: PriceAlert) -> str:
        if alert.alert_type == "price_drop":
            return f"Price Drop Alert: ${alert.current_price}/kWh"
        elif alert.alert_type == "price_spike":
            return f"Price Spike Warning: ${alert.current_price}/kWh"
        elif alert.alert_type == "optimal_window":
            start = alert.optimal_window_start
            if start:
                time_str = start.strftime("%I:%M %p")
                return f"Optimal Usage Window: Starting at {time_str}"
            return "Optimal Usage Window Detected"
        return "Electricity Price Alert"

    def _render_alert_email(self, threshold: AlertThreshold, alert: PriceAlert) -> str:
        try:
            return self._email_service.render_template(
                "price_alert.html",
                alert_type=alert.alert_type,
                current_price=str(alert.current_price),
                threshold=str(alert.threshold) if alert.threshold else None,
                region=alert.region.upper().replace("_", " "),
                supplier=alert.supplier,
                timestamp=alert.timestamp.strftime("%B %d, %Y at %I:%M %p UTC"),
                optimal_start=(
                    alert.optimal_window_start.strftime("%I:%M %p")
                    if alert.optimal_window_start
                    else None
                ),
                optimal_end=(
                    alert.optimal_window_end.strftime("%I:%M %p")
                    if alert.optimal_window_end
                    else None
                ),
                estimated_savings=(
                    str(alert.estimated_savings) if alert.estimated_savings else None
                ),
                currency=threshold.currency,
            )
        except Exception:
            # Fallback to plain HTML if template not found
            return self._render_fallback_alert(alert, threshold.currency)

    def _render_fallback_alert(self, alert: PriceAlert, currency: str) -> str:
        if alert.alert_type == "optimal_window":
            return f"""
            <h2>Optimal Usage Window Detected</h2>
            <p>Average price: <strong>${alert.current_price}/kWh</strong></p>
            <p>Window: {alert.optimal_window_start.strftime('%I:%M %p') if alert.optimal_window_start else 'N/A'}
            - {alert.optimal_window_end.strftime('%I:%M %p') if alert.optimal_window_end else 'N/A'}</p>
            {f'<p>Estimated savings: ${alert.estimated_savings}/kWh vs average</p>' if alert.estimated_savings else ''}
            <p>Region: {alert.region} | Supplier: {alert.supplier}</p>
            """
        return f"""
        <h2>{'Price Drop Alert' if alert.alert_type == 'price_drop' else 'Price Spike Warning'}</h2>
        <p>Current price: <strong>${alert.current_price}/kWh</strong></p>
        <p>Your threshold: ${alert.threshold}/kWh</p>
        <p>Region: {alert.region} | Supplier: {alert.supplier}</p>
        <p>Time: {alert.timestamp.strftime('%B %d, %Y at %I:%M %p UTC')}</p>
        """
