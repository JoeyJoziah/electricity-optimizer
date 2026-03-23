"""
Tests for DataQualityService

Verifies freshness monitoring, anomaly detection, source reliability,
and duplicate detection.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from services.data_quality_service import (
    ANOMALY_STD_THRESHOLD,
    FRESHNESS_ALERT_MULTIPLIER,
    FRESHNESS_THRESHOLDS,
    SOURCE_FAILURE_ALERT_THRESHOLD,
    DataQualityService,
)


class TestFreshnessThresholds:
    """Test freshness threshold configuration."""

    def test_electricity_threshold_is_1_hour(self):
        assert FRESHNESS_THRESHOLDS["electricity"] == 1

    def test_gas_threshold_is_7_days(self):
        assert FRESHNESS_THRESHOLDS["natural_gas"] == 168

    def test_heating_oil_threshold_is_7_days(self):
        assert FRESHNESS_THRESHOLDS["heating_oil"] == 168

    def test_solar_threshold_is_30_days(self):
        assert FRESHNESS_THRESHOLDS["community_solar"] == 720

    def test_alert_multiplier_is_2x(self):
        assert FRESHNESS_ALERT_MULTIPLIER == 2


class TestCheckRateAnomaly:
    """Test static anomaly detection method."""

    def test_normal_rate_is_not_anomaly(self):
        result = DataQualityService.check_rate_anomaly(rate=0.12, avg_rate=0.11, std_rate=0.02)
        assert result["is_anomaly"] is False
        assert result["z_score"] == 0.5

    def test_extreme_rate_is_anomaly(self):
        # $100/kWh when average is $0.12 with std $0.02 → z = 4990
        result = DataQualityService.check_rate_anomaly(rate=100.0, avg_rate=0.12, std_rate=0.02)
        assert result["is_anomaly"] is True
        assert result["z_score"] > ANOMALY_STD_THRESHOLD

    def test_borderline_rate_not_anomaly(self):
        # z_score = 2.9 (below 3.0 threshold)
        result = DataQualityService.check_rate_anomaly(rate=0.178, avg_rate=0.12, std_rate=0.02)
        assert result["is_anomaly"] is False
        assert result["z_score"] < ANOMALY_STD_THRESHOLD

    def test_exactly_at_threshold(self):
        # z_score = 3.0 — not anomaly (> 3.0 required)
        result = DataQualityService.check_rate_anomaly(rate=0.18, avg_rate=0.12, std_rate=0.02)
        assert result["is_anomaly"] is False  # exactly at threshold, not exceeding

    def test_zero_std_is_not_anomaly(self):
        result = DataQualityService.check_rate_anomaly(rate=0.15, avg_rate=0.12, std_rate=0.0)
        assert result["is_anomaly"] is False
        assert result["z_score"] == 0.0

    def test_negative_std_is_not_anomaly(self):
        result = DataQualityService.check_rate_anomaly(rate=0.15, avg_rate=0.12, std_rate=-0.01)
        assert result["is_anomaly"] is False


class TestCheckDuplicate:
    """Test duplicate detection."""

    def test_exact_duplicate_detected(self):
        existing = [{"region": "us_ny", "utility_type": "electricity", "rate": 0.12}]
        assert DataQualityService.check_duplicate(existing, 0.12, "us_ny", "electricity") is True

    def test_near_duplicate_within_tolerance(self):
        existing = [{"region": "us_ny", "utility_type": "electricity", "rate": 0.12}]
        assert (
            DataQualityService.check_duplicate(existing, 0.120005, "us_ny", "electricity") is True
        )

    def test_different_rate_not_duplicate(self):
        existing = [{"region": "us_ny", "utility_type": "electricity", "rate": 0.12}]
        assert DataQualityService.check_duplicate(existing, 0.15, "us_ny", "electricity") is False

    def test_different_region_not_duplicate(self):
        existing = [{"region": "us_ny", "utility_type": "electricity", "rate": 0.12}]
        assert DataQualityService.check_duplicate(existing, 0.12, "us_tx", "electricity") is False

    def test_different_utility_type_not_duplicate(self):
        existing = [{"region": "us_ny", "utility_type": "electricity", "rate": 0.12}]
        assert DataQualityService.check_duplicate(existing, 0.12, "us_ny", "natural_gas") is False

    def test_empty_existing_not_duplicate(self):
        assert DataQualityService.check_duplicate([], 0.12, "us_ny", "electricity") is False


class TestFreshnessReport:
    """Test freshness report with mocked DB."""

    async def test_returns_freshness_entries(self):
        now = datetime.now(UTC)
        mock_db = AsyncMock()

        # Mock DB result
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {
                "utility_type": "electricity",
                "region": "us_ny",
                "last_updated": now - timedelta(minutes=30),
                "record_count": 100,
            },
            {
                "utility_type": "natural_gas",
                "region": "us_ny",
                "last_updated": now - timedelta(days=10),
                "record_count": 50,
            },
        ]
        mock_db.execute.return_value = mock_result

        service = DataQualityService(mock_db)
        report = await service.get_freshness_report()

        assert len(report) == 2

        # Electricity: updated 30min ago, threshold 1h → not stale
        elec = report[0]
        assert elec["utility_type"] == "electricity"
        assert elec["is_stale"] is False
        assert elec["threshold_hours"] == 1

        # Gas: updated 10 days ago, threshold 7d, alert at 14d → not stale
        gas = report[1]
        assert gas["utility_type"] == "natural_gas"
        assert gas["is_stale"] is False
        assert gas["threshold_hours"] == 168

    async def test_stale_data_flagged(self):
        now = datetime.now(UTC)
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {
                "utility_type": "electricity",
                "region": "us_ny",
                "last_updated": now - timedelta(hours=3),  # >2h (2x 1h threshold)
                "record_count": 100,
            },
        ]
        mock_db.execute.return_value = mock_result

        service = DataQualityService(mock_db)
        report = await service.get_freshness_report()

        assert report[0]["is_stale"] is True

    async def test_empty_db_returns_empty(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        service = DataQualityService(mock_db)
        report = await service.get_freshness_report()

        assert report == []


class TestSourceReliability:
    """Test source reliability scoring."""

    async def test_healthy_source(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {
                "source": "eia",
                "total": 100,
                "successes": 95,
                "failures": 5,
                "last_attempt": datetime.now(UTC),
            },
        ]
        mock_db.execute.return_value = mock_result

        service = DataQualityService(mock_db)
        sources = await service.get_source_reliability()

        assert len(sources) == 1
        assert sources[0]["source"] == "eia"
        assert sources[0]["failure_rate"] == 0.05
        assert sources[0]["is_degraded"] is False

    async def test_degraded_source(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {
                "source": "scraper_xy",
                "total": 10,
                "successes": 7,
                "failures": 3,
                "last_attempt": datetime.now(UTC),
            },
        ]
        mock_db.execute.return_value = mock_result

        service = DataQualityService(mock_db)
        sources = await service.get_source_reliability()

        assert sources[0]["failure_rate"] == 0.3
        assert sources[0]["is_degraded"] is True  # 30% > 20% threshold


class TestConstants:
    """Test configuration constants."""

    def test_anomaly_threshold_is_3(self):
        assert ANOMALY_STD_THRESHOLD == 3.0

    def test_source_failure_alert_is_20_percent(self):
        assert SOURCE_FAILURE_ALERT_THRESHOLD == 0.20

    def test_all_utility_types_have_thresholds(self):
        expected = {"electricity", "natural_gas", "heating_oil", "community_solar"}
        assert set(FRESHNESS_THRESHOLDS.keys()) == expected
