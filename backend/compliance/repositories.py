"""
Compliance Repositories

Data access layer for GDPR compliance data including consent records
and deletion logs.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Mapped, mapped_column

from config.database import Base
from models.consent import ConsentRecord, DeletionLog

# =============================================================================
# SQLAlchemy ORM Models
# =============================================================================


class ConsentRecordORM(Base):
    """SQLAlchemy ORM model for consent records.

    user_id is nullable because migration 023 changed the live schema FK from
    ON DELETE CASCADE to ON DELETE SET NULL — preserving consent audit records
    (GDPR legal evidence) even after the user account is erased.  The ORM
    declaration is aligned here to match the live database constraint.
    """

    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False)
    consent_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    withdrawal_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DeletionLogORM(Base):
    """SQLAlchemy ORM model for deletion audit logs.

    user_id is nullable to support GDPR Article 17 (Right to Erasure): when a
    user row is deleted the FK ON DELETE SET NULL fires, preserving the audit
    log entry with user_id = NULL.  Making the column NOT NULL would cause a
    FK violation the moment the parent user row is deleted.
    """

    __tablename__ = "deletion_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_by: Mapped[str] = mapped_column(String(100), nullable=False)
    deletion_type: Mapped[str] = mapped_column(String(20), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False)
    data_categories_deleted: Mapped[list] = mapped_column(JSON, nullable=False)
    legal_basis: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


# =============================================================================
# CONSENT REPOSITORY
# =============================================================================


class ConsentRepository:
    """
    Repository for consent record data access.

    Provides CRUD operations and specialized queries for consent management.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize consent repository.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def create(self, consent: ConsentRecord) -> ConsentRecord:
        """
        Create a new consent record.

        Args:
            consent: ConsentRecord to create

        Returns:
            Created ConsentRecord
        """
        orm_record = ConsentRecordORM(
            id=consent.id,
            user_id=consent.user_id,
            purpose=consent.purpose,
            consent_given=consent.consent_given,
            timestamp=consent.timestamp,
            ip_address=consent.ip_address,
            user_agent=consent.user_agent,
            consent_version=consent.consent_version,
            withdrawal_timestamp=consent.withdrawal_timestamp,
            metadata_json=consent.metadata,
        )

        self.session.add(orm_record)
        await self.session.commit()

        return consent

    async def get_by_id(self, consent_id: str) -> ConsentRecord | None:
        """
        Get consent record by ID.

        Args:
            consent_id: Consent record ID

        Returns:
            ConsentRecord if found, None otherwise
        """
        result = await self.session.execute(
            select(ConsentRecordORM).where(ConsentRecordORM.id == consent_id)
        )
        orm_record = result.scalar_one_or_none()

        if orm_record:
            return self._to_model(orm_record)
        return None

    async def get_by_user_id(self, user_id: str) -> list[ConsentRecord]:
        """
        Get all consent records for a user.

        Args:
            user_id: User's ID

        Returns:
            List of ConsentRecords ordered by timestamp descending
        """
        result = await self.session.execute(
            select(ConsentRecordORM)
            .where(ConsentRecordORM.user_id == user_id)
            .order_by(ConsentRecordORM.timestamp.desc())
        )
        orm_records = result.scalars().all()

        return [self._to_model(r) for r in orm_records]

    async def get_by_user_and_purpose(
        self,
        user_id: str,
        purpose: str,
    ) -> list[ConsentRecord]:
        """
        Get consent records for a user and specific purpose.

        Args:
            user_id: User's ID
            purpose: Consent purpose

        Returns:
            List of ConsentRecords
        """
        result = await self.session.execute(
            select(ConsentRecordORM)
            .where(ConsentRecordORM.user_id == user_id, ConsentRecordORM.purpose == purpose)
            .order_by(ConsentRecordORM.timestamp.desc())
        )
        orm_records = result.scalars().all()

        return [self._to_model(r) for r in orm_records]

    async def get_latest_by_user_and_purpose(
        self,
        user_id: str,
        purpose: str | None = None,
    ) -> dict[str, bool]:
        """
        Get latest consent status for each purpose.

        Uses DISTINCT ON to fetch only the most recent record per purpose
        in a single query instead of fetching all records and filtering
        in Python.

        Args:
            user_id: User's ID
            purpose: Optional specific purpose

        Returns:
            Dict mapping purpose to consent status
        """
        if purpose:
            query = text(
                "SELECT DISTINCT ON (purpose) purpose, consent_given "
                "FROM consent_records "
                "WHERE user_id = :uid AND purpose = :purpose "
                "ORDER BY purpose, timestamp DESC"
            )
            result = await self.session.execute(query, {"uid": user_id, "purpose": purpose})
        else:
            query = text(
                "SELECT DISTINCT ON (purpose) purpose, consent_given "
                "FROM consent_records "
                "WHERE user_id = :uid "
                "ORDER BY purpose, timestamp DESC"
            )
            result = await self.session.execute(query, {"uid": user_id})

        rows = result.fetchall()
        return {row[0]: row[1] for row in rows}

    async def delete_by_user_id(self, user_id: str) -> int:
        """
        Delete all consent records for a user.

        Note: Does NOT commit — caller is responsible for transaction management.
        This method is called from within the GDPR atomic deletion block, so
        committing here would break the parent transaction's rollback coverage.

        Args:
            user_id: User's ID

        Returns:
            Number of records deleted
        """
        result = await self.session.execute(
            text("DELETE FROM consent_records WHERE user_id = :user_id"), {"user_id": user_id}
        )

        return result.rowcount

    def _to_model(self, orm_record: ConsentRecordORM) -> ConsentRecord:
        """Convert ORM record to Pydantic model"""
        return ConsentRecord(
            id=orm_record.id,
            user_id=orm_record.user_id,
            purpose=orm_record.purpose,
            consent_given=orm_record.consent_given,
            timestamp=orm_record.timestamp,
            ip_address=orm_record.ip_address,
            user_agent=orm_record.user_agent,
            consent_version=orm_record.consent_version,
            withdrawal_timestamp=orm_record.withdrawal_timestamp,
            metadata=orm_record.metadata_json,
        )


# =============================================================================
# DELETION LOG REPOSITORY
# =============================================================================


class DeletionLogRepository:
    """
    Repository for deletion log data access.

    Deletion logs are immutable audit records.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize deletion log repository.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def create(self, deletion_log: DeletionLog) -> DeletionLog:
        """
        Create a new deletion log entry.

        Args:
            deletion_log: DeletionLog to create

        Returns:
            Created DeletionLog
        """
        orm_record = DeletionLogORM(
            id=deletion_log.id,
            user_id=deletion_log.user_id,
            deleted_at=deletion_log.deleted_at,
            deleted_by=deletion_log.deleted_by,
            deletion_type=deletion_log.deletion_type,
            ip_address=deletion_log.ip_address,
            user_agent=deletion_log.user_agent,
            data_categories_deleted=deletion_log.data_categories_deleted,
            legal_basis=deletion_log.legal_basis,
            metadata_json=deletion_log.metadata,
        )

        self.session.add(orm_record)
        await self.session.commit()

        return deletion_log

    async def get_by_user_id(self, user_id: str) -> list[DeletionLog]:
        """
        Get all deletion logs for a user.

        Args:
            user_id: User's ID

        Returns:
            List of DeletionLogs
        """
        result = await self.session.execute(
            select(DeletionLogORM)
            .where(DeletionLogORM.user_id == user_id)
            .order_by(DeletionLogORM.deleted_at.desc())
        )
        orm_records = result.scalars().all()

        return [self._to_model(r) for r in orm_records]

    def _to_model(self, orm_record: DeletionLogORM) -> DeletionLog:
        """Convert ORM record to Pydantic model"""
        return DeletionLog(
            id=orm_record.id,
            user_id=orm_record.user_id,
            deleted_at=orm_record.deleted_at,
            deleted_by=orm_record.deleted_by,
            deletion_type=orm_record.deletion_type,
            ip_address=orm_record.ip_address,
            user_agent=orm_record.user_agent,
            data_categories_deleted=orm_record.data_categories_deleted,
            legal_basis=orm_record.legal_basis,
            metadata=orm_record.metadata_json,
        )
