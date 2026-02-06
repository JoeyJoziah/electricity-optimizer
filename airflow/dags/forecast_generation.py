"""
Forecast Generation DAG

Schedule: Hourly
Purpose: Generate 24-hour electricity price forecasts using trained models

Features:
- Load latest production model
- Prepare real-time features from recent price data
- Generate point forecasts with confidence intervals
- Store predictions in TimescaleDB
- Update Redis cache for fast API access

SLA: Complete within 2 minutes
Retry: 2 times with 30-second delay
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from airflow import DAG
from airflow.decorators import task, task_group
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
from airflow.utils.trigger_rule import TriggerRule

from plugins.custom_operators import (
    ForecastGenerationOperator,
    RedisCacheOperator,
    TimescaleDBOperator,
)
from plugins.sensors import ForecastStaleSensor, ModelReadySensor

logger = logging.getLogger(__name__)

# DAG default arguments
default_args = {
    "owner": "electricity-optimizer",
    "depends_on_past": False,
    "email": ["alerts@electricity-optimizer.io"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(seconds=30),
    "execution_timeout": timedelta(minutes=2),
    "sla": timedelta(minutes=2),
}

# DAG documentation
doc_md = """
# Forecast Generation DAG

## Overview
Generates 24-hour ahead electricity price forecasts every hour using the
production ensemble model. Forecasts include point estimates and 90%
confidence intervals for each hour.

## Forecast Process
1. **Model Check**: Verify production model is ready and meets accuracy threshold
2. **Feature Prep**: Extract recent price data and compute features
3. **Prediction**: Run ensemble model inference
4. **Confidence**: Calculate prediction intervals using model uncertainty
5. **Storage**: Save forecasts to TimescaleDB
6. **Cache**: Update Redis for real-time API access

## Output Format
For each region and forecast hour:
- `price_forecast`: Point estimate (EUR/MWh or USD/MWh)
- `price_lower`: 5th percentile (90% CI lower bound)
- `price_upper`: 95th percentile (90% CI upper bound)
- `confidence_level`: 0.9
- `horizon_hours`: 1-24

## Connections Required
- `timescaledb_default`: Feature data and forecast storage
- `redis_default`: Cache for API access

## Performance Requirements
- Total DAG duration: < 2 minutes
- Inference latency: < 1 second per region
- Cache update: < 10 seconds
"""

# Regions to forecast
FORECAST_REGIONS = ["GB", "DE", "FR", "ES", "IT", "NL", "US-CA", "US-TX", "US-NY"]

# Feature extraction query
FEATURE_QUERY = """
WITH recent_prices AS (
    SELECT
        timestamp,
        region,
        price,
        price_type,
        source,
        ROW_NUMBER() OVER (PARTITION BY region ORDER BY timestamp DESC) as rn
    FROM electricity_prices
    WHERE region = %(region)s
    AND timestamp >= NOW() - INTERVAL '8 days'
    AND price_type = 'spot'
),
price_features AS (
    SELECT
        rp.timestamp,
        rp.region,
        rp.price,
        -- Temporal features
        EXTRACT(HOUR FROM rp.timestamp) AS hour_of_day,
        EXTRACT(DOW FROM rp.timestamp) AS day_of_week,
        EXTRACT(MONTH FROM rp.timestamp) AS month,
        CASE WHEN EXTRACT(DOW FROM rp.timestamp) IN (0, 6) THEN 1 ELSE 0 END AS is_weekend,
        -- Price lag features
        LAG(rp.price, 1) OVER (ORDER BY rp.timestamp) AS price_lag_1h,
        LAG(rp.price, 24) OVER (ORDER BY rp.timestamp) AS price_lag_24h,
        LAG(rp.price, 168) OVER (ORDER BY rp.timestamp) AS price_lag_168h,
        -- Rolling statistics (computed in window)
        AVG(rp.price) OVER (ORDER BY rp.timestamp ROWS BETWEEN 24 PRECEDING AND 1 PRECEDING) AS price_rolling_mean_24h,
        STDDEV(rp.price) OVER (ORDER BY rp.timestamp ROWS BETWEEN 24 PRECEDING AND 1 PRECEDING) AS price_rolling_std_24h,
        -- Weather features
        COALESCE(w.temperature, 15.0) AS temperature,
        COALESCE(w.wind_speed, 5.0) AS wind_speed,
        COALESCE(w.solar_radiation, 200.0) AS solar_radiation,
        COALESCE(w.cloud_cover, 50.0) AS cloud_cover,
        -- Generation features
        COALESCE(g.renewable_percentage, 30.0) AS renewable_percentage,
        COALESCE(g.fossil_percentage, 50.0) AS fossil_percentage,
        -- Demand features
        COALESCE(d.load_forecast, 50000) AS load_forecast
    FROM recent_prices rp
    LEFT JOIN weather_data w
        ON rp.region = w.region
        AND DATE_TRUNC('hour', rp.timestamp) = DATE_TRUNC('hour', w.timestamp)
    LEFT JOIN generation_mix g
        ON rp.region = g.region
        AND DATE_TRUNC('hour', rp.timestamp) = DATE_TRUNC('hour', g.timestamp)
    LEFT JOIN demand_data d
        ON rp.region = d.region
        AND DATE_TRUNC('hour', rp.timestamp) = DATE_TRUNC('hour', d.timestamp)
    WHERE rp.rn <= 168  -- Last 7 days (sequence length)
)
SELECT *
FROM price_features
ORDER BY timestamp ASC
"""


with DAG(
    dag_id="forecast_generation",
    default_args=default_args,
    description="Generate hourly electricity price forecasts",
    schedule_interval="0 * * * *",  # Every hour at minute 0
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["forecasts", "inference", "core"],
    doc_md=doc_md,
) as dag:

    # =========================================================================
    # Pre-flight Checks
    # =========================================================================

    start = EmptyOperator(task_id="start")

    # Check if model is ready
    check_model_ready = ModelReadySensor(
        task_id="check_model_ready",
        model_path="/opt/airflow/ml/saved_models/latest",
        min_accuracy_mape=15.0,
        max_age_days=14,
        conn_id="timescaledb_default",
        poke_interval=30,
        timeout=300,
        mode="reschedule",
    )

    # =========================================================================
    # Feature Preparation
    # =========================================================================

    @task(task_id="prepare_features")
    def prepare_features() -> Dict[str, Any]:
        """
        Prepare features for all regions.

        Fetches recent price data and computes derived features
        required for model inference.
        """
        import numpy as np
        import pandas as pd

        from plugins.hooks import TimescaleDBHook

        hook = TimescaleDBHook(conn_id="timescaledb_default")

        all_features = {}
        errors = []

        for region in FORECAST_REGIONS:
            try:
                # Execute query with region parameter
                query = FEATURE_QUERY
                results = hook.execute_query(query, (region,))

                if not results or len(results) < 24:
                    logger.warning(
                        f"Insufficient data for {region}: {len(results) if results else 0} rows"
                    )
                    errors.append({
                        "region": region,
                        "error": "insufficient_data",
                        "rows": len(results) if results else 0,
                    })
                    continue

                df = pd.DataFrame(results)

                # Add cyclical features
                df["hour_sin"] = np.sin(2 * np.pi * df["hour_of_day"] / 24)
                df["hour_cos"] = np.cos(2 * np.pi * df["hour_of_day"] / 24)
                df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
                df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
                df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
                df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

                # Add momentum features
                df["price_momentum_1h"] = df["price"] - df["price_lag_1h"]
                df["price_momentum_24h"] = df["price"] - df["price_lag_24h"]

                # Handle missing values
                df = df.fillna(method="ffill").fillna(method="bfill")

                # Convert to list for XCom (limited size)
                all_features[region] = {
                    "data": df.tail(168).to_dict(orient="records"),  # Last 7 days
                    "row_count": len(df),
                    "latest_timestamp": df["timestamp"].max().isoformat(),
                }

                logger.info(f"Prepared {len(df)} feature rows for {region}")

            except Exception as e:
                logger.error(f"Feature preparation failed for {region}: {e}")
                errors.append({
                    "region": region,
                    "error": str(e),
                })

        return {
            "features": all_features,
            "regions_prepared": list(all_features.keys()),
            "errors": errors,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # =========================================================================
    # Forecast Generation
    # =========================================================================

    @task(task_id="generate_forecasts")
    def generate_forecasts(feature_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate forecasts for all regions using ensemble model.

        Uses weighted ensemble of CNN-LSTM, XGBoost, and LightGBM models.
        Calculates confidence intervals using prediction variance.
        """
        import numpy as np
        import pandas as pd
        import yaml

        features = feature_data.get("features", {})
        if not features:
            raise ValueError("No features available for forecasting")

        # Load model config
        config_path = "/opt/airflow/ml/config/model_config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Load ensemble model
        from ml.inference.ensemble_predictor import EnsemblePredictor

        predictor = EnsemblePredictor(
            model_path="/opt/airflow/ml/saved_models/latest",
            weights=config["ensemble"],
        )

        all_forecasts = []
        forecast_metadata = {}

        for region, region_data in features.items():
            try:
                df = pd.DataFrame(region_data["data"])

                # Generate predictions
                predictions = predictor.predict(
                    df,
                    horizon=24,
                    confidence_level=0.9,
                    return_components=True,
                )

                # Format forecasts
                forecast_start = datetime.utcnow().replace(
                    minute=0, second=0, microsecond=0
                ) + timedelta(hours=1)

                for i in range(24):
                    forecast_time = forecast_start + timedelta(hours=i)
                    all_forecasts.append({
                        "region": region,
                        "forecast_time": forecast_time.isoformat(),
                        "generated_at": datetime.utcnow().isoformat(),
                        "price_forecast": float(predictions["point"][i]),
                        "price_lower": float(predictions["lower"][i]),
                        "price_upper": float(predictions["upper"][i]),
                        "confidence_level": 0.9,
                        "horizon_hours": i + 1,
                        "model_version": predictor.version,
                        # Component predictions for debugging
                        "cnn_lstm_pred": float(predictions["components"]["cnn_lstm"][i]),
                        "xgboost_pred": float(predictions["components"]["xgboost"][i]),
                        "lightgbm_pred": float(predictions["components"]["lightgbm"][i]),
                    })

                forecast_metadata[region] = {
                    "mean_forecast": float(np.mean(predictions["point"])),
                    "min_forecast": float(np.min(predictions["point"])),
                    "max_forecast": float(np.max(predictions["point"])),
                    "mean_uncertainty": float(
                        np.mean(predictions["upper"] - predictions["lower"])
                    ),
                }

                logger.info(f"Generated 24h forecast for {region}")

            except Exception as e:
                logger.error(f"Forecast generation failed for {region}: {e}")
                continue

        logger.info(f"Generated {len(all_forecasts)} total forecasts")

        return {
            "forecasts": all_forecasts,
            "count": len(all_forecasts),
            "regions": list(forecast_metadata.keys()),
            "metadata": forecast_metadata,
            "model_version": predictor.version,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # =========================================================================
    # Storage and Caching
    # =========================================================================

    @task(task_id="store_forecasts")
    def store_forecasts(forecast_data: Dict[str, Any]) -> Dict[str, int]:
        """Store forecasts in TimescaleDB."""
        from plugins.hooks import TimescaleDBHook

        forecasts = forecast_data.get("forecasts", [])
        if not forecasts:
            logger.warning("No forecasts to store")
            return {"inserted": 0}

        hook = TimescaleDBHook(conn_id="timescaledb_default")

        # Prepare data for insertion (remove component predictions for storage)
        storage_data = [
            {
                "region": f["region"],
                "forecast_time": f["forecast_time"],
                "generated_at": f["generated_at"],
                "price_forecast": f["price_forecast"],
                "price_lower": f["price_lower"],
                "price_upper": f["price_upper"],
                "confidence_level": f["confidence_level"],
                "horizon_hours": f["horizon_hours"],
                "model_version": f["model_version"],
            }
            for f in forecasts
        ]

        # Upsert to handle re-runs
        result = hook.upsert_many(
            table="forecasts",
            data=storage_data,
            conflict_columns=["region", "forecast_time", "horizon_hours"],
        )

        logger.info(f"Stored {result['inserted']} forecasts in TimescaleDB")
        return result

    @task(task_id="update_forecast_cache")
    def update_forecast_cache(forecast_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update Redis cache with latest forecasts."""
        from plugins.hooks import RedisHook

        forecasts = forecast_data.get("forecasts", [])
        if not forecasts:
            return {"keys_updated": 0}

        hook = RedisHook(conn_id="redis_default")

        # Group forecasts by region
        by_region: Dict[str, List] = {}
        for f in forecasts:
            region = f["region"]
            if region not in by_region:
                by_region[region] = []
            by_region[region].append(f)

        keys_updated = 0
        ttl = 3900  # 65 minutes (slightly longer than hourly refresh)

        for region, region_forecasts in by_region.items():
            # Sort by horizon
            region_forecasts.sort(key=lambda x: x["horizon_hours"])

            # Store full forecast array
            summary_key = f"forecast:summary:{region}"
            hook.set_json(summary_key, region_forecasts, ttl=ttl)
            keys_updated += 1

            # Store individual hour forecasts for quick lookup
            for f in region_forecasts:
                hour_key = f"forecast:{region}:{f['horizon_hours']}h"
                hook.set_json(hour_key, f, ttl=ttl)
                keys_updated += 1

            # Store latest forecast metadata
            meta_key = f"forecast:meta:{region}"
            meta = {
                "generated_at": forecast_data["timestamp"],
                "model_version": forecast_data["model_version"],
                "forecast_count": len(region_forecasts),
                "mean_price": sum(f["price_forecast"] for f in region_forecasts) / len(region_forecasts),
            }
            hook.set_json(meta_key, meta, ttl=ttl)
            keys_updated += 1

        logger.info(f"Updated {keys_updated} cache keys")

        return {
            "keys_updated": keys_updated,
            "regions": list(by_region.keys()),
            "ttl_seconds": ttl,
        }

    # =========================================================================
    # Quality Check
    # =========================================================================

    @task(task_id="validate_forecasts")
    def validate_forecasts(forecast_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate generated forecasts for reasonableness.

        Checks:
        - All regions have forecasts
        - Price ranges are reasonable
        - Confidence intervals are not too wide
        """
        forecasts = forecast_data.get("forecasts", [])
        issues = []

        # Check region coverage
        expected_regions = set(FORECAST_REGIONS)
        actual_regions = set(f["region"] for f in forecasts)
        missing_regions = expected_regions - actual_regions

        if missing_regions:
            issues.append(f"Missing regions: {missing_regions}")

        # Check price ranges (by region type)
        eu_forecasts = [f for f in forecasts if f["region"] in ["GB", "DE", "FR", "ES", "IT", "NL"]]
        us_forecasts = [f for f in forecasts if f["region"].startswith("US-")]

        # EU prices typically 20-500 EUR/MWh
        for f in eu_forecasts:
            if f["price_forecast"] < -100 or f["price_forecast"] > 1000:
                issues.append(f"Extreme EU forecast: {f['region']} = {f['price_forecast']}")

        # US prices typically 20-200 USD/MWh
        for f in us_forecasts:
            if f["price_forecast"] < -50 or f["price_forecast"] > 500:
                issues.append(f"Extreme US forecast: {f['region']} = {f['price_forecast']}")

        # Check confidence intervals
        for f in forecasts:
            interval_width = f["price_upper"] - f["price_lower"]
            if interval_width > f["price_forecast"] * 2:  # >200% of point estimate
                issues.append(
                    f"Wide CI for {f['region']} h{f['horizon_hours']}: "
                    f"{interval_width:.2f}"
                )

        # Limit issues list
        issues = issues[:20]

        validation_passed = len(issues) == 0

        if not validation_passed:
            logger.warning(f"Forecast validation issues: {issues}")
        else:
            logger.info("Forecast validation passed")

        return {
            "validation_passed": validation_passed,
            "issues": issues,
            "forecast_count": len(forecasts),
            "regions_covered": len(actual_regions),
        }

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

    # Pre-flight
    start >> check_model_ready

    # Feature preparation
    feature_data = prepare_features()
    check_model_ready >> feature_data

    # Forecast generation
    forecast_data = generate_forecasts(feature_data)

    # Storage and caching (parallel)
    storage_result = store_forecasts(forecast_data)
    cache_result = update_forecast_cache(forecast_data)

    forecast_data >> [storage_result, cache_result]

    # Validation
    validation_result = validate_forecasts(forecast_data)
    forecast_data >> validation_result

    # End
    [storage_result, cache_result, validation_result] >> end
