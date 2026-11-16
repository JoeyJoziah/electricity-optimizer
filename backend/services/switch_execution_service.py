"""
Switch Execution Service

Orchestrates the full plan-switch lifecycle from initiation through rollback.

State machine:
    initiating → initiated → submitted → accepted → active
    (failed or rolled_back can occur from any pre-terminal state)

Tables:
    switch_executions  — one row per user/plan/UTC day (deterministic unique
                         idempotency_key; a repeat attempt returns the same row,
                         except that a 'failed' row is reset and re-run)
    switch_audit_log   — decision snapshot written before execution begins

The service delegates all provider interactions to the SwitchExecutor protocol.
The product is advisory-only: the only executor records a recommendation, and
such executions end in the terminal ``advisory_only`` status — never
``initiated``/``submitted``, and never counted as pending.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from lib.tracing import traced
from services.switch_executor import AdvisoryOnlyFallback, get_executor

logger = structlog.get_logger(__name__)

# Users may roll back a switch within 30 days of enactment.
ROLLBACK_WINDOW_DAYS = 30

# Statuses considered "in-flight" for check_pending_switches.
PENDING_STATUSES = ("initiating", "initiated", "submitted", "accepted")

# Terminal status for an execution where only a recommendation was recorded.
ADVISORY_STATUS = "advisory_only"

# Statuses that mean the attempt failed before anything was enrolled. A
# same-day retry reuses such a row instead of returning it forever.
# ('rolled_back' is not one: that is a completed switch the user undid.)
RETRYABLE_FAILURE_STATUSES = ("failed",)

# Statuses that mean a real enrollment was started with a provider.
REAL_SWITCH_STATUSES = ("initiated", "submitted", "accepted", "active")

ADVISORY_MESSAGE = (
    "Recommendation recorded. RateShift is advisory-only and has not switched "
    "your plan; contact the supplier to enroll."
)

# Namespace for deterministic idempotency keys (switch_executions.idempotency_key is a UUID).
_IDEMPOTENCY_NAMESPACE = uuid.UUID("6f1d3a52-8c0e-4b7a-9d55-2f6c1e0a7b91")


def build_idempotency_key(user_id: str, plan_id: str, utc_date: date | None = None) -> str:
    """Deterministic idempotency key for one user, plan and UTC day.

    ``uuid5`` over ``"{user_id}:{plan_id}:{utc_date}"`` — the column is a UUID,
    so the stable string is hashed rather than stored verbatim.
    """
    day = utc_date or datetime.now(UTC).date()
    return str(uuid.uuid5(_IDEMPOTENCY_NAMESPACE, f"{user_id}:{plan_id}:{day.isoformat()}"))


class SwitchExecutionService:
    """Orchestrate plan-switch execution and lifecycle management.

    Args:
        db: An async SQLAlchemy session scoped to the current request.

    Usage:
        svc = SwitchExecutionService(db)
        result = await svc.execute_switch(user_id, decision, state_code="TX")
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    async def execute_switch(
        self,
        user_id: str,
        decision: object,
        state_code: str = "TX",
        *,
        audit_log_id: str | None = None,
        tier: str = "unknown",
        trigger_type: str = "manual",
    ) -> dict:
        """Record a plan switch for a user (advisory-only today).

        Steps:
        1. Derive the deterministic idempotency key (user, plan, UTC date).
        2. If an execution with that key exists, return it unchanged (no-op)
           — unless it failed: then the same row is reset to ``initiating``
           and steps 5-6 run again (steps 3-4 are skipped).
        3. Write a decision snapshot to ``switch_audit_log`` unless the caller
           already has one (``audit_log_id``).
        4. Insert the ``switch_executions`` row (``ON CONFLICT DO NOTHING``).
        5. Verify plan availability and call the executor.
        6. Set the final status: ``advisory_only`` when the executor only
           recorded a recommendation, ``initiated`` for a real enrollment.

        On an executor error the execution row is marked 'failed' and the
        exception is re-raised.

        Args:
            user_id:      UUID string of the user.
            decision:     A ``SwitchDecision`` instance from the decision engine.
            state_code:   Two-letter US state code used to select the executor.
            audit_log_id: Existing ``switch_audit_log`` row for this decision.
                          When None a snapshot row is written.
            tier:         User tier, stored on the snapshot row.
            trigger_type: Trigger stored on the snapshot row.

        Returns:
            Dict with keys ``execution_id``, ``status``, ``enrollment_id``,
            ``executed`` (True only when a real enrollment was started),
            ``idempotent_replay`` and, in advisory mode, ``message``.

        Raises:
            RuntimeError: When the plan is not available for enrollment.
            Exception:    Any exception raised by the executor is re-raised
                          after the execution row is marked 'failed'.
        """
        async with traced(
            "switch_execution.execute_switch",
            attributes={
                "switch.user_id": user_id,
                "switch.state_code": state_code,
            },
        ):
            proposed_plan = getattr(decision, "proposed_plan", None)
            plan_id = proposed_plan.plan_id if proposed_plan else ""

            # Step 1-2 — deterministic key; a repeat attempt is a no-op.
            idempotency_key = build_idempotency_key(user_id, plan_id)
            existing = await self._get_execution_by_key(idempotency_key)
            retrying = False
            if existing is not None:
                if existing["status"] in RETRYABLE_FAILURE_STATUSES:
                    retrying = await self._claim_failed_execution(existing["execution_id"])
                    if not retrying:
                        # A concurrent retry claimed the row first: report its state.
                        existing = await self._get_execution_by_key(idempotency_key) or existing
                if not retrying:
                    logger.info(
                        "switch_execution.idempotent_replay",
                        user_id=user_id,
                        execution_id=existing["execution_id"],
                        status=existing["status"],
                    )
                    return existing
                logger.info(
                    "switch_execution.retry_after_failure",
                    user_id=user_id,
                    execution_id=existing["execution_id"],
                )

            region = f"us_{state_code.lower()}"
            executor = get_executor(region)
            advisory = isinstance(executor, AdvisoryOnlyFallback)
            executor_type = str(getattr(executor, "provider", "unknown"))
            execution_id = existing["execution_id"] if retrying else str(uuid.uuid4())

            if not retrying:
                # Step 3-4 — snapshot + execution row (a failed row being
                # retried already has both).
                raced = await self._insert_execution(
                    execution_id=execution_id,
                    user_id=user_id,
                    decision=decision,
                    audit_log_id=audit_log_id,
                    tier=tier,
                    trigger_type=trigger_type,
                    idempotency_key=idempotency_key,
                    executor_type=executor_type,
                )
                if raced is not None:
                    return raced

            # Step 5-6 — executor interaction
            enrollment_id = None
            final_status = "initiated"

            try:
                available = await executor.check_plan_available(plan_id)
                if not available:
                    raise RuntimeError(f"Plan {plan_id} is not available for enrollment.")

                from services.switch_executor import EnrollmentRequest

                request = EnrollmentRequest(
                    plan_id=plan_id,
                    user_id=user_id,
                    user_name="",
                    service_address="",
                    zip_code="",
                    utility_account_number="",
                    idempotency_key=idempotency_key,
                )
                result = await executor.execute_enrollment(request)
                enrollment_id = result.enrollment_id

                # Nothing was enrolled unless the executor says so. An advisory
                # record is terminal: it is never reported as initiated,
                # submitted or pending.
                advisory = advisory or result.status == ADVISORY_STATUS
                final_status = ADVISORY_STATUS if advisory else "initiated"

                await self._db.execute(
                    text("""
                        UPDATE switch_executions
                        SET status = :status,
                            enrollment_id = :enrollment_id,
                            updated_at = NOW()
                        WHERE id = :id
                    """),
                    {
                        "status": final_status,
                        "enrollment_id": enrollment_id,
                        "id": execution_id,
                    },
                )
                await self._db.commit()

                logger.info(
                    "switch_execution.recommendation_recorded"
                    if advisory
                    else "switch_execution.initiated",
                    user_id=user_id,
                    execution_id=execution_id,
                    enrollment_id=enrollment_id,
                    status=final_status,
                    plan_id=plan_id,
                )

            except Exception as exc:
                logger.error(
                    "switch_execution.failed",
                    user_id=user_id,
                    execution_id=execution_id,
                    error=str(exc),
                )
                try:
                    await self._db.rollback()
                    await self._db.execute(
                        text("""
                            UPDATE switch_executions
                            SET status = 'failed',
                                failure_reason = :reason,
                                updated_at = NOW()
                            WHERE id = :id
                        """),
                        {"reason": str(exc), "id": execution_id},
                    )
                    await self._db.commit()
                except Exception as update_exc:
                    logger.error(
                        "switch_execution.status_update_failed",
                        execution_id=execution_id,
                        error=str(update_exc),
                    )
                raise

            response = {
                "execution_id": execution_id,
                "status": final_status,
                "enrollment_id": enrollment_id,
                "executed": not advisory,
                "idempotent_replay": False,
            }
            if advisory:
                response["message"] = ADVISORY_MESSAGE
            return response

    async def _insert_execution(
        self,
        *,
        execution_id: str,
        user_id: str,
        decision: object,
        audit_log_id: str | None,
        tier: str,
        trigger_type: str,
        idempotency_key: str,
        executor_type: str,
    ) -> dict | None:
        """Steps 3-4 of ``execute_switch``: audit snapshot and execution row.

        Returns None when the row was inserted and committed, or the existing
        execution summary when a concurrent attempt won the insert race.
        """
        # Step 3 — audit log snapshot (only when the caller has none)
        if audit_log_id is None:
            audit_log_id = str(uuid.uuid4())
            await self._db.execute(
                text("""
                    INSERT INTO switch_audit_log
                        (id, user_id, trigger_type, decision, reason,
                         savings_monthly, savings_annual, etf_cost,
                         net_savings_year1, confidence_score, data_source,
                         tier, executed, created_at)
                    VALUES
                        (:id, :user_id, :trigger_type, :decision, :reason,
                         :savings_monthly, :savings_annual, :etf_cost,
                         :net_savings_year1, :confidence_score, :data_source,
                         :tier, FALSE, NOW())
                """),
                {
                    "id": audit_log_id,
                    "user_id": user_id,
                    "trigger_type": trigger_type,
                    "decision": getattr(decision, "action", ""),
                    "reason": getattr(decision, "reason", ""),
                    "savings_monthly": float(
                        getattr(decision, "projected_savings_monthly", Decimal("0"))
                    ),
                    "savings_annual": float(
                        getattr(decision, "projected_savings_annual", Decimal("0"))
                    ),
                    "etf_cost": float(getattr(decision, "etf_cost", Decimal("0"))),
                    "net_savings_year1": float(
                        getattr(decision, "net_savings_year1", Decimal("0"))
                    ),
                    "confidence_score": float(getattr(decision, "confidence", Decimal("0"))),
                    "data_source": getattr(decision, "data_source", "unknown"),
                    "tier": tier,
                },
            )

        # Step 4 — execution row; the unique idempotency_key (migration 066)
        # makes a concurrent duplicate a no-op.
        insert_result = await self._db.execute(
            text("""
                INSERT INTO switch_executions
                    (id, user_id, audit_log_id, idempotency_key, executor_type,
                     status, initiated_at, created_at, updated_at)
                VALUES
                    (:id, :user_id, :audit_log_id, :idempotency_key, :executor_type,
                     'initiating', NOW(), NOW(), NOW())
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING id
            """),
            {
                "id": execution_id,
                "user_id": user_id,
                "audit_log_id": audit_log_id,
                "idempotency_key": idempotency_key,
                "executor_type": executor_type,
            },
        )
        if insert_result.first() is None:
            # Lost a race with a concurrent attempt: discard our snapshot
            # and return the row that won.
            await self._db.rollback()
            existing = await self._get_execution_by_key(idempotency_key)
            if existing is not None:
                return existing
            raise RuntimeError("Switch execution insert conflicted but no existing row found.")

        try:
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        return None

    async def _claim_failed_execution(self, execution_id: str) -> bool:
        """Atomically reset a failed execution to ``initiating`` for a retry.

        The ``status`` guard makes concurrent retries safe: only one caller
        gets the row back, the others see no row and replay instead.
        """
        result = await self._db.execute(
            text("""
                UPDATE switch_executions
                SET status = 'initiating',
                    failure_reason = NULL,
                    enrollment_id = NULL,
                    initiated_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
                  AND status = 'failed'
                RETURNING id
            """),
            {"id": execution_id},
        )
        claimed = result.first() is not None
        try:
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        return claimed

    async def _get_execution_by_key(self, idempotency_key: str) -> dict | None:
        """Return the execution summary for an idempotency key, or None."""
        result = await self._db.execute(
            text("""
                SELECT id, status, enrollment_id
                FROM switch_executions
                WHERE idempotency_key = :idempotency_key
            """),
            {"idempotency_key": idempotency_key},
        )
        row = result.mappings().first()
        if row is None:
            return None
        advisory = row["status"] == ADVISORY_STATUS
        response = {
            "execution_id": str(row["id"]),
            "status": row["status"],
            "enrollment_id": row["enrollment_id"],
            "executed": row["status"] in REAL_SWITCH_STATUSES,
            "idempotent_replay": True,
        }
        if advisory:
            response["message"] = ADVISORY_MESSAGE
        return response

    async def check_pending_switches(self, user_id: str) -> list[dict]:
        """Poll all in-flight switches for a user and refresh their status.

        Queries ``switch_executions`` for rows with a pending status and
        calls ``check_enrollment_status`` for each that has an ``enrollment_id``.
        Updates the DB row if the provider reports a new terminal status.

        Args:
            user_id: UUID string of the user.

        Returns:
            List of execution dicts (id, status, enrollment_id, …).
        """
        async with traced(
            "switch_execution.check_pending",
            attributes={"switch.user_id": user_id},
        ):
            result = await self._db.execute(
                text("""
                    SELECT id, status, enrollment_id, executor_type,
                           created_at, updated_at
                    FROM switch_executions
                    WHERE user_id = :user_id
                      AND status = ANY(:statuses)
                    ORDER BY created_at DESC
                """),
                {
                    "user_id": user_id,
                    "statuses": list(PENDING_STATUSES),
                },
            )
            rows = result.mappings().all()
            executions = [dict(row) for row in rows]

            updated = []
            for execution in executions:
                enrollment_id = execution.get("enrollment_id")
                if not enrollment_id:
                    updated.append(execution)
                    continue

                # Attempt status refresh from executor
                try:
                    executor = get_executor("us_tx")  # default region for status check
                    status_result = await executor.check_enrollment_status(enrollment_id)
                    new_status = status_result.status

                    if new_status != execution["status"]:
                        await self._db.execute(
                            text("""
                                UPDATE switch_executions
                                SET status = :status,
                                    updated_at = NOW()
                                WHERE id = :id
                            """),
                            {"status": new_status, "id": str(execution["id"])},
                        )
                        await self._db.commit()
                        execution = dict(execution)
                        execution["status"] = new_status

                except Exception as exc:
                    logger.warning(
                        "switch_execution.status_check_failed",
                        enrollment_id=enrollment_id,
                        execution_id=str(execution["id"]),
                        error=str(exc),
                    )

                updated.append(execution)

            return updated

    async def rollback_switch(self, execution_id: str, user_id: str) -> dict:
        """Roll back an active switch within the 30-day window.

        Args:
            execution_id: UUID of the execution row.
            user_id:      UUID of the user (ownership verification).

        Returns:
            Dict with keys: ``status``, ``message``.

        Raises:
            ValueError: When the execution is not found, belongs to a different
                        user, is not in 'active' status, or the 30-day window
                        has expired.
        """
        async with traced(
            "switch_execution.rollback",
            attributes={"switch.execution_id": execution_id, "switch.user_id": user_id},
        ):
            # Step 1 — load execution
            result = await self._db.execute(
                text("""
                    SELECT id, user_id, status, enrollment_id, enacted_at
                    FROM switch_executions
                    WHERE id = :id
                """),
                {"id": execution_id},
            )
            row = result.mappings().first()

            if not row:
                raise ValueError(f"Execution {execution_id} not found.")

            if str(row["user_id"]) != user_id:
                raise ValueError(f"Execution {execution_id} does not belong to user {user_id}.")

            if row["status"] != "active":
                raise ValueError(
                    f"Cannot roll back execution with status '{row['status']}'. "
                    "Only 'active' executions may be rolled back."
                )

            enacted_at = row["enacted_at"]
            if enacted_at is not None:
                if enacted_at.tzinfo is None:
                    enacted_at = enacted_at.replace(tzinfo=UTC)
                window_end = enacted_at + timedelta(days=ROLLBACK_WINDOW_DAYS)
                if datetime.now(UTC) > window_end:
                    raise ValueError(
                        f"Rollback window expired. Switch was enacted more than "
                        f"{ROLLBACK_WINDOW_DAYS} days ago."
                    )

            enrollment_id = row["enrollment_id"]

            # Step 4 — attempt executor cancellation
            if enrollment_id:
                try:
                    executor = get_executor("us_tx")
                    await executor.cancel_enrollment(enrollment_id)
                except Exception as exc:
                    logger.warning(
                        "switch_execution.cancel_failed",
                        execution_id=execution_id,
                        enrollment_id=enrollment_id,
                        error=str(exc),
                    )
                    # Proceed with DB update regardless — still mark rolled back

            # Step 5 — update status
            await self._db.execute(
                text("""
                    UPDATE switch_executions
                    SET status = 'rolled_back',
                        rolled_back_from = :rolled_back_from,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {"rolled_back_from": execution_id, "id": execution_id},
            )
            await self._db.commit()

            logger.info(
                "switch_execution.rolled_back",
                execution_id=execution_id,
                user_id=user_id,
                enrollment_id=enrollment_id,
            )

            return {
                "status": "rolled_back",
                "message": "Switch successfully rolled back.",
            }

    async def approve_recommendation(self, audit_log_id: str, user_id: str) -> dict:
        """Approve a pending recommendation.

        Runs the recommendation through the executor. In advisory-only mode
        this records the user's acknowledgement (status ``advisory_only``) and
        does NOT mark the audit log as executed — nothing was enrolled.

        Args:
            audit_log_id: UUID of the ``switch_audit_log`` row.
            user_id:      UUID of the user (ownership verification).

        Returns:
            Execution result dict (from ``execute_switch``).

        Raises:
            ValueError: When the audit log is not found, belongs to a different
                        user, is not a 'recommend' decision, or is already
                        executed.
        """
        async with traced(
            "switch_execution.approve_recommendation",
            attributes={
                "switch.audit_log_id": audit_log_id,
                "switch.user_id": user_id,
            },
        ):
            # Step 1 — load audit log
            result = await self._db.execute(
                text("""
                    SELECT id, user_id, decision, reason, proposed_plan_id,
                           savings_monthly, savings_annual, etf_cost,
                           net_savings_year1, confidence_score, data_source,
                           tier, executed
                    FROM switch_audit_log
                    WHERE id = :id
                """),
                {"id": audit_log_id},
            )
            row = result.mappings().first()

            if not row:
                raise ValueError(f"Audit log {audit_log_id} not found.")

            if str(row["user_id"]) != user_id:
                raise ValueError(f"Audit log {audit_log_id} does not belong to user {user_id}.")

            if row["decision"] != "recommend":
                raise ValueError(
                    f"Audit log {audit_log_id} has decision '{row['decision']}', "
                    "not 'recommend'. Only recommendations may be approved."
                )

            if row["executed"]:
                raise ValueError(f"Audit log {audit_log_id} has already been executed.")

            # Step 2 — build a minimal SwitchDecision-compatible object from the
            # log. The audit log stores no plan columns (the proposed plan is
            # described in ``reason``), so the recommendation itself identifies
            # the plan for idempotency.
            from services.switch_decision_engine import PlanDetails, SwitchDecision

            plan = PlanDetails(
                plan_id=str(row["proposed_plan_id"] or f"recommendation:{audit_log_id}"),
                plan_name="",
                provider_name="",
                rate_kwh=Decimal("0"),
            )
            decision = SwitchDecision(
                action="switch",  # User approved — override to switch
                reason=row["reason"] or "",
                proposed_plan=plan,
                projected_savings_monthly=Decimal(str(row["savings_monthly"] or "0")),
                projected_savings_annual=Decimal(str(row["savings_annual"] or "0")),
                etf_cost=Decimal(str(row["etf_cost"] or "0")),
                net_savings_year1=Decimal(str(row["net_savings_year1"] or "0")),
                confidence=Decimal(str(row["confidence_score"] or "0")),
                data_source=row["data_source"] or "unknown",
            )

            # Step 3 — execute against the existing audit row
            exec_result = await self.execute_switch(
                user_id,
                decision,
                audit_log_id=audit_log_id,
                tier=row["tier"] or "unknown",
            )

            # Step 4 — mark the audit log executed ONLY when a real enrollment
            # was started. An advisory record leaves ``executed`` FALSE.
            if exec_result.get("executed"):
                await self._db.execute(
                    text("""
                        UPDATE switch_audit_log
                        SET executed = TRUE,
                            enrollment_id = :enrollment_id
                        WHERE id = :id
                    """),
                    {
                        "enrollment_id": exec_result.get("enrollment_id"),
                        "id": audit_log_id,
                    },
                )
                await self._db.commit()

            logger.info(
                "switch_execution.recommendation_approved",
                audit_log_id=audit_log_id,
                user_id=user_id,
                execution_id=exec_result.get("execution_id"),
            )

            return exec_result
