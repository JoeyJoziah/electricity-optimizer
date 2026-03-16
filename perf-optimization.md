# Performance Optimization

## Goal
Implement 9 brainstorm-validated performance fixes across backend and frontend.

## Tasks
- [ ] Fix `_check_memory` eviction no-op in `rate_limiter.py:243` -> Verify: pytest test_savings.py passes
- [ ] Add SQL aggregate for price trend in `price_repository.py` -> Verify: new test matches Python logic
- [ ] Refactor `get_price_trend()` to use SQL aggregate -> Verify: test_analytics_service.py passes
- [ ] Cache `require_tier()` in Redis (30s TTL) + webhook invalidation -> Verify: test_services.py passes
- [ ] Reduce moderation timeout 30s->5s in `community_service.py` -> Verify: test_community_service.py passes
- [ ] SSE partial-merge setQueryData in `useRealtime.ts` -> Verify: frontend build succeeds
- [ ] React.memo on prop-driven dashboard children -> Verify: frontend tests pass
- [ ] CLS fix + loading.tsx for 9 routes + NotificationBell fix -> Verify: next build + jest pass
- [ ] Full test suite verification -> Verify: backend 2478+ tests, frontend 1835+ tests all pass

## Done When
- [ ] All tests pass with fresh runs (verification-before-completion: no claims without evidence)
