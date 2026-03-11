"""
Model Version Service

Provides versioning and A/B testing infrastructure for ML models.

This service builds on top of the three tables introduced in migration 030:
  - model_versions  — versioned ML configurations with is_active gating
  - ab_tests        — A/B test runs pairing two model versions
  - ab_outcomes     — per-user outcome events used to evaluate tests

Public API
----------
create_version(model_name, config, metrics)
    Persist a new (inactive) model version record and return it.

get_active_version(model_name)
    Return the currently active version for model_name, or None.

promote_version(version_id)
    Atomically set a version active and deactivate all others for the
    same model_name.  Returns the promoted version.

list_versions(model_name, limit=10)
    Return recent versions newest-first, with their metrics.

compare_versions(version_a_id, version_b_id)
    Return a VersionComparisonResult with side-by-side metric deltas.

A/B testing
-----------
create_ab_test(model_name, version_a_id, version_b_id, traffic_split=0.5)
    Start a new A/B test.  Only one test per model_name may be running at
    a time — raises ValueError if one is already active.

get_ab_assignment(model_name, user_id)
    Deterministically assign a user to a bucket using a hash of
    (test_id, user_id).  The same user always receives the same version
    within a given test run.

record_ab_outcome(test_id, version_id, user_id, outcome)
    Persist a single outcome event.  Duplicate (test_id, user_id) pairs
    are silently ignored (upsert semantics via ON CONFLICT DO NOTHING).

All SQL uses sqlalchemy text() statements, consistent with the existing
repository layer (model_config_repository, forecast_observation_repository).
All primary keys are UUID strings.
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

from lib.tracing import traced

from models.model_version import (
    ABAssignment,
    ABOutcome,
    ABTest,
    ModelVersion,
    VersionComparisonResult,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_json(value: Any) -> Dict[str, Any]:
    """
    Normalise a JSONB column value that may arrive as either a pre-parsed
    dict (asyncpg) or a raw JSON string (psycopg2 / test mocks).
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {}


def _row_to_model_version(row: Any) -> ModelVersion:
    return ModelVersion(
        id=str(row.id),
        model_name=row.model_name,
        version_tag=row.version_tag,
        config=_parse_json(row.config),
        metrics=_parse_json(row.metrics),
        is_active=bool(row.is_active),
        created_at=row.created_at,
        promoted_at=row.promoted_at,
    )


def _row_to_ab_test(row: Any) -> ABTest:
    return ABTest(
        id=str(row.id),
        model_name=row.model_name,
        version_a_id=str(row.version_a_id),
        version_b_id=str(row.version_b_id),
        traffic_split=float(row.traffic_split),
        status=row.status,
        started_at=row.started_at,
        ended_at=row.ended_at,
        results=_parse_json(row.results),
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ModelVersionService:
    """
    Manages ML model versioning and A/B testing lifecycle.

    Usage::

        service = ModelVersionService(db)

        # Create and promote a version
        v = await service.create_version("ensemble", config={...}, metrics={...})
        promoted = await service.promote_version(v.id)

        # Start an A/B test
        test = await service.create_ab_test("ensemble", v1_id, v2_id, 0.3)

        # Deterministic assignment
        assignment = await service.get_ab_assignment("ensemble", user_id)

        # Record an outcome
        await service.record_ab_outcome(test.id, assignment.assigned_version_id,
                                        user_id, "conversion")
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Version CRUD
    # ------------------------------------------------------------------

    async def create_version(
        self,
        model_name: str,
        config: Dict[str, Any],
        metrics: Dict[str, Any],
        version_tag: Optional[str] = None,
    ) -> ModelVersion:
        """
        Persist a new model version record and return it.

        The new version is **not** made active automatically; call
        promote_version() when you are ready to switch traffic.

        Args:
            model_name:  Logical name of the model (e.g. "ensemble").
            config:      Hyperparameter / weight blob to persist as JSONB.
            metrics:     Evaluation metrics (mape, rmse, coverage, …).
            version_tag: Human-readable tag.  Defaults to a UTC timestamp
                         string so callers never need to supply one.

        Returns:
            The persisted ModelVersion with a generated UUID id.
        """
        async with traced("ml.create_version", attributes={"ml.model_name": model_name}):
            return await self._create_version_inner(model_name, config, metrics, version_tag)

    async def _create_version_inner(
        self,
        model_name: str,
        config: Dict[str, Any],
        metrics: Dict[str, Any],
        version_tag: Optional[str] = None,
    ) -> ModelVersion:
        new_id = str(uuid4())
        now = datetime.now(timezone.utc)
        tag = version_tag or now.strftime("v%Y%m%d_%H%M%S")

        try:
            await self._db.execute(
                text(
                    "INSERT INTO model_versions"
                    "    (id, model_name, version_tag, config, metrics,"
                    "     is_active, created_at)"
                    " VALUES"
                    "    (:id, :model_name, :version_tag, :config::jsonb,"
                    "     :metrics::jsonb, false, :created_at)"
                ),
                {
                    "id": new_id,
                    "model_name": model_name,
                    "version_tag": tag,
                    "config": json.dumps(config),
                    "metrics": json.dumps(metrics),
                    "created_at": now,
                },
            )
            await self._db.commit()
        except Exception as exc:
            await self._db.rollback()
            logger.error(
                "model_version_create_failed",
                model_name=model_name,
                version_tag=tag,
                error=str(exc),
            )
            raise

        logger.info(
            "model_version_created",
            model_name=model_name,
            version_id=new_id,
            version_tag=tag,
        )
        return ModelVersion(
            id=new_id,
            model_name=model_name,
            version_tag=tag,
            config=config,
            metrics=metrics,
            is_active=False,
            created_at=now,
            promoted_at=None,
        )

    async def get_active_version(self, model_name: str) -> Optional[ModelVersion]:
        """
        Return the currently active version for *model_name*, or None.

        There should be at most one active row per model_name.  If multiple
        active rows exist due to a data inconsistency, the most recently
        promoted one is returned.
        """
        result = await self._db.execute(
            text(
                "SELECT id, model_name, version_tag, config, metrics,"
                "       is_active, created_at, promoted_at"
                "  FROM model_versions"
                " WHERE model_name = :model_name"
                "   AND is_active = true"
                " ORDER BY promoted_at DESC NULLS LAST, created_at DESC"
                " LIMIT 1"
            ),
            {"model_name": model_name},
        )
        row = result.fetchone()
        if row is None:
            return None
        return _row_to_model_version(row)

    async def get_version_by_id(self, version_id: str) -> Optional[ModelVersion]:
        """Return a single ModelVersion by its UUID, or None if not found."""
        result = await self._db.execute(
            text(
                "SELECT id, model_name, version_tag, config, metrics,"
                "       is_active, created_at, promoted_at"
                "  FROM model_versions"
                " WHERE id = :version_id"
            ),
            {"version_id": version_id},
        )
        row = result.fetchone()
        if row is None:
            return None
        return _row_to_model_version(row)

    async def promote_version(self, version_id: str) -> ModelVersion:
        """
        Atomically promote *version_id* to active status.

        Steps (single transaction):
        1. Fetch the target version to obtain its model_name.
        2. Deactivate all currently active rows for that model_name.
        3. Activate the target row and record the promotion timestamp.
        4. Commit.

        Args:
            version_id: UUID of the version to promote.

        Returns:
            The updated ModelVersion with is_active=True.

        Raises:
            ValueError: If the version_id does not exist.
        """
        async with traced("ml.promote_version", attributes={"ml.version_id": version_id}):
            return await self._promote_version_inner(version_id)

    async def _promote_version_inner(self, version_id: str) -> ModelVersion:
        now = datetime.now(timezone.utc)

        # Fetch target
        result = await self._db.execute(
            text(
                "SELECT id, model_name, version_tag, config, metrics,"
                "       is_active, created_at, promoted_at"
                "  FROM model_versions"
                " WHERE id = :version_id"
            ),
            {"version_id": version_id},
        )
        row = result.fetchone()
        if row is None:
            raise ValueError(f"Model version not found: {version_id!r}")

        model_name = row.model_name

        try:
            # Deactivate existing active versions for this model
            await self._db.execute(
                text(
                    "UPDATE model_versions"
                    "   SET is_active = false"
                    " WHERE model_name = :model_name"
                    "   AND is_active = true"
                    "   AND id <> :version_id"
                ),
                {"model_name": model_name, "version_id": version_id},
            )

            # Promote the target version
            await self._db.execute(
                text(
                    "UPDATE model_versions"
                    "   SET is_active = true,"
                    "       promoted_at = :promoted_at"
                    " WHERE id = :version_id"
                ),
                {"version_id": version_id, "promoted_at": now},
            )

            await self._db.commit()
        except Exception as exc:
            await self._db.rollback()
            logger.error(
                "model_version_promote_failed",
                version_id=version_id,
                error=str(exc),
            )
            raise

        logger.info(
            "model_version_promoted",
            model_name=model_name,
            version_id=version_id,
        )
        return ModelVersion(
            id=str(row.id),
            model_name=row.model_name,
            version_tag=row.version_tag,
            config=_parse_json(row.config),
            metrics=_parse_json(row.metrics),
            is_active=True,
            created_at=row.created_at,
            promoted_at=now,
        )

    async def list_versions(
        self,
        model_name: str,
        limit: int = 10,
    ) -> List[ModelVersion]:
        """
        Return up to *limit* recent versions for *model_name*, newest first.

        Args:
            model_name: Logical model name to filter by.
            limit:      Maximum number of rows to return (default 10).

        Returns:
            Ordered list of ModelVersion objects (most recent first).
        """
        result = await self._db.execute(
            text(
                "SELECT id, model_name, version_tag, config, metrics,"
                "       is_active, created_at, promoted_at"
                "  FROM model_versions"
                " WHERE model_name = :model_name"
                " ORDER BY created_at DESC"
                " LIMIT :limit"
            ),
            {"model_name": model_name, "limit": limit},
        )
        return [_row_to_model_version(row) for row in result.fetchall()]

    async def compare_versions(
        self,
        version_a_id: str,
        version_b_id: str,
    ) -> VersionComparisonResult:
        """
        Compare two model versions side-by-side on their stored metrics.

        For numeric metrics present in both versions, a delta is computed
        as (b - a) so positive means version B is higher.

        Args:
            version_a_id: UUID of the baseline version.
            version_b_id: UUID of the candidate version.

        Returns:
            VersionComparisonResult with per-metric deltas.

        Raises:
            ValueError: If either version_id does not exist.
        """
        ver_a = await self.get_version_by_id(version_a_id)
        if ver_a is None:
            raise ValueError(f"Model version not found: {version_a_id!r}")
        ver_b = await self.get_version_by_id(version_b_id)
        if ver_b is None:
            raise ValueError(f"Model version not found: {version_b_id!r}")

        # Build metric comparison dict for all keys present in either version
        all_keys = set(ver_a.metrics.keys()) | set(ver_b.metrics.keys())
        comparison: Dict[str, Dict[str, Any]] = {}
        for key in sorted(all_keys):
            a_val = ver_a.metrics.get(key)
            b_val = ver_b.metrics.get(key)
            entry: Dict[str, Any] = {"version_a": a_val, "version_b": b_val}
            if isinstance(a_val, (int, float)) and isinstance(b_val, (int, float)):
                entry["delta"] = b_val - a_val
            else:
                entry["delta"] = None
            comparison[key] = entry

        from models.model_version import ModelVersionResponse

        return VersionComparisonResult(
            version_a=ModelVersionResponse(
                id=ver_a.id,
                model_name=ver_a.model_name,
                version_tag=ver_a.version_tag,
                config=ver_a.config,
                metrics=ver_a.metrics,
                is_active=ver_a.is_active,
                created_at=ver_a.created_at,
                promoted_at=ver_a.promoted_at,
            ),
            version_b=ModelVersionResponse(
                id=ver_b.id,
                model_name=ver_b.model_name,
                version_tag=ver_b.version_tag,
                config=ver_b.config,
                metrics=ver_b.metrics,
                is_active=ver_b.is_active,
                created_at=ver_b.created_at,
                promoted_at=ver_b.promoted_at,
            ),
            metric_comparison=comparison,
        )

    # ------------------------------------------------------------------
    # A/B test management
    # ------------------------------------------------------------------

    async def create_ab_test(
        self,
        model_name: str,
        version_a_id: str,
        version_b_id: str,
        traffic_split: float = 0.5,
    ) -> ABTest:
        """
        Start a new A/B test for *model_name*.

        Only one test per model_name may be in 'running' status at a time.
        Attempting to start a second concurrent test raises ValueError.

        *traffic_split* is the fraction of traffic routed to version_a.
        Version B receives the complementary fraction (1 - traffic_split).
        Must be strictly between 0.0 and 1.0.

        Args:
            model_name:    Logical model name shared by both versions.
            version_a_id:  UUID of the control (A) version.
            version_b_id:  UUID of the challenger (B) version.
            traffic_split: Fraction of traffic to route to version A.

        Returns:
            The newly created ABTest record.

        Raises:
            ValueError: If a running test already exists for model_name, or
                        if either version_id is not found.
        """
        if not (0.0 < traffic_split < 1.0):
            raise ValueError(
                f"traffic_split must be strictly between 0.0 and 1.0, got {traffic_split}"
            )

        # Guard: only one running test per model_name
        existing = await self._get_running_test(model_name)
        if existing is not None:
            raise ValueError(
                f"An A/B test is already running for model {model_name!r} "
                f"(test_id={existing.id!r}).  Stop it before starting a new one."
            )

        # Validate both versions exist
        for vid in (version_a_id, version_b_id):
            ver = await self.get_version_by_id(vid)
            if ver is None:
                raise ValueError(f"Model version not found: {vid!r}")
            if ver.model_name != model_name:
                raise ValueError(
                    f"Version {vid!r} belongs to model {ver.model_name!r}, "
                    f"not {model_name!r}"
                )

        new_id = str(uuid4())
        now = datetime.now(timezone.utc)

        try:
            await self._db.execute(
                text(
                    "INSERT INTO ab_tests"
                    "    (id, model_name, version_a_id, version_b_id,"
                    "     traffic_split, status, started_at, results)"
                    " VALUES"
                    "    (:id, :model_name, :version_a_id, :version_b_id,"
                    "     :traffic_split, 'running', :started_at, '{}'::jsonb)"
                ),
                {
                    "id": new_id,
                    "model_name": model_name,
                    "version_a_id": version_a_id,
                    "version_b_id": version_b_id,
                    "traffic_split": traffic_split,
                    "started_at": now,
                },
            )
            await self._db.commit()
        except Exception as exc:
            await self._db.rollback()
            logger.error(
                "ab_test_create_failed",
                model_name=model_name,
                error=str(exc),
            )
            raise

        logger.info(
            "ab_test_created",
            test_id=new_id,
            model_name=model_name,
            version_a=version_a_id,
            version_b=version_b_id,
            traffic_split=traffic_split,
        )
        return ABTest(
            id=new_id,
            model_name=model_name,
            version_a_id=version_a_id,
            version_b_id=version_b_id,
            traffic_split=traffic_split,
            status="running",
            started_at=now,
            ended_at=None,
            results={},
        )

    async def get_ab_assignment(
        self,
        model_name: str,
        user_id: str,
    ) -> Optional[ABAssignment]:
        """
        Deterministically assign a user to a bucket (A or B) for the active
        A/B test of *model_name*.

        Assignment is computed as:
            bucket = "a" if hash(test_id + ":" + user_id) % 100 < split_pct
                     else "b"

        where split_pct = traffic_split * 100.

        Using the test_id as part of the hash key means:
        - The same user always receives the same bucket within a test.
        - Assignments change when a new test is started (new test_id).

        Args:
            model_name: Logical model name to look up the running test for.
            user_id:    UUID string of the user to assign.

        Returns:
            ABAssignment with the assigned version_id and bucket, or None if
            no running test exists for model_name.
        """
        test = await self._get_running_test(model_name)
        if test is None:
            return None

        # Deterministic hash: stable across Python processes
        hash_input = f"{test.id}:{user_id}".encode("utf-8")
        hash_int = int(hashlib.sha256(hash_input).hexdigest(), 16)
        bucket_pct = hash_int % 100  # 0–99

        split_pct = int(test.traffic_split * 100)
        if bucket_pct < split_pct:
            bucket = "a"
            assigned_version_id = test.version_a_id
        else:
            bucket = "b"
            assigned_version_id = test.version_b_id

        return ABAssignment(
            test_id=test.id,
            user_id=user_id,
            assigned_version_id=assigned_version_id,
            bucket=bucket,
        )

    async def record_ab_outcome(
        self,
        test_id: str,
        version_id: str,
        user_id: str,
        outcome: str,
    ) -> ABOutcome:
        """
        Record a single outcome event for a user within an A/B test.

        Duplicate (test_id, user_id) combinations are silently ignored via
        ON CONFLICT DO NOTHING, ensuring idempotent recording.

        Args:
            test_id:    UUID of the A/B test.
            version_id: UUID of the model version that served the user.
            user_id:    UUID of the user whose outcome is being recorded.
            outcome:    Outcome label (e.g. "conversion", "success", "error").

        Returns:
            The ABOutcome that was inserted (or the deduped representation).
        """
        new_id = str(uuid4())
        now = datetime.now(timezone.utc)

        try:
            await self._db.execute(
                text(
                    "INSERT INTO ab_outcomes"
                    "    (id, test_id, version_id, user_id, outcome, recorded_at)"
                    " VALUES"
                    "    (:id, :test_id, :version_id, :user_id, :outcome, :recorded_at)"
                    " ON CONFLICT (test_id, user_id) DO NOTHING"
                ),
                {
                    "id": new_id,
                    "test_id": test_id,
                    "version_id": version_id,
                    "user_id": user_id,
                    "outcome": outcome,
                    "recorded_at": now,
                },
            )
            await self._db.commit()
        except Exception as exc:
            await self._db.rollback()
            logger.error(
                "ab_outcome_record_failed",
                test_id=test_id,
                user_id=user_id,
                error=str(exc),
            )
            raise

        logger.debug(
            "ab_outcome_recorded",
            test_id=test_id,
            version_id=version_id,
            user_id=user_id,
            outcome=outcome,
        )
        return ABOutcome(
            id=new_id,
            test_id=test_id,
            version_id=version_id,
            user_id=user_id,
            outcome=outcome,
            recorded_at=now,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_running_test(self, model_name: str) -> Optional[ABTest]:
        """Return the currently running A/B test for model_name, or None."""
        result = await self._db.execute(
            text(
                "SELECT id, model_name, version_a_id, version_b_id,"
                "       traffic_split, status, started_at, ended_at, results"
                "  FROM ab_tests"
                " WHERE model_name = :model_name"
                "   AND status = 'running'"
                " ORDER BY started_at DESC"
                " LIMIT 1"
            ),
            {"model_name": model_name},
        )
        row = result.fetchone()
        if row is None:
            return None
        return _row_to_ab_test(row)
