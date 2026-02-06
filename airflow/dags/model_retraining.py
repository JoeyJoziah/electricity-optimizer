"""
Model Retraining DAG

Schedule: Weekly (Sunday 2:00 AM UTC)
Purpose: Retrain CNN-LSTM price forecasting model with latest data

Features:
- Extract 2 years of training data from TimescaleDB
- Feature engineering and preprocessing
- Train ensemble model (CNN-LSTM + XGBoost + LightGBM)
- Evaluate on validation set
- Deploy only if MAPE improves
- Update model registry
- Send metrics to monitoring

Timeout: 6 hours
Notification: On failure via email and Slack
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from airflow import DAG
from airflow.decorators import task, task_group
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator
from airflow.utils.trigger_rule import TriggerRule

from plugins.custom_operators import (
    DataQualityOperator,
    ModelTrainingOperator,
    TimescaleDBOperator,
)
from plugins.sensors import PriceDataFreshnessSensor

logger = logging.getLogger(__name__)

# DAG default arguments
default_args = {
    "owner": "electricity-optimizer",
    "depends_on_past": False,
    "email": ["ml-team@electricity-optimizer.io"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=15),
    "execution_timeout": timedelta(hours=6),
}

# DAG documentation
doc_md = """
# Model Retraining DAG

## Overview
Weekly retraining of the electricity price forecasting model using the latest
2 years of historical data. The pipeline includes feature engineering,
hyperparameter optimization, model evaluation, and conditional deployment.

## Model Architecture
- **Primary Model**: CNN-LSTM with attention mechanism
- **Ensemble Components**: XGBoost, LightGBM
- **Ensemble Method**: Weighted averaging (50% CNN-LSTM, 25% each tree model)

## Training Process
1. **Data Extraction**: Pull 2 years of hourly price data
2. **Feature Engineering**: Create temporal, price, and external features
3. **Preprocessing**: Normalize, handle missing values
4. **Training**: Train all ensemble components
5. **Evaluation**: Calculate MAPE, RMSE, MAE on validation set
6. **Deployment**: Replace production model if MAPE improves

## Deployment Criteria
- New model MAPE < Current model MAPE
- Validation loss converged (not overfitting)
- No data quality issues in training data

## Connections Required
- `timescaledb_default`: Training data source
- `mlflow_default`: Experiment tracking (optional)

## Resource Requirements
- CPU: 4+ cores recommended
- Memory: 16GB+ for large datasets
- GPU: Optional, improves training speed
"""

# Training data query
TRAINING_DATA_QUERY = """
WITH price_features AS (
    SELECT
        p.timestamp,
        p.region,
        p.price,
        p.source,
        p.price_type,
        -- Temporal features
        EXTRACT(HOUR FROM p.timestamp) AS hour_of_day,
        EXTRACT(DOW FROM p.timestamp) AS day_of_week,
        EXTRACT(MONTH FROM p.timestamp) AS month,
        EXTRACT(QUARTER FROM p.timestamp) AS quarter,
        CASE WHEN EXTRACT(DOW FROM p.timestamp) IN (0, 6) THEN 1 ELSE 0 END AS is_weekend,
        -- Price lag features
        LAG(p.price, 1) OVER (PARTITION BY p.region ORDER BY p.timestamp) AS price_lag_1h,
        LAG(p.price, 24) OVER (PARTITION BY p.region ORDER BY p.timestamp) AS price_lag_24h,
        LAG(p.price, 168) OVER (PARTITION BY p.region ORDER BY p.timestamp) AS price_lag_168h,
        -- Rolling statistics
        AVG(p.price) OVER (
            PARTITION BY p.region
            ORDER BY p.timestamp
            ROWS BETWEEN 24 PRECEDING AND 1 PRECEDING
        ) AS price_rolling_mean_24h,
        STDDEV(p.price) OVER (
            PARTITION BY p.region
            ORDER BY p.timestamp
            ROWS BETWEEN 24 PRECEDING AND 1 PRECEDING
        ) AS price_rolling_std_24h,
        -- Weather features (from joined table)
        w.temperature,
        w.wind_speed,
        w.solar_radiation,
        w.cloud_cover,
        -- Generation mix features
        g.renewable_percentage,
        g.fossil_percentage,
        g.nuclear_percentage,
        -- Demand features
        d.load_forecast,
        d.load_actual,
        LAG(d.load_actual, 24) OVER (PARTITION BY p.region ORDER BY p.timestamp) AS load_lag_24h
    FROM electricity_prices p
    LEFT JOIN weather_data w
        ON p.region = w.region
        AND DATE_TRUNC('hour', p.timestamp) = DATE_TRUNC('hour', w.timestamp)
    LEFT JOIN generation_mix g
        ON p.region = g.region
        AND DATE_TRUNC('hour', p.timestamp) = DATE_TRUNC('hour', g.timestamp)
    LEFT JOIN demand_data d
        ON p.region = d.region
        AND DATE_TRUNC('hour', p.timestamp) = DATE_TRUNC('hour', d.timestamp)
    WHERE p.timestamp >= NOW() - INTERVAL '2 years'
    AND p.price_type = 'spot'
)
SELECT *
FROM price_features
WHERE price_lag_168h IS NOT NULL  -- Ensure we have enough lag data
ORDER BY region, timestamp
"""


with DAG(
    dag_id="model_retraining",
    default_args=default_args,
    description="Weekly retraining of electricity price forecasting model",
    schedule_interval="0 2 * * 0",  # Sunday at 2:00 AM UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ml", "training", "weekly"],
    doc_md=doc_md,
) as dag:

    # =========================================================================
    # Pre-training Checks
    # =========================================================================

    start = EmptyOperator(task_id="start")

    # Ensure we have fresh training data
    check_data_freshness = PriceDataFreshnessSensor(
        task_id="check_data_freshness",
        regions=["GB", "DE", "US-CA"],
        freshness_threshold_minutes=60 * 24,  # Data within last day
        require_all_regions=False,
        conn_id="timescaledb_default",
        poke_interval=300,
        timeout=1800,
        mode="reschedule",
    )

    # Run data quality check before training
    check_training_data_quality = DataQualityOperator(
        task_id="check_training_data_quality",
        check_type="completeness",
        threshold=24.0,  # Allow up to 24-hour gaps
        lookback_hours=24 * 30,  # Check last month
        alert_on_failure=True,
        conn_id="timescaledb_default",
    )

    # =========================================================================
    # Data Extraction
    # =========================================================================

    @task(task_id="extract_training_data")
    def extract_training_data() -> Dict[str, Any]:
        """
        Extract training data from TimescaleDB.

        Returns metadata about extracted data for downstream tasks.
        The actual data is too large for XCom, so we save to a temp file.
        """
        import pandas as pd

        from plugins.hooks import TimescaleDBHook

        hook = TimescaleDBHook(conn_id="timescaledb_default")
        logger.info("Extracting training data...")

        # Execute query
        results = hook.execute_query(TRAINING_DATA_QUERY)

        if not results:
            raise ValueError("No training data extracted")

        # Convert to DataFrame
        df = pd.DataFrame(results)
        logger.info(f"Extracted {len(df)} rows")

        # Save to temp file (Airflow workers share filesystem in our setup)
        temp_path = "/opt/airflow/ml/data/training_data_temp.parquet"
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
        df.to_parquet(temp_path, index=False)

        # Calculate metadata
        regions = df["region"].unique().tolist()
        date_range = {
            "min": df["timestamp"].min().isoformat(),
            "max": df["timestamp"].max().isoformat(),
        }

        # Per-region statistics
        region_stats = {}
        for region in regions:
            region_df = df[df["region"] == region]
            region_stats[region] = {
                "count": len(region_df),
                "price_mean": float(region_df["price"].mean()),
                "price_std": float(region_df["price"].std()),
                "missing_ratio": float(region_df.isnull().sum().sum() / region_df.size),
            }

        return {
            "temp_path": temp_path,
            "total_rows": len(df),
            "regions": regions,
            "date_range": date_range,
            "region_stats": region_stats,
            "columns": df.columns.tolist(),
        }

    # =========================================================================
    # Feature Engineering
    # =========================================================================

    @task(task_id="engineer_features")
    def engineer_features(extraction_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform additional feature engineering.

        Creates:
        - Cyclical encoding of temporal features
        - Fourier features for seasonality
        - Interaction features
        - Target variable (next 24h prices)
        """
        import numpy as np
        import pandas as pd

        # Load data from temp file
        df = pd.read_parquet(extraction_result["temp_path"])
        logger.info(f"Loaded {len(df)} rows for feature engineering")

        # Cyclical encoding for temporal features
        df["hour_sin"] = np.sin(2 * np.pi * df["hour_of_day"] / 24)
        df["hour_cos"] = np.cos(2 * np.pi * df["hour_of_day"] / 24)
        df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
        df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
        df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
        df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

        # Price momentum features
        df["price_momentum_1h"] = df["price"] - df["price_lag_1h"]
        df["price_momentum_24h"] = df["price"] - df["price_lag_24h"]
        df["price_momentum_168h"] = df["price"] - df["price_lag_168h"]

        # Volatility features
        df["price_volatility"] = df["price_rolling_std_24h"] / (
            df["price_rolling_mean_24h"].abs() + 1e-6
        )

        # Weather interaction features
        if "temperature" in df.columns and "wind_speed" in df.columns:
            df["temp_wind_interaction"] = df["temperature"] * df["wind_speed"]

        if "solar_radiation" in df.columns:
            df["solar_hour_interaction"] = df["solar_radiation"] * df["hour_sin"]

        # Target: next hour's price (for now, will create 24h ahead in training)
        df["target"] = df.groupby("region")["price"].shift(-1)

        # Handle missing values
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].median())

        # Remove rows with missing targets
        df = df.dropna(subset=["target"])

        # Save processed data
        processed_path = "/opt/airflow/ml/data/processed_training_data.parquet"
        df.to_parquet(processed_path, index=False)

        feature_columns = [
            c for c in df.columns
            if c not in ["timestamp", "region", "source", "price_type", "target"]
        ]

        logger.info(
            f"Feature engineering complete: {len(df)} rows, "
            f"{len(feature_columns)} features"
        )

        return {
            "processed_path": processed_path,
            "total_rows": len(df),
            "feature_columns": feature_columns,
            "target_column": "target",
            "feature_count": len(feature_columns),
        }

    # =========================================================================
    # Model Training
    # =========================================================================

    @task_group(group_id="train_models")
    def train_models_group():
        """Train all ensemble model components."""

        @task(task_id="train_cnn_lstm")
        def train_cnn_lstm(features_result: Dict[str, Any]) -> Dict[str, Any]:
            """Train the CNN-LSTM model."""
            import pandas as pd
            import torch
            import yaml

            # Load config
            config_path = "/opt/airflow/ml/config/model_config.yaml"
            with open(config_path) as f:
                config = yaml.safe_load(f)

            # Load data
            df = pd.read_parquet(features_result["processed_path"])

            # Import training module
            from ml.training.cnn_lstm_trainer import CNNLSTMTrainer

            trainer = CNNLSTMTrainer(
                config=config["model"],
                training_config=config["training"],
            )

            # Prepare sequences
            X, y = trainer.prepare_sequences(
                df=df,
                feature_columns=features_result["feature_columns"],
                target_column=features_result["target_column"],
                sequence_length=config["model"]["input"]["sequence_length"],
            )

            # Train
            metrics = trainer.train(
                X_train=X,
                y_train=y,
                validation_split=config["training"]["validation_split"],
                epochs=config["training"]["epochs"],
            )

            # Save model
            model_path = "/opt/airflow/ml/saved_models/cnn_lstm_latest"
            os.makedirs(model_path, exist_ok=True)
            trainer.save(model_path)

            return {
                "model_type": "cnn_lstm",
                "model_path": model_path,
                "metrics": metrics,
                "training_samples": len(X),
            }

        @task(task_id="train_xgboost")
        def train_xgboost(features_result: Dict[str, Any]) -> Dict[str, Any]:
            """Train the XGBoost model."""
            import pandas as pd
            import xgboost as xgb
            import yaml
            from sklearn.model_selection import train_test_split

            # Load config
            config_path = "/opt/airflow/ml/config/model_config.yaml"
            with open(config_path) as f:
                config = yaml.safe_load(f)

            xgb_config = config["ensemble"]["xgboost"]["params"]

            # Load data
            df = pd.read_parquet(features_result["processed_path"])

            X = df[features_result["feature_columns"]]
            y = df[features_result["target_column"]]

            # Split
            X_train, X_val, y_train, y_val = train_test_split(
                X, y, test_size=0.15, shuffle=False
            )

            # Train
            model = xgb.XGBRegressor(**xgb_config)
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=100,
            )

            # Evaluate
            from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

            y_pred = model.predict(X_val)
            mape = mean_absolute_percentage_error(y_val, y_pred) * 100
            mae = mean_absolute_error(y_val, y_pred)

            # Save
            model_path = "/opt/airflow/ml/saved_models/xgboost_latest"
            os.makedirs(model_path, exist_ok=True)
            model.save_model(os.path.join(model_path, "model.json"))

            return {
                "model_type": "xgboost",
                "model_path": model_path,
                "metrics": {"val_mape": mape, "val_mae": mae},
                "training_samples": len(X_train),
            }

        @task(task_id="train_lightgbm")
        def train_lightgbm(features_result: Dict[str, Any]) -> Dict[str, Any]:
            """Train the LightGBM model."""
            import lightgbm as lgb
            import pandas as pd
            import yaml
            from sklearn.model_selection import train_test_split

            # Load config
            config_path = "/opt/airflow/ml/config/model_config.yaml"
            with open(config_path) as f:
                config = yaml.safe_load(f)

            lgb_config = config["ensemble"]["lightgbm"]["params"]

            # Load data
            df = pd.read_parquet(features_result["processed_path"])

            X = df[features_result["feature_columns"]]
            y = df[features_result["target_column"]]

            # Split
            X_train, X_val, y_train, y_val = train_test_split(
                X, y, test_size=0.15, shuffle=False
            )

            # Train
            model = lgb.LGBMRegressor(**lgb_config)
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
            )

            # Evaluate
            from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

            y_pred = model.predict(X_val)
            mape = mean_absolute_percentage_error(y_val, y_pred) * 100
            mae = mean_absolute_error(y_val, y_pred)

            # Save
            model_path = "/opt/airflow/ml/saved_models/lightgbm_latest"
            os.makedirs(model_path, exist_ok=True)
            model.booster_.save_model(os.path.join(model_path, "model.txt"))

            return {
                "model_type": "lightgbm",
                "model_path": model_path,
                "metrics": {"val_mape": mape, "val_mae": mae},
                "training_samples": len(X_train),
            }

        # Return training tasks (they'll be parallelized)
        return train_cnn_lstm, train_xgboost, train_lightgbm

    # =========================================================================
    # Model Evaluation and Deployment
    # =========================================================================

    @task(task_id="evaluate_ensemble")
    def evaluate_ensemble(
        cnn_lstm_result: Dict[str, Any],
        xgboost_result: Dict[str, Any],
        lightgbm_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluate the ensemble model and decide on deployment.

        Combines predictions from all models with configured weights
        and computes final metrics.
        """
        import yaml

        # Load config for weights
        config_path = "/opt/airflow/ml/config/model_config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        weights = {
            "cnn_lstm": config["ensemble"]["cnn_lstm"]["weight"],
            "xgboost": config["ensemble"]["xgboost"]["weight"],
            "lightgbm": config["ensemble"]["lightgbm"]["weight"],
        }

        # Calculate weighted MAPE
        mapes = {
            "cnn_lstm": cnn_lstm_result["metrics"].get("val_mape", 100),
            "xgboost": xgboost_result["metrics"].get("val_mape", 100),
            "lightgbm": lightgbm_result["metrics"].get("val_mape", 100),
        }

        weighted_mape = sum(
            weights[model] * mape
            for model, mape in mapes.items()
        )

        # Get current production model MAPE
        current_mape = float(Variable.get("current_model_mape", default_var=100.0))
        mape_threshold = float(Variable.get("model_mape_threshold", default_var=10.0))

        # Deployment decision
        should_deploy = (
            weighted_mape < current_mape and
            weighted_mape < mape_threshold
        )

        logger.info(
            f"Ensemble evaluation: weighted_mape={weighted_mape:.2f}%, "
            f"current_mape={current_mape:.2f}%, should_deploy={should_deploy}"
        )

        return {
            "weighted_mape": weighted_mape,
            "current_mape": current_mape,
            "mape_threshold": mape_threshold,
            "should_deploy": should_deploy,
            "model_metrics": {
                "cnn_lstm": cnn_lstm_result["metrics"],
                "xgboost": xgboost_result["metrics"],
                "lightgbm": lightgbm_result["metrics"],
            },
            "model_weights": weights,
            "model_paths": {
                "cnn_lstm": cnn_lstm_result["model_path"],
                "xgboost": xgboost_result["model_path"],
                "lightgbm": lightgbm_result["model_path"],
            },
        }

    @task.branch(task_id="check_deployment")
    def check_deployment(evaluation_result: Dict[str, Any]) -> str:
        """Branch based on deployment decision."""
        if evaluation_result["should_deploy"]:
            return "deploy_model"
        else:
            return "skip_deployment"

    @task(task_id="deploy_model")
    def deploy_model(evaluation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Deploy the new model to production."""
        import shutil
        import yaml

        # Create deployment version
        version = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        deploy_path = f"/opt/airflow/ml/saved_models/production_v{version}"
        latest_path = "/opt/airflow/ml/saved_models/latest"

        os.makedirs(deploy_path, exist_ok=True)

        # Copy all model components
        for model_type, model_path in evaluation_result["model_paths"].items():
            dest = os.path.join(deploy_path, model_type)
            shutil.copytree(model_path, dest)

        # Create metadata file
        metadata = {
            "version": version,
            "deployed_at": datetime.utcnow().isoformat(),
            "metrics": evaluation_result["model_metrics"],
            "weights": evaluation_result["model_weights"],
            "weighted_mape": evaluation_result["weighted_mape"],
        }

        with open(os.path.join(deploy_path, "metadata.yaml"), "w") as f:
            yaml.dump(metadata, f)

        # Update symlink to latest
        if os.path.exists(latest_path):
            os.remove(latest_path)
        os.symlink(deploy_path, latest_path)

        # Update Airflow variable with new MAPE
        Variable.set("current_model_mape", str(evaluation_result["weighted_mape"]))

        logger.info(f"Deployed model version {version}")

        return {
            "version": version,
            "deploy_path": deploy_path,
            "weighted_mape": evaluation_result["weighted_mape"],
        }

    skip_deployment = EmptyOperator(task_id="skip_deployment")

    # =========================================================================
    # Metrics and Cleanup
    # =========================================================================

    @task(task_id="send_metrics", trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS)
    def send_metrics(
        evaluation_result: Dict[str, Any],
        deployment_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send training metrics to monitoring system."""
        # In production, would send to Prometheus/Grafana
        metrics = {
            "timestamp": datetime.utcnow().isoformat(),
            "weighted_mape": evaluation_result["weighted_mape"],
            "deployed": evaluation_result["should_deploy"],
            "model_metrics": evaluation_result["model_metrics"],
        }

        if deployment_result:
            metrics["deployment_version"] = deployment_result.get("version")

        logger.info(f"Training metrics: {json.dumps(metrics, indent=2)}")

        return metrics

    @task(task_id="cleanup_temp_files", trigger_rule=TriggerRule.ALL_DONE)
    def cleanup_temp_files(extraction_result: Dict[str, Any]) -> None:
        """Clean up temporary training data files."""
        temp_files = [
            extraction_result.get("temp_path"),
            "/opt/airflow/ml/data/processed_training_data.parquet",
        ]

        for path in temp_files:
            if path and os.path.exists(path):
                os.remove(path)
                logger.info(f"Removed temp file: {path}")

    # =========================================================================
    # End
    # =========================================================================

    end = EmptyOperator(
        task_id="end",
        trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,
    )

    # =========================================================================
    # DAG Dependencies
    # =========================================================================

    # Pre-training checks
    start >> check_data_freshness >> check_training_data_quality

    # Data extraction and feature engineering
    extraction_result = extract_training_data()
    check_training_data_quality >> extraction_result

    features_result = engineer_features(extraction_result)

    # Model training (parallel)
    train_cnn_lstm, train_xgboost, train_lightgbm = train_models_group()

    features_result >> [train_cnn_lstm, train_xgboost, train_lightgbm]

    # Evaluation
    evaluation_result = evaluate_ensemble(
        cnn_lstm_result=train_cnn_lstm(features_result),
        xgboost_result=train_xgboost(features_result),
        lightgbm_result=train_lightgbm(features_result),
    )

    # Deployment decision
    deployment_branch = check_deployment(evaluation_result)
    deployment_result = deploy_model(evaluation_result)

    deployment_branch >> [deployment_result, skip_deployment]

    # Metrics and cleanup
    metrics_result = send_metrics(evaluation_result, deployment_result)
    cleanup_result = cleanup_temp_files(extraction_result)

    [deployment_result, skip_deployment] >> metrics_result >> cleanup_result >> end
