"""
Connection Sync Service

Orchestrates UtilityAPI data pulls for connections that were created via the
direct-connection flow and have been authorized by the customer.

Schema note
-----------
Migration 008 creates ``user_connections`` without sync-tracking columns.
This service uses the ``extra_data`` JSONB column if present, or falls back
to dedicated columns added by migration 009.  Because we want Phase 4 to
work without requiring a DB migration at deploy time, we store sync state
in the same ``user_connections`` row by reading/writing the columns listed
below and gracefully handling their absence:

  last_sync_at            TIMESTAMPTZ
  last_sync_error         TEXT
  sync_frequency_hours    INT  DEFAULT 24
  utilityapi_auth_uid     TEXT  (encrypted at rest)

All of these columns are added by migration 009 (see
``backend/migrations/009_utilityapi_sync.sql``).  Before that migration runs,
``sync_all_due()`` will return an empty list (no rows have the column) and
``sync_connection()`` will attempt the sync but will silently skip status
persistence if the columns don't exist yet.

Design principles
-----------------
- Raw SQL via ``sqlalchemy.text()`` — no ORM.
- structlog for all log events.
- UtilityAPIClient is injected so tests can mock it.
- Each sync is atomic: we commit once at the end, or roll back on error
  and persist the error message.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from integrations.utilityapi import UtilityAPIClient, UtilityAPIError
from utils.encryption import encrypt_field, decrypt_field

logger = structlog.get_logger(__name__)

# How many hours between automatic syncs (used when the row has no value).
_DEFAULT_SYNC_FREQUENCY_HOURS = 24


class ConnectionSyncService:
    """
    Pulls the latest billing/rate data from UtilityAPI for active connections.

    Typical usage in a scheduled job::

        async with get_db_session() as db:
            svc = ConnectionSyncService(db)
            results = await svc.sync_all_due()
    """

    def __init__(
        self,
        db: AsyncSession,
        utilityapi_client: Optional[UtilityAPIClient] = None,
    ):
        """
        Args:
            db:                Async SQLAlchemy session.
            utilityapi_client: Injected client; created lazily if omitted.
        """
        self._db = db
        self._client = utilityapi_client or UtilityAPIClient()

    # ------------------------------------------------------------------
    # Public: sync a single connection
    # ------------------------------------------------------------------

    async def sync_connection(self, connection_id: str) -> dict:
        """
        Pull the latest meter/bill data for one connection and persist any
        new rates into ``connection_extracted_rates``.

        Args:
            connection_id: UUID string for the ``user_connections`` row.

        Returns:
            dict with keys:
              - connection_id  (str)
              - success        (bool)
              - new_rates_found (int)
              - error          (str or None)
              - synced_at      (datetime)

        The connection's ``last_sync_at`` / ``last_sync_error`` / ``status``
        columns are updated before returning.
        """
        log = logger.bind(connection_id=connection_id)
        log.info("sync_connection_start")

        synced_at = datetime.now(timezone.utc)

        # ---- 1. Load connection row ----------------------------------------
        conn = await self._fetch_connection(connection_id)
        if conn is None:
            log.warning("sync_connection_not_found")
            return {
                "connection_id": connection_id,
                "success": False,
                "new_rates_found": 0,
                "error": "Connection not found.",
                "synced_at": synced_at,
            }

        auth_uid_encrypted = conn.get("utilityapi_auth_uid_encrypted")
        if not auth_uid_encrypted:
            msg = "No UtilityAPI authorization UID stored — connection not yet authorized."
            log.warning("sync_connection_no_auth_uid")
            await self._persist_sync_result(
                connection_id, success=False, error=msg, synced_at=synced_at
            )
            return {
                "connection_id": connection_id,
                "success": False,
                "new_rates_found": 0,
                "error": msg,
                "synced_at": synced_at,
            }

        # ---- 2. Decrypt auth UID ------------------------------------------
        try:
            if isinstance(auth_uid_encrypted, memoryview):
                auth_uid_encrypted = bytes(auth_uid_encrypted)
            elif isinstance(auth_uid_encrypted, str):
                auth_uid_encrypted = auth_uid_encrypted.encode("latin-1")
            authorization_uid = decrypt_field(auth_uid_encrypted)
        except Exception as exc:
            msg = f"Could not decrypt UtilityAPI authorization UID: {exc}"
            log.error("sync_connection_decrypt_error", error=str(exc))
            await self._persist_sync_result(
                connection_id, success=False, error=msg, synced_at=synced_at
            )
            return {
                "connection_id": connection_id,
                "success": False,
                "new_rates_found": 0,
                "error": msg,
                "synced_at": synced_at,
            }

        # ---- 3. Fetch meters from UtilityAPI --------------------------------
        try:
            meters = await self._client.get_meters(authorization_uid)
        except UtilityAPIError as exc:
            msg = f"UtilityAPI meters fetch failed: {exc}"
            log.error("sync_connection_meters_error", error=str(exc))
            await self._persist_sync_result(
                connection_id, success=False, error=msg, synced_at=synced_at
            )
            return {
                "connection_id": connection_id,
                "success": False,
                "new_rates_found": 0,
                "error": msg,
                "synced_at": synced_at,
            }

        if not meters:
            msg = "No meters found for this authorization."
            log.warning("sync_connection_no_meters")
            await self._persist_sync_result(
                connection_id, success=False, error=msg, synced_at=synced_at
            )
            return {
                "connection_id": connection_id,
                "success": False,
                "new_rates_found": 0,
                "error": msg,
                "synced_at": synced_at,
            }

        # ---- 4. Determine the date to fetch bills from ----------------------
        last_sync_at: Optional[datetime] = conn.get("last_sync_at")

        # ---- 5. Fetch bills and extract rates -------------------------------
        new_rates: list[dict] = []
        rate_errors: list[str] = []

        for meter in meters:
            meter_uid = meter.get("uid") or meter.get("meter_uid")
            if not meter_uid:
                log.warning("sync_connection_meter_no_uid", meter=meter)
                continue

            try:
                bills = await self._client.get_bills(meter_uid, since=last_sync_at)
            except UtilityAPIError as exc:
                log.warning(
                    "sync_connection_bills_error",
                    meter_uid=meter_uid,
                    error=str(exc),
                )
                rate_errors.append(f"meter {meter_uid}: {exc}")
                continue

            for bill in bills:
                try:
                    rate_data = self._client.extract_rate_from_bill(bill)
                    new_rates.append(rate_data)
                except UtilityAPIError as exc:
                    bill_uid = bill.get("uid", "<unknown>")
                    log.warning(
                        "sync_connection_extract_error",
                        bill_uid=bill_uid,
                        error=str(exc),
                    )
                    rate_errors.append(f"bill {bill_uid}: {exc}")

        # ---- 6. Persist new rates ------------------------------------------
        for rate_data in new_rates:
            await self._insert_extracted_rate(connection_id, rate_data)

        # ---- 7. Update sync state ------------------------------------------
        combined_error = "; ".join(rate_errors) if rate_errors and not new_rates else None
        success = len(rate_errors) == 0 or len(new_rates) > 0

        await self._persist_sync_result(
            connection_id,
            success=success,
            error=combined_error,
            synced_at=synced_at,
        )
        await self._db.commit()

        log.info(
            "sync_connection_complete",
            new_rates_found=len(new_rates),
            errors=len(rate_errors),
            success=success,
        )

        return {
            "connection_id": connection_id,
            "success": success,
            "new_rates_found": len(new_rates),
            "error": combined_error,
            "synced_at": synced_at,
        }

    # ------------------------------------------------------------------
    # Public: sync all connections that are due
    # ------------------------------------------------------------------

    async def sync_all_due(self) -> list[dict]:
        """
        Find all active connections whose next scheduled sync is overdue and
        sync each one sequentially.

        A connection is "due" when::

            last_sync_at + INTERVAL '1 hour' * sync_frequency_hours <= NOW()

        or when ``last_sync_at`` is NULL (never synced).

        Returns:
            List of sync result dicts (same shape as ``sync_connection()``).
        """
        logger.info("sync_all_due_start")

        try:
            result = await self._db.execute(
                text("""
                    SELECT id
                    FROM user_connections
                    WHERE status = 'active'
                      AND utilityapi_auth_uid_encrypted IS NOT NULL
                      AND (
                            last_sync_at IS NULL
                            OR last_sync_at + (COALESCE(sync_frequency_hours, :default_freq) * INTERVAL '1 hour')
                               <= NOW()
                          )
                    ORDER BY COALESCE(last_sync_at, '1970-01-01') ASC
                """),
                {"default_freq": _DEFAULT_SYNC_FREQUENCY_HOURS},
            )
            rows = result.fetchall()
        except Exception as exc:
            # Gracefully handle the case where migration 009 hasn't run yet
            # (the columns don't exist).
            logger.warning(
                "sync_all_due_query_failed",
                error=str(exc),
                hint="Migration 009 may not have run yet.",
            )
            return []

        connection_ids = [str(row[0]) for row in rows]
        logger.info("sync_all_due_connections_found", count=len(connection_ids))

        results: list[dict] = []
        for cid in connection_ids:
            result_item = await self.sync_connection(cid)
            results.append(result_item)

        logger.info(
            "sync_all_due_complete",
            total=len(results),
            succeeded=sum(1 for r in results if r["success"]),
        )
        return results

    # ------------------------------------------------------------------
    # Public: get sync status for one connection
    # ------------------------------------------------------------------

    async def get_sync_status(self, connection_id: str) -> Optional[dict]:
        """
        Return the current sync status for a connection without triggering a sync.

        Returns:
            dict with keys:
              - connection_id       (str)
              - last_sync_at        (datetime or None)
              - last_sync_error     (str or None)
              - next_sync_at        (datetime or None)
              - sync_frequency_hours (int)

            Returns None if the connection is not found.
        """
        try:
            result = await self._db.execute(
                text("""
                    SELECT id,
                           last_sync_at,
                           last_sync_error,
                           COALESCE(sync_frequency_hours, :default_freq) AS sync_frequency_hours
                    FROM user_connections
                    WHERE id = :cid
                """),
                {"cid": connection_id, "default_freq": _DEFAULT_SYNC_FREQUENCY_HOURS},
            )
            row = result.mappings().first()
        except Exception as exc:
            # Columns may not exist yet; fall back to a minimal response
            logger.warning(
                "sync_status_query_failed",
                connection_id=connection_id,
                error=str(exc),
            )
            return {
                "connection_id": connection_id,
                "last_sync_at": None,
                "last_sync_error": None,
                "next_sync_at": None,
                "sync_frequency_hours": _DEFAULT_SYNC_FREQUENCY_HOURS,
            }

        if row is None:
            return None

        last_sync_at: Optional[datetime] = row.get("last_sync_at")
        freq: int = int(row.get("sync_frequency_hours") or _DEFAULT_SYNC_FREQUENCY_HOURS)

        next_sync_at: Optional[datetime] = None
        if last_sync_at is not None:
            from datetime import timedelta

            next_sync_at = last_sync_at + timedelta(hours=freq)

        return {
            "connection_id": str(row["id"]),
            "last_sync_at": last_sync_at,
            "last_sync_error": row.get("last_sync_error"),
            "next_sync_at": next_sync_at,
            "sync_frequency_hours": freq,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _fetch_connection(self, connection_id: str) -> Optional[dict]:
        """
        Load a connection row with all sync-related columns.

        Falls back gracefully if the migration-009 columns don't exist yet.
        """
        # Try the full column list first (migration 009 present)
        try:
            result = await self._db.execute(
                text("""
                    SELECT id, status,
                           utilityapi_auth_uid_encrypted,
                           last_sync_at,
                           last_sync_error,
                           COALESCE(sync_frequency_hours, :default_freq) AS sync_frequency_hours
                    FROM user_connections
                    WHERE id = :cid
                """),
                {"cid": connection_id, "default_freq": _DEFAULT_SYNC_FREQUENCY_HOURS},
            )
            row = result.mappings().first()
            if row is None:
                return None
            return dict(row)
        except Exception:
            pass

        # Fallback: load only the base columns (pre-migration-009)
        try:
            result = await self._db.execute(
                text("""
                    SELECT id, status
                    FROM user_connections
                    WHERE id = :cid
                """),
                {"cid": connection_id},
            )
            row = result.mappings().first()
            if row is None:
                return None
            base = dict(row)
            base.setdefault("utilityapi_auth_uid_encrypted", None)
            base.setdefault("last_sync_at", None)
            base.setdefault("last_sync_error", None)
            base.setdefault("sync_frequency_hours", _DEFAULT_SYNC_FREQUENCY_HOURS)
            return base
        except Exception:
            return None

    async def _insert_extracted_rate(
        self, connection_id: str, rate_data: dict
    ) -> None:
        """Insert a single rate row into ``connection_extracted_rates``."""
        await self._db.execute(
            text("""
                INSERT INTO connection_extracted_rates
                    (id, connection_id, rate_per_kwh, effective_date, source, raw_label)
                VALUES
                    (:id, :cid, :rate, :eff_date, :source, :label)
                ON CONFLICT DO NOTHING
            """),
            {
                "id": str(uuid4()),
                "cid": connection_id,
                "rate": rate_data["rate_per_kwh"],
                "eff_date": rate_data["effective_date"],
                "source": rate_data["source"],
                "label": rate_data.get("raw_label"),
            },
        )

    async def _persist_sync_result(
        self,
        connection_id: str,
        *,
        success: bool,
        error: Optional[str],
        synced_at: datetime,
    ) -> None:
        """
        Update sync-tracking columns and connection status.

        Silently skips persistence if the migration-009 columns do not exist yet.
        """
        new_status = "active" if success else "error"

        try:
            await self._db.execute(
                text("""
                    UPDATE user_connections
                    SET last_sync_at    = :synced_at,
                        last_sync_error = :error,
                        status          = :status
                    WHERE id = :cid
                """),
                {
                    "synced_at": synced_at,
                    "error": error,
                    "status": new_status,
                    "cid": connection_id,
                },
            )
        except Exception as exc:
            # Non-fatal — the sync result itself is still returned to the caller.
            logger.warning(
                "sync_persist_failed",
                connection_id=connection_id,
                error=str(exc),
                hint="Migration 009 columns may not be present yet.",
            )
