# ADR-005: Multi-Utility Expansion Pattern

**Status**: Accepted
**Date**: 2026-03-11
**Decision Makers**: Devin McGrath

## Context

RateShift started as an electricity rate optimizer. Market research showed users want a unified view of all utility costs. Expanding to additional utility types (natural gas, water, propane, heating oil, community solar) requires a consistent, scalable pattern.

Key constraint: not all utilities support switching. Water is a geographic monopoly. Propane and heating oil are seasonal. Community solar is enrollment-based.

## Decision

Implement a **parallel service/route/model pattern per utility type** with differentiated CTAs:

| Utility | Tables | Service | CTA |
|---------|--------|---------|-----|
| Electricity | `electricity_prices`, `suppliers`, `tariffs` | `price_service` | Switch supplier |
| Natural Gas | `gas_prices` | `gas_rate_service` | Switch supplier |
| Community Solar | `community_solar_programs` | `community_solar_service` | Enroll |
| Heating Oil | `heating_oil_prices`, `heating_oil_dealers` | `heating_oil_service` | Compare dealers |
| Propane | `propane_prices` | `propane_service` | Fill-up timing |
| Water | `water_rates` | `water_rate_service` | Monitor only |

Each utility gets:
1. Backend service in `backend/services/`
2. API routes in `backend/api/v1/`
3. Frontend page under `frontend/app/(app)/`
4. Sidebar nav item (total: 15 items)
5. SEO ISR page at `/rates/[state]/[utility_type]`

## Consequences

### Positive
- Consistent developer experience — adding a new utility follows the same pattern
- `UtilityType` enum is the single source of truth
- Tabbed multi-utility dashboard gives users unified view
- SEO engine generates ISR pages per state per utility (153 pages)
- CF Worker cache keys include `utility_type` for proper cache partitioning

### Negative
- More tables and migrations to maintain (6 utility-specific tables)
- Each utility needs its own data source integration
- Sidebar navigation is getting long (15 items)
- Water has no monetization path (monitoring-only, no switching)
- Test suite grows proportionally (39+ tests per utility type)

### Conventions
- Monopoly utilities (water) are monitoring-only — no "Switch" CTA
- Seasonal utilities (propane, heating oil) include timing advice
- `UtilityType` enum additions require: DB migration, backend service, API routes, frontend page, sidebar entry, SEO type
