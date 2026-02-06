"""
Hyperparameter Tuning for Price Forecasting Models

Provides automated hyperparameter optimization using:
- Grid Search
- Random Search
- Bayesian Optimization
- Optuna for advanced optimization

Integrates with MLflow for experiment tracking.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, field, asdict
import numpy as np
import pandas as pd
from datetime import datetime

# ML frameworks
import optuna
from optuna.samplers import TPESampler
from optuna.pruners import MedianPruner
from sklearn.model_selection import ParameterGrid, ParameterSampler
from scipy.stats import uniform, randint

# TensorFlow
import tensorflow as tf
from tensorflow import keras

# Local imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


@dataclass
class HyperparameterSpace:
    """Defines hyperparameter search space"""

    # CNN parameters
    cnn_filters: List[int] = field(default_factory=lambda: [32, 64, 128])
    cnn_kernel_size: List[int] = field(default_factory=lambda: [3, 5, 7])
    cnn_layers: List[int] = field(default_factory=lambda: [1, 2, 3])

    # LSTM parameters
    lstm_units: List[int] = field(default_factory=lambda: [32, 64, 128, 256])
    lstm_layers: List[int] = field(default_factory=lambda: [1, 2, 3])
    lstm_dropout: List[float] = field(default_factory=lambda: [0.0, 0.1, 0.2, 0.3])

    # Dense layer parameters
    dense_units: List[int] = field(default_factory=lambda: [16, 32, 64])
    dense_layers: List[int] = field(default_factory=lambda: [1, 2])
    dense_dropout: List[float] = field(default_factory=lambda: [0.0, 0.1, 0.2])

    # Training parameters
    learning_rate: List[float] = field(default_factory=lambda: [0.0001, 0.0005, 0.001, 0.005])
    batch_size: List[int] = field(default_factory=lambda: [16, 32, 64])
    optimizer: List[str] = field(default_factory=lambda: ['adam', 'rmsprop'])

    # Feature engineering
    lookback_hours: List[int] = field(default_factory=lambda: [72, 168, 336])

    def to_optuna_space(self, trial: optuna.Trial) -> Dict[str, Any]:
        """Convert to Optuna trial suggestions"""
        return {
            'cnn_filters': trial.suggest_categorical('cnn_filters', self.cnn_filters),
            'cnn_kernel_size': trial.suggest_categorical('cnn_kernel_size', self.cnn_kernel_size),
            'cnn_layers': trial.suggest_int('cnn_layers', min(self.cnn_layers), max(self.cnn_layers)),

            'lstm_units': trial.suggest_categorical('lstm_units', self.lstm_units),
            'lstm_layers': trial.suggest_int('lstm_layers', min(self.lstm_layers), max(self.lstm_layers)),
            'lstm_dropout': trial.suggest_float('lstm_dropout', min(self.lstm_dropout), max(self.lstm_dropout)),

            'dense_units': trial.suggest_categorical('dense_units', self.dense_units),
            'dense_layers': trial.suggest_int('dense_layers', min(self.dense_layers), max(self.dense_layers)),
            'dense_dropout': trial.suggest_float('dense_dropout', min(self.dense_dropout), max(self.dense_dropout)),

            'learning_rate': trial.suggest_loguniform('learning_rate', min(self.learning_rate), max(self.learning_rate)),
            'batch_size': trial.suggest_categorical('batch_size', self.batch_size),
            'optimizer': trial.suggest_categorical('optimizer', self.optimizer),

            'lookback_hours': trial.suggest_categorical('lookback_hours', self.lookback_hours)
        }


class HyperparameterTuner:
    """
    Hyperparameter optimization for price forecasting models

    Supports multiple search strategies:
    - Grid Search: Exhaustive search over parameter grid
    - Random Search: Random sampling from parameter distributions
    - Bayesian Optimization: Sequential model-based optimization (Optuna)
    """

    def __init__(
        self,
        model_builder: Callable,
        search_space: HyperparameterSpace,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        metric: str = 'val_loss',
        direction: str = 'minimize',
        n_epochs: int = 50,
        early_stopping_patience: int = 10,
        results_dir: Path = Path('results/tuning')
    ):
        """
        Initialize hyperparameter tuner

        Args:
            model_builder: Function that builds model from hyperparameters
            search_space: Hyperparameter search space
            X_train, y_train: Training data
            X_val, y_val: Validation data
            metric: Metric to optimize ('val_loss', 'val_mape', etc.)
            direction: 'minimize' or 'maximize'
            n_epochs: Max epochs per trial
            early_stopping_patience: Early stopping patience
            results_dir: Directory to save results
        """
        self.model_builder = model_builder
        self.search_space = search_space

        self.X_train = X_train
        self.y_train = y_train
        self.X_val = X_val
        self.y_val = y_val

        self.metric = metric
        self.direction = direction
        self.n_epochs = n_epochs
        self.early_stopping_patience = early_stopping_patience

        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)

        self.results: List[Dict[str, Any]] = []

    def grid_search(
        self,
        max_trials: Optional[int] = None
    ) -> Tuple[Dict[str, Any], float]:
        """
        Grid search over hyperparameter space

        Args:
            max_trials: Maximum number of trials (if None, try all combinations)

        Returns:
            best_params: Best hyperparameters
            best_score: Best validation score
        """
        logger.info("Starting grid search...")

        # Create parameter grid
        param_grid = {
            'cnn_filters': self.search_space.cnn_filters,
            'cnn_kernel_size': self.search_space.cnn_kernel_size,
            'cnn_layers': self.search_space.cnn_layers,
            'lstm_units': self.search_space.lstm_units,
            'lstm_layers': self.search_space.lstm_layers,
            'lstm_dropout': self.search_space.lstm_dropout,
            'dense_units': self.search_space.dense_units,
            'dense_layers': self.search_space.dense_layers,
            'dense_dropout': self.search_space.dense_dropout,
            'learning_rate': self.search_space.learning_rate,
            'batch_size': self.search_space.batch_size,
            'optimizer': self.search_space.optimizer,
            'lookback_hours': self.search_space.lookback_hours
        }

        grid = list(ParameterGrid(param_grid))

        if max_trials and max_trials < len(grid):
            # Random sample if too many combinations
            np.random.shuffle(grid)
            grid = grid[:max_trials]

        logger.info(f"Grid search: {len(grid)} combinations to try")

        best_score = float('inf') if self.direction == 'minimize' else float('-inf')
        best_params = None

        for i, params in enumerate(grid, 1):
            logger.info(f"Trial {i}/{len(grid)}: {params}")

            try:
                score, history = self._evaluate_params(params)

                self.results.append({
                    'trial': i,
                    'params': params,
                    'score': score,
                    'search_method': 'grid_search'
                })

                if self._is_better(score, best_score):
                    best_score = score
                    best_params = params
                    logger.info(f"New best score: {best_score:.6f}")

            except Exception as e:
                logger.error(f"Trial {i} failed: {e}")

        self._save_results()

        return best_params, best_score

    def random_search(
        self,
        n_trials: int = 50
    ) -> Tuple[Dict[str, Any], float]:
        """
        Random search over hyperparameter space

        Args:
            n_trials: Number of random trials

        Returns:
            best_params: Best hyperparameters
            best_score: Best validation score
        """
        logger.info(f"Starting random search with {n_trials} trials...")

        # Define distributions for sampling
        param_distributions = {
            'cnn_filters': self.search_space.cnn_filters,
            'cnn_kernel_size': self.search_space.cnn_kernel_size,
            'cnn_layers': self.search_space.cnn_layers,
            'lstm_units': self.search_space.lstm_units,
            'lstm_layers': self.search_space.lstm_layers,
            'lstm_dropout': uniform(min(self.search_space.lstm_dropout), max(self.search_space.lstm_dropout)),
            'dense_units': self.search_space.dense_units,
            'dense_layers': self.search_space.dense_layers,
            'dense_dropout': uniform(min(self.search_space.dense_dropout), max(self.search_space.dense_dropout)),
            'learning_rate': uniform(min(self.search_space.learning_rate), max(self.search_space.learning_rate)),
            'batch_size': self.search_space.batch_size,
            'optimizer': self.search_space.optimizer,
            'lookback_hours': self.search_space.lookback_hours
        }

        sampler = ParameterSampler(
            param_distributions,
            n_iter=n_trials,
            random_state=42
        )

        best_score = float('inf') if self.direction == 'minimize' else float('-inf')
        best_params = None

        for i, params in enumerate(sampler, 1):
            logger.info(f"Trial {i}/{n_trials}: {params}")

            try:
                score, history = self._evaluate_params(params)

                self.results.append({
                    'trial': i,
                    'params': params,
                    'score': score,
                    'search_method': 'random_search'
                })

                if self._is_better(score, best_score):
                    best_score = score
                    best_params = params
                    logger.info(f"New best score: {best_score:.6f}")

            except Exception as e:
                logger.error(f"Trial {i} failed: {e}")

        self._save_results()

        return best_params, best_score

    def bayesian_optimization(
        self,
        n_trials: int = 100,
        n_startup_trials: int = 10,
        study_name: Optional[str] = None
    ) -> Tuple[Dict[str, Any], float]:
        """
        Bayesian optimization using Optuna

        Args:
            n_trials: Number of trials
            n_startup_trials: Number of random trials before Bayesian optimization
            study_name: Study name for Optuna

        Returns:
            best_params: Best hyperparameters
            best_score: Best validation score
        """
        logger.info(f"Starting Bayesian optimization with {n_trials} trials...")

        if study_name is None:
            study_name = f"electricity_price_forecast_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Create Optuna study
        study = optuna.create_study(
            direction=self.direction,
            study_name=study_name,
            sampler=TPESampler(n_startup_trials=n_startup_trials),
            pruner=MedianPruner(n_startup_trials=n_startup_trials, n_warmup_steps=5)
        )

        def objective(trial: optuna.Trial) -> float:
            """Objective function for Optuna"""
            params = self.search_space.to_optuna_space(trial)

            try:
                score, history = self._evaluate_params(params)

                self.results.append({
                    'trial': trial.number,
                    'params': params,
                    'score': score,
                    'search_method': 'bayesian_optimization'
                })

                return score

            except Exception as e:
                logger.error(f"Trial {trial.number} failed: {e}")
                raise optuna.TrialPruned()

        # Optimize
        study.optimize(
            objective,
            n_trials=n_trials,
            catch=(Exception,),
            show_progress_bar=True
        )

        # Get best results
        best_params = study.best_params
        best_score = study.best_value

        logger.info(f"Best trial: {study.best_trial.number}")
        logger.info(f"Best score: {best_score:.6f}")
        logger.info(f"Best params: {best_params}")

        # Save Optuna study
        study_path = self.results_dir / f"{study_name}.pkl"
        optuna.save_study(study, str(study_path))

        self._save_results()

        return best_params, best_score

    def _evaluate_params(
        self,
        params: Dict[str, Any]
    ) -> Tuple[float, Dict[str, List[float]]]:
        """
        Evaluate a set of hyperparameters

        Args:
            params: Hyperparameters to evaluate

        Returns:
            score: Validation score
            history: Training history
        """
        # Build model with these hyperparameters
        model = self.model_builder(params)

        # Callbacks
        callbacks = [
            keras.callbacks.EarlyStopping(
                monitor=self.metric,
                patience=self.early_stopping_patience,
                restore_best_weights=True,
                verbose=0
            )
        ]

        # Train model
        history = model.fit(
            self.X_train,
            self.y_train,
            validation_data=(self.X_val, self.y_val),
            epochs=self.n_epochs,
            batch_size=params.get('batch_size', 32),
            callbacks=callbacks,
            verbose=0
        )

        # Get best validation score
        if self.metric in history.history:
            scores = history.history[self.metric]
            score = min(scores) if self.direction == 'minimize' else max(scores)
        else:
            # Fallback to final validation loss
            score = history.history['val_loss'][-1]

        return score, history.history

    def _is_better(self, score: float, best_score: float) -> bool:
        """Check if score is better than best_score"""
        if self.direction == 'minimize':
            return score < best_score
        else:
            return score > best_score

    def _save_results(self):
        """Save tuning results to disk"""
        results_path = self.results_dir / f"tuning_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(results_path, 'w') as f:
            json.dump(self.results, f, indent=2)

        logger.info(f"Results saved to {results_path}")


class BayesianOptimizer:
    """
    Simplified Bayesian optimization interface

    Wrapper around HyperparameterTuner.bayesian_optimization for common use cases.
    """

    @staticmethod
    def optimize(
        model_builder: Callable,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        n_trials: int = 50,
        search_space: Optional[HyperparameterSpace] = None
    ) -> Tuple[Dict[str, Any], float]:
        """
        Run Bayesian optimization with default settings

        Args:
            model_builder: Function that builds model from hyperparameters
            X_train, y_train: Training data
            X_val, y_val: Validation data
            n_trials: Number of trials
            search_space: Custom search space (if None, use defaults)

        Returns:
            best_params: Best hyperparameters
            best_score: Best validation score
        """
        if search_space is None:
            search_space = HyperparameterSpace()

        tuner = HyperparameterTuner(
            model_builder=model_builder,
            search_space=search_space,
            X_train=X_train,
            y_train=y_train,
            X_val=X_val,
            y_val=y_val
        )

        return tuner.bayesian_optimization(n_trials=n_trials)


def tune_price_forecaster(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    method: str = 'bayesian',
    n_trials: int = 50,
    search_space: Optional[HyperparameterSpace] = None
) -> Tuple[Dict[str, Any], float]:
    """
    Convenience function for tuning price forecaster

    Args:
        X_train, y_train: Training data
        X_val, y_val: Validation data
        method: 'grid', 'random', or 'bayesian'
        n_trials: Number of trials
        search_space: Custom search space

    Returns:
        best_params: Best hyperparameters
        best_score: Best validation score
    """
    # Import model builder
    from models.price_forecaster import build_model_from_params

    if search_space is None:
        search_space = HyperparameterSpace()

    tuner = HyperparameterTuner(
        model_builder=build_model_from_params,
        search_space=search_space,
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val
    )

    if method == 'grid':
        return tuner.grid_search(max_trials=n_trials)
    elif method == 'random':
        return tuner.random_search(n_trials=n_trials)
    elif method == 'bayesian':
        return tuner.bayesian_optimization(n_trials=n_trials)
    else:
        raise ValueError(f"Unknown method: {method}. Use 'grid', 'random', or 'bayesian'")


if __name__ == '__main__':
    # Example usage
    import sys
    sys.path.append('..')

    from data.feature_engineering import ElectricityPriceFeatureEngine
    from training.train_forecaster import load_training_data, prepare_datasets

    # Load data
    df = load_training_data('data/raw/electricity_prices.csv')

    # Feature engineering
    feature_engine = ElectricityPriceFeatureEngine()
    df_features = feature_engine.transform(df)

    # Prepare datasets
    X_train, y_train, X_val, y_val, X_test, y_test = prepare_datasets(
        df_features,
        lookback_hours=168,
        forecast_horizon=24
    )

    # Tune with Bayesian optimization
    best_params, best_score = tune_price_forecaster(
        X_train, y_train,
        X_val, y_val,
        method='bayesian',
        n_trials=50
    )

    print(f"\nBest params: {best_params}")
    print(f"Best score: {best_score:.6f}")
