# Tasks — ci-integration-sqlalchemy-session_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth.
> Validated 2026-05-21 (see execution.md). Task 2.3 live-DB run deferred (Docker daemon down, no psql, prod DB unsafe for write-path tests) — collection + skip-clean path verified instead.

## Phase 1: Diagnose
- [x] Task 1.1: Read `test_auto_switcher_db.py` + relevant conftest — verified (`backend/tests/integration/conftest.py`)
- [x] Task 1.2: Find `Session.event` call site — was conftest.py:70; now module-level
- [x] Task 1.3: Confirm SQLAlchemy version (expect 2.0.49) — confirmed 2.0.49
- [x] Task 1.4: Check skip-if-no-DATABASE_URL guard state — present at conftest.py:28 (pytestmark skipif)

## Phase 2: Fix
- [x] Task 2.1: Rewrite fixture to SQLA 2.0 API (`event.listens_for`) — `from sqlalchemy import event` + module-level decorator confirmed
- [x] Task 2.2: Restore skip guard if missing — guard present + firing
- [~] Task 2.3: Run integration suite against Neon dev branch — DEFERRED: Docker down + no psql locally; prod DB unsafe for these write-path tests. Substituted: `pytest --collect-only` → 10 tests collect cleanly in 0.04s (no AttributeError), confirming the fix. Live-DB pass-run still pending a dedicated dev branch.

## Phase 3: Ship
- [x] Task 3.1: Commit + push, Backend Tests advances past setup — fix commit merged (`338cfd13` / merge `fa7551cf`); collection no longer errors
- [x] Task 3.2: 10+ tests pass (or skip cleanly without DB) — 10 tests skip cleanly without DB (the "or skip" clause); satisfied for CI
