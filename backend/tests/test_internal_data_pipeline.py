"""
Tests for the Internal Data Pipeline API endpoints.

Covers:
- POST /internal/fetch-weather    — fetch and persist weather data
- POST /internal/market-research  — run market intelligence scan
- POST /internal/scrape-rates     — scrape supplier rates (auto-discovery + batch)

Also includes unit tests for RateScraperService concurrency/timeout behaviour.

Note: internal router uses lazy imports (inside endpoint functions), so patches
target the service modules directly rather than api.v1.internal.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session, get_redis, verify_api_key


BASE_URL = "/api/v1/internal"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock async database session."""
    return AsyncMock()


@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    return AsyncMock()


@pytest.fixture
def auth_client(mock_db, mock_redis_client):
    """TestClient with API key verified and mocked DB/Redis sessions."""
    from main import app

    app.dependency_overrides[verify_api_key] = lambda: True
    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis_client

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_redis, None)


@pytest.fixture
def unauth_client(mock_db, mock_redis_client):
    """TestClient without API key override (auth not bypassed)."""
    from main import app

    # Remove the verify_api_key override so real validation runs
    app.dependency_overrides.pop(verify_api_key, None)
    # Still mock DB/Redis to avoid real connection attempts
    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis_client

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_redis, None)


# =============================================================================
# POST /internal/fetch-weather (persistence)
# =============================================================================


class TestFetchWeatherPersistence:
    """Tests for weather data persistence in POST /api/v1/internal/fetch-weather."""

    @patch("services.weather_service.WeatherService")
    def test_weather_persists_to_db(self, mock_svc_cls, auth_client, mock_db):
        """Weather results should be inserted into weather_cache table."""
        mock_svc = MagicMock()
        mock_svc.fetch_weather_for_regions = AsyncMock(return_value={
            "NY": {"temp_f": 72.5, "humidity": 65, "wind_mph": 8.2, "description": "partly cloudy"},
            "CA": {"temp_f": 85.0, "humidity": 30, "wind_mph": 3.1, "description": "clear sky"},
        })
        mock_svc_cls.return_value = mock_svc

        mock_db.execute = AsyncMock(return_value=None)
        mock_db.commit = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/fetch-weather",
            json={"regions": ["NY", "CA"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["regions_fetched"] == 2
        assert data["persisted"] == 2

        # Verify 2 INSERT calls were made
        assert mock_db.execute.await_count == 2
        mock_db.commit.assert_awaited_once()

    @patch("services.weather_service.WeatherService")
    def test_weather_defaults_to_all_states(self, mock_svc_cls, auth_client, mock_db):
        """Empty body should default to all 51 US state regions."""
        mock_svc = MagicMock()
        mock_svc.fetch_weather_for_regions = AsyncMock(return_value={})
        mock_svc_cls.return_value = mock_svc

        mock_db.execute = AsyncMock(return_value=None)
        mock_db.commit = AsyncMock(return_value=None)

        # No body — should use all-states default
        response = auth_client.post(f"{BASE_URL}/fetch-weather")

        assert response.status_code == 200
        # Verify service was called with all 51 states
        call_args = mock_svc.fetch_weather_for_regions.call_args[0][0]
        assert len(call_args) == 51
        assert "NY" in call_args
        assert "CA" in call_args

    @patch("services.weather_service.WeatherService")
    def test_weather_no_results_no_persist(self, mock_svc_cls, auth_client, mock_db):
        """Empty weather results should not trigger any DB writes."""
        mock_svc = MagicMock()
        mock_svc.fetch_weather_for_regions = AsyncMock(return_value={})
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(
            f"{BASE_URL}/fetch-weather",
            json={"regions": ["NY"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["persisted"] == 0
        mock_db.execute.assert_not_awaited()

    @patch("services.weather_service.WeatherService")
    def test_weather_persist_error_tolerated(self, mock_svc_cls, auth_client, mock_db):
        """DB insert failures should be logged and tolerated, not cause 500."""
        mock_svc = MagicMock()
        mock_svc.fetch_weather_for_regions = AsyncMock(return_value={
            "NY": {"temp_f": 72.5, "humidity": 65, "wind_mph": 8.2, "description": "clear"},
        })
        mock_svc_cls.return_value = mock_svc

        mock_db.execute = AsyncMock(side_effect=RuntimeError("DB write failed"))
        mock_db.commit = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/fetch-weather",
            json={"regions": ["NY"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["regions_fetched"] == 1
        assert data["persisted"] == 0


# =============================================================================
# POST /internal/market-research (persistence)
# =============================================================================


class TestMarketResearchPersistence:
    """Tests for market research data persistence."""

    @patch("services.market_intelligence_service.MarketIntelligenceService")
    def test_market_research_persists_to_db(self, mock_svc_cls, auth_client, mock_db):
        """Market scan results should be inserted into market_intelligence table."""
        mock_svc = MagicMock()
        mock_svc.weekly_market_scan = AsyncMock(return_value=[
            {
                "query": "NY electricity rate change 2026",
                "data": {
                    "answer": "Rates are increasing",
                    "results": [
                        {"title": "NY Rate Hike", "url": "https://example.com/1", "content": "..."},
                        {"title": "Energy Report", "url": "https://example.com/2", "content": "..."},
                    ],
                },
            },
        ])
        mock_svc_cls.return_value = mock_svc

        mock_db.execute = AsyncMock(return_value=None)
        mock_db.commit = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/market-research",
            json={"regions": ["NY"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["persisted"] == 2  # 2 results in the scan

        assert mock_db.execute.await_count == 2
        mock_db.commit.assert_awaited_once()

    @patch("services.market_intelligence_service.MarketIntelligenceService")
    def test_market_research_no_results_no_persist(self, mock_svc_cls, auth_client, mock_db):
        """Empty market scan should not trigger DB writes."""
        mock_svc = MagicMock()
        mock_svc.weekly_market_scan = AsyncMock(return_value=[])
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(
            f"{BASE_URL}/market-research",
            json={"regions": ["NY"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["persisted"] == 0


# =============================================================================
# POST /internal/scrape-rates (auto-discovery)
# =============================================================================


class TestScrapeRatesAutoDiscovery:
    """Tests for the auto-discovery behavior when no supplier_urls provided."""

    @patch("services.rate_scraper_service.RateScraperService")
    def test_explicit_urls(self, mock_svc_cls, auth_client, mock_db):
        """Providing explicit supplier_urls should use them directly."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(return_value={
            "total": 1,
            "succeeded": 1,
            "failed": 0,
            "errors": [],
            "results": [{"supplier_id": "s1", "extracted_data": {}, "success": True}],
        })
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": [{"supplier_id": "s1", "url": "https://example.com"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["total"] == 1
        assert data["succeeded"] == 1
        assert data["failed"] == 0

        mock_svc.scrape_supplier_rates.assert_awaited_once_with(
            [{"supplier_id": "s1", "url": "https://example.com"}]
        )

    @patch("services.rate_scraper_service.RateScraperService")
    def test_empty_body_auto_discovers(self, mock_svc_cls, auth_client, mock_db):
        """Empty body should trigger DB auto-discovery of suppliers with websites."""
        # Mock DB execute to return suppliers with websites
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("id-1", "SupplierA", "https://a.com/rates"),
            ("id-2", "SupplierB", "https://b.com/rates"),
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(return_value={
            "total": 2,
            "succeeded": 2,
            "failed": 0,
            "errors": [],
            "results": [
                {"supplier_id": "id-1", "success": True},
                {"supplier_id": "id-2", "success": True},
            ],
        })
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post(f"{BASE_URL}/scrape-rates")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["succeeded"] == 2

    @patch("services.rate_scraper_service.RateScraperService")
    def test_no_suppliers_found(self, mock_svc_cls, auth_client, mock_db):
        """When no suppliers have websites, return empty results."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = auth_client.post(f"{BASE_URL}/scrape-rates")

        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        assert "No suppliers" in data.get("message", "")


# =============================================================================
# POST /internal/scrape-rates (persistence)
# =============================================================================


class TestScrapeRatesPersistence:
    """Tests for scraped rates data persistence."""

    @patch("services.rate_scraper_service.RateScraperService")
    def test_scrape_results_persisted(self, mock_svc_cls, auth_client, mock_db):
        """Scrape results should be inserted into scraped_rates table."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(return_value={
            "total": 1,
            "succeeded": 1,
            "failed": 0,
            "errors": [],
            "results": [{"supplier_id": "s1", "extracted_data": {"rates": [1.5]}, "success": True}],
        })
        mock_svc_cls.return_value = mock_svc

        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
        mock_db.commit = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": [{"supplier_id": "s1", "url": "https://example.com", "name": "Test"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["persisted"] == 1

        mock_db.commit.assert_awaited_once()


# =============================================================================
# POST /internal/scrape-rates — batch summary endpoint tests
# =============================================================================


class TestScrapeRatesBatchSummary:
    """Endpoint-level tests for the batch summary response format.

    The service layer now returns a summary dict rather than a raw list.
    These tests verify the endpoint exposes all summary fields correctly.
    """

    @patch("services.rate_scraper_service.RateScraperService")
    def test_endpoint_exposes_succeeded_and_failed_counts(self, mock_svc_cls, auth_client, mock_db):
        """Response includes succeeded/failed counts from the batch summary."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(return_value={
            "total": 3,
            "succeeded": 2,
            "failed": 1,
            "errors": [{"supplier_id": "bad", "error": "HTTP 503"}],
            "results": [
                {"supplier_id": "s1", "success": True, "extracted_data": {}},
                {"supplier_id": "s2", "success": True, "extracted_data": {}},
                {"supplier_id": "bad", "success": False, "extracted_data": None},
            ],
        })
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
        mock_db.commit = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={
                "supplier_urls": [
                    {"supplier_id": "s1", "url": "https://s1.com"},
                    {"supplier_id": "s2", "url": "https://s2.com"},
                    {"supplier_id": "bad", "url": "https://bad.com"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["total"] == 3
        assert data["succeeded"] == 2
        assert data["failed"] == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["supplier_id"] == "bad"

    @patch("services.rate_scraper_service.RateScraperService")
    def test_partial_failure_does_not_return_500(self, mock_svc_cls, auth_client, mock_db):
        """A batch with failures must not cause a 500 — partial success is still 200."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(return_value={
            "total": 5,
            "succeeded": 3,
            "failed": 2,
            "errors": [
                {"supplier_id": "fail1", "error": "timeout"},
                {"supplier_id": "fail2", "error": "Connection refused"},
            ],
            "results": [
                {"supplier_id": "ok1", "success": True, "extracted_data": {}},
                {"supplier_id": "ok2", "success": True, "extracted_data": {}},
                {"supplier_id": "ok3", "success": True, "extracted_data": {}},
                {"supplier_id": "fail1", "success": False, "extracted_data": None, "error": "timeout"},
                {"supplier_id": "fail2", "success": False, "extracted_data": None, "error": "Connection refused"},
            ],
        })
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
        mock_db.commit = AsyncMock(return_value=None)

        suppliers = [
            {"supplier_id": f"ok{i}", "url": f"https://ok{i}.com"} for i in range(1, 4)
        ] + [
            {"supplier_id": "fail1", "url": "https://slow.com"},
            {"supplier_id": "fail2", "url": "https://down.com"},
        ]
        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": suppliers},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["failed"] == 2
        assert data["succeeded"] == 3

    @patch("services.rate_scraper_service.RateScraperService")
    def test_all_fail_still_returns_200(self, mock_svc_cls, auth_client, mock_db):
        """Even if every supplier fails, the endpoint returns 200 with the summary."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(return_value={
            "total": 2,
            "succeeded": 0,
            "failed": 2,
            "errors": [
                {"supplier_id": "a", "error": "timeout"},
                {"supplier_id": "b", "error": "HTTP 404"},
            ],
            "results": [
                {"supplier_id": "a", "success": False, "extracted_data": None, "error": "timeout"},
                {"supplier_id": "b", "success": False, "extracted_data": None, "error": "HTTP 404"},
            ],
        })
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
        mock_db.commit = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": [
                {"supplier_id": "a", "url": "https://a.com"},
                {"supplier_id": "b", "url": "https://b.com"},
            ]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["total"] == 2
        assert data["succeeded"] == 0
        assert data["failed"] == 2

    @patch("services.rate_scraper_service.RateScraperService")
    def test_response_includes_all_summary_keys(self, mock_svc_cls, auth_client, mock_db):
        """The response must include all required batch summary fields."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(return_value={
            "total": 1,
            "succeeded": 1,
            "failed": 0,
            "errors": [],
            "results": [{"supplier_id": "x", "success": True, "extracted_data": {}}],
        })
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
        mock_db.commit = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": [{"supplier_id": "x", "url": "https://x.com"}]},
        )

        assert response.status_code == 200
        data = response.json()
        required_keys = {"status", "total", "succeeded", "failed", "errors", "persisted", "results"}
        missing = required_keys - set(data.keys())
        assert not missing, f"Response missing keys: {missing}"


# =============================================================================
# RateScraperService unit tests (concurrency + timeout behaviour)
# =============================================================================


class TestRateScraperServiceConcurrency:
    """Unit tests for the concurrent scraping logic in RateScraperService."""

    @pytest.mark.asyncio
    async def test_scrape_all_succeed(self):
        """All suppliers succeed — summary has succeeded=3, failed=0."""
        from services.rate_scraper_service import RateScraperService

        svc = RateScraperService.__new__(RateScraperService)
        svc._token = "tok"

        async def _fast_extract(url):
            return {"objects": [{"type": "price", "text": "$.12/kWh"}]}

        with patch.object(svc, "extract_rates_from_url", side_effect=_fast_extract):
            # Zero-out the 12-second rate-limit sleep so the test runs fast
            with patch("services.rate_scraper_service._RATE_LIMIT_SLEEP_S", 0.001):
                batch = await svc.scrape_supplier_rates(
                    [
                        {"supplier_id": "s1", "url": "https://a.com"},
                        {"supplier_id": "s2", "url": "https://b.com"},
                        {"supplier_id": "s3", "url": "https://c.com"},
                    ]
                )

        assert batch["total"] == 3
        assert batch["succeeded"] == 3
        assert batch["failed"] == 0
        assert batch["errors"] == []
        results = batch["results"]
        assert len(results) == 3
        assert all(r["success"] for r in results)
        sids = {r["supplier_id"] for r in results}
        assert sids == {"s1", "s2", "s3"}

    @pytest.mark.asyncio
    async def test_partial_failure_does_not_block_batch(self):
        """A failing supplier records success=False without crashing others.

        Verifies that:
        - The batch summary reflects the partial failure counts.
        - The errors list contains the failing supplier_id.
        - Successful suppliers are unaffected.
        """
        from services.rate_scraper_service import RateScraperService

        svc = RateScraperService.__new__(RateScraperService)
        svc._token = "tok"

        async def _flaky_extract(url):
            if "bad" in url:
                raise httpx.HTTPStatusError(
                    "503", request=MagicMock(), response=MagicMock(status_code=503)
                )
            return {"objects": []}

        with patch.object(svc, "extract_rates_from_url", side_effect=_flaky_extract):
            with patch("services.rate_scraper_service._RATE_LIMIT_SLEEP_S", 0.001):
                batch = await svc.scrape_supplier_rates(
                    [
                        {"supplier_id": "ok1", "url": "https://good.com"},
                        {"supplier_id": "fail1", "url": "https://bad.com"},
                        {"supplier_id": "ok2", "url": "https://good2.com"},
                    ]
                )

        assert batch["total"] == 3
        assert batch["succeeded"] == 2
        assert batch["failed"] == 1
        assert len(batch["errors"]) == 1
        assert batch["errors"][0]["supplier_id"] == "fail1"

        by_id = {r["supplier_id"]: r for r in batch["results"]}
        assert by_id["ok1"]["success"] is True
        assert by_id["fail1"]["success"] is False
        assert by_id["ok2"]["success"] is True

    @pytest.mark.asyncio
    async def test_per_supplier_timeout_recorded(self):
        """Suppliers that exceed the per-call timeout are recorded with success=False."""
        from services.rate_scraper_service import RateScraperService

        svc = RateScraperService.__new__(RateScraperService)
        svc._token = "tok"

        async def _hung_extract(url):
            # Simulate a hung connection: sleep longer than the patched timeout.
            # We use the real asyncio.sleep here (not the module-level mock) so
            # asyncio.wait_for can actually cancel this coroutine.
            await asyncio.sleep(10)

        # Patch only the rate-limit sleep in the service module (the one called
        # after releasing the semaphore); leave the real asyncio.wait_for + real
        # asyncio.sleep so the cancellation path works correctly.
        with patch.object(svc, "extract_rates_from_url", side_effect=_hung_extract):
            with patch("services.rate_scraper_service._PER_SUPPLIER_TIMEOUT_S", 0.01):
                # Zero-out the post-call rate-limit sleep so the test completes fast
                with patch("services.rate_scraper_service._RATE_LIMIT_SLEEP_S", 0.001):
                    batch = await svc.scrape_supplier_rates(
                        [{"supplier_id": "hung1", "url": "https://slow.com"}]
                    )

        assert batch["total"] == 1
        assert batch["succeeded"] == 0
        assert batch["failed"] == 1
        assert batch["errors"][0]["supplier_id"] == "hung1"
        assert batch["errors"][0]["error"] == "timeout"
        assert batch["results"][0]["success"] is False
        assert batch["results"][0].get("error") == "timeout"

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_summary(self):
        """An empty supplier list returns a zero summary without calling Diffbot."""
        from services.rate_scraper_service import RateScraperService

        svc = RateScraperService.__new__(RateScraperService)
        svc._token = "tok"

        with patch.object(svc, "extract_rates_from_url", new=AsyncMock()) as mock_extract:
            batch = await svc.scrape_supplier_rates([])

        assert batch == {"total": 0, "succeeded": 0, "failed": 0, "errors": [], "results": []}
        mock_extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_token_returns_none_for_extracted_data(self):
        """When DIFFBOT_API_TOKEN is not configured, extract returns None gracefully."""
        from services.rate_scraper_service import RateScraperService

        svc = RateScraperService.__new__(RateScraperService)
        svc._token = ""  # empty = not configured

        # Patch the rate-limit sleep to avoid a 12-second wait in unit tests
        with patch("services.rate_scraper_service._RATE_LIMIT_SLEEP_S", 0.001):
            batch = await svc.scrape_supplier_rates(
                [{"supplier_id": "s1", "url": "https://example.com"}]
            )

        assert batch["total"] == 1
        assert batch["failed"] == 1
        # extract_rates_from_url returns None when not configured — the service
        # treats data=None as not-successful.
        assert batch["results"][0]["extracted_data"] is None
        assert batch["results"][0]["success"] is False

    @pytest.mark.asyncio
    async def test_concurrency_respects_semaphore_limit(self):
        """Peak concurrent calls must not exceed max_concurrency."""
        import asyncio as _asyncio
        from services.rate_scraper_service import RateScraperService

        svc = RateScraperService.__new__(RateScraperService)
        svc._token = "tok"

        peak_concurrent = 0
        current_concurrent = 0

        async def _counting_extract(url):
            nonlocal peak_concurrent, current_concurrent
            current_concurrent += 1
            peak_concurrent = max(peak_concurrent, current_concurrent)
            await _asyncio.sleep(0.01)  # tiny delay so concurrency overlaps
            current_concurrent -= 1
            return {"objects": []}

        with patch.object(svc, "extract_rates_from_url", side_effect=_counting_extract):
            with patch("services.rate_scraper_service._RATE_LIMIT_SLEEP_S", 0.001):
                # 10 suppliers with max_concurrency=3
                suppliers = [
                    {"supplier_id": f"s{i}", "url": f"https://s{i}.com"}
                    for i in range(10)
                ]
                await svc.scrape_supplier_rates(suppliers, max_concurrency=3)

        assert peak_concurrent <= 3, (
            f"Peak concurrent calls ({peak_concurrent}) exceeded semaphore limit (3)"
        )

    @pytest.mark.asyncio
    async def test_summary_response_format_complete(self):
        """scrape_supplier_rates always returns all required summary keys."""
        from services.rate_scraper_service import RateScraperService

        svc = RateScraperService.__new__(RateScraperService)
        svc._token = "tok"

        async def _mixed_extract(url):
            if "fail" in url:
                raise RuntimeError("Connection refused")
            return {"objects": []}

        with patch.object(svc, "extract_rates_from_url", side_effect=_mixed_extract):
            with patch("services.rate_scraper_service._RATE_LIMIT_SLEEP_S", 0.001):
                batch = await svc.scrape_supplier_rates(
                    [
                        {"supplier_id": "good", "url": "https://good.com"},
                        {"supplier_id": "bad", "url": "https://fail.com"},
                    ]
                )

        # All summary keys must be present
        required_keys = {"total", "succeeded", "failed", "errors", "results"}
        assert required_keys == set(batch.keys())

        # Counts must add up correctly
        assert batch["total"] == batch["succeeded"] + batch["failed"]
        assert len(batch["errors"]) == batch["failed"]
        assert len(batch["results"]) == batch["total"]

        # Error entries have supplier_id and error fields
        for err in batch["errors"]:
            assert "supplier_id" in err
            assert "error" in err
