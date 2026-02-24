"""
Tests for LearningService

Covers all public methods:
- compute_rolling_accuracy: delegates to ObservationService
- detect_bias: delegates to ObservationService
- update_ensemble_weights: inverse-MAPE math, clamping, normalization, Redis write
- store_bias_correction: 24-element vector from bias, empty bias returns None
- prune_stale_patterns: delegates to vector store
- run_full_cycle: full orchestration, Redis MAPE update, multi-region loop
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import numpy as np


# =============================================================================
# SHARED FIXTURES
# =============================================================================


@pytest.fixture
def mock_obs():
    """Mock ObservationService with all async methods."""
    obs = AsyncMock()
    obs.get_forecast_accuracy = AsyncMock(return_value={
        "total": 0, "mape": None, "rmse": None, "coverage": None,
    })
    obs.get_hourly_bias = AsyncMock(return_value=[])
    obs.get_model_accuracy_by_version = AsyncMock(return_value=[])
    return obs


@pytest.fixture
def mock_vs():
    """Mock HNSWVectorStore with sync and async methods."""
    vs = MagicMock()
    vs.insert = MagicMock(return_value="vec-123")
    vs.prune = MagicMock(return_value=0)
    vs.async_insert = AsyncMock(return_value="vec-123")
    vs.async_prune = AsyncMock(return_value=0)
    return vs


@pytest.fixture
def mock_redis():
    """Mock async Redis client."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    return redis


@pytest.fixture
def service(mock_obs, mock_vs, mock_redis):
    """LearningService with all mocked dependencies."""
    from services.learning_service import LearningService
    return LearningService(
        observation_service=mock_obs,
        vector_store=mock_vs,
        redis_client=mock_redis,
    )


@pytest.fixture
def service_no_redis(mock_obs, mock_vs):
    """LearningService without Redis."""
    from services.learning_service import LearningService
    return LearningService(
        observation_service=mock_obs,
        vector_store=mock_vs,
        redis_client=None,
    )


# =============================================================================
# TestComputeRollingAccuracy
# =============================================================================


class TestComputeRollingAccuracy:
    """Tests for LearningService.compute_rolling_accuracy"""

    @pytest.mark.asyncio
    async def test_delegates_to_observation_service(self, service, mock_obs):
        """Should call get_forecast_accuracy with correct args and return result."""
        mock_obs.get_forecast_accuracy.return_value = {
            "total": 50, "mape": 3.5, "rmse": 0.012, "coverage": 88.0,
        }

        result = await service.compute_rolling_accuracy("US", days=14)

        mock_obs.get_forecast_accuracy.assert_awaited_once_with("US", 14)
        assert result["total"] == 50
        assert result["mape"] == 3.5

    @pytest.mark.asyncio
    async def test_default_days(self, service, mock_obs):
        """Should default to 7 days."""
        await service.compute_rolling_accuracy("US")
        mock_obs.get_forecast_accuracy.assert_awaited_once_with("US", 7)


# =============================================================================
# TestDetectBias
# =============================================================================


class TestDetectBias:
    """Tests for LearningService.detect_bias"""

    @pytest.mark.asyncio
    async def test_delegates_to_observation_service(self, service, mock_obs):
        """Should call get_hourly_bias with correct args."""
        mock_obs.get_hourly_bias.return_value = [
            {"hour": 0, "avg_bias": 0.001, "count": 10},
        ]

        result = await service.detect_bias("UK", days=30)

        mock_obs.get_hourly_bias.assert_awaited_once_with("UK", 30)
        assert len(result) == 1
        assert result[0]["hour"] == 0


# =============================================================================
# TestUpdateEnsembleWeights
# =============================================================================


class TestUpdateEnsembleWeights:
    """Tests for LearningService.update_ensemble_weights"""

    @pytest.mark.asyncio
    async def test_no_model_stats_returns_none(self, service, mock_obs):
        """Should return None when no model stats available."""
        mock_obs.get_model_accuracy_by_version.return_value = []

        result = await service.update_ensemble_weights("US")

        assert result is None

    @pytest.mark.asyncio
    async def test_single_model_gets_clamped_weight(self, service, mock_obs, mock_redis):
        """A single model should get weight=1.0 (full share after clamping+normalization)."""
        mock_obs.get_model_accuracy_by_version.return_value = [
            {"model_version": "v2.1", "mape": 5.0, "rmse": 0.01, "count": 50},
        ]

        result = await service.update_ensemble_weights("US")

        assert result is not None
        # Single model: inverse MAPE = 1/5 = 0.2, raw = 0.2/0.2 = 1.0
        # Clamped to max(0.1, min(0.8, 1.0)) = 0.8
        # Re-normalized: 0.8/0.8 = 1.0
        assert result["v2.1"] == 1.0

    @pytest.mark.asyncio
    async def test_two_models_inverse_mape_weighting(self, service, mock_obs, mock_redis):
        """Two models: lower MAPE should get higher weight."""
        mock_obs.get_model_accuracy_by_version.return_value = [
            {"model_version": "v2.1", "mape": 5.0, "rmse": 0.01, "count": 50},
            {"model_version": "v2.0", "mape": 10.0, "rmse": 0.02, "count": 60},
        ]

        result = await service.update_ensemble_weights("US")

        assert result is not None
        # v2.1: 1/5=0.2, v2.0: 1/10=0.1 => total=0.3
        # raw: v2.1=0.667, v2.0=0.333
        # clamped: v2.1=max(0.1,min(0.8,0.667))=0.667, v2.0=max(0.1,min(0.8,0.333))=0.333
        # re-normalized: v2.1=0.667/1.0=0.667, v2.0=0.333/1.0=0.333
        assert result["v2.1"] > result["v2.0"]
        # Weights should sum to ~1.0
        total = sum(result.values())
        assert abs(total - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_three_models_with_clamping(self, service, mock_obs, mock_redis):
        """Three models where one dominates -- clamping should kick in."""
        mock_obs.get_model_accuracy_by_version.return_value = [
            {"model_version": "v3.0", "mape": 1.0, "rmse": 0.002, "count": 40},
            {"model_version": "v2.0", "mape": 50.0, "rmse": 0.05, "count": 30},
            {"model_version": "v1.0", "mape": 100.0, "rmse": 0.10, "count": 20},
        ]

        result = await service.update_ensemble_weights("US")

        assert result is not None
        # v3.0: 1/1=1.0, v2.0: 1/50=0.02, v1.0: 1/100=0.01
        # total = 1.03
        # raw: v3.0=0.971, v2.0=0.019, v1.0=0.0097
        # clamped: v3.0=0.8, v2.0=0.1, v1.0=0.1
        # sum=1.0, normalized: v3.0=0.8, v2.0=0.1, v1.0=0.1
        assert result["v3.0"] >= 0.1
        assert result["v2.0"] >= 0.1
        assert result["v1.0"] >= 0.1
        assert result["v3.0"] <= 0.8
        total = sum(result.values())
        assert abs(total - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_zero_mape_treated_as_perfect(self, service, mock_obs, mock_redis):
        """Model with mape=0 (or None) gets inverse_error=1.0 (default)."""
        mock_obs.get_model_accuracy_by_version.return_value = [
            {"model_version": "v2.1", "mape": 0, "rmse": 0.0, "count": 10},
            {"model_version": "v2.0", "mape": 5.0, "rmse": 0.01, "count": 10},
        ]

        result = await service.update_ensemble_weights("US")

        assert result is not None
        # v2.1: mape=0 => inverse=1.0 (default), v2.0: 1/5=0.2
        # total=1.2, raw: v2.1=0.833, v2.0=0.167
        # clamped: v2.1=0.8, v2.0=0.167 => min 0.1 => 0.167
        # re-normalized
        assert result["v2.1"] > result["v2.0"]

    @pytest.mark.asyncio
    async def test_none_mape_treated_as_default(self, service, mock_obs, mock_redis):
        """Model with mape=None gets inverse_error=1.0."""
        mock_obs.get_model_accuracy_by_version.return_value = [
            {"model_version": "v2.1", "mape": None, "count": 5},
        ]

        result = await service.update_ensemble_weights("US")

        assert result is not None
        assert result["v2.1"] == 1.0  # single model normalizes to 1.0

    @pytest.mark.asyncio
    async def test_redis_write_on_success(self, service, mock_obs, mock_redis):
        """Should write weights to Redis in the expected format."""
        mock_obs.get_model_accuracy_by_version.return_value = [
            {"model_version": "v2.1", "mape": 5.0, "count": 50},
        ]

        await service.update_ensemble_weights("US")

        mock_redis.set.assert_awaited_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "model:ensemble_weights"
        payload = json.loads(call_args[0][1])
        assert "v2.1" in payload
        assert "weight" in payload["v2.1"]

    @pytest.mark.asyncio
    async def test_no_redis_still_returns_weights(self, service_no_redis, mock_obs):
        """Should return weights even when Redis is None."""
        mock_obs.get_model_accuracy_by_version.return_value = [
            {"model_version": "v2.1", "mape": 5.0, "count": 50},
        ]

        result = await service_no_redis.update_ensemble_weights("US")

        assert result is not None
        assert "v2.1" in result

    @pytest.mark.asyncio
    async def test_redis_error_does_not_raise(self, service, mock_obs, mock_redis):
        """Redis failure should be logged but not propagate."""
        mock_obs.get_model_accuracy_by_version.return_value = [
            {"model_version": "v2.1", "mape": 5.0, "count": 50},
        ]
        mock_redis.set.side_effect = ConnectionError("Redis down")

        # Patch the logger to accept structlog-style kwargs used in production code
        with patch("services.learning_service.logger") as mock_logger:
            result = await service.update_ensemble_weights("US")

        assert result is not None
        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_weights_are_rounded_to_four_decimals(self, service, mock_obs, mock_redis):
        """All weight values should be rounded to 4 decimal places."""
        mock_obs.get_model_accuracy_by_version.return_value = [
            {"model_version": "v2.1", "mape": 3.0, "count": 40},
            {"model_version": "v2.0", "mape": 7.0, "count": 30},
        ]

        result = await service.update_ensemble_weights("US")

        for version, weight in result.items():
            # Check that weight has at most 4 decimal places
            assert weight == round(weight, 4)


# =============================================================================
# TestStoreBiasCorrection
# =============================================================================


class TestStoreBiasCorrection:
    """Tests for LearningService.store_bias_correction"""

    @pytest.mark.asyncio
    async def test_empty_bias_returns_none(self, service, mock_obs):
        """Should return None when no bias data is available."""
        mock_obs.get_hourly_bias.return_value = []

        result = await service.store_bias_correction("US")

        assert result is None

    @pytest.mark.asyncio
    async def test_stores_vector_in_vector_store(self, service, mock_obs, mock_vs):
        """Should insert a 24-dim vector into the vector store."""
        mock_obs.get_hourly_bias.return_value = [
            {"hour": 0, "avg_bias": 0.001, "count": 10},
            {"hour": 12, "avg_bias": -0.005, "count": 15},
        ]

        result = await service.store_bias_correction("US", days=14)

        assert result == "vec-123"
        mock_vs.async_insert.assert_called_once()

        call_kwargs = mock_vs.async_insert.call_args
        assert call_kwargs[1]["domain"] == "bias_correction"
        assert call_kwargs[1]["confidence"] == 1.0
        # Metadata should contain region and raw_bias
        meta = call_kwargs[1]["metadata"]
        assert meta["region"] == "US"
        assert meta["days"] == 14
        assert isinstance(meta["raw_bias"], list)
        assert len(meta["raw_bias"]) == 24

    @pytest.mark.asyncio
    async def test_bias_vector_has_correct_hours(self, service, mock_obs, mock_vs):
        """Bias values should be placed at the correct hour index."""
        mock_obs.get_hourly_bias.return_value = [
            {"hour": 5, "avg_bias": 0.01, "count": 20},
            {"hour": 23, "avg_bias": -0.02, "count": 10},
        ]

        await service.store_bias_correction("US")

        call_kwargs = mock_vs.async_insert.call_args
        raw_bias = call_kwargs[1]["metadata"]["raw_bias"]
        assert raw_bias[5] == pytest.approx(0.01, abs=1e-6)
        assert raw_bias[23] == pytest.approx(-0.02, abs=1e-6)
        # Other hours should be 0
        assert raw_bias[0] == pytest.approx(0.0, abs=1e-6)
        assert raw_bias[12] == pytest.approx(0.0, abs=1e-6)

    @pytest.mark.asyncio
    async def test_vector_is_numpy_24_dim(self, service, mock_obs, mock_vs):
        """The vector passed to insert should be a numpy array of dimension 24."""
        mock_obs.get_hourly_bias.return_value = [
            {"hour": 0, "avg_bias": 0.001, "count": 10},
        ]

        await service.store_bias_correction("US")

        call_kwargs = mock_vs.async_insert.call_args
        vector = call_kwargs[1]["vector"]
        assert isinstance(vector, np.ndarray)
        assert vector.shape == (24,)

    @pytest.mark.asyncio
    async def test_out_of_range_hours_ignored(self, service, mock_obs, mock_vs):
        """Hours outside 0-23 should be silently ignored."""
        mock_obs.get_hourly_bias.return_value = [
            {"hour": -1, "avg_bias": 999.0, "count": 1},
            {"hour": 24, "avg_bias": 999.0, "count": 1},
            {"hour": 12, "avg_bias": 0.01, "count": 10},
        ]

        await service.store_bias_correction("US")

        call_kwargs = mock_vs.async_insert.call_args
        raw_bias = call_kwargs[1]["metadata"]["raw_bias"]
        # Only hour 12 should have a non-zero value
        assert raw_bias[12] == pytest.approx(0.01, abs=1e-6)
        # All others should be zero (including that nothing was set for -1 or 24)
        assert sum(abs(v) for i, v in enumerate(raw_bias) if i != 12) == pytest.approx(0.0, abs=1e-6)


# =============================================================================
# TestPruneStalePatterns
# =============================================================================


class TestPruneStalePatterns:
    """Tests for LearningService.prune_stale_patterns"""

    @pytest.mark.asyncio
    async def test_delegates_to_vector_store(self, service, mock_vs):
        """Should call vector_store.prune with correct args."""
        mock_vs.async_prune.return_value = 5

        result = await service.prune_stale_patterns(min_confidence=0.5, min_usage=2)

        mock_vs.async_prune.assert_called_once_with(0.5, 2)
        assert result == 5

    @pytest.mark.asyncio
    async def test_default_params(self, service, mock_vs):
        """Should use default min_confidence=0.3 and min_usage=0."""
        mock_vs.async_prune.return_value = 0

        await service.prune_stale_patterns()

        mock_vs.async_prune.assert_called_once_with(0.3, 0)

    @pytest.mark.asyncio
    async def test_zero_pruned(self, service, mock_vs):
        """Should return 0 when nothing is pruned."""
        mock_vs.async_prune.return_value = 0

        result = await service.prune_stale_patterns()

        assert result == 0


# =============================================================================
# TestRunFullCycle
# =============================================================================


class TestRunFullCycle:
    """Tests for LearningService.run_full_cycle"""

    @pytest.mark.asyncio
    async def test_default_regions_is_us(self, service, mock_obs, mock_vs):
        """Should default to ['US'] when no regions specified."""
        mock_obs.get_forecast_accuracy.return_value = {
            "total": 0, "mape": None, "rmse": None, "coverage": None,
        }
        mock_obs.get_model_accuracy_by_version.return_value = []
        mock_obs.get_hourly_bias.return_value = []

        result = await service.run_full_cycle()

        assert len(result["regions_processed"]) == 1
        assert result["regions_processed"][0]["region"] == "US"

    @pytest.mark.asyncio
    async def test_multi_region_loop(self, service, mock_obs, mock_vs):
        """Should process each region in the list."""
        mock_obs.get_forecast_accuracy.return_value = {
            "total": 10, "mape": 5.0, "rmse": 0.01, "coverage": 90.0,
        }
        mock_obs.get_model_accuracy_by_version.return_value = []
        mock_obs.get_hourly_bias.return_value = []

        result = await service.run_full_cycle(regions=["US", "UK", "DE"])

        assert len(result["regions_processed"]) == 3
        regions_seen = [r["region"] for r in result["regions_processed"]]
        assert regions_seen == ["US", "UK", "DE"]
        # get_forecast_accuracy called 3 times
        assert mock_obs.get_forecast_accuracy.await_count == 3

    @pytest.mark.asyncio
    async def test_weights_updated_populated(self, service, mock_obs, mock_vs, mock_redis):
        """Should populate weights_updated when model stats available."""
        mock_obs.get_forecast_accuracy.return_value = {
            "total": 100, "mape": 5.0, "rmse": 0.01, "coverage": 90.0,
        }
        mock_obs.get_model_accuracy_by_version.return_value = [
            {"model_version": "v2.1", "mape": 5.0, "count": 50},
        ]
        mock_obs.get_hourly_bias.return_value = []

        result = await service.run_full_cycle(regions=["US"])

        assert "US" in result["weights_updated"]
        assert "v2.1" in result["weights_updated"]["US"]

    @pytest.mark.asyncio
    async def test_bias_corrections_populated(self, service, mock_obs, mock_vs):
        """Should populate bias_corrections when bias data available."""
        mock_obs.get_forecast_accuracy.return_value = {
            "total": 50, "mape": 5.0, "rmse": 0.01, "coverage": 90.0,
        }
        mock_obs.get_model_accuracy_by_version.return_value = []
        mock_obs.get_hourly_bias.return_value = [
            {"hour": 0, "avg_bias": 0.001, "count": 10},
        ]

        result = await service.run_full_cycle(regions=["US"])

        assert "US" in result["bias_corrections"]
        assert result["bias_corrections"]["US"] == "vec-123"

    @pytest.mark.asyncio
    async def test_pruning_happens_once(self, service, mock_obs, mock_vs):
        """Pruning should happen once, not per-region."""
        mock_obs.get_forecast_accuracy.return_value = {
            "total": 0, "mape": None, "rmse": None, "coverage": None,
        }
        mock_obs.get_model_accuracy_by_version.return_value = []
        mock_obs.get_hourly_bias.return_value = []
        mock_vs.async_prune.return_value = 3

        result = await service.run_full_cycle(regions=["US", "UK"])

        mock_vs.async_prune.assert_called_once()
        assert result["pruned"] == 3

    @pytest.mark.asyncio
    async def test_redis_mape_update(self, service, mock_obs, mock_vs, mock_redis):
        """Should store primary region's MAPE in Redis."""
        mock_obs.get_forecast_accuracy.return_value = {
            "total": 100, "mape": 4.5, "rmse": 0.01, "coverage": 90.0,
        }
        mock_obs.get_model_accuracy_by_version.return_value = []
        mock_obs.get_hourly_bias.return_value = []

        await service.run_full_cycle(regions=["US"])

        # Redis should have model:recent_mape set
        calls = mock_redis.set.call_args_list
        mape_calls = [c for c in calls if c[0][0] == "model:recent_mape"]
        assert len(mape_calls) == 1
        assert mape_calls[0][0][1] == "4.5"

    @pytest.mark.asyncio
    async def test_redis_mape_skipped_when_none(self, service, mock_obs, mock_vs, mock_redis):
        """Should NOT write MAPE to Redis when accuracy returns None."""
        mock_obs.get_forecast_accuracy.return_value = {
            "total": 0, "mape": None, "rmse": None, "coverage": None,
        }
        mock_obs.get_model_accuracy_by_version.return_value = []
        mock_obs.get_hourly_bias.return_value = []

        await service.run_full_cycle(regions=["US"])

        # No Redis writes for model:recent_mape
        calls = mock_redis.set.call_args_list
        mape_calls = [c for c in calls if c[0][0] == "model:recent_mape"]
        assert len(mape_calls) == 0

    @pytest.mark.asyncio
    async def test_redis_mape_error_does_not_raise(self, service, mock_obs, mock_vs, mock_redis):
        """Redis failure during MAPE store should not crash the cycle."""
        mock_obs.get_forecast_accuracy.return_value = {
            "total": 100, "mape": 4.5, "rmse": 0.01, "coverage": 90.0,
        }
        mock_obs.get_model_accuracy_by_version.return_value = []
        mock_obs.get_hourly_bias.return_value = []
        mock_redis.set.side_effect = ConnectionError("Redis down")

        # Patch the logger to accept structlog-style kwargs used in production code
        with patch("services.learning_service.logger"):
            result = await service.run_full_cycle(regions=["US"])

        assert len(result["regions_processed"]) == 1

    @pytest.mark.asyncio
    async def test_no_redis_still_completes(self, service_no_redis, mock_obs, mock_vs):
        """Full cycle should complete even without Redis."""
        mock_obs.get_forecast_accuracy.return_value = {
            "total": 50, "mape": 3.0, "rmse": 0.005, "coverage": 95.0,
        }
        mock_obs.get_model_accuracy_by_version.return_value = []
        mock_obs.get_hourly_bias.return_value = []

        result = await service_no_redis.run_full_cycle(regions=["US"])

        assert len(result["regions_processed"]) == 1
        assert result["regions_processed"][0]["accuracy"]["mape"] == 3.0

    @pytest.mark.asyncio
    async def test_full_cycle_summary_structure(self, service, mock_obs, mock_vs):
        """Result dict should have all expected keys."""
        mock_obs.get_forecast_accuracy.return_value = {
            "total": 0, "mape": None, "rmse": None, "coverage": None,
        }
        mock_obs.get_model_accuracy_by_version.return_value = []
        mock_obs.get_hourly_bias.return_value = []

        result = await service.run_full_cycle()

        assert "regions_processed" in result
        assert "weights_updated" in result
        assert "bias_corrections" in result
        assert "pruned" in result

    @pytest.mark.asyncio
    async def test_full_cycle_custom_days(self, service, mock_obs, mock_vs):
        """Should pass days parameter through to all sub-calls."""
        mock_obs.get_forecast_accuracy.return_value = {
            "total": 0, "mape": None, "rmse": None, "coverage": None,
        }
        mock_obs.get_model_accuracy_by_version.return_value = []
        mock_obs.get_hourly_bias.return_value = []

        await service.run_full_cycle(regions=["US"], days=30)

        # Verify days=30 was passed to get_forecast_accuracy
        mock_obs.get_forecast_accuracy.assert_awaited_with("US", 30)
        # And to get_model_accuracy_by_version
        mock_obs.get_model_accuracy_by_version.assert_awaited_with("US", 30)
