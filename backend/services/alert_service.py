"""
Price Alert Service

Monitors electricity prices and sends notifications when prices
drop below user-defined thresholds or enter optimal usage windows.

DB-backed methods (get_user_alerts, get_alert_history, create_alert,
update_alert, delete_alert, record_triggered_alert) persist alert
configurations to ``price_alert_configs`` and trigger events to
``alert_history`` (migration 014).

Notification routing:
    When a NotificationDispatcher is supplied to the constructor, alerts
    are routed through all configured channels (IN_APP, PUSH, EMAIL).
    If the dispatcher is not supplied (or fails), the service falls back
    to direct EmailService delivery so existing callers are unaffected.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from lib.tracing import traced
from services.alert_renderer import AlertRenderer
from services.email_service import EmailService

if TYPE_CHECKING:
    from services.notification_dispatcher import NotificationDispatcher

logger = structlog.get_logger(__name__)


class AlertThreshold:
    """Represents a user's price alert configuration."""

    def __init__(
        self,
        user_id: str,
        email: str,
        price_below: Decimal | None = None,
        price_above: Decimal | None = None,
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
        threshold: Decimal | None,
        region: str,
        supplier: str,
        timestamp: datetime,
        optimal_window_start: datetime | None = None,
        optimal_window_end: datetime | None = None,
        estimated_savings: Decimal | None = None,
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

    When a NotificationDispatcher is provided, send_alerts() routes each
    notification through all configured channels (in-app, push, email).
    The legacy EmailService path is retained as a fallback and for callers
    that do not supply a dispatcher.
    """

    def __init__(
        self,
        email_service: EmailService | None = None,
        dispatcher: Optional["NotificationDispatcher"] = None,
        db: Any | None = None,
    ):
        self._email_service = email_service or EmailService()
        self._dispatcher = dispatcher
        self._db = db
        self._renderer = AlertRenderer(self._email_service)

    def check_thresholds(
        self,
        prices: list,
        thresholds: list[AlertThreshold],
    ) -> list[tuple]:
        """
        Check current prices against user thresholds.

        Pre-groups prices by region so each threshold only checks its matching
        prices — O(n+m) instead of O(n*m).

        Args:
            prices: List of current Price objects (region, supplier, price_per_kwh, timestamp)
            thresholds: List of user alert thresholds

        Returns:
            List of (AlertThreshold, PriceAlert) tuples for triggered alerts
        """
        # Group prices by region for efficient lookup
        prices_by_region: dict = {}
        no_region_prices: list = []
        for price in prices:
            region = getattr(price, "region", None)
            if region:
                prices_by_region.setdefault(region, []).append(price)
            else:
                no_region_prices.append(price)

        triggered = []

        for threshold in thresholds:
            matching_prices = (
                prices_by_region.get(threshold.region, []) + no_region_prices
            )

            for price in matching_prices:
                current = Decimal(str(price.price_per_kwh))

                # Check price below threshold
                if threshold.price_below and current <= threshold.price_below:
                    alert = PriceAlert(
                        alert_type="price_drop",
                        current_price=current,
                        threshold=threshold.price_below,
                        region=threshold.region,
                        supplier=getattr(price, "supplier", "Unknown"),
                        timestamp=getattr(price, "timestamp", datetime.now(UTC)),
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
                        timestamp=getattr(price, "timestamp", datetime.now(UTC)),
                    )
                    triggered.append((threshold, alert))

        return triggered

    def check_optimal_windows(
        self,
        forecast_prices: list,
        thresholds: list[AlertThreshold],
        window_hours: int = 2,
    ) -> list[tuple]:
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
                timestamp=datetime.now(UTC),
                optimal_window_start=getattr(
                    window_start_price, "timestamp", datetime.now(UTC)
                ),
                optimal_window_end=getattr(
                    window_end_price, "timestamp", datetime.now(UTC)
                )
                + timedelta(hours=1),
                estimated_savings=max(estimated_savings, Decimal("0")),
            )
            triggered.append((threshold, alert))

        return triggered

    async def send_alerts(self, triggered: list[tuple]) -> list[bool]:
        """
        Send alerts for triggered thresholds via all configured channels.

        When a NotificationDispatcher was supplied at construction time the
        alert is routed through it (in-app + push + email).  If the dispatcher
        call raises an exception, or no dispatcher was supplied, the service
        falls back to direct EmailService delivery so existing callers are
        unaffected.

        The dedup_key written to the dispatcher is
        ``price_alert:<user_id>:<alert_type>:<region>`` so that the
        dispatcher's built-in cooldown deduplicate check complements (but does
        not replace) the AlertService._should_send_alert cooldown logic already
        applied by check_alerts before calling this method.

        Args:
            triggered: List of (AlertThreshold, PriceAlert) tuples

        Returns:
            List of booleans, one per input item, indicating whether that
            individual alert was successfully sent (at least one channel
            succeeded).  Use ``sum(results)`` to obtain the total sent count.
        """
        async with traced("alert.send", attributes={"alert.count": len(triggered)}):
            from services.notification_dispatcher import NotificationChannel

            results: list[bool] = []
            for threshold, alert in triggered:
                try:
                    html = self._render_alert_email(threshold, alert)
                    subject = self._get_alert_subject(alert)
                    success = False

                    if self._dispatcher is not None:
                        try:
                            dedup_key = f"price_alert:{threshold.user_id}:{alert.alert_type}:{alert.region}"
                            dispatch_result = await self._dispatcher.send(
                                user_id=threshold.user_id,
                                type="price_alert",
                                title=subject,
                                body=f"Current price: ${alert.current_price}/kWh"
                                + (
                                    f" (threshold: ${alert.threshold}/kWh)"
                                    if alert.threshold
                                    else ""
                                ),
                                channels=[
                                    NotificationChannel.IN_APP,
                                    NotificationChannel.PUSH,
                                    NotificationChannel.EMAIL,
                                ],
                                metadata={
                                    "alert_type": alert.alert_type,
                                    "region": alert.region,
                                    "current_price": str(alert.current_price),
                                    "threshold": (
                                        str(alert.threshold)
                                        if alert.threshold
                                        else None
                                    ),
                                    "supplier": alert.supplier,
                                },
                                dedup_key=dedup_key,
                                email_to=threshold.email,
                                email_subject=subject,
                                email_html=html,
                            )
                            # Consider the alert sent if it was not deduplicated
                            # and at least one channel succeeded.
                            if not dispatch_result.get("skipped_dedup", False):
                                channel_results = dispatch_result.get("channels", {})
                                success = any(channel_results.values())
                        except Exception as dispatch_exc:
                            logger.warning(
                                "alert_dispatcher_failed_falling_back",
                                user_id=threshold.user_id,
                                error=str(dispatch_exc),
                            )
                            # Fall through to direct email below
                            success = await self._email_service.send(
                                to=threshold.email,
                                subject=subject,
                                html_body=html,
                            )
                    else:
                        # Legacy path: direct email when no dispatcher is configured
                        success = await self._email_service.send(
                            to=threshold.email,
                            subject=subject,
                            html_body=html,
                        )

                    if success:
                        logger.info(
                            "alert_sent",
                            user_id=threshold.user_id,
                            alert_type=alert.alert_type,
                            price=str(alert.current_price),
                            via_dispatcher=self._dispatcher is not None,
                        )
                    results.append(bool(success))
                except Exception as e:
                    logger.error(
                        "alert_send_failed",
                        user_id=threshold.user_id,
                        error=str(e),
                    )
                    results.append(False)
            return results

    def _get_alert_subject(self, alert: PriceAlert) -> str:
        """Delegate to AlertRenderer — kept for backward compatibility."""
        return self._renderer.get_alert_subject(alert)

    def _render_alert_email(self, threshold: AlertThreshold, alert: PriceAlert) -> str:
        """Delegate to AlertRenderer — kept for backward compatibility."""
        return self._renderer.render_alert_email(threshold, alert)

    def _render_fallback_alert(self, alert: PriceAlert, currency: str) -> str:
        """Delegate to AlertRenderer — kept for backward compatibility."""
        return self._renderer.render_fallback_alert(alert, currency)

    # =========================================================================
    # Deduplication helpers (require db: AsyncSession)
    # =========================================================================

    # Cooldown windows keyed by notification_frequency value
    _COOLDOWN_HOURS: dict = {
        "immediate": 1,
        "hourly": 1,
        "daily": 24,
        "weekly": 24 * 7,
    }

    async def _should_send_alert(
        self,
        user_id: str,
        alert_type: str,
        region: str,
        notification_frequency: str,
        db: AsyncSession,
    ) -> bool:
        """
        Return True when a new alert should be sent (not inside cooldown window).

        Looks up the most recent alert_history row for this user+alert_type+region
        combination and compares its triggered_at timestamp against the cooldown
        duration derived from the user's notification_frequency preference.

        Cooldown windows:
            immediate / hourly  →  1 hour
            daily               →  24 hours
            weekly              →  7 days

        If notification_frequency is unrecognised, the hourly cooldown (1 h) is used
        as a safe default.

        Args:
            user_id:                UUID string of the user.
            alert_type:             One of "price_drop", "price_spike", "optimal_window".
            region:                 Region code matched by the alert config.
            notification_frequency: User preference string.
            db:                     Async SQLAlchemy session.

        Returns:
            True  — no recent alert found; caller may send.
            False — a recent alert was sent within the cooldown window; caller should skip.
        """
        cooldown_hours = self._COOLDOWN_HOURS.get(notification_frequency, 1)
        cutoff = datetime.now(UTC) - timedelta(hours=cooldown_hours)

        result = await db.execute(
            text("""
                SELECT triggered_at
                FROM alert_history
                WHERE user_id    = :user_id
                  AND alert_type = :alert_type
                  AND region     = :region
                  AND triggered_at >= :cutoff
                ORDER BY triggered_at DESC
                LIMIT 1
            """),
            {
                "user_id": user_id,
                "alert_type": alert_type,
                "region": region,
                "cutoff": cutoff,
            },
        )
        row = result.first()
        # If a row exists the alert is still within the cooldown window → skip
        return row is None

    async def _batch_should_send_alerts(
        self,
        triggered_pairs: list[tuple],
        freq_by_user: dict[str, str],
        db: "AsyncSession",
    ) -> set:
        """
        Batch deduplication check for multiple triggered alerts.

        Instead of querying alert_history once per triggered pair (N+1),
        groups pairs by cooldown window and runs one query per group
        (max 4 queries for the 4 frequency tiers).

        Returns:
            Set of ``(user_id, alert_type, region)`` tuples that are INSIDE
            their cooldown window and should be SKIPPED.
        """
        if not triggered_pairs:
            return set()

        # Group pairs by effective cooldown hours
        groups: dict[int, list] = {}
        for threshold, alert in triggered_pairs:
            freq = freq_by_user.get(threshold.user_id, "daily")
            cooldown_hours = self._COOLDOWN_HOURS.get(freq, 1)
            groups.setdefault(cooldown_hours, []).append(
                (threshold.user_id, alert.alert_type, alert.region)
            )

        in_cooldown: set = set()
        BATCH_SIZE = 500

        for cooldown_hours, tuples in groups.items():
            cutoff = datetime.now(UTC) - timedelta(hours=cooldown_hours)

            # Process in chunks to prevent unbounded query size
            for chunk_start in range(0, len(tuples), BATCH_SIZE):
                chunk = tuples[chunk_start : chunk_start + BATCH_SIZE]
                params: dict = {"cutoff": cutoff}
                value_clauses = []
                for i, (uid, atype, reg) in enumerate(chunk):
                    params[f"uid_{i}"] = uid
                    params[f"atype_{i}"] = atype
                    params[f"reg_{i}"] = reg
                    value_clauses.append(f"(:uid_{i}, :atype_{i}, :reg_{i})")

                values_sql = ", ".join(value_clauses)
                query = text(f"""
                    SELECT DISTINCT q.user_id, q.alert_type, q.region
                    FROM (VALUES {values_sql}) AS q(user_id, alert_type, region)
                    WHERE EXISTS (
                        SELECT 1
                        FROM alert_history ah
                        WHERE ah.user_id    = q.user_id::uuid
                          AND ah.alert_type = q.alert_type
                          AND ah.region     = q.region
                          AND ah.triggered_at >= :cutoff
                    )
                """)
                result = await db.execute(query, params)
                for row in result.fetchall():
                    in_cooldown.add((row[0], row[1], row[2]))

        return in_cooldown

    # =========================================================================
    # Bulk-load helpers for the check-alerts cron endpoint
    # =========================================================================

    async def get_active_alert_configs(
        self,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        """
        Return all active price_alert_configs joined with the owning user's
        email and notification_frequency preference.

        Used by POST /internal/check-alerts to build AlertThreshold objects
        without a separate per-user query.

        Returns:
            List of dicts with keys:
                id, user_id, email, region, currency,
                price_below, price_above, notify_optimal_windows,
                notification_frequency
        """
        result = await db.execute(
            text("""
                SELECT
                    pac.id,
                    pac.user_id,
                    u.email,
                    pac.region,
                    pac.currency,
                    pac.price_below,
                    pac.price_above,
                    pac.notify_optimal_windows,
                    COALESCE(
                        (u.preferences->>'notification_frequency'),
                        'daily'
                    ) AS notification_frequency
                FROM price_alert_configs pac
                JOIN public.users u ON u.id = pac.user_id
                WHERE pac.is_active = TRUE
                  AND u.is_active   = TRUE
                ORDER BY pac.created_at
                LIMIT 5000
            """),
        )
        rows = result.mappings().all()
        return [
            {
                "id": str(row["id"]),
                "user_id": str(row["user_id"]),
                "email": row["email"],
                "region": row["region"],
                "currency": row["currency"],
                "price_below": (
                    Decimal(str(row["price_below"]))
                    if row["price_below"] is not None
                    else None
                ),
                "price_above": (
                    Decimal(str(row["price_above"]))
                    if row["price_above"] is not None
                    else None
                ),
                "notify_optimal_windows": row["notify_optimal_windows"],
                "notification_frequency": row["notification_frequency"] or "daily",
            }
            for row in rows
        ]

    # =========================================================================
    # DB-backed CRUD methods (require db: AsyncSession)
    # =========================================================================

    async def get_user_alerts(
        self,
        user_id: str,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
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
    ) -> dict[str, Any]:
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
        region: str,
        alert_type: str = "price_drop",
        threshold: float | None = None,
        db: AsyncSession | None = None,
        currency: str = "USD",
        price_below: Decimal | None = None,
        price_above: Decimal | None = None,
        notify_optimal_windows: bool = True,
    ) -> dict[str, Any]:
        """
        Insert a new price alert configuration and return it.

        Free-tier users are limited to 1 alert. The limit check is atomic:
        the user row is locked with FOR UPDATE to prevent race conditions
        between concurrent requests.

        Args:
            user_id:                UUID string of the user.
            region:                 Region code.
            alert_type:             Type of alert (price_drop, price_spike, optimal_window).
            threshold:              Alert trigger threshold value.
            db:                     Async SQLAlchemy session (uses self._db if omitted).
            currency:               ISO 4217 currency code (default 'USD').
            price_below:            Alert threshold for price drops.
            price_above:            Alert threshold for price spikes.
            notify_optimal_windows: Whether to notify about optimal usage windows.

        Returns:
            Dict representation of the created config row.

        Raises:
            ValueError: If neither price_below nor price_above nor
                        notify_optimal_windows is specified.
            PermissionError: If free-tier limit (1 alert) is exceeded.
        """
        async with traced(
            "alert.create",
            attributes={"alert.type": alert_type, "alert.region": region},
        ):
            # Resolve threshold into price_below/price_above based on alert_type
            if threshold is not None:
                if alert_type == "price_drop" and price_below is None:
                    price_below = Decimal(str(threshold))
                elif alert_type == "price_spike" and price_above is None:
                    price_above = Decimal(str(threshold))

            # Use injected db session if no explicit one provided
            db = db or self._db

            if (
                price_below is None
                and price_above is None
                and not notify_optimal_windows
            ):
                raise ValueError(
                    "At least one of price_below, price_above, or notify_optimal_windows "
                    "must be specified."
                )

            # Atomic free-tier limit enforcement: lock user row then count alerts
            # within the same transaction to prevent race conditions.
            tier_result = await db.execute(
                text(
                    "SELECT subscription_tier FROM public.users WHERE id = :id FOR UPDATE"
                ),
                {"id": user_id},
            )
            user_tier = tier_result.scalar_one_or_none() or "free"
            if user_tier not in ("pro", "business"):
                count_result = await db.execute(
                    text(
                        "SELECT COUNT(*) FROM price_alert_configs"
                        " WHERE user_id = :id AND is_active = TRUE"
                    ),
                    {"id": user_id},
                )
                alert_count = count_result.scalar() or 0
                if alert_count >= 1:
                    raise PermissionError(
                        "Free plan limited to 1 alert. Upgrade to Pro for unlimited."
                    )

            try:
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
                        "price_below": (
                            str(price_below) if price_below is not None else None
                        ),
                        "price_above": (
                            str(price_above) if price_above is not None else None
                        ),
                        "notify_optimal_windows": notify_optimal_windows,
                    },
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise
            row = result.mappings().first()
            logger.info("alert_created", user_id=user_id, alert_id=str(row["id"]))
            return self._config_row_to_dict(row)

    async def update_alert(
        self,
        user_id: str,
        alert_id: str,
        db: AsyncSession,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
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
            "region",
            "currency",
            "price_below",
            "price_above",
            "notify_optimal_windows",
            "is_active",
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
        params: dict[str, Any] = {**filtered, "id": alert_id, "user_id": user_id}

        # Normalise Decimal values to strings for asyncpg
        for key in ("price_below", "price_above"):
            if key in params and params[key] is not None:
                params[key] = str(params[key])

        try:
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
        except Exception:
            await db.rollback()
            raise
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
        try:
            result = await db.execute(
                text("""
                    DELETE FROM price_alert_configs
                    WHERE id = :id AND user_id = :user_id
                """),
                {"id": alert_id, "user_id": user_id},
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        deleted = result.rowcount > 0
        if deleted:
            logger.info("alert_deleted", user_id=user_id, alert_id=alert_id)
        return deleted

    async def record_triggered_alert(
        self,
        user_id: str,
        alert: "PriceAlert",
        db: AsyncSession,
        alert_config_id: str | None = None,
        email_sent: bool = False,
        currency: str = "USD",
    ) -> dict[str, Any]:
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
        try:
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
                    "threshold": (
                        str(alert.threshold) if alert.threshold is not None else None
                    ),
                    "region": alert.region,
                    "supplier": alert.supplier,
                    "currency": currency,
                    "optimal_window_start": alert.optimal_window_start,
                    "optimal_window_end": alert.optimal_window_end,
                    "estimated_savings": (
                        str(alert.estimated_savings)
                        if alert.estimated_savings is not None
                        else None
                    ),
                    "triggered_at": alert.timestamp,
                    "email_sent": email_sent,
                },
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        row = result.mappings().first()
        return self._history_row_to_dict(row)

    # =========================================================================
    # Private serialisation helpers
    # =========================================================================

    @staticmethod
    def _config_row_to_dict(row) -> dict[str, Any]:
        """Serialise a price_alert_configs row mapping to a plain dict."""
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "region": row["region"],
            "currency": row["currency"],
            "price_below": (
                float(row["price_below"]) if row["price_below"] is not None else None
            ),
            "price_above": (
                float(row["price_above"]) if row["price_above"] is not None else None
            ),
            "notify_optimal_windows": row["notify_optimal_windows"],
            "is_active": row["is_active"],
            "created_at": (
                row["created_at"].isoformat() if row.get("created_at") else None
            ),
            "updated_at": (
                row["updated_at"].isoformat() if row.get("updated_at") else None
            ),
        }

    @staticmethod
    def _history_row_to_dict(row) -> dict[str, Any]:
        """Serialise an alert_history row mapping to a plain dict."""
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "alert_config_id": (
                str(row["alert_config_id"]) if row["alert_config_id"] else None
            ),
            "alert_type": row["alert_type"],
            "current_price": float(row["current_price"]),
            "threshold": (
                float(row["threshold"]) if row["threshold"] is not None else None
            ),
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
                float(row["estimated_savings"])
                if row["estimated_savings"] is not None
                else None
            ),
            "triggered_at": (
                row["triggered_at"].isoformat() if row.get("triggered_at") else None
            ),
            "email_sent": row["email_sent"],
        }
