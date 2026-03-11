# Spec: Wave 2 — First Expansion (Natural Gas + Community Solar)

## Context
First non-electricity utilities go live. Natural gas has highest infrastructure overlap with electricity. Community solar opens new marketplace. Progressive onboarding replaces single-utility signup. Data quality framework ensures multi-source data integrity.

## Epics
- **MU-002**: Natural gas integration (EIA API, gas suppliers, rate comparison)
- **MU-003a**: Community solar marketplace (EnergySage, state programs)
- **UG-003**: Onboarding V2 (progressive discovery, post-signup utility detection)
- **OM-002**: Data quality framework (freshness monitoring, validation, source scoring)

## Dependencies
- Wave 1 must be complete (schema foundation, utility_accounts table, utility_rates table)
- Infrastructure upgrade triggered: Neon Pro ($19/mo) + Render Starter ($7/mo) = $26/mo

## Acceptance Criteria
- Natural gas rates flowing from EIA API for 10-12 deregulated states
- Gas supplier comparison functional with switch CTAs
- Community solar programs listed for 10 states
- Onboarding completion rate measurable (target > 70%)
- Data freshness monitoring active per utility type

## References
- Design doc: `docs/plans/2026-03-11-multi-utility-expansion.md`
- Decision D2: Start with natural gas
- Decision D3: EIA as primary data source
- Decision D8: Utility-specific alerting cadences
