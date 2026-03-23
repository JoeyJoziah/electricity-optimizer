"""
Forecast Observation Repository

Data access layer for the forecast_observations and recommendation_outcomes tables.
Extracted from ObservationService to separate SQL from business logic.
"""

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class ForecastObservationRepository:
    """Raw SQL data access for forecast observations and recommendation outcomes."""

    def __init__(self, db: AsyncSession):
        self._db = db

    # Number of rows per INSERT statement.  Keeping this at 20 balances
    # round-trip reduction against per-query parameter count limits.
    _INSERT_BATCH_SIZE = 20

    async def insert_forecasts(
        self,
        forecast_id: str,
        region: str,
        predictions: list[dict[str, Any]],
        model_version: str | None = None,
    ) -> int:
        """Batch-INSERT forecast predictions in chunks of _INSERT_BATCH_SIZE.

        Builds an explicit multi-row VALUES list for each chunk so that 20
        rows result in exactly 1 INSERT statement rather than 20 round-trips.
        Commits once after all chunks are inserted.
        """
        if not predictions:
            return 0

        rows = []
        for pred in predictions:
            ts = pred.get("timestamp")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            hour = ts.hour if ts else 0

            rows.append(
                {
                    "id": str(uuid4()),
                    "forecast_id": forecast_id,
                    "region": region.lower(),
                    "forecast_hour": hour,
                    "predicted_price": pred["predicted_price"],
                    "confidence_lower": pred.get("confidence_lower"),
                    "confidence_upper": pred.get("confidence_upper"),
                    "model_version": model_version,
                }
            )

        try:
            # Insert in explicit multi-row VALUE chunks to minimise round-trips.
            for chunk_start in range(0, len(rows), self._INSERT_BATCH_SIZE):
                chunk = rows[chunk_start : chunk_start + self._INSERT_BATCH_SIZE]

                # Build (:id0,:forecast_id0,...), (:id1,:forecast_id1,...) list.
                placeholders = []
                params: dict[str, Any] = {}
                for i, row in enumerate(chunk):
                    placeholders.append(
                        f"(:id{i}, :forecast_id{i}, :region{i}, :forecast_hour{i},"
                        f" :predicted_price{i}, :confidence_lower{i},"
                        f" :confidence_upper{i}, :model_version{i})"
                    )
                    params[f"id{i}"] = row["id"]
                    params[f"forecast_id{i}"] = row["forecast_id"]
                    params[f"region{i}"] = row["region"]
                    params[f"forecast_hour{i}"] = row["forecast_hour"]
                    params[f"predicted_price{i}"] = row["predicted_price"]
                    params[f"confidence_lower{i}"] = row["confidence_lower"]
                    params[f"confidence_upper{i}"] = row["confidence_upper"]
                    params[f"model_version{i}"] = row["model_version"]

                await self._db.execute(
                    text(
                        "INSERT INTO forecast_observations"
                        "    (id, forecast_id, region, forecast_hour, predicted_price,"
                        "     confidence_lower, confidence_upper, model_version)"
                        f" VALUES {', '.join(placeholders)}"
                    ),
                    params,
                )

            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        return len(rows)

    # Maximum number of forecast rows to backfill in a single call when no
    # region filter is supplied.  Prevents unbounded memory usage if the
    # forecast_observations table has millions of unobserved rows.
    _BACKFILL_LIMIT = 10_000

    async def backfill_actuals(self, region: str | None = None) -> int:
        """Match unobserved forecasts to actual prices.

        When *region* is ``None`` the UPDATE is capped at ``_BACKFILL_LIMIT``
        rows (default 10 000) to prevent unbounded memory consumption.  A
        warning is logged when the limit is hit so operators know to call
        again or supply a region filter.
        """
        if region:
            query = text("""
                UPDATE forecast_observations fo
                SET
                    actual_price = ep.price_per_kwh,
                    observed_at = now()
                FROM electricity_prices ep
                WHERE fo.observed_at IS NULL
                  AND fo.region = ep.region
                  AND fo.forecast_hour = EXTRACT(HOUR FROM ep.timestamp)
                  AND ep.timestamp >= fo.created_at - INTERVAL '1 hour'
                  AND ep.timestamp <= fo.created_at + INTERVAL '25 hours'
                  AND fo.region = :region
            """)
            params: dict[str, Any] = {"region": region}
        else:
            # Without a region filter, limit the UPDATE to _BACKFILL_LIMIT
            # rows using a CTE that selects the eligible forecast_observation
            # IDs first.  This avoids a full-table scan / unbounded join
            # against electricity_prices.
            query = text("""
                WITH eligible AS (
                    SELECT fo.id, ep.price_per_kwh
                    FROM forecast_observations fo
                    JOIN electricity_prices ep
                      ON fo.region = ep.region
                     AND fo.forecast_hour = EXTRACT(HOUR FROM ep.timestamp)
                     AND ep.timestamp >= fo.created_at - INTERVAL '1 hour'
                     AND ep.timestamp <= fo.created_at + INTERVAL '25 hours'
                    WHERE fo.observed_at IS NULL
                    LIMIT :backfill_limit
                )
                UPDATE forecast_observations fo
                SET
                    actual_price = eligible.price_per_kwh,
                    observed_at = now()
                FROM eligible
                WHERE fo.id = eligible.id
            """)
            params = {"backfill_limit": self._BACKFILL_LIMIT}
            logger.warning(
                "No region filter supplied; capping backfill to prevent unbounded memory usage",
                limit=self._BACKFILL_LIMIT,
            )

        try:
            result = await self._db.execute(query, params)
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise

        count = result.rowcount
        if not region and count >= self._BACKFILL_LIMIT:
            logger.warning(
                "Backfill hit the row limit; there may be more unobserved rows. "
                "Consider calling again or supplying a region filter.",
                count=count,
                limit=self._BACKFILL_LIMIT,
            )

        return count

    async def insert_recommendation(
        self,
        user_id: str,
        recommendation_type: str,
        recommendation_data: dict[str, Any],
    ) -> str:
        """Record a recommendation served to a user. Returns the outcome ID."""
        outcome_id = str(uuid4())
        query = text("""
            INSERT INTO recommendation_outcomes
                (id, user_id, recommendation_type, recommendation_data)
            VALUES
                (:id, :user_id, :recommendation_type, :recommendation_data)
        """)

        try:
            await self._db.execute(
                query,
                {
                    "id": outcome_id,
                    "user_id": user_id,
                    "recommendation_type": recommendation_type,
                    "recommendation_data": json.dumps(recommendation_data, default=str),
                },
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        return outcome_id

    async def update_recommendation_response(
        self,
        outcome_id: str,
        accepted: bool,
        actual_savings: float | None = None,
    ) -> bool:
        """Update a recommendation outcome with user response."""
        query = text("""
            UPDATE recommendation_outcomes
            SET was_accepted = :accepted,
                actual_savings = :actual_savings,
                responded_at = now()
            WHERE id = :outcome_id
              AND responded_at IS NULL
        """)

        try:
            result = await self._db.execute(
                query,
                {
                    "outcome_id": outcome_id,
                    "accepted": accepted,
                    "actual_savings": actual_savings,
                },
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        return result.rowcount > 0

    async def get_accuracy_metrics(self, region: str, days: int = 7) -> dict[str, Any]:
        """Compute accuracy metrics for observed forecasts."""
        query = text("""
            SELECT
                COUNT(*) as total,
                AVG(ABS(predicted_price - actual_price) / NULLIF(actual_price, 0)) * 100 as mape,
                SQRT(AVG(POWER(predicted_price - actual_price, 2))) as rmse,
                AVG(CASE
                    WHEN actual_price BETWEEN confidence_lower AND confidence_upper
                    THEN 1.0 ELSE 0.0
                END) * 100 as coverage
            FROM forecast_observations
            WHERE observed_at IS NOT NULL
              AND region = :region
              AND created_at >= now() - make_interval(days => :days)
        """)

        result = await self._db.execute(query, {"region": region.lower(), "days": days})
        row = result.fetchone()

        if not row or row.total == 0:
            return {"total": 0, "mape": None, "rmse": None, "coverage": None}

        return {
            "total": row.total,
            "mape": round(float(row.mape), 2) if row.mape else None,
            "rmse": round(float(row.rmse), 6) if row.rmse else None,
            "coverage": round(float(row.coverage), 1) if row.coverage else None,
        }

    async def get_hourly_bias(self, region: str, days: int = 7) -> list[dict[str, Any]]:
        """Compute per-hour bias (predicted - actual)."""
        query = text("""
            SELECT
                forecast_hour as hour,
                AVG(predicted_price - actual_price) as avg_bias,
                COUNT(*) as count
            FROM forecast_observations
            WHERE observed_at IS NOT NULL
              AND region = :region
              AND created_at >= now() - make_interval(days => :days)
            GROUP BY forecast_hour
            ORDER BY forecast_hour
        """)

        result = await self._db.execute(query, {"region": region.lower(), "days": days})
        return [
            {
                "hour": row.hour,
                "avg_bias": round(float(row.avg_bias), 6),
                "count": row.count,
            }
            for row in result.fetchall()
        ]

    async def get_accuracy_by_version(self, region: str, days: int = 7) -> list[dict[str, Any]]:
        """Compute accuracy breakdown by model_version using SQL GROUP BY.

        All aggregation (MAPE, RMSE, coverage) is performed in the database,
        returning one pre-aggregated row per model version rather than fetching
        raw observation rows and aggregating in Python.  This eliminates the
        O(N) data transfer for large 7-day windows where N can be tens of
        thousands of rows per version.

        The ORDER BY mape ASC means callers can rely on the first entry being
        the best-performing model without any additional sorting.
        """
        query = text("""
            SELECT
                model_version,
                COUNT(*) AS count,
                AVG(
                    ABS(predicted_price - actual_price) / NULLIF(actual_price, 0)
                ) * 100 AS mape,
                SQRT(AVG(POWER(predicted_price - actual_price, 2))) AS rmse,
                AVG(
                    CASE
                        WHEN actual_price BETWEEN confidence_lower AND confidence_upper
                        THEN 1.0 ELSE 0.0
                    END
                ) * 100 AS coverage
            FROM forecast_observations
            WHERE observed_at IS NOT NULL
              AND region = :region
              AND created_at >= now() - make_interval(days => :days)
              AND model_version IS NOT NULL
            GROUP BY model_version
            ORDER BY mape ASC NULLS LAST
        """)

        result = await self._db.execute(query, {"region": region.lower(), "days": days})
        return [
            {
                "model_version": row.model_version,
                "count": row.count,
                "mape": round(float(row.mape), 2) if row.mape is not None else None,
                "rmse": round(float(row.rmse), 6) if row.rmse is not None else None,
                "coverage": round(float(row.coverage), 1) if row.coverage is not None else None,
            }
            for row in result.fetchall()
        ]
