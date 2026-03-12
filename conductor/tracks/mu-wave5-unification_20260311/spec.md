# Specification: Wave 5 — Unified Dashboard, Community & Security Hardening

**Track ID:** mu-wave5-unification_20260311
**Type:** Feature
**Created:** 2026-03-11
**Status:** Pending

## Summary

Unify all utility types into a tabbed dashboard with combined savings metrics, launch community features (crowdsourcing, neighborhood comparisons, social proof, discussion forums) with AI auto-moderation, and complete security hardening for the expanded multi-utility attack surface.

## Context

Waves 0-4 established per-utility backends, frontends, and feature flags for 7 utility types (electricity, natural gas, heating oil, propane, community solar, water + cross-cutting forecast/export). Wave 5 ties them together into a cohesive multi-utility experience and adds community engagement.

## Design Decisions (from Brainstorming)

| # | Decision | Alternatives Considered | Rationale |
|---|----------|------------------------|-----------|
| D1 | Tabbed dashboard redesign | Replace existing / New separate page | Preserves existing electricity UX as a tab, adds "All Utilities" as default combined view |
| D2 | Full community (all 4 features) | Social proof only / Crowdsourcing + social proof | User wants complete community experience from launch |
| D3 | AI auto-mod (fail-closed) + report button | Pre-moderation queue / Post-moderation | Cost-effective, leverages existing Groq agent (primary) with Gemini fallback, fail-closed with 30s timeout auto-unhide |
| D4 | Automated scanning + light manual review | Automated only / Full external pentest | Balances thoroughness with timeline; external pentest deferred |
| D5 | All monitored utilities in savings | Switchable only / User-configured | Water saves via conservation, oil via timing — all utilities contribute meaningfully |
| D6 | Low scale (< 1K posts in 3 months) | Medium / High | Early adopter phase, simple pagination sufficient, no denormalized counters |
| D7 | Frontend-First Composition (Approach A) | Backend aggregation / BFF pattern | Simplest path — dashboard composes existing hooks client-side, new backend only for community + combined savings |

## Assumptions

1. Each utility type's existing API hooks can be composed into a combined view without new backend aggregation endpoints (except combined savings)
2. Simple community schema — `community_posts`, `community_votes`, `community_reports` tables with flat structure, no threading
3. Existing `optimization_report_service.py` can be extended for combined savings
4. AI moderation uses Groq (primary, dedicated `classify_content()` non-streaming method) with Gemini fallback; fail-closed with 30s timeout auto-unhide; retroactive re-moderation on service recovery
5. Security: OWASP ZAP + Dependabot + pip-audit + manual auth/encryption/key rotation review
6. Community posts scoped by state (VARCHAR(50) matching existing Region enum values) + per-utility type (CHECK constraint)
7. Low volume: no caching, no denormalized counters, simple offset pagination
8. Neighborhood comparison requires minimum 5 users in a region to display

## Problem Description

### 1. Dashboard Fragmentation

Users currently see only an electricity-focused dashboard. There is no unified view showing combined savings, cross-utility spend breakdown, or easy switching between utility types. Users with multiple tracked utilities must navigate to separate pages.

### 2. No Community Engagement

No mechanism for users to share rate observations, tips, or compare with neighbors. All data is system-sourced (scrapers, APIs). Crowdsourced data would improve coverage and trust, especially in areas with sparse automated data.

### 3. Expanded Attack Surface

Waves 1-4 added 6 new utility types, portal scraping with encrypted credentials, affiliate tracking, and email import — each expanding the security surface. A systematic re-audit is needed.

## Acceptance Criteria

### Dashboard
- [ ] Tabbed layout: "All Utilities" (default) + one tab per active utility type
- [ ] Tabs are deep-linkable via URL search param (`?tab=electricity`)
- [ ] Smart default: single-utility users land on their utility tab; 2+ utilities default to "All Utilities"
- [ ] "All Utilities" tab shows combined savings card + per-utility summary cards
- [ ] Each utility tab loads independently (loading/error states per card)
- [ ] Feature flags hide tabs for disabled utility types
- [ ] Mobile: horizontal scroll on tab bar with gradient fade affordance on edges
- [ ] Combined savings endpoint returns total + per-utility breakdown + percentile rank

### Community
- [ ] Community posts CRUD (create, list with pagination, vote, report)
- [ ] 4 post types: tip, rate_report, discussion, review
- [ ] AI auto-moderation on post creation (fail-closed: hold until classified or 30s timeout auto-unhide)
- [ ] Posts hidden after 5 unique user reports (deduplicated via community_reports table)
- [ ] Flagged posts show edit/resubmit flow for authors
- [ ] Rate crowdsourcing via `rate_per_unit` + `rate_unit` + `supplier_name` fields
- [ ] Community stats endpoint (total users, avg savings, top tip) with attribution: "Based on X users in [state] reporting since [date]"
- [ ] Rate limits: 10 posts/hour, 50 votes/hour per user
- [ ] XSS prevention via nh3 sanitization on title/body (Rust-based, actively maintained replacement for deprecated bleach)

### Neighborhood Comparison
- [ ] Percentile rank: "You pay more than X% of users in your state"
- [ ] Comparison returns null when fewer than 5 users in region (with friendly empty state: "We need a few more neighbors...")
- [ ] Percentile includes context: "You pay $X.XX/kWh vs. state average $Y.YY/kWh"
- [ ] Works per utility type using existing price data

### Security
- [ ] OWASP ZAP baseline scan in CI (GitHub Action, weekly cron only — against Render directly, not CF Worker)
- [ ] `pip-audit` gate in backend CI
- [ ] `npm audit --audit-level=high` gate in frontend CI
- [ ] Manual review checklist completed (auth flows, portal encryption, key rotation)
- [ ] Zero critical/high vulnerabilities
- [ ] Community endpoints XSS-safe and rate-limited

### Testing
- [ ] ~95-100 new tests total across backend + frontend
- [ ] 2-3 Playwright E2E tests for critical flows
- [ ] All existing tests continue passing (2,032 backend + 1,475 frontend)

## Dependencies

- Wave 4 must be complete (all utility types + feature flags live)
- Existing feature flag system (migration 016 + 048)
- Existing agent service (Gemini/Groq) for AI moderation
- Existing `optimization_report_service.py` for savings calculation base

## Out of Scope

- Threaded comments / reply chains
- Real-time WebSocket updates for community
- User profiles / reputation system
- Community moderation admin panel (Phase 2 if needed)
- External penetration test (deferred to post-launch)
- High-scale patterns (caching, denormalized counters, cursor pagination)
- Cross-utility recommendations ("switch gas provider") — deferred

## Technical Notes

### Migration Number
Next available: 049 (after 048_utility_feature_flags.sql)
Creates 3 tables: `community_posts`, `community_votes`, `community_reports` (42 → 45 tables total)

### Moderation Prompt (Groq)
Dedicated `classify_content()` method in agent_service.py (non-streaming). Input: title + body. Output: `{"verdict": "safe"|"flagged", "reason": "..."}`. Fail-closed: post held with `is_pending_moderation=true` until classified or 30s timeout auto-unhides. Retroactive re-moderation on service recovery for posts that timed out.

### New Backend Files
- `backend/services/community_service.py` — CRUD, moderation (Groq primary + Gemini fallback, fail-closed), stats
- `backend/services/savings_aggregator.py` — combined savings calculation
- `backend/services/neighborhood_service.py` — comparison logic
- `backend/api/v1/community.py` — community routes
- `backend/api/v1/savings.py` — extend existing savings router (check for conflict with existing file)
- `backend/tests/test_community_service.py`
- `backend/tests/test_savings_aggregator.py`
- `backend/tests/test_neighborhood_service.py`
- `backend/tests/test_community_api.py`

### New Frontend Files
- `frontend/components/dashboard/DashboardTabs.tsx`
- `frontend/components/dashboard/AllUtilitiesTab.tsx`
- `frontend/components/dashboard/UtilityTabShell.tsx`
- `frontend/components/dashboard/CombinedSavingsCard.tsx`
- `frontend/components/dashboard/NeighborhoodCard.tsx`
- `frontend/components/community/PostList.tsx`
- `frontend/components/community/PostForm.tsx`
- `frontend/components/community/VoteButton.tsx`
- `frontend/components/community/CommunityStats.tsx`
- `frontend/app/community/page.tsx`
- `frontend/lib/api/community.ts`

### CI Files
- `.github/workflows/owasp-zap.yml` — ZAP scan workflow
- `.zap/rules.tsv` — false positive suppressions

---

_Generated by Conductor from brainstorming session design review._
