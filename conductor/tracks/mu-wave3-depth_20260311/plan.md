# Implementation Plan: Wave 3 — Depth

**Track ID:** mu-wave3-depth_20260311
**Spec:** spec.md
**Created:** 2026-03-11
**Status:** [ ] Not Started
**Execution Mode:** Loki RARV Cycles (Autonomous)
**Design Doc:** docs/plans/2026-03-11-multi-utility-expansion.md
**Blocked By:** mu-wave2-first-expansion_20260311

---

## Overview

Deepen platform coverage: CCA transparency, heating oil tracking, proactive rate change alerting across all utilities. Begin revenue generation with affiliate links. Launch programmatic SEO for organic growth. Scalability preparation for growing data volume.

---

## Phase 1: CCA Detection & Transparency (MU-003b)

### Tasks

- [ ] Task 1.1: Build CCA program database
  - Migration 041: `cca_programs` table (id, state, municipality, program_name, provider, generation_mix, rate_vs_default_pct, opt_out_url, updated_at)
  - Seed data for 10 CCA states (CA, MA, NY, NJ, IL, OH, NH, VA, RI, CO)
  - Municipality-level granularity (zip code -> CCA lookup)

- [ ] Task 1.2: Create CCA detection service
  - `backend/services/cca_service.py`
  - `detect_cca(zip_code, municipality)` -> CCA program or None
  - `compare_cca_rate(cca_id, default_utility_rate)` -> savings/cost difference
  - `get_opt_out_info(cca_id)` -> opt-out process details

- [ ] Task 1.3: Create CCA API endpoints
  - `GET /api/v1/cca/detect` — check if user is in a CCA
  - `GET /api/v1/cca/compare/{cca_id}` — CCA vs default rate comparison
  - `GET /api/v1/cca/info/{cca_id}` — program details + opt-out info

- [ ] Task 1.4: Create CCA frontend components
  - `CCAAlert` — "You're in a CCA" banner on dashboard
  - `CCAComparison` — rate comparison visualization
  - `CCAInfo` — program details, generation mix, opt-out guidance
  - Wire into main dashboard as contextual notification

- [ ] Task 1.5: Write CCA tests (detection accuracy, rate comparison, opt-out info)

### Verification
- [ ] CCA detection works for all 10 seeded states
- [ ] Rate comparison shows correct savings/cost
- [ ] All tests pass

---

## Phase 2: Heating Oil Price Tracking (MU-004)

### Tasks

- [ ] Task 2.1: Create EIA heating oil API client
  - `backend/integrations/eia_heating_oil.py`
  - Weekly Petroleum Status Report endpoint
  - PADD (Petroleum Administration for Defense District) to state mapping
  - Price unit: $/gallon

- [ ] Task 2.2: Create heating oil data pipeline
  - Fetch weekly prices -> normalize to per-state -> store in utility_rates
  - Wire into cron: new `fetch-heating-oil.yml` (weekly Monday)

- [ ] Task 2.3: Create dealer directory (lightweight)
  - Store known heating oil dealers by region
  - Source: manual curation of top dealers in Northeast corridor (primary heating oil market)
  - No automated scraping (Decision D12 scope limit)

- [ ] Task 2.4: Create heating oil API endpoints
  - `GET /api/v1/rates/heating-oil` — regional prices
  - `GET /api/v1/rates/heating-oil/history` — price trends
  - `GET /api/v1/rates/heating-oil/dealers` — local dealers

- [ ] Task 2.5: Create heating oil frontend
  - `HeatingOilDashboard` — price display, regional breakdown
  - `OilPriceHistory` — trend chart
  - `DealerList` — local dealer directory
  - Page: `/heating-oil`

- [ ] Task 2.6: Write heating oil tests

### Verification
- [ ] Weekly EIA heating oil data flowing
- [ ] Regional prices display correctly
- [ ] All tests pass

---

## Phase 3: Proactive Rate Change Alerting (MU-007)

### Tasks

- [ ] Task 3.1: Create rate change detection engine
  - `backend/services/rate_change_detector.py`
  - Compare current scrape/fetch vs previous for each utility type + region
  - Configurable threshold: alert on > X% change or absolute change > $Y
  - Track direction (increase vs decrease)

- [ ] Task 3.2: Implement utility-specific alert cadences
  - Electricity: check every 30 min (existing check-alerts.yml)
  - Natural gas: weekly digest (new gas-alerts cron)
  - Heating oil: weekly digest (combined with gas)
  - Propane: bi-weekly digest (Wave 4, but build framework now)
  - Community solar: monthly digest

- [ ] Task 3.3: Create "better deal found" recommendations
  - When rate change detected in user's region, check if cheaper alternative exists
  - Generate recommendation: "Gas rates increased 8% — [Supplier X] is now $0.12/therm cheaper"
  - Store recommendations for display in alert center

- [ ] Task 3.4: Create alert preferences per utility
  - Extend user preferences: per-utility alert opt-in/out
  - Channel preferences: push, email, in-app per utility type
  - Cadence preferences: real-time, daily digest, weekly digest

- [ ] Task 3.5: Create alert frontend
  - `AlertCenter` — unified notification center across all utilities
  - `AlertPreferences` — per-utility opt-in/channel/cadence controls
  - `RateChangeCard` — individual alert with recommendation CTA
  - Extend existing `/alerts` page

- [ ] Task 3.6: Write alerting tests (detection, cadences, recommendations, preferences)

### Verification
- [ ] Rate changes detected within cadence window per utility
- [ ] Recommendations generated with correct supplier suggestions
- [ ] Alert preferences respected (no unwanted notifications)
- [ ] All tests pass

---

## Phase 4: SEO & Content Engine (UG-002)

### Tasks

- [ ] Task 4.1: Create programmatic SEO pages
  - Dynamic routes: `/rates/[state]/[utility-type]` (e.g., `/rates/texas/electricity`)
  - ISR (Incremental Static Regeneration) for rate data freshness
  - 50 states x 6 utility types = up to 300 landing pages

- [ ] Task 4.2: Create rate comparison content
  - Auto-generated city-level pages: `/rates/[state]/[city]/[utility-type]`
  - "Best electricity rates in Houston, TX" template
  - Include current rates, historical trend, top suppliers

- [ ] Task 4.3: Add structured data markup
  - Schema.org Product/Offer for rate listings
  - BreadcrumbList for navigation
  - FAQ schema for common questions per state

- [ ] Task 4.4: Create sitemap generation
  - Dynamic sitemap for all rate pages
  - Update frequency based on utility type (electricity: daily, gas: weekly, etc.)

- [ ] Task 4.5: Write SEO tests (page rendering, structured data, sitemap)

### Verification
- [ ] Landing pages render with SSR/ISR
- [ ] Structured data validates in Google Rich Results Test
- [ ] Sitemap includes all dynamic routes
- [ ] All tests pass

---

## Phase 5: Affiliate Revenue (REV-001)

### Tasks

- [ ] Task 5.1: Create affiliate link system
  - `backend/services/affiliate_service.py`
  - Generate tracked affiliate URLs for supplier switch CTAs
  - Partner integration: Choose Energy, EnergySage (research partner programs)
  - Click tracking with attribution (user_id, utility_type, supplier, timestamp)

- [ ] Task 5.2: Create affiliate tracking table
  - Migration 042: `affiliate_clicks` (id, user_id, supplier_id, utility_type, clicked_at, converted, commission)
  - Revenue reporting endpoints (internal)

- [ ] Task 5.3: Add FTC disclosure
  - "We may earn a commission when you switch" disclosure on comparison pages
  - Disclosure component positioned per FTC guidelines

- [ ] Task 5.4: Update switch CTAs with affiliate links
  - Replace direct supplier links with tracked affiliate URLs
  - Maintain user trust: always show actual rates, not affiliate-optimized ordering

- [ ] Task 5.5: Write affiliate tests (tracking, attribution, disclosure rendering)

### Verification
- [ ] Affiliate clicks tracked with attribution
- [ ] FTC disclosure visible on all comparison pages
- [ ] Supplier ordering not influenced by affiliate status (trust)
- [ ] All tests pass

---

## Phase 6: Scalability Preparation (OM-003)

### Tasks

- [ ] Task 6.1: Document database sharding strategy
  - Evaluate sharding by region vs utility_type vs time
  - Recommend: time-based partitioning for utility_rates (most effective)
  - Document decision, don't implement yet

- [ ] Task 6.2: Evaluate read replica need
  - Profile current query load
  - Identify read-heavy vs write-heavy patterns
  - Document Neon read replica setup process for future

- [ ] Task 6.3: Optimize connection pooling
  - Review asyncpg pool settings for increased load
  - Test with simulated multi-utility query patterns
  - Tune `statement_cache_size=0` and pool size

- [ ] Task 6.4: CDN optimization for rate data
  - Static rate pages via Vercel ISR (already planned in SEO)
  - CF Worker cache tuning for multi-utility API responses
  - Cache key strategy: include utility_type in cache keys

### Verification
- [ ] Sharding strategy documented
- [ ] Connection pool tested under simulated load
- [ ] Cache keys include utility_type
- [ ] All tests pass

---

## Phase 7: Final Validation

### Tasks

- [ ] Task 7.1: Run full test suite (all new + existing)
- [ ] Task 7.2: Deploy migrations 041-042
- [ ] Task 7.3: Verify data pipelines running on schedule
- [ ] Task 7.4: Verify affiliate tracking functional
- [ ] Task 7.5: Update CONTINUITY.md and DSP graph

### Verification
- [ ] All tests pass
- [ ] CCA, heating oil, alerting, SEO, affiliate all live
- [ ] Wave 4 unblocked

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
