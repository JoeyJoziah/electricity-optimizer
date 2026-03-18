"""
Tests for ForecastObservationRepository

Covers all public methods of the raw-SQL data access layer:
- insert_forecasts: batch INSERT, empty guard, string/datetime timestamps
- backfill_actuals: with and without region filter
- insert_recommendation: UUID return, JSON serialization
- update_recommendation_response: accepted/rejected, idempotency guard
- get_accuracy_metrics: normal case, no-data fallback
- get_accuracy_by_version: multi-version SQL aggregation, coverage metric, NULL handling
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# =============================================================================
# HELPERS
# =============================================================================


def _make_result(rowcount: int = 0, fetchone_value=None, fetchall_value=None):
    """Build a mock SQLAlchemy CursorResult proxy."""
    result = MagicMock()
    result.rowcount = rowcount
    result.fetchone.return_value = fetchone_value
    result.fetchall.return_value = fetchall_value or []
    return result


def _row(**kwargs):
    """Create a lightweight mock row with named attributes."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_session():
    """Async SQLAlchemy session mock with execute/commit pre-wired."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_make_result())
    session.commit = AsyncMock()
    return session


@pytest.fixture
def repo(mock_session):
    """ForecastObservationRepository bound to the mock session."""
    from repositories.forecast_observation_repository import \
        ForecastObservationRepository

    return ForecastObservationRepository(mock_session)


# =============================================================================
# TestInsertForecasts
# =============================================================================


class TestInsertForecasts:
    """Tests for ForecastObservationRepository.insert_forecasts"""

    @pytest.mark.asyncio
    async def test_insert_forecasts_batch(self, repo, mock_session):
        """Insert multiple forecasts — should return row count and call execute once."""
        predictions = [
            {
                "timestamp": datetime(2026, 2, 24, 10, 0, tzinfo=timezone.utc),
                "predicted_price": 0.28,
                "confidence_lower": 0.24,
                "confidence_upper": 0.32,
            },
            {
                "timestamp": datetime(2026, 2, 24, 11, 0, tzinfo=timezone.utc),
                "predicted_price": 0.30,
                "confidence_lower": 0.26,
                "confidence_upper": 0.34,
            },
            {
                "timestamp": datetime(2026, 2, 24, 12, 0, tzinfo=timezone.utc),
                "predicted_price": 0.25,
            },
        ]

        count = await repo.insert_forecasts(
            forecast_id="fc-001",
            region="US_CT",
            predictions=predictions,
            model_version="v1.0",
        )

        assert count == 3
        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_insert_forecasts_empty_list(self, repo, mock_session):
        """Empty predictions list — short-circuits and returns 0 without DB calls."""
        count = await repo.insert_forecasts(
            forecast_id="fc-002",
            region="US_NY",
            predictions=[],
        )

        assert count == 0
        mock_session.execute.assert_not_awaited()
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_insert_forecasts_with_string_timestamps(self, repo, mock_session):
        """ISO string timestamps are parsed to datetime and hour extracted correctly."""
        predictions = [
            {
                "timestamp": "2026-02-24T14:00:00+00:00",
                "predicted_price": 0.29,
            }
        ]

        count = await repo.insert_forecasts(
            forecast_id="fc-003",
            region="us_ct",
            predictions=predictions,
        )

        assert count == 1
        # Verify the row passed to execute has forecast_hour=14
        call_args = mock_session.execute.call_args
        rows = call_args[0][
            1
        ]  # second positional arg is the flat params dict (keys use numeric suffix: forecast_hour0, etc.)
        assert rows["forecast_hour0"] == 14

    @pytest.mark.asyncio
    async def test_insert_forecasts_with_datetime_timestamps(self, repo, mock_session):
        """datetime objects are handled directly — hour extracted without parsing."""
        ts = datetime(2026, 2, 24, 9, 0, tzinfo=timezone.utc)
        predictions = [
            {
                "timestamp": ts,
                "predicted_price": 0.27,
                "confidence_lower": 0.23,
                "confidence_upper": 0.31,
            }
        ]

        count = await repo.insert_forecasts(
            forecast_id="fc-004",
            region="us_ct",
            predictions=predictions,
            model_version="v2.0",
        )

        assert count == 1
        rows = mock_session.execute.call_args[0][1]  # flat params dict with numeric-suffix keys
        assert rows["forecast_hour0"] == 9
        assert rows["model_version0"] == "v2.0"
        assert rows["region0"] == "us_ct"


# =============================================================================
# TestBackfillActuals
# =============================================================================


class TestBackfillActuals:
    """Tests for ForecastObservationRepository.backfill_actuals"""

    @pytest.mark.asyncio
    async def test_backfill_actuals_with_region(self, repo, mock_session):
        """Backfill with region filter — passes region param to query."""
        mock_session.execute.return_value = _make_result(rowcount=5)

        updated = await repo.backfill_actuals(region="us_ct")

        assert updated == 5
        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()
        # Verify region param was included
        call_args = mock_session.execute.call_args
        params = call_args[0][1]
        assert params.get("region") == "us_ct"

    @pytest.mark.asyncio
    async def test_backfill_actuals_all_regions(self, repo, mock_session):
        """Backfill without region — uses LIMIT to prevent unbounded memory usage."""
        mock_session.execute.return_value = _make_result(rowcount=12)

        updated = await repo.backfill_actuals()

        assert updated == 12
        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()
        call_args = mock_session.execute.call_args
        params = call_args[0][1]
        # S1-10: no-region path now includes a backfill_limit param
        assert params == {"backfill_limit": 10_000}


# =============================================================================
# TestInsertRecommendation
# =============================================================================


class TestInsertRecommendation:
    """Tests for ForecastObservationRepository.insert_recommendation"""

    @pytest.mark.asyncio
    async def test_insert_recommendation(self, repo, mock_session):
        """Insert recommendation — returns a valid UUID string."""
        outcome_id = await repo.insert_recommendation(
            user_id="user-abc",
            recommendation_type="switch_supplier",
            recommendation_data={"supplier": "Eversource", "savings": 12.5},
        )

        assert isinstance(outcome_id, str)
        assert len(outcome_id) == 36  # UUID format
        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_insert_recommendation_serializes_data(self, repo, mock_session):
        """recommendation_data is JSON-serialized before being stored."""
        rec_data = {"supplier": "United Illuminating", "potential_savings": 8.75}

        await repo.insert_recommendation(
            user_id="user-xyz",
            recommendation_type="usage_shift",
            recommendation_data=rec_data,
        )

        call_args = mock_session.execute.call_args
        params = call_args[0][1]
        # Verify the stored value is a JSON string, not a dict
        stored = params["recommendation_data"]
        assert isinstance(stored, str)
        parsed = json.loads(stored)
        assert parsed["supplier"] == "United Illuminating"
        assert parsed["potential_savings"] == 8.75


# =============================================================================
# TestUpdateRecommendationResponse
# =============================================================================


class TestUpdateRecommendationResponse:
    """Tests for ForecastObservationRepository.update_recommendation_response"""

    @pytest.mark.asyncio
    async def test_update_recommendation_response_accepted(self, repo, mock_session):
        """Accepted=True with no savings — returns True when rowcount=1."""
        mock_session.execute.return_value = _make_result(rowcount=1)

        result = await repo.update_recommendation_response(
            outcome_id="outcome-001",
            accepted=True,
        )

        assert result is True
        call_args = mock_session.execute.call_args
        params = call_args[0][1]
        assert params["accepted"] is True
        assert params["actual_savings"] is None

    @pytest.mark.asyncio
    async def test_update_recommendation_response_rejected(self, repo, mock_session):
        """Accepted=False with actual_savings — returns True and passes savings."""
        mock_session.execute.return_value = _make_result(rowcount=1)

        result = await repo.update_recommendation_response(
            outcome_id="outcome-002",
            accepted=False,
            actual_savings=0.0,
        )

        assert result is True
        params = mock_session.execute.call_args[0][1]
        assert params["accepted"] is False
        assert params["actual_savings"] == 0.0

    @pytest.mark.asyncio
    async def test_update_recommendation_response_already_responded(self, repo, mock_session):
        """When rowcount=0 (already responded), returns False (idempotency guard)."""
        mock_session.execute.return_value = _make_result(rowcount=0)

        result = await repo.update_recommendation_response(
            outcome_id="outcome-already-done",
            accepted=True,
        )

        assert result is False
        mock_session.commit.assert_awaited_once()


# =============================================================================
# TestGetAccuracyMetrics
# =============================================================================


class TestGetAccuracyMetrics:
    """Tests for ForecastObservationRepository.get_accuracy_metrics"""

    @pytest.mark.asyncio
    async def test_get_accuracy_metrics(self, repo, mock_session):
        """Normal case — returns dict with total, mape, rmse, coverage."""
        row = _row(total=50, mape=4.25, rmse=0.012345, coverage=87.5)
        mock_session.execute.return_value = _make_result(fetchone_value=row)

        metrics = await repo.get_accuracy_metrics(region="us_ct", days=7)

        assert metrics["total"] == 50
        assert metrics["mape"] == 4.25
        assert metrics["rmse"] == 0.012345
        assert metrics["coverage"] == 87.5

    @pytest.mark.asyncio
    async def test_get_accuracy_metrics_no_data(self, repo, mock_session):
        """When total=0 (no observed rows), returns dict with None metric values."""
        row = _row(total=0, mape=None, rmse=None, coverage=None)
        mock_session.execute.return_value = _make_result(fetchone_value=row)

        metrics = await repo.get_accuracy_metrics(region="us_ct", days=7)

        assert metrics["total"] == 0
        assert metrics["mape"] is None
        assert metrics["rmse"] is None
        assert metrics["coverage"] is None


# =============================================================================
# TestGetAccuracyByVersion
# =============================================================================


class TestGetAccuracyByVersion:
    """Tests for ForecastObservationRepository.get_accuracy_by_version.

    Verifies that aggregation (MAPE, RMSE, coverage) is computed in SQL via
    GROUP BY model_version rather than fetching raw rows and aggregating in
    Python.  A single db.execute call must return pre-aggregated results.
    """

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self, repo, mock_session):
        """Should return [] when no observed rows exist for the region/window."""
        mock_session.execute.return_value = _make_result(fetchall_value=[])

        result = await repo.get_accuracy_by_version(region="us_ct", days=7)

        assert result == []
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_single_version_returned(self, repo, mock_session):
        """Single model version row is mapped to the expected dict shape."""
        rows = [
            _row(model_version="v2.1", count=50, mape=4.25, rmse=0.012345, coverage=88.5),
        ]
        mock_session.execute.return_value = _make_result(fetchall_value=rows)

        result = await repo.get_accuracy_by_version(region="us_ct", days=7)

        assert len(result) == 1
        entry = result[0]
        assert entry["model_version"] == "v2.1"
        assert entry["count"] == 50
        assert entry["mape"] == 4.25
        assert entry["rmse"] == 0.012345
        assert entry["coverage"] == 88.5

    @pytest.mark.asyncio
    async def test_multiple_versions_ordered_by_mape(self, repo, mock_session):
        """Results come back in ascending MAPE order (best model first)."""
        rows = [
            _row(model_version="v2.1", count=50, mape=3.45, rmse=0.011, coverage=91.0),
            _row(model_version="v2.0", count=80, mape=5.67, rmse=0.023, coverage=85.0),
            _row(model_version="v1.9", count=30, mape=8.90, rmse=0.035, coverage=78.0),
        ]
        mock_session.execute.return_value = _make_result(fetchall_value=rows)

        result = await repo.get_accuracy_by_version(region="us_ct", days=14)

        assert len(result) == 3
        assert result[0]["model_version"] == "v2.1"
        assert result[0]["mape"] == 3.45
        assert result[1]["model_version"] == "v2.0"
        assert result[2]["model_version"] == "v1.9"

    @pytest.mark.asyncio
    async def test_mape_rounded_to_two_decimals(self, repo, mock_session):
        """MAPE values are rounded to 2 decimal places on return."""
        rows = [
            _row(model_version="v2.1", count=10, mape=3.456789, rmse=0.0123456789, coverage=90.123),
        ]
        mock_session.execute.return_value = _make_result(fetchall_value=rows)

        result = await repo.get_accuracy_by_version(region="us_ct", days=7)

        assert result[0]["mape"] == 3.46
        assert result[0]["rmse"] == 0.012346
        assert result[0]["coverage"] == 90.1

    @pytest.mark.asyncio
    async def test_null_mape_returned_as_none(self, repo, mock_session):
        """NULL mape from DB (no actual prices yet) maps to None in the dict."""
        rows = [
            _row(model_version="v3.0", count=2, mape=None, rmse=None, coverage=None),
        ]
        mock_session.execute.return_value = _make_result(fetchall_value=rows)

        result = await repo.get_accuracy_by_version(region="us_ct", days=7)

        assert result[0]["mape"] is None
        assert result[0]["rmse"] is None
        assert result[0]["coverage"] is None

    @pytest.mark.asyncio
    async def test_coverage_computed_per_version(self, repo, mock_session):
        """Coverage (confidence interval hit rate) is included per model version."""
        rows = [
            _row(model_version="v2.1", count=40, mape=3.0, rmse=0.01, coverage=92.5),
            _row(model_version="v2.0", count=60, mape=6.0, rmse=0.02, coverage=75.0),
        ]
        mock_session.execute.return_value = _make_result(fetchall_value=rows)

        result = await repo.get_accuracy_by_version(region="us", days=7)

        assert result[0]["coverage"] == 92.5
        assert result[1]["coverage"] == 75.0

    @pytest.mark.asyncio
    async def test_passes_lowercased_region_and_days(self, repo, mock_session):
        """Region is lowercased and days is passed as a named parameter."""
        mock_session.execute.return_value = _make_result(fetchall_value=[])

        await repo.get_accuracy_by_version(region="US_CT", days=30)

        params = mock_session.execute.call_args[0][1]
        assert params["region"] == "us_ct"
        assert params["days"] == 30

    @pytest.mark.asyncio
    async def test_single_db_call_no_in_memory_aggregation(self, repo, mock_session):
        """Aggregation is done in SQL — exactly one execute call is made."""
        mock_session.execute.return_value = _make_result(fetchall_value=[])

        await repo.get_accuracy_by_version(region="us", days=7)

        # One SELECT ... GROUP BY query, nothing more.
        assert mock_session.execute.await_count == 1
        # No commit needed for a read-only query.
        mock_session.commit.assert_not_awaited()
