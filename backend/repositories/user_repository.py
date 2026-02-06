"""
User Repository

Data access layer for user data.
Implements the repository pattern with caching support.
"""

from datetime import datetime, timezone
from typing import Optional, List, Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.base import BaseRepository, RepositoryError, NotFoundError
from models.user import User, UserPreferences


class UserRepository(BaseRepository[User]):
    """
    Repository for managing user data.

    Provides data access methods for users with proper
    security considerations for sensitive data.
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
        """
        Get a user by ID.

        Args:
            id: User ID

        Returns:
            User if found, None otherwise
        """
        try:
            result = await self._db.execute(
                select(User).where(User.id == id)
            )
            return result.scalar_one_or_none()

        except Exception as e:
            raise RepositoryError(f"Failed to get user by ID: {str(e)}", e)

    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Get a user by email address.

        Args:
            email: User email address

        Returns:
            User if found, None otherwise
        """
        try:
            result = await self._db.execute(
                select(User).where(User.email == email.lower())
            )
            return result.scalar_one_or_none()

        except Exception as e:
            raise RepositoryError(f"Failed to get user by email: {str(e)}", e)

    async def create(self, entity: User) -> User:
        """
        Create a new user.

        Args:
            entity: User data to create

        Returns:
            Created user
        """
        try:
            # Normalize email
            entity.email = entity.email.lower()
            entity.created_at = datetime.now(timezone.utc)
            entity.updated_at = datetime.now(timezone.utc)

            self._db.add(entity)
            await self._db.commit()
            await self._db.refresh(entity)
            return entity

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to create user: {str(e)}", e)

    async def update(self, id: str, entity: User) -> Optional[User]:
        """
        Update an existing user.

        Args:
            id: User ID
            entity: Updated user data

        Returns:
            Updated user if found, None otherwise
        """
        try:
            existing = await self.get_by_id(id)
            if not existing:
                return None

            # Update fields
            for field, value in entity.model_dump(exclude_unset=True).items():
                if field not in ["id", "created_at"]:
                    setattr(existing, field, value)

            existing.updated_at = datetime.now(timezone.utc)

            await self._db.commit()
            await self._db.refresh(existing)
            return existing

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to update user: {str(e)}", e)

    async def delete(self, id: str) -> bool:
        """
        Delete a user.

        Args:
            id: User ID

        Returns:
            True if deleted, False if not found
        """
        try:
            existing = await self.get_by_id(id)
            if not existing:
                return False

            await self._db.delete(existing)
            await self._db.commit()
            return True

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to delete user: {str(e)}", e)

    async def list(
        self,
        page: int = 1,
        page_size: int = 10,
        **filters: Any
    ) -> List[User]:
        """
        List users with pagination.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            **filters: Filter criteria

        Returns:
            List of users
        """
        try:
            offset = (page - 1) * page_size

            query = select(User).offset(offset).limit(page_size)

            # Apply filters
            if "region" in filters:
                query = query.where(User.region == filters["region"])
            if "is_active" in filters:
                query = query.where(User.is_active == filters["is_active"])

            query = query.order_by(User.created_at.desc())

            result = await self._db.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            raise RepositoryError(f"Failed to list users: {str(e)}", e)

    async def count(self, **filters: Any) -> int:
        """
        Count users matching filters.

        Args:
            **filters: Filter criteria

        Returns:
            Count of matching users
        """
        try:
            from sqlalchemy import func

            query = select(func.count()).select_from(User)

            if "region" in filters:
                query = query.where(User.region == filters["region"])
            if "is_active" in filters:
                query = query.where(User.is_active == filters["is_active"])

            result = await self._db.execute(query)
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
        """
        Update user preferences.

        Args:
            user_id: User ID
            preferences: New preferences

        Returns:
            Updated user if found, None otherwise
        """
        try:
            existing = await self.get_by_id(user_id)
            if not existing:
                return None

            existing.preferences = preferences.model_dump()
            existing.updated_at = datetime.now(timezone.utc)

            await self._db.commit()
            await self._db.refresh(existing)
            return existing

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to update preferences: {str(e)}", e)

    async def update_last_login(self, user_id: str) -> bool:
        """
        Update user's last login timestamp.

        Args:
            user_id: User ID

        Returns:
            True if updated successfully
        """
        try:
            existing = await self.get_by_id(user_id)
            if not existing:
                return False

            existing.last_login = datetime.now(timezone.utc)
            existing.updated_at = datetime.now(timezone.utc)

            await self._db.commit()
            return True

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to update last login: {str(e)}", e)

    async def set_email_verified(self, user_id: str) -> bool:
        """
        Mark user's email as verified.

        Args:
            user_id: User ID

        Returns:
            True if updated successfully
        """
        try:
            existing = await self.get_by_id(user_id)
            if not existing:
                return False

            existing.email_verified = True
            existing.is_verified = True
            existing.updated_at = datetime.now(timezone.utc)

            await self._db.commit()
            return True

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to verify email: {str(e)}", e)

    async def record_consent(
        self,
        user_id: str,
        consent_given: bool = True,
        data_processing_agreed: bool = True
    ) -> bool:
        """
        Record user's GDPR consent.

        Args:
            user_id: User ID
            consent_given: Whether consent was given
            data_processing_agreed: Whether data processing was agreed

        Returns:
            True if updated successfully
        """
        try:
            existing = await self.get_by_id(user_id)
            if not existing:
                return False

            existing.consent_given = consent_given
            existing.data_processing_agreed = data_processing_agreed
            existing.consent_date = datetime.now(timezone.utc)
            existing.updated_at = datetime.now(timezone.utc)

            await self._db.commit()
            return True

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to record consent: {str(e)}", e)

    async def get_users_by_region(
        self,
        region: str,
        active_only: bool = True
    ) -> List[User]:
        """
        Get all users in a region.

        Args:
            region: Region code
            active_only: Whether to include only active users

        Returns:
            List of users in the region
        """
        try:
            conditions = [User.region == region.lower()]

            if active_only:
                conditions.append(User.is_active == True)

            query = select(User).where(and_(*conditions))
            result = await self._db.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            raise RepositoryError(f"Failed to get users by region: {str(e)}", e)
