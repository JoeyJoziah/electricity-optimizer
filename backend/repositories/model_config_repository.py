"""
Model Config Repository

Durable storage for ML ensemble weights in PostgreSQL.

Replaces the previous Redis-only approach which silently lost weights on every
Render free-tier restart.  All reads and writes go through raw SQL (sqlalchemy
text()) consistent with ForecastObservationRepository.

Public API
----------
get_active_config(model_name)         -> Optional[ModelConfig]
save_config(model_name, version, ...) -> ModelConfig
list_versions(model_name, limit)      -> List[ModelConfig]
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.model_config import ModelConfig
from repositories.base import RepositoryError

logger = logging.getLogger(__name__)


class ModelConfigRepository:
    """
    Raw-SQL data access for the model_config table.

    Uses sqlalchemy text() statements to remain consistent with the rest of
    the repository layer (ForecastObservationRepository, etc.) and to avoid
    SQLAlchemy ORM mapping overhead for a table that is written infrequently
    but read on every service startup.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    async def get_active_config(self, model_name: str) -> Optional[ModelConfig]:
        """
        Return the currently active configuration for *model_name*.

        There should be at most one active row per model name.  If multiple
        active rows exist (data inconsistency), the most recently created one
        is returned.

        Returns None when no active config has been saved yet so that callers
        can fall back to hard-coded defaults.
        """
        try:
            result = await self._db.execute(
                text(
                    "SELECT id, model_name, model_version, weights_json,"
                    "       training_metadata, accuracy_metrics, is_active,"
                    "       created_at, updated_at"
                    "  FROM model_config"
                    " WHERE model_name = :model_name"
                    "   AND is_active = true"
                    " ORDER BY created_at DESC"
                    " LIMIT 1"
                ),
                {"model_name": model_name},
            )
            row = result.fetchone()
            if row is None:
                return None
            return self._row_to_model(row)
        except Exception as exc:
            raise RepositoryError(f"Failed to get active config for {model_name!r}: {exc}", exc)

    async def list_versions(
        self,
        model_name: str,
        limit: int = 20,
    ) -> List[ModelConfig]:
        """
        Return up to *limit* historical configurations for *model_name*,
        newest first.  Useful for auditing or rolling back weights.
        """
        try:
            result = await self._db.execute(
                text(
                    "SELECT id, model_name, model_version, weights_json,"
                    "       training_metadata, accuracy_metrics, is_active,"
                    "       created_at, updated_at"
                    "  FROM model_config"
                    " WHERE model_name = :model_name"
                    " ORDER BY created_at DESC"
                    " LIMIT :limit"
                ),
                {"model_name": model_name, "limit": limit},
            )
            return [self._row_to_model(row) for row in result.fetchall()]
        except Exception as exc:
            raise RepositoryError(f"Failed to list versions for {model_name!r}: {exc}", exc)

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    async def save_config(
        self,
        model_name: str,
        version: str,
        weights: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> ModelConfig:
        """
        Persist a new weight configuration and mark it active.

        Steps (executed in a single transaction):
        1. Deactivate all existing active rows for *model_name*.
        2. Insert the new row with is_active=True.
        3. Commit and return the new ModelConfig.

        The atomic deactivate-then-insert pattern ensures the partial-index
        on (model_name, is_active) never sees two active rows simultaneously
        under normal operation (single-writer assumption).
        """
        new_id = str(uuid4())
        now = datetime.now(timezone.utc)
        metadata = metadata or {}
        metrics = metrics or {}

        try:
            # Step 1: deactivate existing active configs
            await self._db.execute(
                text(
                    "UPDATE model_config"
                    "   SET is_active = false,"
                    "       updated_at = :now"
                    " WHERE model_name = :model_name"
                    "   AND is_active = true"
                ),
                {"model_name": model_name, "now": now},
            )

            # Step 2: insert the new active row
            await self._db.execute(
                text(
                    "INSERT INTO model_config"
                    "    (id, model_name, model_version, weights_json,"
                    "     training_metadata, accuracy_metrics, is_active,"
                    "     created_at, updated_at)"
                    " VALUES"
                    "    (:id, :model_name, :model_version, :weights_json::jsonb,"
                    "     :training_metadata::jsonb, :accuracy_metrics::jsonb,"
                    "     true, :created_at, :updated_at)"
                ),
                {
                    "id": new_id,
                    "model_name": model_name,
                    "model_version": version,
                    "weights_json": json.dumps(weights),
                    "training_metadata": json.dumps(metadata),
                    "accuracy_metrics": json.dumps(metrics),
                    "created_at": now,
                    "updated_at": now,
                },
            )

            await self._db.commit()

            logger.info(
                "model_config_saved model_name=%s version=%s id=%s",
                model_name,
                version,
                new_id,
            )

            return ModelConfig(
                id=new_id,
                model_name=model_name,
                model_version=version,
                weights_json=weights,
                training_metadata=metadata,
                accuracy_metrics=metrics,
                is_active=True,
                created_at=now,
                updated_at=now,
            )

        except Exception as exc:
            await self._db.rollback()
            raise RepositoryError(
                f"Failed to save config for {model_name!r} v{version}: {exc}", exc
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_model(row: Any) -> ModelConfig:
        """Convert a SQLAlchemy Row to a ModelConfig Pydantic model."""

        def _parse_json(value: Any) -> Any:
            """Handle both pre-parsed dicts (asyncpg) and raw JSON strings."""
            if value is None:
                return {}
            if isinstance(value, (dict, list)):
                return value
            return json.loads(value)

        return ModelConfig(
            id=str(row.id),
            model_name=row.model_name,
            model_version=row.model_version,
            weights_json=_parse_json(row.weights_json),
            training_metadata=_parse_json(row.training_metadata),
            accuracy_metrics=_parse_json(row.accuracy_metrics),
            is_active=row.is_active,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
