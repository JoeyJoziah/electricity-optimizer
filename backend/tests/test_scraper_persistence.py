"""
Tests for scrape-rates rate extraction and persistence (Phase 4).

Coverage:
  - _extract_rate_from_diffbot_data() unit tests
      - Valid rate found in top-level ``text`` field
      - No rate present → returns None
      - Objects list format (Diffbot nested structure)
      - Multiple keyword variants (rate / price / cost / charge)
      - Various kWh capitalisation variants
      - Empty dict / None guard
      - Rate embedded into extracted_data JSON on persist
  - POST /internal/scrape-rates endpoint integration tests
      - Response includes ``rates_found`` count
      - rates_found = 0 when extracted_data carries no rate text
      - rates_found matches number of results with detectable rates
      - Extracted rate is embedded as ``_detected_rate_kwh`` in stored JSON
      - Endpoint still returns 200 and ``rates_found`` when no results persist

All DB calls are mocked; no real Postgres connection is required.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

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
    db = AsyncMock()
    db.execute = AsyncMock(return_value=None)
    db.commit = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    return AsyncMock()


@pytest.fixture
def auth_client(mock_db, mock_redis_client):
    """TestClient with API key bypassed and DB/Redis mocked."""
    from main import app

    app.dependency_overrides[verify_api_key] = lambda: True
    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis_client

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_redis, None)


# =============================================================================
# Unit tests: _extract_rate_from_diffbot_data()
# =============================================================================


class TestExtractRateFromDiffbotData:
    """Unit tests for the _extract_rate_from_diffbot_data() helper."""

    def _fn(self, data):
        """Import lazily so tests don't depend on module-load order."""
        from api.v1.internal.data_pipeline import \
            _extract_rate_from_diffbot_data

        return _extract_rate_from_diffbot_data(data)

    # ----- happy paths -------------------------------------------------------

    def test_extracts_rate_from_top_level_text(self):
        """Rate keyword + value in the ``text`` field is returned as a float."""
        data = {"text": "Current rate: $0.1234 per kWh for residential customers."}
        result = self._fn(data)
        assert result == pytest.approx(0.1234, abs=1e-6)

    def test_extracts_rate_keyword_price(self):
        """The 'price' keyword variant triggers extraction."""
        data = {"text": "Price: 0.1500 kWh — all inclusive."}
        result = self._fn(data)
        assert result == pytest.approx(0.1500, abs=1e-6)

    def test_extracts_rate_keyword_cost(self):
        """The 'cost' keyword variant triggers extraction."""
        data = {"text": "Energy cost 0.2199 /kWh before taxes."}
        result = self._fn(data)
        assert result == pytest.approx(0.2199, abs=1e-6)

    def test_extracts_rate_keyword_charge(self):
        """The 'charge' keyword variant triggers extraction."""
        data = {"text": "Supply charge: $0.0950 per KWH."}
        result = self._fn(data)
        assert result == pytest.approx(0.0950, abs=1e-6)

    def test_case_insensitive_kwh(self):
        """kWh / kwh / KWH are all recognised."""
        for kwh_variant in ("kWh", "kwh", "KWH"):
            data = {"text": f"Rate: 0.1111 per {kwh_variant}"}
            result = self._fn(data)
            assert result == pytest.approx(
                0.1111, abs=1e-6
            ), f"Failed for kWh variant '{kwh_variant}'"

    def test_extracts_from_objects_list(self):
        """When ``text`` is absent, concatenated object texts are searched."""
        data = {
            "objects": [
                {"type": "article", "text": "Company overview and service areas."},
                {
                    "type": "price",
                    "text": "Electricity rate: 0.1350 /kWh during off-peak.",
                },
            ]
        }
        result = self._fn(data)
        assert result == pytest.approx(0.1350, abs=1e-6)

    def test_objects_list_only_uses_objects_with_text(self):
        """Objects without ``text`` are safely skipped."""
        data = {
            "objects": [
                {"type": "image", "url": "https://example.com/img.png"},  # no text
                {"type": "price", "text": "Charge $0.0888 per kWh"},
            ]
        }
        result = self._fn(data)
        assert result == pytest.approx(0.0888, abs=1e-6)

    def test_top_level_text_takes_precedence_over_objects(self):
        """Top-level ``text`` is preferred over the ``objects`` list."""
        data = {
            "text": "Rate: 0.2000 per kWh",
            "objects": [{"text": "rate: 0.9999 per kWh"}],  # should NOT be used
        }
        result = self._fn(data)
        assert result == pytest.approx(0.2000, abs=1e-6)

    # ----- no-match / edge cases ---------------------------------------------

    def test_no_rate_text_returns_none(self):
        """Plain text with no rate pattern → None."""
        data = {"text": "We provide reliable electricity to homes and businesses."}
        result = self._fn(data)
        assert result is None

    def test_empty_dict_returns_none(self):
        """Empty dict is handled without error."""
        assert self._fn({}) is None

    def test_none_input_returns_none(self):
        """None input is handled without error."""
        assert self._fn(None) is None

    def test_empty_text_field_returns_none(self):
        """Explicit empty string for ``text`` returns None."""
        data = {"text": ""}
        assert self._fn(data) is None

    def test_objects_list_all_no_text_returns_none(self):
        """Objects list where no object has text → None (no crash)."""
        data = {
            "objects": [
                {"type": "image", "url": "https://example.com/img.png"},
                {"type": "video", "src": "https://example.com/vid.mp4"},
            ]
        }
        assert self._fn(data) is None

    def test_empty_objects_list_returns_none(self):
        """Empty objects list with no top-level text → None."""
        data = {"objects": []}
        assert self._fn(data) is None

    def test_rate_without_keyword_returns_none(self):
        """A bare currency value with /kWh but no keyword is not matched."""
        data = {"text": "0.1234 /kWh"}
        # The regex requires a keyword before the value
        assert self._fn(data) is None

    def test_malformed_rate_number_returns_none(self):
        """Rate text where the captured group cannot be cast to float → None.

        This path is practically unreachable with the current regex (it only
        captures digit+dot+digit sequences), but the try/except in the
        implementation should handle it gracefully.
        """
        # Use monkeypatching to inject a bad capture group
        import re

        from api.v1.internal.data_pipeline import \
            _extract_rate_from_diffbot_data

        original_search = re.search

        def _bad_search(pattern, text, flags=0):
            m = original_search(pattern, text, flags)
            if m:
                bad = MagicMock()
                bad.group.return_value = "not_a_float"
                return bad
            return None

        with patch("api.v1.internal.data_pipeline.re.search", side_effect=_bad_search):
            # Provide text that would normally match
            data = {"text": "Rate: 0.1234 per kWh"}
            result = _extract_rate_from_diffbot_data(data)
        assert result is None


# =============================================================================
# Integration tests: POST /internal/scrape-rates (rates_found field)
# =============================================================================


class TestScrapeRatesRateExtraction:
    """Endpoint tests verifying the ``rates_found`` field in the response."""

    @patch("services.rate_scraper_service.RateScraperService")
    def test_rates_found_zero_when_no_rate_text(
        self, mock_svc_cls, auth_client, mock_db
    ):
        """When extracted_data has no rate text, rates_found must be 0."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(
            return_value={
                "total": 1,
                "succeeded": 1,
                "failed": 0,
                "errors": [],
                "results": [
                    {
                        "supplier_id": "s1",
                        "success": True,
                        "extracted_data": {"text": "Welcome to our energy portal."},
                    }
                ],
            }
        )
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": [{"supplier_id": "s1", "url": "https://s1.com"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["rates_found"] == 0

    @patch("services.rate_scraper_service.RateScraperService")
    def test_rates_found_one_when_single_rate_detected(
        self, mock_svc_cls, auth_client, mock_db
    ):
        """When one result has a detectable rate, rates_found = 1."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(
            return_value={
                "total": 1,
                "succeeded": 1,
                "failed": 0,
                "errors": [],
                "results": [
                    {
                        "supplier_id": "s1",
                        "success": True,
                        "extracted_data": {
                            "text": "Current rate: $0.1250 per kWh for all residential plans."
                        },
                    }
                ],
            }
        )
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": [{"supplier_id": "s1", "url": "https://s1.com"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["rates_found"] == 1

    @patch("services.rate_scraper_service.RateScraperService")
    def test_rates_found_counts_only_results_with_detectable_rates(
        self, mock_svc_cls, auth_client, mock_db
    ):
        """Mixed batch: only suppliers with rate text in extracted_data count."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(
            return_value={
                "total": 3,
                "succeeded": 3,
                "failed": 0,
                "errors": [],
                "results": [
                    {
                        "supplier_id": "s1",
                        "success": True,
                        "extracted_data": {"text": "Price: 0.1100 kWh residential."},
                    },
                    {
                        "supplier_id": "s2",
                        "success": True,
                        "extracted_data": {"text": "No pricing information available."},
                    },
                    {
                        "supplier_id": "s3",
                        "success": True,
                        "extracted_data": {
                            "objects": [{"text": "Charge: $0.0990 per kWh commercial."}]
                        },
                    },
                ],
            }
        )
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={
                "supplier_urls": [
                    {"supplier_id": "s1", "url": "https://s1.com"},
                    {"supplier_id": "s2", "url": "https://s2.com"},
                    {"supplier_id": "s3", "url": "https://s3.com"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["rates_found"] == 2  # s1 + s3, not s2

    @patch("services.rate_scraper_service.RateScraperService")
    def test_rates_found_zero_when_all_results_fail(
        self, mock_svc_cls, auth_client, mock_db
    ):
        """Failed scrapes (success=False, extracted_data=None) → rates_found = 0."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(
            return_value={
                "total": 2,
                "succeeded": 0,
                "failed": 2,
                "errors": [
                    {"supplier_id": "a", "error": "timeout"},
                    {"supplier_id": "b", "error": "HTTP 503"},
                ],
                "results": [
                    {"supplier_id": "a", "success": False, "extracted_data": None},
                    {"supplier_id": "b", "success": False, "extracted_data": None},
                ],
            }
        )
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={
                "supplier_urls": [
                    {"supplier_id": "a", "url": "https://a.com"},
                    {"supplier_id": "b", "url": "https://b.com"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["rates_found"] == 0

    @patch("services.rate_scraper_service.RateScraperService")
    def test_response_always_includes_rates_found_key(
        self, mock_svc_cls, auth_client, mock_db
    ):
        """The ``rates_found`` key must always be present in the response body."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(
            return_value={
                "total": 1,
                "succeeded": 1,
                "failed": 0,
                "errors": [],
                "results": [
                    {"supplier_id": "x", "success": True, "extracted_data": {}}
                ],
            }
        )
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": [{"supplier_id": "x", "url": "https://x.com"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert "rates_found" in data, "Response is missing the 'rates_found' key"

    @patch("services.rate_scraper_service.RateScraperService")
    def test_detected_rate_embedded_in_extracted_data_json(
        self, mock_svc_cls, auth_client, mock_db
    ):
        """When a rate is detected it must be stored as ``_detected_rate_kwh``
        in the serialised extracted_data JSON that is inserted into the DB."""
        captured_rows: list[dict] = []

        async def _fake_persist_batch(db, table, sql, rows, log_context=""):
            """Capture what would be persisted."""
            captured_rows.extend(rows)
            return len(rows)

        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(
            return_value={
                "total": 1,
                "succeeded": 1,
                "failed": 0,
                "errors": [],
                "results": [
                    {
                        "supplier_id": "s1",
                        "success": True,
                        "extracted_data": {
                            "text": "Rate: $0.1375 per kWh residential."
                        },
                    }
                ],
            }
        )
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=None)

        with patch(
            "api.v1.internal.data_pipeline.persist_batch",
            side_effect=_fake_persist_batch,
        ):
            response = auth_client.post(
                f"{BASE_URL}/scrape-rates",
                json={
                    "supplier_urls": [{"supplier_id": "s1", "url": "https://s1.com"}]
                },
            )

        assert response.status_code == 200
        assert len(captured_rows) == 1

        stored_data = json.loads(captured_rows[0]["data"])
        assert (
            "_detected_rate_kwh" in stored_data
        ), "Expected _detected_rate_kwh to be embedded in stored extracted_data"
        assert stored_data["_detected_rate_kwh"] == pytest.approx(0.1375, abs=1e-6)

    @patch("services.rate_scraper_service.RateScraperService")
    def test_no_detection_key_when_rate_not_found(
        self, mock_svc_cls, auth_client, mock_db
    ):
        """When no rate is detected, ``_detected_rate_kwh`` must NOT be embedded."""
        captured_rows: list[dict] = []

        async def _fake_persist_batch(db, table, sql, rows, log_context=""):
            captured_rows.extend(rows)
            return len(rows)

        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(
            return_value={
                "total": 1,
                "succeeded": 1,
                "failed": 0,
                "errors": [],
                "results": [
                    {
                        "supplier_id": "s1",
                        "success": True,
                        "extracted_data": {"text": "No pricing info here."},
                    }
                ],
            }
        )
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=None)

        with patch(
            "api.v1.internal.data_pipeline.persist_batch",
            side_effect=_fake_persist_batch,
        ):
            response = auth_client.post(
                f"{BASE_URL}/scrape-rates",
                json={
                    "supplier_urls": [{"supplier_id": "s1", "url": "https://s1.com"}]
                },
            )

        assert response.status_code == 200
        assert len(captured_rows) == 1
        stored_data = json.loads(captured_rows[0]["data"])
        assert "_detected_rate_kwh" not in stored_data

    @patch("services.rate_scraper_service.RateScraperService")
    def test_rates_found_in_objects_list_format(
        self, mock_svc_cls, auth_client, mock_db
    ):
        """Diffbot nested objects-list format is handled for rate extraction."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(
            return_value={
                "total": 1,
                "succeeded": 1,
                "failed": 0,
                "errors": [],
                "results": [
                    {
                        "supplier_id": "s1",
                        "success": True,
                        "extracted_data": {
                            "objects": [
                                {"type": "header", "text": "Electricity Plans"},
                                {
                                    "type": "content",
                                    "text": "Charge: $0.0950 per kWh for all plans.",
                                },
                            ]
                        },
                    }
                ],
            }
        )
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": [{"supplier_id": "s1", "url": "https://s1.com"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["rates_found"] == 1

    @patch("services.rate_scraper_service.RateScraperService")
    def test_rates_found_zero_when_no_results(self, mock_svc_cls, auth_client, mock_db):
        """Empty results list → rates_found = 0 (no KeyError on empty batch)."""
        mock_svc = MagicMock()
        mock_svc.scrape_supplier_rates = AsyncMock(
            return_value={
                "total": 0,
                "succeeded": 0,
                "failed": 0,
                "errors": [],
                "results": [],
            }
        )
        mock_svc_cls.return_value = mock_svc
        mock_db.execute = AsyncMock(return_value=None)

        response = auth_client.post(
            f"{BASE_URL}/scrape-rates",
            json={"supplier_urls": [{"supplier_id": "s1", "url": "https://s1.com"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["rates_found"] == 0
