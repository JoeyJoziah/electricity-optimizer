"""
Internal email-scan endpoint.

Covers: /scan-emails

Scans all active email-import connections for utility bill emails and
extracts rate data. Runs in parallel (Semaphore(3)) to stay within
email provider rate limits.
"""

import asyncio
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session

logger = structlog.get_logger(__name__)

router = APIRouter()

# Cap email API parallelism — Gmail / Microsoft Graph are strict per-user.
_SCAN_SEMAPHORE_LIMIT = 3


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/scan-emails", tags=["Internal"])
async def scan_all_emails(db: AsyncSession = Depends(get_db_session)):
    """
    Scan all active email-import connections for utility bills and extract
    rate data.

    For each connection:
      1. Decrypt stored OAuth access token (AES-256-GCM via decrypt_field).
      2. Refresh the token when oauth_token_expires_at < NOW() and a
         refresh_token exists.
      3. Call scan_gmail_inbox() or scan_outlook_inbox() to list utility-bill
         candidate emails.
      4. Call extract_rates_from_email() on each candidate to pull rate /
         amount / kWh data from the email body.
      5. Persist extracted rates to connection_extracted_rates (one row per
         email with extracted data).

    All connections run through asyncio.gather() gated by a Semaphore(3) so
    peak concurrency toward external email APIs never exceeds 3.

    Individual connection errors are caught and logged — one failure does not
    abort the batch.

    Protected by the router-level X-API-Key dependency.

    Returns a summary dict:
        status          — "ok"
        connections_scanned — total active email connections processed
        emails_found    — total utility-bill emails discovered
        rates_extracted — rows successfully written to connection_extracted_rates
        errors          — list of {"connection_id": ..., "error": ...} dicts
    """
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    # 1. Fetch all active email-import connections.
    result = await db.execute(text("""
            SELECT
                id,
                user_id,
                email_provider,
                oauth_access_token,
                oauth_refresh_token,
                oauth_token_expires_at
            FROM user_connections
            WHERE connection_type = 'email_import'
              AND status = 'active'
            ORDER BY updated_at ASC
        """))
    connections = result.mappings().fetchall()

    if not connections:
        logger.info("scan_all_emails_no_connections")
        return {
            "status": "ok",
            "connections_scanned": 0,
            "emails_found": 0,
            "rates_extracted": 0,
            "errors": [],
        }

    sem = asyncio.Semaphore(_SCAN_SEMAPHORE_LIMIT)

    async def _scan_one(conn) -> dict:
        """Scan a single connection and return a per-connection result dict."""
        conn_id = str(conn["id"])
        provider = conn["email_provider"] or "gmail"

        log = logger.bind(connection_id=conn_id, provider=provider)

        try:
            from services.email_scanner_service import (
                extract_rates_from_email, scan_gmail_inbox, scan_outlook_inbox)
            from utils.encryption import decrypt_field

            # ----------------------------------------------------------------
            # Decrypt access token — raw BYTEA column (migration 059)
            # ----------------------------------------------------------------
            raw_access = conn["oauth_access_token"]
            if not raw_access:
                log.warning("scan_emails_no_token")
                return {
                    "connection_id": conn_id,
                    "emails_found": 0,
                    "rates_extracted": 0,
                    "skipped": True,
                }

            enc_access = bytes(raw_access)
            access_token = decrypt_field(enc_access)

            # ----------------------------------------------------------------
            # Token refresh when expired
            # ----------------------------------------------------------------
            expires_at = conn["oauth_token_expires_at"]
            if expires_at is not None:
                # Ensure timezone-aware comparison
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                if expires_at < datetime.now(UTC):
                    raw_refresh = conn["oauth_refresh_token"]
                    if not raw_refresh:
                        log.warning("scan_emails_token_expired_no_refresh")
                        return {
                            "connection_id": conn_id,
                            "emails_found": 0,
                            "rates_extracted": 0,
                            "skipped": True,
                        }
                    from services.email_oauth_service import (
                        encrypt_tokens, refresh_gmail_token,
                        refresh_outlook_token)

                    enc_refresh = bytes(raw_refresh)
                    try:
                        if provider == "gmail":
                            new_tokens = await refresh_gmail_token(enc_refresh)
                        else:
                            new_tokens = await refresh_outlook_token(enc_refresh)

                        access_token = new_tokens["access_token"]
                        new_enc_access, new_enc_refresh = encrypt_tokens(
                            access_token,
                            new_tokens.get("refresh_token"),
                        )
                        await db.execute(
                            text("""
                                UPDATE user_connections
                                SET oauth_access_token = :access,
                                    oauth_refresh_token = COALESCE(:refresh, oauth_refresh_token),
                                    oauth_token_expires_at = NOW() + make_interval(secs => :expires),
                                    updated_at = NOW()
                                WHERE id = :cid
                            """),
                            {
                                "cid": conn_id,
                                "access": new_enc_access,
                                "refresh": new_enc_refresh,
                                "expires": new_tokens.get("expires_in", 3600),
                            },
                        )
                        await db.commit()
                        log.info("scan_emails_token_refreshed")
                    except Exception as refresh_exc:
                        log.warning(
                            "scan_emails_token_refresh_failed",
                            error=str(refresh_exc),
                        )
                        return {
                            "connection_id": conn_id,
                            "emails_found": 0,
                            "rates_extracted": 0,
                            "skipped": True,
                        }

            # ----------------------------------------------------------------
            # Scan inbox (behind semaphore)
            # ----------------------------------------------------------------
            async with sem:
                if provider == "gmail":
                    scan_results = await scan_gmail_inbox(access_token)
                else:
                    scan_results = await scan_outlook_inbox(access_token)

            utility_emails = [r for r in scan_results if r.is_utility_bill]
            log.info(
                "scan_emails_inbox_scanned",
                total=len(scan_results),
                utility=len(utility_emails),
            )

            # ----------------------------------------------------------------
            # Extract rates and batch-persist (single COMMIT per connection)
            # ----------------------------------------------------------------
            rate_rows: list[dict] = []
            for email_result in utility_emails:
                try:
                    extracted = await extract_rates_from_email(
                        provider=provider,
                        access_token=access_token,
                        email_id=email_result.email_id,
                    )
                    if not extracted:
                        continue

                    rate_rows.append(
                        {
                            "cid": conn_id,
                            "source": f"email:{email_result.email_id}",
                            "rate": extracted.get("rate_per_kwh"),
                            "date": (
                                email_result.date.date() if email_result.date else None
                            ),
                            "raw": str(extracted),
                        }
                    )
                    log.debug(
                        "scan_emails_rate_extracted",
                        email_id=email_result.email_id,
                        extracted=extracted,
                    )
                except Exception as extract_exc:
                    log.warning(
                        "scan_emails_rate_extract_failed",
                        email_id=email_result.email_id,
                        error=str(extract_exc),
                    )

            # Batch INSERT all extracted rates in one go
            rates_extracted = 0
            if rate_rows:
                try:
                    for row in rate_rows:
                        await db.execute(
                            text("""
                                INSERT INTO connection_extracted_rates
                                    (connection_id, source, rate_per_kwh, effective_date, raw_label)
                                VALUES
                                    (:cid, :source, :rate, :date, :raw)
                                ON CONFLICT DO NOTHING
                            """),
                            row,
                        )
                    await db.commit()
                    rates_extracted = len(rate_rows)
                except Exception as persist_exc:
                    log.warning(
                        "scan_emails_batch_persist_failed",
                        connection_id=conn_id,
                        rows=len(rate_rows),
                        error=str(persist_exc),
                    )
                    await db.rollback()

            return {
                "connection_id": conn_id,
                "emails_found": len(utility_emails),
                "rates_extracted": rates_extracted,
                "skipped": False,
            }

        except Exception as exc:
            log.error("scan_emails_connection_failed", error=str(exc))
            return {
                "connection_id": conn_id,
                "emails_found": 0,
                "rates_extracted": 0,
                "error": "Connection scan failed. See server logs for details.",
            }

    # 2. Run connections sequentially to avoid shared AsyncSession corruption.
    #    The semaphore inside _scan_one still gates external API concurrency.
    results = []
    for conn in connections:
        result = await _scan_one(conn)
        results.append(result)

    # 3. Aggregate summary.
    total_emails = sum(r.get("emails_found", 0) for r in results)
    total_rates = sum(r.get("rates_extracted", 0) for r in results)
    errors = [
        {"connection_id": r["connection_id"], "error": r["error"]}
        for r in results
        if "error" in r
    ]

    logger.info(
        "scan_all_emails_complete",
        connections_scanned=len(connections),
        emails_found=total_emails,
        rates_extracted=total_rates,
        errors=len(errors),
    )

    return {
        "status": "ok",
        "connections_scanned": len(connections),
        "emails_found": total_emails,
        "rates_extracted": total_rates,
        "errors": errors,
    }
