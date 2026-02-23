"""
Observation Service

Closes the feedback gap by recording forecast predictions alongside actual prices,
and tracking user responses to recommendations. Data accumulated here feeds the
nightly learning cycle (LearningService).
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ObservationService:
    """
    Records forecasts and backfills actual prices so the learning loop can
    compute rolling accuracy, detect bias, and update ensemble weights.
    """

    def __init__(self, db: AsyncSession):
        self._db = db

    async def record_forecast(
        self,
        forecast_id: str,
        region: str,
        predictions: List[Dict[str, Any]],
        model_version: Optional[str] = None,
    ) -> int:
        """
        Batch-INSERT forecast predictions into forecast_observations.

        Args:
            forecast_id: Unique ID grouping this forecast batch.
            region: Price region (e.g. "US", "UK").
            predictions: List of dicts with keys:
                timestamp, predicted_price, confidence_lower, confidence_upper
            model_version: Model version string.

        Returns:
            Number of rows inserted.
        """
        if not predictions:
            return 0

        rows = []
        for pred in predictions:
            ts = pred.get("timestamp")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            hour = ts.hour if ts else 0

            rows.append({
                "id": str(uuid4()),
                "forecast_id": forecast_id,
                "region": region,
                "forecast_hour": hour,
                "predicted_price": pred["predicted_price"],
                "confidence_lower": pred.get("confidence_lower"),
                "confidence_upper": pred.get("confidence_upper"),
                "model_version": model_version,
            })

        query = text("""
            INSERT INTO forecast_observations
                (id, forecast_id, region, forecast_hour, predicted_price,
                 confidence_lower, confidence_upper, model_version)
            VALUES
                (:id, :forecast_id, :region, :forecast_hour, :predicted_price,
                 :confidence_lower, :confidence_upper, :model_version)
        """)

        await self._db.execute(query, rows)
        await self._db.commit()

        logger.info(
            "forecast_recorded",
            forecast_id=forecast_id,
            region=region,
            count=len(rows),
        )
        return len(rows)

    async def observe_actuals_batch(
        self,
        region: Optional[str] = None,
    ) -> int:
        """
        Match unobserved forecast rows to actual prices in electricity_prices.

        Joins on region + hour-of-day within a reasonable time window,
        backfilling actual_price and observed_at.

        Args:
            region: Optional filter to a single region.

        Returns:
            Number of rows updated.
        """
        region_filter = ""
        params: Dict[str, Any] = {}
        if region:
            region_filter = "AND fo.region = :region"
            params["region"] = region

        query = text(f"""
            UPDATE forecast_observations fo
            SET
                actual_price = ep.price_per_kwh,
                observed_at = now()
            FROM electricity_prices ep
            WHERE fo.observed_at IS NULL
              AND LOWER(fo.region) = LOWER(ep.region)
              AND fo.forecast_hour = EXTRACT(HOUR FROM ep.timestamp)
              AND ep.timestamp >= fo.created_at - INTERVAL '1 hour'
              AND ep.timestamp <= fo.created_at + INTERVAL '25 hours'
              {region_filter}
        """)

        result = await self._db.execute(query, params)
        await self._db.commit()

        count = result.rowcount
        logger.info("actuals_backfilled", region=region or "all", count=count)
        return count

    async def record_recommendation(
        self,
        user_id: str,
        recommendation_type: str,
        recommendation_data: Dict[str, Any],
    ) -> str:
        """
        Record a recommendation that was served to a user.

        Args:
            user_id: User UUID.
            recommendation_type: e.g. "switching", "usage".
            recommendation_data: Full recommendation payload.

        Returns:
            The outcome ID for later response tracking.
        """
        outcome_id = str(uuid4())
        query = text("""
            INSERT INTO recommendation_outcomes
                (id, user_id, recommendation_type, recommendation_data)
            VALUES
                (:id, :user_id, :recommendation_type, :recommendation_data)
        """)

        await self._db.execute(query, {
            "id": outcome_id,
            "user_id": user_id,
            "recommendation_type": recommendation_type,
            "recommendation_data": json.dumps(recommendation_data, default=str),
        })
        await self._db.commit()

        logger.info(
            "recommendation_recorded",
            outcome_id=outcome_id,
            user_id=user_id,
            type=recommendation_type,
        )
        return outcome_id

    async def record_recommendation_response(
        self,
        outcome_id: str,
        accepted: bool,
        actual_savings: Optional[float] = None,
    ) -> bool:
        """
        Update a recommendation outcome with user response.

        Args:
            outcome_id: The outcome row ID.
            accepted: Whether the user accepted the recommendation.
            actual_savings: Measured savings (if available).

        Returns:
            True if the row was found and updated.
        """
        query = text("""
            UPDATE recommendation_outcomes
            SET was_accepted = :accepted,
                actual_savings = :actual_savings,
                responded_at = now()
            WHERE id = :outcome_id
              AND responded_at IS NULL
        """)

        result = await self._db.execute(query, {
            "outcome_id": outcome_id,
            "accepted": accepted,
            "actual_savings": actual_savings,
        })
        await self._db.commit()

        updated = result.rowcount > 0
        if updated:
            logger.info(
                "recommendation_response_recorded",
                outcome_id=outcome_id,
                accepted=accepted,
            )
        return updated

    async def get_forecast_accuracy(
        self,
        region: str,
        days: int = 7,
    ) -> Dict[str, Any]:
        """
        Compute accuracy metrics for observed forecasts.

        Args:
            region: Region to filter.
            days: Lookback window.

        Returns:
            Dict with mape, rmse, count, and coverage.
        """
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
              AND LOWER(region) = LOWER(:region)
              AND created_at >= now() - make_interval(days => :days)
        """)

        result = await self._db.execute(query, {"region": region, "days": days})
        row = result.fetchone()

        if not row or row.total == 0:
            return {"total": 0, "mape": None, "rmse": None, "coverage": None}

        return {
            "total": row.total,
            "mape": round(float(row.mape), 2) if row.mape else None,
            "rmse": round(float(row.rmse), 6) if row.rmse else None,
            "coverage": round(float(row.coverage), 1) if row.coverage else None,
        }

    async def get_hourly_bias(
        self,
        region: str,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Compute per-hour bias (predicted - actual) for bias correction.

        Returns:
            List of {hour, avg_bias, count} dicts.
        """
        query = text("""
            SELECT
                forecast_hour as hour,
                AVG(predicted_price - actual_price) as avg_bias,
                COUNT(*) as count
            FROM forecast_observations
            WHERE observed_at IS NOT NULL
              AND LOWER(region) = LOWER(:region)
              AND created_at >= now() - make_interval(days => :days)
            GROUP BY forecast_hour
            ORDER BY forecast_hour
        """)

        result = await self._db.execute(query, {"region": region, "days": days})
        rows = result.fetchall()

        return [
            {
                "hour": row.hour,
                "avg_bias": round(float(row.avg_bias), 6),
                "count": row.count,
            }
            for row in rows
        ]

    async def get_model_accuracy_by_version(
        self,
        region: str,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Compute accuracy breakdown by model_version for ensemble weight tuning.

        Returns:
            List of {model_version, mape, rmse, count} dicts.
        """
        query = text("""
            SELECT
                model_version,
                COUNT(*) as count,
                AVG(ABS(predicted_price - actual_price) / NULLIF(actual_price, 0)) * 100 as mape,
                SQRT(AVG(POWER(predicted_price - actual_price, 2))) as rmse
            FROM forecast_observations
            WHERE observed_at IS NOT NULL
              AND LOWER(region) = LOWER(:region)
              AND created_at >= now() - make_interval(days => :days)
              AND model_version IS NOT NULL
            GROUP BY model_version
            ORDER BY mape ASC
        """)

        result = await self._db.execute(query, {"region": region, "days": days})
        rows = result.fetchall()

        return [
            {
                "model_version": row.model_version,
                "count": row.count,
                "mape": round(float(row.mape), 2) if row.mape else None,
                "rmse": round(float(row.rmse), 6) if row.rmse else None,
            }
            for row in rows
        ]
