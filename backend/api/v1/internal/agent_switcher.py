"""
Internal agent-switcher endpoints.

Covers:
- POST /agent-switcher/scan           — cron-triggered decision engine scan
- POST /agent-switcher/sync-plans     — refresh available-plans cache per zip
- POST /agent-switcher/cleanup-meter-data — drop stale meter_readings partitions

All routes inherit the router-level ``verify_api_key`` dependency from the
parent internal router, so no per-endpoint auth setup is required here.
"""

from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agent-switcher", tags=["internal-agent-switcher"])


# ---------------------------------------------------------------------------
# POST /agent-switcher/scan
# ---------------------------------------------------------------------------


@router.post("/scan")
async def scan_agent_switcher(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Trigger the auto-rate-switcher decision engine for all enrolled users.

    Steps per user:
    1. Query ``user_agent_settings`` for users who are enabled, have a signed
       LOA that has not been revoked.
    2. Build a ``UserContext`` and run ``SwitchDecisionEngine.evaluate()``.
    3. Write the decision to ``switch_audit_log`` (all outcomes).
    4. If ``decision.action == "switch"`` call ``SwitchExecutionService.execute_switch()``.

    Returns a summary dict:
        scanned             — total enrolled users evaluated
        switches_initiated  — users for whom a switch was started
        recommendations_sent — users who received a ``recommend`` decision
        holds               — users whose evaluation returned hold/monitor

    Requires a valid X-API-Key header (enforced by router-level dependency).
    """
    from services.switch_decision_engine import SwitchDecisionEngine, UserContext
    from services.switch_execution_service import SwitchExecutionService

    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    # ------------------------------------------------------------------
    # 1. Load all enrolled users
    # ------------------------------------------------------------------
    try:
        result = await db.execute(
            text("""
                SELECT
                    uas.user_id,
                    uas.enabled,
                    uas.loa_signed_at,
                    uas.loa_revoked_at,
                    uas.savings_threshold_pct,
                    uas.savings_threshold_min,
                    uas.cooldown_days,
                    uas.paused_until,
                    u.subscription_tier
                FROM user_agent_settings uas
                JOIN public.users u ON u.id = uas.user_id
                WHERE uas.enabled = TRUE
                  AND uas.loa_signed_at IS NOT NULL
                  AND uas.loa_revoked_at IS NULL
            """)
        )
        rows = result.mappings().all()
    except Exception as exc:
        logger.error("agent_switcher_scan_load_users_failed", error=str(exc))
        raise HTTPException(
            status_code=500,
            detail="Agent-switcher scan failed: could not load enrolled users.",
        )

    if not rows:
        return {
            "scanned": 0,
            "switches_initiated": 0,
            "recommendations_sent": 0,
            "holds": 0,
        }

    engine = SwitchDecisionEngine(db)
    execution_service = SwitchExecutionService(db)

    scanned = 0
    switches_initiated = 0
    recommendations_sent = 0
    holds = 0

    # ------------------------------------------------------------------
    # 2-4. Evaluate each user
    # ------------------------------------------------------------------
    for row in rows:
        user_id = str(row["user_id"])
        scanned += 1

        try:
            from decimal import Decimal

            ctx = UserContext(
                user_id=user_id,
                tier=row["subscription_tier"] or "free",
                agent_enabled=bool(row["enabled"]),
                loa_signed=row["loa_signed_at"] is not None,
                loa_revoked=row["loa_revoked_at"] is not None,
                paused_until=row["paused_until"],
                savings_threshold_pct=(
                    Decimal(str(row["savings_threshold_pct"]))
                    if row["savings_threshold_pct"] is not None
                    else Decimal("10.0")
                ),
                savings_threshold_min=(
                    Decimal(str(row["savings_threshold_min"]))
                    if row["savings_threshold_min"] is not None
                    else Decimal("10.0")
                ),
                cooldown_days=int(row["cooldown_days"]) if row["cooldown_days"] is not None else 5,
            )

            decision = await engine.evaluate(ctx)

            # 3. Store decision in switch_audit_log
            import uuid

            await db.execute(
                text("""
                    INSERT INTO switch_audit_log
                        (id, user_id, decision, plan_id, plan_name, provider_name,
                         rate_kwh, projected_savings_monthly, projected_savings_annual,
                         confidence, reason, data_source, executed, created_at)
                    VALUES
                        (:id, :user_id, :decision, :plan_id, :plan_name, :provider_name,
                         :rate_kwh, :savings_monthly, :savings_annual,
                         :confidence, :reason, :data_source, FALSE, NOW())
                """),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "decision": decision.action,
                    "plan_id": decision.proposed_plan.plan_id if decision.proposed_plan else None,
                    "plan_name": decision.proposed_plan.plan_name
                    if decision.proposed_plan
                    else None,
                    "provider_name": (
                        decision.proposed_plan.provider_name if decision.proposed_plan else None
                    ),
                    "rate_kwh": (
                        float(decision.proposed_plan.rate_kwh) if decision.proposed_plan else 0.0
                    ),
                    "savings_monthly": float(decision.projected_savings_monthly),
                    "savings_annual": float(decision.projected_savings_annual),
                    "confidence": float(decision.confidence),
                    "reason": decision.reason,
                    "data_source": decision.data_source,
                },
            )
            await db.commit()

            # 4. Act on the decision
            if decision.action == "switch":
                await execution_service.execute_switch(user_id, decision)
                switches_initiated += 1
                logger.info(
                    "agent_switcher_scan_switch_initiated",
                    user_id=user_id,
                    proposed_plan=(
                        decision.proposed_plan.plan_id if decision.proposed_plan else None
                    ),
                )
            elif decision.action == "recommend":
                recommendations_sent += 1
                logger.info(
                    "agent_switcher_scan_recommendation",
                    user_id=user_id,
                    reason=decision.reason,
                )
            else:
                holds += 1
                logger.debug(
                    "agent_switcher_scan_hold",
                    user_id=user_id,
                    action=decision.action,
                    reason=decision.reason,
                )

        except Exception as exc:
            logger.error(
                "agent_switcher_scan_user_error",
                user_id=user_id,
                error=str(exc),
            )
            holds += 1
            # Continue processing remaining users — one bad user must not abort the batch.
            try:
                await db.rollback()
            except Exception:
                pass

    logger.info(
        "agent_switcher_scan_complete",
        scanned=scanned,
        switches_initiated=switches_initiated,
        recommendations_sent=recommendations_sent,
        holds=holds,
    )

    return {
        "scanned": scanned,
        "switches_initiated": switches_initiated,
        "recommendations_sent": recommendations_sent,
        "holds": holds,
    }


# ---------------------------------------------------------------------------
# POST /agent-switcher/sync-plans
# ---------------------------------------------------------------------------


@router.post("/sync-plans")
async def sync_plans(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Refresh the available-plans cache for all zip codes with active enrolled users.

    Steps:
    1. Query distinct zip codes from ``user_agent_settings`` joined with ``users``
       (where ``enabled = TRUE``).
    2. For each zip code call ``EnergyBotService.fetch_plans(zip_code)``.
       ``fetch_plans`` internally upserts results into ``available_plans``.
    3. Tally successes and errors.

    Returns:
        zip_codes_synced — number of zip codes successfully synced
        plans_fetched    — total plans retrieved across all zip codes

    A single zip-code fetch failure is logged but does not abort the batch.
    Requires a valid X-API-Key header (enforced by router-level dependency).
    """
    from services.energybot_service import EnergyBotService

    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    # ------------------------------------------------------------------
    # 1. Distinct zip codes for active enrolled users
    # ------------------------------------------------------------------
    try:
        result = await db.execute(
            text("""
                SELECT DISTINCT uas.zip_code
                FROM user_agent_settings uas
                JOIN public.users u ON u.id = uas.user_id
                WHERE uas.enabled = TRUE
                  AND uas.zip_code IS NOT NULL
                  AND uas.zip_code <> ''
            """)
        )
        rows = result.fetchall()
        zip_codes = [row[0] for row in rows if row[0]]
    except Exception as exc:
        logger.error("agent_switcher_sync_plans_load_zips_failed", error=str(exc))
        raise HTTPException(
            status_code=500,
            detail="Sync-plans failed: could not load zip codes.",
        )

    if not zip_codes:
        return {"zip_codes_synced": 0, "plans_fetched": 0}

    energybot = EnergyBotService(db)
    zip_codes_synced = 0
    plans_fetched = 0

    # ------------------------------------------------------------------
    # 2. Fetch plans per zip code
    # ------------------------------------------------------------------
    for zip_code in zip_codes:
        try:
            plans = await energybot.fetch_plans(zip_code)
            zip_codes_synced += 1
            plans_fetched += len(plans)
            logger.info(
                "agent_switcher_sync_plans_zip_ok",
                zip_code=zip_code,
                plans=len(plans),
            )
        except Exception as exc:
            logger.warning(
                "agent_switcher_sync_plans_zip_failed",
                zip_code=zip_code,
                error=str(exc),
            )
            # Continue with the next zip — partial success is acceptable.

    logger.info(
        "agent_switcher_sync_plans_complete",
        zip_codes_synced=zip_codes_synced,
        plans_fetched=plans_fetched,
    )

    return {
        "zip_codes_synced": zip_codes_synced,
        "plans_fetched": plans_fetched,
    }


# ---------------------------------------------------------------------------
# POST /agent-switcher/cleanup-meter-data
# ---------------------------------------------------------------------------

# Partition naming convention: meter_readings_YYYY_MM (e.g. meter_readings_2024_01)
_PARTITION_PREFIX = "meter_readings_"
_PARTITION_MONTHS_AHEAD = 3
_RETENTION_DAYS = 90


@router.post("/cleanup-meter-data")
async def cleanup_meter_data(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Manage time-based partitions for the ``meter_readings`` table.

    Steps:
    1. Query ``pg_catalog.pg_inherits`` / ``pg_class`` for child tables whose
       names match the ``meter_readings_YYYY_MM`` convention.
    2. Identify partitions older than 90 days based on the name suffix.
    3. DROP old partitions.
    4. CREATE new partitions for the current month plus the next 3 months
       if they do not already exist.
    5. GRANT ownership of new partitions to ``neondb_owner``.

    Returns:
        dropped — list of partition names that were dropped
        created — list of partition names that were created

    Requires a valid X-API-Key header (enforced by router-level dependency).
    """
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    dropped: list[str] = []
    created: list[str] = []

    # ------------------------------------------------------------------
    # 1. Discover existing meter_readings child partitions
    # ------------------------------------------------------------------
    try:
        result = await db.execute(
            text("""
                SELECT c.relname AS partition_name
                FROM pg_catalog.pg_inherits i
                JOIN pg_catalog.pg_class c ON c.oid = i.inhrelid
                JOIN pg_catalog.pg_class p ON p.oid = i.inhparent
                WHERE p.relname = 'meter_readings'
                  AND c.relkind = 'r'
                ORDER BY c.relname
            """)
        )
        partition_rows = result.fetchall()
        existing_partitions = [row[0] for row in partition_rows]
    except Exception as exc:
        logger.warning(
            "cleanup_meter_data_discover_failed",
            error=str(exc),
        )
        existing_partitions = []

    # ------------------------------------------------------------------
    # 2. Identify old partitions (> 90 days)
    # ------------------------------------------------------------------
    cutoff = datetime.now(UTC) - timedelta(days=_RETENTION_DAYS)

    for partition_name in existing_partitions:
        if not partition_name.startswith(_PARTITION_PREFIX):
            continue

        suffix = partition_name[len(_PARTITION_PREFIX) :]  # e.g. "2024_01"
        parts = suffix.split("_")
        if len(parts) != 2:
            continue

        try:
            year, month = int(parts[0]), int(parts[1])
            # Partition covers the whole calendar month; it expires at month-end
            partition_start = datetime(year, month, 1, tzinfo=UTC)
            # If the month started more than 90 days ago, drop it
            if partition_start < cutoff:
                await db.execute(
                    text(f"DROP TABLE IF EXISTS {partition_name}")  # noqa: S608
                )
                await db.commit()
                dropped.append(partition_name)
                logger.info("cleanup_meter_data_dropped", partition=partition_name)
        except (ValueError, Exception) as exc:
            logger.warning(
                "cleanup_meter_data_drop_failed",
                partition=partition_name,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # 4-5. Create future partitions (current month + 3 ahead)
    # ------------------------------------------------------------------
    now = datetime.now(UTC)
    for offset in range(_PARTITION_MONTHS_AHEAD + 1):  # 0, 1, 2, 3
        # Compute target month
        target_month = now.month + offset
        target_year = now.year + (target_month - 1) // 12
        target_month = ((target_month - 1) % 12) + 1

        partition_name = f"{_PARTITION_PREFIX}{target_year:04d}_{target_month:02d}"

        if partition_name in existing_partitions:
            continue  # Already exists — skip

        # Compute partition bounds
        start_date = datetime(target_year, target_month, 1, tzinfo=UTC)
        if target_month == 12:
            end_date = datetime(target_year + 1, 1, 1, tzinfo=UTC)
        else:
            end_date = datetime(target_year, target_month + 1, 1, tzinfo=UTC)

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        try:
            await db.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {partition_name} "
                    f"PARTITION OF meter_readings "
                    f"FOR VALUES FROM ('{start_str}') TO ('{end_str}')"
                )
            )
            await db.execute(text(f"GRANT ALL ON {partition_name} TO neondb_owner"))
            await db.commit()
            created.append(partition_name)
            logger.info(
                "cleanup_meter_data_created",
                partition=partition_name,
                start=start_str,
                end=end_str,
            )
        except Exception as exc:
            logger.warning(
                "cleanup_meter_data_create_failed",
                partition=partition_name,
                error=str(exc),
            )
            try:
                await db.rollback()
            except Exception:
                pass

    logger.info(
        "cleanup_meter_data_complete",
        dropped=dropped,
        created=created,
    )

    return {"dropped": dropped, "created": created}
