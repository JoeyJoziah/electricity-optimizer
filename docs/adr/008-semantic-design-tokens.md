# ADR-008: Semantic Design Token Strategy

**Status**: Accepted
**Date**: 2026-03-16
**Decision Makers**: Devin McGrath

## Context

RateShift's frontend grew organically from a single-utility electricity app to a multi-utility dashboard (electricity, gas, water, propane, heating oil, community solar). Many components used raw Tailwind color classes (`bg-blue-600`, `text-green-500`, `bg-red-100`) directly, creating problems:

- Theme changes required find-and-replace across dozens of files
- New utility types (water, propane) introduced ad-hoc color choices (`cyan-*`, `amber-*`)
- Inconsistent color usage for semantic concepts (success, warning, danger)
- Dark mode support would require touching every component

## Decision

Define **semantic design tokens** in `tailwind.config.ts` and use them exclusively in components:

| Token Family | Purpose | Example Classes |
|-------------|---------|-----------------|
| `primary-*` | Brand actions, links, active states | `bg-primary-600`, `text-primary-500` |
| `success-*` | Savings, positive trends, confirmations | `bg-success-100`, `text-success-700` |
| `warning-*` | Cautions, moderate alerts, pending states | `bg-warning-100`, `text-warning-700` |
| `danger-*` | Errors, critical alerts, destructive actions | `bg-danger-100`, `text-danger-700` |

### Rules
1. **Never use raw color classes** (`blue-*`, `green-*`, `red-*`) in components for semantic meaning
2. **Map utility types to tokens**: electricity = `primary`, gas = `warning`, water = add `utility.water` token if distinct branding is needed
3. **Neutral grays are exempt**: `gray-*` / `slate-*` for backgrounds, borders, and text are acceptable
4. **One-off accent colors** must be defined as tokens in `tailwind.config.ts`, not inlined

## Consequences

### Positive
- Single source of truth for all semantic colors in `tailwind.config.ts`
- Theme changes (including dark mode) require editing one file
- New contributors immediately know which token to use for each semantic concept
- Consistent visual language across all utility dashboards

### Negative
- Existing components need gradual migration (not a blocking change)
- Slightly more indirection: developers must check token definitions
- Some third-party component styles may need overrides
- Tailwind IntelliSense must be configured to recognize custom tokens

### Migration Path
- New components must use semantic tokens (enforced in code review)
- Existing components are migrated opportunistically during feature work
- No automated linting yet (potential future ESLint rule)
