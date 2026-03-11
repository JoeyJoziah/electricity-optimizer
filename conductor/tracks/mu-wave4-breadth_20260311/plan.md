# Implementation Plan: Wave 4 — Breadth

**Track ID:** mu-wave4-breadth_20260311
**Spec:** spec.md
**Created:** 2026-03-11
**Status:** [ ] Not Started
**Execution Mode:** Loki RARV Cycles (Autonomous)
**Design Doc:** docs/plans/2026-03-11-multi-utility-expansion.md
**Blocked By:** mu-wave3-depth_20260311

---

## Overview

Complete utility type coverage with propane (EIA regional averages) and water (municipal rate benchmarking, monitoring only). Launch premium analytics for Pro/Business revenue. Evolve CI/CD to support multi-utility test matrix.

---

## Phase 1: Propane Market Tracking (MU-005)

### Tasks

- [ ] Task 1.1: Create EIA propane API client
  - `backend/integrations/eia_propane.py`
  - Weekly propane price data (wholesale/retail by PADD region)
  - PADD -> state mapping (reuse from heating oil)
  - Price unit: $/gallon

- [ ] Task 1.2: Create propane data pipeline
  - Fetch weekly -> normalize to state -> store in utility_rates (utility_type=PROPANE)
  - Cron: extend `fetch-heating-oil.yml` to also fetch propane (same EIA session)

- [ ] Task 1.3: Create propane API endpoints
  - `GET /api/v1/rates/propane` — regional prices
  - `GET /api/v1/rates/propane/history` — price trends
  - No supplier comparison (Decision D12: no dealer API)

- [ ] Task 1.4: Create propane frontend
  - `PropaneDashboard` — price display, regional map
  - `PropaneTrends` — historical price chart
  - "Best fill-up timing" suggestions based on seasonal patterns
  - Page: `/propane`

- [ ] Task 1.5: Wire propane into rate change alerting (bi-weekly cadence from MU-007)

- [ ] Task 1.6: Write propane tests

### Verification
- [ ] Weekly propane prices flowing from EIA
- [ ] Regional prices display with trends
- [ ] Bi-weekly alerts configured
- [ ] All tests pass

---

## Phase 2: Water Rate Benchmarking (MU-006)

### Tasks

- [ ] Task 2.1: Create water rate database
  - Migration 043: `water_rates` table (id, municipality, state, rate_tiers JSONB, base_charge, unit, effective_date, source_url, updated_at)
  - Initial data: curate rates for top 50 US metros from municipal water authority websites
  - Source: manual curation + Diffbot extraction (budget 200 credits)

- [ ] Task 2.2: Create water benchmarking service
  - `backend/services/water_rate_service.py`
  - Tier calculator: given usage estimate, calculate monthly cost per municipality
  - Regional benchmark: user's rate vs regional average
  - Conservation tips integration (static content)

- [ ] Task 2.3: Create water API endpoints
  - `GET /api/v1/rates/water` — user's water rate tier information
  - `GET /api/v1/rates/water/benchmark` — comparison vs regional average
  - `GET /api/v1/rates/water/tips` — conservation recommendations
  - No "switch" CTA (monopoly — Decision D4)

- [ ] Task 2.4: Create water frontend
  - `WaterRateBenchmark` — "Your rate vs average" comparison
  - `WaterTierCalculator` — estimate monthly cost by usage
  - `ConservationTips` — water saving recommendations
  - Page: `/water`

- [ ] Task 2.5: Write water tests

### Verification
- [ ] Water rates available for top 50 metros
- [ ] Benchmark comparison displays correctly
- [ ] No "switch" CTA present (monitoring only)
- [ ] All tests pass

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
