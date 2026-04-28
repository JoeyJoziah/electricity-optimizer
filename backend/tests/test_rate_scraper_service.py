"""
Tests for RateScraperService (backend/services/rate_scraper_service.py)

Coverage:
- extract_rates_from_url: returns None when token not configured
- extract_rates_from_url: returns parsed JSON on success
- extract_rates_from_url: propagates HTTP errors (raise_for_status)
- _scrape_one: success path returns dict with success=True and extracted_data
- _scrape_one: HTTP failure returns dict with success=False and error set
- _scrape_one: asyncio.TimeoutError returns success=False and error='timeout'
- _scrape_one: always sleeps the rate-limit interval (even on failure)
- scrape_supplier_rates: empty input returns zero-count summary
- scrape_supplier_rates: None input treated as empty
- scrape_supplier_rates: aggregates succeeded/failed counts correctly
- scrape_supplier_rates: errors list contains supplier_id for failures
- scrape_supplier_rates: partial success — some suppliers fail, others succeed
- scrape_supplier_rates: semaphore limits concurrency (max_concurrency param)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.rate_scraper_service import (_RATE_LIMIT_SLEEP_S,
                                           DIFFBOT_EXTRACT_URL,
                                           RateScraperService)

# =============================================================================
# Fixtures
# =============================================================================


def _settings_with_token() -> MagicMock:
    s = MagicMock()
    s.diffbot_api_token = "diffbot-test-token"
    return s


def _settings_no_token() -> MagicMock:
    s = MagicMock()
    s.diffbot_api_token = None
    return s


def _http_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_data
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    else:
        resp.raise_for_status.return_value = None
    return resp


def _make_client(resp: MagicMock) -> AsyncMock:
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _supplier(
    supplier_id: str = "sup-1", url: str = "https://example.com/rates"
) -> dict:
    return {"supplier_id": supplier_id, "url": url}


# =============================================================================
# TestExtractRatesFromUrl
# =============================================================================


class TestExtractRatesFromUrl:
    async def test_returns_none_when_no_token(self):
        svc = RateScraperService(settings=_settings_no_token())
        with patch("services.rate_scraper_service.httpx.AsyncClient") as mock_cls:
            result = await svc.extract_rates_from_url("https://example.com")
            mock_cls.assert_not_called()
        assert result is None

    async def test_returns_json_on_success(self):
        svc = RateScraperService(settings=_settings_with_token())
        extracted = {"objects": [{"text": "rate $0.12 per kWh"}]}
        mock_client = _make_client(_http_response(extracted))

        with patch(
            "services.rate_scraper_service.httpx.AsyncClient", return_value=mock_client
        ):
            result = await svc.extract_rates_from_url("https://example.com/rates")

        assert result == extracted

    async def test_request_passes_token_in_auth_header(self):
        svc = RateScraperService(settings=_settings_with_token())
        mock_client = _make_client(_http_response({}))

        with patch(
            "services.rate_scraper_service.httpx.AsyncClient", return_value=mock_client
        ):
            await svc.extract_rates_from_url("https://example.com")

        call_kwargs = mock_client.get.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer diffbot-test-token"
        params = call_kwargs.kwargs.get("params", {})
        assert params.get("url") == "https://example.com"

    async def test_requests_diffbot_endpoint(self):
        svc = RateScraperService(settings=_settings_with_token())
        mock_client = _make_client(_http_response({}))

        with patch(
            "services.rate_scraper_service.httpx.AsyncClient", return_value=mock_client
        ):
            await svc.extract_rates_from_url("https://example.com")

        url_called = mock_client.get.call_args.args[0]
        assert url_called == DIFFBOT_EXTRACT_URL

    async def test_raises_on_http_error(self):
        svc = RateScraperService(settings=_settings_with_token())
        mock_client = _make_client(_http_response({}, status_code=403))

        with patch(
            "services.rate_scraper_service.httpx.AsyncClient", return_value=mock_client
        ):
            with pytest.raises(Exception):  # noqa: B017
                await svc.extract_rates_from_url("https://example.com")


# =============================================================================
# TestScrapeOne
# =============================================================================


class TestScrapeOne:
    async def test_success_returns_extracted_data(self):
        svc = RateScraperService(settings=_settings_with_token())
        extracted = {"objects": [{"text": "rate $0.10/kWh"}]}
        semaphore = asyncio.Semaphore(1)

        with patch.object(
            svc, "extract_rates_from_url", new_callable=AsyncMock
        ) as mock_extract:
            mock_extract.return_value = extracted
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await svc._scrape_one(_supplier(), semaphore)

        assert result["success"] is True
        assert result["extracted_data"] == extracted
        assert result["supplier_id"] == "sup-1"

    async def test_failure_returns_success_false(self):
        svc = RateScraperService(settings=_settings_with_token())
        semaphore = asyncio.Semaphore(1)

        with patch.object(
            svc, "extract_rates_from_url", new_callable=AsyncMock
        ) as mock_extract:
            mock_extract.side_effect = Exception("Connection refused")
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await svc._scrape_one(_supplier("sup-fail"), semaphore)

        assert result["success"] is False
        assert "error" in result
        assert result["supplier_id"] == "sup-fail"

    async def test_timeout_returns_success_false_with_timeout_error(self):
        svc = RateScraperService(settings=_settings_with_token())
        semaphore = asyncio.Semaphore(1)

        # Simulate asyncio.wait_for raising TimeoutError by patching it directly
        async def _raise_timeout(coro, timeout):
            coro.close()  # prevent "coroutine was never awaited" warning
            raise TimeoutError()

        with patch("asyncio.wait_for", side_effect=_raise_timeout):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await svc._scrape_one(_supplier("sup-timeout"), semaphore)

        assert result["success"] is False
        assert result.get("error") == "timeout"

    async def test_sleeps_after_call_even_on_failure(self):
        svc = RateScraperService(settings=_settings_with_token())
        semaphore = asyncio.Semaphore(1)

        with patch.object(
            svc, "extract_rates_from_url", new_callable=AsyncMock
        ) as mock_extract:
            mock_extract.side_effect = Exception("Network error")
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await svc._scrape_one(_supplier(), semaphore)

        # The rate-limit sleep must always be called in the finally block
        mock_sleep.assert_awaited_once_with(_RATE_LIMIT_SLEEP_S)

    async def test_sleeps_after_successful_call(self):
        svc = RateScraperService(settings=_settings_with_token())
        semaphore = asyncio.Semaphore(1)

        with patch.object(
            svc, "extract_rates_from_url", new_callable=AsyncMock
        ) as mock_extract:
            mock_extract.return_value = {}
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await svc._scrape_one(_supplier(), semaphore)

        mock_sleep.assert_awaited_once_with(_RATE_LIMIT_SLEEP_S)

    async def test_none_extraction_result_returns_success_false(self):
        """When extract_rates_from_url returns None (unconfigured token), success=False."""
        svc = RateScraperService(settings=_settings_no_token())
        semaphore = asyncio.Semaphore(1)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await svc._scrape_one(_supplier(), semaphore)

        assert result["success"] is False


# =============================================================================
# TestScrapeSupplierRates
# =============================================================================


class TestScrapeSupplierRates:
    async def test_empty_list_returns_zero_counts(self):
        svc = RateScraperService(settings=_settings_with_token())
        result = await svc.scrape_supplier_rates([])
        assert result == {
            "total": 0,
            "succeeded": 0,
            "failed": 0,
            "errors": [],
            "results": [],
        }

    async def test_none_input_treated_as_empty(self):
        svc = RateScraperService(settings=_settings_with_token())
        result = await svc.scrape_supplier_rates(None)
        assert result["total"] == 0
        assert result["succeeded"] == 0

    async def test_all_succeed_counts_correctly(self):
        svc = RateScraperService(settings=_settings_with_token())
        suppliers = [
            _supplier(f"sup-{i}", f"https://example.com/{i}") for i in range(3)
        ]

        async def _ok_scrape(item, sem):
            async with sem:
                await asyncio.sleep(0)  # Yield control to let queued coroutines advance
                return {
                    "supplier_id": item["supplier_id"],
                    "extracted_data": {},
                    "success": True,
                }

        with patch.object(svc, "_scrape_one", side_effect=_ok_scrape):
            result = await svc.scrape_supplier_rates(suppliers)

        assert result["total"] == 3
        assert result["succeeded"] == 3
        assert result["failed"] == 0
        assert result["errors"] == []

    async def test_all_fail_counts_correctly(self):
        svc = RateScraperService(settings=_settings_with_token())
        suppliers = [_supplier(f"sup-{i}") for i in range(2)]

        async def _fail_scrape(item, sem):
            async with sem:
                await asyncio.sleep(0)  # Yield control to let queued coroutines advance
                return {
                    "supplier_id": item["supplier_id"],
                    "extracted_data": None,
                    "success": False,
                    "error": "timeout",
                }

        with patch.object(svc, "_scrape_one", side_effect=_fail_scrape):
            result = await svc.scrape_supplier_rates(suppliers)

        assert result["total"] == 2
        assert result["succeeded"] == 0
        assert result["failed"] == 2
        assert len(result["errors"]) == 2

    async def test_partial_success(self):
        svc = RateScraperService(settings=_settings_with_token())
        suppliers = [
            _supplier("ok-1", "https://ok.com"),
            _supplier("fail-1", "https://fail.com"),
            _supplier("ok-2", "https://ok2.com"),
        ]

        async def _mixed_scrape(item, sem):
            async with sem:
                await asyncio.sleep(0)  # Yield control to let queued coroutines advance
                if "fail" in item["supplier_id"]:
                    return {
                        "supplier_id": item["supplier_id"],
                        "extracted_data": None,
                        "success": False,
                        "error": "http_error",
                    }
                return {
                    "supplier_id": item["supplier_id"],
                    "extracted_data": {},
                    "success": True,
                }

        with patch.object(svc, "_scrape_one", side_effect=_mixed_scrape):
            result = await svc.scrape_supplier_rates(suppliers)

        assert result["total"] == 3
        assert result["succeeded"] == 2
        assert result["failed"] == 1
        assert len(result["errors"]) == 1
        assert result["errors"][0]["supplier_id"] == "fail-1"

    async def test_errors_list_contains_supplier_id_and_error(self):
        svc = RateScraperService(settings=_settings_with_token())
        suppliers = [_supplier("bad-sup")]

        async def _fail_scrape(item, sem):
            async with sem:
                await asyncio.sleep(0)  # Yield control to let queued coroutines advance
                return {
                    "supplier_id": item["supplier_id"],
                    "extracted_data": None,
                    "success": False,
                    "error": "connection_refused",
                }

        with patch.object(svc, "_scrape_one", side_effect=_fail_scrape):
            result = await svc.scrape_supplier_rates(suppliers)

        assert result["errors"][0]["supplier_id"] == "bad-sup"
        assert "error" in result["errors"][0]

    async def test_results_list_contains_all_raw_results(self):
        svc = RateScraperService(settings=_settings_with_token())
        suppliers = [_supplier("s1"), _supplier("s2")]

        async def _scrape(item, sem):
            async with sem:
                await asyncio.sleep(0)  # Yield control to let queued coroutines advance
                return {
                    "supplier_id": item["supplier_id"],
                    "extracted_data": {"rate": 0.1},
                    "success": True,
                }

        with patch.object(svc, "_scrape_one", side_effect=_scrape):
            result = await svc.scrape_supplier_rates(suppliers)

        assert len(result["results"]) == 2
        supplier_ids = {r["supplier_id"] for r in result["results"]}
        assert "s1" in supplier_ids
        assert "s2" in supplier_ids

    async def test_respects_max_concurrency_parameter(self):
        """Verify custom max_concurrency creates a semaphore with that limit."""
        svc = RateScraperService(settings=_settings_with_token())
        suppliers = [_supplier(f"s{i}") for i in range(4)]
        captured_semaphores = []

        async def _capture_scrape(item, sem):
            captured_semaphores.append(sem)
            async with sem:
                await asyncio.sleep(0)  # Yield control to let queued coroutines advance
                return {
                    "supplier_id": item["supplier_id"],
                    "extracted_data": {},
                    "success": True,
                }

        with patch.object(svc, "_scrape_one", side_effect=_capture_scrape):
            await svc.scrape_supplier_rates(suppliers, max_concurrency=2)

        # All tasks should share the same semaphore instance
        assert len({id(s) for s in captured_semaphores}) == 1
        # The semaphore should have the custom bound
        sem = captured_semaphores[0]
        assert sem._value == 2  # asyncio.Semaphore stores initial value
