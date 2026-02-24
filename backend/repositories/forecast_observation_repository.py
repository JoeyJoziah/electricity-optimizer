"""
Forecast Observation Repository

Data access layer for the forecast_observations and recommendation_outcomes tables.
Extracted from ObservationService to separate SQL from business logic.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ForecastObservationRepository:
    """Raw SQL data access for forecast observations and recommendation outcomes."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def insert_forecasts(
        self,
        forecast_id: str,
        region: str,
        predictions: List[Dict[str, Any]],
        model_version: Optional[str] = None,
    ) -> int:
        """Batch-INSERT forecast predictions."""
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
                "region": region.lower(),
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
        return len(rows)

    async def backfill_actuals(self, region: Optional[str] = None) -> int:
        """Match unobserved forecasts to actual prices."""
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
            params: Dict[str, Any] = {"region": region}
        else:
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
            """)
            params = {}

        result = await self._db.execute(query, params)
        await self._db.commit()
        return result.rowcount

    async def insert_recommendation(
        self,
        user_id: str,
        recommendation_type: str,
        recommendation_data: Dict[str, Any],
    ) -> str:
        """Record a recommendation served to a user. Returns the outcome ID."""
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
        return outcome_id

    async def update_recommendation_response(
        self,
        outcome_id: str,
        accepted: bool,
        actual_savings: Optional[float] = None,
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

        result = await self._db.execute(query, {
            "outcome_id": outcome_id,
            "accepted": accepted,
            "actual_savings": actual_savings,
        })
        await self._db.commit()
        return result.rowcount > 0

    async def get_accuracy_metrics(
        self, region: str, days: int = 7
    ) -> Dict[str, Any]:
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

    async def get_hourly_bias(
        self, region: str, days: int = 7
    ) -> List[Dict[str, Any]]:
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

    async def get_accuracy_by_version(
        self, region: str, days: int = 7
    ) -> List[Dict[str, Any]]:
        """Compute accuracy breakdown by model_version."""
        query = text("""
            SELECT
                model_version,
                COUNT(*) as count,
                AVG(ABS(predicted_price - actual_price) / NULLIF(actual_price, 0)) * 100 as mape,
                SQRT(AVG(POWER(predicted_price - actual_price, 2))) as rmse
            FROM forecast_observations
            WHERE observed_at IS NOT NULL
              AND region = :region
              AND created_at >= now() - make_interval(days => :days)
              AND model_version IS NOT NULL
            GROUP BY model_version
            ORDER BY mape ASC
        """)

        result = await self._db.execute(query, {"region": region.lower(), "days": days})
        return [
            {
                "model_version": row.model_version,
                "count": row.count,
                "mape": round(float(row.mape), 2) if row.mape else None,
                "rmse": round(float(row.rmse), 6) if row.rmse else None,
            }
            for row in result.fetchall()
        ]
