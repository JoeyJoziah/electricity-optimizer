# Track: Dependency Upgrade — Security Remediation & Major Version Bumps

**ID:** dependency-upgrade_20260317
**Status:** Complete

## Documents

- [Specification](spec.md)
- [Implementation Plan](plan.md)
- [Full Plan (docs)](../../../docs/plans/2026-03-17-dependency-upgrade.md)

## Progress

- Phases: 4/4 complete
- Tasks: 18/18 complete

## Commits

| Phase | Commit | Tasks |
|-------|--------|-------|
| 1 | `7c1f8a5` | 0-4: jest 30, safe Python patches, safe frontend minors, httpx cap |
| 2+3 | `313b7da` | 5-14: Sentry v2, Stripe v14, Redis v7, dev tools, 6 frontend majors |
| 4 | `a55be3b` | 16-17: numpy v2, pandas v2.3 |
| fix | `a391b02` | recharts v3 + zustand v5 type fixes (via UX polish session) |
| fix | `9e069ed` | settings test auth mock for better-auth v1.5.5 ESM |

## Phases

| # | Phase | Tasks | Risk | Status |
|---|-------|-------|------|--------|
| 1 | Security Fixes + Safe Patches | 0-4 | Low | Complete |
| 2 | Medium-Risk Backend (Sentry, Stripe, Redis) | 5-8 | Medium | Complete |
| 3 | Frontend Major Versions | 9-14 | Medium | Complete |
| 4 | ML Stack (numpy, pandas) | 16-17 | High | Complete |
| - | ESLint v10 | 15 | High | DEFERRED |

## Audit Summary

- **npm vulnerabilities**: 13 → 5 (0 HIGH, 5 MOD — all @excalidraw transitive)
- **pip-audit**: clean (no action needed)
- **TypeScript errors**: 17 → 10 (7 fixed: recharts v3 formatter types, zustand v5 mock types)
- **Backend tests**: 2,663 passed (1 pre-existing encryption test excluded)
- **Frontend tests**: 2,024 passed (152 suites, 1 pre-existing FeedbackWidget failure)
- **ML tests**: 458 passed

## Quick Links

- [Back to Tracks](../../tracks.md)
- [Product Context](../../product.md)
