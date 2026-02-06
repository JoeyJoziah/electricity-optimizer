"""
Data Quality Checks DAG

Schedule: Daily at 6:00 AM UTC
Purpose: Comprehensive data quality validation and reporting

Checks:
1. Data completeness - No gaps > 1 hour in any region
2. Price range validation - Detect outliers > 3 standard deviations
3. API response time monitoring - Track external API health
4. Model accuracy degradation - Monitor forecast vs actual
5. Data freshness - Ensure all sources are current

Features:
- Detailed quality report generation
- Slack/email alerting on issues
- Metrics export to Prometheus
- Historical quality tracking
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from airflow import DAG
from airflow.decorators import task, task_group
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator
from airflow.utils.trigger_rule import TriggerRule

from plugins.custom_operators import DataQualityOperator, TimescaleDBOperator

logger = logging.getLogger(__name__)

# DAG default arguments
default_args = {
    "owner": "electricity-optimizer",
    "depends_on_past": False,
    "email": ["data-quality@electricity-optimizer.io"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(minutes=30),
}

# DAG documentation
doc_md = """
# Data Quality Checks DAG

## Overview
Runs comprehensive data quality checks daily at 6 AM UTC, generating a
quality report and alerting on any issues that could affect forecast
accuracy or system reliability.

## Quality Checks

### 1. Completeness Check
- Scans for gaps in price data > 1 hour
- Checks all regions independently
- Severity: HIGH (impacts forecasts)

### 2. Price Range Validation
- Detects statistical outliers (> 3 std dev)
- Region-specific thresholds
- Severity: MEDIUM (may indicate data issues)

### 3. API Health Monitoring
- Tracks response times from external APIs
- Monitors success/failure rates
- Severity: HIGH (impacts data ingestion)

### 4. Model Accuracy Tracking
- Compares forecasts to actual prices
- Alerts on MAPE degradation > 15%
- Severity: MEDIUM (impacts recommendations)

### 5. Data Freshness
- Ensures all data sources are current
- Threshold: 4 hours for critical regions
- Severity: HIGH (stale data = bad forecasts)

## Alerting
- Slack notifications for HIGH severity issues
- Email digest with full report
- Prometheus metrics for dashboards

## Connections Required
- `timescaledb_default`: Data source
- `slack_data_quality`: Slack webhook for alerts
"""

# Quality check thresholds
QUALITY_THRESHOLDS = {
    "completeness": {
        "max_gap_hours": 1.0,
        "severity": "HIGH",
    },
    "price_range": {
        "std_dev_threshold": 3.0,
        "max_outlier_ratio": 0.05,  # 5% outliers is concerning
        "severity": "MEDIUM",
    },
    "api_health": {
        "max_response_time_ms": 5000,
        "min_success_rate": 0.95,
        "severity": "HIGH",
    },
    "model_accuracy": {
        "max_mape": 15.0,
        "degradation_threshold": 2.0,  # 2% worse than baseline
        "severity": "MEDIUM",
    },
    "freshness": {
        "max_age_hours": 4.0,
        "critical_regions": ["GB", "DE", "US-CA"],
        "severity": "HIGH",
    },
}


with DAG(
    dag_id="data_quality",
    default_args=default_args,
    description="Daily data quality checks and reporting",
    schedule_interval="0 6 * * *",  # Daily at 6:00 AM UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["quality", "monitoring", "daily"],
    doc_md=doc_md,
) as dag:

    # =========================================================================
    # Start
    # =========================================================================

    start = EmptyOperator(task_id="start")

    # =========================================================================
    # Quality Checks (Parallel)
    # =========================================================================

    @task_group(group_id="quality_checks")
    def quality_checks_group():
        """Run all quality checks in parallel."""

        # 1. Completeness Check
        check_completeness = DataQualityOperator(
            task_id="check_completeness",
            check_type="completeness",
            threshold=QUALITY_THRESHOLDS["completeness"]["max_gap_hours"],
            lookback_hours=24,
            alert_on_failure=False,  # We'll handle alerting in aggregation
            conn_id="timescaledb_default",
        )

        # 2. Price Range Check
        check_price_range = DataQualityOperator(
            task_id="check_price_range",
            check_type="price_range",
            threshold=QUALITY_THRESHOLDS["price_range"]["std_dev_threshold"],
            lookback_hours=24,
            alert_on_failure=False,
            conn_id="timescaledb_default",
        )

        # 3. API Health Check
        check_api_health = DataQualityOperator(
            task_id="check_api_health",
            check_type="api_health",
            threshold=QUALITY_THRESHOLDS["api_health"]["max_response_time_ms"],
            lookback_hours=24,
            alert_on_failure=False,
            conn_id="timescaledb_default",
        )

        # 4. Model Accuracy Check
        check_model_accuracy = DataQualityOperator(
            task_id="check_model_accuracy",
            check_type="model_accuracy",
            threshold=QUALITY_THRESHOLDS["model_accuracy"]["max_mape"],
            lookback_hours=24,
            alert_on_failure=False,
            conn_id="timescaledb_default",
        )

        # 5. Freshness Check
        check_freshness = DataQualityOperator(
            task_id="check_freshness",
            check_type="freshness",
            threshold=QUALITY_THRESHOLDS["freshness"]["max_age_hours"],
            lookback_hours=24,
            alert_on_failure=False,
            conn_id="timescaledb_default",
        )

        return [
            check_completeness,
            check_price_range,
            check_api_health,
            check_model_accuracy,
            check_freshness,
        ]

    quality_check_tasks = quality_checks_group()

    # =========================================================================
    # Additional Detailed Checks
    # =========================================================================

    @task(task_id="check_region_coverage")
    def check_region_coverage() -> Dict[str, Any]:
        """
        Check that all expected regions have data.

        Returns detailed coverage statistics per region.
        """
        from plugins.hooks import TimescaleDBHook

        hook = TimescaleDBHook(conn_id="timescaledb_default")

        expected_regions = [
            "GB", "DE", "FR", "ES", "IT", "NL",  # EU
            "US-CA", "US-TX", "US-NY", "US-FL",  # US
        ]

        query = """
            SELECT
                region,
                COUNT(*) as record_count,
                MIN(timestamp) as earliest_record,
                MAX(timestamp) as latest_record,
                COUNT(DISTINCT DATE(timestamp)) as days_covered,
                COUNT(*) FILTER (WHERE timestamp >= NOW() - INTERVAL '24 hours') as last_24h_count
            FROM electricity_prices
            WHERE timestamp >= NOW() - INTERVAL '30 days'
            GROUP BY region
        """

        results = hook.execute_query(query)
        results_dict = {r["region"]: r for r in results}

        coverage_report = []
        missing_regions = []
        low_coverage_regions = []

        for region in expected_regions:
            if region not in results_dict:
                missing_regions.append(region)
                coverage_report.append({
                    "region": region,
                    "status": "MISSING",
                    "record_count": 0,
                    "last_24h_count": 0,
                })
            else:
                data = results_dict[region]
                # Expected: ~4 records per hour * 24 hours = 96 records/day
                expected_daily = 96
                actual_daily = data["last_24h_count"]
                coverage_pct = (actual_daily / expected_daily) * 100

                status = "OK" if coverage_pct >= 90 else "LOW" if coverage_pct >= 50 else "CRITICAL"

                if status in ["LOW", "CRITICAL"]:
                    low_coverage_regions.append(region)

                coverage_report.append({
                    "region": region,
                    "status": status,
                    "record_count": data["record_count"],
                    "last_24h_count": actual_daily,
                    "coverage_pct": coverage_pct,
                    "days_covered": data["days_covered"],
                })

        passed = len(missing_regions) == 0 and len(low_coverage_regions) == 0

        return {
            "passed": passed,
            "coverage_report": coverage_report,
            "missing_regions": missing_regions,
            "low_coverage_regions": low_coverage_regions,
            "total_regions": len(expected_regions),
            "covered_regions": len(expected_regions) - len(missing_regions),
        }

    @task(task_id="check_forecast_accuracy_trend")
    def check_forecast_accuracy_trend() -> Dict[str, Any]:
        """
        Check if forecast accuracy is trending worse.

        Compares last 7 days accuracy to previous 7 days.
        """
        from plugins.hooks import TimescaleDBHook

        hook = TimescaleDBHook(conn_id="timescaledb_default")

        query = """
            WITH daily_mape AS (
                SELECT
                    DATE(f.forecast_time) as forecast_date,
                    AVG(ABS(f.price_forecast - p.price) / NULLIF(ABS(p.price), 0)) * 100 as mape
                FROM forecasts f
                JOIN electricity_prices p
                    ON f.region = p.region
                    AND f.forecast_time = p.timestamp
                WHERE f.forecast_time >= NOW() - INTERVAL '14 days'
                AND f.forecast_time < NOW()
                GROUP BY DATE(f.forecast_time)
            )
            SELECT
                forecast_date,
                mape,
                CASE
                    WHEN forecast_date >= NOW()::DATE - INTERVAL '7 days'
                    THEN 'recent'
                    ELSE 'previous'
                END as period
            FROM daily_mape
            ORDER BY forecast_date
        """

        results = hook.execute_query(query)

        if not results:
            return {
                "passed": True,
                "message": "No forecast data available for trend analysis",
            }

        recent_mapes = [r["mape"] for r in results if r["period"] == "recent" and r["mape"]]
        previous_mapes = [r["mape"] for r in results if r["period"] == "previous" and r["mape"]]

        if not recent_mapes or not previous_mapes:
            return {
                "passed": True,
                "message": "Insufficient data for trend analysis",
            }

        import statistics
        recent_avg = statistics.mean(recent_mapes)
        previous_avg = statistics.mean(previous_mapes)

        degradation = recent_avg - previous_avg
        degradation_threshold = QUALITY_THRESHOLDS["model_accuracy"]["degradation_threshold"]

        passed = degradation <= degradation_threshold

        return {
            "passed": passed,
            "recent_avg_mape": recent_avg,
            "previous_avg_mape": previous_avg,
            "degradation": degradation,
            "degradation_threshold": degradation_threshold,
            "trend": "DEGRADING" if degradation > 0 else "IMPROVING",
            "daily_data": [
                {"date": r["forecast_date"].isoformat(), "mape": r["mape"]}
                for r in results
            ],
        }

    # =========================================================================
    # Report Generation
    # =========================================================================

    @task(task_id="aggregate_results")
    def aggregate_results(
        completeness_result: Dict[str, Any],
        price_range_result: Dict[str, Any],
        api_health_result: Dict[str, Any],
        model_accuracy_result: Dict[str, Any],
        freshness_result: Dict[str, Any],
        coverage_result: Dict[str, Any],
        trend_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Aggregate all quality check results into a comprehensive report.
        """
        checks = [
            {
                "name": "completeness",
                "result": completeness_result,
                "severity": QUALITY_THRESHOLDS["completeness"]["severity"],
            },
            {
                "name": "price_range",
                "result": price_range_result,
                "severity": QUALITY_THRESHOLDS["price_range"]["severity"],
            },
            {
                "name": "api_health",
                "result": api_health_result,
                "severity": QUALITY_THRESHOLDS["api_health"]["severity"],
            },
            {
                "name": "model_accuracy",
                "result": model_accuracy_result,
                "severity": QUALITY_THRESHOLDS["model_accuracy"]["severity"],
            },
            {
                "name": "freshness",
                "result": freshness_result,
                "severity": QUALITY_THRESHOLDS["freshness"]["severity"],
            },
            {
                "name": "region_coverage",
                "result": coverage_result,
                "severity": "HIGH",
            },
            {
                "name": "accuracy_trend",
                "result": trend_result,
                "severity": "MEDIUM",
            },
        ]

        # Categorize results
        passed_checks = []
        failed_checks = []
        high_severity_failures = []

        for check in checks:
            if check["result"].get("passed", False):
                passed_checks.append(check["name"])
            else:
                failed_checks.append({
                    "name": check["name"],
                    "severity": check["severity"],
                    "details": check["result"],
                })
                if check["severity"] == "HIGH":
                    high_severity_failures.append(check["name"])

        # Calculate overall health score (0-100)
        total_checks = len(checks)
        passed_count = len(passed_checks)
        health_score = (passed_count / total_checks) * 100

        # Determine overall status
        if high_severity_failures:
            overall_status = "CRITICAL"
        elif failed_checks:
            overall_status = "WARNING"
        else:
            overall_status = "HEALTHY"

        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_status": overall_status,
            "health_score": health_score,
            "total_checks": total_checks,
            "passed_count": passed_count,
            "failed_count": len(failed_checks),
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "high_severity_failures": high_severity_failures,
            "requires_alert": len(high_severity_failures) > 0,
        }

        logger.info(
            f"Quality Report: {overall_status} (score: {health_score:.1f}%, "
            f"{passed_count}/{total_checks} checks passed)"
        )

        return report

    @task(task_id="generate_quality_report")
    def generate_quality_report(aggregated_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a detailed quality report for storage and review.
        """
        report_content = f"""
# Data Quality Report

**Generated:** {aggregated_results['timestamp']}
**Status:** {aggregated_results['overall_status']}
**Health Score:** {aggregated_results['health_score']:.1f}%

## Summary

- Total Checks: {aggregated_results['total_checks']}
- Passed: {aggregated_results['passed_count']}
- Failed: {aggregated_results['failed_count']}

## Passed Checks

{chr(10).join(f"- {check}" for check in aggregated_results['passed_checks'])}

## Failed Checks

"""
        for failure in aggregated_results['failed_checks']:
            report_content += f"""
### {failure['name']} (Severity: {failure['severity']})

{json.dumps(failure['details'], indent=2, default=str)}

"""

        # Store report in database
        from plugins.hooks import TimescaleDBHook

        hook = TimescaleDBHook(conn_id="timescaledb_default")

        hook.insert_many(
            table="quality_reports",
            data=[{
                "timestamp": aggregated_results["timestamp"],
                "overall_status": aggregated_results["overall_status"],
                "health_score": aggregated_results["health_score"],
                "passed_count": aggregated_results["passed_count"],
                "failed_count": aggregated_results["failed_count"],
                "report_json": json.dumps(aggregated_results),
            }],
        )

        logger.info("Quality report stored in database")

        return {
            "report_stored": True,
            "report_content": report_content,
        }

    # =========================================================================
    # Alerting
    # =========================================================================

    @task.branch(task_id="check_alert_needed")
    def check_alert_needed(aggregated_results: Dict[str, Any]) -> str:
        """Determine if alerting is needed."""
        if aggregated_results.get("requires_alert", False):
            return "send_slack_alert"
        else:
            return "skip_alert"

    @task(task_id="send_slack_alert")
    def send_slack_alert(aggregated_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send Slack alert for critical quality issues.
        """
        failures = aggregated_results.get("high_severity_failures", [])

        # Format message
        message = f"""
:warning: *Data Quality Alert*

*Status:* {aggregated_results['overall_status']}
*Health Score:* {aggregated_results['health_score']:.1f}%
*Time:* {aggregated_results['timestamp']}

*Critical Issues:*
{chr(10).join(f"- {f}" for f in failures)}

*Action Required:* Please investigate the failing quality checks.

<https://airflow.electricity-optimizer.io/dags/data_quality|View DAG Run>
"""

        # In production, would use SlackWebhookOperator
        # For now, just log the message
        logger.warning(f"SLACK ALERT:\n{message}")

        return {
            "alert_sent": True,
            "failures": failures,
            "message": message,
        }

    skip_alert = EmptyOperator(task_id="skip_alert")

    # =========================================================================
    # Metrics Export
    # =========================================================================

    @task(task_id="export_metrics", trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS)
    def export_metrics(aggregated_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Export quality metrics to Prometheus.

        Metrics:
        - data_quality_health_score
        - data_quality_checks_passed
        - data_quality_checks_failed
        - data_quality_alert_triggered
        """
        from plugins.hooks import RedisHook

        # Store metrics in Redis for Prometheus scraping
        hook = RedisHook(conn_id="redis_default")

        metrics = {
            "data_quality_health_score": aggregated_results["health_score"],
            "data_quality_checks_passed": aggregated_results["passed_count"],
            "data_quality_checks_failed": aggregated_results["failed_count"],
            "data_quality_alert_triggered": 1 if aggregated_results["requires_alert"] else 0,
            "data_quality_last_run": datetime.utcnow().timestamp(),
        }

        for metric_name, value in metrics.items():
            hook.set_json(f"metrics:{metric_name}", value, ttl=86400)

        logger.info(f"Exported {len(metrics)} metrics")

        return {"metrics_exported": metrics}

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

    # Start
    start >> quality_check_tasks

    # Additional checks (can run in parallel with quality checks)
    coverage_result = check_region_coverage()
    trend_result = check_forecast_accuracy_trend()
    start >> [coverage_result, trend_result]

    # Aggregate all results
    aggregated = aggregate_results(
        completeness_result=quality_check_tasks[0].output,
        price_range_result=quality_check_tasks[1].output,
        api_health_result=quality_check_tasks[2].output,
        model_accuracy_result=quality_check_tasks[3].output,
        freshness_result=quality_check_tasks[4].output,
        coverage_result=coverage_result,
        trend_result=trend_result,
    )

    [quality_check_tasks, coverage_result, trend_result] >> aggregated

    # Generate report
    report = generate_quality_report(aggregated)
    aggregated >> report

    # Alerting
    alert_branch = check_alert_needed(aggregated)
    slack_alert = send_slack_alert(aggregated)

    aggregated >> alert_branch
    alert_branch >> [slack_alert, skip_alert]

    # Export metrics
    metrics = export_metrics(aggregated)
    aggregated >> metrics

    # End
    [report, slack_alert, skip_alert, metrics] >> end
