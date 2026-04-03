"""
Switch Execution Service

Orchestrates the full plan-switch lifecycle from initiation through rollback.

State machine:
    initiating → initiated → submitted → accepted → active
    (failed or rolled_back can occur from any pre-terminal state)

Tables:
    switch_executions  — one row per execution attempt (idempotency_key is unique)
    switch_audit_log   — decision snapshot written before execution begins

The service delegates all provider interactions to the SwitchExecutor protocol.
"""

import uuid
from datetime import UTC, datetime, timedelta
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
    ) -> dict:
        """Initiate a plan switch for a user.

        Steps:
        1. Generate idempotency key.
        2. Write decision snapshot to ``switch_audit_log``.
        3. Insert ``switch_executions`` row (status='initiating').
        4. Resolve the executor for ``state_code``.
        5. Verify plan availability.
        6. Call ``execute_enrollment``.
        7. Update execution status to 'initiated' (or 'submitted' for advisory).
        8. Return execution summary dict.

        On any exception the execution row is marked 'failed' and the
        exception is re-raised after a rollback.

        Args:
            user_id:    UUID string of the user.
            decision:   A ``SwitchDecision`` instance from the decision engine.
            state_code: Two-letter US state code used to select the executor
                        (mapped to Region enum format internally).

        Returns:
            Dict with keys: ``execution_id``, ``status``, ``enrollment_id``.

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
            idempotency_key = str(uuid.uuid4())
            execution_id = str(uuid.uuid4())
            audit_log_id = str(uuid.uuid4())

            proposed_plan = getattr(decision, "proposed_plan", None)
            plan_id = proposed_plan.plan_id if proposed_plan else ""
            plan_name = proposed_plan.plan_name if proposed_plan else ""
            provider_name = proposed_plan.provider_name if proposed_plan else ""
            rate_kwh = float(proposed_plan.rate_kwh) if proposed_plan else 0.0
            savings_monthly = float(getattr(decision, "projected_savings_monthly", Decimal("0")))
            savings_annual = float(getattr(decision, "projected_savings_annual", Decimal("0")))
            confidence = float(getattr(decision, "confidence", Decimal("0")))
            action = getattr(decision, "action", "")
            reason = getattr(decision, "reason", "")
            data_source = getattr(decision, "data_source", "unknown")

            # Step 2 — audit log snapshot
            await self._db.execute(
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
                    "id": audit_log_id,
                    "user_id": user_id,
                    "decision": action,
                    "plan_id": plan_id,
                    "plan_name": plan_name,
                    "provider_name": provider_name,
                    "rate_kwh": rate_kwh,
                    "savings_monthly": savings_monthly,
                    "savings_annual": savings_annual,
                    "confidence": confidence,
                    "reason": reason,
                    "data_source": data_source,
                },
            )

            # Step 3 — execution row
            await self._db.execute(
                text("""
                    INSERT INTO switch_executions
                        (id, user_id, status, idempotency_key, plan_id, plan_name,
                         provider_name, audit_log_id, created_at, updated_at)
                    VALUES
                        (:id, :user_id, 'initiating', :idempotency_key, :plan_id,
                         :plan_name, :provider_name, :audit_log_id, NOW(), NOW())
                """),
                {
                    "id": execution_id,
                    "user_id": user_id,
                    "idempotency_key": idempotency_key,
                    "plan_id": plan_id,
                    "plan_name": plan_name,
                    "provider_name": provider_name,
                    "audit_log_id": audit_log_id,
                },
            )

            try:
                await self._db.commit()
            except Exception:
                await self._db.rollback()
                raise

            # Step 4-7 — executor interaction
            region = f"us_{state_code.lower()}"
            executor = get_executor(region)
            enrollment_id = None
            final_status = "initiated"

            try:
                # Step 5 — plan availability
                available = await executor.check_plan_available(plan_id)
                if not available:
                    raise RuntimeError(f"Plan {plan_id} is not available for enrollment.")

                # Step 6 — execute enrollment
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

                # Step 7 — determine final status
                if isinstance(executor, AdvisoryOnlyFallback):
                    final_status = "submitted"
                else:
                    final_status = "initiated"

                # Update execution row
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
                    "switch_execution.initiated",
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

            return {
                "execution_id": execution_id,
                "status": final_status,
                "enrollment_id": enrollment_id,
            }

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
                    SELECT id, status, enrollment_id, plan_id, plan_name,
                           provider_name, created_at, updated_at
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
        """Approve a pending recommendation and execute the switch.

        For Pro tier users — converts a ``recommend`` audit log entry into
        an active execution.

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
                    SELECT id, user_id, decision, plan_id, plan_name,
                           provider_name, rate_kwh, projected_savings_monthly,
                           projected_savings_annual, confidence, reason,
                           data_source, executed
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

            # Step 2 — build a minimal SwitchDecision-compatible object from the log
            from services.switch_decision_engine import PlanDetails, SwitchDecision

            plan = PlanDetails(
                plan_id=row["plan_id"] or "",
                plan_name=row["plan_name"] or "",
                provider_name=row["provider_name"] or "",
                rate_kwh=Decimal(str(row["rate_kwh"] or "0")),
            )
            decision = SwitchDecision(
                action="switch",  # User approved — override to switch
                reason=row["reason"] or "",
                proposed_plan=plan,
                projected_savings_monthly=Decimal(str(row["projected_savings_monthly"] or "0")),
                projected_savings_annual=Decimal(str(row["projected_savings_annual"] or "0")),
                confidence=Decimal(str(row["confidence"] or "0")),
                data_source=row["data_source"] or "unknown",
            )

            # Step 2 — execute the switch
            exec_result = await self.execute_switch(user_id, decision)

            # Step 3 — mark audit log as executed
            await self._db.execute(
                text("""
                    UPDATE switch_audit_log
                    SET executed = TRUE,
                        enrollment_id = :enrollment_id,
                        updated_at = NOW()
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
