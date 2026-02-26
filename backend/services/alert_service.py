"""
Price Alert Service

Monitors electricity prices and sends notifications when prices
drop below user-defined thresholds or enter optimal usage windows.

DB-backed methods (get_user_alerts, get_alert_history, create_alert,
update_alert, delete_alert, record_triggered_alert) persist alert
configurations to ``price_alert_configs`` and trigger events to
``alert_history`` (migration 014).
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
        region: str = "",
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

    # =========================================================================
    # DB-backed CRUD methods (require db: AsyncSession)
    # =========================================================================

    async def get_user_alerts(
        self,
        user_id: str,
        db: AsyncSession,
    ) -> List[Dict[str, Any]]:
        """
        Return all price alert configurations for a user (active and inactive).

        Args:
            user_id: UUID string of the authenticated user.
            db:      Async SQLAlchemy session.

        Returns:
            List of alert config dicts ordered by created_at DESC.
        """
        result = await db.execute(
            text("""
                SELECT id, user_id, region, currency,
                       price_below, price_above, notify_optimal_windows,
                       is_active, created_at, updated_at
                FROM price_alert_configs
                WHERE user_id = :user_id
                ORDER BY created_at DESC
            """),
            {"user_id": user_id},
        )
        rows = result.mappings().all()
        return [self._config_row_to_dict(row) for row in rows]

    async def get_alert_history(
        self,
        user_id: str,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        Return a paginated list of alert trigger history for a user.

        Args:
            user_id:   UUID string of the authenticated user.
            db:        Async SQLAlchemy session.
            page:      1-based page number.
            page_size: Records per page (clamped 1-100).

        Returns:
            Dict with keys items, total, page, page_size, pages.
        """
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        count_result = await db.execute(
            text("SELECT COUNT(*) FROM alert_history WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        total = count_result.scalar() or 0

        rows_result = await db.execute(
            text("""
                SELECT id, user_id, alert_config_id, alert_type,
                       current_price, threshold, region, supplier, currency,
                       optimal_window_start, optimal_window_end, estimated_savings,
                       triggered_at, email_sent
                FROM alert_history
                WHERE user_id = :user_id
                ORDER BY triggered_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"user_id": user_id, "limit": page_size, "offset": offset},
        )
        rows = rows_result.mappings().all()
        items = [self._history_row_to_dict(row) for row in rows]
        pages = max(1, (total + page_size - 1) // page_size)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": pages,
        }

    async def create_alert(
        self,
        user_id: str,
        db: AsyncSession,
        region: str,
        currency: str = "USD",
        price_below: Optional[Decimal] = None,
        price_above: Optional[Decimal] = None,
        notify_optimal_windows: bool = True,
    ) -> Dict[str, Any]:
        """
        Insert a new price alert configuration and return it.

        Args:
            user_id:                UUID string of the user.
            db:                     Async SQLAlchemy session.
            region:                 Region code (default 'us_ct').
            currency:               ISO 4217 currency code (default 'USD').
            price_below:            Alert threshold for price drops.
            price_above:            Alert threshold for price spikes.
            notify_optimal_windows: Whether to notify about optimal usage windows.

        Returns:
            Dict representation of the created config row.

        Raises:
            ValueError: If neither price_below nor price_above nor
                        notify_optimal_windows is specified.
        """
        if price_below is None and price_above is None and not notify_optimal_windows:
            raise ValueError(
                "At least one of price_below, price_above, or notify_optimal_windows "
                "must be specified."
            )

        result = await db.execute(
            text("""
                INSERT INTO price_alert_configs
                    (id, user_id, region, currency,
                     price_below, price_above, notify_optimal_windows)
                VALUES
                    (:id, :user_id, :region, :currency,
                     :price_below, :price_above, :notify_optimal_windows)
                RETURNING id, user_id, region, currency,
                          price_below, price_above, notify_optimal_windows,
                          is_active, created_at, updated_at
            """),
            {
                "id": str(uuid4()),
                "user_id": user_id,
                "region": region,
                "currency": currency,
                "price_below": str(price_below) if price_below is not None else None,
                "price_above": str(price_above) if price_above is not None else None,
                "notify_optimal_windows": notify_optimal_windows,
            },
        )
        await db.commit()
        row = result.mappings().first()
        logger.info("alert_created", user_id=user_id, alert_id=str(row["id"]))
        return self._config_row_to_dict(row)

    async def update_alert(
        self,
        user_id: str,
        alert_id: str,
        db: AsyncSession,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing alert configuration owned by the user.

        Permitted update keys: region, currency, price_below, price_above,
        notify_optimal_windows, is_active.  Unknown keys are ignored.

        Args:
            user_id:  UUID string of the authenticated user (ownership check).
            alert_id: UUID string of the alert config to update.
            db:       Async SQLAlchemy session.
            updates:  Dict of field->value pairs to update.

        Returns:
            Updated alert dict, or None if the alert was not found / not owned.
        """
        allowed_fields = {
            "region", "currency", "price_below", "price_above",
            "notify_optimal_windows", "is_active",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed_fields}
        if not filtered:
            # No valid fields to update — return existing record unchanged
            rows = await db.execute(
                text("""
                    SELECT id, user_id, region, currency,
                           price_below, price_above, notify_optimal_windows,
                           is_active, created_at, updated_at
                    FROM price_alert_configs
                    WHERE id = :id AND user_id = :user_id
                """),
                {"id": alert_id, "user_id": user_id},
            )
            row = rows.mappings().first()
            return self._config_row_to_dict(row) if row else None

        set_clauses = ", ".join(f"{k} = :{k}" for k in filtered)
        params: Dict[str, Any] = {**filtered, "id": alert_id, "user_id": user_id}

        # Normalise Decimal values to strings for asyncpg
        for key in ("price_below", "price_above"):
            if key in params and params[key] is not None:
                params[key] = str(params[key])

        result = await db.execute(
            text(f"""
                UPDATE price_alert_configs
                SET {set_clauses}, updated_at = NOW()
                WHERE id = :id AND user_id = :user_id
                RETURNING id, user_id, region, currency,
                          price_below, price_above, notify_optimal_windows,
                          is_active, created_at, updated_at
            """),
            params,
        )
        await db.commit()
        row = result.mappings().first()
        if row:
            logger.info("alert_updated", user_id=user_id, alert_id=alert_id)
        return self._config_row_to_dict(row) if row else None

    async def delete_alert(
        self,
        user_id: str,
        alert_id: str,
        db: AsyncSession,
    ) -> bool:
        """
        Delete a price alert configuration owned by the user.

        Args:
            user_id:  UUID string of the authenticated user (ownership check).
            alert_id: UUID string of the alert config to delete.
            db:       Async SQLAlchemy session.

        Returns:
            True if the alert was deleted, False if it was not found.
        """
        result = await db.execute(
            text("""
                DELETE FROM price_alert_configs
                WHERE id = :id AND user_id = :user_id
            """),
            {"id": alert_id, "user_id": user_id},
        )
        await db.commit()
        deleted = result.rowcount > 0
        if deleted:
            logger.info("alert_deleted", user_id=user_id, alert_id=alert_id)
        return deleted

    async def record_triggered_alert(
        self,
        user_id: str,
        alert: "PriceAlert",
        db: AsyncSession,
        alert_config_id: Optional[str] = None,
        email_sent: bool = False,
        currency: str = "USD",
    ) -> Dict[str, Any]:
        """
        Persist a triggered alert event to alert_history.

        Args:
            user_id:         UUID string of the user.
            alert:           The PriceAlert that fired.
            db:              Async SQLAlchemy session.
            alert_config_id: Optional UUID of the originating config row.
            email_sent:      Whether the notification email was sent successfully.
            currency:        Currency code for the record (default 'USD').

        Returns:
            Dict representation of the inserted history row.
        """
        result = await db.execute(
            text("""
                INSERT INTO alert_history
                    (id, user_id, alert_config_id, alert_type,
                     current_price, threshold, region, supplier, currency,
                     optimal_window_start, optimal_window_end, estimated_savings,
                     triggered_at, email_sent)
                VALUES
                    (:id, :user_id, :alert_config_id, :alert_type,
                     :current_price, :threshold, :region, :supplier, :currency,
                     :optimal_window_start, :optimal_window_end, :estimated_savings,
                     :triggered_at, :email_sent)
                RETURNING id, user_id, alert_config_id, alert_type,
                          current_price, threshold, region, supplier, currency,
                          optimal_window_start, optimal_window_end, estimated_savings,
                          triggered_at, email_sent
            """),
            {
                "id": str(uuid4()),
                "user_id": user_id,
                "alert_config_id": alert_config_id,
                "alert_type": alert.alert_type,
                "current_price": str(alert.current_price),
                "threshold": str(alert.threshold) if alert.threshold is not None else None,
                "region": alert.region,
                "supplier": alert.supplier,
                "currency": currency,
                "optimal_window_start": alert.optimal_window_start,
                "optimal_window_end": alert.optimal_window_end,
                "estimated_savings": (
                    str(alert.estimated_savings) if alert.estimated_savings is not None else None
                ),
                "triggered_at": alert.timestamp,
                "email_sent": email_sent,
            },
        )
        await db.commit()
        row = result.mappings().first()
        return self._history_row_to_dict(row)

    # =========================================================================
    # Private serialisation helpers
    # =========================================================================

    @staticmethod
    def _config_row_to_dict(row) -> Dict[str, Any]:
        """Serialise a price_alert_configs row mapping to a plain dict."""
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "region": row["region"],
            "currency": row["currency"],
            "price_below": float(row["price_below"]) if row["price_below"] is not None else None,
            "price_above": float(row["price_above"]) if row["price_above"] is not None else None,
            "notify_optimal_windows": row["notify_optimal_windows"],
            "is_active": row["is_active"],
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        }

    @staticmethod
    def _history_row_to_dict(row) -> Dict[str, Any]:
        """Serialise an alert_history row mapping to a plain dict."""
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "alert_config_id": (
                str(row["alert_config_id"]) if row["alert_config_id"] else None
            ),
            "alert_type": row["alert_type"],
            "current_price": float(row["current_price"]),
            "threshold": float(row["threshold"]) if row["threshold"] is not None else None,
            "region": row["region"],
            "supplier": row["supplier"],
            "currency": row["currency"],
            "optimal_window_start": (
                row["optimal_window_start"].isoformat()
                if row.get("optimal_window_start")
                else None
            ),
            "optimal_window_end": (
                row["optimal_window_end"].isoformat()
                if row.get("optimal_window_end")
                else None
            ),
            "estimated_savings": (
                float(row["estimated_savings"]) if row["estimated_savings"] is not None else None
            ),
            "triggered_at": (
                row["triggered_at"].isoformat() if row.get("triggered_at") else None
            ),
            "email_sent": row["email_sent"],
        }
