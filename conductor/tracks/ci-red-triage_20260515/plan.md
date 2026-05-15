# Implementation Plan: CI Red Triage

**Track ID:** ci-red-triage_20260515
**Created:** 2026-05-15
**Status:** [~] In Progress
**Trigger:** Commit `7d6834c8` exposed 4 latent CI failures previously masked by `paths:` filters. All are launch blockers per "tests are sacred."

## Overview

Resolve 4 CI failures discovered when a `backend/**` push fired previously-skipped jobs. Reds, in order of autonomy/safety:

1. **pip-audit** (Backend Tests sub-step) — 4 CVEs, all patch/minor bumps available
2. **Migration Validation** — `SERIAL PRIMARY KEY` violation in audit-log table; needs validator exception
3. **npm audit (Security Scan)** — 7 vulns, `npm audit fix` available
4. **Backend Lint** — black+isort (CI) vs ruff (pre-commit) config drift on 273 files; needs canonical-formatter decision

Last green CI run on main: `eb5df2ab` (gitignore-only commit, skipped most jobs). Last *fully* green run with all jobs firing: unknown (filters have masked these for ≥15 days).

---

## Phase 1: pip-audit CVE bumps (autonomous, low risk)

- [x] Task 1.1: Bump pinned versions in `backend/requirements.txt`
  - **Source:** pip-audit findings from CI run `25925601093`
  - **Bumps:**
    - `cryptography==46.0.6` → `46.0.7` — CVE-2026-39892 (buffer overflow in `Hash.update()`)
    - `python-multipart==0.0.22` → `0.0.27` — CVE-2026-40347 + CVE-2026-42561 (multipart DoS, header DoS)
    - `python-dotenv==1.0.0` → `1.2.2` — CVE-2026-28684 (symlink-follow file-overwrite)
  - **Risk:** Low. All patch or single-minor bumps. python-dotenv adds `follow_symlinks: bool = False` parameter (default-safe; we don't use `set_key`/`unset_key` in app code).
  - **Verify locally:**
    ```
    cd backend && .venv/bin/pip install -r requirements.txt
    .venv/bin/python -m pytest --collect-only -q  # collection sanity
    .venv/bin/python -m pip-audit -r requirements.txt --strict  # should pass
    ```
  - **Test:** Re-run `_backend-tests.yml` step locally if pip-audit available; otherwise rely on CI

- [x] Task 1.2: Commit + push, verify CI green for pip-audit step
  - **Commits:** `8bc2c462` (deps bump) + `cc5b37dc` (track registration) pushed to main
  - **CI confirmation:** Backend Tests job `76218939710` — pip-audit step output: `No known vulnerabilities found`. Backend Tests job overall still red but on a *different* later step (see Discovered Latent Reds below)

---

## Phase 2: Migration validator exception (autonomous, defensible)

- [x] Task 2.1: Add SERIAL exemption for audit-log tables in validator
  - **Source:** `063_migration_history.sql:11` — `id SERIAL PRIMARY KEY` for the migration history audit log
  - **Context:** UUID convention exists for *business* tables. Migration history is internal bookkeeping with sequential semantics — SERIAL is correct here. The migration was already applied to prod (66 migrations live), so we can't retroactively change column type without a destructive migration.
  - **Action:** In `.github/actions/validate-migrations/action.yml` Check 4, add explicit exemption list. Easiest: skip files in `EXEMPT_FILES`. Initially `["063_migration_history.sql"]`.
  - **Code shape:**
    ```bash
    EXEMPT_FILES="063_migration_history.sql"
    for filepath in "$MIGRATION_DIR"/*.sql; do
      filename=$(basename "$filepath")
      echo "$EXEMPT_FILES" | grep -qw "$filename" && continue
      # ... existing SERIAL check
    done
    ```
  - **Risk:** Low. Exemption is narrow + documented in action.yml comments.
  - **Verify locally:** Run the action shell block against `backend/migrations` and confirm 0 violations

- [x] Task 2.2: Commit + push, verify Migration Validation **convention checks** green
  - **Commit:** `c4fb2a14` pushed to main
  - **CI confirmation:** Migration Validation job `76218939621` — convention check log: `(skipping SERIAL check for exempt file: 063_migration_history.sql)` followed by `All migration convention checks passed.`
  - **Caveat:** Job overall still red because of a *separate* later step ("Apply all migrations sequentially") which fails on `psql:backend/migrations/003_reconcile_schema.sql:252: ERROR: default for column "data_categories_deleted" cannot be cast automatically to type jsonb`. This is a different latent red — see Discovered Latent Reds below.

---

## Phase 3: npm audit fix (semi-autonomous, needs verification)

- [~] Task 3.1: Run `npm audit fix` in `frontend/` — **HALTED, no clean fix available**
  - **Attempt:** Ran `npm audit fix` against current Next 16.2.6 (already latest stable 16.x). Result: dep graph shifted slightly but vuln count went from 7 (5 mod, 2 high) to 10 (9 mod, 1 high). `--force` would downgrade Next.js to 9.3.3 (major regression).
  - **Root cause:** All 14 Next.js advisories list 16.x as vulnerable but no stable 16.3.x patch is released yet (only canaries through 16.3.0-canary.20). DOMPurify + Excalidraw vulns also unfixable without major bumps.
  - **Reverted:** `package-lock.json` restored to pre-attempt state.
  - **Halt reason:** Plan's documented decision gate fired — `--force` and major bumps are out of scope without explicit approval.
  - **Source:** Security Scan failure from CI run `25925601093`
  - **Vulnerabilities (7 total: 5 mod, 2 high):**
    - `@excalidraw/excalidraw` — XSS via Mermaid sequence diagram labels
    - `dompurify` — 4 XSS variants (transitive via mermaid → excalidraw)
    - `next` — DoS, SSRF, cache poisoning, CSP nonce XSS, segment-prefetch bypass (transitive likely; we're already on Next 16)
    - `postcss` — vulnerable transitive
  - **Action:** `cd frontend && npm audit fix` then inspect what changed
  - **Risk:** Medium. May bump Next.js patch version (likely safe within 16.x). Excalidraw bump may be a major.
  - **Verify locally:**
    ```
    cd frontend
    npm audit fix
    git diff package.json package-lock.json | head -100  # inspect changes
    npm test 2>&1 | tail -20  # full suite
    npm run build  # production build sanity
    npx playwright test e2e/visual-regression.spec.ts  # baseline check
    ```
  - **Decision gate:** if `npm audit fix` requires `--force` or major version bumps, HALT and surface for human decision

- [ ] Task 3.2: Commit + push, verify npm audit step green

---

## Phase 4: Backend Lint config drift (HUMAN DECISION REQUIRED)

- [ ] Task 4.1: Decide canonical Python formatter
  - **Problem:** CI runs `black==26.3.1 isort==8.0.1` (ci.yml:79) but pre-commit runs `ruff format` + `ruff check` (.pre-commit-config.yaml). The two formatters disagree on 273 files. Local pre-commit passes; CI fails. Engineers running pre-commit hooks will keep producing red CI.
  - **Options:**
    - **A. Switch CI to ruff** (recommended) — small `ci.yml` diff (3 lines: replace pip install + format step), zero file churn, aligns with pre-commit and modern Python tooling. Risk: rule semantics differ slightly between black and ruff format
    - **B. Switch pre-commit to black+isort** — small `.pre-commit-config.yaml` diff, but ruff is faster and we'd lose ruff's lint integration
    - **C. Run mass `black . && isort .`** — 273 files reformatted, then keep both running and assume they converge. Will probably re-diverge on next ruff release. Most churn, least durable.
  - **Recommendation:** Option A. Ruff is the project's de-facto standard (already in pre-commit, in `requirements-dev.txt`, in CLAUDE.md "ruff clean" success criteria from yesterday's verification-loop)
  - **Output:** decision recorded in `execution.md` + ADR if Option A
  - **Halt point:** This task is the boundary of autonomy. Wait for explicit user approval before executing chosen option.

- [ ] Task 4.2: Execute chosen option (after approval)
- [ ] Task 4.3: Commit + push, verify Backend Lint green

---

## Completion Criteria

- [ ] CI run on main is fully green (all 4 previously-failing jobs pass)
- [ ] `pip-audit -r backend/requirements.txt --strict` exits 0 locally
- [ ] `npm audit --audit-level=high` in `frontend/` exits 0
- [ ] Migration validator passes on current `backend/migrations/`
- [ ] No backend or frontend tests regressed
- [ ] Decision recorded for backend formatter (ruff vs black+isort)
- [ ] Memory updated to correct prior "migration path bug" mischaracterization

## Out of scope

- The 5 *moderate* npm vulns that don't trip `--audit-level=high`
- Mass refactor of pre-commit/ci.yml beyond the formatter alignment
- Pinning policy review (Dependabot already groups minor+patch weekly)

---

## Discovered Latent Reds (out of original plan, surfaced by `cc5b37dc` push)

The `7d6834c8` push (which was a `backend/**`-only diff) surfaced 4 reds. Pushing `cc5b37dc` triggered additional workflows that exposed 5 more pre-existing failures the path filters had been masking. Full latent-red inventory as of CI run `25929338762`:

**Original 4 (in plan):**
1. ✅ pip-audit — closed Phase 1
2. ✅ Migration Validation convention checks — closed Phase 2 (job overall still red, see #5 below)
3. ❌ npm audit — Phase 3 halted (no clean Next.js patch)
4. ❌ Backend Lint formatter drift — Phase 4 awaiting human decision

**Discovered 5 (need follow-up tracks or expansion):**
5. **Migration apply step** — `psql:backend/migrations/003_reconcile_schema.sql:252: ERROR: default for column "data_categories_deleted" cannot be cast automatically to type jsonb`. Convention check (Phase 2) passes, but the `psql -f` smoke-test step fails on this old migration. Likely fix: `ALTER TABLE ... ALTER COLUMN ... TYPE jsonb USING data_categories_deleted::jsonb` rewrite of migration 003, or `DROP DEFAULT` then `ALTER TYPE` then `SET DEFAULT`. Risk: rewriting an applied migration breaks anyone who replays from scratch unless we also add a guard.
6. **ML Tests** — `ERROR: No matching distribution found for tensorflow==2.15.0`. Likely cause: tensorflow 2.15 only ships wheels for Python ≤3.11; CI uses Python 3.12. Either pin tensorflow ≥2.16 or pin CI Python to 3.11 for ML matrix.
7. **Frontend Build** — error in `next.config.js:12:9` during build. Need to inspect file; could be ESM/CJS issue or env-var access at build time.
8. **Frontend Lint** — `Invalid project directory provided, no such directory: .../frontend/lint`. Looks like a workflow shell-quoting bug, e.g., `npm run lint` was rendered as `npm run` `lint` (positional arg parsed as project dir). Likely a `working-directory` + script-name typo in ci.yml.
9. **Backend Tests post-pip-audit** — 10+ integration tests in `tests/integration/test_auto_switcher_db.py` fail at setup with `AttributeError: 'Session' object has no attribute 'event'`. SQLAlchemy fixture pattern incompatible with current sqlalchemy==2.0.49, OR the integration-test skip-if-no-DATABASE_URL pattern stopped firing because CI now provisions postgres. Either fix the fixture or restore the skip guard.

**Implication for PH relaunch:** "Tests are sacred" + "all CI green" is the launch gate. With 9 latent reds across the pipeline, the gate is much further away than the 18-item PRD scope tracker suggests. The PH relaunch track should formally depend on this track being closed.
