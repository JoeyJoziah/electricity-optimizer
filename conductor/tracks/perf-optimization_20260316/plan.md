# Implementation Plan: Performance Optimization

**Track ID:** perf-optimization_20260316
**Spec:** spec.md
**Created:** 2026-03-16
**Status:** [ ] Not Started

## Overview

9 optimizations in 3 phases: backend fixes, frontend fixes, verification. Each task is independently verifiable.

## Phase 1: Backend (5 tasks)

### Tasks

- [ ] 1.1: Fix `_check_memory` eviction no-op in `rate_limiter.py:243-245` — replace with `setdefault` pattern, add 10K-key periodic sweep
- [ ] 1.2: Add SQL aggregate for price trend in `price_repository.py` — ROW_NUMBER-based first/last third avg query matching Python logic
- [ ] 1.3: Refactor `analytics_service.py:get_price_trend()` to use new SQL aggregate instead of `get_historical_prices()`
- [ ] 1.4: Add Redis tier cache in `dependencies.py:require_tier()` — 30s TTL, in-memory fallback with same TTL
- [ ] 1.5: Reduce `MODERATION_TIMEOUT_SECONDS` from 30 to 5 in `community_service.py`

### Verification

- [ ] `.venv/bin/python -m pytest backend/tests/test_savings.py backend/tests/test_analytics_service.py backend/tests/test_community_service.py backend/tests/test_services.py -x` — all pass
- [ ] New test: SQL aggregate matches Python-side computation on sample data

## Phase 2: Frontend (4 tasks)

### Tasks

- [ ] 2.1: SSE partial-merge `setQueryData` in `useRealtime.ts:75-76` — merge `price_per_kwh`, `timestamp`, `is_peak` into existing cache entries
- [ ] 2.2: Audit + apply `React.memo` on prop-driven dashboard children in `DashboardTabs.tsx`
- [ ] 2.3: Add `min-height` + `contain: layout` on conditional banners in `DashboardContent.tsx:188-193`
- [ ] 2.4: Add `loading.tsx` per-route for 9 missing routes; add `refetchIntervalInBackground: false` to NotificationBell

### Verification

- [ ] `cd frontend && npx jest --passWithNoTests` — all pass
- [ ] `cd frontend && npx next build` — builds without errors

## Phase 3: Verification (LAST)

### Tasks

- [ ] 3.1: Run full backend test suite: `.venv/bin/python -m pytest backend/tests/ -x --tb=short`
- [ ] 3.2: Run full frontend test suite: `cd frontend && npx jest`
- [ ] 3.3: Verify no regressions in modified files, review git diff

## Done When

- [ ] All 9 acceptance criteria from spec.md verified
- [ ] Backend 2,478+ tests pass
- [ ] Frontend 1,835+ tests pass
- [ ] Git diff reviewed, no unintended changes
