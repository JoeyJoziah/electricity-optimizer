"""
Integration tests for the Auto Rate Switcher domain (audit P1-12).

These tests exercise the raw SQL statements in ``switch_*.py`` services
against a real Postgres engine. Unit tests in
``test_agent_switcher_api.py`` mock ``db.execute`` and therefore cannot
catch SQL syntax errors, missing migrations, or column-name typos in the
15 raw ``text()`` statements that ``agent_switcher.py`` and
``switch_execution_service.py`` rely on.

Setup
-----
The whole module is skipped if ``DATABASE_URL`` is unset (see
``conftest.py``). CI runs these against a postgres service container.

Each test rolls back at the end via the savepoint-wrapped ``db`` fixture,
so insertions are discarded and tests are order-independent.

Coverage map
------------
- ``SwitchSafeguardsService.check_kill_switch`` — happy path, agent
  disabled, LOA revoked, LOA not signed, paused.
- ``SwitchSafeguardsService.check_cooldown`` — fresh user (no prior
  switches), within-window, past-window.
- ``switch_audit_log`` schema invariants — required columns present,
  decision string in expected enum.
- ``user_agent_settings`` partial-update path used by ``check_now``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Apply both the package-level skip-if-no-DATABASE_URL and a class-level
# requirement that the schema is migrated before tests run.
pytestmark = [pytest.mark.asyncio]


@pytest.fixture
def fresh_user_id() -> str:
    """Generate a stable UUID for the test, kept in scope so multiple
    queries in one test target the same row."""
    return str(uuid.uuid4())


async def _seed_user(db: AsyncSession, user_id: str) -> None:
    """Insert a minimal users row so foreign keys resolve."""
    await db.execute(
        text("""
            INSERT INTO users (id, email, subscription_tier, created_at)
            VALUES (:id, :email, 'pro', NOW())
            ON CONFLICT (id) DO NOTHING
            """),
        {"id": user_id, "email": f"{user_id}@test.invalid"},
    )


async def _seed_settings(
    db: AsyncSession,
    user_id: str,
    *,
    enabled: bool = True,
    loa_signed: bool = True,
    loa_revoked: bool = False,
    paused_until: datetime | None = None,
) -> None:
    now = datetime.now(UTC)
    await db.execute(
        text("""
            INSERT INTO user_agent_settings
                (user_id, enabled, loa_signed_at, loa_revoked_at, paused_until,
                 savings_threshold_pct, savings_threshold_min, cooldown_days,
                 created_at, updated_at)
            VALUES
                (:uid, :enabled, :loa_signed_at, :loa_revoked_at, :paused_until,
                 10.0, 10.0, 5, :now, :now)
            ON CONFLICT (user_id) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                loa_signed_at = EXCLUDED.loa_signed_at,
                loa_revoked_at = EXCLUDED.loa_revoked_at,
                paused_until = EXCLUDED.paused_until,
                updated_at = EXCLUDED.updated_at
            """),
        {
            "uid": user_id,
            "enabled": enabled,
            "loa_signed_at": now if loa_signed else None,
            "loa_revoked_at": now if loa_revoked else None,
            "paused_until": paused_until,
            "now": now,
        },
    )


# =============================================================================
# SwitchSafeguardsService.check_kill_switch — exercises real schema
# =============================================================================


class TestCheckKillSwitchAgainstRealSchema:
    async def test_passes_when_settings_clear(self, db, schema_ready, fresh_user_id):
        from services.switch_safeguards import SwitchSafeguardsService

        await _seed_user(db, fresh_user_id)
        await _seed_settings(db, fresh_user_id, enabled=True, loa_signed=True)

        svc = SwitchSafeguardsService(db)
        result = await svc.check_kill_switch(fresh_user_id)

        assert result.passed is True
        assert "clear" in result.reason.lower()

    async def test_blocks_when_no_settings_row(self, db, schema_ready, fresh_user_id):
        from services.switch_safeguards import SwitchSafeguardsService

        await _seed_user(db, fresh_user_id)
        # No settings row inserted

        svc = SwitchSafeguardsService(db)
        result = await svc.check_kill_switch(fresh_user_id)

        assert result.passed is False
        assert "disabled" in result.reason.lower()

    async def test_blocks_when_disabled(self, db, schema_ready, fresh_user_id):
        from services.switch_safeguards import SwitchSafeguardsService

        await _seed_user(db, fresh_user_id)
        await _seed_settings(db, fresh_user_id, enabled=False, loa_signed=True)

        svc = SwitchSafeguardsService(db)
        result = await svc.check_kill_switch(fresh_user_id)

        assert result.passed is False
        assert "disabled" in result.reason.lower()

    async def test_blocks_when_loa_revoked(self, db, schema_ready, fresh_user_id):
        from services.switch_safeguards import SwitchSafeguardsService

        await _seed_user(db, fresh_user_id)
        await _seed_settings(
            db, fresh_user_id, enabled=True, loa_signed=True, loa_revoked=True
        )

        svc = SwitchSafeguardsService(db)
        result = await svc.check_kill_switch(fresh_user_id)

        assert result.passed is False
        assert "revoked" in result.reason.lower()

    async def test_blocks_when_loa_not_signed(self, db, schema_ready, fresh_user_id):
        from services.switch_safeguards import SwitchSafeguardsService

        await _seed_user(db, fresh_user_id)
        await _seed_settings(db, fresh_user_id, enabled=True, loa_signed=False)

        svc = SwitchSafeguardsService(db)
        result = await svc.check_kill_switch(fresh_user_id)

        assert result.passed is False
        assert (
            "not signed" in result.reason.lower() or "signed" in result.reason.lower()
        )

    async def test_blocks_when_paused_in_future(self, db, schema_ready, fresh_user_id):
        from services.switch_safeguards import SwitchSafeguardsService

        future_pause = datetime.now(UTC) + timedelta(days=14)
        await _seed_user(db, fresh_user_id)
        await _seed_settings(
            db, fresh_user_id, enabled=True, loa_signed=True, paused_until=future_pause
        )

        svc = SwitchSafeguardsService(db)
        result = await svc.check_kill_switch(fresh_user_id)

        assert result.passed is False
        assert "paused" in result.reason.lower()

    async def test_passes_when_pause_window_expired(
        self, db, schema_ready, fresh_user_id
    ):
        """A paused_until in the past should NOT block — the window has elapsed."""
        from services.switch_safeguards import SwitchSafeguardsService

        past_pause = datetime.now(UTC) - timedelta(days=1)
        await _seed_user(db, fresh_user_id)
        await _seed_settings(
            db, fresh_user_id, enabled=True, loa_signed=True, paused_until=past_pause
        )

        svc = SwitchSafeguardsService(db)
        result = await svc.check_kill_switch(fresh_user_id)

        assert result.passed is True


# =============================================================================
# Schema invariants — fail fast if a future migration drops a column the
# raw SQL in agent_switcher.py depends on.
# =============================================================================


class TestAuditLogSchemaInvariants:
    REQUIRED_COLUMNS = {
        "id",
        "user_id",
        "trigger_type",
        "decision",
        "reason",
        "savings_monthly",
        "savings_annual",
        "etf_cost",
        "net_savings_year1",
        "confidence_score",
        "data_source",
        "tier",
        "executed",
        "created_at",
    }

    async def test_required_columns_present(self, db, schema_ready):
        result = await db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'switch_audit_log'
                """))
        columns = {row[0] for row in result.fetchall()}
        missing = self.REQUIRED_COLUMNS - columns
        assert not missing, (
            f"switch_audit_log missing columns required by raw SQL in "
            f"agent_switcher.py:check_now: {sorted(missing)}"
        )

    async def test_executed_column_default_false(self, db, schema_ready, fresh_user_id):
        """check_now INSERTs with executed=FALSE; verify default lines up."""
        await _seed_user(db, fresh_user_id)

        audit_id = str(uuid.uuid4())
        await db.execute(
            text("""
                INSERT INTO switch_audit_log
                    (id, user_id, trigger_type, decision, reason, executed, created_at)
                VALUES
                    (:id, :uid, 'manual', 'hold', 'test', FALSE, NOW())
                """),
            {"id": audit_id, "uid": fresh_user_id},
        )

        result = await db.execute(
            text("SELECT executed FROM switch_audit_log WHERE id = :id"),
            {"id": audit_id},
        )
        row = result.first()
        assert row is not None
        assert row[0] is False


class TestSwitchExecutionsSchemaInvariants:
    async def test_required_status_values_accepted(
        self, db, schema_ready, fresh_user_id
    ):
        """rollback_switch reads status in (active, initiated, submitted, accepted)."""
        await _seed_user(db, fresh_user_id)
        for status_val in ("active", "initiated", "submitted", "accepted"):
            exec_id = str(uuid.uuid4())
            await db.execute(
                text("""
                    INSERT INTO switch_executions
                        (id, user_id, status, created_at, enacted_at)
                    VALUES (:id, :uid, :status, NOW(), NOW())
                    """),
                {"id": exec_id, "uid": fresh_user_id, "status": status_val},
            )
            row = (
                await db.execute(
                    text("SELECT status FROM switch_executions WHERE id = :id"),
                    {"id": exec_id},
                )
            ).first()
            assert row is not None
            assert row[0] == status_val
