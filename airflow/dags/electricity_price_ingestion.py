"""
Electricity Price Ingestion DAG

Schedule: Every 15 minutes
Purpose: Fetch electricity prices from multiple APIs and store in TimescaleDB

Data Sources:
- Flatpeak (UK/EU electricity prices)
- NREL (US utility rates)
- IEA (Global electricity statistics)

Features:
- Parallel API fetching with rate limiting
- Data validation and deduplication
- TimescaleDB storage with upsert
- Redis cache warming
- Automatic forecast trigger on new data

SLA: Complete within 5 minutes
Retry: 3 times with 2-minute delay
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from airflow import DAG
from airflow.decorators import task, task_group
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.utils.trigger_rule import TriggerRule

# Import custom operators and sensors
from plugins.custom_operators import (
    PricingAPIOperator,
    RedisCacheOperator,
    TimescaleDBOperator,
)
from plugins.sensors import APIHealthSensor, MarketOpenSensor

logger = logging.getLogger(__name__)

# DAG default arguments
default_args = {
    "owner": "electricity-optimizer",
    "depends_on_past": False,
    "email": ["alerts@electricity-optimizer.io"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=10),
    "execution_timeout": timedelta(minutes=5),
    "sla": timedelta(minutes=5),
}

# DAG documentation
doc_md = """
# Electricity Price Ingestion DAG

## Overview
This DAG fetches electricity prices from multiple external APIs every 15 minutes,
validates and deduplicates the data, stores it in TimescaleDB, and updates the
Redis cache for fast access.

## Data Flow
1. **Health Check**: Verify at least one API is responsive
2. **Market Check**: Skip if all markets are closed
3. **Parallel Fetch**: Fetch data from Flatpeak, NREL, and IEA in parallel
4. **Aggregate**: Combine and deduplicate data from all sources
5. **Validate**: Run data quality checks
6. **Store**: Upsert into TimescaleDB hypertable
7. **Cache**: Update Redis cache with latest prices
8. **Trigger**: Optionally trigger forecast regeneration

## Connections Required
- `flatpeak_default`: Flatpeak API credentials
- `nrel_default`: NREL API key
- `iea_default`: IEA API credentials
- `timescaledb_default`: TimescaleDB connection
- `redis_default`: Redis connection

## SLA
- Must complete within 5 minutes
- Alerts on SLA miss

## Rate Limiting
Uses resource pool `pricing_api_pool` to manage API quotas:
- Flatpeak: 100 requests/minute
- NREL: 60 requests/minute
- IEA: 30 requests/minute
"""


with DAG(
    dag_id="electricity_price_ingestion",
    default_args=default_args,
    description="Fetch and store electricity prices from multiple APIs",
    schedule_interval="*/15 * * * *",  # Every 15 minutes
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["prices", "ingestion", "core"],
    doc_md=doc_md,
) as dag:

    # =========================================================================
    # Pre-flight Checks
    # =========================================================================

    start = EmptyOperator(task_id="start")

    # Check API health before attempting to fetch
    check_api_health = APIHealthSensor(
        task_id="check_api_health",
        api_sources=["flatpeak", "nrel", "iea"],
        min_healthy_apis=1,
        timeout_seconds=10,
        poke_interval=30,
        timeout=300,
        mode="reschedule",
    )

    # Check if markets are open (skip processing if all closed)
    check_markets_open = MarketOpenSensor(
        task_id="check_markets_open",
        markets=["EPEX_DE", "NORDPOOL_GB", "ERCOT", "CAISO"],
        check_holidays=True,
        poke_interval=60,
        timeout=120,
        soft_fail=True,  # Don't fail DAG if markets closed
    )

    # =========================================================================
    # Data Fetching (Parallel)
    # =========================================================================

    @task_group(group_id="fetch_prices")
    def fetch_prices_group():
        """Fetch prices from all API sources in parallel."""

        # Flatpeak (UK/EU)
        fetch_flatpeak = PricingAPIOperator(
            task_id="fetch_flatpeak",
            api_source="flatpeak",
            regions=["GB", "DE", "FR", "ES", "IT", "NL"],
            conn_id="flatpeak_default",
            rate_limit_pool="pricing_api_pool",
            timeout_seconds=30,
        )

        # NREL (US)
        fetch_nrel = PricingAPIOperator(
            task_id="fetch_nrel",
            api_source="nrel",
            regions=["US-CA", "US-TX", "US-NY", "US-FL"],
            conn_id="nrel_default",
            rate_limit_pool="pricing_api_pool",
            timeout_seconds=30,
        )

        # IEA (Global)
        fetch_iea = PricingAPIOperator(
            task_id="fetch_iea",
            api_source="iea",
            regions=["OECD", "EU27", "USA", "CHN"],
            conn_id="iea_default",
            rate_limit_pool="pricing_api_pool",
            timeout_seconds=30,
            # IEA is lower priority - soft fail if unavailable
            retries=1,
        )

        return [fetch_flatpeak, fetch_nrel, fetch_iea]

    fetch_tasks = fetch_prices_group()

    # =========================================================================
    # Data Aggregation and Validation
    # =========================================================================

    @task(task_id="aggregate_prices", multiple_outputs=True)
    def aggregate_prices(
        flatpeak_data: Dict[str, Any],
        nrel_data: Dict[str, Any],
        iea_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Aggregate and deduplicate prices from all sources.

        Performs:
        - Merge data from all sources
        - Remove duplicates (same timestamp/region/source)
        - Basic validation (price > 0, valid timestamps)
        - Calculate statistics for monitoring

        Returns:
            Aggregated price data with metadata
        """
        all_prices = []

        # Collect prices from each source
        for source_data in [flatpeak_data, nrel_data, iea_data]:
            if source_data and "prices" in source_data:
                all_prices.extend(source_data["prices"])

        if not all_prices:
            logger.warning("No prices received from any source")
            return {
                "prices": [],
                "count": 0,
                "sources": [],
                "errors": [],
            }

        # Deduplicate by (timestamp, region, source)
        seen = set()
        deduped = []
        for price in all_prices:
            key = (
                price.get("timestamp"),
                price.get("region"),
                price.get("source"),
            )
            if key not in seen:
                seen.add(key)
                deduped.append(price)

        # Basic validation
        valid_prices = []
        validation_errors = []

        for price in deduped:
            errors = []

            # Price must be positive (or at least non-negative for some markets)
            if price.get("price") is None:
                errors.append("missing price")
            elif price["price"] < -500:  # Allow negative for wholesale markets
                errors.append(f"price too low: {price['price']}")
            elif price["price"] > 10000:  # Sanity check
                errors.append(f"price too high: {price['price']}")

            # Timestamp must be valid
            if not price.get("timestamp"):
                errors.append("missing timestamp")

            # Region must be specified
            if not price.get("region"):
                errors.append("missing region")

            if errors:
                validation_errors.append({
                    "price": price,
                    "errors": errors,
                })
            else:
                valid_prices.append(price)

        # Calculate statistics
        sources = list(set(p.get("source") for p in valid_prices))
        regions = list(set(p.get("region") for p in valid_prices))

        logger.info(
            f"Aggregated {len(valid_prices)} valid prices from {len(sources)} sources, "
            f"{len(regions)} regions. {len(validation_errors)} validation errors."
        )

        return {
            "prices": valid_prices,
            "count": len(valid_prices),
            "sources": sources,
            "regions": regions,
            "validation_errors": validation_errors[:10],  # Limit for XCom
            "statistics": {
                "total_fetched": len(all_prices),
                "duplicates_removed": len(all_prices) - len(deduped),
                "validation_failures": len(validation_errors),
            },
        }

    @task(task_id="validate_data_quality")
    def validate_data_quality(aggregated_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform additional data quality validation.

        Checks:
        - Minimum number of records received
        - Expected regions present
        - Price distribution sanity
        """
        prices = aggregated_data.get("prices", [])
        issues = []

        # Check minimum records
        min_records = int(Variable.get("price_ingestion_min_records", default_var=10))
        if len(prices) < min_records:
            issues.append(f"Too few records: {len(prices)} < {min_records}")

        # Check expected regions
        expected_regions = {"GB", "DE", "US-CA"}  # Core regions
        actual_regions = set(p.get("region") for p in prices)
        missing_regions = expected_regions - actual_regions

        if missing_regions:
            issues.append(f"Missing core regions: {missing_regions}")

        # Check for extreme values
        if prices:
            prices_values = [p["price"] for p in prices if p.get("price")]
            if prices_values:
                import statistics
                mean_price = statistics.mean(prices_values)
                std_price = statistics.stdev(prices_values) if len(prices_values) > 1 else 0

                extreme_count = sum(
                    1 for p in prices_values
                    if abs(p - mean_price) > 3 * std_price and std_price > 0
                )
                if extreme_count > len(prices) * 0.1:  # >10% extreme values
                    issues.append(f"Many extreme values: {extreme_count}")

        quality_passed = len(issues) == 0
        if not quality_passed:
            logger.warning(f"Data quality issues: {issues}")

        return {
            **aggregated_data,
            "quality_passed": quality_passed,
            "quality_issues": issues,
        }

    # =========================================================================
    # Data Storage
    # =========================================================================

    store_prices = TimescaleDBOperator(
        task_id="store_prices",
        operation="upsert",
        table="electricity_prices",
        data="{{ ti.xcom_pull(task_ids='validate_data_quality') }}",
        conflict_columns=["timestamp", "region", "source"],
        conn_id="timescaledb_default",
        batch_size=500,
    )

    # =========================================================================
    # Cache Update
    # =========================================================================

    @task_group(group_id="update_cache")
    def update_cache_group():
        """Update Redis cache with new price data."""

        # Invalidate stale cache entries
        invalidate_cache = RedisCacheOperator(
            task_id="invalidate_stale_cache",
            operation="invalidate",
            key_pattern="price:latest:*",
            ttl_seconds=900,  # 15 min TTL
            conn_id="redis_default",
        )

        # Update with new data
        update_cache = RedisCacheOperator(
            task_id="update_price_cache",
            operation="update",
            data="{{ ti.xcom_pull(task_ids='validate_data_quality') }}",
            ttl_seconds=900,
            conn_id="redis_default",
        )

        invalidate_cache >> update_cache

    cache_tasks = update_cache_group()

    # =========================================================================
    # Trigger Downstream DAGs
    # =========================================================================

    @task.branch(task_id="check_trigger_forecast")
    def check_trigger_forecast(aggregated_data: Dict[str, Any]) -> str:
        """
        Decide whether to trigger forecast regeneration.

        Trigger if:
        - New data was ingested
        - Data quality passed
        - Core regions have fresh data
        """
        if not aggregated_data.get("quality_passed", False):
            logger.info("Skipping forecast trigger: quality check failed")
            return "skip_forecast_trigger"

        if aggregated_data.get("count", 0) < 10:
            logger.info("Skipping forecast trigger: insufficient new data")
            return "skip_forecast_trigger"

        # Check if core regions have data
        core_regions = {"GB", "DE", "US-CA"}
        actual_regions = set(aggregated_data.get("regions", []))

        if not core_regions.intersection(actual_regions):
            logger.info("Skipping forecast trigger: no core regions in new data")
            return "skip_forecast_trigger"

        logger.info("Triggering forecast regeneration")
        return "trigger_forecast_dag"

    trigger_forecast_dag = TriggerDagRunOperator(
        task_id="trigger_forecast_dag",
        trigger_dag_id="forecast_generation",
        wait_for_completion=False,
        reset_dag_run=False,
        conf={"triggered_by": "price_ingestion"},
    )

    skip_forecast_trigger = EmptyOperator(task_id="skip_forecast_trigger")

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

    # Pre-flight checks
    start >> check_api_health >> check_markets_open

    # Parallel fetch
    check_markets_open >> fetch_tasks

    # Aggregate and validate
    aggregated = aggregate_prices(
        flatpeak_data=fetch_tasks[0].output,
        nrel_data=fetch_tasks[1].output,
        iea_data=fetch_tasks[2].output,
    )
    validated = validate_data_quality(aggregated)

    # Store and cache
    validated >> store_prices >> cache_tasks

    # Conditional forecast trigger
    branch_result = check_trigger_forecast(validated)
    branch_result >> [trigger_forecast_dag, skip_forecast_trigger]

    # End
    [cache_tasks, trigger_forecast_dag, skip_forecast_trigger] >> end
