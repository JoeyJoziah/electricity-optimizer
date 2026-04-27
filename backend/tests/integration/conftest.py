"""
Shared fixtures for backend integration tests.

These tests run against a *real* Postgres database (CI service container or
local dev DB) so we can exercise raw SQL paths that unit tests mock away —
specifically the 23 raw `text()` statements in the auto-switcher domain.

The whole module is skipped when ``DATABASE_URL`` is not set, so local
``pytest backend/tests/`` runs without postgres remain green.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Skip the whole package if postgres is not configured. CI sets this; local
# devs can opt in by exporting DATABASE_URL=postgresql+asyncpg://localhost/...
DATABASE_URL = os.environ.get("INTEGRATION_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason=(
        "Integration tests require DATABASE_URL (or INTEGRATION_TEST_DATABASE_URL). "
        "Set it to a postgres-compatible URL to enable. CI provides this via "
        "the postgres service container."
    ),
)


_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest_asyncio.fixture(scope="module")
async def engine():
    """Create an async SQLAlchemy engine for the test database."""
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")

    # Normalize asyncpg driver if user supplied a sync URL
    url = DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    eng = create_async_engine(url, echo=False, future=True)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession wrapped in a transaction that rolls back on teardown.

    This keeps tests isolated: any inserts/updates/deletes within a test are
    discarded after the test returns, so the order of test execution does not
    matter.
    """
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        # Use a SAVEPOINT so the test can call session.commit() without
        # actually persisting beyond the outer transaction we will roll back.
        async with SessionLocal(bind=conn) as session:

            @session.sync_session.event.listens_for(session.sync_session, "after_transaction_end")
            def _restart_savepoint(s, transaction):  # pragma: no cover — fixture wiring
                if transaction.nested and not transaction._parent.nested:
                    s.begin_nested()

            await session.begin_nested()
            try:
                yield session
            finally:
                await session.rollback()
        # Outer transaction rolls back automatically when exiting `engine.begin()`.


def _migration_files() -> list[Path]:
    """Return migration files in numeric order."""
    return sorted(_MIGRATIONS_DIR.glob("*.sql"))


def _migrations_applied(migration_names: set[str]) -> set[str]:
    return {p.stem for p in _migration_files()} & migration_names


@pytest.fixture(scope="module")
def auto_switcher_migrations_required() -> list[str]:
    """The migrations that the auto-switcher integration tests depend on.

    Tests skip with a clear reason if any of these are missing from the
    schema (e.g. a fresh test DB hasn't been migrated).
    """
    return [
        "060_updated_at_triggers",
        "061_audit_schema_fixes",
        "062_audit_schema_fixes_round2",
        "066_auto_rate_switcher",
    ]


@pytest_asyncio.fixture
async def schema_ready(engine, auto_switcher_migrations_required):
    """Verify the auto-switcher schema is present, skip otherwise.

    Production runs migrations via ``scripts/run_migrations.py``; CI is
    expected to do the same before invoking this test suite. We just check
    for the presence of the key tables here rather than re-applying
    migrations on every test (which would slow the suite and risk schema
    divergence).
    """
    required_tables = {
        "user_agent_settings",
        "switch_audit_log",
        "switch_executions",
        "available_plans",
        "user_plans",
        "meter_readings",
    }
    async with engine.connect() as conn:
        result = await conn.exec_driver_sql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        present = {row[0] for row in result.fetchall()}

    missing = required_tables - present
    if missing:
        pytest.skip(
            f"Auto-switcher schema not migrated. Missing tables: {sorted(missing)}. "
            f"Run scripts/run_migrations.py first. "
            f"Required migrations: {auto_switcher_migrations_required}"
        )
