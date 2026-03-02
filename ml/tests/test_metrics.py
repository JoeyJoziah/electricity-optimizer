"""
Unit Tests for ml/evaluation/metrics.py

Covers:
- Individual metric functions: MAE, RMSE, MAPE, sMAPE, R2
- Directional accuracy metrics (standard and weighted)
- Prediction interval coverage and interval score
- Business metrics: cost of prediction error, optimization savings impact
- calculate_all_metrics and evaluate_forecast aggregators
- compare_models DataFrame output
- Edge cases: zero values, single-element arrays, identical inputs, all-zeros
"""

import numpy as np
import pandas as pd
import pytest

from ml.evaluation.metrics import (
    ForecastMetrics,
    mean_absolute_error,
    root_mean_squared_error,
    mean_absolute_percentage_error,
    symmetric_mean_absolute_percentage_error,
    r2_score,
    direction_accuracy,
    weighted_direction_accuracy,
    prediction_interval_coverage,
    interval_score,
    cost_of_prediction_error,
    optimization_savings_impact,
    calculate_all_metrics,
    evaluate_forecast,
    compare_models,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_arrays(n: int = 24, seed: int = 42, noise: float = 0.02):
    """Return (y_true, y_pred) with mild noise added to true values."""
    rng = np.random.RandomState(seed)
    y_true = np.array([0.10 + 0.20 * abs(np.sin(i * np.pi / 12)) for i in range(n)])
    y_pred = y_true + rng.normal(0, noise, n)
    y_pred = np.maximum(y_pred, 0.001)
    return y_true, y_pred


def _make_intervals(y_pred: np.ndarray, half_width: float = 0.03):
    """Return symmetric prediction intervals around y_pred."""
    return y_pred - half_width, y_pred + half_width


# =============================================================================
# MAE
# =============================================================================


class TestMeanAbsoluteError:
    def test_perfect_forecast_is_zero(self):
        y = np.array([1.0, 2.0, 3.0])
        assert mean_absolute_error(y, y) == pytest.approx(0.0)

    def test_known_values(self):
        y_true = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([1.5, 2.5, 3.5])
        assert mean_absolute_error(y_true, y_pred) == pytest.approx(0.5)

    def test_symmetry(self):
        y_true = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([2.0, 3.0, 4.0])
        assert mean_absolute_error(y_true, y_pred) == mean_absolute_error(y_pred, y_true)

    def test_single_element(self):
        assert mean_absolute_error(np.array([5.0]), np.array([3.0])) == pytest.approx(2.0)

    def test_returns_float(self):
        result = mean_absolute_error(np.array([1.0, 2.0]), np.array([1.1, 2.1]))
        assert isinstance(result, float)

    def test_large_array(self):
        rng = np.random.RandomState(0)
        y_true = rng.uniform(0, 100, 10000)
        y_pred = y_true + rng.normal(0, 5, 10000)
        mae = mean_absolute_error(y_true, y_pred)
        assert mae > 0
        assert mae < 20  # Reasonable bound for std=5 noise


# =============================================================================
# RMSE
# =============================================================================


class TestRootMeanSquaredError:
    def test_perfect_forecast_is_zero(self):
        y = np.array([1.0, 2.0, 3.0])
        assert root_mean_squared_error(y, y) == pytest.approx(0.0)

    def test_known_values(self):
        y_true = np.array([0.0, 0.0])
        y_pred = np.array([3.0, 4.0])
        # sqrt((9 + 16) / 2) = sqrt(12.5)
        assert root_mean_squared_error(y_true, y_pred) == pytest.approx(np.sqrt(12.5))

    def test_rmse_gte_mae(self):
        y_true, y_pred = _make_arrays()
        assert root_mean_squared_error(y_true, y_pred) >= mean_absolute_error(y_true, y_pred)

    def test_single_element(self):
        assert root_mean_squared_error(np.array([5.0]), np.array([3.0])) == pytest.approx(2.0)


# =============================================================================
# MAPE
# =============================================================================


class TestMAPE:
    def test_perfect_forecast_is_zero(self):
        y = np.array([1.0, 2.0, 3.0])
        assert mean_absolute_percentage_error(y, y) == pytest.approx(0.0)

    def test_known_values(self):
        y_true = np.array([100.0, 200.0])
        y_pred = np.array([110.0, 220.0])
        # (|10/100| + |20/200|) / 2 * 100 = 10%
        assert mean_absolute_percentage_error(y_true, y_pred) == pytest.approx(10.0)

    def test_returns_inf_when_all_true_zero(self):
        y_true = np.array([0.0, 0.0, 0.0])
        y_pred = np.array([1.0, 2.0, 3.0])
        result = mean_absolute_percentage_error(y_true, y_pred)
        assert np.isinf(result)

    def test_skips_zero_true_values(self):
        y_true = np.array([0.0, 100.0])
        y_pred = np.array([1.0, 110.0])
        # Only second pair counted: 10%
        result = mean_absolute_percentage_error(y_true, y_pred)
        assert result == pytest.approx(10.0)

    def test_returns_percentage_not_fraction(self):
        y_true = np.array([100.0])
        y_pred = np.array([110.0])
        assert mean_absolute_percentage_error(y_true, y_pred) > 1.0  # Not 0.1


# =============================================================================
# sMAPE
# =============================================================================


class TestSMAPE:
    def test_perfect_forecast_is_zero(self):
        y = np.array([1.0, 2.0, 3.0])
        assert symmetric_mean_absolute_percentage_error(y, y) == pytest.approx(0.0)

    def test_returns_zero_when_all_zero(self):
        y_true = np.array([0.0, 0.0])
        y_pred = np.array([0.0, 0.0])
        assert symmetric_mean_absolute_percentage_error(y_true, y_pred) == pytest.approx(0.0)

    def test_known_values(self):
        y_true = np.array([100.0])
        y_pred = np.array([200.0])
        # 2*|100-200| / (|100| + |200|) * 100 = 200/300 * 100 = 66.67%
        result = symmetric_mean_absolute_percentage_error(y_true, y_pred)
        assert result == pytest.approx(200 / 3, rel=1e-3)

    def test_bounded_behavior(self):
        """sMAPE is bounded in [0, 200] by definition."""
        y_true, y_pred = _make_arrays()
        result = symmetric_mean_absolute_percentage_error(y_true, y_pred)
        assert 0.0 <= result <= 200.0


# =============================================================================
# R2 Score
# =============================================================================


class TestR2Score:
    def test_perfect_forecast_is_one(self):
        y = np.array([1.0, 2.0, 3.0, 4.0])
        assert r2_score(y, y) == pytest.approx(1.0)

    def test_constant_prediction_is_zero(self):
        y_true = np.array([1.0, 2.0, 3.0])
        # Predicting the mean: R2 = 0
        mean_pred = np.full(3, np.mean(y_true))
        assert r2_score(y_true, mean_pred) == pytest.approx(0.0)

    def test_can_be_negative(self):
        y_true = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([10.0, 20.0, 30.0])
        assert r2_score(y_true, y_pred) < 0.0

    def test_constant_y_true_returns_zero(self):
        """When y_true is constant, R2 is defined as 0 (no variance to explain)."""
        y_true = np.array([5.0, 5.0, 5.0])
        y_pred = np.array([4.0, 5.0, 6.0])
        assert r2_score(y_true, y_pred) == pytest.approx(0.0)

    def test_reasonable_forecast_positive_r2(self):
        y_true, y_pred = _make_arrays(noise=0.01)
        r2 = r2_score(y_true, y_pred)
        assert r2 > 0.5


# =============================================================================
# Direction Accuracy
# =============================================================================


class TestDirectionAccuracy:
    def test_perfect_direction_is_100(self):
        y_true = np.array([1.0, 2.0, 3.0, 2.0, 1.0])
        # Predictions shift same direction
        y_pred = np.array([1.0, 2.5, 3.5, 2.5, 1.5])
        acc = direction_accuracy(y_true, y_pred)
        assert acc == pytest.approx(100.0)

    def test_opposite_direction_is_zero(self):
        y_true = np.array([1.0, 2.0, 3.0, 4.0])
        y_pred = np.array([4.0, 3.0, 2.0, 1.0])
        acc = direction_accuracy(y_true, y_pred)
        assert acc == pytest.approx(0.0)

    def test_single_element_returns_zero(self):
        y = np.array([5.0])
        assert direction_accuracy(y, y) == 0.0

    def test_threshold_filters_small_changes(self):
        y_true = np.array([1.0, 1.001, 1.002])
        y_pred = np.array([1.0, 0.999, 1.003])
        # With large threshold, all changes filtered out
        acc = direction_accuracy(y_true, y_pred, threshold=0.01)
        assert acc == 0.0

    def test_returns_percentage_range(self):
        y_true, y_pred = _make_arrays()
        acc = direction_accuracy(y_true, y_pred)
        assert 0.0 <= acc <= 100.0


# =============================================================================
# Weighted Direction Accuracy
# =============================================================================


class TestWeightedDirectionAccuracy:
    def test_single_element_returns_zero(self):
        y = np.array([5.0])
        assert weighted_direction_accuracy(y, y) == 0.0

    def test_all_correct_returns_100(self):
        y_true = np.array([1.0, 3.0, 2.0])
        y_pred = np.array([1.0, 3.5, 2.5])
        acc = weighted_direction_accuracy(y_true, y_pred)
        assert acc == pytest.approx(100.0)

    def test_all_wrong_returns_zero(self):
        y_true = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([3.0, 2.0, 1.0])
        acc = weighted_direction_accuracy(y_true, y_pred)
        assert acc == pytest.approx(0.0)

    def test_large_moves_weighted_more(self):
        """A wrong prediction on a large move should hurt more than a small move."""
        # Two pairs: large up (+10), small up (+1). Predict wrong on large only.
        y_true = np.array([0.0, 10.0, 11.0])
        y_pred = np.array([0.0, 9.0, 10.5])  # Both correct up
        acc_all_right = weighted_direction_accuracy(y_true, y_pred)

        y_pred_wrong_large = np.array([0.0, 11.0, 10.5])  # Large: wrong, small: right
        acc_wrong_large = weighted_direction_accuracy(y_true, y_pred_wrong_large)

        assert acc_wrong_large < acc_all_right

    def test_threshold_no_valid_changes(self):
        y_true = np.array([1.0, 1.0001, 1.0002])
        y_pred = np.array([1.0, 1.0003, 1.0004])
        acc = weighted_direction_accuracy(y_true, y_pred, threshold=1.0)
        assert acc == 0.0

    def test_returns_percentage_range(self):
        y_true, y_pred = _make_arrays()
        acc = weighted_direction_accuracy(y_true, y_pred)
        assert 0.0 <= acc <= 100.0


# =============================================================================
# Prediction Interval Coverage
# =============================================================================


class TestPredictionIntervalCoverage:
    def test_all_within_interval_is_100(self):
        y_true = np.array([1.0, 2.0, 3.0])
        y_lower = np.array([0.0, 1.0, 2.0])
        y_upper = np.array([2.0, 3.0, 4.0])
        assert prediction_interval_coverage(y_true, y_lower, y_upper) == pytest.approx(100.0)

    def test_none_within_interval_is_zero(self):
        y_true = np.array([5.0, 5.0, 5.0])
        y_lower = np.array([0.0, 0.0, 0.0])
        y_upper = np.array([1.0, 1.0, 1.0])
        assert prediction_interval_coverage(y_true, y_lower, y_upper) == pytest.approx(0.0)

    def test_half_within_interval_is_50(self):
        y_true = np.array([0.5, 5.0])  # First inside, second outside
        y_lower = np.array([0.0, 0.0])
        y_upper = np.array([1.0, 1.0])
        assert prediction_interval_coverage(y_true, y_lower, y_upper) == pytest.approx(50.0)

    def test_boundary_values_are_covered(self):
        y_true = np.array([0.0, 1.0])  # Exactly at bounds
        y_lower = np.array([0.0, 0.0])
        y_upper = np.array([1.0, 1.0])
        assert prediction_interval_coverage(y_true, y_lower, y_upper) == pytest.approx(100.0)

    def test_returns_percentage_range(self):
        y_true, y_pred = _make_arrays()
        y_lower, y_upper = _make_intervals(y_pred)
        cov = prediction_interval_coverage(y_true, y_lower, y_upper)
        assert 0.0 <= cov <= 100.0


# =============================================================================
# Interval Score
# =============================================================================


class TestIntervalScore:
    def test_perfect_narrow_interval_penalizes_only_width(self):
        """If all values inside, score equals mean interval width."""
        y_true = np.array([1.0, 2.0, 3.0])
        y_lower = np.array([0.5, 1.5, 2.5])
        y_upper = np.array([1.5, 2.5, 3.5])
        score = interval_score(y_true, y_lower, y_upper, alpha=0.1)
        assert score == pytest.approx(1.0)  # All widths = 1.0

    def test_penalizes_values_below_lower(self):
        y_true = np.array([0.0])   # Below lower
        y_lower = np.array([1.0])
        y_upper = np.array([2.0])
        alpha = 0.1
        # width=1 + (2/0.1)*(1.0-0.0) = 1 + 20 = 21
        score = interval_score(y_true, y_lower, y_upper, alpha=alpha)
        assert score == pytest.approx(21.0)

    def test_penalizes_values_above_upper(self):
        y_true = np.array([3.0])   # Above upper
        y_lower = np.array([1.0])
        y_upper = np.array([2.0])
        alpha = 0.1
        # width=1 + (2/0.1)*(3.0-2.0) = 1 + 20 = 21
        score = interval_score(y_true, y_lower, y_upper, alpha=alpha)
        assert score == pytest.approx(21.0)

    def test_narrower_alpha_penalizes_more(self):
        """Smaller alpha (wider target coverage) means larger penalty for misses."""
        y_true = np.array([5.0])
        y_lower = np.array([0.0])
        y_upper = np.array([1.0])
        score_10 = interval_score(y_true, y_lower, y_upper, alpha=0.1)
        score_5 = interval_score(y_true, y_lower, y_upper, alpha=0.05)
        assert score_5 > score_10

    def test_returns_non_negative(self):
        y_true, y_pred = _make_arrays()
        y_lower, y_upper = _make_intervals(y_pred)
        score = interval_score(y_true, y_lower, y_upper)
        assert score >= 0.0


# =============================================================================
# Cost of Prediction Error
# =============================================================================


class TestCostOfPredictionError:
    def test_perfect_forecast_is_zero(self):
        y = np.array([0.10, 0.20, 0.30])
        assert cost_of_prediction_error(y, y) == pytest.approx(0.0)

    def test_positive_values(self):
        y_true = np.array([0.10, 0.20])
        y_pred = np.array([0.20, 0.30])
        cost = cost_of_prediction_error(y_true, y_pred, consumption_kwh=1.0)
        assert cost >= 0.0

    def test_scales_with_consumption(self):
        y_true = np.array([0.10])
        y_pred = np.array([0.20])
        cost_1 = cost_of_prediction_error(y_true, y_pred, consumption_kwh=1.0)
        cost_2 = cost_of_prediction_error(y_true, y_pred, consumption_kwh=2.0)
        assert cost_2 == pytest.approx(cost_1 * 2.0)

    def test_scales_with_multiplier(self):
        y_true = np.array([0.10, 0.10])
        y_pred = np.array([0.20, 0.20])
        cost_1 = cost_of_prediction_error(y_true, y_pred, cost_multiplier=1.0)
        cost_2 = cost_of_prediction_error(y_true, y_pred, cost_multiplier=3.0)
        assert cost_2 == pytest.approx(cost_1 * 3.0)


# =============================================================================
# Optimization Savings Impact
# =============================================================================


class TestOptimizationSavingsImpact:
    def test_perfect_forecast_zero_impact(self):
        y_true = np.array([0.10, 0.30, 0.10, 0.30])
        impact = optimization_savings_impact(y_true, y_true.copy())
        assert impact == pytest.approx(0.0, abs=1e-6)

    def test_returns_non_negative(self):
        y_true, y_pred = _make_arrays()
        impact = optimization_savings_impact(y_true, y_pred)
        assert impact >= 0.0

    def test_returns_bounded_percentage(self):
        y_true, y_pred = _make_arrays()
        impact = optimization_savings_impact(y_true, y_pred)
        assert 0.0 <= impact <= 100.0

    def test_uniform_prices_zero_impact(self):
        """When all prices are the same, timing doesn't matter, impact is 0."""
        y_true = np.full(10, 0.15)
        y_pred = y_true + np.random.RandomState(1).normal(0, 0.001, 10)
        impact = optimization_savings_impact(y_true, y_pred)
        assert impact == pytest.approx(0.0, abs=1e-6)


# =============================================================================
# calculate_all_metrics
# =============================================================================


class TestCalculateAllMetrics:
    def test_returns_forecast_metrics_instance(self):
        y_true, y_pred = _make_arrays()
        result = calculate_all_metrics(y_true, y_pred)
        assert isinstance(result, ForecastMetrics)

    def test_all_point_metrics_populated(self):
        y_true, y_pred = _make_arrays()
        m = calculate_all_metrics(y_true, y_pred)
        assert m.mae >= 0.0
        assert m.rmse >= 0.0
        assert m.mape >= 0.0
        assert m.smape >= 0.0
        assert m.mse >= 0.0
        assert isinstance(m.r2_score, float)

    def test_directional_metrics_populated(self):
        y_true, y_pred = _make_arrays()
        m = calculate_all_metrics(y_true, y_pred)
        assert 0.0 <= m.direction_accuracy <= 100.0
        assert 0.0 <= m.weighted_direction_accuracy <= 100.0

    def test_probabilistic_metrics_none_without_intervals(self):
        y_true, y_pred = _make_arrays()
        m = calculate_all_metrics(y_true, y_pred)
        assert m.coverage_90 is None
        assert m.coverage_95 is None
        assert m.interval_score_90 is None
        assert m.interval_score_95 is None

    def test_probabilistic_metrics_populated_with_intervals(self):
        y_true, y_pred = _make_arrays()
        y_lower, y_upper = _make_intervals(y_pred)
        m = calculate_all_metrics(y_true, y_pred, y_lower=y_lower, y_upper=y_upper)
        assert m.coverage_90 is not None
        assert m.coverage_95 is not None
        assert m.interval_score_90 is not None
        assert m.interval_score_95 is not None

    def test_business_metrics_populated(self):
        y_true, y_pred = _make_arrays()
        m = calculate_all_metrics(y_true, y_pred)
        assert m.cost_of_error is not None
        assert m.optimization_savings_impact is not None

    def test_sample_size_matches_input(self):
        y_true, y_pred = _make_arrays(n=48)
        m = calculate_all_metrics(y_true, y_pred)
        assert m.n_samples == 48

    def test_forecast_horizon_stored(self):
        y_true, y_pred = _make_arrays()
        m = calculate_all_metrics(y_true, y_pred, forecast_horizon=48)
        assert m.forecast_horizon == 48

    def test_to_dict_returns_dict(self):
        y_true, y_pred = _make_arrays()
        m = calculate_all_metrics(y_true, y_pred)
        d = m.to_dict()
        assert isinstance(d, dict)
        assert "mae" in d
        assert "rmse" in d

    def test_90_coverage_le_95_coverage(self):
        """90% intervals should have narrower coverage than 95% by definition."""
        y_true, y_pred = _make_arrays()
        y_lower, y_upper = _make_intervals(y_pred, half_width=0.05)
        m = calculate_all_metrics(y_true, y_pred, y_lower=y_lower, y_upper=y_upper)
        # 90% intervals are derived as a narrower subset of 95% intervals
        assert m.coverage_90 <= m.coverage_95 + 1.0  # Allow 1% tolerance


# =============================================================================
# evaluate_forecast
# =============================================================================


class TestEvaluateForecast:
    def test_returns_forecast_metrics_instance(self):
        y_true, y_pred = _make_arrays()
        m = evaluate_forecast(y_true, y_pred, verbose=False)
        assert isinstance(m, ForecastMetrics)

    def test_verbose_false_no_output(self, capsys):
        y_true, y_pred = _make_arrays()
        evaluate_forecast(y_true, y_pred, verbose=False)
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_verbose_true_prints_metrics(self, capsys):
        y_true, y_pred = _make_arrays()
        evaluate_forecast(y_true, y_pred, verbose=True)
        captured = capsys.readouterr()
        assert "MAE" in captured.out

    def test_with_intervals(self):
        y_true, y_pred = _make_arrays()
        y_lower, y_upper = _make_intervals(y_pred)
        m = evaluate_forecast(y_true, y_pred, y_lower=y_lower, y_upper=y_upper, verbose=False)
        assert m.coverage_95 is not None

    def test_perfect_prediction_mae_zero(self):
        y = np.array([0.10, 0.20, 0.30])
        m = evaluate_forecast(y, y.copy(), verbose=False)
        assert m.mae == pytest.approx(0.0)


# =============================================================================
# compare_models
# =============================================================================


class TestCompareModels:
    def setup_method(self):
        rng = np.random.RandomState(0)
        self.y_true = np.array([0.10, 0.20, 0.15, 0.30, 0.25, 0.10, 0.20, 0.15])
        self.predictions = {
            "ModelA": self.y_true + rng.normal(0, 0.01, len(self.y_true)),
            "ModelB": self.y_true + rng.normal(0, 0.05, len(self.y_true)),
            "ModelC": self.y_true + rng.normal(0, 0.02, len(self.y_true)),
        }

    def test_returns_dataframe(self):
        df = compare_models(self.y_true, self.predictions)
        assert isinstance(df, pd.DataFrame)

    def test_contains_all_models(self):
        df = compare_models(self.y_true, self.predictions)
        assert set(df["model"]) == {"ModelA", "ModelB", "ModelC"}

    def test_contains_required_columns(self):
        df = compare_models(self.y_true, self.predictions)
        for col in ["model", "mae", "rmse", "mape", "smape", "r2", "dir_acc"]:
            assert col in df.columns, f"Missing column: {col}"

    def test_sorted_by_mape_ascending_default(self):
        df = compare_models(self.y_true, self.predictions, metric="mape")
        mape_values = df["mape"].tolist()
        assert mape_values == sorted(mape_values)

    def test_sorted_by_r2_descending(self):
        df = compare_models(self.y_true, self.predictions, metric="r2")
        r2_values = df["r2"].tolist()
        assert r2_values == sorted(r2_values, reverse=True)

    def test_sorted_by_dir_acc_descending(self):
        df = compare_models(self.y_true, self.predictions, metric="dir_acc")
        values = df["dir_acc"].tolist()
        assert values == sorted(values, reverse=True)

    def test_single_model(self):
        df = compare_models(self.y_true, {"OnlyModel": self.predictions["ModelA"]})
        assert len(df) == 1

    def test_all_metrics_non_negative_where_expected(self):
        df = compare_models(self.y_true, self.predictions)
        for col in ["mae", "rmse", "mape", "smape"]:
            assert (df[col] >= 0).all(), f"{col} has negative values"


# =============================================================================
# ForecastMetrics dataclass
# =============================================================================


class TestForecastMetricsDataclass:
    def _basic_metrics(self, **overrides):
        defaults = dict(
            mae=0.01, rmse=0.02, mape=5.0, smape=4.8, mse=0.0004,
            r2_score=0.95, direction_accuracy=75.0, weighted_direction_accuracy=72.0,
            n_samples=24, forecast_horizon=24,
        )
        defaults.update(overrides)
        return ForecastMetrics(**defaults)

    def test_to_dict_contains_all_fields(self):
        m = self._basic_metrics()
        d = m.to_dict()
        for attr in ["mae", "rmse", "mape", "smape", "mse", "r2_score",
                     "direction_accuracy", "weighted_direction_accuracy",
                     "n_samples", "forecast_horizon"]:
            assert attr in d

    def test_str_contains_key_labels(self):
        m = self._basic_metrics()
        s = str(m)
        assert "MAE" in s
        assert "RMSE" in s
        assert "MAPE" in s
        assert "R" in s

    def test_str_includes_probabilistic_metrics_when_set(self):
        m = self._basic_metrics(
            coverage_90=88.0,
            coverage_95=94.0,
            interval_score_90=0.05,
            interval_score_95=0.04,
        )
        s = str(m)
        assert "Coverage" in s or "90%" in s

    def test_str_includes_business_metrics_when_set(self):
        m = self._basic_metrics(cost_of_error=1.23, optimization_savings_impact=8.5)
        s = str(m)
        assert "Cost" in s or "$" in s

    def test_optional_fields_default_to_none(self):
        m = self._basic_metrics()
        assert m.coverage_90 is None
        assert m.coverage_95 is None
        assert m.cost_of_error is None
        assert m.optimization_savings_impact is None


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    def test_single_element_arrays_work_for_all_point_metrics(self):
        y_true = np.array([0.15])
        y_pred = np.array([0.20])
        assert mean_absolute_error(y_true, y_pred) == pytest.approx(0.05)
        assert root_mean_squared_error(y_true, y_pred) == pytest.approx(0.05)
        # MAPE: 100 * |0.15-0.20| / 0.15
        assert mean_absolute_percentage_error(y_true, y_pred) == pytest.approx(100.0 / 3, rel=0.01)

    def test_very_close_predictions_near_zero_metrics(self):
        y_true = np.linspace(0.1, 0.5, 100)
        y_pred = y_true + 1e-9
        assert mean_absolute_error(y_true, y_pred) < 1e-7
        assert root_mean_squared_error(y_true, y_pred) < 1e-7

    def test_calculate_all_metrics_with_equal_arrays(self):
        y = np.linspace(0.10, 0.40, 24)
        m = calculate_all_metrics(y, y.copy())
        assert m.mae == pytest.approx(0.0)
        assert m.rmse == pytest.approx(0.0)
        assert m.mape == pytest.approx(0.0)
        assert m.r2_score == pytest.approx(1.0)

    def test_direction_accuracy_two_elements(self):
        y_true = np.array([1.0, 2.0])
        y_pred = np.array([1.0, 2.5])
        acc = direction_accuracy(y_true, y_pred)
        assert acc == pytest.approx(100.0)

    def test_numpy_float32_input(self):
        y_true = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        y_pred = np.array([1.1, 2.1, 3.1], dtype=np.float32)
        mae = mean_absolute_error(y_true, y_pred)
        assert mae == pytest.approx(0.1, abs=1e-5)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
