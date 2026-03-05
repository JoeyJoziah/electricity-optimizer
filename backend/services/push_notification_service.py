"""
Push notification service via OneSignal REST API.

Free tier: Unlimited mobile push, 10K web push/send, 10K emails/month. No card.
"""

import httpx
import structlog
from typing import Optional

from config.settings import get_settings

logger = structlog.get_logger(__name__)

ONESIGNAL_API_URL = "https://onesignal.com/api/v1/notifications"


class PushNotificationService:
    def __init__(self, settings=None):
        self._settings = settings or get_settings()
        self._app_id = self._settings.onesignal_app_id
        self._rest_api_key = self._settings.onesignal_rest_api_key

    @property
    def is_configured(self) -> bool:
        return bool(self._app_id and self._rest_api_key)

    async def send_push(
        self,
        user_id: str,
        title: str,
        message: str,
        data: Optional[dict] = None,
    ) -> bool:
        """Send push notification via OneSignal REST API.

        Returns True if the notification was accepted by OneSignal.
        """
        if not self.is_configured:
            logger.debug("onesignal_not_configured")
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    ONESIGNAL_API_URL,
                    headers={
                        "Authorization": f"Basic {self._rest_api_key}",
                    },
                    json={
                        "app_id": self._app_id,
                        "include_external_user_ids": [user_id],
                        "headings": {"en": title},
                        "contents": {"en": message},
                        "data": data or {},
                    },
                )
                resp.raise_for_status()
                logger.info(
                    "push_sent",
                    user_id=user_id,
                    title=title,
                )
                return True
        except Exception as e:
            logger.error(
                "push_failed",
                user_id=user_id,
                error=str(e),
            )
            return False

    async def send_price_alert(
        self,
        user_id: str,
        region: str,
        current_price: float,
        threshold: float,
    ) -> bool:
        """Send a price alert push notification."""
        return await self.send_push(
            user_id=user_id,
            title="Price Alert",
            message=f"Electricity rate in {region} is ${current_price:.4f}/kWh — below your ${threshold:.4f} threshold.",
            data={"type": "price_alert", "region": region},
        )
