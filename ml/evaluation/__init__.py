"""
Evaluation and backtesting utilities for electricity price forecasting.
"""

from .backtesting import (
    BacktestConfig,
    BacktestResult,
    ModelBacktester,
    run_backtest,
)

from .metrics import (
    ForecastMetrics,
    calculate_all_metrics,
    evaluate_forecast,
    compare_models,
    mean_absolute_error,
    root_mean_squared_error,
    mean_absolute_percentage_error,
    symmetric_mean_absolute_percentage_error,
    r2_score,
    direction_accuracy,
    weighted_direction_accuracy,
)

__all__ = [
    'BacktestConfig',
    'BacktestResult',
    'ModelBacktester',
    'run_backtest',
    'ForecastMetrics',
    'calculate_all_metrics',
    'evaluate_forecast',
    'compare_models',
    'mean_absolute_error',
    'root_mean_squared_error',
    'mean_absolute_percentage_error',
    'symmetric_mean_absolute_percentage_error',
    'r2_score',
    'direction_accuracy',
    'weighted_direction_accuracy',
]
