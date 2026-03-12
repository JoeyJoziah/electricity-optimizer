# Implementation Plan: Wave 4 — Breadth

**Track ID:** mu-wave4-breadth_20260311
**Spec:** spec.md
**Created:** 2026-03-11
**Status:** [~] In Progress (Phases 1-2 complete)
**Execution Mode:** Loki RARV Cycles (Autonomous)
**Design Doc:** docs/plans/2026-03-11-multi-utility-expansion.md
**Blocked By:** mu-wave3-depth_20260311

---

## Overview

Complete utility type coverage with propane (EIA regional averages) and water (municipal rate benchmarking, monitoring only). Launch premium analytics for Pro/Business revenue. Evolve CI/CD to support multi-utility test matrix.

---

## Phase 1: Propane Market Tracking (MU-005)

### Tasks

- [x] Task 1.1: EIA propane client (pre-existing in `eia.py` — PROPANE_SERIES + PROPANE_STATE_SERIES)
- [x] Task 1.2: Propane data pipeline (`POST /internal/fetch-propane` + GHA `fetch-heating-oil.yml` extended)
- [x] Task 1.3: Propane API endpoints (4 endpoints: prices, history, compare, timing)
- [x] Task 1.4: Propane frontend (PropaneDashboard, PropanePriceHistory, FillUpTiming, /propane page, sidebar nav)
- [x] Task 1.5: Propane wired into rate change alerting (propane in detection loop, 5% threshold, 30d lookback)
- [x] Task 1.6: Propane tests (16 backend + 22 frontend = 38 tests)
- [x] Task 1.7: SEO — propane added to UTILITY_TYPES for ISR /rates/[state]/propane pages
- [x] Task 1.8: Migration 046 (propane_prices) deployed to Neon production

### Verification
- [x] Weekly propane prices flowing from EIA
- [x] Regional prices display with trends + seasonal fill-up timing
- [x] Rate change alerting configured (5% threshold)
- [x] All tests pass (126 frontend suites / 1,737 tests, 16 backend propane tests)

---

## Phase 2: Water Rate Benchmarking (MU-006)

### Tasks

- [x] Task 2.1: Create water rate database
  - Migration 047: `water_rates` table (id UUID, municipality, state, rate_tiers JSONB, base_charge, unit, effective_date, source_url, created_at, updated_at, UNIQUE(municipality, state))
  - Deployed to Neon production
  - Initial data: table ready for curation of top 50 US metros (manual + Diffbot)

- [x] Task 2.2: Create water benchmarking service
  - `backend/services/water_rate_service.py` — WaterRateService with 6 methods
  - Tier calculator: incremental tier application (limit_gallons + rate_per_gallon)
  - Regional benchmark: avg/min/max monthly cost across municipalities in a state
  - Conservation tips: 8 static tips (Indoor/Outdoor/Monitoring categories)
  - AVG_MONTHLY_GALLONS = 5760 (EPA/USGS reference)

- [x] Task 2.3: Create water API endpoints
  - `GET /api/v1/rates/water` — list rates, filter by state/municipality
  - `GET /api/v1/rates/water/benchmark` — regional comparison with usage_gallons param
  - `GET /api/v1/rates/water/tips` — conservation recommendations with savings totals
  - No "switch" CTA (monopoly — Decision D4)

- [x] Task 2.4: Create water frontend
  - `WaterDashboard` — state selector, info banner, cyan theme
  - `WaterRateBenchmark` — avg/min/max cards, municipality breakdown sorted by cost
  - `WaterTierCalculator` — municipality selector + usage input, tiered cost breakdown
  - `ConservationTips` — grouped by category, difficulty badges, savings estimates
  - Page: `/water` with metadata
  - Sidebar: Water nav item with Waves icon
  - SEO: water added to UTILITY_TYPES for ISR /rates/[state]/water pages

- [x] Task 2.5: Write water tests (17 backend + 22 frontend = 39 tests)

### Verification
- [x] Water rates table deployed (empty — awaiting curation)
- [x] Benchmark comparison displays correctly
- [x] No "switch" CTA present (monitoring only)
- [x] All tests pass (130 frontend suites / 1,759 tests, 17 backend water tests)

---

## Phase 3: Premium Analytics (REV-002)

### Tasks

- [ ] Task 3.1: Create advanced rate forecasting (Pro tier)
  - Extend existing ML pipeline with utility-type parameter
  - Electricity forecasting: existing model (already built)
  - Gas/oil/propane: simple trend extrapolation (no ML until 6+ months data — Decision D9)
  - `GET /api/v1/forecast/{utility_type}` — Pro tier gated

- [ ] Task 3.2: Create multi-utility spend optimization report (Business tier)
  - Aggregate spend across all tracked utilities
  - Identify top savings opportunities ranked by dollar impact
  - Generate PDF report (or HTML email)
  - `GET /api/v1/reports/optimization` — Business tier gated

- [ ] Task 3.3: Create historical rate data export (Business tier)
  - CSV/JSON export of rate history per utility type
  - Date range filter
  - `GET /api/v1/export/rates` — Business tier gated

- [ ] Task 3.4: Create premium analytics frontend
  - `ForecastWidget` — rate prediction charts (Pro)
  - `OptimizationReport` — savings opportunity dashboard (Business)
  - `DataExport` — export controls (Business)
  - Gate UI elements by tier (show upgrade CTA for Free/Pro)

- [ ] Task 3.5: Write premium analytics tests (tier gating, report generation, export)

### Verification
- [ ] Forecasting works for electricity (ML) and others (trend)
- [ ] Optimization report generates correct recommendations
- [ ] Export produces valid CSV/JSON
- [ ] Tier gating enforced correctly
- [ ] All tests pass

---

## Phase 4: CI/CD Evolution (OM-005)

### Tasks

- [ ] Task 4.1: Create utility-type test matrix
  - GitHub Actions matrix strategy: run integration tests per utility type
  - Parallel execution: electricity, gas, oil, propane, solar, water
  - Shared fixtures with utility_type parameterization

- [ ] Task 4.2: Implement feature flag system
  - Simple feature flags via environment variables per utility type
  - `FEATURE_GAS_ENABLED=true`, `FEATURE_SOLAR_ENABLED=true`, etc.
  - Frontend: conditional rendering based on feature flags
  - Backend: endpoint availability based on feature flags

- [ ] Task 4.3: Create deployment canary documentation
  - Document canary deployment strategy for utility-specific changes
  - Define rollback criteria per utility type
  - Don't implement full canary yet — document for Wave 5+

- [ ] Task 4.4: Write CI/CD tests (matrix execution, feature flag behavior)

### Verification
- [ ] Test matrix runs per utility type in CI
- [ ] Feature flags control utility visibility
- [ ] All tests pass

---

## Phase 5: Final Validation

### Tasks

- [ ] Task 5.1: Run full test suite
- [ ] Task 5.2: Deploy migration 043
- [ ] Task 5.3: Verify all 7 utility types represented in platform
- [ ] Task 5.4: Verify premium analytics generating reports
- [ ] Task 5.5: Update CONTINUITY.md and DSP graph

### Verification
- [ ] All tests pass
- [ ] All utility types live: electricity, gas, heating oil, propane, community solar, CCA, water
- [ ] Premium analytics functional
- [ ] Wave 5 unblocked

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
