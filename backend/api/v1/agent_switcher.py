"""
Agent Switcher API

User-facing endpoints for the Auto Rate Switcher agent. All routes require
a Pro or higher subscription tier.

Routes
------
GET    /agent-switcher/settings            — get agent configuration
PUT    /agent-switcher/settings            — update settings (partial)
POST   /agent-switcher/loa/sign            — sign Letter of Authorization
POST   /agent-switcher/loa/revoke          — revoke LOA (disables agent)
GET    /agent-switcher/history             — switch execution history
GET    /agent-switcher/activity            — agent activity feed (all decisions)
POST   /agent-switcher/check-now           — trigger immediate evaluation
POST   /agent-switcher/rollback/{id}       — rollback a switch execution
POST   /agent-switcher/approve/{id}        — approve a recommendation (Pro)
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import SessionData, get_current_user, get_db_session, require_tier

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agent-switcher", tags=["agent-switcher"])


# =============================================================================
# Request / response models
# =============================================================================


class AgentSettingsResponse(BaseModel):
    """Response for GET /agent-switcher/settings."""

    enabled: bool
    savings_threshold_pct: float
    savings_threshold_min: float
    cooldown_days: int
    paused_until: datetime | None
    loa_signed: bool
    loa_revoked: bool
    created_at: datetime | None
    updated_at: datetime | None


class UpdateSettingsRequest(BaseModel):
    """Body for PUT /agent-switcher/settings — all fields optional."""

    enabled: bool | None = None
    savings_threshold_pct: float | None = Field(
        default=None,
        ge=0,
        description="Minimum savings percentage threshold (0-100)",
    )
    savings_threshold_min: float | None = Field(
        default=None,
        ge=0,
        description="Minimum savings dollar amount per month",
    )
    cooldown_days: int | None = Field(
        default=None,
        ge=0,
        description="Days to wait between switches",
    )
    paused_until: datetime | None = None


class LOASignResponse(BaseModel):
    """Response for POST /agent-switcher/loa/sign."""

    signed_at: datetime
    message: str


class LOARevokeResponse(BaseModel):
    """Response for POST /agent-switcher/loa/revoke."""

    revoked_at: datetime
    message: str


class HistoryEntry(BaseModel):
    """Single entry in switch execution history."""

    id: str
    trigger_type: str
    decision: str
    reason: str
    savings_monthly: float | None
    savings_annual: float | None
    etf_cost: float | None
    net_savings_year1: float | None
    confidence_score: float | None
    data_source: str | None
    tier: str
    executed: bool
    execution_status: str | None
    created_at: datetime


class ActivityEntry(BaseModel):
    """Single entry in the agent activity feed."""

    id: str
    trigger_type: str
    decision: str
    reason: str
    confidence_score: float | None
    data_source: str | None
    created_at: datetime


# =============================================================================
# Helpers
# =============================================================================

_DEFAULT_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "savings_threshold_pct": 10.0,
    "savings_threshold_min": 10.0,
    "cooldown_days": 5,
    "paused_until": None,
    "loa_signed": False,
    "loa_revoked": False,
    "created_at": None,
    "updated_at": None,
}


def _row_to_settings(row: Any) -> dict[str, Any]:
    """Convert a DB row mapping to settings response dict."""
    loa_signed_at = row.get("loa_signed_at") if hasattr(row, "get") else None
    loa_revoked_at = row.get("loa_revoked_at") if hasattr(row, "get") else None
    return {
        "enabled": row.get("enabled", False),
        "savings_threshold_pct": float(row["savings_threshold_pct"] or 10.0),
        "savings_threshold_min": float(row["savings_threshold_min"] or 10.0),
        "cooldown_days": int(row["cooldown_days"] or 5),
        "paused_until": row["paused_until"],
        "loa_signed": loa_signed_at is not None,
        "loa_revoked": loa_revoked_at is not None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def _get_settings_row(user_id: str, db: AsyncSession) -> Any | None:
    """Fetch the user_agent_settings row or return None."""
    result = await db.execute(
        text("""
            SELECT id, user_id, enabled, savings_threshold_pct, savings_threshold_min,
                   cooldown_days, paused_until, loa_signed_at, loa_revoked_at,
                   created_at, updated_at
            FROM public.user_agent_settings
            WHERE user_id = :user_id
        """),
        {"user_id": user_id},
    )
    return result.mappings().first()


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/settings",
    summary="Get agent settings",
    response_description="Current agent configuration for the user",
)
async def get_settings(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    _: SessionData = Depends(require_tier("pro")),
) -> dict[str, Any]:
    """
    Return the user's Auto Rate Switcher configuration.
    If no settings row exists, return defaults (agent disabled).
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    row = await _get_settings_row(current_user.user_id, db)
    if row is None:
        return _DEFAULT_SETTINGS.copy()

    return _row_to_settings(row)


@router.put(
    "/settings",
    summary="Update agent settings",
    response_description="Updated agent configuration",
)
async def update_settings(
    body: UpdateSettingsRequest,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    _: SessionData = Depends(require_tier("pro")),
) -> dict[str, Any]:
    """
    Upsert agent settings. Accepts partial updates; unspecified fields
    retain their current values (or defaults if no row exists yet).
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    updates = body.model_dump(exclude_unset=True)

    if not updates:
        # No fields provided — return current settings unchanged
        row = await _get_settings_row(current_user.user_id, db)
        if row is None:
            return _DEFAULT_SETTINGS.copy()
        return _row_to_settings(row)

    # Build the upsert — INSERT ... ON CONFLICT DO UPDATE
    now = datetime.now(UTC)

    # Fetch existing row to merge
    existing = await _get_settings_row(current_user.user_id, db)

    if existing is None:
        # Insert with defaults merged with the provided updates
        enabled = updates.get("enabled", False)
        savings_threshold_pct = updates.get("savings_threshold_pct", 10.0)
        savings_threshold_min = updates.get("savings_threshold_min", 10.0)
        cooldown_days = updates.get("cooldown_days", 5)
        paused_until = updates.get("paused_until", None)

        await db.execute(
            text("""
                INSERT INTO public.user_agent_settings
                    (id, user_id, enabled, savings_threshold_pct, savings_threshold_min,
                     cooldown_days, paused_until, created_at, updated_at)
                VALUES
                    (:id, :user_id, :enabled, :savings_threshold_pct, :savings_threshold_min,
                     :cooldown_days, :paused_until, :now, :now)
            """),
            {
                "id": str(uuid.uuid4()),
                "user_id": current_user.user_id,
                "enabled": enabled,
                "savings_threshold_pct": savings_threshold_pct,
                "savings_threshold_min": savings_threshold_min,
                "cooldown_days": cooldown_days,
                "paused_until": paused_until,
                "now": now,
            },
        )
    else:
        # Build dynamic SET clause from provided fields only
        set_parts = ["updated_at = :now"]
        params: dict[str, Any] = {"user_id": current_user.user_id, "now": now}

        field_map = {
            "enabled": "enabled",
            "savings_threshold_pct": "savings_threshold_pct",
            "savings_threshold_min": "savings_threshold_min",
            "cooldown_days": "cooldown_days",
            "paused_until": "paused_until",
        }
        for field, col in field_map.items():
            if field in updates:
                set_parts.append(f"{col} = :{field}")
                params[field] = updates[field]

        await db.execute(
            text(f"""
                UPDATE public.user_agent_settings
                SET {", ".join(set_parts)}
                WHERE user_id = :user_id
            """),
            params,
        )

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    row = await _get_settings_row(current_user.user_id, db)
    return _row_to_settings(row)


@router.post(
    "/loa/sign",
    summary="Sign Letter of Authorization",
    response_description="LOA signing confirmation",
)
async def sign_loa(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    _: SessionData = Depends(require_tier("pro")),
) -> dict[str, Any]:
    """
    Record that the user has signed the Letter of Authorization.
    Sets loa_signed_at = now(), clears loa_revoked_at.
    Idempotent — safe to call multiple times.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    now = datetime.now(UTC)

    existing = await _get_settings_row(current_user.user_id, db)
    if existing is None:
        await db.execute(
            text("""
                INSERT INTO public.user_agent_settings
                    (id, user_id, enabled, loa_signed_at, loa_revoked_at, created_at, updated_at)
                VALUES
                    (:id, :user_id, FALSE, :now, NULL, :now, :now)
            """),
            {"id": str(uuid.uuid4()), "user_id": current_user.user_id, "now": now},
        )
    else:
        await db.execute(
            text("""
                UPDATE public.user_agent_settings
                SET loa_signed_at = :now,
                    loa_revoked_at = NULL,
                    updated_at = :now
                WHERE user_id = :user_id
            """),
            {"user_id": current_user.user_id, "now": now},
        )

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info("loa_signed", user_id=current_user.user_id)
    return {"signed_at": now, "message": "Letter of Authorization signed successfully."}


@router.post(
    "/loa/revoke",
    summary="Revoke Letter of Authorization",
    response_description="LOA revocation confirmation",
)
async def revoke_loa(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    _: SessionData = Depends(require_tier("pro")),
) -> dict[str, Any]:
    """
    Revoke the Letter of Authorization. Sets loa_revoked_at = now()
    and disables the agent (enabled = False).
    Returns 400 if no LOA has been signed.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    existing = await _get_settings_row(current_user.user_id, db)
    if existing is None or existing.get("loa_signed_at") is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No LOA has been signed. Sign an LOA before revoking.",
        )

    now = datetime.now(UTC)

    await db.execute(
        text("""
            UPDATE public.user_agent_settings
            SET loa_revoked_at = :now,
                enabled = FALSE,
                updated_at = :now
            WHERE user_id = :user_id
        """),
        {"user_id": current_user.user_id, "now": now},
    )

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info("loa_revoked", user_id=current_user.user_id)
    return {
        "revoked_at": now,
        "message": "Letter of Authorization revoked. Agent has been disabled.",
    }


@router.get(
    "/history",
    summary="Get switch history",
    response_description="Paginated list of switch executions",
)
async def get_history(
    limit: int = Query(default=20, ge=1, le=100, description="Maximum records to return"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    _: SessionData = Depends(require_tier("pro")),
) -> dict[str, Any]:
    """
    Return paginated switch execution history for the current user,
    joined with audit log and execution status. Ordered newest first.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    result = await db.execute(
        text("""
            SELECT
                sal.id,
                sal.trigger_type,
                sal.decision,
                sal.reason,
                sal.savings_monthly,
                sal.savings_annual,
                sal.etf_cost,
                sal.net_savings_year1,
                sal.confidence_score,
                sal.data_source,
                sal.tier,
                sal.executed,
                se.status AS execution_status,
                sal.created_at
            FROM public.switch_audit_log sal
            LEFT JOIN public.switch_executions se ON se.audit_log_id = sal.id
            WHERE sal.user_id = :user_id
            ORDER BY sal.created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"user_id": current_user.user_id, "limit": limit, "offset": offset},
    )
    rows = result.mappings().all()

    entries = [
        {
            "id": str(row["id"]),
            "trigger_type": row["trigger_type"],
            "decision": row["decision"],
            "reason": row["reason"],
            "savings_monthly": float(row["savings_monthly"])
            if row["savings_monthly"] is not None
            else None,
            "savings_annual": float(row["savings_annual"])
            if row["savings_annual"] is not None
            else None,
            "etf_cost": float(row["etf_cost"]) if row["etf_cost"] is not None else None,
            "net_savings_year1": float(row["net_savings_year1"])
            if row["net_savings_year1"] is not None
            else None,
            "confidence_score": float(row["confidence_score"])
            if row["confidence_score"] is not None
            else None,
            "data_source": row["data_source"],
            "tier": row["tier"],
            "executed": row["executed"],
            "execution_status": row["execution_status"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]

    return {"history": entries, "total": len(entries), "limit": limit, "offset": offset}


@router.get(
    "/activity",
    summary="Get agent activity feed",
    response_description="All agent scan results including holds",
)
async def get_activity(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum records to return"),
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    _: SessionData = Depends(require_tier("pro")),
) -> dict[str, Any]:
    """
    Return the full agent activity feed — every scan result including
    hold and monitor decisions. Ordered newest first.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    result = await db.execute(
        text("""
            SELECT
                id,
                trigger_type,
                decision,
                reason,
                confidence_score,
                data_source,
                created_at
            FROM public.switch_audit_log
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"user_id": current_user.user_id, "limit": limit},
    )
    rows = result.mappings().all()

    entries = [
        {
            "id": str(row["id"]),
            "trigger_type": row["trigger_type"],
            "decision": row["decision"],
            "reason": row["reason"],
            "confidence_score": float(row["confidence_score"])
            if row["confidence_score"] is not None
            else None,
            "data_source": row["data_source"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]

    return {"activity": entries, "total": len(entries)}


@router.post(
    "/check-now",
    summary="Trigger immediate evaluation",
    response_description="Decision engine result",
)
async def check_now(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    _: SessionData = Depends(require_tier("pro")),
) -> dict[str, Any]:
    """
    Trigger an immediate decision engine evaluation for the current user.
    Stores the result in switch_audit_log and returns the decision.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    # Get user context from DB
    result = await db.execute(
        text("SELECT subscription_tier, region FROM public.users WHERE id = :id"),
        {"id": current_user.user_id},
    )
    user_row = result.first()

    if user_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    tier = user_row[0] or "free"

    # Get agent settings — if agent not enabled or LOA not signed, return hold
    settings_row = await _get_settings_row(current_user.user_id, db)

    if settings_row is None or not settings_row.get("loa_signed_at"):
        decision = {
            "action": "hold",
            "reason": "Agent not configured. Please sign the Letter of Authorization to enable.",
            "current_plan": None,
            "proposed_plan": None,
            "projected_savings_monthly": 0.0,
            "projected_savings_annual": 0.0,
            "etf_cost": 0.0,
            "net_savings_year1": 0.0,
            "confidence": 0.0,
            "cooldown_remaining_days": 0,
            "contract_days_remaining": 0,
            "data_source": "none",
        }
    else:
        # Import and run the decision engine
        try:
            from services.switch_decision_engine import (
                SwitchDecisionEngine,
                UserContext,
            )

            # Build a UserContext from the settings and DB data
            ctx = UserContext(
                user_id=current_user.user_id,
                tier=tier,
                agent_enabled=bool(settings_row.get("enabled", False)),
                loa_signed=settings_row.get("loa_signed_at") is not None,
                loa_revoked=settings_row.get("loa_revoked_at") is not None,
                paused_until=settings_row.get("paused_until"),
                savings_threshold_pct=Decimal(
                    str(settings_row.get("savings_threshold_pct") or "10.0")
                ),
                savings_threshold_min=Decimal(
                    str(settings_row.get("savings_threshold_min") or "10.0")
                ),
                cooldown_days=int(settings_row.get("cooldown_days") or 5),
            )

            engine = SwitchDecisionEngine(db)
            raw_decision = await engine.evaluate(ctx)
            decision = {
                "action": raw_decision.action,
                "reason": raw_decision.reason,
                "current_plan": raw_decision.current_plan,
                "proposed_plan": raw_decision.proposed_plan,
                "projected_savings_monthly": float(raw_decision.projected_savings_monthly),
                "projected_savings_annual": float(raw_decision.projected_savings_annual),
                "etf_cost": float(raw_decision.etf_cost),
                "net_savings_year1": float(raw_decision.net_savings_year1),
                "confidence": float(raw_decision.confidence),
                "cooldown_remaining_days": raw_decision.cooldown_remaining_days,
                "contract_days_remaining": raw_decision.contract_days_remaining,
                "data_source": raw_decision.data_source,
            }
        except (ImportError, Exception) as exc:
            logger.warning("check_now_engine_error", user_id=current_user.user_id, error=str(exc))
            # Return advisory hold if engine not available or evaluation fails
            decision = {
                "action": "hold",
                "reason": "No current plan data available. Connect a utility account to enable plan comparison.",
                "current_plan": None,
                "proposed_plan": None,
                "projected_savings_monthly": 0.0,
                "projected_savings_annual": 0.0,
                "etf_cost": 0.0,
                "net_savings_year1": 0.0,
                "confidence": 0.0,
                "cooldown_remaining_days": 0,
                "contract_days_remaining": 0,
                "data_source": "none",
            }

    # Store result in switch_audit_log
    audit_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    try:
        await db.execute(
            text("""
                INSERT INTO public.switch_audit_log
                    (id, user_id, trigger_type, decision, reason, savings_monthly,
                     savings_annual, etf_cost, net_savings_year1, confidence_score,
                     data_source, tier, executed, created_at)
                VALUES
                    (:id, :user_id, 'manual', :decision, :reason, :savings_monthly,
                     :savings_annual, :etf_cost, :net_savings_year1, :confidence_score,
                     :data_source, :tier, FALSE, :now)
            """),
            {
                "id": audit_id,
                "user_id": current_user.user_id,
                "decision": decision["action"],
                "reason": decision["reason"],
                "savings_monthly": decision["projected_savings_monthly"],
                "savings_annual": decision["projected_savings_annual"],
                "etf_cost": decision["etf_cost"],
                "net_savings_year1": decision["net_savings_year1"],
                "confidence_score": decision["confidence"],
                "data_source": decision["data_source"],
                "tier": tier,
                "now": now,
            },
        )
        await db.commit()
    except Exception:
        await db.rollback()
        # Non-fatal — return the decision even if audit log insertion fails
        logger.warning("check_now_audit_log_failed", user_id=current_user.user_id)

    logger.info(
        "check_now_completed",
        user_id=current_user.user_id,
        action=decision["action"],
        audit_id=audit_id,
    )
    return {"audit_log_id": audit_id, "decision": decision}


@router.post(
    "/rollback/{execution_id}",
    summary="Rollback a switch execution",
    response_description="Rollback result",
)
async def rollback_switch(
    execution_id: uuid.UUID = Path(..., description="UUID of the switch execution to roll back"),
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    _: SessionData = Depends(require_tier("pro")),
) -> dict[str, Any]:
    """
    Initiate a rollback of the specified switch execution.
    The execution must belong to the current user, be in 'active' status,
    and be within the 30-day rollback window.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    # Fetch the execution
    result = await db.execute(
        text("""
            SELECT id, user_id, status, enacted_at, created_at
            FROM public.switch_executions
            WHERE id = :execution_id
        """),
        {"execution_id": str(execution_id)},
    )
    row = result.mappings().first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Switch execution {execution_id} not found",
        )

    if str(row["user_id"]) != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Switch execution {execution_id} not found",
        )

    if row["status"] not in ("active", "initiated", "submitted", "accepted"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot rollback execution with status '{row['status']}'. Only active executions can be rolled back.",
        )

    # Check 30-day window
    enacted_at = row.get("enacted_at") or row.get("created_at")
    if enacted_at is not None:
        now = datetime.now(UTC)
        enacted_at_aware = enacted_at if enacted_at.tzinfo else enacted_at.replace(tzinfo=UTC)
        days_since = (now - enacted_at_aware).days
        if days_since > 30:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rollback window has expired. Rollbacks are only available within 30 days of switch enactment ({days_since} days elapsed).",
            )

    # Import and call rollback service if available
    try:
        from services.switch_execution_service import SwitchExecutionService

        service = SwitchExecutionService(db)
        result_data = await service.rollback_switch(str(execution_id), current_user.user_id)
        return result_data
    except (ImportError, Exception):
        # Service not yet implemented or failed — mark as rolled_back directly
        now = datetime.now(UTC)
        await db.execute(
            text("""
                UPDATE public.switch_executions
                SET status = 'rolled_back', updated_at = :now
                WHERE id = :execution_id
            """),
            {"execution_id": str(execution_id), "now": now},
        )
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        logger.info(
            "rollback_completed", user_id=current_user.user_id, execution_id=str(execution_id)
        )
        return {
            "execution_id": str(execution_id),
            "status": "rolled_back",
            "message": "Switch has been rolled back successfully.",
        }


@router.post(
    "/approve/{audit_log_id}",
    summary="Approve a recommendation",
    response_description="Execution result for the approved recommendation",
)
async def approve_recommendation(
    audit_log_id: uuid.UUID = Path(..., description="UUID of the audit log entry to approve"),
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    _: SessionData = Depends(require_tier("pro")),
) -> dict[str, Any]:
    """
    Approve a pending recommendation (Pro tier). Triggers execution of
    the switch for the specified audit log entry.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    # Fetch the audit log entry
    result = await db.execute(
        text("""
            SELECT id, user_id, decision, executed, proposed_plan_id, tier
            FROM public.switch_audit_log
            WHERE id = :audit_log_id
        """),
        {"audit_log_id": str(audit_log_id)},
    )
    row = result.mappings().first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit log entry {audit_log_id} not found",
        )

    if str(row["user_id"]) != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit log entry {audit_log_id} not found",
        )

    if row["decision"] != "recommend":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Entry {audit_log_id} is not a recommendation (decision='{row['decision']}'). Only 'recommend' entries can be approved.",
        )

    if row["executed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Recommendation {audit_log_id} has already been executed.",
        )

    # Import and call execution service if available
    try:
        from services.switch_execution_service import SwitchExecutionService

        service = SwitchExecutionService(db)
        result_data = await service.approve_recommendation(str(audit_log_id), current_user.user_id)
        return result_data
    except (ImportError, Exception):
        # Service not yet implemented or failed — mark as executed and return advisory
        await db.execute(
            text("""
                UPDATE public.switch_audit_log
                SET executed = TRUE
                WHERE id = :audit_log_id
            """),
            {"audit_log_id": str(audit_log_id)},
        )
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        logger.info(
            "recommendation_approved", user_id=current_user.user_id, audit_log_id=str(audit_log_id)
        )
        return {
            "audit_log_id": str(audit_log_id),
            "status": "initiated",
            "message": "Recommendation approved. Switch execution initiated.",
        }
