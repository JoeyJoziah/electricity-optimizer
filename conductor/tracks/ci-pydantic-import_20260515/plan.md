# Implementation Plan: CI pydantic ImportError

**Track ID:** ci-pydantic-import_20260515
**Created:** 2026-05-15
**Status:** [~] In Progress
**Discovered:** 2026-05-15 while verifying E2E run `25931993759` on commit `0a7c6de1`. Backend cannot boot in CI; affects Backend Tests, Security Tests, and E2E Tests jobs.

## Overview

The backend fails to import in CI with:

```
File "config/settings.py", line 10, in <module>
    from pydantic import Field, field_validator, model_validator
ImportError: cannot import name 'field_validator' from 'pydantic' (...)
Did you mean: 'root_validator'?
```

`field_validator` is a pydantic v2 API. We pin `pydantic==2.12.5` in `backend/requirements.txt`, so this should work — and it does locally. The CI failure happens specifically when `backend/requirements-dev.txt` is installed AFTER `backend/requirements.txt`.

## Root Cause

`backend/requirements-dev.txt:25` pins `safety==3.0.0`. That release of safety has a transitive dep on `safety-schemas==0.0.5` which requires `pydantic<2`, which downgrades the previously-installed pydantic 2.12.5 to pydantic 1.10.26.

CI install log on run `25931993759`:
```
Successfully installed ... pydantic-1.10.26 ...
```

(directly contradicting the `pydantic-2.12.5` from the requirements.txt install one step earlier).

Local `.venv` has `safety==3.7.0` + `safety-schemas==0.0.16` (both pydantic-2 compatible) because pip resolution gave us a newer minor at install time. CI is a fresh resolve and respects the `==3.0.0` pin strictly.

This is a textbook "local-venv-masks-ci-resolver-conflict" pattern — same family as the pytest-asyncio issue from yesterday's session.

## Decision

**Remove `safety` from `requirements-dev.txt` entirely.** Justification:
- `grep -rln "\bsafety\b" .github/ Makefile` returns empty — nothing actually invokes the `safety` tool
- We already use `pip-audit` for python dep CVE scanning (in `_backend-tests.yml` per Phase 1 of `ci-red-triage_20260515`)
- Two redundant security scanners on the same dep file with conflicting pydantic constraints = pure liability
- Keeping safety at a higher pin would defer the problem; deletion eliminates the class

Alternative considered: bump to `safety>=3.5`. Rejected because adds maintenance surface for a tool we don't run.

---

## Phase 1: Remove safety + verify

- [x] Task 1.1: Delete `safety==3.0.0` line from `backend/requirements-dev.txt` — replaced with explanatory comment block
  - **Verify locally:**
    ```
    cd backend && ../.venv/bin/pip install -r requirements-dev.txt --dry-run 2>&1 | grep -i pydantic
    ```
    Should show no pydantic downgrade attempt
  - **Risk:** Low. Nothing imports `safety` and pip-audit covers the same intent.

- [x] Task 1.2: Commit + push, verify CI green
  - **Commit:** `17f21844` (safety removal) + `2a78670c` (track registration)
  - **CI confirmation (run `25932772064`):**
    - Install log: `Successfully installed ... pydantic-2.12.5 ...` — no v1 downgrade
    - Backend Tests advances all the way to **test collection** (vs. previous run which exit-1'd at install)
    - Security Tests sub-job: backend boots (`INFO: Application startup complete.`), 99-100% of SQL-injection tests PASSED
    - E2E Tests: skipped this run because path filter only fires on `frontend/**` and this commit batch was backend/conductor only — manual workflow_dispatch (added in `0a7c6de1`) is the way to verify new E2E specs end-to-end
  - **New downstream failures revealed (separate latent reds, NOT this fix's responsibility):**
    - Backend Tests: still red on `'Session' object has no attribute 'event'` in `tests/integration/test_auto_switcher_db.py` (this is latent red #9 — pre-existing, separate track needed)
    - Security Tests: 3 rate-limit test assertion failures in `test_rate_limiting.py` (latent red #11 — newly discovered; narrow scope)
  - **Success criteria:** Backend Tests job advances past collection (pydantic import succeeds); Security Tests `wait-for-service` completes (backend starts); E2E Tests can run
  - **Note:** Backend Tests will likely still fail downstream on the integration-test fixture issue (latent red #5: `'Session.event' AttributeError`). That's a separate track. This track only needs the import to succeed.

---

## Completion Criteria

- [ ] `grep -i pydantic` on a fresh requirements-dev install resolves to 2.12.5 (no downgrade)
- [ ] CI Backend Tests job advances past `from config.settings import settings` import
- [ ] CI Security Tests job's `wait-for-service` succeeds (backend boots within 60s)
- [ ] E2E Tests job runs the new `unsubscribe-flow.spec.ts` + `drip-enrollment.spec.ts` (pass or fail; the goal here is "they actually execute")

## Out of scope

- Switching to a different security scanner
- Rewriting `requirements-dev.txt` for unrelated cleanups
- Resolving the integration-test fixture latent red (#5)

## Related

- Pattern: same family as 2026-05-14 pytest-asyncio fix (CI fresh resolve vs local cached venv) → see `local-venv-masks-ci-resolver-conflict` learned skill
- This is latent red #6 from `ci-red-triage_20260515`'s "Discovered Latent Reds" — splitting into its own track per Decision 2 from the morning interview
