"""
Tests for /api/v1/internal/data-quality/* endpoints.

Coverage:
- GET /freshness — response shape, stale_count derived from entries
- GET /anomalies — response shape, lookback_days echoed, anomaly_count
- GET /sources — response shape, window_hours echoed, degraded_count derived
- Query parameter validation (lookback_days, window_hours bounds)
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _noop_verify_api_key():
    return True


def _make_db_session():
    return AsyncMock()


@pytest.fixture()
def client():
    from api.dependencies import get_db_session, verify_api_key
    from main import app

    db_session = _make_db_session()
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[verify_api_key] = _noop_verify_api_key

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(verify_api_key, None)


def _make_freshness_report(entries):
    """Simulate a DataQualityService.get_freshness_report() return."""
    return entries


def _make_anomalies(count):
    return [{"id": i, "deviation": 4.5, "region": "us_ct"} for i in range(count)]


def _make_sources(sources):
    return sources


# ---------------------------------------------------------------------------
# GET /freshness
# ---------------------------------------------------------------------------


class TestFreshnessReport:
    def test_response_shape(self, client):
        report = [
            {"region": "us_ct", "utility_type": "electricity", "is_stale": False},
            {"region": "us_ny", "utility_type": "electricity", "is_stale": True},
        ]
        with patch("api.v1.internal.data_quality.DataQualityService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_freshness_report = AsyncMock(return_value=report)
            response = client.get("/api/v1/internal/data-quality/freshness")

        assert response.status_code == 200
        data = response.json()
        assert "total_entries" in data
        assert "stale_count" in data
        assert "entries" in data

    def test_stale_count_matches_is_stale_entries(self, client):
        report = [
            {"region": "us_ct", "is_stale": False},
            {"region": "us_ny", "is_stale": True},
            {"region": "us_ma", "is_stale": True},
        ]
        with patch("api.v1.internal.data_quality.DataQualityService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_freshness_report = AsyncMock(return_value=report)
            response = client.get("/api/v1/internal/data-quality/freshness")

        data = response.json()
        assert data["total_entries"] == 3
        assert data["stale_count"] == 2

    def test_all_fresh_gives_stale_count_zero(self, client):
        report = [
            {"region": "us_ct", "is_stale": False},
            {"region": "us_ny", "is_stale": False},
        ]
        with patch("api.v1.internal.data_quality.DataQualityService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_freshness_report = AsyncMock(return_value=report)
            response = client.get("/api/v1/internal/data-quality/freshness")

        assert response.json()["stale_count"] == 0

    def test_empty_report_returns_zeros(self, client):
        with patch("api.v1.internal.data_quality.DataQualityService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_freshness_report = AsyncMock(return_value=[])
            response = client.get("/api/v1/internal/data-quality/freshness")

        data = response.json()
        assert data["total_entries"] == 0
        assert data["stale_count"] == 0
        assert data["entries"] == []


# ---------------------------------------------------------------------------
# GET /anomalies
# ---------------------------------------------------------------------------


class TestAnomaliesReport:
    def test_response_shape(self, client):
        with patch("api.v1.internal.data_quality.DataQualityService") as MockSvc:
            instance = MockSvc.return_value
            instance.detect_anomalies = AsyncMock(return_value=[])
            response = client.get("/api/v1/internal/data-quality/anomalies")

        assert response.status_code == 200
        data = response.json()
        assert "lookback_days" in data
        assert "anomaly_count" in data
        assert "anomalies" in data

    def test_default_lookback_days_is_30(self, client):
        with patch("api.v1.internal.data_quality.DataQualityService") as MockSvc:
            instance = MockSvc.return_value
            instance.detect_anomalies = AsyncMock(return_value=[])
            response = client.get("/api/v1/internal/data-quality/anomalies")

        assert response.json()["lookback_days"] == 30

    def test_custom_lookback_days_echoed(self, client):
        with patch("api.v1.internal.data_quality.DataQualityService") as MockSvc:
            instance = MockSvc.return_value
            instance.detect_anomalies = AsyncMock(return_value=[])
            response = client.get("/api/v1/internal/data-quality/anomalies?lookback_days=7")

        assert response.json()["lookback_days"] == 7

    def test_anomaly_count_matches_list_length(self, client):
        anomalies = _make_anomalies(3)
        with patch("api.v1.internal.data_quality.DataQualityService") as MockSvc:
            instance = MockSvc.return_value
            instance.detect_anomalies = AsyncMock(return_value=anomalies)
            response = client.get("/api/v1/internal/data-quality/anomalies")

        data = response.json()
        assert data["anomaly_count"] == 3
        assert len(data["anomalies"]) == 3

    def test_lookback_days_below_min_returns_422(self, client):
        with patch("api.v1.internal.data_quality.DataQualityService") as MockSvc:
            instance = MockSvc.return_value
            instance.detect_anomalies = AsyncMock(return_value=[])
            response = client.get("/api/v1/internal/data-quality/anomalies?lookback_days=0")

        assert response.status_code == 422

    def test_lookback_days_above_max_returns_422(self, client):
        with patch("api.v1.internal.data_quality.DataQualityService") as MockSvc:
            instance = MockSvc.return_value
            instance.detect_anomalies = AsyncMock(return_value=[])
            response = client.get("/api/v1/internal/data-quality/anomalies?lookback_days=366")

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /sources
# ---------------------------------------------------------------------------


class TestSourcesReport:
    def test_response_shape(self, client):
        with patch("api.v1.internal.data_quality.DataQualityService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_source_reliability = AsyncMock(return_value=[])
            response = client.get("/api/v1/internal/data-quality/sources")

        assert response.status_code == 200
        data = response.json()
        assert "window_hours" in data
        assert "total_sources" in data
        assert "degraded_count" in data
        assert "sources" in data

    def test_default_window_hours_is_24(self, client):
        with patch("api.v1.internal.data_quality.DataQualityService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_source_reliability = AsyncMock(return_value=[])
            response = client.get("/api/v1/internal/data-quality/sources")

        assert response.json()["window_hours"] == 24

    def test_degraded_count_derived_from_is_degraded_flag(self, client):
        sources = [
            {"source": "eia", "is_degraded": False},
            {"source": "nrel", "is_degraded": True},
            {"source": "openweather", "is_degraded": True},
        ]
        with patch("api.v1.internal.data_quality.DataQualityService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_source_reliability = AsyncMock(return_value=sources)
            response = client.get("/api/v1/internal/data-quality/sources")

        data = response.json()
        assert data["total_sources"] == 3
        assert data["degraded_count"] == 2

    def test_window_hours_above_max_returns_422(self, client):
        with patch("api.v1.internal.data_quality.DataQualityService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_source_reliability = AsyncMock(return_value=[])
            response = client.get("/api/v1/internal/data-quality/sources?window_hours=721")

        assert response.status_code == 422

    def test_custom_window_hours_echoed(self, client):
        with patch("api.v1.internal.data_quality.DataQualityService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_source_reliability = AsyncMock(return_value=[])
            response = client.get("/api/v1/internal/data-quality/sources?window_hours=48")

        assert response.json()["window_hours"] == 48
