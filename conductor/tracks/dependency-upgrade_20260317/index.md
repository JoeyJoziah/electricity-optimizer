# Track: Dependency Upgrade — Security Remediation & Major Version Bumps

**ID:** dependency-upgrade_20260317
**Status:** In Progress

## Documents

- [Specification](spec.md)
- [Implementation Plan](plan.md)
- [Full Plan (docs)](../../../docs/plans/2026-03-17-dependency-upgrade.md)

## Progress

- Phases: 3/4 complete
- Tasks: 14/18 complete

## Commits

| Phase | Commit | Tasks |
|-------|--------|-------|
| 1 | `7c1f8a5` | 0-4: jest 30, safe Python patches, safe frontend minors, httpx cap |
| 2+3 | `313b7da` | 5-14: Sentry v2, Stripe v14, Redis v7, dev tools, 6 frontend majors |

## Phases

| # | Phase | Tasks | Risk | Status |
|---|-------|-------|------|--------|
| 1 | Security Fixes + Safe Patches | 0-4 | Low | Complete |
| 2 | Medium-Risk Backend (Sentry, Stripe, Redis) | 5-8 | Medium | Complete |
| 3 | Frontend Major Versions | 9-14 | Medium | Complete |
| 4 | ML Stack (numpy, pandas) | 16-17 | High | In Progress |
| - | ESLint v10 | 15 | High | DEFERRED |

## Audit Summary

- **npm vulnerabilities**: 13 → 5 (0 HIGH, 5 MOD — all @excalidraw transitive)
- **pip-audit**: clean (no action needed)
- **Backend tests**: 2,662 passed (1 pre-existing encryption test excluded)
- **Frontend tests**: 2,024 passed (152 suites, 1 pre-existing FeedbackWidget failure)

## Quick Links

- [Back to Tracks](../../tracks.md)
- [Product Context](../../product.md)
