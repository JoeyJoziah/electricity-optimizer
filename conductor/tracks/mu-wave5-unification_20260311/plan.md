# Implementation Plan: Wave 5 — Unification

**Track ID:** mu-wave5-unification_20260311
**Spec:** spec.md
**Created:** 2026-03-11
**Status:** [ ] Not Started
**Execution Mode:** Loki RARV Cycles (Autonomous)
**Design Doc:** docs/plans/2026-03-11-multi-utility-expansion.md
**Blocked By:** mu-wave4-breadth_20260311

---

## Overview

Unify all 7 utility types into a single cohesive dashboard. Launch community features for engagement and crowdsourced data. Complete security hardening for the expanded multi-utility attack surface.

---

## Phase 1: Unified Multi-Utility Dashboard (MU-008)

### Tasks

- [ ] Task 1.1: Create combined savings calculation service
  - `backend/services/savings_aggregator.py`
  - Aggregate savings across all tracked utility accounts per user
  - "Total saved this month/year" metric
  - Per-utility breakdown with percentage contribution

- [ ] Task 1.2: Create spend breakdown API
  - `GET /api/v1/dashboard/overview` — combined savings + spend breakdown
  - `GET /api/v1/dashboard/breakdown` — per-utility spend data
  - `GET /api/v1/dashboard/trends` — multi-utility trend data for charts

- [ ] Task 1.3: Redesign dashboard frontend
  - `UnifiedDashboard` — main dashboard with utility tabs + combined view
  - `SavingsHero` — prominent total savings display
  - `SpendBreakdown` — pie chart by utility type
  - `TrendChart` — line chart with multi-utility overlay
  - `UtilityTabs` — switch between individual utility views
  - `CrossUtilitySuggestions` — "Switch gas to save $X, add solar to save $Y"

- [ ] Task 1.4: Create cross-utility optimization engine
  - Given all user utility accounts, identify top N savings opportunities
  - Rank by dollar impact across utility types
  - "You could save $47/mo by switching gas + adding community solar"

- [ ] Task 1.5: Write dashboard tests (savings calculation, breakdown accuracy, rendering)

### Verification
- [ ] Combined savings metric calculates correctly
- [ ] Spend breakdown pie chart renders with real data
- [ ] Cross-utility suggestions are actionable
- [ ] All tests pass

---

## Phase 2: Community Features (UG-004)

### Tasks

- [ ] Task 2.1: Create rate report crowdsourcing
  - Migration 044: `community_rate_reports` table (id, user_id, utility_type, region_id, reported_rate, rate_unit, provider_name, bill_date, verified, created_at)
  - `POST /api/v1/community/rate-report` — submit rate observation
  - Moderation: auto-flag outliers, manual review queue

- [ ] Task 2.2: Create neighborhood comparison
  - Aggregate community-reported rates by zip code
  - "Your electricity rate vs your neighborhood average"
  - Privacy: only show aggregates (min 5 reports to display)

- [ ] Task 2.3: Create social proof elements
  - "X users in [city] saved $Y this month"
  - Display on dashboard and landing pages
  - Source from actual user savings data (anonymized)

- [ ] Task 2.4: Create discussion/tips (lightweight)
  - Migration 045: `community_tips` table (id, user_id, utility_type, region_id, title, body, upvotes, created_at)
  - `GET /api/v1/community/tips` — browse tips by utility + region
  - `POST /api/v1/community/tips` — submit tip
  - `POST /api/v1/community/tips/{id}/upvote` — upvote
  - Rate limit: 5 tips/day per user

- [ ] Task 2.5: Create community frontend
  - `RateReportForm` — submit rate observation
  - `NeighborhoodComparison` — zip code comparison widget
  - `SocialProof` — savings counter on dashboard
  - `TipsSection` — browseable tips with upvoting
  - Page: `/community`

- [ ] Task 2.6: Write community tests

### Verification
- [ ] Rate reports submittable and aggregated
- [ ] Neighborhood comparison shows with >= 5 reports
- [ ] Social proof displays accurate anonymized data
- [ ] Tips browseable and upvotable
- [ ] All tests pass

---

## Phase 3: Security Hardening (OM-004)

### Tasks

- [ ] Task 3.1: OWASP Top 10 re-audit
  - Audit all new endpoints (gas, solar, CCA, oil, propane, water, community, affiliate)
  - Check: injection, auth, sensitive data exposure, XXE, access control, config, XSS, deserialization, components, logging
  - Document findings and fixes

- [ ] Task 3.2: API key rotation automation
  - Document rotation procedures for all 27+ API keys
  - Implement automated rotation for EIA API key (if supported)
  - Alert on API key age (> 90 days without rotation)

- [ ] Task 3.3: Encrypted credential storage audit
  - Verify AES-256-GCM encryption for portal scraper credentials
  - Verify community rate reports don't leak PII
  - Verify affiliate tracking doesn't expose user identity

- [ ] Task 3.4: Dependency vulnerability scanning
  - `pip-audit` + `npm audit` in CI pipeline
  - Block deployment on critical/high vulnerabilities
  - Dependabot alerts reviewed and addressed

- [ ] Task 3.5: Write security tests (auth on new endpoints, input validation, XSS prevention)

### Verification
- [ ] Zero critical/high OWASP findings
- [ ] Key rotation documented for all API keys
- [ ] Dependency scan clean (no critical/high)
- [ ] All tests pass

---

## Phase 4: Final Validation & "US Uswitch" Launch Readiness

### Tasks

- [ ] Task 4.1: Run full test suite (all utilities, all features)
- [ ] Task 4.2: Deploy migrations 044-045
- [ ] Task 4.3: Performance benchmark (page load, API response times)
- [ ] Task 4.4: Verify all 7 utility types functional end-to-end
- [ ] Task 4.5: Update CONTINUITY.md — Wave 5 complete, "US Uswitch" MVP
- [ ] Task 4.6: Update DSP graph (final entity count)
- [ ] Task 4.7: Generate multi-utility expansion completion report

### Verification
- [ ] All tests pass
- [ ] Unified dashboard shows all utility types
- [ ] Community features live
- [ ] Security hardening complete
- [ ] Multi-utility platform is feature-complete for Waves 0-5
- [ ] Ready for Wave 6+ (deferred: API, white-label, enterprise)

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
