"""
Referral Service

Manages referral codes for user growth. Double-sided incentive:
referrer gets credit, referee gets extended trial.
Reward redemption deferred to Wave 3 (Stripe integration).
"""

import secrets
import string
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# 8-char alphanumeric codes (uppercase + digits, no ambiguous chars)
_CODE_ALPHABET = string.ascii_uppercase + string.digits
_CODE_LENGTH = 8
_MAX_RETRIES = 5


class ReferralError(Exception):
    pass


class ReferralService:
    """Service for referral code management."""

    def __init__(self, db: AsyncSession):
        self._db = db

    def _generate_code(self) -> str:
        """Generate a random 8-char alphanumeric code."""
        return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))

    async def generate_code(self, user_id: str) -> str:
        """Generate a new referral code for a user. Retries on collision."""
        for attempt in range(_MAX_RETRIES):
            code = self._generate_code()
            try:
                await self._db.execute(
                    text(
                        "INSERT INTO referrals (referrer_id, referral_code) "
                        "VALUES (:referrer_id, :code)"
                    ),
                    {"referrer_id": user_id, "code": code},
                )
                await self._db.commit()
                logger.info("referral_code_generated", user_id=user_id, code=code)
                return code
            except Exception:
                await self._db.rollback()
                if attempt == _MAX_RETRIES - 1:
                    raise ReferralError("Failed to generate unique referral code")
        raise ReferralError("Failed to generate unique referral code")

    async def get_or_create_code(self, user_id: str) -> str:
        """Return existing referral code or generate a new one."""
        result = await self._db.execute(
            text(
                "SELECT referral_code FROM referrals "
                "WHERE referrer_id = :user_id AND referee_id IS NULL AND status = 'pending' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"user_id": user_id},
        )
        row = result.scalar_one_or_none()
        if row:
            return row
        return await self.generate_code(user_id)

    async def get_referral_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Look up a referral by code."""
        result = await self._db.execute(
            text(
                "SELECT id, referrer_id, referee_id, referral_code, status, "
                "reward_applied, created_at, completed_at "
                "FROM referrals WHERE referral_code = :code"
            ),
            {"code": code.upper()},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def apply_referral(self, referee_id: str, code: str) -> Dict[str, Any]:
        """
        Apply a referral code for a new user.
        Validates: code exists, is pending, referee isn't the referrer.
        """
        code = code.upper()
        referral = await self.get_referral_by_code(code)

        if not referral:
            raise ReferralError("Invalid referral code")

        if referral["status"] != "pending":
            raise ReferralError("Referral code already used or expired")

        if referral["referee_id"] is not None:
            raise ReferralError("Referral code already claimed")

        if str(referral["referrer_id"]) == str(referee_id):
            raise ReferralError("Cannot use your own referral code")

        await self._db.execute(
            text(
                "UPDATE referrals SET referee_id = :referee_id "
                "WHERE id = :id AND status = 'pending'"
            ),
            {"referee_id": referee_id, "id": referral["id"]},
        )
        await self._db.commit()

        logger.info(
            "referral_applied",
            code=code,
            referrer_id=str(referral["referrer_id"]),
            referee_id=referee_id,
        )
        return {**referral, "referee_id": referee_id}

    async def complete_referral(self, referee_id: str) -> Optional[Dict[str, Any]]:
        """
        Mark referral complete after referee completes qualifying action.
        Sets status=completed, completed_at, reward_applied=True.
        """
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            text(
                "UPDATE referrals SET status = 'completed', "
                "completed_at = :now, reward_applied = TRUE "
                "WHERE referee_id = :referee_id AND status = 'pending' "
                "RETURNING id, referrer_id, referee_id, referral_code, status, "
                "reward_applied, created_at, completed_at"
            ),
            {"referee_id": referee_id, "now": now},
        )
        await self._db.commit()
        row = result.mappings().first()
        return dict(row) if row else None

    async def get_stats(self, user_id: str) -> Dict[str, Any]:
        """Get referral statistics for a user."""
        result = await self._db.execute(
            text(
                "SELECT "
                "  COUNT(*) AS total, "
                "  COUNT(*) FILTER (WHERE status = 'pending') AS pending, "
                "  COUNT(*) FILTER (WHERE status = 'completed') AS completed, "
                "  COUNT(*) FILTER (WHERE reward_applied = TRUE) AS reward_credits "
                "FROM referrals WHERE referrer_id = :user_id"
            ),
            {"user_id": user_id},
        )
        row = result.mappings().first()
        return {
            "total": row["total"] if row else 0,
            "pending": row["pending"] if row else 0,
            "completed": row["completed"] if row else 0,
            "reward_credits": row["reward_credits"] if row else 0,
        }
