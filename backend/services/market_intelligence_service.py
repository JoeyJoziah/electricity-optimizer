"""
Energy market intelligence via Tavily AI search.

Free tier: 1,000 credits/month. No card required.
"""

import httpx
import structlog

from config.settings import get_settings

logger = structlog.get_logger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class MarketIntelligenceService:
    def __init__(self, settings=None):
        self._settings = settings or get_settings()
        self._api_key = self._settings.tavily_api_key

    async def search_energy_news(self, query: str, max_results: int = 5) -> dict | None:
        """Search for energy market news. Uses 1 credit per basic search."""
        if not self._api_key:
            return None
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TAVILY_SEARCH_URL,
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "search_depth": "basic",  # 1 credit (vs 2 for "advanced")
                    "max_results": max_results,
                    "include_answer": True,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "answer": data.get("answer"),
                "results": [
                    {
                        "title": r.get("title"),
                        "url": r.get("url"),
                        "content": r.get("content", "")[:500],
                    }
                    for r in data.get("results", [])
                ],
            }

    async def weekly_market_scan(self, regions: list[str]) -> list[dict]:
        """Weekly scan for rate changes across regions.

        Budget: ~10 searches/week x 4 weeks = 40/month (4% of quota).
        """
        queries = [
            f"{region} electricity rate change 2026"
            for region in regions[:10]  # Cap at 10 regions per scan
        ]
        results = []
        for query in queries:
            try:
                data = await self.search_energy_news(query, max_results=3)
                if data:
                    results.append({"query": query, "data": data})
            except Exception as e:
                logger.warning("tavily_search_failed", query=query, error=str(e))
        return results
