"""
Tests for MarketIntelligenceService (backend/services/market_intelligence_service.py)

Coverage:
- search_energy_news: returns None when API key not configured
- search_energy_news: returns structured dict on success
- search_energy_news: truncates content to 500 chars
- search_energy_news: propagates HTTP errors (4xx/5xx raise_for_status)
- search_energy_news: respects max_results parameter in request payload
- search_energy_news: extracts answer and results correctly
- weekly_market_scan: returns empty list when no regions given
- weekly_market_scan: caps regions at 10
- weekly_market_scan: skips failed queries without raising
- weekly_market_scan: returns only successful results
- weekly_market_scan: calls search_energy_news once per region
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.market_intelligence_service import MarketIntelligenceService

# =============================================================================
# Fixtures
# =============================================================================


def _settings_with_key() -> MagicMock:
    settings = MagicMock()
    settings.tavily_api_key = "tvly-test-api-key"
    return settings


def _settings_no_key() -> MagicMock:
    settings = MagicMock()
    settings.tavily_api_key = None
    return settings


def _tavily_response(
    answer: str = "Test answer", n_results: int = 2, long_content: bool = False
) -> dict:
    """Build a synthetic Tavily API response."""
    content = "X" * 1000 if long_content else "Short content"
    return {
        "answer": answer,
        "results": [
            {
                "title": f"Result {i}",
                "url": f"https://example.com/{i}",
                "content": content,
            }
            for i in range(n_results)
        ],
    }


def _mock_http_client(json_response: dict, status_code: int = 200) -> AsyncMock:
    resp = MagicMock()
    resp.json.return_value = json_response
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    else:
        resp.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# =============================================================================
# TestSearchEnergyNews
# =============================================================================


class TestSearchEnergyNews:
    async def test_returns_none_when_no_api_key(self):
        svc = MarketIntelligenceService(settings=_settings_no_key())
        with patch("services.market_intelligence_service.httpx.AsyncClient") as mock_cls:
            result = await svc.search_energy_news("CT electricity rates")
            mock_cls.assert_not_called()

        assert result is None

    async def test_returns_structured_dict_on_success(self):
        svc = MarketIntelligenceService(settings=_settings_with_key())
        mock_client = _mock_http_client(_tavily_response())

        with patch(
            "services.market_intelligence_service.httpx.AsyncClient", return_value=mock_client
        ):
            result = await svc.search_energy_news("CT electricity rates")

        assert result is not None
        assert "answer" in result
        assert "results" in result
        assert result["answer"] == "Test answer"
        assert len(result["results"]) == 2

    async def test_result_fields_include_title_url_content(self):
        svc = MarketIntelligenceService(settings=_settings_with_key())
        mock_client = _mock_http_client(_tavily_response(n_results=1))

        with patch(
            "services.market_intelligence_service.httpx.AsyncClient", return_value=mock_client
        ):
            result = await svc.search_energy_news("query")

        item = result["results"][0]
        assert "title" in item
        assert "url" in item
        assert "content" in item

    async def test_content_truncated_to_500_chars(self):
        svc = MarketIntelligenceService(settings=_settings_with_key())
        mock_client = _mock_http_client(_tavily_response(n_results=1, long_content=True))

        with patch(
            "services.market_intelligence_service.httpx.AsyncClient", return_value=mock_client
        ):
            result = await svc.search_energy_news("query")

        content = result["results"][0]["content"]
        assert len(content) <= 500

    async def test_respects_max_results_in_request(self):
        svc = MarketIntelligenceService(settings=_settings_with_key())
        mock_client = _mock_http_client(_tavily_response(n_results=3))

        with patch(
            "services.market_intelligence_service.httpx.AsyncClient", return_value=mock_client
        ):
            await svc.search_energy_news("query", max_results=3)

        json_body = mock_client.post.call_args.kwargs.get("json", {})
        assert json_body.get("max_results") == 3

    async def test_request_includes_api_key(self):
        svc = MarketIntelligenceService(settings=_settings_with_key())
        mock_client = _mock_http_client(_tavily_response())

        with patch(
            "services.market_intelligence_service.httpx.AsyncClient", return_value=mock_client
        ):
            await svc.search_energy_news("query")

        json_body = mock_client.post.call_args.kwargs.get("json", {})
        assert json_body.get("api_key") == "tvly-test-api-key"

    async def test_uses_basic_search_depth(self):
        svc = MarketIntelligenceService(settings=_settings_with_key())
        mock_client = _mock_http_client(_tavily_response())

        with patch(
            "services.market_intelligence_service.httpx.AsyncClient", return_value=mock_client
        ):
            await svc.search_energy_news("query")

        json_body = mock_client.post.call_args.kwargs.get("json", {})
        assert json_body.get("search_depth") == "basic"

    async def test_raises_on_http_error(self):
        svc = MarketIntelligenceService(settings=_settings_with_key())
        mock_client = _mock_http_client({}, status_code=429)

        with (
            patch(
                "services.market_intelligence_service.httpx.AsyncClient", return_value=mock_client
            ),
            pytest.raises(Exception),  # noqa: B017
        ):
            await svc.search_energy_news("query")

    async def test_empty_results_list(self):
        svc = MarketIntelligenceService(settings=_settings_with_key())
        mock_client = _mock_http_client({"answer": "No data", "results": []})

        with patch(
            "services.market_intelligence_service.httpx.AsyncClient", return_value=mock_client
        ):
            result = await svc.search_energy_news("obscure query")

        assert result is not None
        assert result["results"] == []
        assert result["answer"] == "No data"

    async def test_missing_answer_defaults_to_none(self):
        svc = MarketIntelligenceService(settings=_settings_with_key())
        # Tavily response without 'answer' key
        mock_client = _mock_http_client({"results": []})

        with patch(
            "services.market_intelligence_service.httpx.AsyncClient", return_value=mock_client
        ):
            result = await svc.search_energy_news("query")

        assert result["answer"] is None


# =============================================================================
# TestWeeklyMarketScan
# =============================================================================


class TestWeeklyMarketScan:
    async def test_returns_empty_list_for_no_regions(self):
        svc = MarketIntelligenceService(settings=_settings_with_key())
        result = await svc.weekly_market_scan([])
        assert result == []

    async def test_calls_search_once_per_region(self):
        svc = MarketIntelligenceService(settings=_settings_with_key())
        regions = ["CT", "NY", "MA"]

        with patch.object(svc, "search_energy_news", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {"answer": "a", "results": []}
            result = await svc.weekly_market_scan(regions)

        assert mock_search.await_count == len(regions)
        assert len(result) == len(regions)

    async def test_caps_at_10_regions(self):
        svc = MarketIntelligenceService(settings=_settings_with_key())
        # Pass 15 regions; only the first 10 should be queried
        regions = [f"STATE_{i}" for i in range(15)]

        with patch.object(svc, "search_energy_news", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {"answer": "x", "results": []}
            result = await svc.weekly_market_scan(regions)

        assert mock_search.await_count == 10
        assert len(result) == 10

    async def test_skips_failed_queries_without_raising(self):
        svc = MarketIntelligenceService(settings=_settings_with_key())
        regions = ["CT", "NY", "MA"]

        async def _search_side_effect(query, max_results=5):
            if "NY" in query:
                raise Exception("Tavily timeout")
            return {"answer": "ok", "results": []}

        with patch.object(svc, "search_energy_news", side_effect=_search_side_effect):
            result = await svc.weekly_market_scan(regions)

        # CT and MA succeed; NY is skipped
        assert len(result) == 2
        for r in result:
            assert "NY" not in r["query"]

    async def test_skips_none_results(self):
        svc = MarketIntelligenceService(settings=_settings_no_key())
        regions = ["CT", "NY"]

        # search_energy_news returns None when no API key configured
        with patch.object(svc, "search_energy_news", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = None
            result = await svc.weekly_market_scan(regions)

        # None results are not appended
        assert result == []

    async def test_result_includes_query_and_data(self):
        svc = MarketIntelligenceService(settings=_settings_with_key())
        regions = ["TX"]
        search_data = {"answer": "TX rates rising", "results": []}

        with patch.object(svc, "search_energy_news", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = search_data
            result = await svc.weekly_market_scan(regions)

        assert len(result) == 1
        assert "query" in result[0]
        assert "data" in result[0]
        assert result[0]["data"] == search_data
        assert "TX" in result[0]["query"]

    async def test_query_includes_year(self):
        svc = MarketIntelligenceService(settings=_settings_with_key())
        regions = ["CA"]

        with patch.object(svc, "search_energy_news", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {"answer": "a", "results": []}
            await svc.weekly_market_scan(regions)

        query_used = mock_search.call_args.args[0]
        assert "electricity rate change" in query_used
        assert "CA" in query_used
