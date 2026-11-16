"""
Data Quality Service

Monitors data freshness, detects anomalies, and tracks source reliability
across all utility data sources.
"""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Expected freshness windows per utility type (in hours)
FRESHNESS_THRESHOLDS: dict[str, int] = {
    "electricity": 1,  # 1 hour
    "natural_gas": 168,  # 7 days
    "heating_oil": 168,  # 7 days
    "community_solar": 720,  # 30 days
}

# Alert when data exceeds 2x the expected freshness window
FRESHNESS_ALERT_MULTIPLIER = 2

# Anomaly detection: flag rates deviating > 3 std from rolling average
ANOMALY_STD_THRESHOLD = 3.0

# Source reliability: alert at > 20% failure rate
SOURCE_FAILURE_ALERT_THRESHOLD = 0.20


class DataQualityService:
    """
    Monitors data quality across all utility data sources.

    - Freshness: tracks last_updated per utility_type per region
    - Anomalies: detects rate values deviating from rolling averages
    - Sources: tracks success/failure per data source
    """

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_freshness_report(self) -> list[dict]:
        """
        Get freshness status for each utility_type / region combination.

        Returns list of dicts with: utility_type, region, last_updated,
        threshold_hours, is_stale, hours_since_update.
        """
        result = await self._db.execute(
            text("""
                SELECT utility_type, region,
                       MAX("timestamp") as last_updated,
                       COUNT(*) as record_count
                FROM electricity_prices
                GROUP BY utility_type, region
                ORDER BY utility_type, region
            """)
        )
        rows = result.mappings().all()
        now = datetime.now(UTC)
        report = []

        for r in rows:
            utility_type = r["utility_type"]
            threshold_hours = FRESHNESS_THRESHOLDS.get(utility_type, 168)
            last_updated = r["last_updated"]

            if last_updated:
                # Ensure timezone-aware
                if last_updated.tzinfo is None:
                    last_updated = last_updated.replace(tzinfo=UTC)
                hours_since = (now - last_updated).total_seconds() / 3600
            else:
                hours_since = float("inf")

            is_stale = hours_since > (threshold_hours * FRESHNESS_ALERT_MULTIPLIER)

            report.append(
                {
                    "utility_type": utility_type,
                    "region": r["region"],
                    "last_updated": last_updated.isoformat() if last_updated else None,
                    "record_count": r["record_count"],
                    "threshold_hours": threshold_hours,
                    "alert_threshold_hours": threshold_hours * FRESHNESS_ALERT_MULTIPLIER,
                    "hours_since_update": round(hours_since, 1)
                    if hours_since != float("inf")
                    else None,
                    "is_stale": is_stale,
                }
            )

        return report

    async def detect_anomalies(self, lookback_days: int = 30) -> list[dict]:
        """
        Detect rate anomalies by comparing recent rates against rolling averages.

        Flags rates that deviate more than ANOMALY_STD_THRESHOLD standard deviations
        from the rolling average within the lookback period.
        """
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)

        result = await self._db.execute(
            text("""
                WITH stats AS (
                    SELECT utility_type, region,
                           AVG(price_per_kwh) as avg_rate,
                           STDDEV(price_per_kwh) as std_rate,
                           COUNT(*) as sample_count
                    FROM electricity_prices
                    WHERE "timestamp" >= :cutoff
                      AND price_per_kwh IS NOT NULL
                    GROUP BY utility_type, region
                    HAVING COUNT(*) >= 3
                )
                SELECT p.id, p.utility_type, p.region,
                       p.price_per_kwh AS rate_per_kwh,
                       p."timestamp" AS updated_at, p.source_api AS source,
                       s.avg_rate, s.std_rate, s.sample_count,
                       ABS(p.price_per_kwh - s.avg_rate) /
                           NULLIF(s.std_rate, 0) as z_score
                FROM electricity_prices p
                JOIN stats s ON p.utility_type = s.utility_type
                             AND p.region = s.region
                WHERE p."timestamp" >= :cutoff
                  AND p.price_per_kwh IS NOT NULL
                  AND s.std_rate > 0
                  AND ABS(p.price_per_kwh - s.avg_rate) /
                      NULLIF(s.std_rate, 0) > :threshold
                ORDER BY p."timestamp" DESC
                LIMIT 100
            """),
            {"cutoff": cutoff, "threshold": ANOMALY_STD_THRESHOLD},
        )
        rows = result.mappings().all()

        return [
            {
                "id": str(r["id"]),
                "utility_type": r["utility_type"],
                "region": r["region"],
                "rate": float(r["rate_per_kwh"]) if r["rate_per_kwh"] else None,
                "avg_rate": round(float(r["avg_rate"]), 4) if r["avg_rate"] else None,
                "std_rate": round(float(r["std_rate"]), 4) if r["std_rate"] else None,
                "z_score": round(float(r["z_score"]), 2) if r["z_score"] else None,
                "source": r["source"],
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            }
            for r in rows
        ]

    async def get_source_reliability(self, window_hours: int = 24) -> list[dict]:
        """
        Calculate success/failure rates per data source within a time window.

        Uses scraped_rates for scraper outcomes and electricity_prices for API ingestion.
        Falls back to counting non-null rates in electricity_prices if
        scrape_results doesn't exist.
        """
        cutoff = datetime.now(UTC) - timedelta(hours=window_hours)

        # Scraper outcomes live in scraped_rates (success flag per fetch); API
        # ingestion (EIA/NREL) only records successful writes in
        # electricity_prices, so those sources report no failures.
        scraped = await self._db.execute(
            text("""
                SELECT supplier_name AS source,
                       COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE success) AS successes,
                       COUNT(*) FILTER (WHERE NOT success) AS failures,
                       MAX(fetched_at) AS last_attempt
                FROM scraped_rates
                WHERE fetched_at >= :cutoff
                GROUP BY supplier_name
                ORDER BY supplier_name
            """),
            {"cutoff": cutoff},
        )
        ingested = await self._db.execute(
            text("""
                SELECT source_api AS source,
                       COUNT(*) AS total,
                       COUNT(*) AS successes,
                       0 AS failures,
                       MAX("timestamp") AS last_attempt
                FROM electricity_prices
                WHERE "timestamp" >= :cutoff
                  AND source_api IS NOT NULL
                GROUP BY source_api
                ORDER BY source_api
            """),
            {"cutoff": cutoff},
        )
        rows = list(scraped.mappings().all()) + list(ingested.mappings().all())

        return [
            {
                "source": r["source"],
                "total_attempts": r["total"],
                "successes": r["successes"],
                "failures": r["failures"],
                "failure_rate": round(r["failures"] / r["total"], 3) if r["total"] > 0 else 0,
                "is_degraded": (r["failures"] / r["total"]) > SOURCE_FAILURE_ALERT_THRESHOLD
                if r["total"] > 0
                else False,
                "last_attempt": r["last_attempt"].isoformat() if r["last_attempt"] else None,
            }
            for r in rows
        ]

    @staticmethod
    def check_rate_anomaly(
        rate: float,
        avg_rate: float,
        std_rate: float,
    ) -> dict:
        """
        Check if a single rate is anomalous.

        Returns dict with is_anomaly flag and z_score.
        """
        if std_rate <= 0:
            return {"is_anomaly": False, "z_score": 0.0}

        z_score = abs(rate - avg_rate) / std_rate
        return {
            "is_anomaly": z_score > ANOMALY_STD_THRESHOLD,
            "z_score": round(z_score, 2),
        }

    @staticmethod
    def check_duplicate(
        existing_rates: list[dict],
        new_rate: float,
        new_region: str,
        new_utility_type: str,
        tolerance: float = 0.0001,
    ) -> bool:
        """
        Check if a rate record is a duplicate of an existing one.

        Returns True if a matching record exists (same region, utility type,
        and rate within tolerance).
        """
        for existing in existing_rates:
            if (
                existing.get("region") == new_region
                and existing.get("utility_type") == new_utility_type
                and abs(float(existing.get("rate", 0)) - new_rate) < tolerance
            ):
                return True
        return False
