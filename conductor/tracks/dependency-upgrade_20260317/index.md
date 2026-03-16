# Track: Dependency Upgrade — Security Remediation & Major Version Bumps

**ID:** dependency-upgrade_20260317
**Status:** Planned

## Documents

- [Specification](spec.md)
- [Implementation Plan](plan.md)
- [Full Plan (docs)](../../../docs/plans/2026-03-17-dependency-upgrade.md)

## Progress

- Phases: 0/4 complete
- Tasks: 0/18 complete

## Phases

| # | Phase | Tasks | Risk | Status |
|---|-------|-------|------|--------|
| 1 | Security Fixes + Safe Patches | 0-4 | Low | Pending |
| 2 | Medium-Risk Backend (Sentry, Stripe, Redis) | 5-8 | Medium | Pending |
| 3 | Frontend Major Versions | 9-14 | Medium | Pending |
| 4 | ML Stack (numpy, pandas) | 16-17 | High | Pending |
| - | ESLint v10 | 15 | High | DEFERRED |

## Audit Summary

- **npm vulnerabilities**: 13 (3 HIGH, 6 MOD, 4 LOW) → target: 6 (devDep only)
- **pip-audit**: clean (no action needed)
- **Outdated Python**: 73 packages
- **Outdated npm**: 16 packages

## Quick Links

- [Back to Tracks](../../tracks.md)
- [Product Context](../../product.md)
