"""
Compliance Repositories

Data access layer for GDPR compliance data including consent records
and deletion logs.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import uuid4

from sqlalchemy import Column, String, Boolean, DateTime, JSON, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Mapped, mapped_column

from config.database import Base
from models.consent import ConsentRecord, DeletionLog


# =============================================================================
# SQLAlchemy ORM Models
# =============================================================================


class ConsentRecordORM(Base):
    """SQLAlchemy ORM model for consent records"""

    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False)
    consent_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    withdrawal_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class DeletionLogORM(Base):
    """SQLAlchemy ORM model for deletion audit logs"""

    __tablename__ = "deletion_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_by: Mapped[str] = mapped_column(String(36), nullable=False)
    deletion_type: Mapped[str] = mapped_column(String(20), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False)
    data_categories_deleted: Mapped[list] = mapped_column(JSON, nullable=False)
    legal_basis: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


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

    async def get_by_id(self, consent_id: str) -> Optional[ConsentRecord]:
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

    async def get_by_user_id(self, user_id: str) -> List[ConsentRecord]:
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
    ) -> List[ConsentRecord]:
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
            .where(
                ConsentRecordORM.user_id == user_id,
                ConsentRecordORM.purpose == purpose
            )
            .order_by(ConsentRecordORM.timestamp.desc())
        )
        orm_records = result.scalars().all()

        return [self._to_model(r) for r in orm_records]

    async def get_latest_by_user_and_purpose(
        self,
        user_id: str,
        purpose: Optional[str] = None,
    ) -> Dict[str, bool]:
        """
        Get latest consent status for each purpose.

        Args:
            user_id: User's ID
            purpose: Optional specific purpose

        Returns:
            Dict mapping purpose to consent status
        """
        # Get all records for user, ordered by timestamp
        records = await self.get_by_user_id(user_id)

        # Build dict of latest consent per purpose
        status = {}
        for record in records:
            if record.purpose not in status:
                status[record.purpose] = record.consent_given

        return status

    async def delete_by_user_id(self, user_id: str) -> int:
        """
        Delete all consent records for a user.

        Args:
            user_id: User's ID

        Returns:
            Number of records deleted
        """
        result = await self.session.execute(
            text("DELETE FROM consent_records WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        await self.session.commit()

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

    async def get_by_user_id(self, user_id: str) -> List[DeletionLog]:
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
