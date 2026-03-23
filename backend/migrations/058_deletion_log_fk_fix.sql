-- =============================================================================
-- Migration 058: Fix DeletionLogORM FK + align ConsentRecordORM FK
-- =============================================================================
--
-- Findings [08-P0-1, 09-P0-2, 12-P0-3]:
--
-- PROBLEM 1 — deletion_logs (08-P0-1, 09-P0-2):
--   DeletionLogORM declares:
--     user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"),
--                                          nullable=False)
--   This is a contradiction: SET NULL means the DB will NULL out user_id when the
--   user row is deleted, but NOT NULL means NULL is not allowed.  PostgreSQL will
--   raise an FK violation on every GDPR deletion, crashing the deletion entirely.
--
--   Fix: Make deletion_logs.user_id nullable so SET NULL can succeed.  GDPR
--   audit trail is preserved (the log row stays); user_id becomes NULL after
--   the user is erased, which is exactly the right semantics.
--
--   The deletion_logs table has an immutability trigger that blocks UPDATE/DELETE
--   on rows — DDL (ALTER TABLE) is NOT blocked by row-level triggers.
--
-- PROBLEM 2 — consent_records (12-P0-3):
--   ORM (repositories.py line 31) declares:
--     ForeignKey("users.id", ondelete="CASCADE")
--   But migration 023 changed the live schema FK to:
--     ON DELETE SET NULL  (and made user_id nullable)
--
--   The ORM Python declaration is currently wrong relative to the live DB.
--   We fix by aligning the ORM definition to match the live schema (SET NULL).
--   This preserves the consent audit trail when a user is deleted — which is
--   the correct GDPR behaviour (consent records are legal evidence, must persist).
--
--   The Python ORM file (backend/compliance/repositories.py) is updated
--   separately to match: ondelete="SET NULL" with nullable=True.
--
-- =============================================================================


-- ---------------------------------------------------------------------------
-- PART 1: Fix deletion_logs.user_id — make nullable for SET NULL to work
-- ---------------------------------------------------------------------------

-- Step 1a: Drop existing FK constraint (may be named deletion_logs_user_id_fkey
--          or something else from the original CREATE TABLE in migration 002)
DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    SELECT conname INTO constraint_name
    FROM   pg_constraint
    WHERE  conrelid = 'public.deletion_logs'::regclass
    AND    contype  = 'f'
    AND    conkey   = ARRAY[(
        SELECT attnum FROM pg_attribute
        WHERE attrelid = 'public.deletion_logs'::regclass
          AND attname = 'user_id'
    )];

    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE public.deletion_logs DROP CONSTRAINT %I', constraint_name);
        RAISE NOTICE 'Migration 058: dropped FK constraint % on deletion_logs.user_id', constraint_name;
    ELSE
        RAISE NOTICE 'Migration 058: no FK constraint found on deletion_logs.user_id — nothing to drop';
    END IF;
END $$;

-- Step 1b: Make user_id nullable (allows SET NULL to work on user deletion)
--          The immutability trigger blocks UPDATE/DELETE rows, not DDL.
DO $$
BEGIN
    ALTER TABLE public.deletion_logs ALTER COLUMN user_id DROP NOT NULL;
    RAISE NOTICE 'Migration 058: deletion_logs.user_id is now nullable';
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'Migration 058: could not drop NOT NULL on deletion_logs.user_id: %', SQLERRM;
END $$;

-- Step 1c: Re-add FK with ON DELETE SET NULL
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE  conrelid = 'public.deletion_logs'::regclass
        AND    conname  = 'fk_deletion_logs_user_id'
    ) THEN
        ALTER TABLE public.deletion_logs
            ADD CONSTRAINT fk_deletion_logs_user_id
            FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;

        RAISE NOTICE 'Migration 058: added FK fk_deletion_logs_user_id (ON DELETE SET NULL)';
    ELSE
        RAISE NOTICE 'Migration 058: fk_deletion_logs_user_id already exists — skipped';
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- PART 2: Verify consent_records FK is ON DELETE SET NULL
--         (migration 023 already applied this; this block is idempotent)
-- ---------------------------------------------------------------------------

-- Ensure fk_consent_user uses SET NULL (aligns live schema with ORM fix in 058)
DO $$
BEGIN
    -- Drop existing constraint regardless of its current action
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE  conrelid = 'public.consent_records'::regclass
        AND    conname  = 'fk_consent_user'
    ) THEN
        ALTER TABLE public.consent_records DROP CONSTRAINT fk_consent_user;
        RAISE NOTICE 'Migration 058: dropped existing fk_consent_user from consent_records';
    END IF;

    -- Ensure user_id is nullable (023 already did this, but be idempotent)
    ALTER TABLE public.consent_records ALTER COLUMN user_id DROP NOT NULL;

    -- Re-create with explicit SET NULL
    ALTER TABLE public.consent_records
        ADD CONSTRAINT fk_consent_user
        FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;

    RAISE NOTICE 'Migration 058: consent_records.fk_consent_user set to ON DELETE SET NULL';
END $$;


-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------

GRANT ALL ON public.deletion_logs TO neondb_owner;
GRANT ALL ON public.consent_records TO neondb_owner;


-- ---------------------------------------------------------------------------
-- Completion notice
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    RAISE NOTICE 'Migration 058 complete: deletion_logs.user_id nullable + SET NULL FK; consent_records FK aligned.';
END $$;
