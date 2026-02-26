"""
Tests for ObservationService

Covers all public methods:
- record_forecast: batch INSERT, empty predictions guard, timestamp parsing
- observe_actuals_batch: with/without region filter, zero-row update
- record_recommendation: UUID generation, JSON serialization
- record_recommendation_response: idempotency guard, already-responded case
- get_forecast_accuracy: null metrics on empty, MAPE/RMSE/coverage calculation
- get_hourly_bias: 24-hour grouping, empty result
- get_model_accuracy_by_version: multi-version ranking
- archive_old_observations: count-before-delete, no-op on empty, commit
- get_observation_summary: total/oldest/newest, empty table handling
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# HELPERS
# =============================================================================


def _make_result(rowcount=0, fetchone_value=None, fetchall_value=None):
    """Build a mock SQLAlchemy result proxy."""
    result = MagicMock()
    result.rowcount = rowcount
    result.fetchone.return_value = fetchone_value
    result.fetchall.return_value = fetchall_value or []
    return result


def _row(**kwargs):
    """Create a mock row object with named attributes."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


# =============================================================================
# TestRecordForecast
# =============================================================================


class TestRecordForecast:
    """Tests for ObservationService.record_forecast"""

    @pytest.fixture
    def db(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock())
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def service(self, db):
        from services.observation_service import ObservationService
        return ObservationService(db)

    @pytest.mark.asyncio
    async def test_empty_predictions_returns_zero(self, service, db):
        """Should short-circuit and return 0 when predictions list is empty."""
        result = await service.record_forecast(
            forecast_id="fc-1",
            region="US",
            predictions=[],
        )
        assert result == 0
        db.execute.assert_not_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_single_prediction_inserts_one_row(self, service, db):
        """Should insert exactly 1 row for a single prediction."""
        predictions = [
            {
                "timestamp": datetime(2026, 2, 23, 14, 0, tzinfo=timezone.utc),
                "predicted_price": 0.25,
                "confidence_lower": 0.20,
                "confidence_upper": 0.30,
            }
        ]

        result = await service.record_forecast(
            forecast_id="fc-1",
            region="US",
            predictions=predictions,
            model_version="v2.1",
        )

        assert result == 1
        db.execute.assert_awaited_once()
        db.commit.assert_awaited_once()

        # Verify the params passed to execute
        call_args = db.execute.call_args
        rows = call_args[0][1]  # second positional arg is the rows list
        assert len(rows) == 1
        assert rows[0]["forecast_id"] == "fc-1"
        assert rows[0]["region"] == "us"
        assert rows[0]["predicted_price"] == 0.25
        assert rows[0]["confidence_lower"] == 0.20
        assert rows[0]["confidence_upper"] == 0.30
        assert rows[0]["model_version"] == "v2.1"
        assert rows[0]["forecast_hour"] == 14

    @pytest.mark.asyncio
    async def test_batch_predictions_inserts_all(self, service, db):
        """Should insert all predictions in a single batch."""
        predictions = [
            {
                "timestamp": datetime(2026, 2, 23, h, 0, tzinfo=timezone.utc),
                "predicted_price": 0.10 + h * 0.01,
            }
            for h in range(24)
        ]

        result = await service.record_forecast(
            forecast_id="fc-batch",
            region="UK",
            predictions=predictions,
        )

        assert result == 24
        call_args = db.execute.call_args
        rows = call_args[0][1]
        assert len(rows) == 24
        # Verify forecast_hour values span 0-23
        hours = [r["forecast_hour"] for r in rows]
        assert hours == list(range(24))

    @pytest.mark.asyncio
    async def test_iso_string_timestamp_parsed(self, service, db):
        """Should parse ISO-format string timestamps correctly."""
        predictions = [
            {
                "timestamp": "2026-02-23T08:00:00+00:00",
                "predicted_price": 0.18,
            }
        ]

        result = await service.record_forecast(
            forecast_id="fc-iso",
            region="US",
            predictions=predictions,
        )

        assert result == 1
        rows = db.execute.call_args[0][1]
        assert rows[0]["forecast_hour"] == 8

    @pytest.mark.asyncio
    async def test_missing_optional_fields_default_to_none(self, service, db):
        """Confidence bounds should be None if not provided."""
        predictions = [
            {
                "timestamp": datetime(2026, 2, 23, 12, 0, tzinfo=timezone.utc),
                "predicted_price": 0.22,
            }
        ]

        await service.record_forecast(
            forecast_id="fc-min",
            region="US",
            predictions=predictions,
        )

        rows = db.execute.call_args[0][1]
        assert rows[0]["confidence_lower"] is None
        assert rows[0]["confidence_upper"] is None
        assert rows[0]["model_version"] is None

    @pytest.mark.asyncio
    async def test_unique_ids_per_row(self, service, db):
        """Each inserted row should have a unique UUID id."""
        predictions = [
            {
                "timestamp": datetime(2026, 2, 23, h, 0, tzinfo=timezone.utc),
                "predicted_price": 0.20,
            }
            for h in range(5)
        ]

        await service.record_forecast(
            forecast_id="fc-ids",
            region="US",
            predictions=predictions,
        )

        rows = db.execute.call_args[0][1]
        ids = [r["id"] for r in rows]
        assert len(set(ids)) == 5  # all unique

    @pytest.mark.asyncio
    async def test_none_timestamp_defaults_hour_to_zero(self, service, db):
        """When timestamp is None, forecast_hour should default to 0."""
        predictions = [
            {
                "timestamp": None,
                "predicted_price": 0.15,
            }
        ]

        await service.record_forecast(
            forecast_id="fc-none-ts",
            region="US",
            predictions=predictions,
        )

        rows = db.execute.call_args[0][1]
        assert rows[0]["forecast_hour"] == 0


# =============================================================================
# TestObserveActualsBatch
# =============================================================================


class TestObserveActualsBatch:
    """Tests for ObservationService.observe_actuals_batch"""

    @pytest.fixture
    def db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def service(self, db):
        from services.observation_service import ObservationService
        return ObservationService(db)

    @pytest.mark.asyncio
    async def test_no_region_filter(self, service, db):
        """Should run UPDATE without region clause when no region specified."""
        db.execute = AsyncMock(return_value=_make_result(rowcount=10))

        result = await service.observe_actuals_batch()

        assert result == 10
        db.execute.assert_awaited_once()
        db.commit.assert_awaited_once()
        # The query text should NOT contain ":region" param
        call_args = db.execute.call_args
        params = call_args[0][1]
        assert "region" not in params

    @pytest.mark.asyncio
    async def test_with_region_filter(self, service, db):
        """Should include region filter when region is specified."""
        db.execute = AsyncMock(return_value=_make_result(rowcount=5))

        result = await service.observe_actuals_batch(region="US")

        assert result == 5
        call_args = db.execute.call_args
        params = call_args[0][1]
        assert params["region"] == "US"

    @pytest.mark.asyncio
    async def test_zero_rows_updated(self, service, db):
        """Should return 0 when no forecast rows match actual prices."""
        db.execute = AsyncMock(return_value=_make_result(rowcount=0))

        result = await service.observe_actuals_batch(region="XX")

        assert result == 0


# =============================================================================
# TestRecordRecommendation
# =============================================================================


class TestRecordRecommendation:
    """Tests for ObservationService.record_recommendation"""

    @pytest.fixture
    def db(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock())
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def service(self, db):
        from services.observation_service import ObservationService
        return ObservationService(db)

    @pytest.mark.asyncio
    async def test_returns_uuid_string(self, service, db):
        """Should return a valid UUID string as outcome_id."""
        import uuid

        outcome_id = await service.record_recommendation(
            user_id="user-123",
            recommendation_type="switching",
            recommendation_data={"supplier": "NextEra Energy", "savings": 15.0},
        )

        # Should be a valid UUID
        parsed = uuid.UUID(outcome_id)
        assert str(parsed) == outcome_id

    @pytest.mark.asyncio
    async def test_inserts_correct_params(self, service, db):
        """Should pass serialized JSON data to the INSERT."""
        rec_data = {"supplier": "NextEra", "savings": 12.5}

        outcome_id = await service.record_recommendation(
            user_id="user-456",
            recommendation_type="usage",
            recommendation_data=rec_data,
        )

        db.execute.assert_awaited_once()
        call_args = db.execute.call_args
        params = call_args[0][1]
        assert params["id"] == outcome_id
        assert params["user_id"] == "user-456"
        assert params["recommendation_type"] == "usage"
        # recommendation_data should be JSON-serialized
        parsed = json.loads(params["recommendation_data"])
        assert parsed == rec_data

    @pytest.mark.asyncio
    async def test_json_serializes_datetime(self, service, db):
        """Should handle datetime objects in recommendation_data via default=str."""
        rec_data = {
            "created_at": datetime(2026, 2, 23, 12, 0, tzinfo=timezone.utc),
            "amount": 10.0,
        }

        await service.record_recommendation(
            user_id="user-789",
            recommendation_type="switching",
            recommendation_data=rec_data,
        )

        params = db.execute.call_args[0][1]
        parsed = json.loads(params["recommendation_data"])
        # datetime should have been serialized via str()
        assert "2026" in parsed["created_at"]

    @pytest.mark.asyncio
    async def test_commit_called(self, service, db):
        """Should commit after INSERT."""
        await service.record_recommendation(
            user_id="u1",
            recommendation_type="switching",
            recommendation_data={},
        )
        db.commit.assert_awaited_once()


# =============================================================================
# TestRecordRecommendationResponse
# =============================================================================


class TestRecordRecommendationResponse:
    """Tests for ObservationService.record_recommendation_response"""

    @pytest.fixture
    def db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def service(self, db):
        from services.observation_service import ObservationService
        return ObservationService(db)

    @pytest.mark.asyncio
    async def test_accepted_response_updates_row(self, service, db):
        """Should return True when row is found and updated."""
        db.execute = AsyncMock(return_value=_make_result(rowcount=1))

        result = await service.record_recommendation_response(
            outcome_id="out-1",
            accepted=True,
            actual_savings=5.50,
        )

        assert result is True
        db.commit.assert_awaited_once()
        params = db.execute.call_args[0][1]
        assert params["outcome_id"] == "out-1"
        assert params["accepted"] is True
        assert params["actual_savings"] == 5.50

    @pytest.mark.asyncio
    async def test_rejected_response(self, service, db):
        """Should pass accepted=False correctly."""
        db.execute = AsyncMock(return_value=_make_result(rowcount=1))

        result = await service.record_recommendation_response(
            outcome_id="out-2",
            accepted=False,
        )

        assert result is True
        params = db.execute.call_args[0][1]
        assert params["accepted"] is False
        assert params["actual_savings"] is None

    @pytest.mark.asyncio
    async def test_already_responded_returns_false(self, service, db):
        """Should return False when responded_at IS NOT NULL (idempotency guard)."""
        db.execute = AsyncMock(return_value=_make_result(rowcount=0))

        result = await service.record_recommendation_response(
            outcome_id="out-already",
            accepted=True,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_nonexistent_outcome_returns_false(self, service, db):
        """Should return False when outcome_id does not exist."""
        db.execute = AsyncMock(return_value=_make_result(rowcount=0))

        result = await service.record_recommendation_response(
            outcome_id="nonexistent",
            accepted=True,
        )

        assert result is False


# =============================================================================
# TestGetForecastAccuracy
# =============================================================================


class TestGetForecastAccuracy:
    """Tests for ObservationService.get_forecast_accuracy"""

    @pytest.fixture
    def db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def service(self, db):
        from services.observation_service import ObservationService
        return ObservationService(db)

    @pytest.mark.asyncio
    async def test_no_observed_rows_returns_null_metrics(self, service, db):
        """Should return null metrics when total is 0."""
        row = _row(total=0, mape=None, rmse=None, coverage=None)
        db.execute = AsyncMock(return_value=_make_result(fetchone_value=row))

        result = await service.get_forecast_accuracy(region="US", days=7)

        assert result == {"total": 0, "mape": None, "rmse": None, "coverage": None}

    @pytest.mark.asyncio
    async def test_no_row_returned(self, service, db):
        """Should return null metrics when fetchone returns None."""
        db.execute = AsyncMock(return_value=_make_result(fetchone_value=None))

        result = await service.get_forecast_accuracy(region="US")

        assert result["total"] == 0
        assert result["mape"] is None

    @pytest.mark.asyncio
    async def test_valid_metrics_returned(self, service, db):
        """Should return rounded MAPE, RMSE, and coverage."""
        row = _row(total=100, mape=5.6789, rmse=0.012345678, coverage=92.345)
        db.execute = AsyncMock(return_value=_make_result(fetchone_value=row))

        result = await service.get_forecast_accuracy(region="US", days=14)

        assert result["total"] == 100
        assert result["mape"] == 5.68  # rounded to 2 decimal places
        assert result["rmse"] == 0.012346  # rounded to 6 decimal places
        assert result["coverage"] == 92.3  # rounded to 1 decimal place

    @pytest.mark.asyncio
    async def test_none_mape_handled(self, service, db):
        """Should return None for mape when DB returns NULL."""
        row = _row(total=5, mape=None, rmse=0.05, coverage=80.0)
        db.execute = AsyncMock(return_value=_make_result(fetchone_value=row))

        result = await service.get_forecast_accuracy(region="US")

        assert result["total"] == 5
        assert result["mape"] is None
        assert result["rmse"] == 0.05
        assert result["coverage"] == 80.0

    @pytest.mark.asyncio
    async def test_passes_region_and_days_params(self, service, db):
        """Should pass correct parameters to the SQL query."""
        row = _row(total=0, mape=None, rmse=None, coverage=None)
        db.execute = AsyncMock(return_value=_make_result(fetchone_value=row))

        await service.get_forecast_accuracy(region="UK", days=30)

        params = db.execute.call_args[0][1]
        assert params["region"] == "uk"
        assert params["days"] == 30


# =============================================================================
# TestGetHourlyBias
# =============================================================================


class TestGetHourlyBias:
    """Tests for ObservationService.get_hourly_bias"""

    @pytest.fixture
    def db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def service(self, db):
        from services.observation_service import ObservationService
        return ObservationService(db)

    @pytest.mark.asyncio
    async def test_empty_result(self, service, db):
        """Should return empty list when no observed data exists."""
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=[]))

        result = await service.get_hourly_bias(region="US")

        assert result == []

    @pytest.mark.asyncio
    async def test_multiple_hours_returned(self, service, db):
        """Should return one entry per hour group."""
        rows = [
            _row(hour=0, avg_bias=0.001234, count=10),
            _row(hour=12, avg_bias=-0.005678, count=15),
            _row(hour=23, avg_bias=0.000001, count=5),
        ]
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=rows))

        result = await service.get_hourly_bias(region="US", days=14)

        assert len(result) == 3
        assert result[0] == {"hour": 0, "avg_bias": 0.001234, "count": 10}
        assert result[1] == {"hour": 12, "avg_bias": -0.005678, "count": 15}
        assert result[2] == {"hour": 23, "avg_bias": 0.000001, "count": 5}

    @pytest.mark.asyncio
    async def test_bias_rounded_to_six_decimals(self, service, db):
        """avg_bias should be rounded to 6 decimal places."""
        rows = [
            _row(hour=5, avg_bias=0.12345678901234, count=20),
        ]
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=rows))

        result = await service.get_hourly_bias(region="US")

        assert result[0]["avg_bias"] == 0.123457  # rounded to 6 places

    @pytest.mark.asyncio
    async def test_passes_correct_params(self, service, db):
        """Should pass region and days to the SQL query."""
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=[]))

        await service.get_hourly_bias(region="DE", days=21)

        params = db.execute.call_args[0][1]
        assert params["region"] == "de"
        assert params["days"] == 21


# =============================================================================
# TestGetModelAccuracyByVersion
# =============================================================================


class TestGetModelAccuracyByVersion:
    """Tests for ObservationService.get_model_accuracy_by_version"""

    @pytest.fixture
    def db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def service(self, db):
        from services.observation_service import ObservationService
        return ObservationService(db)

    @pytest.mark.asyncio
    async def test_empty_result(self, service, db):
        """Should return empty list when no model data exists."""
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=[]))

        result = await service.get_model_accuracy_by_version(region="US")

        assert result == []

    @pytest.mark.asyncio
    async def test_multiple_versions_ranked(self, service, db):
        """Should return entries for each model version."""
        rows = [
            _row(model_version="v2.1", count=50, mape=3.45, rmse=0.012345),
            _row(model_version="v2.0", count=80, mape=5.67, rmse=0.023456),
            _row(model_version="v1.9", count=30, mape=8.90, rmse=0.034567),
        ]
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=rows))

        result = await service.get_model_accuracy_by_version(region="US", days=14)

        assert len(result) == 3
        assert result[0]["model_version"] == "v2.1"
        assert result[0]["mape"] == 3.45
        assert result[0]["rmse"] == 0.012345
        assert result[0]["count"] == 50
        assert result[1]["model_version"] == "v2.0"
        assert result[2]["model_version"] == "v1.9"

    @pytest.mark.asyncio
    async def test_none_mape_handled(self, service, db):
        """Should return None for mape when DB returns NULL."""
        rows = [
            _row(model_version="v3.0", count=2, mape=None, rmse=None),
        ]
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=rows))

        result = await service.get_model_accuracy_by_version(region="US")

        assert result[0]["mape"] is None
        assert result[0]["rmse"] is None

    @pytest.mark.asyncio
    async def test_mape_rounded_to_two_decimals(self, service, db):
        """MAPE should be rounded to 2 decimal places."""
        rows = [
            _row(model_version="v2.1", count=10, mape=3.456789, rmse=0.0123456789),
        ]
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=rows))

        result = await service.get_model_accuracy_by_version(region="US")

        assert result[0]["mape"] == 3.46
        assert result[0]["rmse"] == 0.012346


# =============================================================================
# TestArchiveOldObservations
# =============================================================================


class TestArchiveOldObservations:
    """Tests for ObservationService.archive_old_observations"""

    @pytest.fixture
    def db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def service(self, db):
        from services.observation_service import ObservationService
        return ObservationService(db)

    @pytest.mark.asyncio
    async def test_returns_no_op_when_count_is_zero(self, service, db):
        """Should return archived=0 with a message when there is nothing to delete."""
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        db.execute = AsyncMock(return_value=count_result)

        result = await service.archive_old_observations(days=90)

        assert result["archived"] == 0
        assert "message" in result
        # Only the COUNT query should be issued — no DELETE
        db.execute.assert_awaited_once()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_archived_count_when_rows_exist(self, service, db):
        """Should issue DELETE and return the count of archived observations."""
        count_result = MagicMock()
        count_result.scalar.return_value = 15
        delete_result = MagicMock()

        db.execute = AsyncMock(side_effect=[count_result, delete_result])

        result = await service.archive_old_observations(days=90)

        assert result["archived"] == 15
        assert result["cutoff_days"] == 90

    @pytest.mark.asyncio
    async def test_commit_called_after_delete(self, service, db):
        """Should commit the DELETE transaction."""
        count_result = MagicMock()
        count_result.scalar.return_value = 5
        delete_result = MagicMock()

        db.execute = AsyncMock(side_effect=[count_result, delete_result])

        await service.archive_old_observations()

        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_issues_two_queries_when_rows_present(self, service, db):
        """Should run COUNT then DELETE when there are observations to archive."""
        count_result = MagicMock()
        count_result.scalar.return_value = 7
        delete_result = MagicMock()

        db.execute = AsyncMock(side_effect=[count_result, delete_result])

        await service.archive_old_observations(days=30)

        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_default_days_is_90(self, service, db):
        """Default archival window should be 90 days."""
        count_result = MagicMock()
        count_result.scalar.return_value = 3
        delete_result = MagicMock()

        db.execute = AsyncMock(side_effect=[count_result, delete_result])

        result = await service.archive_old_observations()

        assert result["cutoff_days"] == 90

    @pytest.mark.asyncio
    async def test_scalar_none_treated_as_zero(self, service, db):
        """If the COUNT scalar returns None, it should be treated as 0 (no-op)."""
        count_result = MagicMock()
        count_result.scalar.return_value = None
        db.execute = AsyncMock(return_value=count_result)

        result = await service.archive_old_observations()

        assert result["archived"] == 0
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cutoff_passed_to_queries(self, service, db):
        """Both queries should receive the same :cutoff datetime parameter."""
        from datetime import timedelta

        count_result = MagicMock()
        count_result.scalar.return_value = 2
        delete_result = MagicMock()

        db.execute = AsyncMock(side_effect=[count_result, delete_result])

        before = datetime.utcnow() - timedelta(days=90)
        await service.archive_old_observations(days=90)
        after = datetime.utcnow() - timedelta(days=90)

        for call_args in db.execute.call_args_list:
            params = call_args[0][1]
            assert "cutoff" in params
            assert before <= params["cutoff"] <= after + timedelta(seconds=2)


# =============================================================================
# TestGetObservationSummary
# =============================================================================


class TestGetObservationSummary:
    """Tests for ObservationService.get_observation_summary"""

    @pytest.fixture
    def db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def service(self, db):
        from services.observation_service import ObservationService
        return ObservationService(db)

    @pytest.mark.asyncio
    async def test_empty_table_returns_zero_and_nones(self, service, db):
        """Should return total=0 and None dates when the table is empty."""
        row = MagicMock()
        row.__getitem__ = lambda self, i: (0, None, None)[i]
        result_mock = MagicMock()
        result_mock.fetchone.return_value = row
        db.execute = AsyncMock(return_value=result_mock)

        result = await service.get_observation_summary()

        assert result["total"] == 0
        assert result["oldest"] is None
        assert result["newest"] is None

    @pytest.mark.asyncio
    async def test_returns_none_when_fetchone_is_none(self, service, db):
        """Should handle a None fetchone result gracefully."""
        result_mock = MagicMock()
        result_mock.fetchone.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await service.get_observation_summary()

        assert result["total"] == 0
        assert result["oldest"] is None
        assert result["newest"] is None

    @pytest.mark.asyncio
    async def test_returns_summary_with_data(self, service, db):
        """Should return total, oldest, and newest as strings when data exists."""
        oldest_dt = datetime(2026, 1, 1, 0, 0, 0)
        newest_dt = datetime(2026, 2, 25, 12, 30, 0)
        row = MagicMock()
        row.__getitem__ = lambda self, i: (250, oldest_dt, newest_dt)[i]
        result_mock = MagicMock()
        result_mock.fetchone.return_value = row
        db.execute = AsyncMock(return_value=result_mock)

        result = await service.get_observation_summary()

        assert result["total"] == 250
        assert "2026-01-01" in result["oldest"]
        assert "2026-02-25" in result["newest"]

    @pytest.mark.asyncio
    async def test_issues_single_query(self, service, db):
        """Should execute exactly one SELECT query."""
        row = MagicMock()
        row.__getitem__ = lambda self, i: (0, None, None)[i]
        result_mock = MagicMock()
        result_mock.fetchone.return_value = row
        db.execute = AsyncMock(return_value=result_mock)

        await service.get_observation_summary()

        db.execute.assert_awaited_once()
