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
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import structlog

from models.consent import ConsentPurpose, ConsentRecord, DeletionLog

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
        db_session=None,
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
        self.db_session = db_session

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
        metadata: dict[str, Any] | None = None,
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
            consent_given=consent_given,
        )

        try:
            record = ConsentRecord(
                id=str(uuid4()),
                user_id=user_id,
                purpose=purpose,
                consent_given=consent_given,
                timestamp=datetime.now(UTC),
                ip_address=ip_address,
                user_agent=user_agent,
                consent_version=consent_version,
                withdrawal_timestamp=None if consent_given else datetime.now(UTC),
                metadata=metadata,
            )

            await self.consent_repo.create(record)

            logger.info(
                "consent_recorded",
                consent_id=record.id,
                user_id=user_id,
                purpose=purpose,
            )

            return record

        except Exception as e:
            logger.error(
                "consent_recording_failed",
                user_id=user_id,
                purpose=purpose,
                error=str(e),
            )
            raise ConsentError(f"Failed to record consent: {str(e)}") from e

    async def get_consent_history(
        self,
        user_id: str,
        purpose: str | None = None,
    ) -> list[ConsentRecord]:
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
            logger.error("consent_history_fetch_failed", user_id=user_id, error=str(e))
            raise

    async def get_current_consent_status(
        self,
        user_id: str,
    ) -> dict[str, bool]:
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
            logger.error("consent_status_fetch_failed", user_id=user_id, error=str(e))
            raise

    async def withdraw_all_consents(
        self,
        user_id: str,
        ip_address: str,
        user_agent: str,
    ) -> list[ConsentRecord]:
        """
        Withdraw consent for all purposes (Article 21).

        All withdrawal records are inserted inside a single database
        transaction so the operation is atomic: either every purpose is
        withdrawn or none are (no partial/inconsistent consent state on
        failure).  Uses ``db_session`` directly with raw SQL to avoid the
        per-record commit in ``consent_repo.create()``.

        If no ``db_session`` is available, falls back to the non-atomic
        per-record path (backward compatibility with test fixtures that
        only inject repository mocks).

        Args:
            user_id: User's ID
            ip_address: Client IP for audit
            user_agent: Client user agent for audit

        Returns:
            List of withdrawal records created

        Raises:
            ConsentError: If the bulk withdrawal fails (all changes rolled back)
        """
        logger.info("withdrawing_all_consents", user_id=user_id)

        now = datetime.now(UTC)
        withdrawals: list[ConsentRecord] = []

        # Build all withdrawal records in memory first
        for purpose in ConsentPurpose:
            record = ConsentRecord(
                id=str(uuid4()),
                user_id=user_id,
                purpose=purpose.value,
                consent_given=False,
                timestamp=now,
                ip_address=ip_address,
                user_agent=user_agent,
                consent_version="1.0",
                withdrawal_timestamp=now,
                metadata={"bulk_withdrawal": True},
            )
            withdrawals.append(record)

        if self.db_session:
            # Atomic path: single transaction via raw SQL
            from sqlalchemy import text as sa_text

            try:
                for record in withdrawals:
                    await self.db_session.execute(
                        sa_text("""
                            INSERT INTO consent_records
                                (id, user_id, purpose, consent_given, timestamp,
                                 ip_address, user_agent, consent_version,
                                 withdrawal_timestamp, metadata_json)
                            VALUES
                                (:id, :user_id, :purpose, :consent_given, :ts,
                                 :ip_address, :user_agent, :consent_version,
                                 :withdrawal_ts, :metadata)
                        """),
                        {
                            "id": record.id,
                            "user_id": record.user_id,
                            "purpose": record.purpose,
                            "consent_given": record.consent_given,
                            "ts": record.timestamp,
                            "ip_address": record.ip_address,
                            "user_agent": record.user_agent,
                            "consent_version": record.consent_version,
                            "withdrawal_ts": record.withdrawal_timestamp,
                            "metadata": (
                                json.dumps(record.metadata) if record.metadata else None
                            ),
                        },
                    )

                # Single commit for the entire batch
                await self.db_session.commit()

            except Exception as e:
                await self.db_session.rollback()
                logger.error(
                    "bulk_consent_withdrawal_failed",
                    user_id=user_id,
                    error=str(e),
                )
                raise ConsentError(
                    f"Failed to withdraw all consents atomically: {str(e)}"
                ) from e
        else:
            # Fallback: per-record path (each record_consent commits individually)
            try:
                for record in withdrawals:
                    await self.consent_repo.create(record)
            except Exception as e:
                logger.error(
                    "consent_withdrawal_failed",
                    user_id=user_id,
                    error=str(e),
                )
                raise ConsentError(f"Failed to withdraw consents: {str(e)}") from e

        logger.info(
            "all_consents_withdrawn",
            user_id=user_id,
            withdrawal_count=len(withdrawals),
        )

        return withdrawals

    # -------------------------------------------------------------------------
    # Data Export (Article 15, 20)
    # -------------------------------------------------------------------------

    async def export_user_data(
        self,
        user_id: str,
    ) -> dict[str, Any]:
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
                        "action": log_entry.action,
                        "timestamp": str(log_entry.timestamp),
                        "details": getattr(log_entry, "details", {}),
                    }
                    for log_entry in logs
                ]

            # Get linked supplier accounts (if DB session available)
            supplier_accounts = []
            if self.db_session:
                try:
                    from sqlalchemy import text as sa_text

                    from utils.encryption import decrypt_field

                    result = await self.db_session.execute(
                        sa_text("""
                            SELECT usa.supplier_id, sr.name AS supplier_name,
                                   usa.account_number_encrypted, usa.meter_number_encrypted,
                                   usa.service_zip, usa.account_nickname, usa.is_primary,
                                   usa.created_at
                            FROM user_supplier_accounts usa
                            JOIN supplier_registry sr ON usa.supplier_id = sr.id
                            WHERE usa.user_id = :user_id
                        """),
                        {"user_id": user_id},
                    )
                    for row in result.mappings().all():
                        account_data = {
                            "supplier_id": str(row["supplier_id"]),
                            "supplier_name": row["supplier_name"],
                            "service_zip": row["service_zip"],
                            "account_nickname": row["account_nickname"],
                            "is_primary": row["is_primary"],
                            "created_at": str(row["created_at"]),
                        }
                        # For GDPR export, include decrypted account numbers
                        if row["account_number_encrypted"]:
                            try:
                                account_data["account_number"] = decrypt_field(
                                    bytes(row["account_number_encrypted"])
                                )
                            except Exception:
                                account_data["account_number"] = "(decryption failed)"
                        if row["meter_number_encrypted"]:
                            try:
                                account_data["meter_number"] = decrypt_field(
                                    bytes(row["meter_number_encrypted"])
                                )
                            except Exception:
                                account_data["meter_number"] = "(decryption failed)"
                        supplier_accounts.append(account_data)
                except Exception as e:
                    logger.warning("supplier_accounts_export_failed", error=str(e))

            # Get notifications
            notifications_data = []
            if self.db_session:
                try:
                    from sqlalchemy import text as sa_text

                    notif_result = await self.db_session.execute(
                        sa_text("""
                            SELECT id, type, title, body, read_at, created_at
                            FROM notifications WHERE user_id = :user_id
                            ORDER BY created_at DESC
                        """),
                        {"user_id": user_id},
                    )
                    for row in notif_result.mappings().all():
                        notifications_data.append(
                            {
                                "id": str(row["id"]),
                                "type": row["type"],
                                "title": row["title"],
                                "body": row.get("body"),
                                "read_at": (
                                    str(row["read_at"]) if row.get("read_at") else None
                                ),
                                "created_at": str(row["created_at"]),
                            }
                        )
                except Exception as e:
                    logger.warning("notifications_export_failed", error=str(e))

            # Get community data (posts, votes, reports)
            community_posts_data = []
            if self.db_session:
                try:
                    from sqlalchemy import text as sa_text

                    posts_result = await self.db_session.execute(
                        sa_text("""
                            SELECT id, region, utility_type, post_type, title, body,
                                   rate_per_unit, supplier_name, created_at
                            FROM community_posts WHERE user_id = :user_id
                            ORDER BY created_at DESC
                        """),
                        {"user_id": user_id},
                    )
                    for row in posts_result.mappings().all():
                        community_posts_data.append(
                            {
                                "id": str(row["id"]),
                                "region": row["region"],
                                "utility_type": row["utility_type"],
                                "post_type": row["post_type"],
                                "title": row["title"],
                                "body": row["body"],
                                "rate_per_unit": (
                                    str(row["rate_per_unit"])
                                    if row.get("rate_per_unit")
                                    else None
                                ),
                                "supplier_name": row.get("supplier_name"),
                                "created_at": str(row["created_at"]),
                            }
                        )
                except Exception as e:
                    logger.warning("community_posts_export_failed", error=str(e))

            # Get connection data (user_connections, bill_uploads, extracted_rates)
            connections_data = []
            bill_uploads_data = []
            extracted_rates_data = []
            if self.db_session:
                try:
                    from sqlalchemy import text as sa_text

                    # User connections
                    conn_result = await self.db_session.execute(
                        sa_text("""
                            SELECT id, connection_type, connection_method, supplier_name,
                                   label, status, created_at, updated_at
                            FROM user_connections WHERE user_id = :user_id
                        """),
                        {"user_id": user_id},
                    )
                    for row in conn_result.mappings().all():
                        connections_data.append(
                            {
                                "id": str(row["id"]),
                                "connection_type": row["connection_type"],
                                "connection_method": row.get("connection_method"),
                                "supplier_name": row.get("supplier_name"),
                                "label": row.get("label"),
                                "status": row["status"],
                                "created_at": str(row["created_at"]),
                                "updated_at": str(row.get("updated_at")),
                            }
                        )

                    # Bill uploads
                    bill_result = await self.db_session.execute(
                        sa_text("""
                            SELECT id, connection_id, filename, file_size, status,
                                   created_at
                            FROM bill_uploads WHERE connection_id IN (
                                SELECT id FROM user_connections WHERE user_id = :user_id
                            )
                        """),
                        {"user_id": user_id},
                    )
                    for row in bill_result.mappings().all():
                        bill_uploads_data.append(
                            {
                                "id": str(row["id"]),
                                "connection_id": str(row["connection_id"]),
                                "filename": row["filename"],
                                "file_size": row.get("file_size"),
                                "status": row["status"],
                                "created_at": str(row["created_at"]),
                            }
                        )

                    # Extracted rates
                    rates_result = await self.db_session.execute(
                        sa_text("""
                            SELECT id, connection_id, rate_amount, rate_unit,
                                   effective_date, utility_type
                            FROM connection_extracted_rates WHERE connection_id IN (
                                SELECT id FROM user_connections WHERE user_id = :user_id
                            )
                        """),
                        {"user_id": user_id},
                    )
                    for row in rates_result.mappings().all():
                        extracted_rates_data.append(
                            {
                                "id": str(row["id"]),
                                "connection_id": str(row["connection_id"]),
                                "rate_amount": str(row.get("rate_amount")),
                                "rate_unit": row.get("rate_unit"),
                                "effective_date": str(row.get("effective_date")),
                                "utility_type": row.get("utility_type"),
                            }
                        )
                except Exception as e:
                    logger.warning("connection_data_export_failed", error=str(e))

            export = {
                "user_id": user_id,
                "export_timestamp": datetime.now(UTC).isoformat(),
                "export_format_version": "1.3",
                "profile_data": profile_data,
                "preferences_data": preferences_data,
                "consent_history": consent_history,
                "price_alerts": price_alerts,
                "recommendations": recommendations,
                "activity_logs": activity_logs,
                "supplier_accounts": supplier_accounts,
                "connections": connections_data,
                "bill_uploads": bill_uploads_data,
                "extracted_rates": extracted_rates_data,
                "notifications": notifications_data,
                "community_posts": community_posts_data,
            }

            logger.info(
                "user_data_exported",
                user_id=user_id,
                data_categories=list(export.keys()),
            )

            return export

        except UserNotFoundError:
            raise
        except Exception as e:
            logger.error("data_export_failed", user_id=user_id, error=str(e))
            raise DataExportError(f"Failed to export user data: {str(e)}") from e

    # -------------------------------------------------------------------------
    # Data Deletion (Article 17)
    # -------------------------------------------------------------------------

    async def delete_user_data(
        self,
        user_id: str,
        deleted_by: str | None = None,
        ip_address: str = "0.0.0.0",
        user_agent: str = "System",
        anonymize_retained: bool = False,
    ) -> DeletionLog:
        """
        Delete all user data (Right to Erasure).

        Implements GDPR Article 17. All database deletions are executed
        within a single transaction — if any step fails, all changes
        are rolled back (atomic all-or-nothing semantics).

        File cleanup (bill upload files) happens after the DB commit
        and is best-effort; filesystem failures are logged but do not
        re-raise since the DB records are already gone.

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
            DataDeletionError: If deletion fails (all changes rolled back)
        """
        logger.info(
            "deleting_user_data",
            user_id=user_id,
            deleted_by=deleted_by or user_id,
            anonymize_retained=anonymize_retained,
        )

        # Verify user exists (read-only check before starting transaction)
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)

        if not self.db_session:
            raise DataDeletionError(
                "Database session required for atomic GDPR deletion"
            )

        from sqlalchemy import text as sa_text

        deleted_categories: list[str] = []
        upload_files_to_delete: list[str] = []

        try:
            # --- Atomic transaction: all DELETEs or none ---

            # 1. Delete consent records
            await self.db_session.execute(
                sa_text("DELETE FROM consent_records WHERE user_id = :uid"),
                {"uid": user_id},
            )
            deleted_categories.append("consents")

            # 2. Delete price alerts
            await self.db_session.execute(
                sa_text("DELETE FROM price_alerts WHERE user_id = :uid"),
                {"uid": user_id},
            )
            deleted_categories.append("price_alerts")

            # 3. Delete recommendations
            await self.db_session.execute(
                sa_text("DELETE FROM recommendations WHERE user_id = :uid"),
                {"uid": user_id},
            )
            deleted_categories.append("recommendations")

            # 4. Handle activity logs
            if anonymize_retained:
                await self.db_session.execute(
                    sa_text(
                        "UPDATE activity_logs SET user_id = 'anonymized' WHERE user_id = :uid"
                    ),
                    {"uid": user_id},
                )
            else:
                await self.db_session.execute(
                    sa_text("DELETE FROM activity_logs WHERE user_id = :uid"),
                    {"uid": user_id},
                )
            deleted_categories.append("activity_logs")

            # 5. Delete extracted rates (child of connections)
            await self.db_session.execute(
                sa_text("""
                    DELETE FROM connection_extracted_rates
                    WHERE connection_id IN (
                        SELECT id FROM user_connections WHERE user_id = :uid
                    )
                """),
                {"uid": user_id},
            )
            deleted_categories.append("extracted_rates")

            # 6. Collect bill upload file paths for post-commit cleanup
            bill_result = await self.db_session.execute(
                sa_text("""
                    SELECT id FROM bill_uploads
                    WHERE connection_id IN (
                        SELECT id FROM user_connections WHERE user_id = :uid
                    )
                """),
                {"uid": user_id},
            )
            for row in bill_result.mappings().all():
                import os

                upload_files_to_delete.append(os.path.join("uploads", str(row["id"])))

            await self.db_session.execute(
                sa_text("""
                    DELETE FROM bill_uploads
                    WHERE connection_id IN (
                        SELECT id FROM user_connections WHERE user_id = :uid
                    )
                """),
                {"uid": user_id},
            )
            deleted_categories.append("bill_uploads")

            # 7. Delete user connections
            await self.db_session.execute(
                sa_text("DELETE FROM user_connections WHERE user_id = :uid"),
                {"uid": user_id},
            )
            deleted_categories.append("connections")

            # 8. Delete supplier accounts
            await self.db_session.execute(
                sa_text("DELETE FROM user_supplier_accounts WHERE user_id = :uid"),
                {"uid": user_id},
            )
            deleted_categories.append("supplier_accounts")

            # 9. Delete AI agent data
            await self.db_session.execute(
                sa_text("DELETE FROM agent_conversations WHERE user_id = :uid"),
                {"uid": user_id},
            )
            await self.db_session.execute(
                sa_text("DELETE FROM agent_tasks WHERE user_id = :uid"),
                {"uid": user_id},
            )
            await self.db_session.execute(
                sa_text("DELETE FROM agent_usage_daily WHERE user_id = :uid"),
                {"uid": user_id},
            )
            deleted_categories.append("agent_data")

            # 10. Delete community data (votes/reports reference posts via CASCADE)
            await self.db_session.execute(
                sa_text("DELETE FROM community_votes WHERE user_id = :uid"),
                {"uid": user_id},
            )
            await self.db_session.execute(
                sa_text("DELETE FROM community_reports WHERE user_id = :uid"),
                {"uid": user_id},
            )
            await self.db_session.execute(
                sa_text("DELETE FROM community_posts WHERE user_id = :uid"),
                {"uid": user_id},
            )
            deleted_categories.append("community_data")

            # 11. Delete notifications
            await self.db_session.execute(
                sa_text("DELETE FROM notifications WHERE user_id = :uid"),
                {"uid": user_id},
            )
            deleted_categories.append("notifications")

            # 12. Delete feedback
            await self.db_session.execute(
                sa_text("DELETE FROM feedback WHERE user_id = :uid"),
                {"uid": user_id},
            )
            deleted_categories.append("feedback")

            # 13. Delete savings data
            await self.db_session.execute(
                sa_text("DELETE FROM user_savings WHERE user_id = :uid"),
                {"uid": user_id},
            )
            deleted_categories.append("savings")

            # 14. Delete recommendation outcomes
            await self.db_session.execute(
                sa_text("DELETE FROM recommendation_outcomes WHERE user_id = :uid"),
                {"uid": user_id},
            )
            deleted_categories.append("recommendation_outcomes")

            # 15. Delete ML predictions and A/B assignments
            await self.db_session.execute(
                sa_text("DELETE FROM model_predictions WHERE user_id = :uid"),
                {"uid": user_id},
            )
            await self.db_session.execute(
                sa_text("DELETE FROM model_ab_assignments WHERE user_id = :uid"),
                {"uid": user_id},
            )
            deleted_categories.append("ml_data")

            # 16. Delete referrals (as referrer; referee SET NULL via FK)
            await self.db_session.execute(
                sa_text("DELETE FROM referrals WHERE referrer_id = :uid"),
                {"uid": user_id},
            )
            deleted_categories.append("referrals")

            # 17. Delete user profile (last — FK constraints)
            await self.db_session.execute(
                sa_text("DELETE FROM users WHERE id = :uid"),
                {"uid": user_id},
            )
            deleted_categories.append("profile")

            # --- Build deletion log INSIDE the transaction [09-P0-3 fix] ---
            # The log is written before commit so that a crash between deletion
            # and log-persist cannot leave us with a user deleted but no audit
            # trail.  Both the deletion and the log record are atomic.
            #
            # Note: user_id is preserved in the log as the original user_id
            # string even though the users row is now deleted — the FK is
            # ON DELETE SET NULL, so after commit the DB will NULL it out.
            # We capture user_id in the log before that happens.
            deletion_log = DeletionLog(
                id=str(uuid4()),
                user_id=user_id,
                deleted_at=datetime.now(UTC),
                deleted_by=deleted_by or user_id,
                deletion_type="anonymization" if anonymize_retained else "full",
                ip_address=ip_address,
                user_agent=user_agent,
                data_categories_deleted=deleted_categories,
                legal_basis="user_request",
            )

            await self.db_session.execute(
                sa_text("""
                    INSERT INTO deletion_logs
                        (id, user_id, deleted_at, deleted_by, deletion_type,
                         ip_address, user_agent, data_categories_deleted, legal_basis)
                    VALUES
                        (:id, :user_id, :deleted_at, :deleted_by, :deletion_type,
                         :ip_address, :user_agent, :categories, :legal_basis)
                """),
                {
                    "id": deletion_log.id,
                    "user_id": deletion_log.user_id,
                    "deleted_at": deletion_log.deleted_at,
                    "deleted_by": deletion_log.deleted_by,
                    "deletion_type": deletion_log.deletion_type,
                    "ip_address": deletion_log.ip_address,
                    "user_agent": deletion_log.user_agent,
                    "categories": json.dumps(deletion_log.data_categories_deleted),
                    "legal_basis": deletion_log.legal_basis,
                },
            )

            # Single commit — deletions + audit log are fully atomic
            await self.db_session.commit()

        except Exception as e:
            await self.db_session.rollback()
            logger.error("data_deletion_failed", user_id=user_id, error=str(e))
            raise DataDeletionError(f"Failed to delete user data: {str(e)}") from e

        # --- Post-commit: best-effort file cleanup ---
        for path in upload_files_to_delete:
            try:
                import os

                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(
                    "gdpr_file_cleanup_failed",
                    user_id=user_id,
                    path=path,
                    error=str(e),
                )

        logger.info(
            "user_data_deleted", user_id=user_id, categories_deleted=deleted_categories
        )

        return deletion_log


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

    async def identify_expired_data(self) -> dict[str, list[str]]:
        """
        Identify data that has exceeded retention period.

        Returns:
            Dict mapping data category to list of expired record IDs
        """
        cutoff_date = datetime.now(UTC) - timedelta(days=self.retention_days)

        expired = {}

        if self.activity_log_repo:
            expired_logs = await self.activity_log_repo.get_before_date(cutoff_date)
            expired["activity_logs"] = [log.id for log in expired_logs]

        return expired

    async def purge_expired_data(
        self,
        respect_legal_holds: bool = True,
    ) -> dict[str, int]:
        """
        Purge data that has exceeded retention period.

        Args:
            respect_legal_holds: Whether to skip data under legal hold

        Returns:
            Dict mapping data category to count of purged records
        """
        logger.info("purging_expired_data", retention_days=self.retention_days)

        cutoff_date = datetime.now(UTC) - timedelta(days=self.retention_days)
        purged = {}

        if self.activity_log_repo:
            count = await self.activity_log_repo.delete_before_date(
                cutoff_date, respect_legal_holds=respect_legal_holds
            )
            purged["activity_logs"] = count

        logger.info("expired_data_purged", purged_counts=purged)

        return purged
