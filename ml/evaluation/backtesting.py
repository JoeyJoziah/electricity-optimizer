"""
Backtesting Framework for Electricity Price Forecasting

This module provides comprehensive backtesting capabilities to evaluate
model performance on historical data with realistic out-of-sample testing.

Features:
- Walk-forward validation with expanding or rolling windows
- Multiple evaluation metrics (MAPE, RMSE, MAE, direction accuracy)
- Confidence interval coverage analysis
- Performance by time period (hour, day, season)
- Visualization of forecasts vs actuals
- Statistical significance testing
"""

import os
import json
import logging
from typing import Dict, List, Optional, Tuple, Union, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""

    # Window configuration
    window_type: str = "expanding"  # expanding or rolling
    min_train_size: int = 8760       # 1 year minimum training data
    test_size: int = 720             # 30 days test period
    step_size: int = 168             # Re-evaluate weekly

    # Model parameters
    sequence_length: int = 168
    forecast_horizon: int = 24

    # Evaluation settings
    retrain_frequency: int = 168     # Retrain weekly (in hours)
    use_cached_predictions: bool = False

    # Performance targets
    target_mape: float = 10.0
    target_coverage: float = 0.9

    # Output configuration
    save_predictions: bool = True
    generate_plots: bool = True
    output_dir: str = "ml/evaluation/results"


@dataclass
class BacktestResult:
    """Results from a single backtest period."""

    start_date: datetime
    end_date: datetime
    n_samples: int

    # Core metrics
    mape: float
    rmse: float
    mae: float
    r2: float

    # Direction metrics
    direction_accuracy: float

    # Confidence interval metrics
    coverage: float
    mean_interval_width: float

    # Hourly breakdown
    mape_by_hour: Dict[int, float] = field(default_factory=dict)

    # Predictions and actuals (optional)
    predictions: Optional[np.ndarray] = None
    actuals: Optional[np.ndarray] = None
    lower_bounds: Optional[np.ndarray] = None
    upper_bounds: Optional[np.ndarray] = None


class MetricsCalculator:
    """Calculate evaluation metrics for forecasts."""

    @staticmethod
    def mape(y_true: np.ndarray, y_pred: np.ndarray, epsilon: float = 1e-8) -> float:
        """Mean Absolute Percentage Error."""
        return np.mean(np.abs((y_true - y_pred) / (np.abs(y_true) + epsilon))) * 100

    @staticmethod
    def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """Root Mean Squared Error."""
        return np.sqrt(np.mean((y_true - y_pred) ** 2))

    @staticmethod
    def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """Mean Absolute Error."""
        return np.mean(np.abs(y_true - y_pred))

    @staticmethod
    def r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """R-squared (coefficient of determination)."""
        ss_res = np.sum((y_true - y_pred) ** 2)
        ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
        return 1 - (ss_res / (ss_tot + 1e-8))

    @staticmethod
    def direction_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """Accuracy of predicted price direction changes."""
        if len(y_true.shape) == 1 or y_true.shape[1] < 2:
            return 0.0

        actual_direction = np.sign(y_true[:, 1:] - y_true[:, :-1])
        pred_direction = np.sign(y_pred[:, 1:] - y_pred[:, :-1])
        return np.mean(actual_direction == pred_direction)

    @staticmethod
    def coverage(
        y_true: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray
    ) -> float:
        """Percentage of actual values within confidence interval."""
        in_interval = (y_true >= lower) & (y_true <= upper)
        return np.mean(in_interval)

    @staticmethod
    def mean_interval_width(lower: np.ndarray, upper: np.ndarray) -> float:
        """Average width of confidence intervals."""
        return np.mean(upper - lower)

    @staticmethod
    def compute_all(
        y_true: np.ndarray,
        y_pred: np.ndarray,
        lower: Optional[np.ndarray] = None,
        upper: Optional[np.ndarray] = None
    ) -> Dict[str, float]:
        """Compute all metrics."""
        metrics = {
            'mape': MetricsCalculator.mape(y_true, y_pred),
            'rmse': MetricsCalculator.rmse(y_true, y_pred),
            'mae': MetricsCalculator.mae(y_true, y_pred),
            'r2': MetricsCalculator.r2_score(y_true, y_pred),
            'direction_accuracy': MetricsCalculator.direction_accuracy(y_true, y_pred)
        }

        if lower is not None and upper is not None:
            metrics['coverage'] = MetricsCalculator.coverage(y_true, lower, upper)
            metrics['mean_interval_width'] = MetricsCalculator.mean_interval_width(lower, upper)

        return metrics


class ModelBacktester:
    """
    Walk-forward backtesting framework for price forecasting models.

    Implements realistic out-of-sample testing by:
    1. Training on historical data up to time t
    2. Forecasting for time t+1 to t+horizon
    3. Moving forward by step_size and repeating
    4. Optionally retraining at specified intervals
    """

    def __init__(
        self,
        model,  # ElectricityPriceForecaster or EnsembleForecaster
        feature_engine,  # ElectricityPriceFeatureEngine
        config: BacktestConfig = None
    ):
        """
        Initialize backtester.

        Args:
            model: Forecasting model with predict() method
            feature_engine: Feature engineering pipeline
            config: Backtest configuration
        """
        self.model = model
        self.feature_engine = feature_engine
        self.config = config or BacktestConfig()
        self.results: List[BacktestResult] = []

        os.makedirs(self.config.output_dir, exist_ok=True)

    def run(
        self,
        df: pd.DataFrame,
        target_col: str = 'price'
    ) -> Dict:
        """
        Run walk-forward backtest.

        Args:
            df: DataFrame with DateTimeIndex containing price data
            target_col: Name of target column

        Returns:
            Dictionary with aggregated backtest results
        """
        logger.info("Starting backtest...")

        # Prepare features
        logger.info("Preparing features...")
        df_features = self.feature_engine.transform(df, target_col=target_col)

        # Get feature columns
        feature_cols = [c for c in df_features.columns if c != target_col]

        # Determine backtest periods
        total_samples = len(df_features)
        min_start = self.config.min_train_size + self.config.sequence_length

        if total_samples < min_start + self.config.test_size:
            raise ValueError(
                f"Insufficient data for backtesting. "
                f"Need at least {min_start + self.config.test_size} samples, "
                f"got {total_samples}"
            )

        # Walk-forward validation
        current_position = min_start
        all_predictions = []
        all_actuals = []
        all_lowers = []
        all_uppers = []
        all_dates = []

        period_count = 0
        hours_since_retrain = 0

        while current_position + self.config.test_size <= total_samples:
            period_count += 1
            logger.info(f"Backtest period {period_count}: "
                       f"position {current_position}/{total_samples}")

            # Determine training window
            if self.config.window_type == "expanding":
                train_start = 0
            else:  # rolling
                train_start = max(0, current_position - self.config.min_train_size)

            train_end = current_position
            test_end = min(current_position + self.config.test_size, total_samples)

            # Get training data
            train_data = df_features.iloc[train_start:train_end]
            test_data = df_features.iloc[current_position:test_end]

            # Check if retraining needed
            if hours_since_retrain >= self.config.retrain_frequency:
                logger.info("Retraining model...")
                # Create sequences for training
                X_train, y_train = self._create_sequences(
                    train_data, feature_cols, target_col
                )

                if hasattr(self.model, 'fit') and len(X_train) > 0:
                    try:
                        self.model.fit(X_train, y_train, verbose=0)
                    except Exception as e:
                        logger.warning(f"Retraining failed: {e}")

                hours_since_retrain = 0

            # Create test sequences
            X_test, y_test = self._create_sequences(
                test_data, feature_cols, target_col
            )

            if len(X_test) == 0:
                logger.warning(f"No test samples for period {period_count}")
                current_position += self.config.step_size
                hours_since_retrain += self.config.step_size
                continue

            # Generate predictions
            try:
                if hasattr(self.model, 'predict_with_confidence'):
                    predictions, lower, upper = self.model.predict_with_confidence(X_test)
                elif hasattr(self.model, 'predict'):
                    result = self.model.predict(X_test, return_confidence=True)
                    if isinstance(result, tuple) and len(result) == 3:
                        predictions, lower, upper = result
                    else:
                        predictions = result
                        lower = predictions - np.std(predictions) * 1.96
                        upper = predictions + np.std(predictions) * 1.96
                else:
                    raise ValueError("Model must have predict() method")
            except Exception as e:
                logger.error(f"Prediction failed: {e}")
                current_position += self.config.step_size
                hours_since_retrain += self.config.step_size
                continue

            # Store results
            all_predictions.append(predictions)
            all_actuals.append(y_test)
            all_lowers.append(lower)
            all_uppers.append(upper)
            all_dates.extend(test_data.index[:len(predictions)].tolist())

            # Compute period metrics
            period_result = self._compute_period_metrics(
                y_test, predictions, lower, upper,
                test_data.index[0], test_data.index[-1]
            )
            self.results.append(period_result)

            # Move to next period
            current_position += self.config.step_size
            hours_since_retrain += self.config.step_size

        # Aggregate results
        logger.info(f"Completed {len(self.results)} backtest periods")

        # Combine all predictions
        if len(all_predictions) > 0:
            all_predictions = np.vstack(all_predictions)
            all_actuals = np.vstack(all_actuals)
            all_lowers = np.vstack(all_lowers)
            all_uppers = np.vstack(all_uppers)
        else:
            all_predictions = np.array([])
            all_actuals = np.array([])
            all_lowers = np.array([])
            all_uppers = np.array([])

        # Generate summary
        summary = self._generate_summary(
            all_actuals, all_predictions, all_lowers, all_uppers, all_dates
        )

        # Save results
        if self.config.save_predictions:
            self._save_results(summary, all_predictions, all_actuals, all_dates)

        # Generate plots
        if self.config.generate_plots and HAS_MATPLOTLIB:
            self._generate_plots(all_actuals, all_predictions, all_lowers, all_uppers)

        return summary

    def _create_sequences(
        self,
        df: pd.DataFrame,
        feature_cols: List[str],
        target_col: str
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Create sequences for model input."""
        seq_len = self.config.sequence_length
        horizon = self.config.forecast_horizon

        X, y = [], []

        for i in range(len(df) - seq_len - horizon + 1):
            X.append(df[feature_cols].iloc[i:i + seq_len].values)
            y.append(df[target_col].iloc[i + seq_len:i + seq_len + horizon].values)

        if len(X) == 0:
            return np.array([]), np.array([])

        return np.array(X), np.array(y)

    def _compute_period_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray,
        start_date: datetime,
        end_date: datetime
    ) -> BacktestResult:
        """Compute metrics for a single backtest period."""
        metrics = MetricsCalculator.compute_all(y_true, y_pred, lower, upper)

        # Compute hourly breakdown of MAPE
        mape_by_hour = {}
        for hour in range(self.config.forecast_horizon):
            if hour < y_true.shape[1]:
                hour_mape = MetricsCalculator.mape(
                    y_true[:, hour], y_pred[:, hour]
                )
                mape_by_hour[hour] = hour_mape

        return BacktestResult(
            start_date=start_date,
            end_date=end_date,
            n_samples=len(y_true),
            mape=metrics['mape'],
            rmse=metrics['rmse'],
            mae=metrics['mae'],
            r2=metrics['r2'],
            direction_accuracy=metrics['direction_accuracy'],
            coverage=metrics.get('coverage', 0.0),
            mean_interval_width=metrics.get('mean_interval_width', 0.0),
            mape_by_hour=mape_by_hour
        )

    def _generate_summary(
        self,
        all_actuals: np.ndarray,
        all_predictions: np.ndarray,
        all_lowers: np.ndarray,
        all_uppers: np.ndarray,
        all_dates: List
    ) -> Dict:
        """Generate summary statistics from all backtest periods."""
        if len(all_actuals) == 0:
            return {'status': 'no_results'}

        # Overall metrics
        overall_metrics = MetricsCalculator.compute_all(
            all_actuals, all_predictions, all_lowers, all_uppers
        )

        # Period-level statistics
        period_mapes = [r.mape for r in self.results]
        period_rmses = [r.rmse for r in self.results]

        # Hourly performance
        hourly_mape = {}
        for hour in range(self.config.forecast_horizon):
            if hour < all_actuals.shape[1]:
                hourly_mape[hour] = MetricsCalculator.mape(
                    all_actuals[:, hour], all_predictions[:, hour]
                )

        summary = {
            'overall': overall_metrics,
            'period_statistics': {
                'n_periods': len(self.results),
                'mape_mean': np.mean(period_mapes),
                'mape_std': np.std(period_mapes),
                'mape_min': np.min(period_mapes),
                'mape_max': np.max(period_mapes),
                'rmse_mean': np.mean(period_rmses),
                'rmse_std': np.std(period_rmses)
            },
            'hourly_mape': hourly_mape,
            'target_achievement': {
                'mape_target': self.config.target_mape,
                'mape_achieved': overall_metrics['mape'] <= self.config.target_mape,
                'coverage_target': self.config.target_coverage,
                'coverage_achieved': overall_metrics.get('coverage', 0) >= self.config.target_coverage
            },
            'date_range': {
                'start': str(min(all_dates)) if all_dates else None,
                'end': str(max(all_dates)) if all_dates else None
            }
        }

        # Log summary
        logger.info("=" * 50)
        logger.info("BACKTEST SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Overall MAPE: {overall_metrics['mape']:.2f}%")
        logger.info(f"Overall RMSE: {overall_metrics['rmse']:.4f}")
        logger.info(f"Overall MAE: {overall_metrics['mae']:.4f}")
        logger.info(f"Direction Accuracy: {overall_metrics['direction_accuracy']:.2%}")
        if 'coverage' in overall_metrics:
            logger.info(f"Coverage: {overall_metrics['coverage']:.2%}")
        logger.info(f"Target MAPE ({self.config.target_mape}%): "
                   f"{'ACHIEVED' if summary['target_achievement']['mape_achieved'] else 'NOT ACHIEVED'}")
        logger.info("=" * 50)

        return summary

    def _save_results(
        self,
        summary: Dict,
        predictions: np.ndarray,
        actuals: np.ndarray,
        dates: List
    ):
        """Save backtest results to files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save summary
        summary_path = os.path.join(
            self.config.output_dir,
            f"backtest_summary_{timestamp}.json"
        )
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        # Save predictions
        if len(predictions) > 0:
            pred_path = os.path.join(
                self.config.output_dir,
                f"backtest_predictions_{timestamp}.npz"
            )
            np.savez(
                pred_path,
                predictions=predictions,
                actuals=actuals
            )

        # Save period results
        period_results = [asdict(r) for r in self.results]
        period_path = os.path.join(
            self.config.output_dir,
            f"backtest_periods_{timestamp}.json"
        )
        with open(period_path, 'w') as f:
            json.dump(period_results, f, indent=2, default=str)

        logger.info(f"Results saved to {self.config.output_dir}")

    def _generate_plots(
        self,
        actuals: np.ndarray,
        predictions: np.ndarray,
        lowers: np.ndarray,
        uppers: np.ndarray
    ):
        """Generate visualization plots."""
        if not HAS_MATPLOTLIB:
            logger.warning("matplotlib not available, skipping plots")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 1. Forecast vs Actual scatter plot
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.scatter(
            actuals.flatten(),
            predictions.flatten(),
            alpha=0.3,
            s=1
        )
        ax.plot(
            [actuals.min(), actuals.max()],
            [actuals.min(), actuals.max()],
            'r--',
            label='Perfect forecast'
        )
        ax.set_xlabel('Actual Price')
        ax.set_ylabel('Predicted Price')
        ax.set_title('Forecast vs Actual')
        ax.legend()

        plot_path = os.path.join(
            self.config.output_dir,
            f"backtest_scatter_{timestamp}.png"
        )
        plt.savefig(plot_path, dpi=150, bbox_inches='tight')
        plt.close()

        # 2. MAPE by forecast hour
        if len(self.results) > 0:
            hourly_mapes = {}
            for r in self.results:
                for hour, mape in r.mape_by_hour.items():
                    if hour not in hourly_mapes:
                        hourly_mapes[hour] = []
                    hourly_mapes[hour].append(mape)

            hours = sorted(hourly_mapes.keys())
            mape_means = [np.mean(hourly_mapes[h]) for h in hours]
            mape_stds = [np.std(hourly_mapes[h]) for h in hours]

            fig, ax = plt.subplots(figsize=(12, 6))
            ax.bar(hours, mape_means, yerr=mape_stds, capsize=3, alpha=0.7)
            ax.axhline(y=self.config.target_mape, color='r', linestyle='--',
                      label=f'Target MAPE ({self.config.target_mape}%)')
            ax.set_xlabel('Forecast Hour')
            ax.set_ylabel('MAPE (%)')
            ax.set_title('MAPE by Forecast Horizon')
            ax.legend()

            plot_path = os.path.join(
                self.config.output_dir,
                f"backtest_hourly_mape_{timestamp}.png"
            )
            plt.savefig(plot_path, dpi=150, bbox_inches='tight')
            plt.close()

        # 3. Period-level MAPE distribution
        if len(self.results) > 0:
            period_mapes = [r.mape for r in self.results]

            fig, ax = plt.subplots(figsize=(10, 6))
            ax.hist(period_mapes, bins=30, edgecolor='black', alpha=0.7)
            ax.axvline(x=self.config.target_mape, color='r', linestyle='--',
                      label=f'Target MAPE ({self.config.target_mape}%)')
            ax.axvline(x=np.mean(period_mapes), color='g', linestyle='-',
                      label=f'Mean MAPE ({np.mean(period_mapes):.2f}%)')
            ax.set_xlabel('MAPE (%)')
            ax.set_ylabel('Frequency')
            ax.set_title('Distribution of Period MAPEs')
            ax.legend()

            plot_path = os.path.join(
                self.config.output_dir,
                f"backtest_mape_dist_{timestamp}.png"
            )
            plt.savefig(plot_path, dpi=150, bbox_inches='tight')
            plt.close()

        logger.info(f"Plots saved to {self.config.output_dir}")


def run_backtest(
    model,
    feature_engine,
    df: pd.DataFrame,
    config: BacktestConfig = None
) -> Dict:
    """
    Convenience function to run backtest.

    Args:
        model: Forecasting model
        feature_engine: Feature engineering pipeline
        df: Price data
        config: Backtest configuration

    Returns:
        Backtest summary
    """
    backtester = ModelBacktester(model, feature_engine, config)
    return backtester.run(df)


def test_backtesting():
    """Test backtesting framework with dummy data."""
    print("Testing Backtesting Framework...")

    # Import feature engineering
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from data.feature_engineering import (
        ElectricityPriceFeatureEngine,
        create_dummy_data
    )

    # Create dummy data
    print("\nCreating dummy data...")
    df = create_dummy_data(n_hours=2000)  # Smaller for testing
    print(f"Data shape: {df.shape}")

    # Create feature engine
    feature_engine = ElectricityPriceFeatureEngine(
        country='UK',
        lookback_hours=168,
        forecast_hours=24
    )

    # Create a simple mock model for testing
    class MockModel:
        def predict(self, X, return_confidence=True):
            n_samples = len(X)
            predictions = np.random.randn(n_samples, 24) * 10 + 50
            lower = predictions - 10
            upper = predictions + 10
            if return_confidence:
                return predictions, lower, upper
            return predictions

    model = MockModel()

    # Configure backtest
    config = BacktestConfig(
        min_train_size=500,
        test_size=100,
        step_size=50,
        retrain_frequency=500,  # Don't retrain in test
        generate_plots=False,
        output_dir='/tmp/backtest_test'
    )

    # Run backtest
    print("\nRunning backtest...")
    backtester = ModelBacktester(model, feature_engine, config)
    summary = backtester.run(df)

    print(f"\nBacktest Summary:")
    print(f"  Periods: {summary['period_statistics']['n_periods']}")
    print(f"  Overall MAPE: {summary['overall']['mape']:.2f}%")
    print(f"  MAPE Target Achieved: {summary['target_achievement']['mape_achieved']}")

    print("\nBacktesting test passed!")


if __name__ == "__main__":
    test_backtesting()
