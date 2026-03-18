# Implementation Plan: Wave 1 — Multi-Utility Schema Foundation

**Track ID:** mu-wave1-foundation_20260311
**Spec:** spec.md
**Created:** 2026-03-11
**Updated:** 2026-03-11 (refined after codebase audit)
**Status:** [x] Complete (2026-03-11)
**Execution Mode:** Loki RARV Cycles (Autonomous)
**Design Doc:** docs/plans/2026-03-11-multi-utility-expansion.md
**Blocked By:** mu-wave0-prereqs_20260311 (COMPLETE)

---

## Overview

Deploy the `utility_accounts` table (user-utility linking), referral system for
user growth, and PWA basics for mobile engagement. OM-001 (OpenTelemetry) is
handled by its own track.

### Codebase Audit Findings (2026-03-11)

The original plan assumed `utility_type` didn't exist on `electricity_prices`.
Audit revealed:

- **Migration 006** already added `utility_type` enum + column to
  `electricity_prices`, `suppliers`, and `tariffs`
- **`models/utility.py`** already defines `UtilityType` (5 types) and
  `PriceUnit` (12 units) with default mappings
- **`models/price.py`** already has `utility_type` and `unit` fields
- **`PriceRepository`** already queries with `utility_type` support

**Eliminated from plan:**
- ~~utility_prices VIEW~~ (utility_type is a real column, not needed)
- ~~utility_rates table~~ (electricity_prices already multi-utility)
- ~~UtilityRate model/repo~~ (PriceRepository already handles this)

**Migration numbering:** Latest deployed is 037. Next = **038**.

---

## Phase 1: Utility Accounts (MU-001a)

### Context

Users need to link their utility accounts (electricity provider, gas provider,
etc.) to get personalized rate comparisons. This table connects users to
specific utility types and providers.

**Existing patterns to follow:**
- Migrations: `IF NOT EXISTS`, UUID PK via `gen_random_uuid()`, `neondb_owner` GRANT
- Models: Pydantic `BaseModel` with `ConfigDict(from_attributes=True)` (not SQLAlchemy ORM)
- Repos: Extend `BaseRepository[T]`, use `text()` SQL, inject `AsyncSession`
- API: `APIRouter`, `Depends(get_current_user)` for auth, `Depends(get_timescale_session)` for DB
- Tests: `AsyncMock` DB session, `MagicMock` results, `@pytest.mark.asyncio`

### Tasks

- [x] Task 1.1: Create migration `038_utility_accounts.sql`
  - Table: `utility_accounts`
    - `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
    - `user_id UUID NOT NULL` (logical FK to users/neon_auth)
    - `utility_type utility_type NOT NULL` (reuse existing enum from migration 006)
    - `region VARCHAR(50) NOT NULL` (matches `electricity_prices.region` format)
    - `provider_name VARCHAR(200) NOT NULL`
    - `account_number_encrypted BYTEA` (AES-256-GCM, nullable — not all users have it)
    - `is_primary BOOLEAN NOT NULL DEFAULT FALSE`
    - `metadata JSONB DEFAULT '{}'`
    - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
    - `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
  - Indexes: `(user_id)`, `(user_id, utility_type)`, `(region, utility_type)`
  - Constraint: `UNIQUE(user_id, utility_type, provider_name)` (prevent duplicates)
  - GRANT to `neondb_owner`

- [x] Task 1.2: Create Pydantic model `models/utility_account.py`
  - `UtilityAccount(BaseModel)` — full model matching DB columns
  - `UtilityAccountCreate(BaseModel)` — request body (user_id auto-injected)
  - `UtilityAccountUpdate(BaseModel)` — partial update (all optional)
  - `UtilityAccountResponse(BaseModel)` — response (excludes encrypted fields)
  - Follow `models/price.py` patterns: `ConfigDict(from_attributes=True)`, UUID default factory

- [x] Task 1.3: Create `repositories/utility_account_repository.py`
  - Extend `BaseRepository[UtilityAccount]`
  - `__init__(self, db_session: AsyncSession)`
  - `get_by_id(id)` — single account
  - `create(entity)` — INSERT with RETURNING
  - `update(id, entity)` — partial UPDATE
  - `delete(id)` — DELETE by id
  - `list(page, page_size, **filters)` — paginated list
  - `count(**filters)` — count matching
  - `get_by_user(user_id)` — all accounts for a user
  - `get_by_user_and_type(user_id, utility_type)` — filtered by utility type
  - Raw SQL with `text()` (matches PriceRepository pattern)

- [x] Task 1.4: Register repository in `repositories/__init__.py`
  - Import `UtilityAccountRepository`
  - Add to `__all__`

- [x] Task 1.5: Create API router `api/v1/utility_accounts.py`
  - `GET /utility-accounts` — list current user's accounts (auth required)
  - `POST /utility-accounts` — create account (auth required, inject user_id from session)
  - `PUT /utility-accounts/{id}` — update account (auth required, ownership check)
  - `DELETE /utility-accounts/{id}` — delete account (auth required, ownership check)
  - `GET /utility-accounts/types` — list available UtilityType values (public)
  - Use `Depends(get_current_user)` and `Depends(get_timescale_session)`
  - Follow `api/v1/user.py` router pattern

- [x] Task 1.6: Register router in `main.py`
  - Mount at `/api/v1/utility-accounts`

- [x] Task 1.7: Write tests `tests/test_utility_accounts.py`
  - Repository tests: CRUD, get_by_user, get_by_user_and_type, uniqueness constraint
  - API endpoint tests: auth required, create/read/update/delete, ownership enforcement
  - Model tests: validation, defaults, serialization
  - Target: 15-20 tests

### Verification
- [x] Migration 038 applies cleanly
- [x] All CRUD operations work through API
- [x] Ownership enforcement prevents cross-user access
- [x] All existing tests still pass
- [x] New tests pass

---

## Phase 2: Referral System (UG-001)

### Context

Referral codes for user growth. Double-sided incentive: referrer gets credit,
referee gets extended trial. All tiers eligible. No Stripe integration yet
(reward tracking only, redemption in Wave 3).

### Tasks

- [x] Task 2.1: Create migration `039_referrals.sql`
  - Table: `referrals`
    - `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
    - `referrer_id UUID NOT NULL` (user who shares)
    - `referee_id UUID` (user who signs up, nullable until completion)
    - `referral_code VARCHAR(12) NOT NULL UNIQUE`
    - `status VARCHAR(20) NOT NULL DEFAULT 'pending'` CHECK (pending/completed/expired)
    - `reward_applied BOOLEAN NOT NULL DEFAULT FALSE`
    - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
    - `completed_at TIMESTAMPTZ`
  - Indexes: `(referral_code)`, `(referrer_id)`, `(referee_id)`
  - GRANT to `neondb_owner`

- [x] Task 2.2: Create `services/referral_service.py`
  - `ReferralService(db: AsyncSession)`
  - `generate_code(user_id)` — 8-char alphanumeric, retry on collision, store with referrer_id
  - `get_or_create_code(user_id)` — return existing or generate new
  - `apply_referral(referee_id, code)` — validate code exists + pending, set referee_id
  - `complete_referral(referee_id)` — mark complete, set completed_at, set reward_applied=True
  - `get_stats(user_id)` — {total, pending, completed, reward_credits}
  - `get_referral_by_code(code)` — lookup for validation
  - Raw SQL with `text()`, same pattern as MaintenanceService

- [x] Task 2.3: Create `api/v1/referrals.py`
  - `GET /referrals/code` — get or generate user's referral code (auth required)
  - `POST /referrals/apply` — apply referral code (auth required, body: {code: str})
  - `GET /referrals/stats` — referral dashboard data (auth required)
  - Register in `main.py` at `/api/v1/referrals`

- [x] Task 2.4: Write tests `tests/test_referral_service.py`
  - Code generation: uniqueness, format (8 chars alphanumeric)
  - Apply flow: valid code, already-used code, self-referral blocked, nonexistent code
  - Complete flow: status transition, reward_applied flag, completed_at set
  - Stats: correct counts
  - API: auth, validation, responses
  - Target: 15-20 tests

### Verification
- [x] Migration 039 applies cleanly
- [x] Referral codes generate as 8-char alphanumeric
- [x] Apply -> complete flow works
- [x] Self-referral blocked
- [x] All tests pass

---

## Phase 3: PWA Basics (UG-005)

### Context

Progressive Web App support for mobile engagement. Service worker for offline
rate caching, web manifest for install prompt, OneSignal web push integration.
Next.js 16 uses App Router — no `_app.tsx`.

### Tasks

- [x] Task 3.1: Add web manifest
  - Create `frontend/public/manifest.json` with:
    - `name: "RateShift"`, `short_name: "RateShift"`, `display: "standalone"`
    - `theme_color`, `background_color` matching brand
    - Icon refs (192x192, 512x512) — use existing or create placeholder PNGs
  - Add manifest link in root layout `<head>` via Next.js metadata API

- [x] Task 3.2: Create service worker `frontend/public/sw.js`
  - Cache static assets on install (App Shell pattern)
  - Network-first strategy for `/api/v1/prices/*` — fall back to cached stale data
  - Cache-first for static assets (JS/CSS/images)
  - Version-based cache busting on update
  - Register in root layout via `useEffect` in a client component

- [x] Task 3.3: Create install prompt component
  - `frontend/src/components/InstallPrompt.tsx`
  - Listen for `beforeinstallprompt` event
  - Show dismissible banner after 2nd visit (localStorage counter)
  - Track install acceptance/dismissal

- [x] Task 3.4: OneSignal web push setup
  - Add OneSignal web SDK init to root layout (already have OneSignal for mobile)
  - Permission prompt on settings page (not intrusive — button, not auto-popup)
  - Wire `userId` binding post-login (matches existing mobile pattern)

- [x] Task 3.5: Write PWA tests
  - Manifest: valid JSON, required fields present
  - Service worker: registration logic test
  - InstallPrompt: render, dismiss, visit counter

### Verification
- [x] `manifest.json` valid and linked in HTML head
- [x] Service worker registers successfully
- [x] Install prompt shows on 2nd visit (mobile Chrome)
- [x] OneSignal web push permission requestable
- [x] All tests pass

---

## Phase 4: Integration & Final Validation

### Tasks

- [x] Task 4.1: Run full backend test suite — zero regressions
- [x] Task 4.2: Run full frontend test suite — zero regressions
- [x] Task 4.3: Update conductor track status
- [x] Task 4.4: Update DSP graph with new entities (utility_account model, referral service, etc.)

### Verification
- [x] All backend tests pass (2,032+ existing + ~35 new)
- [x] All frontend tests pass (1,475+ existing + ~5 new)
- [x] Migrations 038-039 ready for deployment
- [x] Existing electricity functionality unaffected
- [x] Wave 2 unblocked

---

_Generated by Conductor. Refined 2026-03-11 after codebase audit._
_Tasks will be marked [~] in progress and [x] complete._
