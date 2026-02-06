"""
Custom Airflow Operators for Electricity Price Optimizer

These operators encapsulate the business logic for:
- Fetching price data from multiple APIs
- Storing data in TimescaleDB
- Training ML models
- Generating forecasts
- Running data quality checks
- Managing Redis cache
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

import httpx
import numpy as np
import pandas as pd
from airflow.exceptions import AirflowException, AirflowSkipException
from airflow.models import BaseOperator
from airflow.utils.context import Context

from plugins.hooks import PricingAPIHook, RedisHook, TimescaleDBHook

logger = logging.getLogger(__name__)


class PricingAPIOperator(BaseOperator):
    """
    Fetch electricity pricing data from external APIs.

    Supports:
    - Flatpeak (UK/EU electricity prices)
    - NREL (US utility rates)
    - IEA (Global electricity statistics)

    Features:
    - Automatic retry with exponential backoff
    - Rate limiting
    - Data normalization to common schema
    - Deduplication

    :param api_source: API to fetch from ('flatpeak', 'nrel', 'iea')
    :param regions: List of regions to fetch data for
    :param start_time: Start of time range (default: 15 min ago)
    :param end_time: End of time range (default: now)
    :param conn_id: Airflow connection ID for the API
    :param rate_limit_pool: Resource pool for rate limiting
    """

    template_fields: Sequence[str] = ("regions", "start_time", "end_time")
    ui_color = "#e8f4f8"
    ui_fgcolor = "#000000"

    def __init__(
        self,
        *,
        api_source: str,
        regions: Optional[List[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        conn_id: Optional[str] = None,
        rate_limit_pool: str = "pricing_api_pool",
        timeout_seconds: int = 60,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.api_source = api_source.lower()
        self.regions = regions or self._default_regions()
        self.start_time = start_time
        self.end_time = end_time
        self.conn_id = conn_id or f"{self.api_source}_default"
        self.rate_limit_pool = rate_limit_pool
        self.timeout_seconds = timeout_seconds

    def _default_regions(self) -> List[str]:
        """Return default regions based on API source."""
        defaults = {
            "flatpeak": ["GB", "DE", "FR", "ES", "IT", "NL"],
            "nrel": ["US-CA", "US-TX", "US-NY", "US-FL"],
            "iea": ["OECD", "EU27", "USA", "CHN"],
        }
        return defaults.get(self.api_source, [])

    def execute(self, context: Context) -> Dict[str, Any]:
        """Execute the API fetch operation."""
        logger.info(
            f"Fetching {self.api_source} price data for regions: {self.regions}"
        )

        hook = PricingAPIHook(
            api_source=self.api_source,
            conn_id=self.conn_id,
        )

        # Calculate time range
        execution_date = context["execution_date"]
        end_dt = datetime.fromisoformat(self.end_time) if self.end_time else execution_date
        start_dt = (
            datetime.fromisoformat(self.start_time)
            if self.start_time
            else end_dt - timedelta(minutes=15)
        )

        all_prices = []
        errors = []

        for region in self.regions:
            try:
                logger.info(f"Fetching {region} from {self.api_source}")
                prices = hook.get_prices(
                    region=region,
                    start_time=start_dt,
                    end_time=end_dt,
                    timeout=self.timeout_seconds,
                )
                all_prices.extend(prices)
                logger.info(f"Retrieved {len(prices)} records for {region}")
            except Exception as e:
                error_msg = f"Failed to fetch {region}: {str(e)}"
                logger.warning(error_msg)
                errors.append({"region": region, "error": str(e)})

        if not all_prices and errors:
            raise AirflowException(
                f"All API calls failed for {self.api_source}: {errors}"
            )

        # Normalize and deduplicate
        normalized = self._normalize_prices(all_prices)
        deduped = self._deduplicate(normalized)

        result = {
            "source": self.api_source,
            "count": len(deduped),
            "regions": list(set(p["region"] for p in deduped)),
            "time_range": {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
            },
            "prices": deduped,
            "errors": errors,
        }

        logger.info(
            f"Completed {self.api_source} fetch: {len(deduped)} records from "
            f"{len(result['regions'])} regions"
        )

        return result

    def _normalize_prices(self, prices: List[Dict]) -> List[Dict]:
        """Normalize prices to common schema."""
        normalized = []
        for price in prices:
            normalized.append(
                {
                    "timestamp": price.get("timestamp"),
                    "region": price.get("region"),
                    "price": float(price.get("price", 0)),
                    "currency": price.get("currency", "EUR"),
                    "unit": price.get("unit", "EUR/MWh"),
                    "source": self.api_source,
                    "price_type": price.get("price_type", "spot"),
                    "fetched_at": datetime.utcnow().isoformat(),
                }
            )
        return normalized

    def _deduplicate(self, prices: List[Dict]) -> List[Dict]:
        """Remove duplicate price records."""
        seen = set()
        deduped = []
        for price in prices:
            key = (price["timestamp"], price["region"], price["source"])
            if key not in seen:
                seen.add(key)
                deduped.append(price)
        return deduped


class TimescaleDBOperator(BaseOperator):
    """
    Store or query data in TimescaleDB.

    Features:
    - Upsert with conflict resolution
    - Batch inserts for performance
    - Automatic hypertable handling
    - Connection pooling

    :param operation: Type of operation ('insert', 'upsert', 'query')
    :param table: Target table name
    :param data: Data to insert/upsert (can be XCom reference)
    :param query: SQL query for 'query' operation
    :param conflict_columns: Columns for upsert conflict resolution
    :param conn_id: Airflow connection ID
    :param batch_size: Batch size for bulk inserts
    """

    template_fields: Sequence[str] = ("data", "query")
    ui_color = "#f4e8f8"
    ui_fgcolor = "#000000"

    def __init__(
        self,
        *,
        operation: str,
        table: Optional[str] = None,
        data: Optional[Any] = None,
        query: Optional[str] = None,
        conflict_columns: Optional[List[str]] = None,
        conn_id: str = "timescaledb_default",
        batch_size: int = 1000,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.operation = operation.lower()
        self.table = table
        self.data = data
        self.query = query
        self.conflict_columns = conflict_columns or ["timestamp", "region", "source"]
        self.conn_id = conn_id
        self.batch_size = batch_size

        if self.operation in ("insert", "upsert") and not self.table:
            raise ValueError(f"Table required for {self.operation} operation")
        if self.operation == "query" and not self.query:
            raise ValueError("Query required for query operation")

    def execute(self, context: Context) -> Any:
        """Execute the database operation."""
        hook = TimescaleDBHook(conn_id=self.conn_id)

        if self.operation == "insert":
            return self._execute_insert(hook)
        elif self.operation == "upsert":
            return self._execute_upsert(hook)
        elif self.operation == "query":
            return self._execute_query(hook)
        else:
            raise ValueError(f"Unknown operation: {self.operation}")

    def _execute_insert(self, hook: TimescaleDBHook) -> Dict[str, int]:
        """Execute bulk insert."""
        data = self._get_data()
        if not data:
            logger.info("No data to insert")
            return {"inserted": 0}

        total_inserted = 0
        for i in range(0, len(data), self.batch_size):
            batch = data[i : i + self.batch_size]
            count = hook.insert_many(self.table, batch)
            total_inserted += count
            logger.info(f"Inserted batch {i // self.batch_size + 1}: {count} rows")

        logger.info(f"Total inserted: {total_inserted} rows into {self.table}")
        return {"inserted": total_inserted}

    def _execute_upsert(self, hook: TimescaleDBHook) -> Dict[str, int]:
        """Execute bulk upsert with conflict resolution."""
        data = self._get_data()
        if not data:
            logger.info("No data to upsert")
            return {"upserted": 0, "updated": 0}

        total_upserted = 0
        total_updated = 0

        for i in range(0, len(data), self.batch_size):
            batch = data[i : i + self.batch_size]
            result = hook.upsert_many(
                table=self.table,
                data=batch,
                conflict_columns=self.conflict_columns,
            )
            total_upserted += result.get("inserted", 0)
            total_updated += result.get("updated", 0)

        logger.info(
            f"Upsert complete: {total_upserted} inserted, {total_updated} updated"
        )
        return {"upserted": total_upserted, "updated": total_updated}

    def _execute_query(self, hook: TimescaleDBHook) -> List[Dict]:
        """Execute query and return results."""
        logger.info(f"Executing query: {self.query[:100]}...")
        results = hook.execute_query(self.query)
        logger.info(f"Query returned {len(results)} rows")
        return results

    def _get_data(self) -> List[Dict]:
        """Get data from self.data, handling XCom references."""
        if isinstance(self.data, dict) and "prices" in self.data:
            return self.data["prices"]
        elif isinstance(self.data, list):
            return self.data
        elif self.data is None:
            return []
        else:
            return [self.data]


class ModelTrainingOperator(BaseOperator):
    """
    Train or retrain ML models for price forecasting.

    Features:
    - CNN-LSTM model training
    - Hyperparameter optimization
    - Model versioning and registry
    - Performance metrics tracking

    :param model_type: Type of model ('cnn_lstm', 'xgboost', 'ensemble')
    :param training_data_query: SQL query to fetch training data
    :param validation_split: Fraction of data for validation
    :param epochs: Maximum training epochs
    :param early_stopping_patience: Epochs to wait for improvement
    :param model_registry_path: Path to save model artifacts
    :param conn_id: TimescaleDB connection ID
    """

    template_fields: Sequence[str] = ("training_data_query",)
    ui_color = "#f8f4e8"
    ui_fgcolor = "#000000"

    def __init__(
        self,
        *,
        model_type: str = "ensemble",
        training_data_query: Optional[str] = None,
        validation_split: float = 0.15,
        epochs: int = 200,
        early_stopping_patience: int = 20,
        model_registry_path: str = "/opt/airflow/ml/saved_models",
        conn_id: str = "timescaledb_default",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.model_type = model_type
        self.training_data_query = training_data_query or self._default_query()
        self.validation_split = validation_split
        self.epochs = epochs
        self.early_stopping_patience = early_stopping_patience
        self.model_registry_path = model_registry_path
        self.conn_id = conn_id

    def _default_query(self) -> str:
        """Default query for training data (last 2 years)."""
        return """
            SELECT
                timestamp,
                region,
                price,
                price_type,
                hour_of_day,
                day_of_week,
                month,
                is_weekend,
                temperature,
                wind_speed,
                solar_radiation,
                load_forecast,
                renewable_percentage
            FROM price_data_features
            WHERE timestamp >= NOW() - INTERVAL '2 years'
            ORDER BY timestamp ASC
        """

    def execute(self, context: Context) -> Dict[str, Any]:
        """Execute model training."""
        import torch
        import yaml

        from ml.training.trainer import ModelTrainer

        logger.info(f"Starting {self.model_type} model training")

        # Load training data
        hook = TimescaleDBHook(conn_id=self.conn_id)
        data = hook.execute_query(self.training_data_query)

        if not data or len(data) < 8760:  # Minimum 1 year of hourly data
            raise AirflowException(
                f"Insufficient training data: {len(data) if data else 0} rows "
                f"(minimum: 8760)"
            )

        logger.info(f"Loaded {len(data)} training samples")

        # Convert to DataFrame
        df = pd.DataFrame(data)

        # Load model configuration
        config_path = "/opt/airflow/ml/config/model_config.yaml"
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        # Initialize trainer
        trainer = ModelTrainer(
            model_type=self.model_type,
            config=config,
            validation_split=self.validation_split,
            epochs=self.epochs,
            early_stopping_patience=self.early_stopping_patience,
        )

        # Train model
        training_start = datetime.utcnow()
        metrics = trainer.train(df)
        training_duration = (datetime.utcnow() - training_start).total_seconds()

        # Save model
        model_version = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        model_path = f"{self.model_registry_path}/{self.model_type}_{model_version}"
        trainer.save_model(model_path)

        result = {
            "model_type": self.model_type,
            "model_version": model_version,
            "model_path": model_path,
            "training_samples": len(df),
            "training_duration_seconds": training_duration,
            "metrics": metrics,
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.info(
            f"Training complete: MAPE={metrics.get('val_mape', 'N/A'):.2f}%, "
            f"duration={training_duration:.1f}s"
        )

        return result


class ForecastGenerationOperator(BaseOperator):
    """
    Generate electricity price forecasts using trained models.

    Features:
    - 24-hour ahead forecasting
    - Confidence interval calculation
    - Multi-region batch processing
    - Ensemble model support

    :param model_path: Path to trained model
    :param forecast_horizon: Hours to forecast ahead
    :param regions: Regions to generate forecasts for
    :param feature_query: SQL query for feature data
    :param conn_id: TimescaleDB connection ID
    """

    template_fields: Sequence[str] = ("model_path", "regions", "feature_query")
    ui_color = "#e8f8e8"
    ui_fgcolor = "#000000"

    def __init__(
        self,
        *,
        model_path: Optional[str] = None,
        forecast_horizon: int = 24,
        regions: Optional[List[str]] = None,
        feature_query: Optional[str] = None,
        confidence_level: float = 0.9,
        conn_id: str = "timescaledb_default",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.model_path = model_path or "/opt/airflow/ml/saved_models/latest"
        self.forecast_horizon = forecast_horizon
        self.regions = regions or ["GB", "DE", "US-CA"]
        self.feature_query = feature_query or self._default_feature_query()
        self.confidence_level = confidence_level
        self.conn_id = conn_id

    def _default_feature_query(self) -> str:
        """Default query for forecast features."""
        return """
            SELECT *
            FROM price_features_latest
            WHERE region = %s
            ORDER BY timestamp DESC
            LIMIT 168
        """

    def execute(self, context: Context) -> Dict[str, Any]:
        """Execute forecast generation."""
        import torch

        from ml.inference.predictor import PricePredictor

        logger.info(
            f"Generating {self.forecast_horizon}h forecasts for: {self.regions}"
        )

        # Load model
        predictor = PricePredictor(model_path=self.model_path)

        # Get features for each region
        hook = TimescaleDBHook(conn_id=self.conn_id)
        all_forecasts = []

        for region in self.regions:
            try:
                # Fetch recent features
                features = hook.execute_query(self.feature_query, (region,))
                if not features:
                    logger.warning(f"No feature data for {region}, skipping")
                    continue

                df = pd.DataFrame(features)

                # Generate forecast
                forecast = predictor.predict(
                    df,
                    horizon=self.forecast_horizon,
                    confidence_level=self.confidence_level,
                )

                # Format results
                forecast_start = datetime.utcnow().replace(
                    minute=0, second=0, microsecond=0
                ) + timedelta(hours=1)

                for i, (point, lower, upper) in enumerate(
                    zip(
                        forecast["point"],
                        forecast["lower"],
                        forecast["upper"],
                    )
                ):
                    all_forecasts.append(
                        {
                            "region": region,
                            "forecast_time": (
                                forecast_start + timedelta(hours=i)
                            ).isoformat(),
                            "generated_at": datetime.utcnow().isoformat(),
                            "price_forecast": float(point),
                            "price_lower": float(lower),
                            "price_upper": float(upper),
                            "confidence_level": self.confidence_level,
                            "horizon_hours": i + 1,
                            "model_version": predictor.model_version,
                        }
                    )

                logger.info(f"Generated {len(forecast['point'])} forecasts for {region}")

            except Exception as e:
                logger.error(f"Failed to generate forecast for {region}: {e}")
                continue

        result = {
            "forecasts": all_forecasts,
            "count": len(all_forecasts),
            "regions": list(set(f["region"] for f in all_forecasts)),
            "model_version": predictor.model_version if all_forecasts else None,
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.info(f"Generated {len(all_forecasts)} total forecasts")
        return result


class DataQualityOperator(BaseOperator):
    """
    Perform data quality checks on price data.

    Checks:
    - Data completeness (no gaps > threshold)
    - Price range validation (outlier detection)
    - API response time monitoring
    - Model accuracy tracking

    :param check_type: Type of check to perform
    :param threshold: Threshold for the check
    :param lookback_hours: Hours to look back for checks
    :param alert_on_failure: Whether to raise alert on failure
    :param conn_id: TimescaleDB connection ID
    """

    template_fields: Sequence[str] = ("lookback_hours",)
    ui_color = "#f8e8e8"
    ui_fgcolor = "#000000"

    VALID_CHECK_TYPES = [
        "completeness",
        "price_range",
        "api_health",
        "model_accuracy",
        "freshness",
    ]

    def __init__(
        self,
        *,
        check_type: str,
        threshold: Optional[float] = None,
        lookback_hours: int = 24,
        alert_on_failure: bool = True,
        conn_id: str = "timescaledb_default",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if check_type not in self.VALID_CHECK_TYPES:
            raise ValueError(
                f"Invalid check_type: {check_type}. "
                f"Must be one of: {self.VALID_CHECK_TYPES}"
            )
        self.check_type = check_type
        self.threshold = threshold
        self.lookback_hours = lookback_hours
        self.alert_on_failure = alert_on_failure
        self.conn_id = conn_id

    def execute(self, context: Context) -> Dict[str, Any]:
        """Execute the data quality check."""
        hook = TimescaleDBHook(conn_id=self.conn_id)

        check_methods = {
            "completeness": self._check_completeness,
            "price_range": self._check_price_range,
            "api_health": self._check_api_health,
            "model_accuracy": self._check_model_accuracy,
            "freshness": self._check_freshness,
        }

        result = check_methods[self.check_type](hook)
        result["check_type"] = self.check_type
        result["timestamp"] = datetime.utcnow().isoformat()
        result["lookback_hours"] = self.lookback_hours

        if not result["passed"] and self.alert_on_failure:
            logger.error(f"Data quality check failed: {result}")
            # In production, would trigger alert here

        return result

    def _check_completeness(self, hook: TimescaleDBHook) -> Dict[str, Any]:
        """Check for data gaps."""
        threshold = self.threshold or 1.0  # 1 hour max gap

        query = f"""
            WITH time_gaps AS (
                SELECT
                    region,
                    timestamp,
                    LAG(timestamp) OVER (PARTITION BY region ORDER BY timestamp) as prev_timestamp,
                    EXTRACT(EPOCH FROM (timestamp - LAG(timestamp) OVER (
                        PARTITION BY region ORDER BY timestamp
                    ))) / 3600.0 as gap_hours
                FROM electricity_prices
                WHERE timestamp >= NOW() - INTERVAL '{self.lookback_hours} hours'
            )
            SELECT
                region,
                MAX(gap_hours) as max_gap_hours,
                COUNT(*) FILTER (WHERE gap_hours > {threshold}) as gaps_over_threshold
            FROM time_gaps
            WHERE gap_hours IS NOT NULL
            GROUP BY region
        """

        results = hook.execute_query(query)
        max_gap = max((r["max_gap_hours"] or 0 for r in results), default=0)
        total_gaps = sum(r["gaps_over_threshold"] or 0 for r in results)

        return {
            "passed": max_gap <= threshold and total_gaps == 0,
            "max_gap_hours": max_gap,
            "gaps_over_threshold": total_gaps,
            "threshold_hours": threshold,
            "details": results,
        }

    def _check_price_range(self, hook: TimescaleDBHook) -> Dict[str, Any]:
        """Check for price outliers."""
        std_threshold = self.threshold or 3.0  # 3 standard deviations

        query = f"""
            WITH stats AS (
                SELECT
                    region,
                    AVG(price) as mean_price,
                    STDDEV(price) as std_price
                FROM electricity_prices
                WHERE timestamp >= NOW() - INTERVAL '30 days'
                GROUP BY region
            )
            SELECT
                p.region,
                p.timestamp,
                p.price,
                s.mean_price,
                s.std_price,
                ABS(p.price - s.mean_price) / NULLIF(s.std_price, 0) as z_score
            FROM electricity_prices p
            JOIN stats s ON p.region = s.region
            WHERE p.timestamp >= NOW() - INTERVAL '{self.lookback_hours} hours'
            AND ABS(p.price - s.mean_price) / NULLIF(s.std_price, 0) > {std_threshold}
        """

        outliers = hook.execute_query(query)

        return {
            "passed": len(outliers) == 0,
            "outlier_count": len(outliers),
            "threshold_std": std_threshold,
            "outliers": outliers[:10],  # Limit to 10 for display
        }

    def _check_api_health(self, hook: TimescaleDBHook) -> Dict[str, Any]:
        """Check API response times and availability."""
        threshold_ms = self.threshold or 5000  # 5 second threshold

        query = f"""
            SELECT
                source,
                COUNT(*) as total_requests,
                COUNT(*) FILTER (WHERE success = true) as successful_requests,
                AVG(response_time_ms) as avg_response_time_ms,
                MAX(response_time_ms) as max_response_time_ms,
                COUNT(*) FILTER (WHERE response_time_ms > {threshold_ms}) as slow_requests
            FROM api_health_metrics
            WHERE timestamp >= NOW() - INTERVAL '{self.lookback_hours} hours'
            GROUP BY source
        """

        results = hook.execute_query(query)

        all_healthy = all(
            r["successful_requests"] / max(r["total_requests"], 1) >= 0.95
            and (r["avg_response_time_ms"] or 0) < threshold_ms
            for r in results
        )

        return {
            "passed": all_healthy,
            "threshold_ms": threshold_ms,
            "sources": results,
        }

    def _check_model_accuracy(self, hook: TimescaleDBHook) -> Dict[str, Any]:
        """Check if model accuracy has degraded."""
        mape_threshold = self.threshold or 10.0  # 10% MAPE threshold

        query = f"""
            WITH forecast_errors AS (
                SELECT
                    f.region,
                    f.forecast_time,
                    f.price_forecast,
                    a.price as actual_price,
                    ABS(f.price_forecast - a.price) / NULLIF(a.price, 0) * 100 as ape
                FROM forecasts f
                JOIN electricity_prices a
                    ON f.region = a.region
                    AND f.forecast_time = a.timestamp
                WHERE f.forecast_time >= NOW() - INTERVAL '{self.lookback_hours} hours'
                AND f.forecast_time <= NOW()
            )
            SELECT
                region,
                AVG(ape) as mape,
                STDDEV(ape) as std_ape,
                COUNT(*) as sample_count
            FROM forecast_errors
            GROUP BY region
        """

        results = hook.execute_query(query)

        if not results:
            return {
                "passed": True,
                "message": "No forecast data available for comparison",
                "mape_threshold": mape_threshold,
            }

        avg_mape = np.mean([r["mape"] or 0 for r in results])

        return {
            "passed": avg_mape <= mape_threshold,
            "avg_mape": avg_mape,
            "mape_threshold": mape_threshold,
            "by_region": results,
        }

    def _check_freshness(self, hook: TimescaleDBHook) -> Dict[str, Any]:
        """Check if data is fresh enough."""
        max_age_hours = self.threshold or 1.0  # 1 hour max age

        query = """
            SELECT
                source,
                region,
                MAX(timestamp) as latest_timestamp,
                EXTRACT(EPOCH FROM (NOW() - MAX(timestamp))) / 3600.0 as age_hours
            FROM electricity_prices
            GROUP BY source, region
        """

        results = hook.execute_query(query)
        stale_sources = [r for r in results if (r["age_hours"] or 999) > max_age_hours]

        return {
            "passed": len(stale_sources) == 0,
            "max_age_hours": max_age_hours,
            "stale_sources": stale_sources,
            "all_sources": results,
        }


class RedisCacheOperator(BaseOperator):
    """
    Manage Redis cache for price data and forecasts.

    Operations:
    - Invalidate stale cache entries
    - Pre-warm cache with frequently accessed data
    - Update forecast cache
    - Clear specific cache patterns

    :param operation: Cache operation ('invalidate', 'warm', 'update', 'clear')
    :param key_pattern: Redis key pattern for operation
    :param data: Data to cache (for 'update' operation)
    :param ttl_seconds: TTL for cached data
    :param conn_id: Redis connection ID
    """

    template_fields: Sequence[str] = ("key_pattern", "data")
    ui_color = "#e8e8f8"
    ui_fgcolor = "#000000"

    def __init__(
        self,
        *,
        operation: str,
        key_pattern: Optional[str] = None,
        data: Optional[Any] = None,
        ttl_seconds: int = 3600,
        conn_id: str = "redis_default",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.operation = operation.lower()
        self.key_pattern = key_pattern
        self.data = data
        self.ttl_seconds = ttl_seconds
        self.conn_id = conn_id

    def execute(self, context: Context) -> Dict[str, Any]:
        """Execute the cache operation."""
        hook = RedisHook(conn_id=self.conn_id)

        if self.operation == "invalidate":
            return self._invalidate_cache(hook)
        elif self.operation == "warm":
            return self._warm_cache(hook, context)
        elif self.operation == "update":
            return self._update_cache(hook)
        elif self.operation == "clear":
            return self._clear_cache(hook)
        else:
            raise ValueError(f"Unknown operation: {self.operation}")

    def _invalidate_cache(self, hook: RedisHook) -> Dict[str, Any]:
        """Invalidate cache entries matching pattern."""
        pattern = self.key_pattern or "price:*"
        keys_deleted = hook.delete_pattern(pattern)

        logger.info(f"Invalidated {keys_deleted} cache entries matching '{pattern}'")
        return {"pattern": pattern, "keys_deleted": keys_deleted}

    def _warm_cache(self, hook: RedisHook, context: Context) -> Dict[str, Any]:
        """Pre-warm cache with frequently accessed data."""
        # Get frequently accessed regions from XCom or default
        regions = ["GB", "DE", "FR", "US-CA", "US-TX"]

        # Fetch latest data from TimescaleDB
        ts_hook = TimescaleDBHook(conn_id="timescaledb_default")

        warmed_keys = 0
        for region in regions:
            query = f"""
                SELECT timestamp, price, source
                FROM electricity_prices
                WHERE region = '{region}'
                AND timestamp >= NOW() - INTERVAL '24 hours'
                ORDER BY timestamp DESC
            """
            data = ts_hook.execute_query(query)

            if data:
                key = f"price:latest:{region}"
                hook.set_json(key, data, ttl=self.ttl_seconds)
                warmed_keys += 1
                logger.info(f"Cached {len(data)} records for {region}")

        return {"regions": regions, "keys_warmed": warmed_keys}

    def _update_cache(self, hook: RedisHook) -> Dict[str, Any]:
        """Update cache with new data."""
        if not self.data:
            logger.warning("No data provided for cache update")
            return {"keys_updated": 0}

        # Handle forecast data
        if isinstance(self.data, dict) and "forecasts" in self.data:
            forecasts = self.data["forecasts"]
            regions_updated = set()

            for forecast in forecasts:
                region = forecast["region"]
                key = f"forecast:{region}:{forecast['horizon_hours']}h"
                hook.set_json(key, forecast, ttl=self.ttl_seconds)
                regions_updated.add(region)

            # Also update summary keys
            for region in regions_updated:
                region_forecasts = [
                    f for f in forecasts if f["region"] == region
                ]
                summary_key = f"forecast:summary:{region}"
                hook.set_json(summary_key, region_forecasts, ttl=self.ttl_seconds)

            return {
                "keys_updated": len(forecasts) + len(regions_updated),
                "regions": list(regions_updated),
            }

        # Handle price data
        if isinstance(self.data, dict) and "prices" in self.data:
            prices = self.data["prices"]
            keys_updated = 0

            # Group by region
            by_region: Dict[str, List] = {}
            for price in prices:
                region = price["region"]
                if region not in by_region:
                    by_region[region] = []
                by_region[region].append(price)

            for region, region_prices in by_region.items():
                key = f"price:latest:{region}"
                hook.set_json(key, region_prices, ttl=self.ttl_seconds)
                keys_updated += 1

            return {"keys_updated": keys_updated, "regions": list(by_region.keys())}

        return {"keys_updated": 0, "message": "Unknown data format"}

    def _clear_cache(self, hook: RedisHook) -> Dict[str, Any]:
        """Clear all cache entries matching pattern."""
        pattern = self.key_pattern or "*"
        keys_deleted = hook.delete_pattern(pattern)

        logger.info(f"Cleared {keys_deleted} cache entries matching '{pattern}'")
        return {"pattern": pattern, "keys_deleted": keys_deleted}
