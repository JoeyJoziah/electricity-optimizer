# Execution Log — ci-red-triage_20260515

## 2026-05-15 — Track created + Phases 1+2 closed

### Reds discovered

When commit `7d6834c8` (pytest-asyncio pin fix) fired previously-skipped CI jobs, 4 distinct failures surfaced:

1. **pip-audit** — 4 CVEs in cryptography / python-multipart / python-dotenv
2. **Migration Validation** — `063_migration_history.sql:11` SERIAL violation (real, not the "path bug" prior memory claimed)
3. **Security Scan / npm audit** — 7 vulns
4. **Backend Lint** — black+isort vs ruff config drift on 273 files

Plan ordered phases by autonomy: 1+2 fully autonomous, 3 semi-autonomous with halt-on-`--force`, 4 requires human formatter decision.

### Phase 1: pip-audit — DONE

Bumped 3 production deps in `backend/requirements.txt`:
- `cryptography 46.0.6 → 46.0.7`
- `python-multipart 0.0.22 → 0.0.27`
- `python-dotenv 1.0.0 → 1.2.2`

Auditing showed we only use `load_dotenv` (not `set_key`/`unset_key`), so the dotenv CVE wasn't exploitable in app code, but the bump was still needed for `pip-audit --strict` to pass in CI.

Local: `pip-audit -r backend/requirements.txt --strict` → `No known vulnerabilities found`. Pytest collection unchanged at 4035/4043.

Commit: `8bc2c462`. CI confirmation: Backend Tests job `76218939710` log shows `No known vulnerabilities found`.

### Phase 2: Migration validator exemption — DONE

Added `SERIAL_EXEMPT_FILES="063_migration_history.sql"` list to Check 4 in `.github/actions/validate-migrations/action.yml`. The migration history table intentionally uses SERIAL because sequential audit-log ordering is its purpose; UUID convention applies to business tables, not bookkeeping. Migration is already applied in prod across 66 deployments and cannot be retroactively changed without destructive schema work.

Local simulation: 0 violations across 68 migration files.

Commit: `c4fb2a14`. CI confirmation: Migration Validation job `76218939621` logs `(skipping SERIAL check for exempt file: 063_migration_history.sql)` followed by `All migration convention checks passed`.

### Phase 3: npm audit fix — HALTED

Attempted `npm audit fix`. Result: dep graph shifted slightly but vuln count went from 7 (5 mod, 2 high) to 10 (9 mod, 1 high). `--force` would downgrade Next.js to 9.3.3 (major regression).

Root cause: all 14 Next.js advisories list 16.x as vulnerable; no stable 16.3.x patch is released yet (only canaries through 16.3.0-canary.20). DOMPurify + Excalidraw vulns also unfixable without major bumps.

Reverted `package-lock.json`. Halt protocol fired per plan's documented decision gate.

### Phase 4: Backend Lint formatter decision — NOT STARTED (human-gated)

Awaiting decision: switch CI to ruff (recommended), switch pre-commit to black+isort, or run mass `black . && isort .`.

### Discovered latent reds (out of original plan)

Pushing `cc5b37dc` triggered workflows that surfaced 5 additional pre-existing failures the path filters had been masking. Full inventory in `plan.md` "Discovered Latent Reds" section (items #5-9).

Net effect: launch-blocker pile is ~9 latent reds, not 4. PH relaunch track must depend on this track being closed.

### Commits

- `8bc2c462` — fix(deps): patch CVEs in cryptography, python-multipart, python-dotenv
- `c4fb2a14` — ci(migrations): exempt audit-log tables from SERIAL check
- `cc5b37dc` — chore(conductor): register ci-red-triage_20260515 + mark Phase 1+2 complete

## 2026-05-15 (later) — Latent reds split into independent tracks

Discovered latent reds #5-9 were getting too varied (Postgres migration vs Python wheel availability vs Next.js config vs YAML shell quoting vs SQLAlchemy fixture) to keep gating a single parent track's closure on all five. Each has a distinct domain, owner, and risk profile, so the cleaner pattern is one track per root cause.

Split off:

- `ci-migration-apply-jsonb_20260515` — latent red #5 (jsonb cast at `003_reconcile_schema.sql:252`)
- `ci-ml-tensorflow-py312_20260515` — latent red #6 (tensorflow 2.15 no Py3.12 wheel)
- `ci-frontend-build-nextconfig_20260515` — latent red #7 (`next.config.js:12` build error)
- `ci-frontend-lint-workflow_20260515` — latent red #8 (workflow shell-quoting parses `lint` as project dir)
- `ci-integration-sqlalchemy-session_20260515` — latent red #9 (`Session.event` AttributeError in `test_auto_switcher_db.py`)

This parent track (`ci-red-triage_20260515`) now has exactly one open item: **Phase 3 (npm audit)**, which remains halted pending Next 16.3 stable or an explicit `--force`/major-bump approval. All five split tracks are launch-blockers for `ph-relaunch-jun2_20260515`.
