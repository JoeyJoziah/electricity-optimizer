# Implementation Plan: Wave 2 — First Expansion

**Track ID:** mu-wave2-first-expansion_20260311
**Spec:** spec.md
**Created:** 2026-03-11
**Status:** [ ] Not Started
**Execution Mode:** Loki RARV Cycles (Autonomous)
**Design Doc:** docs/plans/2026-03-11-multi-utility-expansion.md
**Blocked By:** mu-wave1-foundation_20260311

---

## Overview

First non-electricity utilities go live. Natural gas via EIA API, community solar via EnergySage/state databases. Progressive onboarding replaces single-utility signup. Data quality framework ensures multi-source data reliability. Infrastructure upgrade: $0/mo -> $26/mo (Neon Pro + Render Starter).

---

## Phase 1: Natural Gas Integration (MU-002)

### Tasks

- [ ] Task 1.1: Create EIA Natural Gas API client
  - `backend/integrations/eia_gas.py`
  - Henry Hub spot price endpoint
  - Citygate price by state endpoint
  - Residential price by state endpoint (monthly, 6-8 week lag)
  - Reuse existing EIA API key from 1Password
  - Rate limiting: respect EIA 1000 req/day limit

- [ ] Task 1.2: Create gas rate data pipeline
  - `backend/services/gas_rate_service.py`
  - Fetch -> normalize -> store in `utility_rates` (utility_type=NATURAL_GAS)
  - Price unit conversion: $/Mcf -> $/therm -> $/CCF
  - Weekly aggregation from monthly EIA data
  - Wire into cron: extend `scrape-rates.yml` or new `fetch-gas-rates.yml`

- [ ] Task 1.3: Create gas supplier data layer
  - Scrape Choose Energy gas plans (extend existing scraper pattern)
  - Store gas suppliers in `suppliers` table with utility_types=['NATURAL_GAS']
  - Gas plan comparison logic: fixed vs variable, contract length, early termination

- [ ] Task 1.4: Create gas deregulation mapping
  - Extend `Region` model: `deregulated_gas` field already exists
  - Populate data for 10-12 deregulated gas states (GA, OH, PA, NY, NJ, MD, VA, CT, RI, NH, ME, MA)
  - Create migration 039 to seed gas deregulation data

- [ ] Task 1.5: Create gas API endpoints
  - `GET /api/v1/rates/natural-gas` — gas rates for user's region
  - `GET /api/v1/rates/natural-gas/compare` — gas supplier comparison
  - `GET /api/v1/rates/natural-gas/history` — price history chart data
  - Wire into existing rate router or create new `gas_router.py`

- [ ] Task 1.6: Create gas frontend components
  - `GasRateCard` — current rate display with unit ($/therm)
  - `GasSupplierComparison` — table comparing plans
  - `GasPriceHistory` — chart component (reuse existing chart pattern)
  - Gas tab in rates dashboard
  - Switch CTA for deregulated states, "Monitor" for regulated

- [ ] Task 1.7: Write gas integration tests
  - EIA client: mock API responses, error handling, rate limiting
  - Pipeline: data normalization, unit conversion, storage
  - Supplier scraper: mock responses, plan parsing
  - API: endpoints, auth, validation
  - Frontend: component rendering, data display

### Verification
- [ ] EIA gas data flowing and stored in utility_rates
- [ ] Gas supplier comparison works for deregulated states
- [ ] Price history chart renders with real data
- [ ] All tests pass

---

## Phase 2: Community Solar Marketplace (MU-003a)

### Tasks

- [ ] Task 2.1: Research and integrate community solar data sources
  - EnergySage community solar API (if available) or scrape program listings
  - State program databases: NY, MA, MN, CO, IL, NJ, MD, ME, NH, OR
  - Model: program name, state, savings %, capacity, enrollment status

- [ ] Task 2.2: Create community solar service
  - `backend/services/community_solar_service.py`
  - Program discovery by region/zip code
  - Savings calculator: current electricity bill -> estimated savings with community solar
  - Enrollment status tracking

- [ ] Task 2.3: Create community solar data model
  - Migration 040: `community_solar_programs` table
  - Fields: id, state, program_name, provider, savings_percent, capacity_kw, spots_available, enrollment_url, updated_at
  - Populate initial data for top 10 states

- [ ] Task 2.4: Create community solar API endpoints
  - `GET /api/v1/community-solar/programs` — programs in user's area
  - `GET /api/v1/community-solar/savings` — estimated savings calculator
  - `GET /api/v1/community-solar/program/{id}` — program details

- [ ] Task 2.5: Create community solar frontend
  - `CommunitySolarDiscovery` — browse available programs
  - `SavingsCalculator` — input current bill, see projected savings
  - `ProgramCard` — individual program with enrollment CTA
  - New page: `/community-solar`

- [ ] Task 2.6: Write community solar tests
  - Service: savings calculation accuracy, program filtering
  - API: endpoints, validation
  - Frontend: components, calculator interaction

### Verification
- [ ] Community solar programs listed for 10 states
- [ ] Savings calculator produces reasonable estimates
- [ ] Enrollment CTAs link to provider pages
- [ ] All tests pass

---

## Phase 3: Onboarding V2 — Progressive Discovery (UG-003)

### Tasks

- [ ] Task 3.1: Redesign onboarding flow
  - Step 1: Address entry (existing geocoding) + primary utility selection
  - Step 2: Rate display for primary utility
  - Step 3: "We found more utilities in your area" discovery prompt
  - Remove multi-step wizard pattern — progressive, not front-loaded

- [ ] Task 3.2: Create utility discovery service
  - `backend/services/utility_discovery_service.py`
  - Given address/region, determine available utility types
  - Check deregulation status per utility type
  - Return: list of {utility_type, status: deregulated/regulated/available, description}

- [ ] Task 3.3: Create post-signup nudge system
  - "Add your gas provider" nudge after first electricity view
  - Bill upload prompt: "Upload a bill to auto-detect your utilities"
  - Completion progress indicator (2/5 utilities tracked)

- [ ] Task 3.4: Update frontend onboarding components
  - Simplify `OnboardingWizard` to address + primary utility
  - Add `UtilityDiscoveryCard` — post-signup utility suggestions
  - Add `CompletionProgress` — progress ring showing utility coverage
  - Update `/onboarding` route

- [ ] Task 3.5: Write onboarding tests
  - Flow: address -> primary utility -> dashboard (no friction)
  - Discovery: correct utilities suggested per region
  - Nudge: timing and dismissal behavior
  - Completion tracking accuracy

### Verification
- [ ] Onboarding takes < 60 seconds for address + primary utility
- [ ] Utility discovery correctly identifies available utilities per region
- [ ] Post-signup nudges appear with correct timing
- [ ] All tests pass

---

## Phase 4: Data Quality Framework (OM-002)

### Tasks

- [ ] Task 4.1: Create data freshness monitoring
  - `backend/services/data_quality_service.py`
  - Track last_updated per utility_type per region
  - Expected freshness: electricity=1h, gas=7d, heating_oil=7d, solar=30d
  - Alert when data exceeds 2x expected freshness window

- [ ] Task 4.2: Create data validation pipeline
  - Anomaly detection: flag rates that deviate > 3 std from rolling average
  - Source validation: check EIA/scraper responses for expected schema
  - Duplicate detection: prevent re-ingestion of identical rate records

- [ ] Task 4.3: Create source reliability scoring
  - Track success/failure rate per data source
  - Downgrade unreliable sources in rate comparison rankings
  - Alert on source degradation (> 20% failure rate in 24h window)

- [ ] Task 4.4: Create data quality dashboard (internal)
  - Extend `/internal/` endpoints
  - `GET /internal/data-quality/freshness` — freshness report
  - `GET /internal/data-quality/anomalies` — recent anomalies
  - `GET /internal/data-quality/sources` — source reliability scores

- [ ] Task 4.5: Write data quality tests
  - Freshness: correct alerting thresholds per utility type
  - Validation: anomaly detection accuracy
  - Source scoring: reliability calculation
  - Dashboard: endpoint responses

### Verification
- [ ] Freshness monitoring active per utility type
- [ ] Anomaly detection catches obviously wrong rates (e.g., $100/kWh)
- [ ] Source reliability visible in internal dashboard
- [ ] All tests pass

---

## Phase 5: Infrastructure Upgrade & Final Validation

### Tasks

- [ ] Task 5.1: Document infrastructure upgrade decision
  - Neon: Free -> Pro ($19/mo) when storage > 450 MiB
  - Render: Free -> Starter ($7/mo) if memory pressure detected
  - Create upgrade runbook with rollback steps

- [ ] Task 5.2: Run full test suite
  - Backend + frontend + E2E
  - All new gas + solar + onboarding + data quality tests

- [ ] Task 5.3: Deploy migrations to Neon production
  - Migrations 039-040 (gas deregulation seed, community solar programs)

- [ ] Task 5.4: Update CONTINUITY.md and DSP graph

### Verification
- [ ] All tests pass
- [ ] Gas rates visible in dashboard
- [ ] Community solar programs browsable
- [ ] Onboarding V2 live
- [ ] Data quality monitoring active
- [ ] Wave 3 unblocked

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
