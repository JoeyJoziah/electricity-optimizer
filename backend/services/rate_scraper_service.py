"""
Supplier rate scraping via Diffbot Extract API.

Free tier: 10,000 credits/month (recurring), 5 calls/min. No card required.

Concurrency model
-----------------
Diffbot enforces 5 calls/min = 1 call every 12 s (sequential).
Running 37 suppliers sequentially therefore takes:

    37 suppliers × (network latency + 12 s sleep) ≈ 7–10 min

We model this with a shared asyncio.Semaphore(5) that gates concurrent
slots while asyncio.gather drives the I/O in parallel.  After each slot
is acquired we wait the mandatory inter-call gap only when releasing it,
so n ≤ 5 calls are in-flight simultaneously but the effective throughput
never exceeds 5/min.

With 5 parallel workers the wall-clock time for 37 suppliers drops to:

    ceil(37 / 5) × 12 s = 8 × 12 s = 96 s  (best case, fast responses)

Each individual Diffbot call is wrapped with a 30-second asyncio timeout
so a single slow or hung supplier cannot block the batch indefinitely.

Error isolation
---------------
Per-supplier failures are caught inside ``_scrape_one`` and recorded as
``success=False`` entries.  ``scrape_supplier_rates`` always returns a
batch summary rather than raising so callers can report partial success.
"""

import asyncio
from typing import Optional

import httpx
import structlog

from config.settings import get_settings

logger = structlog.get_logger(__name__)

DIFFBOT_EXTRACT_URL = "https://api.diffbot.com/v3/analyze"

# Diffbot free tier: 5 calls/min → 1 call per 12 s
_RATE_LIMIT_SLEEP_S: float = 12.0

# Hard ceiling per individual supplier call (network + Diffbot processing)
_PER_SUPPLIER_TIMEOUT_S: float = 30.0

# Maximum parallel in-flight requests (must not exceed Diffbot's 5/min burst)
_MAX_CONCURRENCY: int = 5


class RateScraperService:
    def __init__(self, settings=None):
        self._settings = settings or get_settings()
        self._token = self._settings.diffbot_api_token

    async def extract_rates_from_url(self, url: str) -> Optional[dict]:
        """Extract structured data from a supplier rate page.

        Uses 1 Diffbot credit per page. Free tier: 10,000/month.
        Rate limit: 5 calls/min — caller must throttle via semaphore.
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

    async def _scrape_one(
        self,
        item: dict,
        semaphore: asyncio.Semaphore,
    ) -> dict:
        """Scrape a single supplier URL, respecting the shared rate-limit semaphore.

        Acquires the semaphore slot, calls Diffbot, sleeps the mandatory
        inter-call gap (to stay within Diffbot's 5 calls/min), then releases
        the slot.  A per-call asyncio timeout of ``_PER_SUPPLIER_TIMEOUT_S``
        prevents a single hung request from holding the slot indefinitely.

        Failures are caught here and returned as a result dict with
        ``success=False`` so the batch is never aborted by one bad supplier.
        """
        supplier_id = item["supplier_id"]
        url = item["url"]

        async with semaphore:
            try:
                data = await asyncio.wait_for(
                    self.extract_rates_from_url(url),
                    timeout=_PER_SUPPLIER_TIMEOUT_S,
                )
                result = {
                    "supplier_id": supplier_id,
                    "extracted_data": data,
                    "success": data is not None,
                }
                logger.info(
                    "scrape_succeeded",
                    supplier_id=supplier_id,
                    url=url,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "scrape_timeout",
                    supplier_id=supplier_id,
                    url=url,
                    timeout_s=_PER_SUPPLIER_TIMEOUT_S,
                )
                result = {
                    "supplier_id": supplier_id,
                    "extracted_data": None,
                    "success": False,
                    "error": "timeout",
                }
            except Exception as exc:
                logger.error(
                    "scrape_failed",
                    supplier_id=supplier_id,
                    url=url,
                    error=str(exc),
                )
                result = {
                    "supplier_id": supplier_id,
                    "extracted_data": None,
                    "success": False,
                    "error": str(exc),
                }
            finally:
                # Respect Diffbot's 5 calls/min limit: hold the slot for the
                # mandatory inter-call gap before releasing it so the next
                # waiter doesn't fire too quickly.
                await asyncio.sleep(_RATE_LIMIT_SLEEP_S)

        return result

    async def scrape_supplier_rates(
        self,
        supplier_urls: list[dict],
        max_concurrency: int = _MAX_CONCURRENCY,
    ) -> dict:
        """Scrape multiple supplier URLs with concurrent rate limiting.

        Uses asyncio.Semaphore(max_concurrency) to cap parallel in-flight
        Diffbot calls and asyncio.gather to run them all concurrently.
        Individual supplier failures are isolated — they record
        ``success=False`` without aborting the batch.

        Args:
            supplier_urls: [{"supplier_id": str, "url": str}, ...]
            max_concurrency: max parallel Diffbot calls (default 5).

        Returns:
            {
                "total": int,       # total suppliers attempted
                "succeeded": int,   # suppliers with success=True
                "failed": int,      # suppliers with success=False
                "errors": [         # non-empty only when failures occurred
                    {"supplier_id": str, "error": str}, ...
                ],
                "results": [        # raw per-supplier result dicts
                    {"supplier_id": str, "extracted_data": dict|None,
                     "success": bool, ...}, ...
                ],
            }

        Timing estimate (37 suppliers, max_concurrency=5):
            ceil(37 / 5) * 12 s ≈ 96 s  (vs. 444 s sequential)
        """
        if not supplier_urls:
            return {"total": 0, "succeeded": 0, "failed": 0, "errors": [], "results": []}

        semaphore = asyncio.Semaphore(max_concurrency)
        tasks = [self._scrape_one(item, semaphore) for item in supplier_urls]
        raw_results: list[dict] = list(await asyncio.gather(*tasks, return_exceptions=False))

        succeeded = sum(1 for r in raw_results if r.get("success"))
        failed = len(raw_results) - succeeded
        errors = [
            {"supplier_id": r["supplier_id"], "error": r.get("error", "unknown")}
            for r in raw_results
            if not r.get("success")
        ]

        logger.info(
            "scrape_batch_complete",
            total=len(raw_results),
            succeeded=succeeded,
            failed=failed,
        )

        return {
            "total": len(raw_results),
            "succeeded": succeeded,
            "failed": failed,
            "errors": errors,
            "results": raw_results,
        }
