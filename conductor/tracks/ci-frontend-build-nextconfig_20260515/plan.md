# Implementation Plan: Frontend Build — next.config.js:12 error

**Track ID:** ci-frontend-build-nextconfig_20260515
**Created:** 2026-05-15
**Status:** [ ] Not Started
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

- [ ] Task 1.1: Read `frontend/next.config.js` (or `.mjs`/`.ts` variant) lines 1-30
- [ ] Task 1.2: Pull the exact CI error message + stack from run `25929338762` (or rerun if expired)
- [ ] Task 1.3: Cross-reference line 12 against likely cause list

## Phase 2: Fix

- [ ] Task 2.1: Apply the targeted fix matching the diagnosis (env-var default, ESM rename, syntax cleanup, etc.)
- [ ] Task 2.2: Verify `npm run build` succeeds locally with the same Node version CI uses
- [ ] Task 2.3: Verify production bundle output unchanged (no behavior drift)

## Phase 3: Ship + verify

- [ ] Task 3.1: Commit + push, Frontend Build job turns green
- [ ] Task 3.2: Confirm Vercel deploy preview still builds successfully (parallel sanity check)

## Completion Criteria

- [ ] Frontend Build job green on main
- [ ] Vercel preview deployments still build (no regression)
- [ ] Root cause documented in execution.md

## Out of scope

- Migrating next.config to TypeScript
- Refactoring other Next.js config plumbing

## Related

- `ci-red-triage_20260515` — parent
- `ph-relaunch-jun2_20260515` — launch-blocked until CI fully green
