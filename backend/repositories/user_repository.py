"""
User Repository

Data access layer for user data.
Uses raw SQL queries to avoid ORM-model mismatch with Pydantic models.
"""

import json
from datetime import datetime, timezone
from typing import Optional, List, Any, Dict
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.base import BaseRepository, RepositoryError, NotFoundError
from models.user import User, UserPreferences

logger = structlog.get_logger(__name__)

# Columns returned by SELECT queries — matches the Neon DB schema
_USER_COLUMNS = """
    id::text, email, name, region, preferences,
    current_supplier, is_active, is_verified,
    created_at, updated_at,
    stripe_customer_id, subscription_tier,
    email_verified, current_tariff,
    average_daily_kwh, household_size,
    current_supplier_id::text,
    utility_types, annual_usage_kwh,
    onboarding_completed
"""


def _row_to_user(row) -> User:
    """Convert a SQLAlchemy Row mapping to a User Pydantic model."""
    data: Dict[str, Any] = {}
    for key in row.keys():
        val = row[key]
        # Convert UUID to string if needed
        if key in ("id", "current_supplier_id") and val is not None:
            val = str(val)
        data[key] = val
    # Map DB columns to Pydantic fields, providing defaults for columns
    # that may not exist in the DB (added in migration 002 which may
    # not have been applied to all environments)
    return User(
        id=data.get("id", str(uuid4())),
        email=data.get("email", ""),
        name=data.get("name", ""),
        region=data.get("region"),
        is_active=data.get("is_active", True),
        is_verified=data.get("is_verified", False),
        email_verified=data.get("email_verified", False),
        subscription_tier=data.get("subscription_tier", "free"),
        stripe_customer_id=data.get("stripe_customer_id"),
        preferences=data.get("preferences", {}),
        current_supplier=data.get("current_supplier"),
        current_supplier_id=data.get("current_supplier_id"),
        current_tariff=data.get("current_tariff"),
        average_daily_kwh=data.get("average_daily_kwh"),
        annual_usage_kwh=data.get("annual_usage_kwh"),
        household_size=data.get("household_size"),
        utility_types=data.get("utility_types"),
        onboarding_completed=data.get("onboarding_completed", False),
        consent_given=data.get("consent_given", False),
        consent_date=data.get("consent_date"),
        data_processing_agreed=data.get("data_processing_agreed", False),
        created_at=data.get("created_at", datetime.now(timezone.utc)),
        updated_at=data.get("updated_at", datetime.now(timezone.utc)),
        last_login=data.get("last_login"),
    )


class UserRepository(BaseRepository[User]):
    """
    Repository for managing user data.

    Uses raw SQL queries (not ORM) to interact with the users table.
    This avoids the Pydantic/SQLAlchemy model mismatch that caused
    CRIT-03/05 in the codebase audit.
    """

    def __init__(self, db_session: AsyncSession, cache: Any = None):
        """
        Initialize the user repository.

        Args:
            db_session: SQLAlchemy async session
            cache: Redis cache client (optional)
        """
        self._db = db_session
        self._cache = cache

    async def get_by_id(self, id: str) -> Optional[User]:
        """Get a user by ID."""
        try:
            result = await self._db.execute(
                text(f"SELECT {_USER_COLUMNS} FROM users WHERE id = :id"),
                {"id": id},
            )
            row = result.mappings().first()
            return _row_to_user(row) if row else None

        except Exception as e:
            raise RepositoryError(f"Failed to get user by ID: {str(e)}", e)

    async def get_by_email(self, email: str) -> Optional[User]:
        """Get a user by email address."""
        try:
            result = await self._db.execute(
                text(f"SELECT {_USER_COLUMNS} FROM users WHERE email = :email"),
                {"email": email.lower()},
            )
            row = result.mappings().first()
            return _row_to_user(row) if row else None

        except Exception as e:
            raise RepositoryError(f"Failed to get user by email: {str(e)}", e)

    async def create(self, entity: User) -> User:
        """Create a new user."""
        try:
            entity.email = entity.email.lower()
            now = datetime.now(timezone.utc)
            entity.created_at = now
            entity.updated_at = now

            result = await self._db.execute(
                text(f"""
                    INSERT INTO users (
                        id, email, name, region, preferences,
                        current_supplier, is_active, is_verified,
                        subscription_tier, stripe_customer_id,
                        email_verified, current_tariff,
                        average_daily_kwh, household_size,
                        created_at, updated_at
                    ) VALUES (
                        :id, :email, :name, :region, :preferences::jsonb,
                        :current_supplier, :is_active, :is_verified,
                        :subscription_tier, :stripe_customer_id,
                        :email_verified, :current_tariff,
                        :average_daily_kwh, :household_size,
                        :created_at, :updated_at
                    )
                    RETURNING {_USER_COLUMNS}
                """),
                {
                    "id": entity.id,
                    "email": entity.email,
                    "name": entity.name,
                    "region": entity.region,
                    "preferences": json.dumps(entity.preferences) if entity.preferences else "{}",
                    "current_supplier": entity.current_supplier,
                    "is_active": entity.is_active,
                    "is_verified": entity.is_verified,
                    "subscription_tier": entity.subscription_tier,
                    "stripe_customer_id": entity.stripe_customer_id,
                    "email_verified": entity.email_verified,
                    "current_tariff": entity.current_tariff,
                    "average_daily_kwh": float(entity.average_daily_kwh) if entity.average_daily_kwh is not None else None,
                    "household_size": entity.household_size,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            await self._db.commit()
            row = result.mappings().first()
            return _row_to_user(row) if row else entity

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to create user: {str(e)}", e)

    # Columns allowed in dynamic UPDATE SET clause (prevents SQL injection via field names)
    _UPDATABLE_COLUMNS = frozenset({
        "email", "name", "region", "preferences",
        "current_supplier", "is_active", "is_verified",
        "subscription_tier", "stripe_customer_id",
        "email_verified", "current_tariff",
        "average_daily_kwh", "household_size",
        "current_supplier_id", "utility_types",
        "annual_usage_kwh", "onboarding_completed",
        "updated_at",
    })

    async def update(self, id: str, entity: User) -> Optional[User]:
        """Update an existing user."""
        try:
            # Build dynamic SET clause from entity fields
            updates = entity.model_dump(exclude_unset=True)
            # Never update id or created_at
            updates.pop("id", None)
            updates.pop("created_at", None)
            updates["updated_at"] = datetime.now(timezone.utc)
            # Only allow known columns
            updates = {k: v for k, v in updates.items() if k in self._UPDATABLE_COLUMNS}

            if not updates:
                return await self.get_by_id(id)

            set_clauses = []
            params: Dict[str, Any] = {"user_id": id}
            for field, value in updates.items():
                param_name = f"p_{field}"
                if field == "preferences":
                    set_clauses.append(f"{field} = :{param_name}::jsonb")
                    params[param_name] = json.dumps(value) if value else "{}"
                elif field == "average_daily_kwh" and value is not None:
                    set_clauses.append(f"{field} = :{param_name}")
                    params[param_name] = float(value)
                else:
                    set_clauses.append(f"{field} = :{param_name}")
                    params[param_name] = value

            set_sql = ", ".join(set_clauses)
            result = await self._db.execute(
                text(f"""
                    UPDATE users SET {set_sql}
                    WHERE id = :user_id
                    RETURNING {_USER_COLUMNS}
                """),
                params,
            )
            await self._db.commit()
            row = result.mappings().first()
            return _row_to_user(row) if row else None

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to update user: {str(e)}", e)

    async def delete(self, id: str) -> bool:
        """Delete a user."""
        try:
            result = await self._db.execute(
                text("DELETE FROM users WHERE id = :id RETURNING id"),
                {"id": id},
            )
            await self._db.commit()
            return result.first() is not None

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to delete user: {str(e)}", e)

    async def list(
        self,
        page: int = 1,
        page_size: int = 10,
        **filters: Any
    ) -> List[User]:
        """List users with pagination."""
        try:
            offset = (page - 1) * page_size
            conditions = []
            params: Dict[str, Any] = {"limit": page_size, "offset": offset}

            if "region" in filters:
                conditions.append("region = :region")
                params["region"] = filters["region"]
            if "is_active" in filters:
                conditions.append("is_active = :is_active")
                params["is_active"] = filters["is_active"]

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            result = await self._db.execute(
                text(f"""
                    SELECT {_USER_COLUMNS} FROM users
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                """),
                params,
            )
            rows = result.mappings().all()
            return [_row_to_user(row) for row in rows]

        except Exception as e:
            raise RepositoryError(f"Failed to list users: {str(e)}", e)

    async def count(self, **filters: Any) -> int:
        """Count users matching filters."""
        try:
            conditions = []
            params: Dict[str, Any] = {}

            if "region" in filters:
                conditions.append("region = :region")
                params["region"] = filters["region"]
            if "is_active" in filters:
                conditions.append("is_active = :is_active")
                params["is_active"] = filters["is_active"]

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            result = await self._db.execute(
                text(f"SELECT COUNT(*) FROM users {where_clause}"),
                params,
            )
            return result.scalar() or 0

        except Exception as e:
            raise RepositoryError(f"Failed to count users: {str(e)}", e)

    # ==========================================================================
    # User-specific methods
    # ==========================================================================

    async def update_preferences(
        self,
        user_id: str,
        preferences: UserPreferences
    ) -> Optional[User]:
        """Update user preferences."""
        try:
            import json
            result = await self._db.execute(
                text(f"""
                    UPDATE users
                    SET preferences = :prefs::jsonb, updated_at = NOW()
                    WHERE id = :user_id
                    RETURNING {_USER_COLUMNS}
                """),
                {
                    "user_id": user_id,
                    "prefs": json.dumps(preferences.model_dump()),
                },
            )
            await self._db.commit()
            row = result.mappings().first()
            return _row_to_user(row) if row else None

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to update preferences: {str(e)}", e)

    async def update_last_login(self, user_id: str) -> bool:
        """Update user's last login timestamp (direct UPDATE, no SELECT)."""
        try:
            result = await self._db.execute(
                text("""
                    UPDATE users
                    SET last_login = NOW(), updated_at = NOW()
                    WHERE id = :user_id
                    RETURNING id
                """),
                {"user_id": user_id},
            )
            await self._db.commit()
            return result.first() is not None

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to update last login: {str(e)}", e)

    async def set_email_verified(self, user_id: str) -> bool:
        """Mark user's email as verified (direct UPDATE, no SELECT)."""
        try:
            result = await self._db.execute(
                text("""
                    UPDATE users
                    SET email_verified = TRUE, is_verified = TRUE, updated_at = NOW()
                    WHERE id = :user_id
                    RETURNING id
                """),
                {"user_id": user_id},
            )
            await self._db.commit()
            return result.first() is not None

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to verify email: {str(e)}", e)

    async def record_consent(
        self,
        user_id: str,
        consent_given: bool = True,
        data_processing_agreed: bool = True
    ) -> bool:
        """Record user's GDPR consent (direct UPDATE, no SELECT)."""
        try:
            result = await self._db.execute(
                text("""
                    UPDATE users
                    SET consent_given = :consent_given,
                        data_processing_agreed = :data_processing_agreed,
                        consent_date = NOW(),
                        updated_at = NOW()
                    WHERE id = :user_id
                    RETURNING id
                """),
                {
                    "user_id": user_id,
                    "consent_given": consent_given,
                    "data_processing_agreed": data_processing_agreed,
                },
            )
            await self._db.commit()
            return result.first() is not None

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to record consent: {str(e)}", e)

    async def get_by_stripe_customer_id(self, customer_id: str) -> Optional[User]:
        """Look up user by their Stripe customer ID."""
        try:
            result = await self._db.execute(
                text(f"""
                    SELECT {_USER_COLUMNS} FROM users
                    WHERE stripe_customer_id = :customer_id
                """),
                {"customer_id": customer_id},
            )
            row = result.mappings().first()
            return _row_to_user(row) if row else None

        except Exception as e:
            raise RepositoryError(f"Failed to get user by Stripe customer ID: {str(e)}", e)

    async def get_users_by_region(
        self,
        region: str,
        active_only: bool = True
    ) -> List[User]:
        """Get users in a region (with LIMIT for safety)."""
        try:
            conditions = ["region = :region"]
            if active_only:
                conditions.append("is_active = TRUE")

            where_clause = " AND ".join(conditions)

            result = await self._db.execute(
                text(f"""
                    SELECT {_USER_COLUMNS} FROM users
                    WHERE {where_clause}
                    LIMIT 5000
                """),
                {"region": region.lower()},
            )
            rows = result.mappings().all()
            return [_row_to_user(row) for row in rows]

        except Exception as e:
            raise RepositoryError(f"Failed to get users by region: {str(e)}", e)
