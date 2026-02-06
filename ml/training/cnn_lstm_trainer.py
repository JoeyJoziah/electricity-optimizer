"""
CNN-LSTM Model Trainer

Trains the CNN-LSTM model with attention mechanism for electricity price
forecasting. Supports multi-step forecasting with confidence intervals.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)


class CNNLSTMTrainer:
    """
    Trainer for CNN-LSTM price forecasting model.

    Architecture:
    - 1D CNN layers for local pattern extraction
    - Bidirectional LSTM layers for temporal dependencies
    - Multi-head attention for long-range dependencies
    - Dense output layers for multi-step prediction

    Args:
        config: Model configuration dictionary
        training_config: Training hyperparameters dictionary

    Example:
        trainer = CNNLSTMTrainer(config, training_config)
        X, y = trainer.prepare_sequences(df, feature_cols, target_col)
        metrics = trainer.train(X, y, validation_split=0.15)
        trainer.save("/path/to/model")
    """

    def __init__(
        self,
        config: Dict[str, Any],
        training_config: Dict[str, Any],
    ):
        self.config = config
        self.training_config = training_config
        self.model = None
        self.scaler = None
        self.history = None

    def prepare_sequences(
        self,
        df: pd.DataFrame,
        feature_columns: List[str],
        target_column: str,
        sequence_length: int = 168,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare sequences for training.

        Creates overlapping sequences of input features and corresponding
        target values for sequence-to-sequence training.

        Args:
            df: DataFrame with features and target
            feature_columns: List of feature column names
            target_column: Target column name
            sequence_length: Length of input sequences (default: 168 = 7 days)

        Returns:
            Tuple of (X, y) arrays:
                X: (n_samples, sequence_length, n_features)
                y: (n_samples, forecast_horizon, n_outputs)
        """
        import torch
        from sklearn.preprocessing import StandardScaler

        logger.info(f"Preparing sequences with length {sequence_length}")

        # Extract features and target
        features = df[feature_columns].values.astype(np.float32)
        target = df[target_column].values.astype(np.float32)

        # Scale features
        self.scaler = StandardScaler()
        features_scaled = self.scaler.fit_transform(features)

        # Get forecast horizon from config
        forecast_horizon = self.config.get("output", {}).get("forecast_horizon", 24)

        # Create sequences
        X_list = []
        y_list = []

        for i in range(len(features_scaled) - sequence_length - forecast_horizon + 1):
            X_list.append(features_scaled[i : i + sequence_length])

            # Target: next forecast_horizon values
            y_values = target[i + sequence_length : i + sequence_length + forecast_horizon]

            # Create point estimate (target) and bounds (simple uncertainty)
            # In production, would use quantile regression or similar
            y_point = y_values
            y_lower = y_values * 0.9  # Simple 10% lower bound
            y_upper = y_values * 1.1  # Simple 10% upper bound

            y_list.append(np.stack([y_point, y_lower, y_upper], axis=-1))

        X = np.array(X_list, dtype=np.float32)
        y = np.array(y_list, dtype=np.float32)

        logger.info(f"Created {len(X)} sequences, X shape: {X.shape}, y shape: {y.shape}")

        return X, y

    def _build_model(
        self,
        n_features: int,
        sequence_length: int,
    ):
        """Build the CNN-LSTM model architecture."""
        import torch
        import torch.nn as nn

        class CNNLSTMModel(nn.Module):
            def __init__(
                self,
                n_features: int,
                sequence_length: int,
                config: Dict[str, Any],
            ):
                super().__init__()

                cnn_config = config.get("cnn", {})
                lstm_config = config.get("lstm", {})
                attention_config = config.get("attention", {})
                dense_config = config.get("dense", {})
                output_config = config.get("output", {})

                # CNN layers
                cnn_filters = cnn_config.get("filters", [64, 128, 64])
                kernel_sizes = cnn_config.get("kernel_sizes", [3, 5, 3])

                self.conv_layers = nn.ModuleList()
                in_channels = n_features

                for filters, kernel_size in zip(cnn_filters, kernel_sizes):
                    self.conv_layers.append(nn.Sequential(
                        nn.Conv1d(in_channels, filters, kernel_size, padding=kernel_size // 2),
                        nn.BatchNorm1d(filters) if cnn_config.get("batch_norm", True) else nn.Identity(),
                        nn.ReLU(),
                        nn.MaxPool1d(2),
                    ))
                    in_channels = filters
                    sequence_length = sequence_length // 2

                # LSTM layers
                lstm_units = lstm_config.get("units", [128, 64])
                lstm_dropout = lstm_config.get("dropout", 0.2)

                self.lstm_layers = nn.ModuleList()
                lstm_input = cnn_filters[-1]

                for i, units in enumerate(lstm_units):
                    self.lstm_layers.append(
                        nn.LSTM(
                            lstm_input,
                            units,
                            batch_first=True,
                            bidirectional=True,
                            dropout=lstm_dropout if i < len(lstm_units) - 1 else 0,
                        )
                    )
                    lstm_input = units * 2  # Bidirectional doubles output

                # Attention
                if attention_config.get("enabled", True):
                    self.attention = nn.MultiheadAttention(
                        embed_dim=lstm_units[-1] * 2,
                        num_heads=attention_config.get("heads", 4),
                        dropout=attention_config.get("dropout", 0.1),
                        batch_first=True,
                    )
                else:
                    self.attention = None

                # Dense layers
                dense_units = dense_config.get("units", [64, 32])
                dense_dropout = dense_config.get("dropout", 0.3)

                self.dense_layers = nn.ModuleList()
                dense_input = lstm_units[-1] * 2

                for units in dense_units:
                    self.dense_layers.append(nn.Sequential(
                        nn.Linear(dense_input, units),
                        nn.ReLU(),
                        nn.Dropout(dense_dropout),
                    ))
                    dense_input = units

                # Output layer
                forecast_horizon = output_config.get("forecast_horizon", 24)
                n_outputs = output_config.get("num_outputs", 3)  # point, lower, upper

                self.output_layer = nn.Linear(dense_input, forecast_horizon * n_outputs)
                self.forecast_horizon = forecast_horizon
                self.n_outputs = n_outputs

            def forward(self, x):
                # x: (batch, seq_len, features)

                # CNN expects (batch, features, seq_len)
                x = x.permute(0, 2, 1)

                for conv in self.conv_layers:
                    x = conv(x)

                # Back to (batch, seq_len, features) for LSTM
                x = x.permute(0, 2, 1)

                # LSTM layers
                for lstm in self.lstm_layers:
                    x, _ = lstm(x)

                # Attention
                if self.attention is not None:
                    attn_out, _ = self.attention(x, x, x)
                    x = x + attn_out  # Residual connection

                # Take last timestep
                x = x[:, -1, :]

                # Dense layers
                for dense in self.dense_layers:
                    x = dense(x)

                # Output
                x = self.output_layer(x)

                # Reshape to (batch, horizon, n_outputs)
                x = x.view(-1, self.forecast_horizon, self.n_outputs)

                return x

        self.model = CNNLSTMModel(n_features, sequence_length, self.config)
        return self.model

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        validation_split: float = 0.15,
        epochs: int = 200,
    ) -> Dict[str, float]:
        """
        Train the model.

        Args:
            X_train: Training features (n_samples, seq_len, n_features)
            y_train: Training targets (n_samples, horizon, n_outputs)
            validation_split: Fraction for validation
            epochs: Maximum training epochs

        Returns:
            Dictionary of final metrics (loss, val_loss, val_mape)
        """
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        logger.info(f"Starting training: {len(X_train)} samples, {epochs} max epochs")

        # Split data
        n_val = int(len(X_train) * validation_split)
        X_val, y_val = X_train[-n_val:], y_train[-n_val:]
        X_train, y_train = X_train[:-n_val], y_train[:-n_val]

        # Convert to tensors
        X_train_t = torch.FloatTensor(X_train)
        y_train_t = torch.FloatTensor(y_train)
        X_val_t = torch.FloatTensor(X_val)
        y_val_t = torch.FloatTensor(y_val)

        # Create data loaders
        batch_size = self.training_config.get("batch_size", 32)
        train_dataset = TensorDataset(X_train_t, y_train_t)
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

        # Build model
        n_features = X_train.shape[2]
        sequence_length = X_train.shape[1]
        self._build_model(n_features, sequence_length)

        # Optimizer and loss
        optimizer_config = self.training_config.get("optimizer", {})
        optimizer = torch.optim.Adam(
            self.model.parameters(),
            lr=optimizer_config.get("learning_rate", 0.001),
            betas=(optimizer_config.get("beta_1", 0.9), optimizer_config.get("beta_2", 0.999)),
        )

        loss_fn = nn.MSELoss()

        # Learning rate scheduler
        lr_config = self.training_config.get("lr_schedule", {})
        if lr_config.get("enabled", True):
            scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
                optimizer,
                mode="min",
                factor=lr_config.get("factor", 0.5),
                patience=lr_config.get("patience", 10),
                min_lr=lr_config.get("min_lr", 1e-6),
            )
        else:
            scheduler = None

        # Early stopping
        early_config = self.training_config.get("early_stopping", {})
        patience = early_config.get("patience", 20)
        min_delta = early_config.get("min_delta", 0.0001)
        best_val_loss = float("inf")
        patience_counter = 0
        best_weights = None

        # Training loop
        self.history = {"loss": [], "val_loss": [], "val_mape": []}

        for epoch in range(epochs):
            # Training phase
            self.model.train()
            train_loss = 0

            for batch_X, batch_y in train_loader:
                optimizer.zero_grad()
                output = self.model(batch_X)
                loss = loss_fn(output, batch_y)
                loss.backward()
                optimizer.step()
                train_loss += loss.item()

            train_loss /= len(train_loader)

            # Validation phase
            self.model.eval()
            with torch.no_grad():
                val_output = self.model(X_val_t)
                val_loss = loss_fn(val_output, y_val_t).item()

                # Calculate MAPE on point estimates
                point_pred = val_output[:, :, 0].numpy()
                point_actual = y_val_t[:, :, 0].numpy()
                val_mape = np.mean(np.abs((point_actual - point_pred) / (point_actual + 1e-8))) * 100

            # Update history
            self.history["loss"].append(train_loss)
            self.history["val_loss"].append(val_loss)
            self.history["val_mape"].append(val_mape)

            # Learning rate scheduling
            if scheduler:
                scheduler.step(val_loss)

            # Logging
            if epoch % 10 == 0:
                logger.info(
                    f"Epoch {epoch}: loss={train_loss:.4f}, "
                    f"val_loss={val_loss:.4f}, val_mape={val_mape:.2f}%"
                )

            # Early stopping check
            if val_loss < best_val_loss - min_delta:
                best_val_loss = val_loss
                best_weights = {k: v.clone() for k, v in self.model.state_dict().items()}
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    logger.info(f"Early stopping at epoch {epoch}")
                    break

        # Restore best weights
        if best_weights and early_config.get("restore_best_weights", True):
            self.model.load_state_dict(best_weights)

        # Final metrics
        final_metrics = {
            "loss": self.history["loss"][-1],
            "val_loss": min(self.history["val_loss"]),
            "val_mape": min(self.history["val_mape"]),
            "epochs_trained": len(self.history["loss"]),
        }

        logger.info(f"Training complete: val_mape={final_metrics['val_mape']:.2f}%")

        return final_metrics

    def save(self, path: str):
        """Save model and artifacts."""
        import torch
        import joblib

        os.makedirs(path, exist_ok=True)

        # Save model
        torch.save(self.model, os.path.join(path, "model.pt"))

        # Save scaler
        if self.scaler:
            joblib.dump(self.scaler, os.path.join(path, "scaler.pkl"))

        # Save config
        with open(os.path.join(path, "config.yaml"), "w") as f:
            yaml.dump(self.config, f)

        # Save training config
        with open(os.path.join(path, "training_config.yaml"), "w") as f:
            yaml.dump(self.training_config, f)

        # Save metadata
        metadata = {
            "trained_at": datetime.utcnow().isoformat(),
            "metrics": {
                "val_loss": min(self.history["val_loss"]),
                "val_mape": min(self.history["val_mape"]),
            },
            "epochs_trained": len(self.history["loss"]),
        }
        with open(os.path.join(path, "metadata.yaml"), "w") as f:
            yaml.dump(metadata, f)

        logger.info(f"Model saved to {path}")
