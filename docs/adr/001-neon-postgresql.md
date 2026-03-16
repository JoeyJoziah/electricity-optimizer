# ADR-001: Neon PostgreSQL as Primary Database

**Status**: Accepted
**Date**: 2026-02-15
**Decision Makers**: Devin McGrath

## Context

RateShift needed a production PostgreSQL database that supports:
- Serverless scale-to-zero for cost efficiency during early growth
- Database branching for preview deployments and safe migrations
- Built-in authentication integration (to avoid managing a separate auth DB)
- Connection pooling for serverless/edge environments

Options considered: Neon, Supabase, PlanetScale (MySQL), AWS RDS, Railway.

## Decision

Use **Neon PostgreSQL** (project `cold-rice-23455092`) as the sole database.

- **Pooled endpoint** (`ep-withered-morning-aix83cfw-pooler`) for application connections
- **Direct endpoint** (`ep-withered-morning-aix83cfw`) for migrations only
- **Branches**: `production` (default), `vercel-dev` (preview deployments)
- **Auth**: Neon Auth integration with Better Auth (9 `neon_auth` schema tables)

## Consequences

### Positive
- Scale-to-zero reduces costs during low-traffic periods
- Database branching enables safe schema testing on PRs
- Neon Auth provides session, account, verification tables out-of-the-box
- Connection pooling via PgBouncer built-in

### Negative
- UUID primary keys required (all 44 public tables use UUID PKs)
- `neondb_owner` role must be used for all GRANTs in migrations
- No `SERIAL` columns — use `gen_random_uuid()` defaults
- Cold starts possible on scale-to-zero (mitigated by CF Worker caching)
- `neon_auth` schema is managed by Better Auth — do not modify directly

### Conventions Established
- All migrations use `IF NOT EXISTS` for idempotency
- Sequential migration numbering (000-049)
- `validate-migrations` composite action enforces conventions in CI
