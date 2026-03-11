# Spec: Wave 1 — Multi-Utility Schema Foundation + Growth Basics

## Context
Deploy utility_accounts table for user-utility linking, referral system for
user growth, and PWA basics for mobile engagement. OpenTelemetry observability
runs in parallel (existing track).

## Codebase Audit (2026-03-11)
- `utility_type` enum and column already exist on `electricity_prices` (migration 006)
- `UtilityType` and `PriceUnit` enums already defined in `models/utility.py`
- `PriceRepository` already supports multi-utility queries
- **Eliminated:** utility_prices VIEW, utility_rates table (redundant)
- **Migration numbering:** 038+ (037 is latest deployed)

## Epics
- **MU-001a**: Utility accounts table (user-utility-provider linking)
- **UG-001**: Referral system (codes, apply/complete flow, stats)
- **UG-005**: PWA basics (manifest, service worker, install prompt, web push)
- **OM-001**: OpenTelemetry (existing track — do not duplicate)

## Dependencies
- Wave 0 must be complete (NREL migrated, cache retention active) — **DONE**
- OM-001 is an existing track — coordinate but do not duplicate

## Infrastructure
- $0/mo (no paid tier changes)
- 2 new migrations (038, 039)
- ~35 new backend tests, ~5 new frontend tests

## Acceptance Criteria
- `utility_accounts` table deployed with CRUD API
- Users can link multiple utility accounts (electricity, gas, etc.)
- Ownership enforcement: users can only access their own accounts
- Referral codes generate and track successful referrals
- Self-referral blocked
- Service worker registered with offline rate viewing
- Web manifest enables install prompt on mobile
- All existing tests still pass (zero regressions)

## References
- Design doc: `docs/plans/2026-03-11-multi-utility-expansion.md`
- Decision D7: VIEW-based migration (superseded — utility_type already real column)
- Decision D11: Multi-utility user account model
- Existing patterns: `repositories/price_repository.py`, `api/v1/user.py`, `models/price.py`
