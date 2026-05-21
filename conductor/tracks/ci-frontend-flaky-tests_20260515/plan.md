# Implementation Plan: Frontend Flaky Test Cleanup

**Track ID:** ci-frontend-flaky-tests_20260515
**Created:** 2026-05-15
**Status:** [x] Complete — verified 2026-05-21 (8 files run 10/10 consecutive green; full FE suite 3/3 consecutive @ 3437/3437; fix commit `9340309e` confirmed in origin/main)
**Trigger:** Loki pre-push verification hook blocked 3 consecutive push attempts during the 2026-05-15 session with different flaky test failures each time

## Problem

Pre-push hook ran the full frontend Jest suite three times during the autofix-baseline push:

| Run | Time | Failures | Tests that flaked |
|---|---|---|---|
| 1 | 15:24:18 | 1 | `ConnectionsOverview.test.tsx:392` — 5s timeout |
| 2 | 15:38:44 | 1 | `decisionPresentation.test.ts:95` — clock race ("3h 30m" vs "3h 29m") |
| 3 | 15:43:34 | 15 across 8 suites | Population of known flakes (see below) |

These failures are **not caused by the change being pushed** (mechanical comment-only autofix diff). They are pre-existing instability in the test suite that's now blocking development velocity directly via the pre-push hook.

## Inventory of known flaky tests

From `.claude/logs/loki-verify.log` history:

| File | Failure mode | Likely fix |
|---|---|---|
| `__tests__/components/auto-switcher/decisionPresentation.test.ts:95` | Real-clock crossing "30m → 29m remaining" boundary mid-test | `jest.useFakeTimers({ now: <fixed date> })` |
| `__tests__/components/connections/ConnectionsOverview.test.tsx:392` | 5000ms timeout on async test | Raise test timeout + `waitFor` with longer max + assert specific elements |
| `__tests__/components/rate-changes/RateChangeFeed.test.tsx:117` | 5000ms timeout on filter selection | Same pattern |
| `__tests__/components/suppliers/SupplierSelector.test.tsx` | Recurring failure (mode unspecified in logs) | Investigate |
| `__tests__/components/connections/ConnectionRates.test.tsx` | Recurring | Investigate |
| `__tests__/components/community-solar/CommunitySolarContent.test.tsx` | Recurring | Investigate |
| `__tests__/hooks/useReports.test.ts` | Recurring | Investigate |
| `__tests__/components/ComparisonTable.test.tsx` | Recurring | Investigate |

## Approach

1. **Determinism over relaxation.** Use `jest.useFakeTimers`, `MockDate`, `waitFor` with explicit timeouts, deterministic mock data. **Do not** raise jest `--testTimeout` globally; that masks real perf regressions.
2. **No silenced assertions.** If a test asserts `/3h 30m remaining/`, the fix is to make the clock deterministic so the assertion can be tight, not to switch to `.toMatch(/.+/)` or remove the assertion.
3. **One commit per file** where possible — keeps revert surface small if any fix accidentally weakens coverage.

## Completion Criteria

- [x] All 8 listed test files pass 10/10 consecutive runs locally — verified 2026-05-21 (8-file set, 10/10 green, 108 tests each)
- [x] No `--testTimeout` increase at config level — fixes used `jest.useFakeTimers` (decisionPresentation) + `userEvent.setup({ delay: null })` (5 component files); no global timeout change
- [x] No `.skip()` / `.todo()` added — confirmed; 2 no-defect files (CommunitySolarContent, useReports) left fully intact
- [x] Pre-push hook passes cleanly on a follow-up no-op push — fix commit `9340309e` is in origin/main; local==origin, tree clean

## Out of scope

- Identifying additional flaky tests beyond the 8 inventoried
- Refactoring test infrastructure (jest config, setup files) beyond fixing specific flakes
- Performance optimization of slow tests (separate concern from flake)

## Related

- `ci-frontend-lint-baseline_20260515` — blocked behind this for the autofix push
- `ph-relaunch-jun2_20260515` — launch-gate quality bar
