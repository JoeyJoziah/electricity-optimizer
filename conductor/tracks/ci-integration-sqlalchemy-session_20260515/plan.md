# Implementation Plan: Integration Tests — SQLAlchemy `Session.event` AttributeError

**Track ID:** ci-integration-sqlalchemy-session_20260515
**Created:** 2026-05-15
**Status:** [ ] Not Started
**Source:** `ci-red-triage_20260515` plan.md — Discovered Latent Red #9
**Discovered in CI runs:** `25929338762`, `25932772064`

## Problem

10+ integration tests in `backend/tests/integration/test_auto_switcher_db.py` fail at setup:

```
AttributeError: 'Session' object has no attribute 'event'
```

The error also surfaced in the post-pydantic-fix run (`25932772064`) — Backend Tests advanced past collection (proving the pydantic fix in `ci-pydantic-import_20260515` worked) but then hit this fixture-level failure.

## Root Cause Hypotheses

**A. SQLAlchemy 2.0 API change** — `Session.event` was a 1.x convenience; in 2.0 you use module-level `sqlalchemy.event.listens_for(Session, ...)`. Fixture probably calls `session.event.listens_for(...)` instead of `event.listens_for(session, ...)`.

**B. Lost skip-if-no-DATABASE_URL guard** — historical pattern (from audit-remediation_20260427) was to skip integration tests when CI didn't provision postgres. If CI now provisions postgres, the previously-skipped fixture runs and exposes the long-broken `session.event` call.

Both could be true simultaneously: the bug has always existed, but the skip guard was hiding it.

## Phase 1: Diagnose

- [ ] Task 1.1: Read `backend/tests/integration/test_auto_switcher_db.py` and any shared fixtures it imports (probably `conftest.py`)
- [ ] Task 1.2: Find the `Session.event` call site
- [ ] Task 1.3: Confirm SQLAlchemy version (`sqlalchemy==2.0.49` per pinning)
- [ ] Task 1.4: Check whether a `pytest.mark.skipif(not DATABASE_URL, ...)` guard exists and is firing correctly

## Phase 2: Fix

- [ ] Task 2.1: Rewrite the fixture to use the SQLAlchemy 2.0 API: `from sqlalchemy import event` + `event.listens_for(target, 'event_name')(handler)`
- [ ] Task 2.2: If the skip guard is missing, restore it so local devs without DATABASE_URL can still run unit tests cleanly
- [ ] Task 2.3: Run `pytest backend/tests/integration/test_auto_switcher_db.py` against a real Neon dev branch to verify

## Phase 3: Ship + verify

- [ ] Task 3.1: Commit + push, verify Backend Tests advances past the integration test setup
- [ ] Task 3.2: Confirm 10+ previously-erroring tests now pass (or skip if no DB)

## Completion Criteria

- [ ] Backend Tests job green on main
- [ ] Integration tests pass when DATABASE_URL is set, skip cleanly when it isn't
- [ ] No remaining `Session.event` references in test code (codebase-wide grep)

## Out of scope

- Auto Rate Switcher feature changes
- Rewriting the integration test architecture beyond fixing the broken fixture

## Related

- `ci-red-triage_20260515` — parent
- `ci-pydantic-import_20260515` — sibling fix; unblocks reaching this error
- `ph-relaunch-jun2_20260515` — launch-blocked until CI fully green
- Audit pattern `integration-test-skip-without-db` from `audit-remediation_20260427`
