"""Tests for RateChangeDetector and AlertPreferenceService."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.rate_change_detector import (DEFAULT_THRESHOLDS, LOOKBACK_DAYS,
                                           AlertPreferenceService,
                                           RateChangeDetector)


def _mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


def _row(data: dict):
    """Create a mock mapping row."""
    m = MagicMock()
    m.__getitem__ = lambda self, key: data[key]
    m.get = lambda key, default=None: data.get(key, default)
    return m


# =============================================================================
# RateChangeDetector
# =============================================================================


class TestDetectChanges:
    async def test_detects_electricity_increase(self):
        db = _mock_db()
        rows = [
            _row(
                {
                    "region": "us_ct",
                    "supplier": "Eversource",
                    "current_price": Decimal("0.12"),
                    "previous_price": Decimal("0.10"),
                }
            ),
        ]
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = rows
        db.execute.return_value = result_mock

        detector = RateChangeDetector(db)
        changes = await detector.detect_changes("electricity")

        assert len(changes) == 1
        assert changes[0]["change_direction"] == "increase"
        assert changes[0]["change_pct"] == 20.0
        assert changes[0]["utility_type"] == "electricity"

    async def test_detects_gas_decrease(self):
        db = _mock_db()
        rows = [
            _row(
                {
                    "region": "TX",
                    "supplier": "TXU",
                    "current_price": Decimal("0.80"),
                    "previous_price": Decimal("1.00"),
                }
            ),
        ]
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = rows
        db.execute.return_value = result_mock

        detector = RateChangeDetector(db)
        changes = await detector.detect_changes("natural_gas")

        assert len(changes) == 1
        assert changes[0]["change_direction"] == "decrease"
        assert changes[0]["change_pct"] == -20.0

    async def test_skips_below_threshold(self):
        db = _mock_db()
        rows = [
            _row(
                {
                    "region": "CT",
                    "supplier": "EIA",
                    "current_price": Decimal("3.51"),
                    "previous_price": Decimal("3.50"),  # 0.3% change
                }
            ),
        ]
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = rows
        db.execute.return_value = result_mock

        detector = RateChangeDetector(db)
        changes = await detector.detect_changes("heating_oil")

        assert len(changes) == 0

    async def test_detects_heating_oil_change(self):
        db = _mock_db()
        rows = [
            _row(
                {
                    "region": "CT",
                    "supplier": "EIA",
                    "current_price": Decimal("3.80"),
                    "previous_price": Decimal("3.50"),  # 8.6% change
                }
            ),
        ]
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = rows
        db.execute.return_value = result_mock

        detector = RateChangeDetector(db)
        changes = await detector.detect_changes("heating_oil")

        assert len(changes) == 1
        assert changes[0]["change_pct"] == pytest.approx(8.57, abs=0.01)

    async def test_empty_when_no_price_data(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = []
        db.execute.return_value = result_mock

        detector = RateChangeDetector(db)
        changes = await detector.detect_changes("electricity")

        assert changes == []


class TestFindCheaperAlternative:
    async def test_finds_cheaper_supplier(self):
        db = _mock_db()
        row = _row({"supplier": "CheapCo", "price": Decimal("0.08")})
        result_mock = MagicMock()
        result_mock.mappings.return_value.first.return_value = row
        db.execute.return_value = result_mock

        detector = RateChangeDetector(db)
        alt = await detector.find_cheaper_alternative("electricity", "us_ct", 0.12)

        assert alt is not None
        assert alt["supplier"] == "CheapCo"
        assert alt["savings"] == pytest.approx(0.04, abs=0.001)

    async def test_returns_none_when_no_cheaper(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.mappings.return_value.first.return_value = None
        db.execute.return_value = result_mock

        detector = RateChangeDetector(db)
        alt = await detector.find_cheaper_alternative("electricity", "us_ct", 0.05)

        assert alt is None

    async def test_returns_none_for_heating_oil(self):
        db = _mock_db()
        detector = RateChangeDetector(db)
        alt = await detector.find_cheaper_alternative("heating_oil", "CT", 3.50)

        assert alt is None


class TestStoreChanges:
    async def test_stores_changes(self):
        db = _mock_db()
        detector = RateChangeDetector(db)

        changes = [
            {
                "utility_type": "electricity",
                "region": "us_ct",
                "supplier": "Eversource",
                "previous_price": 0.10,
                "current_price": 0.12,
                "change_pct": 20.0,
                "change_direction": "increase",
            },
        ]
        stored = await detector.store_changes(changes)

        assert stored == 1
        db.execute.assert_called_once()
        db.commit.assert_called_once()


class TestGetRecentChanges:
    async def test_returns_recent_changes(self):
        db = _mock_db()
        now = datetime.now(UTC)
        rows = [
            _row(
                {
                    "id": "abc-123",
                    "utility_type": "electricity",
                    "region": "us_ct",
                    "supplier": "Eversource",
                    "previous_price": Decimal("0.10"),
                    "current_price": Decimal("0.12"),
                    "change_pct": Decimal("20.0"),
                    "change_direction": "increase",
                    "detected_at": now,
                    "recommendation_supplier": None,
                    "recommendation_price": None,
                    "recommendation_savings": None,
                }
            ),
        ]
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = rows
        db.execute.return_value = result_mock

        detector = RateChangeDetector(db)
        changes = await detector.get_recent_changes(utility_type="electricity")

        assert len(changes) == 1
        assert changes[0]["id"] == "abc-123"
        assert changes[0]["change_pct"] == 20.0

    async def test_empty_when_no_recent(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = []
        db.execute.return_value = result_mock

        detector = RateChangeDetector(db)
        changes = await detector.get_recent_changes()

        assert changes == []


# =============================================================================
# AlertPreferenceService
# =============================================================================


class TestGetPreferences:
    async def test_returns_all_prefs(self):
        db = _mock_db()
        now = datetime.now(UTC)
        rows = [
            _row(
                {
                    "id": "pref-1",
                    "user_id": "user-1",
                    "utility_type": "electricity",
                    "enabled": True,
                    "channels": ["email", "push"],
                    "cadence": "daily",
                    "created_at": now,
                    "updated_at": now,
                }
            ),
        ]
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = rows
        db.execute.return_value = result_mock

        service = AlertPreferenceService(db)
        prefs = await service.get_preferences("user-1")

        assert len(prefs) == 1
        assert prefs[0]["utility_type"] == "electricity"
        assert prefs[0]["channels"] == ["email", "push"]


class TestUpsertPreference:
    async def test_upsert_creates_pref(self):
        db = _mock_db()
        now = datetime.now(UTC)
        row = _row(
            {
                "id": "pref-new",
                "user_id": "user-1",
                "utility_type": "natural_gas",
                "enabled": True,
                "channels": ["email"],
                "cadence": "weekly",
                "created_at": now,
                "updated_at": now,
            }
        )
        result_mock = MagicMock()
        result_mock.mappings.return_value.first.return_value = row
        db.execute.return_value = result_mock

        service = AlertPreferenceService(db)
        pref = await service.upsert_preference(
            user_id="user-1",
            utility_type="natural_gas",
            cadence="weekly",
        )

        assert pref["utility_type"] == "natural_gas"
        assert pref["cadence"] == "weekly"
        db.commit.assert_called_once()


class TestIsEnabled:
    async def test_enabled_when_pref_exists(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.first.return_value = (True,)
        db.execute.return_value = result_mock

        service = AlertPreferenceService(db)
        assert await service.is_enabled("user-1", "electricity") is True

    async def test_disabled_when_pref_false(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.first.return_value = (False,)
        db.execute.return_value = result_mock

        service = AlertPreferenceService(db)
        assert await service.is_enabled("user-1", "electricity") is False

    async def test_default_enabled_when_no_pref(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.first.return_value = None
        db.execute.return_value = result_mock

        service = AlertPreferenceService(db)
        assert await service.is_enabled("user-1", "heating_oil") is True


class TestDefaultThresholds:
    def test_all_utility_types_have_thresholds(self):
        for ut in [
            "electricity",
            "natural_gas",
            "heating_oil",
            "propane",
            "community_solar",
        ]:
            assert ut in DEFAULT_THRESHOLDS

    def test_all_utility_types_have_lookback(self):
        for ut in [
            "electricity",
            "natural_gas",
            "heating_oil",
            "propane",
            "community_solar",
        ]:
            assert ut in LOOKBACK_DAYS
