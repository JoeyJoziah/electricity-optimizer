"""
Tests for Price Analytics API endpoints (backend/api/v1/prices_analytics.py)

Covers:
- GET /api/v1/prices/statistics  — valid response, invalid params (422)
- GET /api/v1/prices/optimal-windows — valid response, param validation
- GET /api/v1/prices/trends — valid response
- GET /api/v1/prices/peak-hours — valid response

All endpoints use the PriceService / AnalyticsService dependency; those are
replaced with lightweight async mocks so no real DB or Redis is required.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_db_session, TokenData


# ---------------------------------------------------------------------------
# Mock service helpers
# ---------------------------------------------------------------------------


class _MockPriceService:
    """Minimal async stand-in for PriceService."""

    async def get_price_statistics(self, region, days):
        return {
            "min_price": 0.15,
            "max_price": 0.28,
            "avg_price": 0.21,
            "count": days * 24,
        }

    async def get_optimal_usage_windows(
        self, region, duration_hours, within_hours, supplier=None
    ):
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        return [
            {
                "start": (now + timedelta(hours=2)).isoformat(),
                "end": (now + timedelta(hours=2 + duration_hours)).isoformat(),
                "avg_price": 0.16,
                "rank": 1,
            },
            {
                "start": (now + timedelta(hours=14)).isoformat(),
                "end": (now + timedelta(hours=14 + duration_hours)).isoformat(),
                "avg_price": 0.19,
                "rank": 2,
            },
        ]


class _MockAnalyticsService:
    """Minimal async stand-in for AnalyticsService."""

    async def get_price_trend(self, region, days):
        return {
            "direction": "down",
            "change_percent": -2.3,
            "current_avg": 0.21,
            "previous_avg": 0.215,
        }

    async def get_peak_hours_analysis(self, region, days):
        return {
            "peak_hours": list(range(7, 20)),
            "off_peak_hours": list(range(0, 7)) + list(range(20, 24)),
            "peak_avg_price": 0.25,
            "off_peak_avg_price": 0.16,
        }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def analytics_client():
    """
    TestClient with:
    - Authenticated user (via get_current_user override)
    - No-op DB session (via get_db_session override)
    - Mocked PriceService and AnalyticsService injected at the dependency level
    """
    from main import app
    from api.dependencies import get_price_service, get_analytics_service

    test_user = TokenData(user_id="user-analytics-1", email="analytics@test.com")

    mock_price_svc = _MockPriceService()
    mock_analytics_svc = _MockAnalyticsService()

    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db_session] = lambda: MagicMock()
    app.dependency_overrides[get_price_service] = lambda: mock_price_svc
    app.dependency_overrides[get_analytics_service] = lambda: mock_analytics_svc

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_price_service, None)
    app.dependency_overrides.pop(get_analytics_service, None)


# ---------------------------------------------------------------------------
# GET /api/v1/prices/statistics
# ---------------------------------------------------------------------------


class TestPriceStatistics:
    """Tests for GET /api/v1/prices/statistics."""

    def test_statistics_returns_200(self, analytics_client):
        """Valid region returns 200 with expected statistics fields."""
        response = analytics_client.get(
            "/api/v1/prices/statistics", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["region"] == "us_ct"
        assert "min_price" in data
        assert "max_price" in data
        assert "avg_price" in data
        assert "count" in data
        assert "period_days" in data

    def test_statistics_default_days(self, analytics_client):
        """Omitting days param should default to 7 days (count = 168)."""
        response = analytics_client.get(
            "/api/v1/prices/statistics", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 7
        assert data["count"] == 7 * 24  # mock returns days * 24

    def test_statistics_custom_days(self, analytics_client):
        """Explicit days param should be reflected in response."""
        response = analytics_client.get(
            "/api/v1/prices/statistics", params={"region": "us_ct", "days": 14}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 14
        assert data["count"] == 14 * 24

    def test_statistics_missing_region_returns_422(self, analytics_client):
        """Omitting required region param should return 422 Unprocessable Entity."""
        response = analytics_client.get("/api/v1/prices/statistics")
        assert response.status_code == 422

    def test_statistics_invalid_region_returns_422(self, analytics_client):
        """An unrecognised region value should fail PriceRegion enum validation."""
        response = analytics_client.get(
            "/api/v1/prices/statistics", params={"region": "notaregion"}
        )
        assert response.status_code == 422

    def test_statistics_days_below_minimum_returns_422(self, analytics_client):
        """days < 1 should fail ge=1 validation."""
        response = analytics_client.get(
            "/api/v1/prices/statistics", params={"region": "us_ct", "days": 0}
        )
        assert response.status_code == 422

    def test_statistics_days_above_maximum_returns_422(self, analytics_client):
        """days > 365 should fail le=365 validation."""
        response = analytics_client.get(
            "/api/v1/prices/statistics", params={"region": "us_ct", "days": 366}
        )
        assert response.status_code == 422

    def test_statistics_source_field_present(self, analytics_client):
        """Response should include a source field (live or fallback)."""
        response = analytics_client.get(
            "/api/v1/prices/statistics", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        assert "source" in response.json()


# ---------------------------------------------------------------------------
# GET /api/v1/prices/optimal-windows
# ---------------------------------------------------------------------------


class TestOptimalWindows:
    """Tests for GET /api/v1/prices/optimal-windows."""

    def test_optimal_windows_returns_200(self, analytics_client):
        """Valid request should return 200 with windows list."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["region"] == "us_ct"
        assert "windows" in data
        assert isinstance(data["windows"], list)

    def test_optimal_windows_contains_expected_keys(self, analytics_client):
        """Each window entry should have start, end, avg_price, and rank."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        windows = response.json()["windows"]
        assert len(windows) > 0
        first = windows[0]
        assert "start" in first
        assert "end" in first
        assert "avg_price" in first
        assert "rank" in first

    def test_optimal_windows_duration_param(self, analytics_client):
        """Custom duration_hours should be reflected in response."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows",
            params={"region": "us_ct", "duration_hours": 4},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["duration_hours"] == 4

    def test_optimal_windows_within_hours_param(self, analytics_client):
        """Custom within_hours should be reflected in response."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows",
            params={"region": "us_ct", "within_hours": 48},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["within_hours"] == 48

    def test_optimal_windows_missing_region_returns_422(self, analytics_client):
        """Omitting region should return 422."""
        response = analytics_client.get("/api/v1/prices/optimal-windows")
        assert response.status_code == 422

    def test_optimal_windows_duration_below_minimum_returns_422(
        self, analytics_client
    ):
        """duration_hours < 1 should fail ge=1 validation."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows",
            params={"region": "us_ct", "duration_hours": 0},
        )
        assert response.status_code == 422

    def test_optimal_windows_duration_above_maximum_returns_422(
        self, analytics_client
    ):
        """duration_hours > 12 should fail le=12 validation."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows",
            params={"region": "us_ct", "duration_hours": 13},
        )
        assert response.status_code == 422

    def test_optimal_windows_generated_at_present(self, analytics_client):
        """Response should include a generated_at timestamp."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        assert "generated_at" in response.json()


# ---------------------------------------------------------------------------
# GET /api/v1/prices/trends
# ---------------------------------------------------------------------------


class TestPriceTrends:
    """Tests for GET /api/v1/prices/trends."""

    def test_trends_returns_200(self, analytics_client):
        """Valid request should return 200 with trend data."""
        response = analytics_client.get(
            "/api/v1/prices/trends", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["region"] == "us_ct"

    def test_trends_contains_direction(self, analytics_client):
        """Response should include a trend direction."""
        response = analytics_client.get(
            "/api/v1/prices/trends", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "direction" in data
        assert data["direction"] in ("up", "down", "stable")

    def test_trends_contains_change_percent(self, analytics_client):
        """Response should include a numeric change_percent field."""
        response = analytics_client.get(
            "/api/v1/prices/trends", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "change_percent" in data
        assert isinstance(data["change_percent"], (int, float))

    def test_trends_period_days_reflected(self, analytics_client):
        """Custom days param should be reflected in response."""
        response = analytics_client.get(
            "/api/v1/prices/trends", params={"region": "us_ct", "days": 30}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 30

    def test_trends_missing_region_returns_422(self, analytics_client):
        """Omitting region should return 422."""
        response = analytics_client.get("/api/v1/prices/trends")
        assert response.status_code == 422

    def test_trends_invalid_region_returns_422(self, analytics_client):
        """Invalid region value should fail enum validation."""
        response = analytics_client.get(
            "/api/v1/prices/trends", params={"region": "invalid_region"}
        )
        assert response.status_code == 422

    def test_trends_days_above_maximum_returns_422(self, analytics_client):
        """days > 90 should fail le=90 validation."""
        response = analytics_client.get(
            "/api/v1/prices/trends", params={"region": "us_ct", "days": 91}
        )
        assert response.status_code == 422

    def test_trends_generated_at_present(self, analytics_client):
        """Response should include a generated_at timestamp."""
        response = analytics_client.get(
            "/api/v1/prices/trends", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        assert "generated_at" in response.json()

    def test_trends_source_field_present(self, analytics_client):
        """Response should include a source field."""
        response = analytics_client.get(
            "/api/v1/prices/trends", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        assert "source" in response.json()


# ---------------------------------------------------------------------------
# GET /api/v1/prices/peak-hours
# ---------------------------------------------------------------------------


class TestPeakHours:
    """Tests for GET /api/v1/prices/peak-hours."""

    def test_peak_hours_returns_200(self, analytics_client):
        """Valid request should return 200 with peak-hour analysis."""
        response = analytics_client.get(
            "/api/v1/prices/peak-hours", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["region"] == "us_ct"

    def test_peak_hours_contains_expected_keys(self, analytics_client):
        """Response should include peak_hours, off_peak_hours and price averages."""
        response = analytics_client.get(
            "/api/v1/prices/peak-hours", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "peak_hours" in data
        assert "off_peak_hours" in data
        assert "peak_avg_price" in data
        assert "off_peak_avg_price" in data

    def test_peak_hours_lists_are_lists(self, analytics_client):
        """peak_hours and off_peak_hours should be lists of integers."""
        response = analytics_client.get(
            "/api/v1/prices/peak-hours", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["peak_hours"], list)
        assert isinstance(data["off_peak_hours"], list)

    def test_peak_hours_period_days_reflected(self, analytics_client):
        """Custom days param should be reflected in response."""
        response = analytics_client.get(
            "/api/v1/prices/peak-hours", params={"region": "us_ct", "days": 14}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 14

    def test_peak_hours_missing_region_returns_422(self, analytics_client):
        """Omitting region should return 422."""
        response = analytics_client.get("/api/v1/prices/peak-hours")
        assert response.status_code == 422

    def test_peak_hours_invalid_region_returns_422(self, analytics_client):
        """Invalid region value should fail enum validation."""
        response = analytics_client.get(
            "/api/v1/prices/peak-hours", params={"region": "bad_region"}
        )
        assert response.status_code == 422

    def test_peak_hours_days_above_maximum_returns_422(self, analytics_client):
        """days > 30 should fail le=30 validation."""
        response = analytics_client.get(
            "/api/v1/prices/peak-hours", params={"region": "us_ct", "days": 31}
        )
        assert response.status_code == 422

    def test_peak_hours_days_below_minimum_returns_422(self, analytics_client):
        """days < 1 should fail ge=1 validation."""
        response = analytics_client.get(
            "/api/v1/prices/peak-hours", params={"region": "us_ct", "days": 0}
        )
        assert response.status_code == 422

    def test_peak_hours_generated_at_present(self, analytics_client):
        """Response should include a generated_at timestamp."""
        response = analytics_client.get(
            "/api/v1/prices/peak-hours", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        assert "generated_at" in response.json()

    def test_peak_off_peak_hours_cover_full_day(self, analytics_client):
        """Combined peak and off-peak hours should cover all 24 hours."""
        response = analytics_client.get(
            "/api/v1/prices/peak-hours", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        data = response.json()
        all_hours = set(data["peak_hours"]) | set(data["off_peak_hours"])
        assert all_hours == set(range(24))


# ---------------------------------------------------------------------------
# Pagination — GET /api/v1/prices/optimal-windows
# ---------------------------------------------------------------------------


class TestOptimalWindowsPagination:
    """Tests for page/page_size pagination on /optimal-windows."""

    def test_pagination_fields_present_in_response(self, analytics_client):
        """Response should include total, page, and page_size fields."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    def test_default_page_is_one(self, analytics_client):
        """Omitting page should default to page 1."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        assert response.json()["page"] == 1

    def test_default_page_size_is_twenty(self, analytics_client):
        """Omitting page_size should default to 20."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows", params={"region": "us_ct"}
        )
        assert response.status_code == 200
        assert response.json()["page_size"] == 20

    def test_custom_page_size_reflected(self, analytics_client):
        """Custom page_size should appear in response and cap returned items."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows",
            params={"region": "us_ct", "page_size": 1},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page_size"] == 1
        assert len(data["windows"]) <= 1

    def test_page_two_returns_empty_when_beyond_total(self, analytics_client):
        """Requesting page 2 when total results <= page_size yields an empty windows list."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows",
            params={"region": "us_ct", "page": 2, "page_size": 20},
        )
        assert response.status_code == 200
        data = response.json()
        # The mock service returns 2 windows; page 2 with page_size=20 is empty
        assert data["windows"] == []
        assert data["page"] == 2

    def test_page_zero_returns_422(self, analytics_client):
        """page < 1 should fail ge=1 validation."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows",
            params={"region": "us_ct", "page": 0},
        )
        assert response.status_code == 422

    def test_page_size_zero_returns_422(self, analytics_client):
        """page_size < 1 should fail ge=1 validation."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows",
            params={"region": "us_ct", "page_size": 0},
        )
        assert response.status_code == 422

    def test_page_size_above_max_returns_422(self, analytics_client):
        """page_size > 100 should fail le=100 validation."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows",
            params={"region": "us_ct", "page_size": 101},
        )
        assert response.status_code == 422

    def test_page_size_at_max_boundary_returns_200(self, analytics_client):
        """page_size == 100 is the maximum allowed value."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows",
            params={"region": "us_ct", "page_size": 100},
        )
        assert response.status_code == 200
        assert response.json()["page_size"] == 100

    def test_total_reflects_all_windows_not_just_page(self, analytics_client):
        """total should reflect the full result count, not the page slice."""
        response = analytics_client.get(
            "/api/v1/prices/optimal-windows",
            params={"region": "us_ct", "page": 1, "page_size": 1},
        )
        assert response.status_code == 200
        data = response.json()
        # Mock returns 2 windows; total must be 2 regardless of page_size
        assert data["total"] == 2
        assert len(data["windows"]) == 1
