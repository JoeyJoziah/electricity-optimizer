# Spec: Wave 0 — Multi-Utility Pre-requisites

## Context
Before expanding RateShift to multi-utility, critical pre-requisites must be addressed to prevent service disruption and storage overflow.

## Requirements
1. Migrate NREL API calls from `developer.nrel.gov` to `developer.nlr.gov` before April 30, 2026 deadline
2. Implement cache table retention policies to prevent Neon 512 MiB ceiling breach
3. Audit current Neon storage usage and establish monitoring alert at 400 MiB

## Acceptance Criteria
- All NREL API endpoints respond correctly after domain migration
- `weather_cache` rows older than 30 days are automatically purged
- `scraped_rates` rows older than 90 days are automatically purged
- `market_intelligence` rows older than 180 days are automatically purged
- Neon storage usage is documented and below 400 MiB
- db-maintenance workflow includes retention cleanup

## References
- Design doc: `docs/plans/2026-03-11-multi-utility-expansion.md`
- Decision D16: NREL migration is P0
- Decision D17: Cache retention is BLOCKER
