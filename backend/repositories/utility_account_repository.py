"""
Utility Account Repository

Data access layer for user utility accounts.
Uses raw SQL with text() since UtilityAccount is a Pydantic model, not SQLAlchemy ORM.
"""

import json
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.utility_account import UtilityAccount
from repositories.base import BaseRepository, NotFoundError, RepositoryError

_COLUMNS = (
    "id, user_id, utility_type, region, provider_name, "
    "is_primary, metadata, created_at, updated_at"
)


def _row_to_account(row: dict) -> UtilityAccount:
    """Convert a DB row mapping to a UtilityAccount Pydantic model."""
    return UtilityAccount(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        utility_type=row["utility_type"],
        region=row["region"],
        provider_name=row["provider_name"],
        is_primary=row["is_primary"],
        metadata=row.get("metadata") or {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class UtilityAccountRepository(BaseRepository[UtilityAccount]):
    """Repository for managing user utility accounts."""

    def __init__(self, db_session: AsyncSession):
        self._db = db_session

    async def get_by_id(self, id: str) -> Optional[UtilityAccount]:
        """Get a utility account by ID."""
        try:
            result = await self._db.execute(
                text(f"SELECT {_COLUMNS} FROM utility_accounts WHERE id = :id"),
                {"id": id},
            )
            row = result.mappings().first()
            return _row_to_account(row) if row else None
        except Exception as e:
            raise RepositoryError(f"Failed to get utility account: {e}", e)

    async def create(self, entity: UtilityAccount) -> UtilityAccount:
        """Create a new utility account."""
        try:
            result = await self._db.execute(
                text(
                    "INSERT INTO utility_accounts "
                    "(id, user_id, utility_type, region, provider_name, "
                    "account_number_encrypted, is_primary, metadata) "
                    "VALUES (:id, :user_id, :utility_type, :region, :provider_name, "
                    ":account_number_encrypted, :is_primary, :metadata::jsonb) "
                    f"RETURNING {_COLUMNS}"
                ),
                {
                    "id": entity.id,
                    "user_id": entity.user_id,
                    "utility_type": entity.utility_type,
                    "region": entity.region,
                    "provider_name": entity.provider_name,
                    "account_number_encrypted": entity.account_number_encrypted,
                    "is_primary": entity.is_primary,
                    "metadata": json.dumps(entity.metadata) if entity.metadata else "{}",
                },
            )
            await self._db.commit()
            row = result.mappings().first()
            return _row_to_account(row)
        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to create utility account: {e}", e)

    async def update(self, id: str, entity: UtilityAccount) -> Optional[UtilityAccount]:
        """Update an existing utility account."""
        try:
            result = await self._db.execute(
                text(
                    "UPDATE utility_accounts SET "
                    "provider_name = COALESCE(:provider_name, provider_name), "
                    "is_primary = COALESCE(:is_primary, is_primary), "
                    "metadata = COALESCE(:metadata::jsonb, metadata), "
                    "updated_at = now() "
                    f"WHERE id = :id RETURNING {_COLUMNS}"
                ),
                {
                    "id": id,
                    "provider_name": entity.provider_name,
                    "is_primary": entity.is_primary,
                    "metadata": json.dumps(entity.metadata) if entity.metadata else None,
                },
            )
            await self._db.commit()
            row = result.mappings().first()
            return _row_to_account(row) if row else None
        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to update utility account: {e}", e)

    async def delete(self, id: str) -> bool:
        """Delete a utility account by ID."""
        try:
            result = await self._db.execute(
                text("DELETE FROM utility_accounts WHERE id = :id"),
                {"id": id},
            )
            await self._db.commit()
            return result.rowcount > 0
        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to delete utility account: {e}", e)

    async def list(
        self,
        page: int = 1,
        page_size: int = 10,
        **filters: Any,
    ) -> List[UtilityAccount]:
        """List utility accounts with pagination and optional filters."""
        try:
            offset = (page - 1) * page_size
            where_clauses = []
            params: dict = {"limit": page_size, "offset": offset}

            if "user_id" in filters:
                where_clauses.append("user_id = :user_id")
                params["user_id"] = filters["user_id"]
            if "utility_type" in filters:
                where_clauses.append("utility_type = :utility_type")
                params["utility_type"] = filters["utility_type"]
            if "region" in filters:
                where_clauses.append("region = :region")
                params["region"] = filters["region"]

            where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            result = await self._db.execute(
                text(
                    f"SELECT {_COLUMNS} FROM utility_accounts {where} "
                    "ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                params,
            )
            return [_row_to_account(row) for row in result.mappings().all()]
        except Exception as e:
            raise RepositoryError(f"Failed to list utility accounts: {e}", e)

    async def count(self, **filters: Any) -> int:
        """Count utility accounts matching filters."""
        try:
            where_clauses = []
            params: dict = {}

            if "user_id" in filters:
                where_clauses.append("user_id = :user_id")
                params["user_id"] = filters["user_id"]
            if "utility_type" in filters:
                where_clauses.append("utility_type = :utility_type")
                params["utility_type"] = filters["utility_type"]

            where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            result = await self._db.execute(
                text(f"SELECT COUNT(*) FROM utility_accounts {where}"),
                params,
            )
            return result.scalar() or 0
        except Exception as e:
            raise RepositoryError(f"Failed to count utility accounts: {e}", e)

    async def get_by_user(self, user_id: str) -> List[UtilityAccount]:
        """Get all utility accounts for a user."""
        return await self.list(page=1, page_size=100, user_id=user_id)

    async def get_by_user_and_type(self, user_id: str, utility_type: str) -> List[UtilityAccount]:
        """Get utility accounts for a user filtered by utility type."""
        return await self.list(page=1, page_size=100, user_id=user_id, utility_type=utility_type)
