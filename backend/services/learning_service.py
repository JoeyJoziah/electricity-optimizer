"""
Learning Service

Nightly learning cycle inspired by AgentDB's NightlyLearner pattern.
Computes rolling accuracy, detects systematic bias, adjusts ensemble
weights, and prunes stale patterns from the vector store.

Designed to run as a batch job (via POST /internal/learn).
"""

import json
import logging
from typing import Optional, Dict, Any, List

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from services.observation_service import ObservationService
from services.hnsw_vector_store import HNSWVectorStore
from services.vector_store import price_curve_to_vector

logger = logging.getLogger(__name__)

# Weight bounds to prevent any single model from dominating or being zeroed out
MIN_WEIGHT = 0.1
MAX_WEIGHT = 0.8


class LearningService:
    """
    Runs the nightly learning cycle:
    1. Compute rolling accuracy (MAPE/RMSE) per model
    2. Detect systematic bias by hour-of-day
    3. Update ensemble weights in Redis
    4. Store bias correction vectors in the vector store
    5. Prune low-quality patterns
    """

    def __init__(
        self,
        observation_service: ObservationService,
        vector_store: HNSWVectorStore,
        redis_client: Optional[Any] = None,
    ):
        self._obs = observation_service
        self._vs = vector_store
        self._redis = redis_client

    async def compute_rolling_accuracy(
        self,
        region: str,
        days: int = 7,
    ) -> Dict[str, Any]:
        """
        Compute rolling accuracy metrics from observed forecasts.

        Returns:
            Dict with mape, rmse, count, coverage.
        """
        return await self._obs.get_forecast_accuracy(region, days)

    async def detect_bias(
        self,
        region: str,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Detect systematic over/under-prediction by hour.

        Returns:
            List of {hour, avg_bias, count} dicts.
        """
        return await self._obs.get_hourly_bias(region, days)

    async def update_ensemble_weights(
        self,
        region: str,
        days: int = 7,
    ) -> Optional[Dict[str, float]]:
        """
        Compute new ensemble weights based on model accuracy.

        Uses inverse-MAPE weighting: models with lower error get higher weight.
        Writes result to Redis key `model:ensemble_weights`.

        Returns:
            New weight dict, or None if insufficient data.
        """
        model_stats = await self._obs.get_model_accuracy_by_version(region, days)

        if not model_stats or len(model_stats) < 1:
            logger.info("insufficient_data_for_weight_update", region=region)
            return None

        # Inverse-MAPE weighting
        weights: Dict[str, float] = {}
        inverse_errors = {}
        for stat in model_stats:
            version = stat["model_version"]
            mape = stat.get("mape")
            if mape and mape > 0:
                inverse_errors[version] = 1.0 / mape
            else:
                inverse_errors[version] = 1.0

        total_inverse = sum(inverse_errors.values())
        if total_inverse == 0:
            return None

        for version, inv_err in inverse_errors.items():
            raw_weight = inv_err / total_inverse
            # Clamp to bounds
            weights[version] = max(MIN_WEIGHT, min(MAX_WEIGHT, raw_weight))

        # Re-normalize after clamping
        total = sum(weights.values())
        if total > 0:
            weights = {k: round(v / total, 4) for k, v in weights.items()}

        # Store in Redis for EnsemblePredictor to read
        if self._redis:
            try:
                # Convert to the format EnsemblePredictor expects:
                # {"model_name": {"weight": 0.5}, ...}
                redis_payload = {k: {"weight": v} for k, v in weights.items()}
                await self._redis.set(
                    "model:ensemble_weights",
                    json.dumps(redis_payload),
                )
                logger.info(
                    "ensemble_weights_updated",
                    region=region,
                    weights=weights,
                )
            except Exception as e:
                logger.warning("redis_weight_update_failed", error=str(e))

        return weights

    async def store_bias_correction(
        self,
        region: str,
        days: int = 7,
    ) -> Optional[str]:
        """
        Store hourly bias as a correction vector in the vector store.

        The 24-element vector represents average prediction error per hour.
        Downstream consumers can subtract this from raw predictions.

        Returns:
            Vector ID if stored, None if insufficient data.
        """
        bias_data = await self.detect_bias(region, days)

        if not bias_data:
            return None

        # Build a 24-hour bias vector
        bias_vector = np.zeros(24, dtype=np.float32)
        for entry in bias_data:
            hour = entry["hour"]
            if 0 <= hour < 24:
                bias_vector[hour] = entry["avg_bias"]

        # Normalize for cosine similarity storage
        norm_vector = price_curve_to_vector(bias_vector.tolist(), target_dim=24)

        vec_id = self._vs.insert(
            domain="bias_correction",
            vector=norm_vector,
            metadata={
                "region": region,
                "days": days,
                "raw_bias": bias_vector.tolist(),
            },
            confidence=1.0,
        )

        logger.info(
            "bias_correction_stored",
            region=region,
            vector_id=vec_id,
            max_bias=float(np.max(np.abs(bias_vector))),
        )
        return vec_id

    async def prune_stale_patterns(
        self,
        min_confidence: float = 0.3,
        min_usage: int = 0,
    ) -> int:
        """
        Remove low-quality vectors from the store.

        Returns:
            Number of vectors pruned.
        """
        count = self._vs.prune(min_confidence, min_usage)
        logger.info("stale_patterns_pruned", count=count)
        return count

    async def run_full_cycle(
        self,
        regions: Optional[List[str]] = None,
        days: int = 7,
    ) -> Dict[str, Any]:
        """
        Run the complete nightly learning cycle.

        Args:
            regions: List of regions to process (defaults to ["US"]).
            days: Lookback window for accuracy computation.

        Returns:
            Summary of what was done.
        """
        if regions is None:
            regions = ["US"]

        results: Dict[str, Any] = {
            "regions_processed": [],
            "weights_updated": {},
            "bias_corrections": {},
            "pruned": 0,
        }

        for region in regions:
            # 1. Compute accuracy
            accuracy = await self.compute_rolling_accuracy(region, days)
            logger.info(
                "rolling_accuracy_computed",
                region=region,
                accuracy=accuracy,
            )

            # 2. Update ensemble weights
            weights = await self.update_ensemble_weights(region, days)
            if weights:
                results["weights_updated"][region] = weights

            # 3. Store bias correction
            bias_id = await self.store_bias_correction(region, days)
            if bias_id:
                results["bias_corrections"][region] = bias_id

            results["regions_processed"].append({
                "region": region,
                "accuracy": accuracy,
            })

        # 4. Prune stale patterns
        results["pruned"] = await self.prune_stale_patterns()

        # 5. Update model accuracy in Redis for the /model-info endpoint
        if self._redis and results["regions_processed"]:
            try:
                primary = results["regions_processed"][0]["accuracy"]
                if primary.get("mape") is not None:
                    await self._redis.set(
                        "model:recent_mape",
                        str(primary["mape"]),
                    )
            except Exception as e:
                logger.warning("redis_mape_update_failed", error=str(e))

        logger.info("learning_cycle_complete", results=results)
        return results
