"""
Training Script for Electricity Price Forecasting Models

This script orchestrates the complete training pipeline:
1. Load and validate data
2. Apply feature engineering
3. Create train/val/test splits
4. Train CNN-LSTM model
5. Train ensemble models (XGBoost, LightGBM)
6. Evaluate and save models
7. Generate training report

Usage:
    python train_forecaster.py --config config/model_config.yaml
    python train_forecaster.py --data data/prices.csv --epochs 100
"""

import os
import sys
import argparse
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
import numpy as np
import pandas as pd
import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ml.models.price_forecaster import (
    ElectricityPriceForecaster,
    ModelConfig as CNNLSTMConfig
)
from ml.models.ensemble import (
    EnsembleForecaster,
    EnsembleConfig,
    XGBoostConfig,
    LightGBMConfig
)
from ml.data.feature_engineering import (
    ElectricityPriceFeatureEngine,
    create_dummy_data
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    """Configuration for training pipeline."""

    # Data configuration
    data_path: Optional[str] = None
    use_dummy_data: bool = True
    dummy_data_hours: int = 8760  # 1 year

    # Feature engineering
    sequence_length: int = 168  # 7 days
    forecast_horizon: int = 24  # 24 hours
    country_code: str = "UK"

    # Train/Val/Test split
    train_ratio: float = 0.7
    val_ratio: float = 0.15
    test_ratio: float = 0.15

    # Model configuration
    num_features: int = 50  # Will be set after feature engineering
    cnn_filters: List[int] = field(default_factory=lambda: [64, 128, 64])
    cnn_kernel_sizes: List[int] = field(default_factory=lambda: [3, 5, 3])
    lstm_units: List[int] = field(default_factory=lambda: [128, 64])
    dense_units: List[int] = field(default_factory=lambda: [64, 32])

    # Training parameters
    epochs: int = 100
    batch_size: int = 32
    learning_rate: float = 0.001
    early_stopping_patience: int = 20

    # Ensemble configuration
    train_ensemble: bool = True
    cnn_lstm_weight: float = 0.5
    xgboost_weight: float = 0.25
    lightgbm_weight: float = 0.25

    # Output paths
    output_dir: str = "ml/saved_models"
    checkpoint_dir: str = "ml/checkpoints"
    log_dir: str = "ml/logs"

    # Performance targets
    target_mape: float = 10.0  # MAPE < 10%

    @classmethod
    def from_yaml(cls, path: str) -> 'TrainingConfig':
        """Load configuration from YAML file."""
        with open(path, 'r') as f:
            config_dict = yaml.safe_load(f)

        # Flatten nested config
        flat_config = {}
        for section, values in config_dict.items():
            if isinstance(values, dict):
                for key, value in values.items():
                    flat_config[key] = value
            else:
                flat_config[section] = values

        # Map to TrainingConfig fields
        return cls(
            sequence_length=flat_config.get('sequence_length', 168),
            forecast_horizon=flat_config.get('forecast_horizon', 24),
            epochs=flat_config.get('epochs', 100),
            batch_size=flat_config.get('batch_size', 32),
            learning_rate=flat_config.get('learning_rate', 0.001),
            cnn_filters=flat_config.get('filters', [64, 128, 64]),
            lstm_units=flat_config.get('units', [128, 64]),
            target_mape=flat_config.get('mape', 10.0),
        )


class ModelTrainer:
    """
    Orchestrates the complete training pipeline.

    Handles:
    - Data loading and validation
    - Feature engineering
    - Model training (CNN-LSTM and ensemble)
    - Evaluation and reporting
    - Model saving
    """

    def __init__(self, config: TrainingConfig):
        self.config = config
        self.feature_engine = None
        self.cnn_lstm_model = None
        self.ensemble_model = None
        self.training_results = {}

        # Create output directories
        os.makedirs(self.config.output_dir, exist_ok=True)
        os.makedirs(self.config.checkpoint_dir, exist_ok=True)
        os.makedirs(self.config.log_dir, exist_ok=True)

    def load_data(self) -> pd.DataFrame:
        """Load and validate data."""
        logger.info("Loading data...")

        if self.config.use_dummy_data:
            logger.info(f"Creating dummy data with {self.config.dummy_data_hours} hours")
            df = create_dummy_data(
                n_hours=self.config.dummy_data_hours,
                include_weather=True,
                include_generation=True
            )
        else:
            if not self.config.data_path:
                raise ValueError("data_path must be provided when use_dummy_data=False")

            logger.info(f"Loading data from {self.config.data_path}")
            df = pd.read_csv(self.config.data_path, index_col=0, parse_dates=True)

        logger.info(f"Data loaded: {len(df)} rows, {len(df.columns)} columns")
        logger.info(f"Date range: {df.index.min()} to {df.index.max()}")

        return df

    def prepare_features(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Apply feature engineering and create sequences."""
        logger.info("Preparing features...")

        # Initialize feature engine
        self.feature_engine = ElectricityPriceFeatureEngine(
            country=self.config.country_code,
            lookback_hours=self.config.sequence_length,
            forecast_hours=self.config.forecast_horizon
        )

        # Fit and transform
        self.feature_engine.fit(df)
        df_features = self.feature_engine.transform(df)

        # Create sequences
        X, y = self.feature_engine.create_sequences(df_features)

        # Update num_features in config
        self.config.num_features = X.shape[2]

        logger.info(f"Features prepared: X={X.shape}, y={y.shape}")
        logger.info(f"Number of features: {self.config.num_features}")

        return X, y

    def split_data(
        self,
        X: np.ndarray,
        y: np.ndarray
    ) -> Tuple[Tuple[np.ndarray, np.ndarray], ...]:
        """Split data into train/val/test sets."""
        logger.info("Splitting data...")

        n_samples = len(X)

        # Calculate split indices
        train_end = int(n_samples * self.config.train_ratio)
        val_end = int(n_samples * (self.config.train_ratio + self.config.val_ratio))

        # Split (maintaining temporal order)
        X_train, y_train = X[:train_end], y[:train_end]
        X_val, y_val = X[train_end:val_end], y[train_end:val_end]
        X_test, y_test = X[val_end:], y[val_end:]

        logger.info(f"Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")

        return (X_train, y_train), (X_val, y_val), (X_test, y_test)

    def train_cnn_lstm(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray
    ) -> Dict:
        """Train CNN-LSTM model."""
        logger.info("Training CNN-LSTM model...")

        # Create model config
        model_config = CNNLSTMConfig(
            sequence_length=self.config.sequence_length,
            num_features=self.config.num_features,
            forecast_horizon=self.config.forecast_horizon,
            cnn_filters=self.config.cnn_filters,
            cnn_kernel_sizes=self.config.cnn_kernel_sizes,
            lstm_units=self.config.lstm_units,
            dense_units=self.config.dense_units,
            learning_rate=self.config.learning_rate,
            batch_size=self.config.batch_size,
            epochs=self.config.epochs
        )

        # Create and train model
        self.cnn_lstm_model = ElectricityPriceForecaster(config=model_config)

        history = self.cnn_lstm_model.fit(
            X_train, y_train,
            X_val=X_val,
            y_val=y_val,
            checkpoint_dir=self.config.checkpoint_dir,
            log_dir=self.config.log_dir
        )

        return history

    def train_ensemble(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray
    ):
        """Train ensemble model."""
        if not self.config.train_ensemble:
            logger.info("Ensemble training disabled")
            return

        logger.info("Training ensemble model...")

        # Create ensemble config
        ensemble_config = EnsembleConfig(
            cnn_lstm_weight=self.config.cnn_lstm_weight,
            xgboost_weight=self.config.xgboost_weight,
            lightgbm_weight=self.config.lightgbm_weight,
            forecast_horizon=self.config.forecast_horizon,
            xgboost=XGBoostConfig(n_estimators=200),  # Reduced for training speed
            lightgbm=LightGBMConfig(n_estimators=200)
        )

        # Create ensemble with pre-trained CNN-LSTM
        self.ensemble_model = EnsembleForecaster(
            config=ensemble_config,
            cnn_lstm_model=self.cnn_lstm_model
        )

        # Train ensemble (CNN-LSTM already trained)
        self.ensemble_model.fit(
            X_train, y_train,
            X_val=X_val,
            y_val=y_val,
            fit_cnn_lstm=False  # Already trained
        )

    def evaluate(
        self,
        X_test: np.ndarray,
        y_test: np.ndarray
    ) -> Dict:
        """Evaluate all models."""
        logger.info("Evaluating models...")

        results = {}

        # Evaluate CNN-LSTM
        if self.cnn_lstm_model is not None:
            cnn_lstm_metrics = self.cnn_lstm_model.evaluate(X_test, y_test)
            results['cnn_lstm'] = cnn_lstm_metrics
            logger.info(f"CNN-LSTM MAPE: {cnn_lstm_metrics['mape']:.2f}%")

        # Evaluate ensemble
        if self.ensemble_model is not None:
            ensemble_results = self.ensemble_model.evaluate(X_test, y_test)
            results['ensemble'] = ensemble_results
            logger.info(f"Ensemble MAPE: {ensemble_results['ensemble']['mape']:.2f}%")

        # Check if target MAPE achieved
        best_mape = min(
            results.get('cnn_lstm', {}).get('mape', float('inf')),
            results.get('ensemble', {}).get('ensemble', {}).get('mape', float('inf'))
        )

        if best_mape <= self.config.target_mape:
            logger.info(f"Target MAPE of {self.config.target_mape}% achieved!")
        else:
            logger.warning(
                f"Target MAPE of {self.config.target_mape}% not achieved. "
                f"Best: {best_mape:.2f}%"
            )

        return results

    def save_models(self):
        """Save trained models."""
        logger.info("Saving models...")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save CNN-LSTM
        if self.cnn_lstm_model is not None:
            cnn_lstm_path = os.path.join(
                self.config.output_dir,
                f"cnn_lstm_{timestamp}"
            )
            self.cnn_lstm_model.save(cnn_lstm_path)

        # Save ensemble
        if self.ensemble_model is not None:
            ensemble_path = os.path.join(
                self.config.output_dir,
                f"ensemble_{timestamp}"
            )
            self.ensemble_model.save(ensemble_path)

        # Save training results
        results_path = os.path.join(
            self.config.output_dir,
            f"training_results_{timestamp}.json"
        )
        with open(results_path, 'w') as f:
            json.dump(self.training_results, f, indent=2, default=str)

        logger.info(f"Models saved to {self.config.output_dir}")

    def generate_report(self) -> str:
        """Generate training report."""
        report = []
        report.append("=" * 60)
        report.append("ELECTRICITY PRICE FORECASTING - TRAINING REPORT")
        report.append("=" * 60)
        report.append(f"\nTimestamp: {datetime.now().isoformat()}")

        # Configuration
        report.append("\n" + "-" * 40)
        report.append("CONFIGURATION")
        report.append("-" * 40)
        report.append(f"Sequence Length: {self.config.sequence_length} hours")
        report.append(f"Forecast Horizon: {self.config.forecast_horizon} hours")
        report.append(f"Number of Features: {self.config.num_features}")
        report.append(f"Epochs: {self.config.epochs}")
        report.append(f"Batch Size: {self.config.batch_size}")
        report.append(f"Learning Rate: {self.config.learning_rate}")

        # Results
        if 'evaluation' in self.training_results:
            report.append("\n" + "-" * 40)
            report.append("EVALUATION RESULTS")
            report.append("-" * 40)

            for model_name, metrics in self.training_results['evaluation'].items():
                report.append(f"\n{model_name.upper()}:")
                if isinstance(metrics, dict):
                    for metric_name, value in metrics.items():
                        if isinstance(value, dict):
                            for k, v in value.items():
                                report.append(f"  {k}: {v:.4f}")
                        else:
                            report.append(f"  {metric_name}: {value:.4f}")

        # Target achievement
        report.append("\n" + "-" * 40)
        report.append("TARGET ACHIEVEMENT")
        report.append("-" * 40)
        report.append(f"Target MAPE: {self.config.target_mape}%")

        if 'evaluation' in self.training_results:
            best_mape = float('inf')
            best_model = None

            eval_results = self.training_results['evaluation']
            if 'cnn_lstm' in eval_results:
                mape = eval_results['cnn_lstm'].get('mape', float('inf'))
                if mape < best_mape:
                    best_mape = mape
                    best_model = 'CNN-LSTM'

            if 'ensemble' in eval_results:
                ensemble_mape = eval_results['ensemble'].get('ensemble', {}).get('mape', float('inf'))
                if ensemble_mape < best_mape:
                    best_mape = ensemble_mape
                    best_model = 'Ensemble'

            report.append(f"Best MAPE: {best_mape:.2f}% ({best_model})")
            status = "ACHIEVED" if best_mape <= self.config.target_mape else "NOT ACHIEVED"
            report.append(f"Status: {status}")

        report.append("\n" + "=" * 60)

        return "\n".join(report)

    def run(self) -> Dict:
        """Run the complete training pipeline."""
        logger.info("Starting training pipeline...")

        start_time = datetime.now()

        try:
            # 1. Load data
            df = self.load_data()

            # 2. Prepare features
            X, y = self.prepare_features(df)

            # 3. Split data
            (X_train, y_train), (X_val, y_val), (X_test, y_test) = self.split_data(X, y)

            # 4. Train CNN-LSTM
            history = self.train_cnn_lstm(X_train, y_train, X_val, y_val)
            self.training_results['cnn_lstm_history'] = history

            # 5. Train ensemble
            self.train_ensemble(X_train, y_train, X_val, y_val)

            # 6. Evaluate
            evaluation = self.evaluate(X_test, y_test)
            self.training_results['evaluation'] = evaluation

            # 7. Save models
            self.save_models()

            # 8. Generate report
            report = self.generate_report()
            print(report)

            # Save report
            report_path = os.path.join(
                self.config.output_dir,
                f"training_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )
            with open(report_path, 'w') as f:
                f.write(report)

            self.training_results['status'] = 'success'
            self.training_results['duration'] = str(datetime.now() - start_time)

        except Exception as e:
            logger.error(f"Training failed: {e}")
            self.training_results['status'] = 'failed'
            self.training_results['error'] = str(e)
            raise

        logger.info(f"Training completed in {datetime.now() - start_time}")

        return self.training_results


def train_model(config: TrainingConfig = None) -> Dict:
    """
    Main training function.

    Args:
        config: Training configuration

    Returns:
        Training results dictionary
    """
    if config is None:
        config = TrainingConfig()

    trainer = ModelTrainer(config)
    return trainer.run()


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description='Train electricity price forecasting models'
    )
    parser.add_argument(
        '--config',
        type=str,
        help='Path to YAML configuration file'
    )
    parser.add_argument(
        '--data',
        type=str,
        help='Path to data file (CSV)'
    )
    parser.add_argument(
        '--epochs',
        type=int,
        default=100,
        help='Number of training epochs'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=32,
        help='Batch size'
    )
    parser.add_argument(
        '--learning-rate',
        type=float,
        default=0.001,
        help='Learning rate'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='ml/saved_models',
        help='Output directory for models'
    )
    parser.add_argument(
        '--no-ensemble',
        action='store_true',
        help='Skip ensemble training'
    )
    parser.add_argument(
        '--dummy-data',
        action='store_true',
        help='Use dummy data for testing'
    )
    parser.add_argument(
        '--dummy-hours',
        type=int,
        default=8760,
        help='Hours of dummy data to generate'
    )

    args = parser.parse_args()

    # Create configuration
    if args.config:
        config = TrainingConfig.from_yaml(args.config)
    else:
        config = TrainingConfig()

    # Override with CLI arguments
    if args.data:
        config.data_path = args.data
        config.use_dummy_data = False
    if args.dummy_data:
        config.use_dummy_data = True
    if args.dummy_hours:
        config.dummy_data_hours = args.dummy_hours
    if args.epochs:
        config.epochs = args.epochs
    if args.batch_size:
        config.batch_size = args.batch_size
    if args.learning_rate:
        config.learning_rate = args.learning_rate
    if args.output_dir:
        config.output_dir = args.output_dir
    if args.no_ensemble:
        config.train_ensemble = False

    # Run training
    results = train_model(config)

    return results


if __name__ == "__main__":
    main()
