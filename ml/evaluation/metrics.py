"""
Performance Metrics for Price Forecasting Models

Provides comprehensive evaluation metrics for time series forecasting:
- Point forecast metrics: MAE, RMSE, MAPE, sMAPE
- Probabilistic metrics: Coverage, Interval Score
- Directional metrics: Direction Accuracy, Weighted Direction Accuracy
- Business metrics: Cost of Prediction Error, Savings Impact
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class ForecastMetrics:
    """Container for forecast evaluation metrics"""

    # Point forecast metrics
    mae: float  # Mean Absolute Error
    rmse: float  # Root Mean Squared Error
    mape: float  # Mean Absolute Percentage Error (%)
    smape: float  # Symmetric MAPE (%)
    mse: float  # Mean Squared Error
    r2_score: float  # R² Score

    # Directional metrics
    direction_accuracy: float  # Accuracy of predicting price direction (%)
    weighted_direction_accuracy: float  # Weighted by magnitude (%)

    # Probabilistic metrics (if confidence intervals available)
    coverage_90: Optional[float] = None  # Coverage of 90% prediction intervals
    coverage_95: Optional[float] = None  # Coverage of 95% prediction intervals
    interval_score_90: Optional[float] = None  # Interval score for 90% intervals
    interval_score_95: Optional[float] = None  # Interval score for 95% intervals

    # Business metrics
    cost_of_error: Optional[float] = None  # Financial cost of prediction errors
    optimization_savings_impact: Optional[float] = None  # Impact on savings (%)

    # Sample statistics
    n_samples: int = 0
    forecast_horizon: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    def __str__(self) -> str:
        """Pretty print metrics"""
        lines = [
            "=" * 60,
            "FORECAST PERFORMANCE METRICS",
            "=" * 60,
            "",
            "Point Forecast Metrics:",
            f"  MAE:   {self.mae:.4f}",
            f"  RMSE:  {self.rmse:.4f}",
            f"  MAPE:  {self.mape:.2f}%",
            f"  sMAPE: {self.smape:.2f}%",
            f"  R²:    {self.r2_score:.4f}",
            "",
            "Directional Metrics:",
            f"  Direction Accuracy:          {self.direction_accuracy:.2f}%",
            f"  Weighted Direction Accuracy: {self.weighted_direction_accuracy:.2f}%",
        ]

        if self.coverage_90 is not None:
            lines.extend([
                "",
                "Probabilistic Metrics:",
                f"  90% Interval Coverage: {self.coverage_90:.2f}%",
                f"  95% Interval Coverage: {self.coverage_95:.2f}%",
                f"  90% Interval Score:    {self.interval_score_90:.4f}",
                f"  95% Interval Score:    {self.interval_score_95:.4f}",
            ])

        if self.cost_of_error is not None:
            lines.extend([
                "",
                "Business Metrics:",
                f"  Cost of Error:           £{self.cost_of_error:.2f}",
                f"  Savings Impact:          {self.optimization_savings_impact:.2f}%",
            ])

        lines.extend([
            "",
            f"Sample Size: {self.n_samples}",
            f"Forecast Horizon: {self.forecast_horizon}h",
            "=" * 60
        ])

        return "\n".join(lines)


def mean_absolute_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Mean Absolute Error (MAE)

    MAE = (1/n) * Σ|y_true - y_pred|
    """
    return np.mean(np.abs(y_true - y_pred))


def root_mean_squared_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Root Mean Squared Error (RMSE)

    RMSE = sqrt((1/n) * Σ(y_true - y_pred)²)
    """
    return np.sqrt(np.mean((y_true - y_pred) ** 2))


def mean_absolute_percentage_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Mean Absolute Percentage Error (MAPE) in percentage

    MAPE = (100/n) * Σ|y_true - y_pred| / |y_true|

    Note: Sensitive to zero values in y_true
    """
    # Avoid division by zero
    mask = y_true != 0
    if not np.any(mask):
        return np.inf

    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100


def symmetric_mean_absolute_percentage_error(
    y_true: np.ndarray,
    y_pred: np.ndarray
) -> float:
    """
    Symmetric MAPE (sMAPE) in percentage

    sMAPE = (100/n) * Σ(2 * |y_true - y_pred|) / (|y_true| + |y_pred|)

    More robust than MAPE when y_true is close to zero
    """
    numerator = np.abs(y_true - y_pred)
    denominator = (np.abs(y_true) + np.abs(y_pred)) / 2

    # Avoid division by zero
    mask = denominator != 0
    if not np.any(mask):
        return 0.0

    return np.mean(numerator[mask] / denominator[mask]) * 100


def r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    R² (Coefficient of Determination)

    R² = 1 - (SS_res / SS_tot)
    where SS_res = Σ(y_true - y_pred)²
          SS_tot = Σ(y_true - mean(y_true))²
    """
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)

    if ss_tot == 0:
        return 0.0

    return 1 - (ss_res / ss_tot)


def direction_accuracy(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    threshold: float = 0.0
) -> float:
    """
    Direction Accuracy - Percentage of correct directional predictions

    Measures how often the model correctly predicts whether the price
    will go up or down compared to previous value.

    Args:
        y_true: Actual values
        y_pred: Predicted values
        threshold: Minimum change to consider (ignore small fluctuations)

    Returns:
        Accuracy percentage (0-100)
    """
    if len(y_true) < 2:
        return 0.0

    # Calculate changes
    true_changes = np.diff(y_true)
    pred_changes = np.diff(y_pred)

    # Apply threshold
    mask = np.abs(true_changes) > threshold

    if not np.any(mask):
        return 0.0

    # Check if directions match
    correct = np.sign(true_changes[mask]) == np.sign(pred_changes[mask])

    return np.mean(correct) * 100


def weighted_direction_accuracy(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    threshold: float = 0.0
) -> float:
    """
    Weighted Direction Accuracy

    Similar to direction accuracy but weights by magnitude of change.
    Larger price movements are more important to predict correctly.

    Returns:
        Weighted accuracy percentage (0-100)
    """
    if len(y_true) < 2:
        return 0.0

    # Calculate changes
    true_changes = np.diff(y_true)
    pred_changes = np.diff(y_pred)

    # Apply threshold
    mask = np.abs(true_changes) > threshold

    if not np.any(mask):
        return 0.0

    # Check if directions match
    correct = (np.sign(true_changes[mask]) == np.sign(pred_changes[mask])).astype(float)

    # Weight by magnitude of true change
    weights = np.abs(true_changes[mask])
    weights = weights / np.sum(weights)  # Normalize

    return np.sum(correct * weights) * 100


def prediction_interval_coverage(
    y_true: np.ndarray,
    y_lower: np.ndarray,
    y_upper: np.ndarray
) -> float:
    """
    Prediction Interval Coverage

    Percentage of actual values that fall within prediction intervals

    Args:
        y_true: Actual values
        y_lower: Lower bound of prediction interval
        y_upper: Upper bound of prediction interval

    Returns:
        Coverage percentage (0-100)
    """
    within_interval = (y_true >= y_lower) & (y_true <= y_upper)
    return np.mean(within_interval) * 100


def interval_score(
    y_true: np.ndarray,
    y_lower: np.ndarray,
    y_upper: np.ndarray,
    alpha: float = 0.1
) -> float:
    """
    Interval Score (Gneiting & Raftery, 2007)

    Proper scoring rule for probabilistic forecasts with prediction intervals.
    Lower is better.

    IS = (upper - lower) + (2/alpha) * (lower - y) * I(y < lower)
                         + (2/alpha) * (y - upper) * I(y > upper)

    Args:
        y_true: Actual values
        y_lower: Lower bound of prediction interval
        y_upper: Upper bound of prediction interval
        alpha: Miscoverage rate (e.g., 0.1 for 90% interval)

    Returns:
        Average interval score
    """
    width = y_upper - y_lower

    below_penalty = (2 / alpha) * np.maximum(0, y_lower - y_true)
    above_penalty = (2 / alpha) * np.maximum(0, y_true - y_upper)

    scores = width + below_penalty + above_penalty

    return np.mean(scores)


def cost_of_prediction_error(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    consumption_kwh: float = 10.0,
    cost_multiplier: float = 1.0
) -> float:
    """
    Calculate financial cost of prediction errors

    Estimates the additional cost incurred due to imperfect forecasts
    in the context of load optimization.

    Args:
        y_true: Actual prices
        y_pred: Predicted prices
        consumption_kwh: Assumed consumption per hour (kWh)
        cost_multiplier: Multiplier for cost calculation

    Returns:
        Total cost in currency units (e.g., GBP, USD)
    """
    # Cost if using predictions
    predicted_cost = np.sum(y_pred * consumption_kwh)

    # Actual cost
    actual_cost = np.sum(y_true * consumption_kwh)

    # Additional cost due to errors
    additional_cost = np.abs(predicted_cost - actual_cost) * cost_multiplier

    return additional_cost


def optimization_savings_impact(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    consumption_kwh: float = 10.0
) -> float:
    """
    Estimate impact of forecast errors on optimization savings

    Measures how much the savings would be reduced due to using
    predictions instead of perfect foresight.

    Args:
        y_true: Actual prices
        y_pred: Predicted prices
        consumption_kwh: Assumed consumption per hour

    Returns:
        Percentage reduction in savings (0-100)
    """
    # Optimal cost with perfect foresight (use cheapest hours)
    optimal_cost = np.sum(np.sort(y_true)[:len(y_true) // 2]) * consumption_kwh

    # Cost using predictions (use hours predicted to be cheap)
    predicted_cheap_indices = np.argsort(y_pred)[:len(y_pred) // 2]
    predicted_cost = np.sum(y_true[predicted_cheap_indices]) * consumption_kwh

    # Baseline cost (use all hours equally)
    baseline_cost = np.mean(y_true) * consumption_kwh * len(y_true)

    # Savings with perfect foresight
    perfect_savings = baseline_cost - optimal_cost

    # Savings with predictions
    actual_savings = baseline_cost - predicted_cost

    if perfect_savings == 0:
        return 0.0

    # Impact on savings (positive = reduced savings)
    impact = ((perfect_savings - actual_savings) / perfect_savings) * 100

    return max(0.0, impact)


def calculate_all_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_lower: Optional[np.ndarray] = None,
    y_upper: Optional[np.ndarray] = None,
    consumption_kwh: float = 10.0,
    forecast_horizon: int = 24
) -> ForecastMetrics:
    """
    Calculate comprehensive forecast metrics

    Args:
        y_true: Actual values
        y_pred: Predicted values
        y_lower: Lower bound of 95% prediction interval (optional)
        y_upper: Upper bound of 95% prediction interval (optional)
        consumption_kwh: Consumption for cost calculations
        forecast_horizon: Forecast horizon in hours

    Returns:
        ForecastMetrics object with all computed metrics
    """
    # Point forecast metrics
    mae = mean_absolute_error(y_true, y_pred)
    rmse = root_mean_squared_error(y_true, y_pred)
    mape = mean_absolute_percentage_error(y_true, y_pred)
    smape = symmetric_mean_absolute_percentage_error(y_true, y_pred)
    mse = np.mean((y_true - y_pred) ** 2)
    r2 = r2_score(y_true, y_pred)

    # Directional metrics
    dir_acc = direction_accuracy(y_true, y_pred)
    weighted_dir_acc = weighted_direction_accuracy(y_true, y_pred)

    # Probabilistic metrics (if intervals provided)
    coverage_90 = None
    coverage_95 = None
    interval_score_90 = None
    interval_score_95 = None

    if y_lower is not None and y_upper is not None:
        # Assume provided intervals are 95%
        coverage_95 = prediction_interval_coverage(y_true, y_lower, y_upper)
        interval_score_95 = interval_score(y_true, y_lower, y_upper, alpha=0.05)

        # Approximate 90% intervals by shrinking 95% intervals
        interval_width = y_upper - y_lower
        y_lower_90 = y_pred - (interval_width * 0.9 / 2)
        y_upper_90 = y_pred + (interval_width * 0.9 / 2)

        coverage_90 = prediction_interval_coverage(y_true, y_lower_90, y_upper_90)
        interval_score_90 = interval_score(y_true, y_lower_90, y_upper_90, alpha=0.10)

    # Business metrics
    cost_error = cost_of_prediction_error(y_true, y_pred, consumption_kwh)
    savings_impact = optimization_savings_impact(y_true, y_pred, consumption_kwh)

    return ForecastMetrics(
        mae=mae,
        rmse=rmse,
        mape=mape,
        smape=smape,
        mse=mse,
        r2_score=r2,
        direction_accuracy=dir_acc,
        weighted_direction_accuracy=weighted_dir_acc,
        coverage_90=coverage_90,
        coverage_95=coverage_95,
        interval_score_90=interval_score_90,
        interval_score_95=interval_score_95,
        cost_of_error=cost_error,
        optimization_savings_impact=savings_impact,
        n_samples=len(y_true),
        forecast_horizon=forecast_horizon
    )


def evaluate_forecast(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_lower: Optional[np.ndarray] = None,
    y_upper: Optional[np.ndarray] = None,
    verbose: bool = True
) -> ForecastMetrics:
    """
    Evaluate forecast and optionally print results

    Args:
        y_true: Actual values
        y_pred: Predicted values
        y_lower: Lower prediction interval bounds
        y_upper: Upper prediction interval bounds
        verbose: If True, print metrics

    Returns:
        ForecastMetrics object
    """
    metrics = calculate_all_metrics(
        y_true=y_true,
        y_pred=y_pred,
        y_lower=y_lower,
        y_upper=y_upper
    )

    if verbose:
        print(metrics)

    return metrics


def compare_models(
    y_true: np.ndarray,
    predictions: Dict[str, np.ndarray],
    metric: str = 'mape'
) -> pd.DataFrame:
    """
    Compare multiple models on various metrics

    Args:
        y_true: Actual values
        predictions: Dict mapping model names to predictions
        metric: Primary metric for ranking ('mae', 'rmse', 'mape', etc.)

    Returns:
        DataFrame with metrics for each model, sorted by primary metric
    """
    results = []

    for model_name, y_pred in predictions.items():
        metrics = calculate_all_metrics(y_true, y_pred)

        results.append({
            'model': model_name,
            'mae': metrics.mae,
            'rmse': metrics.rmse,
            'mape': metrics.mape,
            'smape': metrics.smape,
            'r2': metrics.r2_score,
            'dir_acc': metrics.direction_accuracy,
            'weighted_dir_acc': metrics.weighted_direction_accuracy
        })

    df = pd.DataFrame(results)

    # Sort by primary metric (lower is better for most metrics)
    if metric in ['r2', 'dir_acc', 'weighted_dir_acc']:
        df = df.sort_values(metric, ascending=False)
    else:
        df = df.sort_values(metric, ascending=True)

    return df


if __name__ == '__main__':
    # Example usage
    np.random.seed(42)

    # Simulate actual prices (24 hours)
    y_true = np.array([0.20, 0.18, 0.16, 0.15, 0.14, 0.13, 0.12, 0.11,
                       0.15, 0.20, 0.25, 0.30, 0.32, 0.35, 0.38, 0.40,
                       0.39, 0.37, 0.35, 0.33, 0.30, 0.27, 0.24, 0.22])

    # Simulate predictions (with some error)
    y_pred = y_true + np.random.normal(0, 0.02, len(y_true))

    # Simulate prediction intervals
    y_lower = y_pred - 0.03
    y_upper = y_pred + 0.03

    # Evaluate
    print("\n" + "=" * 60)
    print("EXAMPLE: Price Forecast Evaluation")
    print("=" * 60 + "\n")

    metrics = evaluate_forecast(
        y_true=y_true,
        y_pred=y_pred,
        y_lower=y_lower,
        y_upper=y_upper,
        verbose=True
    )

    # Compare multiple models
    print("\n" + "=" * 60)
    print("MODEL COMPARISON")
    print("=" * 60 + "\n")

    predictions = {
        'CNN-LSTM': y_pred,
        'XGBoost': y_true + np.random.normal(0, 0.03, len(y_true)),
        'ARIMA': y_true + np.random.normal(0, 0.04, len(y_true))
    }

    comparison = compare_models(y_true, predictions, metric='mape')
    print(comparison.to_string(index=False))
