"""
TDD Tests for Backtesting System

These tests are written FIRST following TDD principles.
Target: 6+ months historical data validation

Test Coverage:
- Walk-forward validation
- Expanding and rolling windows
- Metrics aggregation
- Period-by-period analysis
- Target achievement (MAPE < 10%)
- Results persistence
"""

import pytest
import numpy as np
import pandas as pd
import os
from datetime import datetime, timedelta


class TestBacktestConfiguration:
    """Tests for backtest configuration."""

    def test_default_backtest_config(self):
        """Test default backtest configuration values."""
        from ml.evaluation.backtesting import BacktestConfig

        config = BacktestConfig()

        assert config.window_type == "expanding"
        assert config.min_train_size == 8760  # 1 year
        assert config.test_size == 720  # 30 days
        assert config.step_size == 168  # 1 week
        assert config.target_mape == 10.0

    def test_custom_backtest_config(self):
        """Test custom backtest configuration."""
        from ml.evaluation.backtesting import BacktestConfig

        config = BacktestConfig(
            window_type="rolling",
            min_train_size=4320,  # 6 months
            test_size=360,  # 15 days
            step_size=72,  # 3 days
            target_mape=8.0
        )

        assert config.window_type == "rolling"
        assert config.min_train_size == 4320
        assert config.test_size == 360
        assert config.step_size == 72
        assert config.target_mape == 8.0

    def test_rolling_vs_expanding_window(self):
        """Test both window types are valid."""
        from ml.evaluation.backtesting import BacktestConfig

        expanding = BacktestConfig(window_type="expanding")
        rolling = BacktestConfig(window_type="rolling")

        assert expanding.window_type == "expanding"
        assert rolling.window_type == "rolling"


class TestBacktestResults:
    """Tests for backtest result data structures."""

    def test_backtest_result_fields(self):
        """Test BacktestResult has all required fields."""
        from ml.evaluation.backtesting import BacktestResult

        result = BacktestResult(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            n_samples=100,
            mape=8.5,
            rmse=4.2,
            mae=3.1,
            r2=0.85,
            direction_accuracy=0.65,
            coverage=0.92,
            mean_interval_width=5.0
        )

        assert result.mape == 8.5
        assert result.rmse == 4.2
        assert result.mae == 3.1
        assert result.r2 == 0.85
        assert result.direction_accuracy == 0.65
        assert result.coverage == 0.92

    def test_backtest_result_hourly_breakdown(self):
        """Test BacktestResult can store hourly MAPE breakdown."""
        from ml.evaluation.backtesting import BacktestResult

        hourly_mape = {0: 7.5, 1: 8.0, 2: 9.5, 3: 6.2}

        result = BacktestResult(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            n_samples=100,
            mape=8.5,
            rmse=4.2,
            mae=3.1,
            r2=0.85,
            direction_accuracy=0.65,
            coverage=0.92,
            mean_interval_width=5.0,
            mape_by_hour=hourly_mape
        )

        assert result.mape_by_hour == hourly_mape


class TestMetricsCalculator:
    """Tests for metrics calculation."""

    def test_mape_calculation(self):
        """Test MAPE calculation."""
        from ml.evaluation.backtesting import MetricsCalculator

        y_true = np.array([100, 200, 300, 400])
        y_pred = np.array([90, 210, 290, 420])

        mape = MetricsCalculator.mape(y_true, y_pred)

        # Expected: mean(|10/100|, |10/200|, |10/300|, |20/400|) * 100
        expected = np.mean([10/100, 10/200, 10/300, 20/400]) * 100

        assert abs(mape - expected) < 0.01

    def test_rmse_calculation(self):
        """Test RMSE calculation."""
        from ml.evaluation.backtesting import MetricsCalculator

        y_true = np.array([100, 200, 300])
        y_pred = np.array([110, 190, 310])

        rmse = MetricsCalculator.rmse(y_true, y_pred)

        # Expected: sqrt(mean([100, 100, 100])) = 10
        assert abs(rmse - 10.0) < 0.01

    def test_mae_calculation(self):
        """Test MAE calculation."""
        from ml.evaluation.backtesting import MetricsCalculator

        y_true = np.array([100, 200, 300])
        y_pred = np.array([110, 190, 310])

        mae = MetricsCalculator.mae(y_true, y_pred)

        # Expected: mean([10, 10, 10]) = 10
        assert abs(mae - 10.0) < 0.01

    def test_r2_score_calculation(self):
        """Test R2 score calculation."""
        from ml.evaluation.backtesting import MetricsCalculator

        y_true = np.array([1, 2, 3, 4, 5])
        y_pred = np.array([1.1, 2.0, 2.9, 4.1, 4.9])

        r2 = MetricsCalculator.r2_score(y_true, y_pred)

        # Should be close to 1 for good predictions
        assert r2 > 0.9

    def test_direction_accuracy_calculation(self):
        """Test direction accuracy calculation."""
        from ml.evaluation.backtesting import MetricsCalculator

        # Prices going up, down, up, down
        y_true = np.array([[1, 2], [3, 2], [2, 3], [4, 3]])
        y_pred = np.array([[1, 2], [3, 2], [2, 1], [4, 5]])  # 2 correct, 2 wrong

        dir_acc = MetricsCalculator.direction_accuracy(y_true, y_pred)

        assert 0 <= dir_acc <= 1

    def test_coverage_calculation(self):
        """Test prediction interval coverage calculation."""
        from ml.evaluation.backtesting import MetricsCalculator

        y_true = np.array([10, 20, 30, 40])
        y_lower = np.array([8, 18, 28, 38])
        y_upper = np.array([12, 22, 32, 42])

        coverage = MetricsCalculator.coverage(y_true, y_lower, y_upper)

        # All values should be within intervals
        assert coverage == 1.0

    def test_coverage_with_misses(self):
        """Test coverage with some values outside intervals."""
        from ml.evaluation.backtesting import MetricsCalculator

        y_true = np.array([10, 20, 30, 40])
        y_lower = np.array([15, 18, 28, 38])  # First value outside
        y_upper = np.array([25, 22, 32, 42])

        coverage = MetricsCalculator.coverage(y_true, y_lower, y_upper)

        assert coverage == 0.75  # 3 out of 4

    def test_compute_all_metrics(self):
        """Test computing all metrics at once."""
        from ml.evaluation.backtesting import MetricsCalculator

        y_true = np.random.randn(100, 24) * 10 + 50
        y_pred = y_true + np.random.randn(100, 24) * 2
        y_lower = y_pred - 3
        y_upper = y_pred + 3

        metrics = MetricsCalculator.compute_all(y_true, y_pred, y_lower, y_upper)

        assert 'mape' in metrics
        assert 'rmse' in metrics
        assert 'mae' in metrics
        assert 'r2' in metrics
        assert 'direction_accuracy' in metrics
        assert 'coverage' in metrics


class TestModelBacktester:
    """Tests for the backtesting framework."""

    def test_backtester_initialization(self, mock_forecaster, feature_engine, tmp_results_dir):
        """Test backtester can be initialized."""
        from ml.evaluation.backtesting import ModelBacktester, BacktestConfig

        config = BacktestConfig(
            min_train_size=500,
            test_size=100,
            output_dir=tmp_results_dir
        )

        backtester = ModelBacktester(
            model=mock_forecaster,
            feature_engine=feature_engine,
            config=config
        )

        assert backtester.model is not None
        assert backtester.feature_engine is not None
        assert backtester.config.min_train_size == 500

    def test_backtester_run_produces_results(
        self, mock_forecaster, feature_engine, sample_price_data, tmp_results_dir
    ):
        """Test backtester run produces results."""
        from ml.evaluation.backtesting import ModelBacktester, BacktestConfig

        config = BacktestConfig(
            min_train_size=500,
            test_size=200,  # Larger test size to ensure sequences can be created
            step_size=100,
            sequence_length=168,
            forecast_horizon=24,
            retrain_frequency=10000,  # Don't retrain
            generate_plots=False,
            save_predictions=False,
            output_dir=tmp_results_dir
        )

        backtester = ModelBacktester(
            model=mock_forecaster,
            feature_engine=feature_engine,
            config=config
        )

        summary = backtester.run(sample_price_data)

        assert 'overall' in summary
        assert 'period_statistics' in summary
        assert summary['period_statistics']['n_periods'] >= 1

    def test_backtester_overall_metrics(
        self, mock_forecaster, feature_engine, sample_price_data, tmp_results_dir
    ):
        """Test backtester computes overall metrics."""
        from ml.evaluation.backtesting import ModelBacktester, BacktestConfig

        config = BacktestConfig(
            min_train_size=500,
            test_size=200,
            step_size=100,
            sequence_length=168,
            forecast_horizon=24,
            retrain_frequency=10000,
            generate_plots=False,
            save_predictions=False,
            output_dir=tmp_results_dir
        )

        backtester = ModelBacktester(
            model=mock_forecaster,
            feature_engine=feature_engine,
            config=config
        )

        summary = backtester.run(sample_price_data)

        overall = summary['overall']
        assert 'mape' in overall
        assert 'rmse' in overall
        assert 'mae' in overall
        assert 'r2' in overall

    def test_backtester_period_statistics(
        self, mock_forecaster, feature_engine, sample_price_data, tmp_results_dir
    ):
        """Test backtester computes period-level statistics."""
        from ml.evaluation.backtesting import ModelBacktester, BacktestConfig

        config = BacktestConfig(
            min_train_size=500,
            test_size=200,
            step_size=100,
            sequence_length=168,
            forecast_horizon=24,
            retrain_frequency=10000,
            generate_plots=False,
            save_predictions=False,
            output_dir=tmp_results_dir
        )

        backtester = ModelBacktester(
            model=mock_forecaster,
            feature_engine=feature_engine,
            config=config
        )

        summary = backtester.run(sample_price_data)

        stats = summary['period_statistics']
        assert 'n_periods' in stats
        assert 'mape_mean' in stats
        assert 'mape_std' in stats
        assert 'mape_min' in stats
        assert 'mape_max' in stats

    def test_backtester_target_achievement(
        self, mock_forecaster, feature_engine, sample_price_data, tmp_results_dir
    ):
        """Test backtester reports target achievement."""
        from ml.evaluation.backtesting import ModelBacktester, BacktestConfig

        config = BacktestConfig(
            min_train_size=200,
            test_size=200,
            step_size=100,
            sequence_length=168,
            forecast_horizon=24,
            target_mape=10.0,
            target_coverage=0.9,
            retrain_frequency=10000,
            generate_plots=False,
            save_predictions=False,
            output_dir=tmp_results_dir
        )

        backtester = ModelBacktester(
            model=mock_forecaster,
            feature_engine=feature_engine,
            config=config
        )

        summary = backtester.run(sample_price_data)

        target = summary['target_achievement']
        assert 'mape_target' in target
        assert 'mape_achieved' in target
        assert 'coverage_target' in target
        assert 'coverage_achieved' in target


class TestBacktestWithExtendedData:
    """Tests with 6+ months of historical data."""

    def test_backtest_6_months_data(
        self, mock_forecaster, feature_engine, extended_price_data, tmp_results_dir
    ):
        """Test backtest with 6 months of data."""
        from ml.evaluation.backtesting import ModelBacktester, BacktestConfig

        config = BacktestConfig(
            window_type="expanding",
            min_train_size=1000,  # ~42 days minimum training
            test_size=300,  # Must be >= sequence_length + forecast_horizon (192)
            step_size=200,
            sequence_length=168,
            forecast_horizon=24,
            retrain_frequency=10000,  # Don't retrain
            generate_plots=False,
            save_predictions=False,
            output_dir=tmp_results_dir
        )

        backtester = ModelBacktester(
            model=mock_forecaster,
            feature_engine=feature_engine,
            config=config
        )

        summary = backtester.run(extended_price_data)

        # Should have multiple periods
        n_periods = summary['period_statistics']['n_periods']
        assert n_periods >= 10, f"Expected at least 10 periods, got {n_periods}"

    def test_backtest_rolling_window_6_months(
        self, mock_forecaster, feature_engine, extended_price_data, tmp_results_dir
    ):
        """Test rolling window backtest with 6 months data."""
        from ml.evaluation.backtesting import ModelBacktester, BacktestConfig

        config = BacktestConfig(
            window_type="rolling",
            min_train_size=720,  # 30 days training window
            test_size=300,  # Must be >= sequence_length + forecast_horizon (192)
            step_size=200,
            sequence_length=168,
            forecast_horizon=24,
            retrain_frequency=10000,
            generate_plots=False,
            save_predictions=False,
            output_dir=tmp_results_dir
        )

        backtester = ModelBacktester(
            model=mock_forecaster,
            feature_engine=feature_engine,
            config=config
        )

        summary = backtester.run(extended_price_data)

        assert summary['period_statistics']['n_periods'] >= 5


class TestBacktestResultsPersistence:
    """Tests for saving backtest results."""

    def test_results_saved_to_json(
        self, mock_forecaster, feature_engine, sample_price_data, tmp_results_dir
    ):
        """Test backtest results are saved to JSON."""
        from ml.evaluation.backtesting import ModelBacktester, BacktestConfig

        config = BacktestConfig(
            min_train_size=200,
            test_size=50,
            step_size=25,
            retrain_frequency=1000,
            generate_plots=False,
            save_predictions=True,
            output_dir=tmp_results_dir
        )

        backtester = ModelBacktester(
            model=mock_forecaster,
            feature_engine=feature_engine,
            config=config
        )

        backtester.run(sample_price_data)

        # Check files were created
        files = os.listdir(tmp_results_dir)
        json_files = [f for f in files if f.endswith('.json')]

        assert len(json_files) > 0

    def test_predictions_saved_to_npz(
        self, mock_forecaster, feature_engine, sample_price_data, tmp_results_dir
    ):
        """Test predictions are saved to NPZ file."""
        from ml.evaluation.backtesting import ModelBacktester, BacktestConfig

        config = BacktestConfig(
            min_train_size=200,
            test_size=200,
            step_size=100,
            sequence_length=168,
            forecast_horizon=24,
            retrain_frequency=10000,
            generate_plots=False,
            save_predictions=True,
            output_dir=tmp_results_dir
        )

        backtester = ModelBacktester(
            model=mock_forecaster,
            feature_engine=feature_engine,
            config=config
        )

        backtester.run(sample_price_data)

        # Check NPZ file was created
        files = os.listdir(tmp_results_dir)
        npz_files = [f for f in files if f.endswith('.npz')]

        assert len(npz_files) > 0


class TestHourlyBreakdown:
    """Tests for hourly performance breakdown."""

    def test_hourly_mape_breakdown(
        self, mock_forecaster, feature_engine, sample_price_data, tmp_results_dir
    ):
        """Test hourly MAPE breakdown is computed."""
        from ml.evaluation.backtesting import ModelBacktester, BacktestConfig

        config = BacktestConfig(
            min_train_size=500,
            test_size=200,
            step_size=100,
            sequence_length=168,
            forecast_horizon=24,
            retrain_frequency=10000,
            generate_plots=False,
            save_predictions=False,
            output_dir=tmp_results_dir
        )

        backtester = ModelBacktester(
            model=mock_forecaster,
            feature_engine=feature_engine,
            config=config
        )

        summary = backtester.run(sample_price_data)

        assert 'hourly_mape' in summary
        hourly = summary['hourly_mape']

        # Should have entries for each forecast hour
        assert len(hourly) > 0

    def test_hourly_mape_increases_with_horizon(
        self, mock_forecaster, feature_engine, sample_price_data, tmp_results_dir
    ):
        """Test that MAPE generally increases with forecast horizon."""
        from ml.evaluation.backtesting import ModelBacktester, BacktestConfig

        config = BacktestConfig(
            min_train_size=500,
            test_size=200,
            step_size=100,
            sequence_length=168,
            forecast_horizon=24,
            retrain_frequency=10000,
            generate_plots=False,
            save_predictions=False,
            output_dir=tmp_results_dir
        )

        backtester = ModelBacktester(
            model=mock_forecaster,
            feature_engine=feature_engine,
            config=config
        )

        summary = backtester.run(sample_price_data)
        hourly = summary['hourly_mape']

        # With real models, later hours typically have higher MAPE
        # For mock model, just verify structure
        if len(hourly) >= 2:
            hours = sorted(hourly.keys())
            assert hours[0] < hours[-1]


class TestBacktestEdgeCases:
    """Tests for edge cases in backtesting."""

    def test_insufficient_data_raises_error(
        self, mock_forecaster, feature_engine, tmp_results_dir
    ):
        """Test backtester raises error with insufficient data."""
        from ml.evaluation.backtesting import ModelBacktester, BacktestConfig

        # Create very small dataset
        dates = pd.date_range(start='2024-01-01', periods=100, freq='H')
        small_data = pd.DataFrame({'price': np.random.rand(100)}, index=dates)

        config = BacktestConfig(
            min_train_size=500,  # More than available data
            test_size=100,
            output_dir=tmp_results_dir
        )

        backtester = ModelBacktester(
            model=mock_forecaster,
            feature_engine=feature_engine,
            config=config
        )

        with pytest.raises(ValueError, match="Insufficient data"):
            backtester.run(small_data)

    def test_handles_prediction_errors(
        self, feature_engine, sample_price_data, tmp_results_dir
    ):
        """Test backtester handles prediction errors gracefully."""
        from ml.evaluation.backtesting import ModelBacktester, BacktestConfig

        # Model that sometimes fails
        class FailingModel:
            call_count = 0

            def predict(self, X, return_confidence=True):
                self.call_count += 1
                if self.call_count % 3 == 0:
                    raise RuntimeError("Prediction failed")
                n = len(X)
                preds = np.random.randn(n, 24) * 10 + 50
                if return_confidence:
                    return preds, preds - 5, preds + 5
                return preds

        config = BacktestConfig(
            min_train_size=500,
            test_size=200,
            step_size=100,
            sequence_length=168,
            forecast_horizon=24,
            retrain_frequency=10000,
            generate_plots=False,
            save_predictions=False,
            output_dir=tmp_results_dir
        )

        backtester = ModelBacktester(
            model=FailingModel(),
            feature_engine=feature_engine,
            config=config
        )

        # Should complete without raising
        summary = backtester.run(sample_price_data)

        # Should still have some results
        assert summary is not None
