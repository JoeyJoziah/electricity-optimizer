"""
Alert Email Renderer

Presentation-layer concern: rendering price alert notifications into HTML.
Extracted from AlertService so that email rendering logic lives separately
from alert business logic.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.alert_service import AlertThreshold, PriceAlert


class AlertRenderer:
    """
    Renders price alert notifications as HTML email bodies.

    Accepts the same ``email_service`` dependency as ``AlertService`` because
    the primary rendering path delegates to ``EmailService.render_template``
    for template-based HTML.  The fallback path produces inline HTML directly
    with no external dependency.
    """

    def __init__(self, email_service) -> None:
        self._email_service = email_service

    # ------------------------------------------------------------------
    # Public rendering interface
    # ------------------------------------------------------------------

    def get_alert_subject(self, alert: "PriceAlert") -> str:
        """Return an appropriate email subject line for the given alert."""
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

    def render_alert_email(
        self,
        threshold: "AlertThreshold",
        alert: "PriceAlert",
    ) -> str:
        """
        Render the alert as an HTML email body.

        Attempts to use the configured email template (``price_alert.html``).
        Falls back to inline HTML when the template is unavailable.
        """
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
            return self.render_fallback_alert(alert, threshold.currency)

    def render_fallback_alert(self, alert: "PriceAlert", currency: str) -> str:
        """Render a minimal inline-HTML email body when the template is missing."""
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
