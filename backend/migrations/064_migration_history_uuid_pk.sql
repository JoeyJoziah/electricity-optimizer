-- Migration 064: Convert migration_history PK from SERIAL to UUID
-- Fixes convention violation: all tables must use UUID primary keys.
--
-- Strategy: Add UUID column, populate it, swap PK, drop SERIAL column.
-- Idempotent: IF NOT EXISTS / IF EXISTS guards throughout.

-- 1. Add UUID column if it doesn't exist
ALTER TABLE migration_history ADD COLUMN IF NOT EXISTS uuid_id UUID DEFAULT gen_random_uuid();

-- 2. Backfill UUIDs for any rows with NULL uuid_id
UPDATE migration_history SET uuid_id = gen_random_uuid() WHERE uuid_id IS NULL;

-- 3. Drop the old PK constraint (SERIAL-based)
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'migration_history_pkey'
          AND conrelid = 'migration_history'::regclass
    ) THEN
        ALTER TABLE migration_history DROP CONSTRAINT migration_history_pkey;
    END IF;
END $$;

-- 4. Set uuid_id as the new PK
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'migration_history_pkey'
          AND conrelid = 'migration_history'::regclass
    ) THEN
        ALTER TABLE migration_history ADD CONSTRAINT migration_history_pkey PRIMARY KEY (uuid_id);
    END IF;
END $$;

-- 5. Make uuid_id NOT NULL with a default
ALTER TABLE migration_history ALTER COLUMN uuid_id SET NOT NULL;
ALTER TABLE migration_history ALTER COLUMN uuid_id SET DEFAULT gen_random_uuid();

-- 6. Drop the old SERIAL id column
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'migration_history'
          AND column_name = 'id'
          AND table_schema = 'public'
          AND data_type = 'integer'
    ) THEN
        ALTER TABLE migration_history DROP COLUMN id;
    END IF;
END $$;

-- 7. Rename uuid_id to id
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'migration_history'
          AND column_name = 'uuid_id'
          AND table_schema = 'public'
    ) THEN
        ALTER TABLE migration_history RENAME COLUMN uuid_id TO id;
    END IF;
END $$;

-- 8. Drop the old sequence if it exists (orphaned by SERIAL removal)
DROP SEQUENCE IF EXISTS migration_history_id_seq;

-- 9. Ensure grants remain correct
GRANT SELECT, INSERT, UPDATE, DELETE ON migration_history TO neondb_owner;

-- 10. Record this migration
INSERT INTO migration_history (migration_name, applied_by)
VALUES ('064_migration_history_uuid_pk', 'migration')
ON CONFLICT DO NOTHING;
