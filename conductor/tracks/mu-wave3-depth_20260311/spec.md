# Spec: Wave 3 — Depth (CCA, Heating Oil, Alerting, SEO, Affiliate)

## Context
Deepen multi-utility coverage with CCA transparency, heating oil price tracking, and proactive rate change alerting. Begin revenue generation with affiliate links. Launch SEO engine for organic growth. Prepare for scale.

## Epics
- **MU-003b**: CCA detection & transparency
- **MU-004**: Heating oil price tracking
- **MU-007**: Proactive rate change alerting (multi-utility, cadence-aware)
- **UG-002**: SEO & content engine (programmatic landing pages)
- **REV-001**: Affiliate revenue (supplier switch links)
- **OM-003**: Scalability preparation

## Dependencies
- Wave 2 must be complete (gas + solar live, onboarding V2, data quality framework)

## Infrastructure
- $26/mo continues (no change from Wave 2)

## Acceptance Criteria
- CCA lookup works by zip code + municipality
- Heating oil prices display with regional breakdown
- Rate change alerts fire with utility-specific cadences
- Programmatic SEO pages rank for target keywords
- First affiliate click tracked and attributed
- Read replica or sharding strategy documented

## References
- Design doc: `docs/plans/2026-03-11-multi-utility-expansion.md`
- Decision D5: CCA as electricity feature
- Decision D8: Utility-specific alerting cadences
- Decision D10: CCA and Community Solar are separate
