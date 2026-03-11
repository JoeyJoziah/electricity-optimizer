"""
Learning Service

Nightly learning cycle inspired by AgentDB's NightlyLearner pattern.
Computes rolling accuracy, detects systematic bias, adjusts ensemble
weights, and prunes stale patterns from the vector store.

Designed to run as a batch job (via POST /internal/learn).

Weight persistence
------------------
Ensemble weights are written to two stores on every successful update:

1. Redis  (fast, ephemeral) — EnsemblePredictor reads this on the hot path.
2. PostgreSQL model_config table (durable) — survives Render restarts.

On EnsemblePredictor startup the load order is:
  Redis (if available) -> PostgreSQL (fallback) -> hard-coded defaults.
"""

import json
import logging
from typing import Optional, Dict, Any, List

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from lib.tracing import traced
from services.observation_service import ObservationService
from services.hnsw_vector_store import HNSWVectorStore
from services.vector_store import price_curve_to_vector

logger = logging.getLogger(__name__)

# Weight bounds to prevent any single model from dominating or being zeroed out
MIN_WEIGHT = 0.1
MAX_WEIGHT = 0.8

# Canonical model name used as the primary key in model_config
ENSEMBLE_MODEL_NAME = "ensemble"


class LearningService:
    """
    Runs the nightly learning cycle:
    1. Compute rolling accuracy (MAPE/RMSE) per model
    2. Detect systematic bias by hour-of-day
    3. Update ensemble weights in Redis AND PostgreSQL
    4. Store bias correction vectors in the vector store
    5. Prune low-quality patterns
    """

    def __init__(
        self,
        observation_service: ObservationService,
        vector_store: HNSWVectorStore,
        redis_client: Optional[Any] = None,
        db_session: Optional[AsyncSession] = None,
    ):
        self._obs = observation_service
        self._vs = vector_store
        self._redis = redis_client
        self._db = db_session

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
        async with traced("ml.compute_accuracy", attributes={"ml.region": region, "ml.days": days}):
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
        accuracy_metrics: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, float]]:
        """
        Compute new ensemble weights based on model accuracy.

        Uses inverse-MAPE weighting: models with lower error get higher weight.
        Writes result to:
          - Redis key ``model:ensemble_weights`` (fast, ephemeral)
          - PostgreSQL ``model_config`` table via ModelConfigRepository (durable)

        Args:
            region: Region code used to scope the accuracy query.
            days: Lookback window in days.
            accuracy_metrics: Optional pre-computed metrics dict to attach to
                the PostgreSQL record (mape, rmse, coverage, etc.).

        Returns:
            New weight dict, or None if insufficient data.
        """
        async with traced("ml.update_weights", attributes={"ml.region": region, "ml.days": days}):
            model_stats = await self._obs.get_model_accuracy_by_version(region, days)

        if not model_stats or len(model_stats) < 1:
            logger.info("insufficient_data_for_weight_update region=%s", region)
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

        # Convert to the format EnsemblePredictor expects:
        # {"model_name": {"weight": 0.5}, ...}
        ensemble_payload = {k: {"weight": v} for k, v in weights.items()}

        # --- Store in Redis (fast, ephemeral) ---
        if self._redis:
            try:
                await self._redis.set(
                    "model:ensemble_weights",
                    json.dumps(ensemble_payload),
                )
                logger.info(
                    "ensemble_weights_updated_redis region=%s weights=%s",
                    region,
                    weights,
                )
            except Exception as e:
                logger.warning("redis_weight_update_failed error=%s", str(e))

        # --- Persist to PostgreSQL (durable, survives restarts) ---
        if self._db is not None:
            await self._persist_weights_to_db(
                weights=ensemble_payload,
                region=region,
                days=days,
                accuracy_metrics=accuracy_metrics or {},
                model_stats=model_stats,
            )

        return weights

    async def _persist_weights_to_db(
        self,
        weights: Dict[str, Any],
        region: str,
        days: int,
        accuracy_metrics: Dict[str, Any],
        model_stats: List[Dict[str, Any]],
    ) -> None:
        """
        Write ensemble weights to the PostgreSQL model_config table AND
        create a new immutable ModelVersion record for lineage tracking.

        Two separate persistence operations are performed:
        1. model_config (legacy store) — overwritten on every cycle so
           EnsemblePredictor can do a simple get_active_config() lookup.
        2. model_versions (versioning store) — a new append-only row is
           inserted so every nightly run produces a trackable version.
           If the cycle produces improved accuracy (lower MAPE) the new
           version is automatically promoted to active.

        Errors are caught and logged so that a DB failure never prevents the
        in-memory learning cycle from completing.
        """
        try:
            from repositories.model_config_repository import ModelConfigRepository
            from datetime import datetime, timezone

            repo = ModelConfigRepository(self._db)
            # Build a version string based on the best-performing model
            # (first entry from get_model_accuracy_by_version which orders by MAPE ASC)
            best_version = model_stats[0].get("model_version", "unknown")
            # Attach provenance metadata
            metadata = {
                "region": region,
                "days": days,
                "model_stats_count": len(model_stats),
                "trained_at": datetime.now(timezone.utc).isoformat(),
            }
            await repo.save_config(
                model_name=ENSEMBLE_MODEL_NAME,
                version=best_version,
                weights=weights,
                metadata=metadata,
                metrics=accuracy_metrics,
            )
            logger.info(
                "ensemble_weights_persisted_to_db model_name=%s version=%s",
                ENSEMBLE_MODEL_NAME,
                best_version,
            )
        except Exception as e:
            logger.warning(
                "db_weight_persist_failed error=%s", str(e)
            )

        # --- Create a new ModelVersion record for lineage tracking ---
        try:
            from services.model_version_service import ModelVersionService
            from datetime import datetime, timezone

            mv_svc = ModelVersionService(self._db)
            new_version = await mv_svc.create_version(
                model_name=ENSEMBLE_MODEL_NAME,
                config=weights,
                metrics=accuracy_metrics,
            )

            # Promote the new version if it represents an improvement over the
            # currently active one.  We use MAPE as the primary signal.
            active = await mv_svc.get_active_version(ENSEMBLE_MODEL_NAME)
            new_mape = accuracy_metrics.get("mape") if accuracy_metrics else None
            if active is None:
                # No active version yet — always promote the first one.
                await mv_svc.promote_version(new_version.id)
                logger.info(
                    "model_version_promoted_first model_version=%s",
                    new_version.version_tag,
                )
            elif new_mape is not None:
                active_mape = active.metrics.get("mape") if active.metrics else None
                if active_mape is None or new_mape < active_mape:
                    await mv_svc.promote_version(new_version.id)
                    logger.info(
                        "model_version_promoted_improved model_version=%s "
                        "new_mape=%.4f active_mape=%s",
                        new_version.version_tag,
                        new_mape,
                        active_mape,
                    )
                else:
                    logger.info(
                        "model_version_not_promoted model_version=%s "
                        "new_mape=%.4f active_mape=%.4f",
                        new_version.version_tag,
                        new_mape,
                        active_mape,
                    )
        except Exception as e:
            logger.warning(
                "model_version_create_failed error=%s", str(e)
            )

    async def load_weights_from_db(
        self,
        model_name: str = ENSEMBLE_MODEL_NAME,
    ) -> Optional[Dict[str, Any]]:
        """
        Load the active ensemble weights from PostgreSQL.

        Called by EnsemblePredictor on startup when Redis is unavailable.
        Returns the weights_json dict or None if no active config exists.
        """
        if self._db is None:
            return None
        try:
            from repositories.model_config_repository import ModelConfigRepository

            repo = ModelConfigRepository(self._db)
            config = await repo.get_active_config(model_name)
            if config is None:
                logger.info(
                    "no_active_db_weights model_name=%s using_defaults=true",
                    model_name,
                )
                return None
            logger.info(
                "ensemble_weights_loaded_from_db model_name=%s version=%s",
                model_name,
                config.model_version,
            )
            return config.weights_json
        except Exception as e:
            logger.warning(
                "db_weight_load_failed model_name=%s error=%s", model_name, str(e)
            )
            return None

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

        vec_id = await self._vs.async_insert(
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
            "bias_correction_stored region=%s vector_id=%s max_bias=%s",
            region,
            vec_id,
            float(np.max(np.abs(bias_vector))),
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
        count = await self._vs.async_prune(min_confidence, min_usage)
        logger.info("stale_patterns_pruned count=%d", count)
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
                "rolling_accuracy_computed region=%s accuracy=%s",
                region,
                accuracy,
            )

            # 2. Update ensemble weights (Redis + PostgreSQL)
            weights = await self.update_ensemble_weights(
                region,
                days,
                accuracy_metrics=accuracy,
            )
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
                logger.warning("redis_mape_update_failed error=%s", str(e))

        logger.info("learning_cycle_complete results=%s", results)
        return results
