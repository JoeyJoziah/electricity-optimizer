-- =============================================================================
-- Migration 035: Backfill public.users from neon_auth.user
-- Date: 2026-03-10
-- =============================================================================
--
-- PROBLEM
-- -------
-- 16 accounts exist in neon_auth.user (managed by Better Auth) but only 2
-- have a corresponding row in public.users (the application user table).
-- The remaining 14 authenticated users cannot use any application feature
-- because all endpoints query public.users by id.
--
-- ROOT CAUSE
-- ----------
-- The public.users sync (ensure_user_profile) was only triggered from
-- GET /api/v1/auth/me.  Users who authenticated via OAuth, magic link,
-- or before that endpoint was wired up never called /auth/me, so their
-- public.users row was never created.
--
-- Additionally, the original init_neon.sql schema had:
--   name   VARCHAR(200) NOT NULL
--   region VARCHAR(50)  NOT NULL
-- The ensure_user_profile INSERT supplied NULL for region, causing silent
-- failures (the exception was swallowed) for any users who signed up before
-- migration 018 dropped the NOT NULL constraint on region.
--
-- FIX
-- ---
-- This migration does a one-time backfill.  It is safe to run multiple
-- times because it uses INSERT ... ON CONFLICT DO UPDATE with a WHERE
-- clause that only fires when data actually differs.
--
-- COMPANION CHANGES (deployed alongside this migration)
-- -------------------------------------------------------
-- 1. backend/auth/neon_auth.py — ensure_user_profile upserts email/name
--    changes and returns a bool indicating whether a row was created.
-- 2. backend/api/v1/users.py  — GET /users/profile triggers on-demand sync
--    instead of returning 404 when the row is missing.
-- 3. frontend/lib/hooks/useAuth.tsx — fires GET /auth/me after every
--    successful sign-in (email/password and session restore) to eagerly
--    create the public.users row before the user reaches the dashboard.
-- 4. backend/api/v1/internal/sync.py — POST /internal/sync-users endpoint
--    for future admin-triggered bulk re-syncs.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Step 1: Insert missing users
-- ---------------------------------------------------------------------------
-- For every account in neon_auth.user that has no matching row in
-- public.users, insert a skeleton row.
--
-- Columns set here:
--   id           — copied verbatim from neon_auth.user.id (UUID)
--   email        — lowercased to match the application convention
--   name         — COALESCE to '' to satisfy the NOT NULL constraint that
--                  exists in environments that predate migration 018
--   region       — NULL (user picks region during onboarding)
--   is_active    — true
--   created_at   — approximate using neon_auth.user."createdAt"
--   updated_at   — NOW()

INSERT INTO public.users (id, email, name, region, is_active, created_at, updated_at)
SELECT
    u.id::uuid,
    lower(u.email),
    COALESCE(u.name, ''),
    NULL,           -- region: user sets this during onboarding
    true,
    u."createdAt",  -- preserve original signup timestamp
    NOW()
FROM neon_auth."user" u
WHERE NOT EXISTS (
    SELECT 1 FROM public.users pu WHERE pu.id = u.id::uuid
);

-- ---------------------------------------------------------------------------
-- Step 2: Update email/name for rows that already exist but are stale
-- ---------------------------------------------------------------------------
-- Users may have changed their email or display name in the identity provider.
-- This updates only the fields that differ to avoid unnecessary writes.

UPDATE public.users pu
SET
    email      = lower(nu.email),
    name       = CASE
                     WHEN nu.name IS NOT NULL AND nu.name <> ''
                     THEN nu.name
                     ELSE pu.name
                 END,
    updated_at = NOW()
FROM neon_auth."user" nu
WHERE pu.id = nu.id::uuid
  AND (
      pu.email <> lower(nu.email)
      OR (nu.name IS NOT NULL AND nu.name <> '' AND pu.name <> nu.name)
  );

-- ---------------------------------------------------------------------------
-- Step 3: Sanity check — log counts (visible in migration output)
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    neon_count  INT;
    app_count   INT;
    missing     INT;
BEGIN
    SELECT COUNT(*) INTO neon_count FROM neon_auth."user";
    SELECT COUNT(*) INTO app_count  FROM public.users;

    -- Users in neon_auth but still missing from public.users after the
    -- backfill (should be 0; non-zero means a constraint or permission error)
    SELECT COUNT(*) INTO missing
    FROM neon_auth."user" u
    WHERE NOT EXISTS (
        SELECT 1 FROM public.users pu WHERE pu.id = u.id::uuid
    );

    RAISE NOTICE 'Migration 035 complete.';
    RAISE NOTICE '  neon_auth.user rows : %', neon_count;
    RAISE NOTICE '  public.users rows   : %', app_count;
    RAISE NOTICE '  Still missing       : %', missing;

    IF missing > 0 THEN
        RAISE WARNING 'Some neon_auth users could not be backfilled (count=%). Check constraints or permissions.', missing;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------
DO $$ BEGIN
    GRANT SELECT, INSERT, UPDATE ON public.users TO neondb_owner;
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'neondb_owner role not found, skipping grant';
END $$;
