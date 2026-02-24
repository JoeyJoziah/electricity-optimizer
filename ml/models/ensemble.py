"""
Ensemble Model for Electricity Price Forecasting

Combines CNN-LSTM with gradient boosting models (XGBoost, LightGBM)
for improved prediction accuracy and robustness.

The ensemble uses weighted averaging with configurable weights,
allowing the deep learning model to capture complex temporal patterns
while gradient boosting models provide additional signal from
engineered features.
"""

import os
import json
import logging
import pickle
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict, field
import numpy as np
from abc import ABC, abstractmethod

try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False

from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.multioutput import MultiOutputRegressor

logger = logging.getLogger(__name__)


@dataclass
class XGBoostConfig:
    """Configuration for XGBoost model."""

    n_estimators: int = 500
    max_depth: int = 8
    learning_rate: float = 0.05
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    min_child_weight: int = 3
    reg_alpha: float = 0.1
    reg_lambda: float = 1.0
    objective: str = "reg:squarederror"
    tree_method: str = "hist"
    random_state: int = 42
    n_jobs: int = -1
    early_stopping_rounds: int = 50


@dataclass
class LightGBMConfig:
    """Configuration for LightGBM model."""

    n_estimators: int = 500
    max_depth: int = 8
    learning_rate: float = 0.05
    num_leaves: int = 31
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    min_child_samples: int = 20
    reg_alpha: float = 0.1
    reg_lambda: float = 1.0
    objective: str = "regression"
    boosting_type: str = "gbdt"
    random_state: int = 42
    n_jobs: int = -1
    verbose: int = -1


@dataclass
class EnsembleConfig:
    """Configuration for ensemble model."""

    # Model weights (should sum to 1)
    cnn_lstm_weight: float = 0.5
    xgboost_weight: float = 0.25
    lightgbm_weight: float = 0.25

    # Individual model configs
    xgboost: XGBoostConfig = field(default_factory=XGBoostConfig)
    lightgbm: LightGBMConfig = field(default_factory=LightGBMConfig)

    # Ensemble method
    method: str = "weighted_average"  # weighted_average, stacking

    # Feature configuration
    sequence_length: int = 168
    forecast_horizon: int = 24

    def __post_init__(self):
        # Normalize weights
        total = self.cnn_lstm_weight + self.xgboost_weight + self.lightgbm_weight
        self.cnn_lstm_weight /= total
        self.xgboost_weight /= total
        self.lightgbm_weight /= total


class BaseGBMForecaster(ABC, BaseEstimator, RegressorMixin):
    """Abstract base class for gradient boosting forecasters."""

    def __init__(self, forecast_horizon: int = 24):
        self.forecast_horizon = forecast_horizon
        self.models = []  # One model per forecast step
        self.is_fitted = False

    @abstractmethod
    def _create_model(self):
        """Create a single gradient boosting model."""
        pass

    def _prepare_features(self, X: np.ndarray) -> np.ndarray:
        """
        Flatten 3D sequence data to 2D for gradient boosting.

        Args:
            X: Input shape (samples, sequence_length, features)

        Returns:
            Flattened array shape (samples, sequence_length * features)
        """
        if len(X.shape) == 3:
            return X.reshape(X.shape[0], -1)
        return X

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None
    ) -> 'BaseGBMForecaster':
        """
        Fit the model.

        Args:
            X: Training features
            y: Training targets, shape (samples, forecast_horizon)
            X_val: Validation features (optional)
            y_val: Validation targets (optional)
        """
        X_flat = self._prepare_features(X)

        if X_val is not None:
            X_val_flat = self._prepare_features(X_val)

        self.models = []

        for step in range(self.forecast_horizon):
            logger.info(f"Training model for forecast step {step + 1}/{self.forecast_horizon}")

            model = self._create_model()

            # Train with or without validation
            if X_val is not None and y_val is not None:
                model.fit(
                    X_flat, y[:, step],
                    eval_set=[(X_val_flat, y_val[:, step])],
                )
            else:
                model.fit(X_flat, y[:, step])

            self.models.append(model)

        self.is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Generate predictions.

        Args:
            X: Input features

        Returns:
            Predictions, shape (samples, forecast_horizon)
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before prediction")

        X_flat = self._prepare_features(X)

        predictions = np.zeros((X_flat.shape[0], self.forecast_horizon))

        for step, model in enumerate(self.models):
            predictions[:, step] = model.predict(X_flat)

        return predictions


class XGBoostForecaster(BaseGBMForecaster):
    """XGBoost-based forecaster for electricity prices."""

    def __init__(
        self,
        config: XGBoostConfig = None,
        forecast_horizon: int = 24
    ):
        super().__init__(forecast_horizon)
        self.config = config or XGBoostConfig()

        if not HAS_XGBOOST:
            raise ImportError("xgboost is required but not installed")

    def _create_model(self):
        """Create XGBoost regressor."""
        return xgb.XGBRegressor(
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            learning_rate=self.config.learning_rate,
            subsample=self.config.subsample,
            colsample_bytree=self.config.colsample_bytree,
            min_child_weight=self.config.min_child_weight,
            reg_alpha=self.config.reg_alpha,
            reg_lambda=self.config.reg_lambda,
            objective=self.config.objective,
            tree_method=self.config.tree_method,
            random_state=self.config.random_state,
            n_jobs=self.config.n_jobs,
            early_stopping_rounds=self.config.early_stopping_rounds,
            verbosity=0
        )

    def get_feature_importance(self) -> Dict[str, np.ndarray]:
        """Get feature importance from all models."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted first")

        importance = {
            'gain': np.zeros(len(self.models[0].feature_importances_)),
            'weight': np.zeros(len(self.models[0].feature_importances_))
        }

        for model in self.models:
            importance['gain'] += model.feature_importances_

        importance['gain'] /= len(self.models)

        return importance

    def save(self, path: str):
        """Save model to disk."""
        os.makedirs(path, exist_ok=True)

        # Save config
        config_path = os.path.join(path, 'xgb_config.json')
        with open(config_path, 'w') as f:
            json.dump(asdict(self.config), f, indent=2)

        # Save models
        for i, model in enumerate(self.models):
            model_path = os.path.join(path, f'xgb_model_{i}.json')
            model.save_model(model_path)

        logger.info(f"XGBoost model saved to {path}")

    def load(self, path: str):
        """Load model from disk."""
        # Load config
        config_path = os.path.join(path, 'xgb_config.json')
        with open(config_path, 'r') as f:
            config_dict = json.load(f)
        self.config = XGBoostConfig(**config_dict)

        # Load models
        self.models = []
        i = 0
        while True:
            model_path = os.path.join(path, f'xgb_model_{i}.json')
            if not os.path.exists(model_path):
                break
            model = xgb.XGBRegressor()
            model.load_model(model_path)
            self.models.append(model)
            i += 1

        self.is_fitted = len(self.models) > 0
        logger.info(f"XGBoost model loaded from {path}")


class LightGBMForecaster(BaseGBMForecaster):
    """LightGBM-based forecaster for electricity prices."""

    def __init__(
        self,
        config: LightGBMConfig = None,
        forecast_horizon: int = 24
    ):
        super().__init__(forecast_horizon)
        self.config = config or LightGBMConfig()

        if not HAS_LIGHTGBM:
            raise ImportError("lightgbm is required but not installed")

    def _create_model(self):
        """Create LightGBM regressor."""
        return lgb.LGBMRegressor(
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            learning_rate=self.config.learning_rate,
            num_leaves=self.config.num_leaves,
            subsample=self.config.subsample,
            colsample_bytree=self.config.colsample_bytree,
            min_child_samples=self.config.min_child_samples,
            reg_alpha=self.config.reg_alpha,
            reg_lambda=self.config.reg_lambda,
            objective=self.config.objective,
            boosting_type=self.config.boosting_type,
            random_state=self.config.random_state,
            n_jobs=self.config.n_jobs,
            verbose=self.config.verbose
        )

    def get_feature_importance(self) -> Dict[str, np.ndarray]:
        """Get feature importance from all models."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted first")

        n_features = len(self.models[0].feature_importances_)
        importance = {
            'gain': np.zeros(n_features),
            'split': np.zeros(n_features)
        }

        for model in self.models:
            importance['gain'] += model.feature_importances_

        importance['gain'] /= len(self.models)

        return importance

    def save(self, path: str):
        """Save model to disk."""
        os.makedirs(path, exist_ok=True)

        # Save config
        config_path = os.path.join(path, 'lgb_config.json')
        with open(config_path, 'w') as f:
            json.dump(asdict(self.config), f, indent=2)

        # Save models
        for i, model in enumerate(self.models):
            model_path = os.path.join(path, f'lgb_model_{i}.txt')
            model.booster_.save_model(model_path)

        logger.info(f"LightGBM model saved to {path}")

    def load(self, path: str):
        """Load model from disk."""
        # Load config
        config_path = os.path.join(path, 'lgb_config.json')
        with open(config_path, 'r') as f:
            config_dict = json.load(f)
        self.config = LightGBMConfig(**config_dict)

        # Load models
        self.models = []
        i = 0
        while True:
            model_path = os.path.join(path, f'lgb_model_{i}.txt')
            if not os.path.exists(model_path):
                break
            model = lgb.Booster(model_file=model_path)
            self.models.append(model)
            i += 1

        self.is_fitted = len(self.models) > 0
        logger.info(f"LightGBM model loaded from {path}")


class EnsembleForecaster:
    """
    Ensemble forecaster combining CNN-LSTM with gradient boosting models.

    Provides weighted averaging of predictions from:
    - CNN-LSTM: Captures complex temporal patterns
    - XGBoost: Robust gradient boosting with feature importance
    - LightGBM: Fast gradient boosting with good handling of categorical features

    The ensemble typically achieves better performance than individual models
    by combining their complementary strengths.
    """

    def __init__(
        self,
        config: EnsembleConfig = None,
        cnn_lstm_model=None  # ElectricityPriceForecaster instance
    ):
        """
        Initialize ensemble forecaster.

        Args:
            config: Ensemble configuration
            cnn_lstm_model: Pre-trained CNN-LSTM model (optional)
        """
        self.config = config or EnsembleConfig()
        self.cnn_lstm_model = cnn_lstm_model

        # Initialize gradient boosting models
        self.xgboost_model = None
        self.lightgbm_model = None

        if HAS_XGBOOST and self.config.xgboost_weight > 0:
            self.xgboost_model = XGBoostForecaster(
                config=self.config.xgboost,
                forecast_horizon=self.config.forecast_horizon
            )

        if HAS_LIGHTGBM and self.config.lightgbm_weight > 0:
            self.lightgbm_model = LightGBMForecaster(
                config=self.config.lightgbm,
                forecast_horizon=self.config.forecast_horizon
            )

        self.is_fitted = False

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        fit_cnn_lstm: bool = True,
        cnn_lstm_kwargs: Optional[Dict] = None
    ) -> 'EnsembleForecaster':
        """
        Fit all models in the ensemble.

        Args:
            X_train: Training features
            y_train: Training targets
            X_val: Validation features
            y_val: Validation targets
            fit_cnn_lstm: Whether to train the CNN-LSTM model
            cnn_lstm_kwargs: Additional arguments for CNN-LSTM training
        """
        logger.info("Training ensemble models...")

        # Train CNN-LSTM
        if fit_cnn_lstm and self.cnn_lstm_model is not None:
            logger.info("Training CNN-LSTM model...")
            kwargs = cnn_lstm_kwargs or {}
            self.cnn_lstm_model.fit(
                X_train, y_train,
                X_val=X_val,
                y_val=y_val,
                **kwargs
            )

        # Train XGBoost
        if self.xgboost_model is not None and self.config.xgboost_weight > 0:
            logger.info("Training XGBoost model...")
            self.xgboost_model.fit(X_train, y_train, X_val, y_val)

        # Train LightGBM
        if self.lightgbm_model is not None and self.config.lightgbm_weight > 0:
            logger.info("Training LightGBM model...")
            self.lightgbm_model.fit(X_train, y_train, X_val, y_val)

        self.is_fitted = True
        logger.info("Ensemble training completed")

        return self

    def predict(
        self,
        X: np.ndarray,
        return_individual: bool = False
    ) -> Union[np.ndarray, Tuple[np.ndarray, Dict[str, np.ndarray]]]:
        """
        Generate ensemble predictions.

        Args:
            X: Input features
            return_individual: Whether to return individual model predictions

        Returns:
            Ensemble predictions, shape (samples, forecast_horizon)
            If return_individual=True, also returns dict of individual predictions
        """
        if not self.is_fitted:
            raise RuntimeError("Ensemble must be fitted before prediction")

        individual_predictions = {}
        weights = []
        predictions_list = []

        # CNN-LSTM predictions
        if self.cnn_lstm_model is not None and self.config.cnn_lstm_weight > 0:
            cnn_pred = self.cnn_lstm_model.predict(X, return_confidence=False)
            individual_predictions['cnn_lstm'] = cnn_pred
            predictions_list.append(cnn_pred)
            weights.append(self.config.cnn_lstm_weight)

        # XGBoost predictions
        if self.xgboost_model is not None and self.config.xgboost_weight > 0:
            xgb_pred = self.xgboost_model.predict(X)
            individual_predictions['xgboost'] = xgb_pred
            predictions_list.append(xgb_pred)
            weights.append(self.config.xgboost_weight)

        # LightGBM predictions
        if self.lightgbm_model is not None and self.config.lightgbm_weight > 0:
            lgb_pred = self.lightgbm_model.predict(X)
            individual_predictions['lightgbm'] = lgb_pred
            predictions_list.append(lgb_pred)
            weights.append(self.config.lightgbm_weight)

        # Weighted average
        if len(predictions_list) == 0:
            raise RuntimeError("No models available for prediction")

        weights = np.array(weights)
        weights = weights / weights.sum()  # Normalize

        ensemble_pred = np.zeros_like(predictions_list[0])
        for pred, weight in zip(predictions_list, weights):
            ensemble_pred += pred * weight

        if return_individual:
            return ensemble_pred, individual_predictions
        return ensemble_pred

    def predict_with_confidence(
        self,
        X: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate predictions with confidence intervals.

        Uses the spread between individual model predictions
        to estimate uncertainty.

        Args:
            X: Input features

        Returns:
            (forecast, lower_bound, upper_bound)
        """
        ensemble_pred, individual = self.predict(X, return_individual=True)

        # Stack individual predictions
        all_preds = np.stack(list(individual.values()), axis=0)

        # Compute confidence bounds from model disagreement
        std = np.std(all_preds, axis=0)

        # Use 1.96 * std for 95% confidence interval
        lower = ensemble_pred - 1.96 * std
        upper = ensemble_pred + 1.96 * std

        return ensemble_pred, lower, upper

    def evaluate(
        self,
        X_test: np.ndarray,
        y_test: np.ndarray
    ) -> Dict[str, Dict[str, float]]:
        """
        Evaluate ensemble and individual model performance.

        Args:
            X_test: Test features
            y_test: Test targets

        Returns:
            Dictionary with metrics for ensemble and each individual model
        """
        results = {}

        # Get all predictions
        ensemble_pred, individual = self.predict(X_test, return_individual=True)

        # Evaluate ensemble
        results['ensemble'] = self._compute_metrics(y_test, ensemble_pred)

        # Evaluate individual models
        for name, pred in individual.items():
            results[name] = self._compute_metrics(y_test, pred)

        # Log results
        for name, metrics in results.items():
            logger.info(f"{name}: MAPE={metrics['mape']:.2f}%, "
                       f"MAE={metrics['mae']:.4f}, RMSE={metrics['rmse']:.4f}")

        return results

    def _compute_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray
    ) -> Dict[str, float]:
        """Compute evaluation metrics."""
        mae = np.mean(np.abs(y_true - y_pred))
        rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
        mape = np.mean(np.abs((y_true - y_pred) / (y_true + 1e-8))) * 100

        return {
            'mae': float(mae),
            'rmse': float(rmse),
            'mape': float(mape)
        }

    def save(self, path: str):
        """Save ensemble model."""
        os.makedirs(path, exist_ok=True)

        # Save config
        config_path = os.path.join(path, 'ensemble_config.json')
        config_dict = {
            'cnn_lstm_weight': self.config.cnn_lstm_weight,
            'xgboost_weight': self.config.xgboost_weight,
            'lightgbm_weight': self.config.lightgbm_weight,
            'method': self.config.method,
            'sequence_length': self.config.sequence_length,
            'forecast_horizon': self.config.forecast_horizon
        }
        with open(config_path, 'w') as f:
            json.dump(config_dict, f, indent=2)

        # Save individual models
        if self.cnn_lstm_model is not None:
            cnn_lstm_path = os.path.join(path, 'cnn_lstm')
            self.cnn_lstm_model.save(cnn_lstm_path)

        if self.xgboost_model is not None:
            xgb_path = os.path.join(path, 'xgboost')
            self.xgboost_model.save(xgb_path)

        if self.lightgbm_model is not None:
            lgb_path = os.path.join(path, 'lightgbm')
            self.lightgbm_model.save(lgb_path)

        logger.info(f"Ensemble saved to {path}")

    def load(self, path: str):
        """Load ensemble model."""
        # Load config
        config_path = os.path.join(path, 'ensemble_config.json')
        with open(config_path, 'r') as f:
            config_dict = json.load(f)

        self.config = EnsembleConfig(
            cnn_lstm_weight=config_dict.get('cnn_lstm_weight', 0.5),
            xgboost_weight=config_dict.get('xgboost_weight', 0.25),
            lightgbm_weight=config_dict.get('lightgbm_weight', 0.25)
        )

        # Load individual models
        cnn_lstm_path = os.path.join(path, 'cnn_lstm')
        if os.path.exists(cnn_lstm_path):
            from .price_forecaster import ElectricityPriceForecaster
            self.cnn_lstm_model = ElectricityPriceForecaster(model_path=cnn_lstm_path)

        xgb_path = os.path.join(path, 'xgboost')
        if os.path.exists(xgb_path) and HAS_XGBOOST:
            self.xgboost_model = XGBoostForecaster()
            self.xgboost_model.load(xgb_path)

        lgb_path = os.path.join(path, 'lightgbm')
        if os.path.exists(lgb_path) and HAS_LIGHTGBM:
            self.lightgbm_model = LightGBMForecaster()
            self.lightgbm_model.load(lgb_path)

        self.is_fitted = True
        logger.info(f"Ensemble loaded from {path}")
