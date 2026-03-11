# Multi-Utility Platform Expansion — Final Design Document

**Status:** APPROVED (Multi-Agent Brainstorming complete)
**Date:** 2026-03-11
**Review Process:** Primary Designer + Skeptic/Challenger + Constraint Guardian + User Advocate + Integrator/Arbiter
**Positioning:** "The US Uswitch" — first multi-utility rate comparison platform

---

## Understanding Summary

- **What:** Expand RateShift from electricity-only rate comparison to comprehensive multi-utility savings covering electricity, natural gas, heating oil, propane, community solar, CCA, and water rate monitoring
- **Why:** No US platform holds the multi-utility comparison position. The deregulated utility market is fragmented across electricity (18 states + DC), natural gas (10-12 states), and unregulated commodities (heating oil, propane). Users manage 3-5 utility bills with zero cross-visibility
- **Who:** US homeowners and renters in deregulated markets, expanding to all 50 states for monitoring-only utilities
- **Key constraint:** Incremental, utility-by-utility stacking starting from existing electricity infrastructure (~25% model layer done, ~5% service/API done)
- **Non-goals (Wave 1-5):** Enterprise/B2B features, white-label API, international expansion, real-time trading

---

## Existing Multi-Utility Support (Baseline Assessment)

### Already Built (~25% model layer)
- `UtilityType` enum: ELECTRICITY, NATURAL_GAS, HEATING_OIL, PROPANE, SOLAR (in `backend/models/region.py`)
- `PriceUnit` enum: 16 units covering all utility types (kWh, therm, gallon, CCF, etc.)
- `Region` model: `deregulated_gas`, `deregulated_electricity`, `solar_incentives` fields
- `Supplier` model: `utility_types` JSON field for multi-utility suppliers

### Gaps (~5% service/API layer)
- Table names are electricity-specific (`electricity_prices`)
- `price_per_kwh` columns semantically wrong for 4/5 utility types
- 27 hardcoded SQL references to `electricity_prices`
- ML pipeline has zero utility-type awareness
- All scrapers/integrations are electricity-only
- No multi-utility user account model (user -> many utility accounts)

---

## Design Approach: Incremental Utility Stacking (Approach A)

### Strategy
Extend utility-by-utility starting with natural gas (highest overlap with existing electricity infrastructure). Use VIEW-based schema migration for zero-downtime table evolution. Defer ML forecasting for non-electricity until 6+ months of data collection per utility type.

### Key Architecture Decisions

**Schema migration:** `CREATE VIEW utility_prices AS SELECT *, 'ELECTRICITY'::text AS utility_type FROM electricity_prices` — zero-downtime, reversible, no 27-reference rename

**Data sources:**
- Electricity: EIA API (existing) + NREL/OpenEI + state PUC scrapers
- Natural gas: EIA API (same key, monthly with 6-8 week lag)
- Heating oil: EIA Weekly Petroleum Status Report
- Propane: EIA propane data (weekly regional averages)
- Community solar: EnergySage API + state program databases
- Water: Municipal rate schedules (manual + Diffbot extraction)

**Alerting cadences** (utility-specific, not one-size-fits-all):
- Electricity: 30 min (existing real-time scrapers)
- Natural gas: Weekly digest (EIA monthly, 6-8 week lag)
- Heating oil: Weekly digest (EIA weekly report)
- Propane: Bi-weekly digest (regional averages)
- Community solar: Monthly (program changes are infrequent)
- Water: Quarterly (rate changes are rare)

---

## Epic Definitions

### Track 1: PRODUCT_DEPTH (Multi-Utility Core)

#### MU-000: Wave 0 Pre-requisites
- NREL API domain migration (`developer.nrel.gov` -> `developer.nlr.gov`, deadline April 30 2026)
- Cache table retention policies (weather_cache 30d, scraped_rates 90d, market_intelligence 180d)
- Neon storage audit (current usage vs 512 MiB ceiling on free tier)

#### MU-001: Multi-Utility Schema Foundation
- `CREATE VIEW utility_prices` with utility_type discriminator
- `utility_accounts` table (user -> many utility accounts, each with utility_type + region + provider)
- `price_per_unit` column alongside `price_per_kwh` (dual-write during transition)
- Generic `utility_rates` table for non-electricity rates
- Updated Pydantic schemas with UtilityType-aware serialization
- Repository pattern update: `PriceRepository.get_by_utility_type()`

#### MU-002: Natural Gas Integration
- EIA Natural Gas API client (monthly Henry Hub + citygate prices)
- Gas supplier scraper (Choose Energy gas plans)
- `gas_rates` data pipeline with weekly aggregation
- Gas-specific rate comparison logic (therms, CCF conversion)
- Gas deregulation state mapping (10-12 states)
- Frontend: Gas rate cards, supplier comparison, switch CTA for deregulated states

#### MU-003a: Community Solar Marketplace
- EnergySage community solar API integration
- State community solar program database (10 states)
- Savings calculator (current bill vs community solar subscription)
- Frontend: Community solar discovery, program comparison, enrollment CTA
- Separate from CCA — these are fundamentally different products

#### MU-003b: CCA Detection & Transparency
- CCA program database (10 states, municipality-level)
- Address-to-CCA lookup (zip code + municipality matching)
- CCA rate vs default utility rate comparison
- Opt-out guidance where applicable
- Frontend: "You're in a CCA" notification, rate comparison, opt-out info

#### MU-004: Heating Oil Price Tracking
- EIA Weekly Petroleum Status Report client
- Regional heating oil price aggregation (PADDs -> states)
- Dealer directory (Yellow Pages/Yelp API scraping for local dealers)
- Price alert system (weekly digest)
- Frontend: Heating oil dashboard, price history charts, dealer list

#### MU-005: Propane Market Tracking
- EIA propane price data (weekly regional averages, wholesale only)
- Regional price dashboard (no dealer-level comparison — YAGNI, no dealer API)
- Price trend monitoring and alerts (bi-weekly digest)
- Frontend: Propane price widget, historical trends, fill-up timing suggestions

#### MU-006: Water Rate Benchmarking
- Municipal water rate database (manual curation + Diffbot extraction)
- Rate tier calculator (usage-based tier modeling)
- Benchmark: "Your water rate vs regional average"
- Conservation tips integration
- Frontend: Water bill analyzer, usage benchmarking, no "switch" CTA (monopoly)

#### MU-007: Proactive Rate Change Alerting
- Rate change detection engine (diff current vs previous scrape)
- Multi-channel alerts (push + email + in-app)
- Utility-specific cadences (see alerting cadences above)
- "Better deal found" auto-recommendations
- Frontend: Alert preferences per utility, notification center

#### MU-008: Unified Multi-Utility Dashboard
- Combined savings view across all utility types
- Spend breakdown by utility (pie chart + trend lines)
- Single "total savings" metric
- Cross-utility optimization suggestions
- Frontend: Dashboard redesign with utility tabs + combined view

### Track 2: USER_GROWTH

#### UG-001: Referral & Viral Loop
- Referral code system (unique per user)
- Double-sided incentive (referrer + referee both get Pro trial extension)
- Shareable savings cards (image generation for social sharing)
- Referral tracking dashboard

#### UG-002: SEO & Content Engine
- Programmatic SEO: `/rates/{state}/{utility-type}` landing pages
- Rate comparison content generation (city-level pages)
- Blog/guide content: "How to switch gas providers in [state]"
- Schema markup for rate data (Product, Offer structured data)

#### UG-003: Onboarding V2 (Progressive Discovery)
- Address + primary utility only (not multi-utility wizard)
- Post-signup: discover additional utilities via bill upload/parsing
- Guided setup: "We found gas plans in your area" nudge
- Completion progress indicator
- Address validation (existing OWM + Nominatim geocoding)

#### UG-004: Community Features
- Rate report crowdsourcing (user-submitted rate data)
- Neighborhood average comparison
- "X users in your area saved $Y" social proof
- Discussion/tips forum (lightweight, per-utility)

#### UG-005: PWA & Mobile
- Service worker for offline rate viewing
- Push notification integration (OneSignal existing)
- Add-to-homescreen prompt
- Responsive dashboard optimization

### Track 3: REVENUE & MONETIZATION

#### REV-001: Affiliate Revenue
- Affiliate link integration for supplier switch CTAs
- Choose Energy / EnergySage partner programs
- Revenue tracking per referral
- Disclosure compliance (FTC affiliate disclosure)

#### REV-002: Premium Analytics (Pro/Business Tier)
- Advanced rate forecasting (Pro)
- Multi-utility spend optimization report (Business)
- Historical rate data export (Business)
- API access for power users (Business)

#### REV-003: Data API (Deferred to Wave 6+)
#### REV-004: White-Label (Deferred to Wave 6+)
#### REV-005: Enterprise B2B (Deferred to Wave 6+)

### Track 4: OPERATIONAL MATURITY

#### OM-001: Observability & Monitoring
- OpenTelemetry custom spans for all 26 services (existing track: otel-distributed-tracing)
- Grafana Cloud export
- SLI/SLO definitions per critical path
- Error budget tracking

#### OM-002: Data Quality Framework
- Rate data freshness monitoring (per utility type)
- Data validation pipeline (anomaly detection on scraped rates)
- Source reliability scoring
- Data completeness dashboards

#### OM-003: Scalability Preparation
- Database sharding strategy (by region)
- Read replica setup for analytics queries
- CDN optimization for static rate data
- Connection pool tuning for multi-utility load

#### OM-004: Security Hardening
- OWASP Top 10 re-audit with multi-utility attack surface
- API key rotation automation
- Encrypted credential storage audit (AES-256-GCM for portal scraper)
- Dependency vulnerability scanning automation

#### OM-005: CI/CD Evolution
- Matrix testing per utility type
- Deployment canary for utility-specific changes
- Feature flag system (utility-type granularity)
- Rollback automation

---

## Execution Plan: 6-Wave Sequence

### Wave 0: Pre-requisites ($0/mo infrastructure)
- **MU-000**: NREL migration + cache retention + Neon audit
- **Duration:** 1-2 days
- **Gate:** NREL endpoints responding, cache policies active, Neon < 400 MiB

### Wave 1: Foundation ($0/mo infrastructure)
- **MU-001**: Multi-utility schema foundation (VIEW strategy)
- **UG-001**: Referral system
- **UG-005**: PWA basics
- **OM-001**: OpenTelemetry (existing track)
- **Duration:** 2-3 weeks
- **Gate:** `utility_prices` VIEW active, referral codes generating, service worker registered

### Wave 2: First Expansion ($26/mo: Neon Pro $19 + Render Starter $7)
- **MU-002**: Natural gas integration
- **MU-003a**: Community solar marketplace
- **UG-003**: Onboarding V2
- **OM-002**: Data quality framework
- **Duration:** 3-4 weeks
- **Gate:** Gas rates flowing, community solar programs listed, onboarding completion rate > 70%
- **Infrastructure trigger:** Neon storage > 450 MiB OR gas data pipeline active

### Wave 3: Depth ($26/mo continues)
- **MU-003b**: CCA detection
- **MU-004**: Heating oil tracking
- **MU-007**: Rate change alerting
- **UG-002**: SEO engine
- **REV-001**: Affiliate revenue
- **OM-003**: Scalability prep
- **Duration:** 3-4 weeks
- **Gate:** CCA lookup functional, heating oil prices displaying, first affiliate click tracked

### Wave 4: Breadth ($26/mo continues)
- **MU-005**: Propane tracking
- **MU-006**: Water benchmarking
- **REV-002**: Premium analytics
- **OM-005**: CI/CD evolution
- **Duration:** 2-3 weeks
- **Gate:** All 7 utility types represented, premium analytics generating reports

### Wave 5: Unification ($26/mo continues)
- **MU-008**: Unified multi-utility dashboard
- **UG-004**: Community features
- **OM-004**: Security hardening
- **Duration:** 2-3 weeks
- **Gate:** Combined savings metric calculating, community posts submitting, OWASP clean

### Wave 6+ (Deferred)
- REV-003: Data API
- REV-004: White-label
- REV-005: Enterprise B2B
- Triggered by: 10K+ users OR $500+/mo affiliate revenue

---

## Decision Log

| # | Decision | Alternatives Considered | Rationale |
|---|----------|------------------------|-----------|
| D1 | Incremental utility stacking (Approach A) | Full abstraction rewrite (B), Microservice modules (C) | Lowest risk, fastest to first new utility, preserves existing electricity value |
| D2 | Start with natural gas (MU-002) | Heating oil, community solar | Highest infrastructure overlap with electricity, same EIA API, 10-12 deregulated states |
| D3 | EIA as primary data source for gas/oil/propane | Proprietary APIs, manual curation | Free, reliable, covers 3 utility types with same API key |
| D4 | Water is monitoring-only (no "switch" CTA) | Skip water entirely, add water marketplace | Water is monopoly — no switching possible, but monitoring fills dashboard gap |
| D5 | CCA as feature of electricity platform, not separate utility | Separate utility type, skip CCA | CCA affects electricity rate — it's a modifier, not independent utility |
| D6 | Progressive onboarding (address + primary utility only) | Multi-utility wizard, utility auto-detection | Reduces onboarding abandonment risk; discover utilities post-signup via bill upload |
| D7 | VIEW-based schema migration (not table rename) | Direct RENAME TABLE, dual-write with new table | Zero-downtime, reversible, avoids 27 hardcoded SQL reference updates |
| D8 | Utility-specific alerting cadences | Uniform 30-min for all, user-configurable | EIA data is monthly with 6-8 week lag — 30-min alerts for gas would show stale data |
| D9 | Defer ML forecasting for non-electricity | Train immediately with sparse data | Need 6+ months of collected data per utility type before models are meaningful |
| D10 | Community Solar and CCA as separate epics (MU-003a/MU-003b) | Combined "community energy" epic | Fundamentally different products: solar = subscription marketplace, CCA = transparency tool |
| D11 | Multi-utility user account model (user -> many accounts) | Single account with utility flags | Users may have different providers per utility type; need per-account tracking |
| D12 | Propane: regional averages only (no dealer-level) | Dealer API scraping, manual dealer directory | No propane dealer API exists; dealer-level data is YAGNI for MVP |
| D13 | Infrastructure at $0/mo through Wave 1 | Pre-provision paid tiers | Delay cost until data pipeline demands it (Neon Pro at ~450 MiB) |
| D14 | Enterprise features deferred to Wave 6+ | Include B2B in Wave 3-4 | Premature — need consumer traction first; B2B requires sales team |
| D15 | Diffbot credit conservation (5K free credits) | Unlimited scraping, alternate extraction | Budget 500/mo for rate extraction; monitor burn rate in OM-002 |
| D16 | NREL domain migration is P0 (MU-000) | Defer to Wave 1 | April 30, 2026 deadline — service disruption if missed |
| D17 | Cache table retention policies in MU-000 | Address in Wave 2 with data quality | Neon 512 MiB ceiling is BLOCKER — must be addressed before adding more data |
| D18 | "US Uswitch" competitive positioning | Electricity-only niche, utility marketplace | No US competitor holds multi-utility comparison position; validated by market research |

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Neon 512 MiB exceeded before Wave 2 paid upgrade | Service disruption | MU-000 cache retention + monitoring alert at 400 MiB |
| EIA API rate limiting or deprecation | Loss of gas/oil/propane data | Cache aggressively, implement circuit breaker, monitor API health |
| Diffbot free credits exhausted | Loss of rate extraction | Budget 500/mo, implement extraction caching, fall back to manual curation |
| NREL domain migration missed (April 30 2026) | NREL API calls fail | P0 in MU-000, implement before any other work |
| Render 512MB RAM OOM with multi-utility pipelines | Backend crashes | Monitor memory, implement utility-type-specific worker processes |
| Tavily 1K credits/mo exhausted | Loss of market research | Rate-limit market research pipeline, cache results aggressively |

---

## Assumptions

1. EIA API remains free and available (no API key changes)
2. Neon Pro tier ($19/mo) will be sufficient through Wave 5
3. Community solar data is accessible via EnergySage API or public program databases
4. Heating oil/propane users are willing to use a web app (demographic typically older)
5. Water rate data can be curated for top 50 metros within Wave 4 timeline
6. Affiliate revenue from gas/solar switching will be comparable to electricity affiliate rates
7. CCA information is publicly available at municipality level
8. User demand exists for multi-utility dashboard (validated by market gap analysis, not user testing)
