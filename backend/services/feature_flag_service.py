"""
Feature Flag Service

Evaluates and manages feature flags with support for:
- Global enable/disable
- Subscription tier gating (free < pro < business)
- Percentage-based rollout using a deterministic MD5 hash
"""

import hashlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

logger = structlog.get_logger(__name__)

# Ordered tier values — higher index = higher tier
_TIER_ORDER: dict[str, int] = {"free": 0, "pro": 1, "business": 2}


class FeatureFlagService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def is_enabled(
        self,
        flag_name: str,
        user_id: str = None,
        user_tier: str = None,
    ) -> bool:
        """
        Evaluate whether a feature flag is enabled for the given user context.

        Evaluation order:
        1. Flag must exist and have ``enabled = TRUE``.
        2. If ``tier_required`` is set and ``user_tier`` is provided, the user
           must meet or exceed the required tier.
        3. If ``percentage < 100`` and ``user_id`` is provided, a deterministic
           hash decides inclusion.
        """
        result = await self._db.execute(
            text(
                "SELECT enabled, tier_required, percentage"
                " FROM feature_flags WHERE name = :name"
            ),
            {"name": flag_name},
        )
        row = result.fetchone()
        if not row:
            return False

        enabled, tier_required, percentage = row[0], row[1], row[2]

        if not enabled:
            return False

        if tier_required and user_tier:
            user_level = _TIER_ORDER.get(user_tier, 0)
            required_level = _TIER_ORDER.get(tier_required, 0)
            if user_level < required_level:
                return False

        if percentage < 100 and user_id:
            hash_val = int(
                hashlib.md5(f"{flag_name}:{user_id}".encode()).hexdigest()[:8],
                16,
            )
            if (hash_val % 100) >= percentage:
                return False

        return True

    async def get_all_flags(self) -> list[dict]:
        """Return all feature flags ordered alphabetically by name."""
        result = await self._db.execute(
            text(
                "SELECT name, enabled, tier_required, percentage, description"
                " FROM feature_flags ORDER BY name"
            )
        )
        return [
            {
                "name": r[0],
                "enabled": r[1],
                "tier_required": r[2],
                "percentage": r[3],
                "description": r[4],
            }
            for r in result.fetchall()
        ]

    async def update_flag(
        self,
        name: str,
        enabled: bool = None,
        tier_required: str = None,
        percentage: int = None,
    ) -> bool:
        """
        Partially update a feature flag's fields.

        Returns True when at least one field was provided and the UPDATE ran,
        False when no fields were supplied (caller should return 404/400).
        """
        set_parts: list[str] = []
        params: dict = {"name": name}

        if enabled is not None:
            set_parts.append("enabled = :enabled")
            params["enabled"] = enabled
        if tier_required is not None:
            set_parts.append("tier_required = :tier_required")
            params["tier_required"] = tier_required
        if percentage is not None:
            set_parts.append("percentage = :percentage")
            params["percentage"] = percentage

        if not set_parts:
            return False

        set_parts.append("updated_at = NOW()")
        sql = f"UPDATE feature_flags SET {', '.join(set_parts)} WHERE name = :name"
        await self._db.execute(text(sql), params)
        await self._db.commit()
        logger.info("feature_flag_updated", name=name, changes=set_parts)
        return True
