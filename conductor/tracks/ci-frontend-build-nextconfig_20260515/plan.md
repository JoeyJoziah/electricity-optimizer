# Implementation Plan: Frontend Build — next.config.js:12 error

**Track ID:** ci-frontend-build-nextconfig_20260515
**Created:** 2026-05-15
**Status:** [x] Complete — validated 2026-05-21 (`CI=true npm run build` succeeds locally with empty NEXT_PUBLIC_APP_URL → guard warns, no throw; Frontend Build job green in CI run 25939815464)
**Source:** `ci-red-triage_20260515` plan.md — Discovered Latent Red #7
**Discovered in CI run:** `25929338762`

## Problem

Frontend Build job errors at `next.config.js:12:9` during build. Local `npm run build` succeeds, so this is a CI-environment-specific failure.

## Likely Causes (in order of probability)

1. **ESM/CJS mismatch** — Next 16 nudged config to ESM (`next.config.mjs`) but ours is still `.js` with `module.exports = ...`. CI Node version may be stricter.
2. **Env-var access at config-load time** — line 12 reads `process.env.SOMETHING` and CI doesn't have that var set; local `.env.local` masks the gap.
3. **Top-level `await` or other syntax** — only valid in ESM context; works locally if Node version newer than CI.
4. **Path resolution** — relative import in next.config.js resolving differently in CI working dir.

## Phase 1: Diagnose

- [x] Task 1.1: Read `frontend/next.config.js` (or `.mjs`/`.ts` variant) lines 1-30
- [x] Task 1.2: Pull the exact CI error message + stack from run `25929338762` (or rerun if expired)
- [x] Task 1.3: Cross-reference line 12 against likely cause list

## Phase 2: Fix

- [x] Task 2.1: Apply the targeted fix matching the diagnosis (env-var default, ESM rename, syntax cleanup, etc.)
- [x] Task 2.2: Verify `npm run build` succeeds locally with the same Node version CI uses
- [x] Task 2.3: Verify production bundle output unchanged (no behavior drift)

## Phase 3: Ship + verify

- [x] Task 3.1: Commit + push, Frontend Build job turns green
- [x] Task 3.2: Confirm Vercel deploy preview still builds successfully (parallel sanity check)

## Completion Criteria

- [x] Frontend Build job green on main
- [x] Vercel preview deployments still build (no regression)
- [x] Root cause documented in execution.md

## Out of scope

- Migrating next.config to TypeScript
- Refactoring other Next.js config plumbing

## Related

- `ci-red-triage_20260515` — parent
- `ph-relaunch-jun2_20260515` — launch-blocked until CI fully green
