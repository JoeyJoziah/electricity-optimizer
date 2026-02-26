"""
Observation Service

Thin orchestrator that delegates data access to ForecastObservationRepository.
Adds logging and business-level coordination on top of raw data operations.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.forecast_observation_repository import ForecastObservationRepository

logger = logging.getLogger(__name__)


class ObservationService:
    """
    Records forecasts and backfills actual prices so the learning loop can
    compute rolling accuracy, detect bias, and update ensemble weights.
    """

    def __init__(self, db: AsyncSession):
        self._repo = ForecastObservationRepository(db)

    async def record_forecast(
        self,
        forecast_id: str,
        region: str,
        predictions: List[Dict[str, Any]],
        model_version: Optional[str] = None,
    ) -> int:
        """Batch-INSERT forecast predictions into forecast_observations."""
        count = await self._repo.insert_forecasts(
            forecast_id, region, predictions, model_version
        )
        if count > 0:
            logger.info(
                "forecast_recorded",
                forecast_id=forecast_id,
                region=region,
                count=count,
            )
        return count

    async def observe_actuals_batch(
        self,
        region: Optional[str] = None,
    ) -> int:
        """Match unobserved forecast rows to actual prices."""
        count = await self._repo.backfill_actuals(region)
        logger.info("actuals_backfilled", region=region or "all", count=count)
        return count

    async def record_recommendation(
        self,
        user_id: str,
        recommendation_type: str,
        recommendation_data: Dict[str, Any],
    ) -> str:
        """Record a recommendation served to a user."""
        outcome_id = await self._repo.insert_recommendation(
            user_id, recommendation_type, recommendation_data
        )
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
        """Update a recommendation outcome with user response."""
        updated = await self._repo.update_recommendation_response(
            outcome_id, accepted, actual_savings
        )
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
        """Compute accuracy metrics for observed forecasts."""
        return await self._repo.get_accuracy_metrics(region, days)

    async def get_hourly_bias(
        self,
        region: str,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """Compute per-hour bias (predicted - actual) for bias correction."""
        return await self._repo.get_hourly_bias(region, days)

    async def get_model_accuracy_by_version(
        self,
        region: str,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """Compute accuracy breakdown by model_version."""
        return await self._repo.get_accuracy_by_version(region, days)

    async def archive_old_observations(self, days: int = 90):
        """Archive observations older than specified days."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Count before archival
        count_result = await self._repo._db.execute(
            text("SELECT COUNT(*) FROM forecast_observations WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        count = count_result.scalar() or 0

        if count == 0:
            return {"archived": 0, "message": "No old observations to archive"}

        # Delete old observations (in production, would move to archive table first)
        await self._repo._db.execute(
            text("DELETE FROM forecast_observations WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await self._repo._db.commit()

        logger.info("observations_archived", extra={"count": count, "cutoff_days": days})
        return {"archived": count, "cutoff_days": days}

    async def get_observation_summary(self):
        """Get summary statistics for observations."""
        result = await self._repo._db.execute(text("""
            SELECT
                COUNT(*) as total,
                MIN(created_at) as oldest,
                MAX(created_at) as newest
            FROM forecast_observations
        """))
        row = result.fetchone()
        if not row or not row[0]:
            return {"total": 0, "oldest": None, "newest": None}
        return {"total": row[0], "oldest": str(row[1]), "newest": str(row[2])}
