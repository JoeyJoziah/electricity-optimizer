# Spec: Wave 4 — Breadth (Propane, Water, Premium Analytics, CI/CD)

## Context
Complete utility coverage with propane tracking and water benchmarking. Launch premium analytics for revenue. Evolve CI/CD for multi-utility testing matrix.

## Epics
- **MU-005**: Propane market tracking (EIA regional averages, no dealer-level)
- **MU-006**: Water rate benchmarking (municipal rates, monitoring only)
- **REV-002**: Premium analytics (Pro/Business tier features)
- **OM-005**: CI/CD evolution (matrix testing, feature flags, canary deploys)

## Dependencies
- Wave 3 must be complete

## Infrastructure
- $26/mo continues

## Acceptance Criteria
- Propane regional prices display with trend monitoring
- Water rate benchmarking for top 50 metros
- Premium analytics reports generating for Pro/Business users
- CI matrix tests per utility type

## References
- Design doc: `docs/plans/2026-03-11-multi-utility-expansion.md`
- Decision D4: Water is monitoring-only
- Decision D12: Propane regional averages only
