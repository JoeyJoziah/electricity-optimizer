#!/usr/bin/env python3
"""
Test Script for Electricity Price Forecasting Models

This script tests the complete ML pipeline including:
1. Feature engineering on dummy data
2. CNN-LSTM model training
3. Ensemble model training
4. Prediction and evaluation
5. Model save/load

Requirements:
    pip install -r requirements-ml.txt

Usage:
    python test_forecaster.py
    python test_forecaster.py --quick  # Fast test with minimal epochs
    python test_forecaster.py --full   # Full training test
"""

import os
import sys
import argparse
import time
import logging
from pathlib import Path
import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_feature_engineering():
    """Test feature engineering pipeline."""
    print("\n" + "=" * 60)
    print("TEST 1: Feature Engineering")
    print("=" * 60)

    from ml.data.feature_engineering import (
        ElectricityPriceFeatureEngine,
        create_dummy_data
    )

    # Create dummy data
    print("\n1.1 Creating dummy data...")
    df = create_dummy_data(n_hours=2000)
    print(f"    Data shape: {df.shape}")
    print(f"    Date range: {df.index.min()} to {df.index.max()}")
    print(f"    Columns: {list(df.columns)[:5]}...")

    # Initialize feature engine
    print("\n1.2 Initializing feature engine...")
    feature_engine = ElectricityPriceFeatureEngine(
        country='UK',
        lookback_hours=168,
        forecast_hours=24
    )

    # Fit and transform
    print("\n1.3 Fitting and transforming features...")
    feature_engine.fit(df)
    df_features = feature_engine.transform(df)
    print(f"    Features shape: {df_features.shape}")
    print(f"    Feature columns: {len(df_features.columns)}")

    # Create sequences
    print("\n1.4 Creating sequences...")
    X, y = feature_engine.create_sequences(df_features)
    print(f"    X shape: {X.shape}")
    print(f"    y shape: {y.shape}")

    # Verify no NaN
    nan_x = np.isnan(X).sum()
    nan_y = np.isnan(y).sum()
    print(f"    NaN in X: {nan_x}")
    print(f"    NaN in y: {nan_y}")

    assert nan_x == 0, "NaN values found in features"
    assert nan_y == 0, "NaN values found in targets"

    print("\n    [PASSED] Feature Engineering Test")
    return X, y, feature_engine


def test_cnn_lstm_model(X, y, epochs=5):
    """Test CNN-LSTM model."""
    print("\n" + "=" * 60)
    print("TEST 2: CNN-LSTM Model")
    print("=" * 60)

    try:
        import tensorflow as tf
        print(f"    TensorFlow version: {tf.__version__}")
    except ImportError:
        print("    [SKIPPED] TensorFlow not installed")
        return None

    from ml.models.price_forecaster import (
        ElectricityPriceForecaster,
        ModelConfig
    )

    # Split data
    train_size = int(0.8 * len(X))
    X_train, X_test = X[:train_size], X[train_size:]
    y_train, y_test = y[:train_size], y[train_size:]

    print(f"\n2.1 Data split:")
    print(f"    Train: {len(X_train)}, Test: {len(X_test)}")

    # Create model
    print("\n2.2 Creating CNN-LSTM model...")
    config = ModelConfig(
        sequence_length=X.shape[1],
        num_features=X.shape[2],
        forecast_horizon=y.shape[1],
        cnn_filters=[32, 64, 32],
        lstm_units=[64, 32],
        dense_units=[32, 16],
        epochs=epochs,
        batch_size=32
    )

    model = ElectricityPriceForecaster(config=config)
    print(f"    Model parameters: {model.model.count_params():,}")

    # Train
    print(f"\n2.3 Training model for {epochs} epochs...")
    start_time = time.time()
    history = model.fit(
        X_train, y_train,
        checkpoint_dir='/tmp/ml_test/checkpoints',
        log_dir='/tmp/ml_test/logs',
        verbose=0
    )
    train_time = time.time() - start_time
    print(f"    Training time: {train_time:.2f}s")

    # Predict
    print("\n2.4 Generating predictions...")
    start_time = time.time()
    forecast, lower, upper = model.predict(X_test[:10], return_confidence=True)
    pred_time = (time.time() - start_time) * 1000 / 10  # ms per sample
    print(f"    Prediction shape: {forecast.shape}")
    print(f"    Inference time: {pred_time:.2f}ms per sample")

    # Evaluate
    print("\n2.5 Evaluating model...")
    metrics = model.evaluate(X_test, y_test)
    print(f"    MAPE: {metrics['mape']:.2f}%")
    print(f"    RMSE: {metrics['rmse']:.4f}")
    print(f"    MAE: {metrics['mae']:.4f}")
    print(f"    Direction Accuracy: {metrics['direction_accuracy']:.2%}")
    print(f"    Coverage: {metrics['coverage']:.2%}")

    # Save and load
    print("\n2.6 Testing save/load...")
    model.save('/tmp/ml_test/cnn_lstm')

    loaded_model = ElectricityPriceForecaster(model_path='/tmp/ml_test/cnn_lstm')
    loaded_metrics = loaded_model.evaluate(X_test, y_test)
    print(f"    Loaded model MAPE: {loaded_metrics['mape']:.2f}%")

    # Verify metrics match
    assert abs(metrics['mape'] - loaded_metrics['mape']) < 0.01, "Metrics mismatch after load"

    print("\n    [PASSED] CNN-LSTM Model Test")
    return model


def test_gradient_boosting(X, y):
    """Test gradient boosting models."""
    print("\n" + "=" * 60)
    print("TEST 3: Gradient Boosting Models")
    print("=" * 60)

    # Split data
    train_size = int(0.8 * len(X))
    X_train, X_test = X[:train_size], X[train_size:]
    y_train, y_test = y[:train_size], y[train_size:]

    # Test XGBoost
    try:
        import xgboost
        print(f"\n3.1 Testing XGBoost...")
        print(f"    XGBoost version: {xgboost.__version__}")

        from ml.models.ensemble import XGBoostForecaster, XGBoostConfig

        xgb_model = XGBoostForecaster(
            config=XGBoostConfig(n_estimators=50),
            forecast_horizon=y.shape[1]
        )

        start_time = time.time()
        xgb_model.fit(X_train, y_train)
        train_time = time.time() - start_time
        print(f"    Training time: {train_time:.2f}s")

        xgb_pred = xgb_model.predict(X_test)
        xgb_mape = np.mean(np.abs((y_test - xgb_pred) / (y_test + 1e-8))) * 100
        print(f"    MAPE: {xgb_mape:.2f}%")

        print("    [PASSED] XGBoost Test")

    except ImportError:
        print("    [SKIPPED] XGBoost not installed")

    # Test LightGBM
    try:
        import lightgbm
        print(f"\n3.2 Testing LightGBM...")
        print(f"    LightGBM version: {lightgbm.__version__}")

        from ml.models.ensemble import LightGBMForecaster, LightGBMConfig

        lgb_model = LightGBMForecaster(
            config=LightGBMConfig(n_estimators=50),
            forecast_horizon=y.shape[1]
        )

        start_time = time.time()
        lgb_model.fit(X_train, y_train)
        train_time = time.time() - start_time
        print(f"    Training time: {train_time:.2f}s")

        lgb_pred = lgb_model.predict(X_test)
        lgb_mape = np.mean(np.abs((y_test - lgb_pred) / (y_test + 1e-8))) * 100
        print(f"    MAPE: {lgb_mape:.2f}%")

        print("    [PASSED] LightGBM Test")

    except ImportError:
        print("    [SKIPPED] LightGBM not installed")


def test_ensemble(X, y, cnn_lstm_model=None, epochs=5):
    """Test ensemble model."""
    print("\n" + "=" * 60)
    print("TEST 4: Ensemble Model")
    print("=" * 60)

    try:
        import tensorflow as tf
    except ImportError:
        print("    [SKIPPED] TensorFlow not installed")
        return

    from ml.models.ensemble import EnsembleForecaster, EnsembleConfig

    # Split data
    train_size = int(0.8 * len(X))
    X_train, X_test = X[:train_size], X[train_size:]
    y_train, y_test = y[:train_size], y[train_size:]

    # Create ensemble
    print("\n4.1 Creating ensemble model...")

    try:
        import xgboost
        import lightgbm
        has_gbm = True
    except ImportError:
        has_gbm = False

    if has_gbm and cnn_lstm_model is not None:
        config = EnsembleConfig(
            cnn_lstm_weight=0.5,
            xgboost_weight=0.25,
            lightgbm_weight=0.25,
            forecast_horizon=y.shape[1]
        )
        ensemble = EnsembleForecaster(config=config, cnn_lstm_model=cnn_lstm_model)
    elif has_gbm:
        config = EnsembleConfig(
            cnn_lstm_weight=0.0,
            xgboost_weight=0.5,
            lightgbm_weight=0.5,
            forecast_horizon=y.shape[1]
        )
        ensemble = EnsembleForecaster(config=config)
    else:
        print("    [SKIPPED] No GBM models available for ensemble")
        return

    # Train
    print("\n4.2 Training ensemble...")
    start_time = time.time()
    ensemble.fit(
        X_train, y_train,
        X_val=X_test[:100],
        y_val=y_test[:100],
        fit_cnn_lstm=(cnn_lstm_model is None)
    )
    train_time = time.time() - start_time
    print(f"    Training time: {train_time:.2f}s")

    # Evaluate
    print("\n4.3 Evaluating ensemble...")
    results = ensemble.evaluate(X_test, y_test)

    print(f"    Ensemble MAPE: {results['ensemble']['mape']:.2f}%")
    for model_name, metrics in results.items():
        if model_name != 'ensemble':
            print(f"    {model_name} MAPE: {metrics['mape']:.2f}%")

    # Predict with confidence
    print("\n4.4 Testing confidence intervals...")
    forecast, lower, upper = ensemble.predict_with_confidence(X_test[:5])
    print(f"    Forecast shape: {forecast.shape}")
    print(f"    Interval width (mean): {np.mean(upper - lower):.4f}")

    print("\n    [PASSED] Ensemble Model Test")


def test_backtesting(feature_engine, epochs=2):
    """Test backtesting framework."""
    print("\n" + "=" * 60)
    print("TEST 5: Backtesting Framework")
    print("=" * 60)

    try:
        import tensorflow as tf
    except ImportError:
        print("    [SKIPPED] TensorFlow not installed")
        return

    from ml.data.feature_engineering import create_dummy_data
    from ml.evaluation.backtesting import (
        ModelBacktester,
        BacktestConfig
    )

    # Create mock model for testing
    class MockModel:
        def predict(self, X, return_confidence=True):
            n_samples = len(X)
            predictions = np.random.randn(n_samples, 24) * 10 + 50
            lower = predictions - 10
            upper = predictions + 10
            if return_confidence:
                return predictions, lower, upper
            return predictions

    # Create data
    print("\n5.1 Creating test data...")
    df = create_dummy_data(n_hours=1500)

    # Configure backtest
    config = BacktestConfig(
        min_train_size=500,
        test_size=100,
        step_size=50,
        retrain_frequency=1000,  # Don't retrain in test
        generate_plots=False,
        save_predictions=True,
        output_dir='/tmp/ml_test/backtest'
    )

    # Run backtest
    print("\n5.2 Running backtest...")
    model = MockModel()
    backtester = ModelBacktester(model, feature_engine, config)

    start_time = time.time()
    summary = backtester.run(df)
    backtest_time = time.time() - start_time

    print(f"    Backtest time: {backtest_time:.2f}s")
    print(f"    Periods evaluated: {summary['period_statistics']['n_periods']}")
    print(f"    Overall MAPE: {summary['overall']['mape']:.2f}%")
    print(f"    MAPE std: {summary['period_statistics']['mape_std']:.2f}%")

    print("\n    [PASSED] Backtesting Test")


def run_all_tests(quick=True):
    """Run all tests."""
    print("\n" + "=" * 70)
    print("ELECTRICITY PRICE FORECASTING - COMPREHENSIVE TEST SUITE")
    print("=" * 70)

    epochs = 3 if quick else 20

    # Test 1: Feature Engineering
    X, y, feature_engine = test_feature_engineering()

    # Test 2: CNN-LSTM
    cnn_lstm_model = test_cnn_lstm_model(X, y, epochs=epochs)

    # Test 3: Gradient Boosting
    test_gradient_boosting(X, y)

    # Test 4: Ensemble
    test_ensemble(X, y, cnn_lstm_model, epochs=epochs)

    # Test 5: Backtesting
    test_backtesting(feature_engine, epochs=epochs)

    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETED SUCCESSFULLY")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='Test ML forecasting models')
    parser.add_argument('--quick', action='store_true', help='Quick test with minimal epochs')
    parser.add_argument('--full', action='store_true', help='Full test with more epochs')
    args = parser.parse_args()

    quick = not args.full
    run_all_tests(quick=quick)


if __name__ == "__main__":
    main()
