# Specification: Verification & Integration Quality Gates

**Track ID:** verification-gates_20260318
**Type:** Chore
**Created:** 2026-03-18
**Status:** Approved

## Summary

Close local developer-level quality gate gaps by wiring git hooks (pre-commit, pre-push), hardening the continuous-verify hook, adding conductor track completion validation, and implementing API contract checks between Pydantic models and TypeScript interfaces.

## Context

RateShift has strong CI/CD-level verification (migration-gate, security-gate, smoke tests, auto-rollback in deploy-production.yml) and a `scripts/loki-verify.sh` test runner, but lacks local developer-level quality gates. There are no pre-commit hooks, no pre-push gates, no automated conductor track completion validation, and no schema-level API contract checks. The `continuous-verify.sh` hook exists but only triggers after 5+ cross-category edits.

## Acceptance Criteria

- [ ] Pre-commit hook blocks commits with lint errors (frontend: eslint+prettier, backend: ruff)
- [ ] Pre-push hook blocks pushes when tests fail (wraps loki-verify.sh --quick)
- [ ] SKIP_VERIFY=1 escape hatch works for pre-push
- [ ] `scripts/verify-track-completion.sh` accurately reports conductor track status
- [ ] `scripts/verify-all-tracks.sh` produces summary table of all tracks
- [ ] `scripts/api-contract-check.py` detects Pydantic↔TypeScript field mismatches
- [ ] Continuous-verify triggers more reliably (3 edits, any category, 60s cooldown)
- [ ] Continuous-verify falls back to direct pytest/jest when loki-verify.sh missing
- [ ] All new scripts have --help and --dry-run flags
- [ ] No existing tests broken

## Dependencies

- `scripts/loki-verify.sh` — existing test orchestrator (pre-push wraps this)
- `.claude/hooks/verification/continuous-verify.sh` — existing hook (enhanced, not replaced)
- `conductor/tracks/*/plan.md` — track plans with checkbox conventions

## Non-Goals

- E2E test gates (too slow for local hooks)
- Blocking CI on API contract mismatches (annotation-only initially)
- Auto-fixing lint errors on commit (eslint --fix is opt-in via lint-staged)
