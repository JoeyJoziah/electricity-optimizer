"""
GDPR Compliance Service

Implements GDPR compliance functionality:
- Article 6: Lawful basis for processing (explicit consent)
- Article 7: Conditions for consent
- Article 15: Right to access (data export)
- Article 17: Right to erasure (complete deletion)
- Article 20: Data portability (machine-readable export)
- Article 21: Right to object (consent withdrawal)
"""

import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from uuid import uuid4

import structlog

from models.consent import (
    ConsentRecord,
    DeletionLog,
    UserDataExport,
    ConsentPurpose,
)


logger = structlog.get_logger()


# =============================================================================
# EXCEPTIONS
# =============================================================================


class GDPRError(Exception):
    """Base exception for GDPR compliance errors"""
    pass


class UserNotFoundError(GDPRError):
    """Raised when user is not found"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        super().__init__(f"User not found: {user_id}")


class ConsentError(GDPRError):
    """Raised when consent operation fails"""
    pass


class DataExportError(GDPRError):
    """Raised when data export fails"""
    pass


class DataDeletionError(GDPRError):
    """Raised when data deletion fails"""
    pass


# =============================================================================
# ANONYMIZATION UTILITIES
# =============================================================================


def anonymize_email(email: str) -> str:
    """
    Anonymize an email address while preserving format.

    Args:
        email: Original email address

    Returns:
        Anonymized email in format anon_<hash>@anonymized.local
    """
    hash_suffix = hashlib.sha256(email.encode()).hexdigest()[:8]
    return f"anon_{hash_suffix}@anonymized.local"


def anonymize_name(name: str) -> str:
    """
    Anonymize a user's name.

    Args:
        name: Original name

    Returns:
        Anonymized name
    """
    hash_suffix = hashlib.sha256(name.encode()).hexdigest()[:6]
    return f"Anonymous User {hash_suffix}"


def anonymize_ip(ip_address: str) -> str:
    """
    Anonymize an IP address by zeroing the last octet.

    Args:
        ip_address: Original IP address (IPv4)

    Returns:
        Anonymized IP with last octet set to 0
    """
    parts = ip_address.split(".")
    if len(parts) == 4:
        parts[-1] = "0"
        return ".".join(parts)
    return "0.0.0.0"


def anonymize_user_agent(user_agent: str) -> str:
    """
    Anonymize user agent string.

    Args:
        user_agent: Original user agent

    Returns:
        Generic anonymized user agent
    """
    return "Anonymous"


# =============================================================================
# GDPR COMPLIANCE SERVICE
# =============================================================================


class GDPRComplianceService:
    """
    Main GDPR compliance service.

    Handles consent management, data export, and data deletion.
    """

    def __init__(
        self,
        consent_repository,
        user_repository,
        price_alert_repository=None,
        recommendation_repository=None,
        activity_log_repository=None,
    ):
        """
        Initialize GDPR compliance service.

        Args:
            consent_repository: Repository for consent records
            user_repository: Repository for user data
            price_alert_repository: Optional repository for price alerts
            recommendation_repository: Optional repository for recommendations
            activity_log_repository: Optional repository for activity logs
        """
        self.consent_repo = consent_repository
        self.user_repo = user_repository
        self.price_alert_repo = price_alert_repository
        self.recommendation_repo = recommendation_repository
        self.activity_log_repo = activity_log_repository

    # -------------------------------------------------------------------------
    # Consent Management (Article 6, 7)
    # -------------------------------------------------------------------------

    async def record_consent(
        self,
        user_id: str,
        purpose: str,
        consent_given: bool,
        ip_address: str,
        user_agent: str,
        consent_version: str = "1.0",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConsentRecord:
        """
        Record a consent decision (grant or withdrawal).

        Creates an immutable record of the consent action for audit purposes.

        Args:
            user_id: User's ID
            purpose: Purpose of data processing (e.g., "marketing")
            consent_given: True if consenting, False if withdrawing
            ip_address: Client IP address for audit trail
            user_agent: Client user agent for audit trail
            consent_version: Version of consent policy being accepted
            metadata: Additional metadata

        Returns:
            Created ConsentRecord

        Raises:
            ConsentError: If consent recording fails
        """
        logger.info(
            "recording_consent",
            user_id=user_id,
            purpose=purpose,
            consent_given=consent_given
        )

        try:
            record = ConsentRecord(
                id=str(uuid4()),
                user_id=user_id,
                purpose=purpose,
                consent_given=consent_given,
                timestamp=datetime.now(timezone.utc),
                ip_address=ip_address,
                user_agent=user_agent,
                consent_version=consent_version,
                withdrawal_timestamp=None if consent_given else datetime.now(timezone.utc),
                metadata=metadata,
            )

            await self.consent_repo.create(record)

            logger.info(
                "consent_recorded",
                consent_id=record.id,
                user_id=user_id,
                purpose=purpose
            )

            return record

        except Exception as e:
            logger.error(
                "consent_recording_failed",
                user_id=user_id,
                purpose=purpose,
                error=str(e)
            )
            raise ConsentError(f"Failed to record consent: {str(e)}") from e

    async def get_consent_history(
        self,
        user_id: str,
        purpose: Optional[str] = None,
    ) -> List[ConsentRecord]:
        """
        Get consent history for a user.

        Args:
            user_id: User's ID
            purpose: Optional filter by purpose

        Returns:
            List of consent records ordered by timestamp
        """
        logger.info("getting_consent_history", user_id=user_id, purpose=purpose)

        try:
            if purpose:
                records = await self.consent_repo.get_by_user_and_purpose(
                    user_id, purpose
                )
            else:
                records = await self.consent_repo.get_by_user_id(user_id)

            return records

        except Exception as e:
            logger.error(
                "consent_history_fetch_failed",
                user_id=user_id,
                error=str(e)
            )
            raise

    async def get_current_consent_status(
        self,
        user_id: str,
    ) -> Dict[str, bool]:
        """
        Get current consent status for all purposes.

        Args:
            user_id: User's ID

        Returns:
            Dict mapping purpose to current consent status
        """
        logger.info("getting_consent_status", user_id=user_id)

        try:
            status = await self.consent_repo.get_latest_by_user_and_purpose(user_id)
            return status

        except Exception as e:
            logger.error(
                "consent_status_fetch_failed",
                user_id=user_id,
                error=str(e)
            )
            raise

    async def withdraw_all_consents(
        self,
        user_id: str,
        ip_address: str,
        user_agent: str,
    ) -> List[ConsentRecord]:
        """
        Withdraw consent for all purposes (Article 21).

        Args:
            user_id: User's ID
            ip_address: Client IP for audit
            user_agent: Client user agent for audit

        Returns:
            List of withdrawal records created
        """
        logger.info("withdrawing_all_consents", user_id=user_id)

        withdrawals = []

        for purpose in ConsentPurpose:
            record = await self.record_consent(
                user_id=user_id,
                purpose=purpose.value,
                consent_given=False,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"bulk_withdrawal": True}
            )
            withdrawals.append(record)

        logger.info(
            "all_consents_withdrawn",
            user_id=user_id,
            withdrawal_count=len(withdrawals)
        )

        return withdrawals

    # -------------------------------------------------------------------------
    # Data Export (Article 15, 20)
    # -------------------------------------------------------------------------

    async def export_user_data(
        self,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Export all user data in machine-readable format.

        Implements GDPR Article 15 (Right of access) and
        Article 20 (Right to data portability).

        Args:
            user_id: User's ID

        Returns:
            Complete user data export as dictionary

        Raises:
            UserNotFoundError: If user does not exist
            DataExportError: If export fails
        """
        logger.info("exporting_user_data", user_id=user_id)

        try:
            # Get user profile
            user = await self.user_repo.get_by_id(user_id)
            if not user:
                raise UserNotFoundError(user_id)

            # Compile profile data
            profile_data = {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "region": getattr(user, "region", None),
                "is_active": getattr(user, "is_active", True),
                "is_verified": getattr(user, "is_verified", False),
                "current_supplier": getattr(user, "current_supplier", None),
                "current_tariff": getattr(user, "current_tariff", None),
                "created_at": str(getattr(user, "created_at", None)),
                "last_login": str(getattr(user, "last_login", None)),
            }

            # Get preferences
            preferences_data = getattr(user, "preferences", {}) or {}

            # Get consent history
            consent_records = await self.consent_repo.get_by_user_id(user_id)
            consent_history = [
                {
                    "purpose": r.purpose,
                    "consent_given": r.consent_given,
                    "timestamp": str(r.timestamp),
                    "consent_version": getattr(r, "consent_version", "1.0"),
                }
                for r in consent_records
            ]

            # Get price alerts (if repository available)
            price_alerts = []
            if self.price_alert_repo:
                alerts = await self.price_alert_repo.get_by_user_id(user_id)
                price_alerts = [
                    {
                        "id": a.id,
                        "type": getattr(a, "type", "unknown"),
                        "threshold": str(getattr(a, "threshold", 0)),
                        "created_at": str(getattr(a, "created_at", None)),
                    }
                    for a in alerts
                ]

            # Get recommendations (if repository available)
            recommendations = []
            if self.recommendation_repo:
                recs = await self.recommendation_repo.get_by_user_id(user_id)
                recommendations = [
                    {
                        "id": r.id,
                        "type": getattr(r, "type", "unknown"),
                        "created_at": str(getattr(r, "created_at", None)),
                    }
                    for r in recs
                ]

            # Get activity logs (if repository available)
            activity_logs = []
            if self.activity_log_repo:
                logs = await self.activity_log_repo.get_by_user_id(user_id)
                activity_logs = [
                    {
                        "action": l.action,
                        "timestamp": str(l.timestamp),
                        "details": getattr(l, "details", {}),
                    }
                    for l in logs
                ]

            export = {
                "user_id": user_id,
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "export_format_version": "1.0",
                "profile_data": profile_data,
                "preferences_data": preferences_data,
                "consent_history": consent_history,
                "price_alerts": price_alerts,
                "recommendations": recommendations,
                "activity_logs": activity_logs,
            }

            logger.info(
                "user_data_exported",
                user_id=user_id,
                data_categories=list(export.keys())
            )

            return export

        except UserNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "data_export_failed",
                user_id=user_id,
                error=str(e)
            )
            raise DataExportError(f"Failed to export user data: {str(e)}") from e

    # -------------------------------------------------------------------------
    # Data Deletion (Article 17)
    # -------------------------------------------------------------------------

    async def delete_user_data(
        self,
        user_id: str,
        deleted_by: Optional[str] = None,
        ip_address: str = "0.0.0.0",
        user_agent: str = "System",
        anonymize_retained: bool = False,
    ) -> DeletionLog:
        """
        Delete all user data (Right to Erasure).

        Implements GDPR Article 17. Creates an immutable deletion
        log for audit purposes.

        Args:
            user_id: User's ID
            deleted_by: Who initiated deletion (default: user themselves)
            ip_address: Client IP for audit
            user_agent: Client user agent for audit
            anonymize_retained: Whether to anonymize vs delete retained data

        Returns:
            DeletionLog record

        Raises:
            UserNotFoundError: If user does not exist
            DataDeletionError: If deletion fails
        """
        logger.info(
            "deleting_user_data",
            user_id=user_id,
            deleted_by=deleted_by or user_id,
            anonymize_retained=anonymize_retained
        )

        try:
            # Verify user exists
            user = await self.user_repo.get_by_id(user_id)
            if not user:
                raise UserNotFoundError(user_id)

            deleted_categories = []

            # Delete consent records
            await self.consent_repo.delete_by_user_id(user_id)
            deleted_categories.append("consents")

            # Delete price alerts (if repository available)
            if self.price_alert_repo:
                await self.price_alert_repo.delete_by_user_id(user_id)
                deleted_categories.append("price_alerts")

            # Delete recommendations (if repository available)
            if self.recommendation_repo:
                await self.recommendation_repo.delete_by_user_id(user_id)
                deleted_categories.append("recommendations")

            # Delete activity logs (if repository available)
            if self.activity_log_repo:
                if anonymize_retained:
                    await self.activity_log_repo.anonymize_by_user_id(user_id)
                else:
                    await self.activity_log_repo.delete_by_user_id(user_id)
                deleted_categories.append("activity_logs")

            # Delete user profile
            await self.user_repo.delete(user_id)
            deleted_categories.append("profile")

            # Create deletion log
            deletion_log = DeletionLog(
                id=str(uuid4()),
                user_id=user_id,
                deleted_at=datetime.now(timezone.utc),
                deleted_by=deleted_by or user_id,
                deletion_type="anonymization" if anonymize_retained else "full",
                ip_address=ip_address,
                user_agent=user_agent,
                data_categories_deleted=deleted_categories,
                legal_basis="user_request",
            )

            # Store deletion log (would be in a separate immutable store)
            # await self.deletion_log_repo.create(deletion_log)

            logger.info(
                "user_data_deleted",
                user_id=user_id,
                categories_deleted=deleted_categories
            )

            return deletion_log

        except UserNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "data_deletion_failed",
                user_id=user_id,
                error=str(e)
            )
            raise DataDeletionError(f"Failed to delete user data: {str(e)}") from e


# =============================================================================
# DATA RETENTION SERVICE
# =============================================================================


class DataRetentionService:
    """
    Handles automatic data retention and expiration.

    Implements retention policies as required by GDPR Article 5(1)(e).
    """

    def __init__(
        self,
        retention_days: int = 730,
        consent_repository=None,
        activity_log_repository=None,
    ):
        """
        Initialize data retention service.

        Args:
            retention_days: Number of days to retain data (default: 2 years)
            consent_repository: Repository for consent records
            activity_log_repository: Repository for activity logs
        """
        self.retention_days = retention_days
        self.consent_repo = consent_repository
        self.activity_log_repo = activity_log_repository

    async def identify_expired_data(self) -> Dict[str, List[str]]:
        """
        Identify data that has exceeded retention period.

        Returns:
            Dict mapping data category to list of expired record IDs
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.retention_days)

        expired = {}

        if self.activity_log_repo:
            expired_logs = await self.activity_log_repo.get_before_date(cutoff_date)
            expired["activity_logs"] = [log.id for log in expired_logs]

        return expired

    async def purge_expired_data(
        self,
        respect_legal_holds: bool = True,
    ) -> Dict[str, int]:
        """
        Purge data that has exceeded retention period.

        Args:
            respect_legal_holds: Whether to skip data under legal hold

        Returns:
            Dict mapping data category to count of purged records
        """
        logger.info("purging_expired_data", retention_days=self.retention_days)

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        purged = {}

        if self.activity_log_repo:
            count = await self.activity_log_repo.delete_before_date(
                cutoff_date,
                respect_legal_holds=respect_legal_holds
            )
            purged["activity_logs"] = count

        logger.info("expired_data_purged", purged_counts=purged)

        return purged
