"""Tests for the Water Rate API (backend/api/v1/water.py).

Mounted at: /api/v1/rates/water  (public, no auth)

Covers:
- GET /rates/water           (all rates; state filter; municipality+state → single; not found → 404)
- GET /rates/water/benchmark (valid state; no data → 404; usage_gallons max 100000)
- GET /rates/water/tips      (returns tips list with count)
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session

_BASE = "/api/v1/rates/water"

_RATE = {
    "state": "CT",
    "municipality": "New Haven",
    "rate_per_gallon": 0.005,
    "monthly_base_fee": 12.0,
}

_BENCHMARK = {
    "state": "CT",
    "municipalities": 5,
    "avg_rate_per_gallon": 0.0052,
    "min_rate": 0.0043,
    "max_rate": 0.0065,
}

_TIPS = [
    {
        "tip": "Fix leaky faucets",
        "estimated_savings_gallons": 3000,
        "difficulty": "easy",
    },
    {
        "tip": "Install low-flow showerhead",
        "estimated_savings_gallons": 7000,
        "difficulty": "easy",
    },
]


@pytest.fixture
def client():
    from main import app

    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_db_session, None)


# ---------------------------------------------------------------------------
# GET /rates/water
# ---------------------------------------------------------------------------


class TestGetWaterRates:
    def test_returns_all_rates(self, client):
        with patch(
            "services.water_rate_service.WaterRateService.get_rates",
            new=AsyncMock(return_value=[_RATE]),
        ):
            resp = client.get(_BASE)
        assert resp.status_code == 200
        body = resp.json()
        assert "rates" in body
        assert body["count"] == 1

    def test_state_filter_passed_to_service(self, client):
        with patch(
            "services.water_rate_service.WaterRateService.get_rates",
            new=AsyncMock(return_value=[]),
        ) as mock_svc:
            resp = client.get(f"{_BASE}?state=CT")
        assert resp.status_code == 200
        mock_svc.assert_awaited_once_with("CT")

    def test_municipality_and_state_returns_single(self, client):
        with patch(
            "services.water_rate_service.WaterRateService.get_rate_by_municipality",
            new=AsyncMock(return_value=_RATE),
        ):
            resp = client.get(f"{_BASE}?state=CT&municipality=New+Haven")
        assert resp.status_code == 200
        assert resp.json()["rates"][0]["municipality"] == "New Haven"

    def test_municipality_not_found_returns_404(self, client):
        with patch(
            "services.water_rate_service.WaterRateService.get_rate_by_municipality",
            new=AsyncMock(return_value=None),
        ):
            resp = client.get(f"{_BASE}?state=CT&municipality=Nowhereville")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /rates/water/benchmark
# ---------------------------------------------------------------------------


class TestGetWaterBenchmark:
    def test_valid_state_returns_benchmark(self, client):
        with patch(
            "services.water_rate_service.WaterRateService.get_benchmark",
            new=AsyncMock(return_value=_BENCHMARK),
        ):
            resp = client.get(f"{_BASE}/benchmark?state=CT")
        assert resp.status_code == 200
        body = resp.json()
        assert body["municipalities"] == 5

    def test_no_data_for_state_returns_404(self, client):
        with patch(
            "services.water_rate_service.WaterRateService.get_benchmark",
            new=AsyncMock(return_value={**_BENCHMARK, "municipalities": 0}),
        ):
            resp = client.get(f"{_BASE}/benchmark?state=XX")
        assert resp.status_code == 404

    def test_usage_gallons_over_max_returns_422(self, client):
        resp = client.get(f"{_BASE}/benchmark?state=CT&usage_gallons=100001")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /rates/water/tips
# ---------------------------------------------------------------------------


class TestGetWaterTips:
    def test_returns_tips_with_count(self, client):
        with patch(
            "services.water_rate_service.WaterRateService.get_conservation_tips",
            return_value=_TIPS,
        ):
            resp = client.get(f"{_BASE}/tips")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert "estimated_annual_savings_gallons" in body
