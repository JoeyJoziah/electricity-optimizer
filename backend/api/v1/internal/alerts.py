"""
Internal alerts endpoint.

Covers: /check-alerts
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/check-alerts", tags=["Internal"])
async def check_alerts(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Run the price-alert pipeline: load active configs, fetch recent prices,
    check thresholds, deduplicate, and send outstanding alerts.

    Summary response fields:
        checked      — total (threshold, price) pairs evaluated
        triggered    — pairs where the price breached the threshold
        sent         — alerts actually emailed (passed dedup)
        deduplicated — alerts suppressed because one was already sent
                       within the user's notification_frequency cooldown

    Cooldown windows:
        immediate / hourly  ->  1 hour
        daily               ->  24 hours
        weekly              ->  7 days

    Protected by the router-level X-API-Key dependency.
    """
    from services.alert_service import AlertService, AlertThreshold
    from services.notification_dispatcher import NotificationDispatcher, NotificationChannel
    from services.notification_service import NotificationService
    from services.push_notification_service import PushNotificationService
    from services.email_service import EmailService
    from repositories.price_repository import PriceRepository

    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Build a NotificationDispatcher so alert sends reach all channels.
    try:
        dispatcher = NotificationDispatcher(
            db=db,
            notification_service=NotificationService(db),
            push_service=PushNotificationService(),
            email_service=EmailService(),
        )
    except Exception as exc:
        logger.warning("check_alerts_dispatcher_init_failed", error=str(exc))
        dispatcher = None

    service = AlertService(dispatcher=dispatcher)
    price_repo = PriceRepository(db)

    try:
        # ------------------------------------------------------------------
        # 1. Load all active alert configs (joined with user email + prefs)
        # ------------------------------------------------------------------
        configs = await service.get_active_alert_configs(db)

        if not configs:
            return {"checked": 0, "triggered": 0, "sent": 0, "deduplicated": 0}

        # ------------------------------------------------------------------
        # 2. Collect the distinct regions that need current prices
        # ------------------------------------------------------------------
        regions = list({cfg["region"] for cfg in configs if cfg["region"]})

        # Fetch latest prices for all needed regions in a single query
        try:
            all_prices = await price_repo.list_latest_by_regions(regions, limit_per_region=20)
        except Exception as exc:
            logger.warning("check_alerts_price_fetch_failed", error=str(exc))
            all_prices = []

        # ------------------------------------------------------------------
        # 3. Build AlertThreshold objects from the DB config rows
        # ------------------------------------------------------------------
        thresholds = [
            AlertThreshold(
                user_id=cfg["user_id"],
                email=cfg["email"],
                price_below=cfg["price_below"],
                price_above=cfg["price_above"],
                notify_optimal_windows=cfg["notify_optimal_windows"],
                region=cfg["region"],
                currency=cfg["currency"],
            )
            for cfg in configs
        ]

        # Map user_id -> notification_frequency for fast lookup in dedup step
        freq_by_user = {cfg["user_id"]: cfg["notification_frequency"] for cfg in configs}
        # Map user_id -> alert_config_id for history records
        config_id_by_user = {cfg["user_id"]: cfg["id"] for cfg in configs}

        # ------------------------------------------------------------------
        # 4. Check thresholds (pure, no DB I/O)
        # ------------------------------------------------------------------
        triggered_pairs = service.check_thresholds(all_prices, thresholds)

        checked = len(thresholds) * len(all_prices) if all_prices else 0
        triggered_count = len(triggered_pairs)
        to_send = []
        deduplicated = 0

        # ------------------------------------------------------------------
        # 5. Deduplication — batch check cooldown windows (single query per
        #    frequency tier instead of one query per triggered pair)
        # ------------------------------------------------------------------
        in_cooldown = await service._batch_should_send_alerts(
            triggered_pairs, freq_by_user, db
        )
        for threshold, alert in triggered_pairs:
            key = (threshold.user_id, alert.alert_type, alert.region)
            if key not in in_cooldown:
                to_send.append((threshold, alert))
            else:
                deduplicated += 1
                logger.debug(
                    "check_alerts_deduplicated",
                    user_id=threshold.user_id,
                    alert_type=alert.alert_type,
                    region=alert.region,
                    frequency=freq_by_user.get(threshold.user_id, "daily"),
                )

        # ------------------------------------------------------------------
        # 6. Send non-duplicate alerts and record history
        # ------------------------------------------------------------------
        # send_alerts() returns a per-item list of booleans so we can record
        # the accurate email_sent flag for each alert in alert_history.
        send_results = await service.send_alerts(to_send)
        sent = sum(send_results)

        # Persist each triggered alert to alert_history using the actual
        # per-item send outcome so that email_sent is only True when the
        # notification was actually delivered.
        for (threshold, alert), email_was_sent in zip(to_send, send_results):
            try:
                await service.record_triggered_alert(
                    user_id=threshold.user_id,
                    alert=alert,
                    db=db,
                    alert_config_id=config_id_by_user.get(threshold.user_id),
                    email_sent=email_was_sent,
                    currency=threshold.currency,
                )
            except Exception as exc:
                logger.error(
                    "check_alerts_history_record_failed",
                    user_id=threshold.user_id,
                    error=str(exc),
                )

        logger.info(
            "check_alerts_complete",
            checked=checked,
            triggered=triggered_count,
            sent=sent,
            deduplicated=deduplicated,
        )

        return {
            "checked": checked,
            "triggered": triggered_count,
            "sent": sent,
            "deduplicated": deduplicated,
        }

    except Exception as exc:
        logger.error("check_alerts_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Alert check failed. See server logs for details.")
