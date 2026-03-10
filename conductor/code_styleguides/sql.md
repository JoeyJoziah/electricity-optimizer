# SQL Style Guide

Conventions for Neon PostgreSQL migrations and queries.

## Migrations

### File Naming

Sequential numbering: `NNN_description.sql` (e.g., `025_data_cache_tables.sql`)

### Required Patterns

1. **`IF NOT EXISTS`** on all `CREATE TABLE` and `CREATE INDEX` statements
2. **`GRANT` to `neondb_owner`** on all new tables
3. **UUID primary keys** -- never use `SERIAL` or `BIGSERIAL`
4. **Idempotent** -- migrations must be safe to re-run

```sql
-- Good
CREATE TABLE IF NOT EXISTS weather_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region VARCHAR(10) NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_weather_cache_region
    ON weather_cache(region);

GRANT ALL ON weather_cache TO neondb_owner;

-- Bad
CREATE TABLE weather_cache (            -- missing IF NOT EXISTS
    id SERIAL PRIMARY KEY,              -- no SERIAL, use UUID
    region TEXT,                         -- use VARCHAR with length
    data JSON                           -- prefer JSONB
);
```

### Column Conventions

| Type | Convention |
|------|-----------|
| Primary key | `id UUID PRIMARY KEY DEFAULT gen_random_uuid()` |
| Timestamps | `TIMESTAMPTZ DEFAULT NOW()` |
| Foreign keys | `UUID REFERENCES parent_table(id)` |
| Strings | `VARCHAR(N)` with explicit length |
| JSON data | `JSONB` (not `JSON`) |
| Booleans | `BOOLEAN DEFAULT false` |
| Money | `NUMERIC(10,2)` (never `FLOAT`) |

### Nullability

Pydantic models MUST match DDL nullability. If a column is `NOT NULL` in the migration, the corresponding Pydantic field must not be `Optional`.

## Queries

### Quoting

- Use double quotes for `neon_auth` schema identifiers: `neon_auth.session."updatedAt"`
- Standard snake_case columns in `public` schema do not need quoting

### Performance

- Use parameterized queries (`$1`, `$2` or `:param`) -- never string interpolation
- Batch inserts via single multi-row `INSERT` (chunked at 500 rows)
- Add indexes for columns used in WHERE, JOIN, ORDER BY

### Data Retention

- Use PL/pgSQL functions: `cleanup_old_X(retention_days DEFAULT N)`
- No pg_cron on Neon -- scheduled via external GHA cron
