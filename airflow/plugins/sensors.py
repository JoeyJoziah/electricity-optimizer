"""
Custom Airflow Sensors for Electricity Price Optimizer

These sensors provide event-driven triggers for:
- Price data freshness monitoring
- Model readiness checks
- API health verification
- Market schedule awareness
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from airflow.exceptions import AirflowException, AirflowSkipException
from airflow.sensors.base import BaseSensorOperator
from airflow.utils.context import Context

from plugins.hooks import PricingAPIHook, RedisHook, TimescaleDBHook

logger = logging.getLogger(__name__)


class PriceDataFreshnessSensor(BaseSensorOperator):
    """
    Sensor to check if price data is fresh enough for processing.

    Pokes TimescaleDB to verify that recent price data exists within
    the specified freshness threshold.

    :param regions: List of regions to check
    :param freshness_threshold_minutes: Maximum age of data in minutes
    :param require_all_regions: If True, all regions must have fresh data
    :param conn_id: TimescaleDB connection ID
    """

    template_fields: Sequence[str] = ("regions",)
    ui_color = "#c7e9c0"
    poke_context_fields = ("regions", "freshness_threshold_minutes")

    def __init__(
        self,
        *,
        regions: Optional[List[str]] = None,
        freshness_threshold_minutes: int = 30,
        require_all_regions: bool = False,
        conn_id: str = "timescaledb_default",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.regions = regions or ["GB", "DE", "US-CA"]
        self.freshness_threshold_minutes = freshness_threshold_minutes
        self.require_all_regions = require_all_regions
        self.conn_id = conn_id

    def poke(self, context: Context) -> bool:
        """Check if price data is fresh."""
        hook = TimescaleDBHook(conn_id=self.conn_id)

        regions_str = ",".join(f"'{r}'" for r in self.regions)
        query = f"""
            SELECT
                region,
                MAX(timestamp) as latest_timestamp,
                EXTRACT(EPOCH FROM (NOW() - MAX(timestamp))) / 60 as age_minutes
            FROM electricity_prices
            WHERE region IN ({regions_str})
            GROUP BY region
        """

        results = hook.execute_query(query)
        results_dict = {r["region"]: r for r in results}

        fresh_regions = []
        stale_regions = []

        for region in self.regions:
            if region not in results_dict:
                stale_regions.append(region)
                logger.info(f"Region {region}: No data found")
            elif results_dict[region]["age_minutes"] > self.freshness_threshold_minutes:
                stale_regions.append(region)
                logger.info(
                    f"Region {region}: Data is "
                    f"{results_dict[region]['age_minutes']:.1f} minutes old "
                    f"(threshold: {self.freshness_threshold_minutes} min)"
                )
            else:
                fresh_regions.append(region)
                logger.info(
                    f"Region {region}: Data is fresh "
                    f"({results_dict[region]['age_minutes']:.1f} minutes old)"
                )

        if self.require_all_regions:
            return len(stale_regions) == 0
        else:
            return len(fresh_regions) > 0


class ModelReadySensor(BaseSensorOperator):
    """
    Sensor to check if a trained model is ready for inference.

    Verifies that:
    - Model file exists at expected path
    - Model meets minimum accuracy requirements
    - Model is not too old (within retraining window)

    :param model_path: Path to model artifacts
    :param min_accuracy_mape: Minimum MAPE threshold (lower is better)
    :param max_age_days: Maximum model age in days
    :param conn_id: TimescaleDB connection ID for metrics lookup
    """

    template_fields: Sequence[str] = ("model_path",)
    ui_color = "#fdd0a2"

    def __init__(
        self,
        *,
        model_path: str = "/opt/airflow/ml/saved_models/latest",
        min_accuracy_mape: float = 15.0,
        max_age_days: int = 14,
        conn_id: str = "timescaledb_default",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.model_path = model_path
        self.min_accuracy_mape = min_accuracy_mape
        self.max_age_days = max_age_days
        self.conn_id = conn_id

    def poke(self, context: Context) -> bool:
        """Check if model is ready."""
        import os

        import torch
        import yaml

        # Check model file exists
        model_file = os.path.join(self.model_path, "model.pt")
        metadata_file = os.path.join(self.model_path, "metadata.yaml")

        if not os.path.exists(model_file):
            logger.info(f"Model file not found: {model_file}")
            return False

        if not os.path.exists(metadata_file):
            logger.warning(f"Metadata file not found: {metadata_file}")
            # Model exists but no metadata - might be OK for initial runs
            return True

        # Load metadata
        with open(metadata_file, "r") as f:
            metadata = yaml.safe_load(f)

        # Check model age
        trained_at = datetime.fromisoformat(metadata.get("trained_at", "2000-01-01"))
        age_days = (datetime.utcnow() - trained_at).days

        if age_days > self.max_age_days:
            logger.info(
                f"Model is {age_days} days old (max: {self.max_age_days} days)"
            )
            return False

        # Check accuracy
        val_mape = metadata.get("metrics", {}).get("val_mape", 100.0)
        if val_mape > self.min_accuracy_mape:
            logger.info(
                f"Model MAPE {val_mape:.2f}% exceeds threshold {self.min_accuracy_mape}%"
            )
            return False

        logger.info(
            f"Model is ready: age={age_days} days, MAPE={val_mape:.2f}%"
        )
        return True


class APIHealthSensor(BaseSensorOperator):
    """
    Sensor to verify external API health before making requests.

    Performs lightweight health checks on pricing APIs to ensure
    they are responsive before starting data ingestion.

    :param api_sources: List of API sources to check
    :param timeout_seconds: Timeout for health check requests
    :param min_healthy_apis: Minimum number of APIs that must be healthy
    """

    template_fields: Sequence[str] = ("api_sources",)
    ui_color = "#c6dbef"

    def __init__(
        self,
        *,
        api_sources: Optional[List[str]] = None,
        timeout_seconds: int = 10,
        min_healthy_apis: int = 1,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.api_sources = api_sources or ["flatpeak", "nrel", "iea"]
        self.timeout_seconds = timeout_seconds
        self.min_healthy_apis = min_healthy_apis

    def poke(self, context: Context) -> bool:
        """Check API health."""
        healthy_apis = []
        unhealthy_apis = []

        for api_source in self.api_sources:
            try:
                hook = PricingAPIHook(
                    api_source=api_source,
                    conn_id=f"{api_source}_default",
                )
                is_healthy = hook.health_check(timeout=self.timeout_seconds)

                if is_healthy:
                    healthy_apis.append(api_source)
                    logger.info(f"API {api_source}: healthy")
                else:
                    unhealthy_apis.append(api_source)
                    logger.warning(f"API {api_source}: unhealthy")

            except Exception as e:
                unhealthy_apis.append(api_source)
                logger.error(f"API {api_source}: health check failed - {e}")

        logger.info(
            f"API health check: {len(healthy_apis)} healthy, "
            f"{len(unhealthy_apis)} unhealthy"
        )

        return len(healthy_apis) >= self.min_healthy_apis


class MarketOpenSensor(BaseSensorOperator):
    """
    Sensor to check if electricity markets are open.

    Respects market schedules and holidays to avoid running
    pipelines when no new data is expected.

    :param markets: List of market identifiers
    :param check_holidays: Whether to check for holidays
    :param skip_weekends: Whether to skip weekend days
    """

    template_fields: Sequence[str] = ("markets",)
    ui_color = "#dadaeb"

    # Market schedules (UTC times)
    MARKET_SCHEDULES = {
        "EPEX_DE": {"open": 0, "close": 24, "weekends": True},  # 24/7
        "EPEX_FR": {"open": 0, "close": 24, "weekends": True},
        "NORDPOOL_GB": {"open": 0, "close": 24, "weekends": True},
        "ERCOT": {"open": 6, "close": 22, "weekends": True},  # 6 AM - 10 PM CT
        "CAISO": {"open": 7, "close": 23, "weekends": True},  # 7 AM - 11 PM PT
        "PJM": {"open": 5, "close": 21, "weekends": True},  # 5 AM - 9 PM ET
    }

    # Known holidays (simplified - would use a holiday library in production)
    HOLIDAYS_2024 = {
        "US": [
            "2024-01-01",  # New Year
            "2024-07-04",  # Independence Day
            "2024-11-28",  # Thanksgiving
            "2024-12-25",  # Christmas
        ],
        "EU": [
            "2024-01-01",  # New Year
            "2024-12-25",  # Christmas
            "2024-12-26",  # Boxing Day
        ],
    }

    def __init__(
        self,
        *,
        markets: Optional[List[str]] = None,
        check_holidays: bool = True,
        skip_weekends: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.markets = markets or ["EPEX_DE", "NORDPOOL_GB", "ERCOT"]
        self.check_holidays = check_holidays
        self.skip_weekends = skip_weekends

    def poke(self, context: Context) -> bool:
        """Check if markets are open."""
        now = datetime.utcnow()
        current_hour = now.hour
        current_date = now.strftime("%Y-%m-%d")
        is_weekend = now.weekday() >= 5

        open_markets = []
        closed_markets = []

        for market in self.markets:
            schedule = self.MARKET_SCHEDULES.get(
                market,
                {"open": 0, "close": 24, "weekends": True},
            )

            # Check weekend
            if is_weekend and not schedule.get("weekends", True):
                closed_markets.append((market, "weekend"))
                continue

            # Check hours
            if not (schedule["open"] <= current_hour < schedule["close"]):
                closed_markets.append((market, "outside hours"))
                continue

            # Check holidays
            if self.check_holidays:
                region = "US" if market in ["ERCOT", "CAISO", "PJM"] else "EU"
                holidays = self.HOLIDAYS_2024.get(region, [])
                if current_date in holidays:
                    closed_markets.append((market, "holiday"))
                    continue

            open_markets.append(market)

        logger.info(
            f"Market status: {len(open_markets)} open, {len(closed_markets)} closed"
        )

        for market, reason in closed_markets:
            logger.info(f"Market {market} closed: {reason}")

        # Return True if at least one market is open
        return len(open_markets) > 0


class DataUpdateSensor(BaseSensorOperator):
    """
    Sensor to detect when new price data has been ingested.

    Monitors the electricity_prices table for new records since
    the last DAG run, triggering downstream tasks only when
    new data is available.

    :param regions: Regions to monitor
    :param min_new_records: Minimum number of new records required
    :param conn_id: TimescaleDB connection ID
    """

    template_fields: Sequence[str] = ("regions",)
    ui_color = "#bcbddc"

    def __init__(
        self,
        *,
        regions: Optional[List[str]] = None,
        min_new_records: int = 1,
        conn_id: str = "timescaledb_default",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.regions = regions or ["GB", "DE", "US-CA"]
        self.min_new_records = min_new_records
        self.conn_id = conn_id

    def poke(self, context: Context) -> bool:
        """Check for new data since last run."""
        hook = TimescaleDBHook(conn_id=self.conn_id)

        # Get the previous execution date
        prev_execution = context.get("prev_execution_date")
        if not prev_execution:
            logger.info("No previous execution - considering data as new")
            return True

        regions_str = ",".join(f"'{r}'" for r in self.regions)
        query = f"""
            SELECT COUNT(*) as new_records
            FROM electricity_prices
            WHERE region IN ({regions_str})
            AND fetched_at > '{prev_execution.isoformat()}'
        """

        results = hook.execute_query(query)
        new_records = results[0]["new_records"] if results else 0

        logger.info(
            f"Found {new_records} new records since {prev_execution} "
            f"(threshold: {self.min_new_records})"
        )

        return new_records >= self.min_new_records


class ForecastStaleSensor(BaseSensorOperator):
    """
    Sensor to check if forecasts are stale and need regeneration.

    Triggers forecast generation when:
    - No forecast exists for the next hour
    - Forecast confidence has degraded significantly
    - New price data makes existing forecasts outdated

    :param regions: Regions to check
    :param staleness_threshold_minutes: Time after which forecast is stale
    :param conn_id: Redis connection ID for forecast cache
    """

    template_fields: Sequence[str] = ("regions",)
    ui_color = "#9ecae1"

    def __init__(
        self,
        *,
        regions: Optional[List[str]] = None,
        staleness_threshold_minutes: int = 60,
        conn_id: str = "redis_default",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.regions = regions or ["GB", "DE", "US-CA"]
        self.staleness_threshold_minutes = staleness_threshold_minutes
        self.conn_id = conn_id

    def poke(self, context: Context) -> bool:
        """Check if forecasts are stale."""
        hook = RedisHook(conn_id=self.conn_id)

        stale_regions = []
        fresh_regions = []

        for region in self.regions:
            key = f"forecast:summary:{region}"
            forecast = hook.get_json(key)

            if not forecast:
                stale_regions.append((region, "missing"))
                continue

            # Check forecast age
            if isinstance(forecast, list) and forecast:
                generated_at = datetime.fromisoformat(
                    forecast[0].get("generated_at", "2000-01-01")
                )
                age_minutes = (datetime.utcnow() - generated_at).total_seconds() / 60

                if age_minutes > self.staleness_threshold_minutes:
                    stale_regions.append((region, f"{age_minutes:.0f}min old"))
                else:
                    fresh_regions.append(region)
            else:
                stale_regions.append((region, "invalid format"))

        logger.info(
            f"Forecast status: {len(fresh_regions)} fresh, "
            f"{len(stale_regions)} stale"
        )

        for region, reason in stale_regions:
            logger.info(f"Region {region}: stale ({reason})")

        # Return True if any forecasts are stale (need regeneration)
        return len(stale_regions) > 0
