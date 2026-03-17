"""
A/B Test Service

Manages per-user model version assignments and prediction accuracy tracking
for A/B tests.  Backed by the two tables added in migration 033:

  model_predictions    — per-user, per-version prediction events used to
                         compute version-level MAPE and MAE after the test.

  model_ab_assignments — persistent user → model_version mapping so the
                         same user always receives the same version within
                         a test window.

The assignment algorithm uses consistent hashing so no DB write is required
on the hot path; a record is only persisted lazily the first time a user
is observed.

Public API
----------
assign_user(user_id, version_a, version_b, split_ratio=0.5)
    Deterministically assign a user to a model version.  Persists the
    assignment if it does not already exist.  Returns the assigned version.

get_assignment(user_id)
    Return the persisted model_version for a user, or None.

record_prediction(user_id, model_version, region, predicted, actual=None)
    Store a prediction event.  actual and error_pct may be None at
    prediction time and backfilled later via update_actual().

update_actual(prediction_id, actual_value)
    Set the actual_value and compute error_pct on an existing prediction row.

get_split_metrics()
    Return accuracy metrics (MAPE, MAE, count) grouped by model_version.

auto_promote(version_a, version_b, threshold=0.05, min_predictions=100)
    If the challenger (version_b) beats the champion (version_a) by at
    least `threshold` on MAPE and has at least `min_predictions` samples,
    return the winning version string.  Returns None otherwise.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _hash_user_to_bucket(user_id: str, salt: str = "ab_split") -> int:
    """
    Deterministically map a user_id to an integer in [0, 99].

    The salt parameter allows the split to be varied per test without
    requiring a DB lookup for the test UUID.

    Args:
        user_id: UUID string identifying the user.
        salt:    Additional entropy to differentiate multiple tests.

    Returns:
        Integer in range [0, 99].
    """
    hash_input = f"{salt}:{user_id}".encode("utf-8")
    hash_int = int(hashlib.sha256(hash_input).hexdigest(), 16)
    return hash_int % 100


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ABTestService:
    """
    Manages A/B split assignments and prediction accuracy tracking.

    This service is intentionally kept separate from ModelVersionService so
    that the hot-path prediction code can import it without pulling in all
    of the version lifecycle management code.

    Usage::

        svc = ABTestService(db)

        # Assign a user (idempotent — same user always gets same version)
        version = await svc.assign_user(user_id, "v1.0", "v2.0", split_ratio=0.5)

        # Record a prediction
        pred_id = await svc.record_prediction(user_id, version, "NY", 0.142)

        # Later, backfill the actual value
        await svc.update_actual(pred_id, actual_value=0.138)

        # Check split metrics
        metrics = await svc.get_split_metrics()
        # → [{"model_version": "v1.0", "mape": 4.8, "mae": 0.006, "count": 312},
        #    {"model_version": "v2.0", "mape": 4.1, "mae": 0.005, "count": 289}]

        # Auto-promote if challenger wins
        winner = await svc.auto_promote("v1.0", "v2.0", threshold=0.05, min_predictions=100)
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    async def assign_user(
        self,
        user_id: str,
        version_a: str,
        version_b: str,
        split_ratio: float = 0.5,
        salt: str = "ab_split",
    ) -> str:
        """
        Deterministically assign a user to one of two model versions.

        The assignment is computed via consistent hashing so the same
        (user_id, salt) pair always maps to the same version.  The result
        is persisted to model_ab_assignments on first call; subsequent
        calls for the same user_id return the persisted version.

        Args:
            user_id:     UUID string of the user to assign.
            version_a:   Name / tag of the control version (A).
            version_b:   Name / tag of the challenger version (B).
            split_ratio: Fraction of traffic routed to version_a.
                         Must be in (0.0, 1.0).  Defaults to 0.5.
            salt:        Hash salt — change to reset assignments for a
                         new test while keeping existing records.

        Returns:
            The assigned model version string (either version_a or version_b).
        """
        if not (0.0 < split_ratio < 1.0):
            raise ValueError(f"split_ratio must be strictly between 0.0 and 1.0, got {split_ratio}")

        # Check for an existing persistent assignment first
        existing = await self.get_assignment(user_id)
        if existing is not None:
            return existing

        # Compute deterministic bucket
        bucket_pct = _hash_user_to_bucket(user_id, salt)
        split_pct = int(split_ratio * 100)
        assigned_version = version_a if bucket_pct < split_pct else version_b

        # Persist
        new_id = str(uuid4())
        now = datetime.now(timezone.utc)
        try:
            await self._db.execute(
                text(
                    "INSERT INTO model_ab_assignments"
                    "    (id, user_id, model_version, assigned_at)"
                    " VALUES (:id, :user_id, :model_version, :assigned_at)"
                    " ON CONFLICT (user_id) DO NOTHING"
                ),
                {
                    "id": new_id,
                    "user_id": user_id,
                    "model_version": assigned_version,
                    "assigned_at": now,
                },
            )
            await self._db.commit()
        except Exception as exc:
            await self._db.rollback()
            logger.error(
                "ab_assignment_persist_failed",
                user_id=user_id,
                error=str(exc),
            )
            raise

        logger.info(
            "ab_assignment_created",
            user_id=user_id,
            model_version=assigned_version,
        )
        return assigned_version

    async def get_assignment(self, user_id: str) -> Optional[str]:
        """
        Return the persisted model_version for a user, or None.

        Args:
            user_id: UUID string of the user to look up.

        Returns:
            model_version string if a record exists, otherwise None.
        """
        result = await self._db.execute(
            text("SELECT model_version" "  FROM model_ab_assignments" " WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        row = result.fetchone()
        if row is None:
            return None
        return str(row.model_version)

    # ------------------------------------------------------------------
    # Prediction recording
    # ------------------------------------------------------------------

    async def record_prediction(
        self,
        user_id: str,
        model_version: str,
        region: str,
        predicted_value: float,
        actual_value: Optional[float] = None,
    ) -> str:
        """
        Persist a prediction event for accuracy tracking.

        actual_value and error_pct may be None at prediction time.
        Call update_actual() later to backfill the observed outcome.

        Also updates the last_prediction_at timestamp on the assignment
        record so that user engagement can be tracked.

        Args:
            user_id:         UUID string of the user.
            model_version:   Version tag that served this prediction.
            region:          Region code (e.g. "NY", "CA").
            predicted_value: Raw prediction output.
            actual_value:    Observed actual value (optional at insert time).

        Returns:
            UUID string of the newly created prediction record.
        """
        new_id = str(uuid4())
        now = datetime.now(timezone.utc)

        error_pct: Optional[float] = None
        if actual_value is not None and actual_value != 0.0:
            error_pct = abs(predicted_value - actual_value) / abs(actual_value) * 100.0

        try:
            await self._db.execute(
                text(
                    "INSERT INTO model_predictions"
                    "    (id, model_version, user_id, region,"
                    "     predicted_value, actual_value, error_pct, created_at)"
                    " VALUES"
                    "    (:id, :model_version, :user_id, :region,"
                    "     :predicted_value, :actual_value, :error_pct, :created_at)"
                ),
                {
                    "id": new_id,
                    "model_version": model_version,
                    "user_id": user_id,
                    "region": region,
                    "predicted_value": predicted_value,
                    "actual_value": actual_value,
                    "error_pct": error_pct,
                    "created_at": now,
                },
            )

            # Update last_prediction_at on the assignment record (best-effort)
            await self._db.execute(
                text(
                    "UPDATE model_ab_assignments"
                    "   SET last_prediction_at = :ts"
                    " WHERE user_id = :user_id"
                ),
                {"ts": now, "user_id": user_id},
            )

            await self._db.commit()
        except Exception as exc:
            await self._db.rollback()
            logger.error(
                "prediction_record_failed",
                user_id=user_id,
                model_version=model_version,
                error=str(exc),
            )
            raise

        logger.debug(
            "prediction_recorded",
            prediction_id=new_id,
            model_version=model_version,
            user_id=user_id,
        )
        return new_id

    async def update_actual(
        self,
        prediction_id: str,
        actual_value: float,
    ) -> bool:
        """
        Backfill the actual value and compute error_pct on an existing row.

        Args:
            prediction_id: UUID of the model_predictions row to update.
            actual_value:  The observed actual value.

        Returns:
            True if the row was found and updated, False otherwise.
        """
        # Fetch the predicted_value so we can compute error_pct
        result = await self._db.execute(
            text("SELECT predicted_value" "  FROM model_predictions" " WHERE id = :prediction_id"),
            {"prediction_id": prediction_id},
        )
        row = result.fetchone()
        if row is None:
            logger.warning("update_actual_not_found", prediction_id=prediction_id)
            return False

        predicted = float(row.predicted_value)
        error_pct: Optional[float] = None
        if actual_value != 0.0:
            error_pct = abs(predicted - actual_value) / abs(actual_value) * 100.0

        try:
            await self._db.execute(
                text(
                    "UPDATE model_predictions"
                    "   SET actual_value = :actual_value,"
                    "       error_pct    = :error_pct"
                    " WHERE id = :prediction_id"
                ),
                {
                    "prediction_id": prediction_id,
                    "actual_value": actual_value,
                    "error_pct": error_pct,
                },
            )
            await self._db.commit()
        except Exception as exc:
            await self._db.rollback()
            logger.error(
                "update_actual_failed",
                prediction_id=prediction_id,
                error=str(exc),
            )
            raise

        return True

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    async def get_split_metrics(self) -> List[Dict[str, Any]]:
        """
        Return accuracy metrics grouped by model_version.

        Only rows where error_pct is not NULL are included in MAPE/MAE
        aggregation (i.e. rows that have been backfilled with actual values).

        Returns:
            List of dicts, each with:
                model_version (str)
                mape          (float | None)  — mean absolute percentage error
                mae           (float | None)  — mean absolute error
                count         (int)           — total predictions (incl. no-actual)
                observed      (int)           — predictions with actual value set
        """
        result = await self._db.execute(
            text(
                "SELECT"
                "    model_version,"
                "    AVG(error_pct)                            AS mape,"
                "    AVG(ABS(predicted_value - actual_value))  AS mae,"
                "    COUNT(*)                                  AS total_count,"
                "    COUNT(error_pct)                          AS observed_count"
                "  FROM model_predictions"
                " GROUP BY model_version"
                " ORDER BY mape ASC NULLS LAST"
            )
        )
        rows = result.fetchall()

        metrics = []
        for row in rows:
            metrics.append(
                {
                    "model_version": row.model_version,
                    "mape": float(row.mape) if row.mape is not None else None,
                    "mae": float(row.mae) if row.mae is not None else None,
                    "count": int(row.total_count),
                    "observed": int(row.observed_count),
                }
            )
        return metrics

    # ------------------------------------------------------------------
    # Auto-promote
    # ------------------------------------------------------------------

    async def auto_promote(
        self,
        version_a: str,
        version_b: str,
        threshold: float = 0.05,
        min_predictions: int = 100,
    ) -> Optional[str]:
        """
        Return the winning version if version_b outperforms version_a.

        A winner is declared when all of the following hold:
          1. version_b has at least `min_predictions` observed predictions.
          2. version_b MAPE < version_a MAPE * (1 - threshold).
             i.e. version_b must be better by at least `threshold` fraction.

        The method returns the version string of the winner, or None if the
        conditions are not met (insufficient data or no significant improvement).

        Args:
            version_a:       Baseline model version tag.
            version_b:       Challenger model version tag.
            threshold:       Minimum relative improvement required (default 0.05 = 5%).
            min_predictions: Minimum number of observed predictions for version_b
                             before a winner can be declared (default 100).

        Returns:
            Winning version string, or None if no winner yet.
        """
        metrics = await self.get_split_metrics()

        metrics_by_version = {m["model_version"]: m for m in metrics}

        a_metrics = metrics_by_version.get(version_a)
        b_metrics = metrics_by_version.get(version_b)

        if a_metrics is None or b_metrics is None:
            logger.info(
                "auto_promote_insufficient_data",
                version_a=version_a,
                version_b=version_b,
                has_a=a_metrics is not None,
                has_b=b_metrics is not None,
            )
            return None

        a_mape = a_metrics.get("mape")
        b_mape = b_metrics.get("mape")
        b_observed = b_metrics.get("observed", 0)

        # Require minimum sample size for challenger
        if b_observed < min_predictions:
            logger.info(
                "auto_promote_insufficient_observations",
                version_b=version_b,
                observed=b_observed,
                required=min_predictions,
            )
            return None

        # Both versions need observed accuracy to compare
        if a_mape is None or b_mape is None:
            return None

        # Challenger must beat champion by at least `threshold` fraction
        improvement = (a_mape - b_mape) / a_mape if a_mape > 0 else 0.0
        if improvement >= threshold:
            logger.info(
                "auto_promote_winner",
                winner=version_b,
                a_mape=a_mape,
                b_mape=b_mape,
                improvement=improvement,
                threshold=threshold,
            )
            return version_b

        logger.info(
            "auto_promote_no_winner",
            version_a=version_a,
            version_b=version_b,
            a_mape=a_mape,
            b_mape=b_mape,
            improvement=improvement,
            threshold=threshold,
        )
        return None
