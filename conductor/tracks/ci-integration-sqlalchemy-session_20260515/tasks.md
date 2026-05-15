# Tasks — ci-integration-sqlalchemy-session_20260515

> Extracted from plan.md on 2026-05-15. plan.md remains source of truth.

## Phase 1: Diagnose
- [ ] Task 1.1: Read `test_auto_switcher_db.py` + relevant conftest
- [ ] Task 1.2: Find `Session.event` call site
- [ ] Task 1.3: Confirm SQLAlchemy version (expect 2.0.49)
- [ ] Task 1.4: Check skip-if-no-DATABASE_URL guard state

## Phase 2: Fix
- [ ] Task 2.1: Rewrite fixture to SQLA 2.0 API (`event.listens_for`)
- [ ] Task 2.2: Restore skip guard if missing
- [ ] Task 2.3: Run integration suite against Neon dev branch

## Phase 3: Ship
- [ ] Task 3.1: Commit + push, Backend Tests advances past setup
- [ ] Task 3.2: 10+ tests pass (or skip cleanly without DB)
