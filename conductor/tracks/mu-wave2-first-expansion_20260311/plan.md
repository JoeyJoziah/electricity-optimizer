# Implementation Plan: Wave 2 — First Expansion

**Track ID:** mu-wave2-first-expansion_20260311
**Spec:** spec.md
**Created:** 2026-03-11
**Status:** [x] Complete (2026-03-11)
**Execution Mode:** Loki RARV Cycles (Autonomous)
**Design Doc:** docs/plans/2026-03-11-multi-utility-expansion.md
**Blocked By:** mu-wave1-foundation_20260311 (COMPLETE)
**Updated:** 2026-03-11 (audit corrections — EIA client, gas deregulation, utility_rates refs)

---

## Overview

First non-electricity utilities go live. Natural gas via EIA API, community solar via EnergySage/state databases. Progressive onboarding replaces single-utility signup. Data quality framework ensures multi-source data reliability. Infrastructure upgrade: $0/mo -> $26/mo (Neon Pro + Render Starter).

---

## Phase 1: Natural Gas Integration (MU-002)

### Tasks

- [x] Task 1.1: ~~Create EIA Natural Gas API client~~ **ALREADY EXISTS**
  - `backend/integrations/pricing_apis/eia.py` has `get_gas_price()`, `get_heating_oil_price()`, `get_propane_price()`, `get_price_by_utility_type()`
  - Rate limiting, caching, circuit breaker all wired in
  - $/Mcf → $/therm conversion built in (÷ 10.37)

- [x] Task 1.2: Create gas rate service (pipeline)
  - `backend/services/gas_rate_service.py`
  - Fetch from EIA client → normalize → store in `electricity_prices` (utility_type=NATURAL_GAS)
  - **CORRECTED**: No `utility_rates` table — `electricity_prices` already multi-utility (migration 006)
  - PriceRepository already supports `utility_type` filter on all queries
  - Wire into cron: new `fetch-gas-rates.yml` GHA workflow
  - Fetch for all `DEREGULATED_GAS_STATES` (16 states)

- [x] Task 1.3: Seed gas suppliers in registry
  - Add gas supplier entries to `supplier_registry` (already supports `utility_types[]`)
  - Migration 040: seed gas suppliers for deregulated states
  - Gas plan comparison logic: fixed vs variable, contract length

- [x] Task 1.4: ~~Create gas deregulation mapping~~ **ALREADY EXISTS**
  - Migration 006 created `state_regulations` table with `gas_deregulated` column
  - 16 states seeded (CT, TX, OH, PA, IL, NY, NJ, MA, MD, RI, NH, ME, DE, GA, IN, KY)
  - `DEREGULATED_GAS_STATES` set in `models/region.py`

- [x] Task 1.5: Create gas API endpoints
  - `GET /api/v1/rates/natural-gas` — gas rates for user's region
  - `GET /api/v1/rates/natural-gas/compare` — gas supplier comparison
  - `GET /api/v1/rates/natural-gas/history` — price history chart data
  - Wire into existing rate router or create new `gas_router.py`

- [x] Task 1.6: Create gas frontend components
  - `GasRateCard` — current rate display with unit ($/therm)
  - `GasSupplierComparison` — table comparing plans
  - `GasPriceHistory` — chart component (reuse existing chart pattern)
  - Gas tab in rates dashboard
  - Switch CTA for deregulated states, "Monitor" for regulated

- [x] Task 1.7: Write gas integration tests
  - EIA client: mock API responses, error handling, rate limiting
  - Pipeline: data normalization, unit conversion, storage
  - Supplier scraper: mock responses, plan parsing
  - API: endpoints, auth, validation
  - Frontend: component rendering, data display

### Verification
- [x] EIA gas data flowing and stored in electricity_prices (utility_type=NATURAL_GAS)
- [x] Gas supplier comparison works for deregulated states
- [x] Price history chart renders with real data
- [x] All tests pass (15 backend + 19 frontend = 34 gas tests, 1563 total frontend)

---

## Phase 2: Community Solar Marketplace (MU-003a)

### Tasks

- [x] Task 2.1: Research and integrate community solar data sources
  - EnergySage community solar API (if available) or scrape program listings
  - State program databases: NY, MA, MN, CO, IL, NJ, MD, ME, NH, OR
  - Model: program name, state, savings %, capacity, enrollment status

- [x] Task 2.2: Create community solar service
  - `backend/services/community_solar_service.py`
  - Program discovery by region/zip code
  - Savings calculator: current electricity bill -> estimated savings with community solar
  - Enrollment status tracking

- [x] Task 2.3: Create community solar data model
  - Migration 041: `community_solar_programs` table (040 = gas supplier seed)
  - Fields: id, state, program_name, provider, savings_percent, capacity_kw, spots_available, enrollment_url, updated_at
  - Populate initial data for top 10 states

- [x] Task 2.4: Create community solar API endpoints
  - `GET /api/v1/community-solar/programs` — programs in user's area
  - `GET /api/v1/community-solar/savings` — estimated savings calculator
  - `GET /api/v1/community-solar/program/{id}` — program details

- [x] Task 2.5: Create community solar frontend
  - `CommunitySolarDiscovery` — browse available programs
  - `SavingsCalculator` — input current bill, see projected savings
  - `ProgramCard` — individual program with enrollment CTA
  - New page: `/community-solar`

- [x] Task 2.6: Write community solar tests
  - Service: savings calculation accuracy, program filtering
  - API: endpoints, validation
  - Frontend: components, calculator interaction

### Verification
- [x] Community solar programs listed for 10 states (15 programs seeded across 12 states)
- [x] Savings calculator produces reasonable estimates (unit-tested with rounding)
- [x] Enrollment CTAs link to provider pages
- [x] All tests pass (17 backend + 23 frontend = 40 solar tests, 1586 total frontend)

---

## Phase 3: Onboarding V2 — Progressive Discovery (UG-003)

### Tasks

- [x] Task 3.1: Redesign onboarding flow
  - Simplified to single step: region selection → auto-set electricity → complete
  - Removed multi-step wizard (utility-types, supplier, account-link steps)
  - Progressive discovery via UtilityDiscoveryCard on dashboard post-signup

- [x] Task 3.2: Create utility discovery service
  - `backend/services/utility_discovery_service.py` — pure logic, no DB required
  - Checks DEREGULATED_ELECTRICITY_STATES, DEREGULATED_GAS_STATES, HEATING_OIL_STATES, COMMUNITY_SOLAR_STATES
  - `discover(state)` → list of {utility_type, label, status, description}
  - `get_completion_status(state, tracked_types)` → tracked/available/percent/missing
  - `backend/api/v1/utility_discovery.py` — GET /discover, GET /completion

- [x] Task 3.3: Create post-signup nudge system
  - `UtilityDiscoveryCard` — shows untracked utilities with status badges and links
  - Dismissable via onDismiss prop
  - `CompletionProgress` — SVG progress ring showing N/M utilities tracked
  - Hides automatically when 100% complete

- [x] Task 3.4: Update frontend onboarding components
  - Simplified `OnboardingWizard` to region-only (43 lines, was 215)
  - Created `UtilityDiscoveryCard` — post-signup utility suggestions with routes
  - Created `CompletionProgress` — progress ring with tracked/available counts
  - API client: `utility-discovery.ts`, hooks: `useUtilityDiscovery.ts`

- [x] Task 3.5: Write onboarding tests
  - Backend: 19 tests (discover per state, completion tracking, edge cases)
  - Frontend: 35 tests (wizard 7, hooks 7, discovery card 9, progress 5, onboarding page 7)
  - Flow: region → dashboard (single step, no friction)
  - Discovery: correct utilities per region, dismiss behavior
  - Completion: tracked/available counts, singular/plural, 100% hide

### Verification
- [x] Onboarding is single step — region select → complete (< 30 seconds)
- [x] Utility discovery correctly identifies available utilities per region (19 backend tests)
- [x] Post-signup nudges: UtilityDiscoveryCard shows untracked, CompletionProgress shows ring
- [x] All tests pass (19 backend + 35 frontend = 54 onboarding tests, 1606 total frontend)

---

## Phase 4: Data Quality Framework (OM-002)

### Tasks

- [x] Task 4.1: Create data freshness monitoring
  - `backend/services/data_quality_service.py`
  - Track last_updated per utility_type per region via `get_freshness_report()`
  - FRESHNESS_THRESHOLDS: electricity=1h, natural_gas=168h, heating_oil=168h, community_solar=720h
  - Alert when data exceeds 2x expected freshness window (FRESHNESS_ALERT_MULTIPLIER=2)

- [x] Task 4.2: Create data validation pipeline
  - Anomaly detection: `detect_anomalies(lookback_days)` — z-score > 3.0 std from rolling avg
  - `check_rate_anomaly(rate, avg, std)` — static method for single-rate validation
  - Duplicate detection: `check_duplicate(existing, rate, region, type, tolerance=0.0001)`

- [x] Task 4.3: Create source reliability scoring
  - `get_source_reliability(window_hours)` — success/failure from scrape_results table
  - Fallback to electricity_prices counts when scrape_results unavailable
  - SOURCE_FAILURE_ALERT_THRESHOLD = 0.20 (>20% failure = degraded)

- [x] Task 4.4: Create data quality dashboard (internal)
  - `backend/api/v1/internal/data_quality.py` — 3 endpoints wired into internal router
  - `GET /internal/data-quality/freshness` — freshness report with stale_count
  - `GET /internal/data-quality/anomalies` — anomalies with configurable lookback_days (1-365)
  - `GET /internal/data-quality/sources` — source reliability with configurable window_hours (1-720)

- [x] Task 4.5: Write data quality tests
  - `backend/tests/test_data_quality_service.py` — 25 tests across 6 test classes
  - TestFreshnessThresholds (5), TestCheckRateAnomaly (6), TestCheckDuplicate (6)
  - TestFreshnessReport (3 async), TestSourceReliability (2 async), TestConstants (3)
  - All 25 tests pass

### Verification
- [x] Freshness monitoring active per utility type (4 thresholds configured)
- [x] Anomaly detection catches obviously wrong rates (e.g., $100/kWh → z=4990, flagged)
- [x] Source reliability visible in internal dashboard (3 endpoints)
- [x] All tests pass (25 backend data quality tests)

---

## Phase 5: Infrastructure Upgrade & Final Validation

### Tasks

- [x] Task 5.1: Document infrastructure upgrade decision
  - `docs/runbooks/infrastructure-upgrade-wave2.md` — upgrade triggers, steps, rollback
  - Decision: Stay Free for Wave 2 (new data < 1 MiB/mo)
  - Upgrade Neon at 400 MiB, Render on OOM detection

- [x] Task 5.2: Run full test suite
  - Backend: 2,236 passed, 2 skipped, 0 failures (10.5s)
  - Frontend: 1,606 passed, 111 suites, 0 failures (24s)
  - Includes all gas (34) + solar (40) + onboarding (54) + data quality (25) tests

- [x] Task 5.3: Deploy migrations to Neon production
  - Migrations 040-041 (gas supplier seed, community solar programs)
  - Deployed manually via terminal (2026-03-11)

- [x] Task 5.4: Update DSP graph
  - DSP bootstrap run: 1,082 entities, 1,483 imports, 0 cycles
  - New entities include: data_quality_service, utility_discovery_service, community_solar_service, gas_rate_service

### Verification
- [x] All tests pass (2,236 backend + 1,606 frontend = 3,842 total)
- [x] Gas rates visible in dashboard (Phase 1 complete, API + frontend)
- [x] Community solar programs browsable (Phase 2 complete, 15 programs seeded)
- [x] Onboarding V2 live (Phase 3 complete, single-step wizard)
- [x] Data quality monitoring active (Phase 4 complete, 3 internal endpoints)
- [x] Wave 3 unblocked (migrations 040-041 deployed)

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
