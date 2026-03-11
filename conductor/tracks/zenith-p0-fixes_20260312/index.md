# Track: Zenith P0 — Production Safety Fixes

**ID:** zenith-p0-fixes_20260312
**Status:** Pending
**Type:** Bug Fix / Security Hardening
**Origin:** Project Zenith audit findings (H-15-01, H-16-02, H-14-01)

## Documents

- [Specification](spec.md) — Requirements and context for each fix
- [Implementation Plan](plan.md) — Step-by-step execution plan with TDD

## Scope

3 production safety fixes identified as P0 in the Project Zenith audit:

| # | Fix | Section | Finding ID | Risk |
|---|-----|---------|------------|------|
| 1 | Reduce session cache TTL / add ban-propagation | Security | H-15-01 | Banned user access for up to 5 minutes |
| 2 | Add circuit breaker for backend API clients | Integrations | H-16-02 | Failing APIs get hammered until timeout |
| 3 | Scope `git add` in CI auto-format | CI/CD | H-14-01 | Untracked files accidentally committed |

## Progress

- Phases: 0/3 complete
- Tasks: 0/9 complete

## Quick Links

- [Back to Tracks](../../tracks.md)
- [Product Context](../../product.md)
- [Zenith Summary](../codebase-zenith_20260311/SUMMARY.md)
