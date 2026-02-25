"""
Connection Service — orchestrates connection lifecycle.

Handles CRUD for user_connections, bill_uploads, and connection_extracted_rates.
All credential fields are encrypted at rest via AES-256-GCM.
"""

from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from utils.encryption import encrypt_field, decrypt_field, mask_account_number
import structlog

logger = structlog.get_logger()


class ConnectionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # List connections
    # ------------------------------------------------------------------

    async def list_connections(self, user_id: str) -> List[dict]:
        """Return all connections for a user, joined with supplier names."""
        result = await self.db.execute(
            text("""
                SELECT id, user_id, connection_type, supplier_id, supplier_name,
                       status, account_number_masked, email_provider, label, created_at
                FROM user_connections
                WHERE user_id = :user_id
                ORDER BY created_at DESC
            """),
            {"user_id": user_id},
        )
        rows = result.mappings().all()
        return [self._row_to_connection(row) for row in rows]

    # ------------------------------------------------------------------
    # Create connection
    # ------------------------------------------------------------------

    async def create_connection(
        self,
        user_id: str,
        connection_type: str,
        *,
        supplier_id: Optional[str] = None,
        supplier_name: Optional[str] = None,
        account_number_encrypted: Optional[bytes] = None,
        account_number_masked: Optional[str] = None,
        email_provider: Optional[str] = None,
        label: Optional[str] = None,
        status: str = "pending",
    ) -> dict:
        """Insert a new user_connection row and return it."""
        result = await self.db.execute(
            text("""
                INSERT INTO user_connections
                    (user_id, connection_type, status, supplier_id, supplier_name,
                     account_number_encrypted, account_number_masked,
                     email_provider, label, consent_given, consent_given_at)
                VALUES
                    (:user_id, :connection_type, :status, :supplier_id, :supplier_name,
                     :enc_acct, :masked_acct,
                     :email_provider, :label, TRUE, NOW())
                RETURNING id, user_id, connection_type, supplier_id, supplier_name,
                          status, account_number_masked, email_provider, label, created_at
            """),
            {
                "user_id": user_id,
                "connection_type": connection_type,
                "status": status,
                "supplier_id": supplier_id,
                "supplier_name": supplier_name,
                "enc_acct": account_number_encrypted,
                "masked_acct": account_number_masked,
                "email_provider": email_provider,
                "label": label,
            },
        )
        await self.db.commit()
        row = result.mappings().first()

        logger.info(
            "connection_created",
            user_id=user_id,
            connection_type=connection_type,
            connection_id=str(row["id"]),
        )

        return self._row_to_connection(row)

    # ------------------------------------------------------------------
    # Get single connection
    # ------------------------------------------------------------------

    async def get_connection(
        self, user_id: str, connection_id: str
    ) -> Optional[dict]:
        """Fetch a single connection owned by user_id."""
        result = await self.db.execute(
            text("""
                SELECT id, user_id, connection_type, supplier_id, supplier_name,
                       status, account_number_masked, email_provider, label, created_at
                FROM user_connections
                WHERE id = :connection_id AND user_id = :user_id
            """),
            {"connection_id": connection_id, "user_id": user_id},
        )
        row = result.mappings().first()
        if not row:
            return None
        return self._row_to_connection(row)

    # ------------------------------------------------------------------
    # Delete connection (soft delete → status = 'disconnected')
    # ------------------------------------------------------------------

    async def delete_connection(
        self, user_id: str, connection_id: str
    ) -> bool:
        """Soft-delete a connection. Returns True if updated, False if not found."""
        result = await self.db.execute(
            text("""
                UPDATE user_connections SET status = 'disconnected'
                WHERE id = :connection_id AND user_id = :user_id
                RETURNING id
            """),
            {"connection_id": connection_id, "user_id": user_id},
        )
        deleted = result.scalar_one_or_none()
        await self.db.commit()

        if deleted:
            logger.info(
                "connection_deleted",
                user_id=user_id,
                connection_id=connection_id,
            )
        return deleted is not None

    # ------------------------------------------------------------------
    # Extracted rates
    # ------------------------------------------------------------------

    async def get_extracted_rates(
        self, connection_id: str
    ) -> List[dict]:
        """Get all extracted rates for a connection, newest first."""
        result = await self.db.execute(
            text("""
                SELECT id, connection_id, rate_per_kwh, effective_date, source, raw_label
                FROM connection_extracted_rates
                WHERE connection_id = :connection_id
                ORDER BY effective_date DESC
            """),
            {"connection_id": connection_id},
        )
        return [dict(row) for row in result.mappings().all()]

    async def get_current_rate(self, connection_id: str) -> Optional[dict]:
        """Get the most recent extracted rate for a connection."""
        result = await self.db.execute(
            text("""
                SELECT id, connection_id, rate_per_kwh, effective_date, source, raw_label
                FROM connection_extracted_rates
                WHERE connection_id = :connection_id
                ORDER BY effective_date DESC
                LIMIT 1
            """),
            {"connection_id": connection_id},
        )
        row = result.mappings().first()
        if not row:
            return None
        return dict(row)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_connection(row) -> dict:
        """Convert a DB row mapping to a dict with string-safe fields."""
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "connection_type": row["connection_type"],
            "supplier_id": str(row["supplier_id"]) if row.get("supplier_id") else None,
            "supplier_name": row.get("supplier_name"),
            "status": row["status"],
            "account_number_masked": row.get("account_number_masked"),
            "email_provider": row.get("email_provider"),
            "label": row.get("label"),
            "created_at": str(row["created_at"]),
        }
