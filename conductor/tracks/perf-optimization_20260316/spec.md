# Specification: Performance Optimization — Brainstorm-Validated

**Track ID:** perf-optimization_20260316
**Type:** Refactor
**Created:** 2026-03-16
**Status:** Approved

## Summary

Implement 9 performance optimizations across backend, frontend, and infrastructure, validated through multi-agent brainstorming (Skeptic, Constraint Guardian, User Advocate, Integrator/Arbiter).

## Context

Profiling by 3 parallel agents identified 60+ findings across backend (20), frontend (20+), and infrastructure (10). The multi-agent brainstorming process approved 9 items and deferred 1 (cache stampede — theoretical at current scale).

## Acceptance Criteria

- [ ] `require_tier()` no longer queries DB on every tier-gated request (Redis cache + webhook invalidation)
- [ ] SSE price events use partial-merge `setQueryData` instead of `invalidateQueries`
- [ ] `get_price_trend()` uses SQL aggregate instead of 5,000-row Python fetch
- [ ] `_check_memory` eviction bug fixed with `setdefault` + periodic sweep
- [ ] AI moderation timeout reduced from 30s to 5s (keep inline await)
- [ ] Dashboard children wrapped in `React.memo` where prop-driven (audited)
- [ ] CLS fixed on conditional banners with `min-height` + `contain: layout`
- [ ] `loading.tsx` added per-route for 9 missing routes
- [ ] NotificationBell uses `refetchIntervalInBackground: false`
- [ ] All existing tests pass after changes
- [ ] New tests added for SQL aggregate and tier caching

## Dependencies

- Stripe webhook handler (`apply_webhook_action`) must be updated for tier cache invalidation
- `price_repository.py` needs new SQL aggregate method

## Out of Scope

- Cache stampede backoff (deferred — theoretical at current scale)
- Infrastructure tier upgrades (no Gunicorn worker count changes, no Redis pool increases)
- New backend batch endpoints for frontend request consolidation

## Technical Notes

- Single Gunicorn worker (512MB) — no `asyncio.create_task` for long-running background work
- Redis max_connections=10 shared across rate limiting, caching, tier caching
- Neon pool_size=3 — SQL aggregate reduces connection hold time vs 5K-row fetch
