"""
Supplier rate scraping via Diffbot Extract API.

Free tier: 10,000 credits/month (recurring), 5 calls/min. No card required.
"""

import asyncio

import httpx
import structlog
from typing import Optional

from config.settings import get_settings

logger = structlog.get_logger(__name__)

DIFFBOT_EXTRACT_URL = "https://api.diffbot.com/v3/analyze"


class RateScraperService:
    def __init__(self, settings=None):
        self._settings = settings or get_settings()
        self._token = self._settings.diffbot_api_token

    async def extract_rates_from_url(self, url: str) -> Optional[dict]:
        """Extract structured data from a supplier rate page.

        Uses 1 Diffbot credit per page. Free tier: 10,000/month.
        Rate limit: 5 calls/min — caller must throttle.
        """
        if not self._token:
            logger.warning("diffbot_not_configured")
            return None

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                DIFFBOT_EXTRACT_URL,
                params={"token": self._token, "url": url},
            )
            resp.raise_for_status()
            return resp.json()

    async def scrape_supplier_rates(
        self, supplier_urls: list[dict]
    ) -> list[dict]:
        """Scrape multiple supplier URLs with rate limiting.

        Args:
            supplier_urls: [{"supplier_id": str, "url": str}, ...]

        Returns:
            [{"supplier_id": str, "extracted_data": dict, "success": bool}, ...]
        """
        results = []
        for item in supplier_urls:
            try:
                data = await self.extract_rates_from_url(item["url"])
                results.append({
                    "supplier_id": item["supplier_id"],
                    "extracted_data": data,
                    "success": True,
                })
            except Exception as e:
                logger.error(
                    "scrape_failed",
                    supplier_id=item["supplier_id"],
                    url=item["url"],
                    error=str(e),
                )
                results.append({
                    "supplier_id": item["supplier_id"],
                    "extracted_data": None,
                    "success": False,
                })
            # Rate limit: 5 calls/min = 12s between calls
            await asyncio.sleep(12)
        return results
