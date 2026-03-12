# Implementation Plan: Wave 5 — Unified Dashboard, Community & Security Hardening

**Track ID:** mu-wave5-unification_20260311
**Spec:** spec.md
**Created:** 2026-03-11
**Status:** [~] In Progress
**Execution Mode:** TDD (Red-Green-Refactor)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify all utility types into a tabbed dashboard, launch community features with AI moderation, and harden security for the expanded attack surface.

**Architecture:** Frontend-First Composition (D7). Dashboard composes existing React Query hooks client-side. New backend only for community CRUD, combined savings aggregation, and neighborhood comparison. AI moderation uses Groq (primary, dedicated `classify_content()` non-streaming) with Gemini fallback; fail-closed with 30s timeout.

**Tech Stack:** FastAPI + SQLAlchemy (backend), Next.js + React Query + Tailwind (frontend), nh3 (XSS, Rust-based), OWASP ZAP (security scanning, weekly), pip-audit + npm audit (dependency scanning), Groq (AI moderation primary) + Gemini (fallback)

---

## Phase 1: Database & Backend Foundation

Create the community tables and core backend services. No frontend yet.

### Tasks

- [x] Task 1.1: Write migration 049 — `community_posts`, `community_votes`, and `community_reports` tables
  - **Files:** Create `backend/migrations/049_community_tables.sql`
  - **Pre-step:** Run on `vercel-dev` branch first to validate before production
  - **Schema:**
    ```sql
    -- Migration 049: Community tables (3 new tables, 42 → 45 total)
    CREATE TABLE IF NOT EXISTS community_posts (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id UUID NOT NULL REFERENCES users(id),
      region VARCHAR(50) NOT NULL,
      utility_type VARCHAR(30) NOT NULL CHECK (utility_type IN (
        'electricity', 'natural_gas', 'heating_oil', 'propane',
        'community_solar', 'water', 'general'
      )),
      post_type VARCHAR(20) NOT NULL CHECK (post_type IN ('tip', 'rate_report', 'discussion', 'review')),
      title TEXT NOT NULL,
      body TEXT NOT NULL,
      rate_per_unit NUMERIC(10,6),
      rate_unit VARCHAR(10),
      supplier_name TEXT,
      is_hidden BOOLEAN DEFAULT false,
      is_pending_moderation BOOLEAN DEFAULT true,
      hidden_reason TEXT,
      created_at TIMESTAMPTZ DEFAULT now(),
      updated_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS community_votes (
      user_id UUID NOT NULL REFERENCES users(id),
      post_id UUID NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
      created_at TIMESTAMPTZ DEFAULT now(),
      PRIMARY KEY (user_id, post_id)
    );

    CREATE TABLE IF NOT EXISTS community_reports (
      user_id UUID NOT NULL REFERENCES users(id),
      post_id UUID NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
      reason TEXT,
      created_at TIMESTAMPTZ DEFAULT now(),
      PRIMARY KEY (user_id, post_id)
    );

    -- Composite index for filtered queries
    CREATE INDEX IF NOT EXISTS idx_community_posts_region_utility
      ON community_posts (region, utility_type, created_at DESC)
      WHERE is_hidden = false;

    -- Updated_at trigger (reuse pattern from existing tables)
    CREATE OR REPLACE FUNCTION update_community_posts_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
      NEW.updated_at = now();
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER trg_community_posts_updated_at
      BEFORE UPDATE ON community_posts
      FOR EACH ROW EXECUTE FUNCTION update_community_posts_updated_at();

    -- Grants
    GRANT ALL ON community_posts TO neondb_owner;
    GRANT ALL ON community_votes TO neondb_owner;
    GRANT ALL ON community_reports TO neondb_owner;
    ```
  - **Conventions:** UUID PKs, `neondb_owner` GRANT, `IF NOT EXISTS`, VARCHAR(50) for region (not enum type), CHECK constraints for utility_type and post_type, no denormalized counters (upvotes/report_count derived via COUNT queries), composite PK dedup on votes and reports
  - **Note:** `upvotes` and `report_count` are NOT stored — they are derived via `COUNT(*)` on `community_votes` and `community_reports` tables respectively. This prevents counter drift.
  - **Verify:** Migration runs against vercel-dev branch first, then production

- [x] Task 1.2: Create SQLAlchemy models for `community_posts`, `community_votes`, and `community_reports`
  - **Files:** Create `backend/models/community.py`
  - **Models:** `CommunityPost`, `CommunityVote`, `CommunityReport`
  - **Fields:** `region` as `String(50)` (not Enum type), `utility_type` as `String(30)`, `rate_per_unit` + `rate_unit` (not `rate_kwh`), `is_pending_moderation` boolean
  - **No denormalized fields:** `upvotes` and `report_count` are NOT model columns — derive via relationship counts or subqueries
  - **Conventions:** Match existing model patterns (UUID type, mapped_column, relationship)
  - **Verify:** Models importable, no circular imports

- [x] Task 1.3: Write failing tests for `CommunityService`
  - **Files:** Create `backend/tests/test_community_service.py`
  - **Tests (~20):**
    - `test_create_post_success` — returns post with UUID id, `is_pending_moderation=true`
    - `test_create_post_sanitizes_xss` — `<script>` tags stripped from title/body via nh3
    - `test_create_post_triggers_moderation` — calls Groq classify_content, sets is_pending_moderation
    - `test_create_post_fail_closed` — post hidden until AI classifies or 30s timeout
    - `test_create_post_timeout_auto_unhides` — 30s timeout → `is_pending_moderation=false`
    - `test_list_posts_paginated` — returns page of posts, excludes hidden and pending
    - `test_list_posts_filters_by_region_and_utility`
    - `test_list_posts_empty_page` — returns empty list, not error
    - `test_vote_toggle_idempotent` — voting twice removes vote (composite PK dedup)
    - `test_vote_count_derived` — upvote count is COUNT(*) on community_votes, not stored column
    - `test_report_post_deduplicates` — same user reporting twice is idempotent (composite PK)
    - `test_report_post_hides_at_threshold` — 5 unique reports → `is_hidden=true`
    - `test_report_post_different_users_required` — verifies 5 different users needed
    - `test_moderation_hides_flagged_post` — Groq returns "flagged" → hidden
    - `test_moderation_groq_fallback_to_gemini` — Groq 429 → tries Gemini
    - `test_moderation_both_fail_timeout_unhides` — both fail → 30s timeout unhides
    - `test_retroactive_remoderation` — recovered service re-checks timed-out posts
    - `test_flagged_post_edit_resubmit` — author can edit and resubmit flagged post
    - `test_community_stats` — returns total_users, avg_savings_pct, top_tip with attribution
    - `test_rate_limit_posts` — 11th post in an hour returns 429
  - **Run:** `.venv/bin/python -m pytest tests/test_community_service.py -v`
  - **Expected:** All FAIL (service not implemented)

- [x] Task 1.4: Implement `CommunityService`
  - **Files:** Create `backend/services/community_service.py`
  - **Methods:**
    - `create_post(db, user_id, data) -> CommunityPost` — sanitize with nh3, persist with `is_pending_moderation=true`, fire moderation
    - `list_posts(db, region, utility_type, page, per_page) -> list[CommunityPost]` — paginated, exclude hidden AND pending moderation, include derived vote counts via subquery
    - `toggle_vote(db, user_id, post_id) -> bool` — insert or delete from community_votes (composite PK dedup), no stored counter
    - `report_post(db, user_id, post_id, reason) -> None` — insert into community_reports (composite PK dedup), hide if COUNT >= 5
    - `moderate_post(db, post_id, agent_service) -> None` — call Groq `classify_content()` (non-streaming), fallback to Gemini on 429, set is_hidden on "flagged", set is_pending_moderation=false on success; 30s timeout auto-unhides
    - `retroactive_moderate(db, agent_service) -> int` — re-check posts where is_pending_moderation=false AND moderation timed out
    - `edit_and_resubmit(db, user_id, post_id, data) -> CommunityPost` — allow author to edit flagged post, re-sanitize, re-trigger moderation
    - `get_stats(db, region) -> dict` — aggregate query for social proof stats with attribution (user count, date range)
  - **Dependencies:** `nh3` (add to requirements.txt)
  - **Run:** `.venv/bin/python -m pytest tests/test_community_service.py -v`
  - **Expected:** All PASS

- [x] Task 1.5: Write failing tests for `SavingsAggregator`
  - **Files:** Create `backend/tests/test_savings_aggregator.py`
  - **Tests (~6):**
    - `test_combined_savings_single_utility`
    - `test_combined_savings_multiple_utilities`
    - `test_combined_savings_no_data_returns_zero`
    - `test_savings_breakdown_per_utility`
    - `test_savings_rank_percentile`
    - `test_combined_savings_skips_disabled_flags`
  - **Run:** `.venv/bin/python -m pytest tests/test_savings_aggregator.py -v`
  - **Expected:** All FAIL

- [x] Task 1.6: Implement `SavingsAggregator`
  - **Files:** Create `backend/services/savings_aggregator.py`
  - **Methods:**
    - `get_combined_savings(db, user_id) -> CombinedSavings` — calls each utility's existing savings calc, aggregates
    - Returns: `{ total_monthly_savings, breakdown: [{utility_type, savings}], savings_rank_pct }`
  - **Extend:** `optimization_report_service.py` if needed for per-utility savings extraction
  - **Run:** `.venv/bin/python -m pytest tests/test_savings_aggregator.py -v`
  - **Expected:** All PASS

- [x] Task 1.7: Write failing tests for `NeighborhoodService`
  - **Files:** Create `backend/tests/test_neighborhood_service.py`
  - **Tests (~5):**
    - `test_comparison_returns_percentile`
    - `test_comparison_null_when_insufficient_data` — < 5 users → null fields
    - `test_comparison_cheapest_supplier`
    - `test_comparison_potential_savings`
    - `test_comparison_by_utility_type`
  - **Run:** `.venv/bin/python -m pytest tests/test_neighborhood_service.py -v`
  - **Expected:** All FAIL

- [x] Task 1.8: Implement `NeighborhoodService`
  - **Files:** Create `backend/services/neighborhood_service.py`
  - **Methods:**
    - `get_comparison(db, user_id, region, utility_type) -> NeighborhoodComparison`
    - Uses `PERCENT_RANK()` window function over rates in region
    - Returns null fields when < 5 users in region
  - **Run:** `.venv/bin/python -m pytest tests/test_neighborhood_service.py -v`
  - **Expected:** All PASS

- [x] Task 1.9: Commit Phase 1
  - **Run:** Full backend suite `.venv/bin/python -m pytest -v --tb=short`
  - **Expected:** All pass, zero regressions
  - **Commit:** `feat(community): add community tables, services, and savings aggregator (mu-wave5)`

### Verification

- [x] Migration 049 creates 3 tables (community_posts, community_votes, community_reports) with correct constraints
- [x] Migration validated on vercel-dev branch before production
- [x] CommunityService: 20 tests passing
- [x] SavingsAggregator: 6 tests passing
- [x] NeighborhoodService: 5 tests passing
- [x] Full backend suite green (no regressions) — 2462 passed, 0 failed

---

## Phase 2: Community & Savings API Routes

Wire services into FastAPI routes with auth, rate limiting, and validation.

### Tasks

- [x] Task 2.1: Write failing tests for community API routes
  - **Files:** Create `backend/tests/test_community_api.py`
  - **Tests (~10):**
    - `test_create_post_authenticated` — 201 with valid payload
    - `test_create_post_unauthenticated` — 401
    - `test_create_post_invalid_type` — 422
    - `test_list_posts_with_filters` — 200 with region + utility_type query params
    - `test_list_posts_pagination` — page=2 returns next set
    - `test_vote_toggle` — 200, toggles
    - `test_vote_unauthenticated` — 401
    - `test_report_post` — 200, inserts into community_reports
    - `test_report_post_duplicate` — 200 idempotent (composite PK)
    - `test_community_stats` — 200 with aggregated data + attribution
    - `test_rate_limit_exceeded` — 429 after 10 posts/hour
    - `test_edit_resubmit_flagged_post` — 200, author can edit flagged post
  - **Run:** `.venv/bin/python -m pytest tests/test_community_api.py -v`
  - **Expected:** All FAIL

- [x] Task 2.2: Implement community API routes
  - **Files:** Create `backend/api/v1/community.py`
  - **Routes:**
    - `GET /community/posts` — query params: region, utility_type, page (default 1), per_page (default 20)
    - `POST /community/posts` — body: { title, body, utility_type, region, post_type, rate_per_unit?, rate_unit?, supplier_name? }
    - `PUT /community/posts/{id}` — edit/resubmit flagged post (author only)
    - `POST /community/posts/{id}/vote` — toggle upvote
    - `POST /community/posts/{id}/report` — flag for review (body: { reason? })
    - `GET /community/stats` — query param: region
  - **Auth:** All POST routes require `current_user` dependency. GET routes are public.
  - **Rate limiting:** Custom dependency `RateLimiter(10, 3600)` on POST /posts, `RateLimiter(50, 3600)` on POST /vote
  - **Register:** Add router to `backend/main.py`
  - **Run:** `.venv/bin/python -m pytest tests/test_community_api.py -v`
  - **Expected:** All PASS

- [x] Task 2.3: Write failing tests for combined savings route
  - **Files:** Add to `backend/tests/test_savings_aggregator.py` or new `backend/tests/test_savings_api.py`
  - **Tests (~4):**
    - `test_combined_savings_authenticated` — 200
    - `test_combined_savings_unauthenticated` — 401
    - `test_combined_savings_response_shape` — has total, breakdown, rank
    - `test_neighborhood_comparison_authenticated` — 200
  - **Expected:** All FAIL

- [x] Task 2.4: Implement savings + neighborhood API routes
  - **Files:** Check if `backend/api/v1/savings.py` already exists — if so, EXTEND it; if not, create it. Add neighborhood routes to `backend/api/v1/community.py` or new `neighborhood.py`.
  - **IMPORTANT:** Check existing router registrations in `backend/main.py` before adding — avoid prefix conflicts
  - **Routes:**
    - `GET /savings/combined` — requires auth, returns combined savings
    - `GET /neighborhood/compare` — query params: region, utility_type
  - **Register:** Add router(s) to `backend/main.py`
  - **Run:** `.venv/bin/python -m pytest tests/test_savings_api.py -v`
  - **Expected:** All PASS

- [x] Task 2.5: Update conftest.py mock fixtures (N/A — community uses raw SQL, not ORM)
  - **Files:** Modify `backend/tests/conftest.py`
  - Add `community_posts`, `community_votes`, and `community_reports` model attrs to `mock_sqlalchemy_select`
  - Include new fields: `is_pending_moderation`, `rate_per_unit`, `rate_unit`
  - **Run:** Full backend suite
  - **Expected:** No regressions

- [x] Task 2.6: Commit Phase 2
  - **Run:** Full backend suite `.venv/bin/python -m pytest -v --tb=short`
  - **Expected:** All pass
  - **Commit:** `feat(api): add community, savings, and neighborhood API routes (mu-wave5)`

### Verification

- [x] Community API: 12 tests passing
- [x] Savings API: 4 tests passing
- [x] Full backend suite green (2478 passed)
- [x] Routes registered in app_factory.py

---

## Phase 3: Dashboard Tab Frontend

Restructure the dashboard page into a tabbed layout. No community frontend yet.

### Tasks

- [x] Task 3.1: Create `DashboardTabs` component
  - **Files:** Create `frontend/components/dashboard/DashboardTabs.tsx`
  - **Behavior:**
    - Tab bar: "All Utilities", "Electricity", "Natural Gas", "Heating Oil", "Propane", "Community Solar", "Water"
    - URL search param: `?tab=electricity` (deep-linkable, back-button friendly)
    - Smart default: single-utility users land on their utility tab; 2+ utilities default to `all`
    - Uses `useSearchParams()` from next/navigation
    - Checks `useFeatureFlag('utility_<type>')` — hides tab if flag disabled
    - Mobile: horizontal scroll with `overflow-x-auto` + gradient fade affordance on edges (left/right)
    - Active tab: `border-b-2 border-primary` (Tailwind)
  - **Verify:** Component renders without errors

- [x] Task 3.2: Create `AllUtilitiesTab` component
  - **Files:** Create `frontend/components/dashboard/AllUtilitiesTab.tsx`
  - **Behavior:**
    - Renders `CombinedSavingsCard` at top
    - Grid of per-utility summary cards (one per active utility type)
    - Each card uses its own React Query hook — independent loading/error states
    - Feature flag check per card — hidden if utility disabled
  - **Verify:** Component renders with mock data

- [x] Task 3.3: Create `CombinedSavingsCard` component
  - **Files:** Create `frontend/components/dashboard/CombinedSavingsCard.tsx`
  - **Behavior:**
    - Calls `GET /savings/combined` via React Query
    - Displays total monthly savings, stacked bar by utility type, percentile badge
    - Loading skeleton, error fallback
  - **API client:** Add `getCombinedSavings()` to `frontend/lib/api/` (new file or extend existing)

- [x] Task 3.4: Create `NeighborhoodCard` component
  - **Files:** Create `frontend/components/dashboard/NeighborhoodCard.tsx`
  - **Behavior:**
    - Calls `GET /neighborhood/compare` via React Query
    - Bar chart: your rate vs. average rate in state
    - Percentile text: "You pay more than X% of users"
    - "Insufficient data" placeholder when API returns null fields
    - Reuses existing chart library (recharts or similar)

- [x] Task 3.5: Create `UtilityTabShell` component
  - **Files:** Create `frontend/components/dashboard/UtilityTabShell.tsx`
  - **Behavior:**
    - Shared layout wrapper for individual utility tabs
    - Renders price chart, supplier table, forecast, alerts sections
    - Electricity tab renders current `DashboardContent` inside this shell (zero changes to existing component)
    - Other utility tabs follow same pattern with their respective hooks

- [x] Task 3.6: Wire `DashboardTabs` into dashboard page
  - **Files:** Modify `frontend/app/dashboard/page.tsx` (or equivalent)
  - Replace current `DashboardContent` render with `DashboardTabs`
  - `DashboardContent` becomes the content of the Electricity tab (rename import, no code change)
  - **Verify:** Dashboard loads with tabs, electricity tab shows existing content

- [x] Task 3.7: Write dashboard frontend tests (~28)
  - **Files:** Create `frontend/__tests__/components/dashboard/DashboardTabs.test.tsx` and related
  - **Tests:**
    - Tab switching renders correct content
    - URL param syncs with active tab
    - Smart default: single-utility user lands on their utility tab
    - Smart default: multi-utility user lands on "All Utilities"
    - Feature flag hides disabled utility tabs
    - Loading/error states per utility card in All Utilities tab
    - Combined savings card renders with mock data
    - Combined savings card shows loading skeleton
    - Neighborhood card renders comparison bar chart
    - Neighborhood card shows "insufficient data" placeholder ("We need a few more neighbors...")
    - Neighborhood card includes context: "You pay $X.XX/kWh vs. state average $Y.YY/kWh"
    - Mobile tab bar is scrollable with gradient fade affordance
    - Electricity tab renders existing DashboardContent
    - Back button returns to previous tab
    - Direct URL with `?tab=natural_gas` opens correct tab
  - **Run:** `cd frontend && npm test -- --testPathPattern=DashboardTabs`
  - **Expected:** All PASS

- [x] Task 3.8: Update Sidebar test for dashboard (no nav changes needed, 16/16 passing)
  - **Files:** Modify `frontend/__tests__/components/layout/Sidebar.test.tsx` if sidebar labels change
  - **Verify:** No regressions in existing 22 sidebar tests

- [x] Task 3.9: Commit Phase 3
  - **Run:** `cd frontend && npm test` (full suite)
  - **Expected:** All pass, zero regressions — 1808 passed, 135 suites
  - **Commit:** `feat(dashboard): add tabbed multi-utility dashboard with combined savings (mu-wave5)` (bc3ab4f)

### Verification

- [x] Tabs render and switch correctly (9 DashboardTabs tests)
- [x] URL deep-linking works (respects ?tab= param test)
- [x] Feature flags hide/show tabs (via utilityTypes from settings store)
- [x] Combined savings + neighborhood cards render (7 + 5 tests)
- [x] Electricity tab preserves existing behavior exactly (integration test: 15/15)
- [x] 28 new tests passing (DashboardTabs.test.tsx)
- [x] Full frontend suite green (1808 passed, 135 suites)

---

## Phase 4: Community Frontend

Build the community page and components.

### Tasks

- [x] Task 4.1: Create community API client
  - **Files:** Create `frontend/lib/api/community.ts`
  - **Functions:**
    - `fetchPosts(region, utilityType, page)` — GET /community/posts
    - `createPost(data)` — POST /community/posts
    - `toggleVote(postId)` — POST /community/posts/{id}/vote
    - `reportPost(postId)` — POST /community/posts/{id}/report
    - `fetchCommunityStats(region)` — GET /community/stats
  - **React Query hooks:** `useCommunityPosts()`, `useCreatePost()`, `useCommunityStats()`

- [x] Task 4.2: Create `PostList` component
  - **Files:** Create `frontend/components/community/PostList.tsx`
  - **Behavior:**
    - Renders paginated list of community posts
    - Filter dropdowns: region (state), utility type, post type
    - Each post card: title, body preview, author (anonymized), upvote count, time ago
    - Hidden posts show "[Content under review]" placeholder
    - Pending moderation posts show "Your post is being reviewed" (visible only to author)
    - Simple offset pagination (prev/next buttons)

- [x] Task 4.3: Create `PostForm` component
  - **Files:** Create `frontend/components/community/PostForm.tsx`
  - **Behavior:**
    - Form fields: title, body, utility_type (dropdown), region (dropdown using Region enum), post_type (dropdown)
    - Optional fields for rate_report type: rate_per_unit (number), rate_unit (dropdown: kWh, therm, gallon, CCF), supplier_name (text)
    - Consent text: "Your post will be visible to other users in your state. We review content for safety."
    - Client-side validation: title required (3-200 chars), body required (10-5000 chars)
    - Submit calls `createPost()` mutation, shows success/error toast
    - Requires authentication (show login prompt if not authed)

- [x] Task 4.4: Create `VoteButton` and `ReportButton` components
  - **Files:** Create `frontend/components/community/VoteButton.tsx`, `ReportButton.tsx`
  - **VoteButton:** Toggle upvote with optimistic update, shows count
  - **ReportButton:** Confirmation dialog ("Are you sure?"), calls reportPost

- [x] Task 4.5: Create `CommunityStats` component
  - **Files:** Create `frontend/components/community/CommunityStats.tsx`
  - **Behavior:**
    - Banner: "X users in [state] saved an average of Y%" with attribution: "Based on X users reporting since [date]"
    - Top tip card
    - Renders on community page + optionally on dashboard social proof section

- [x] Task 4.6: Create community page
  - **Files:** Create `frontend/app/(app)/community/page.tsx`
  - **Layout:** Stats banner at top, PostForm (collapsed/expandable), PostList below
  - **Route:** `/community`

- [x] Task 4.7: Add community link to sidebar navigation
  - **Files:** Modify `frontend/components/layout/Sidebar.tsx`
  - Add "Community" nav item with `Users` icon from lucide-react
  - Position: after Optimize, before Analytics
  - **Verify:** Sidebar renders with new item, a11y tests still pass

- [x] Task 4.8: Write community frontend tests (~27)
  - **Files:** Create `frontend/__tests__/components/community/Community.test.tsx`
  - **Tests:** 27 tests covering PostList (8), PostForm (7), VoteButton (3), ReportButton (4), CommunityStats (5)
  - **Run:** `cd frontend && npx jest --testPathPattern=community`
  - **Expected:** All PASS — 27/27

- [x] Task 4.9: Update Sidebar tests for Community nav item
  - **Files:** Modified `frontend/__tests__/components/layout/Sidebar.test.tsx` (14→15 items, Community href)
  - **Also:** Updated `frontend/__tests__/a11y/sidebar.a11y.test.tsx` with `Users` icon mock
  - **Run:** `cd frontend && npx jest --testPathPattern=Sidebar`
  - **Expected:** All PASS — 39/39

- [x] Task 4.10: Commit Phase 4
  - **Run:** `cd frontend && npm test` (full suite)
  - **Expected:** All pass — 1835 passed, 136 suites
  - **Commit:** `feat(community): add community page with posts, voting, and stats (mu-wave5)` (6437020)

### Verification

- [x] Community page renders at `/community`
- [x] Post creation, voting, and reporting work (API client + hooks wired)
- [x] AI moderation triggers on post create (backend CommunityService handles this)
- [x] Stats banner shows aggregate data
- [x] Sidebar shows Community link (15th nav item)
- [x] 27 new community tests passing
- [x] Full frontend suite green (1835 passed, 136 suites)

---

## Phase 5: Security Hardening

Automated scanning, dependency auditing, and manual review.

### Tasks

- [x] Task 5.1: Add OWASP ZAP GitHub Action
  - **Files:** Created `.github/workflows/owasp-zap.yml` + `.zap/rules.tsv`
  - Weekly cron Sunday 4am UTC, `zaproxy/action-baseline@v0.12.0`, targets Render directly
  - 5 false-positive suppression rules in `.zap/rules.tsv`

- [x] Task 5.2: Add `pip-audit` to backend CI
  - **Files:** Modified `.github/workflows/_backend-tests.yml`
  - Added `pip-audit --strict --desc` step after dependency install, fails on known vulnerabilities

- [x] Task 5.3: Add `npm audit` gate to frontend CI
  - **Files:** Modified `.github/workflows/ci.yml`
  - Upgraded from `--audit-level=critical` (warning) to `--audit-level=high` (fail on error)

- [x] Task 5.4: nh3 already in backend dependencies
  - `nh3>=0.2.14` already in `backend/requirements.txt`, used in `community_service.py`

- [x] Task 5.5: Community security review
  - Security audit (11 PASS, 1 medium-risk finding):
    - [x] All community POST endpoints require authentication
    - [x] Title/body sanitized via nh3 before storage
    - [~] SQL queries — community_service uses `sqlalchemy.text()` with named bind params (parameterized correctly, no injection, but deviates from ORM standard)
    - [x] Rate limiting enforced on create endpoints (10/hour)
    - [x] Reports deduplicated via composite PK
    - [x] is_hidden server-side only
    - [x] is_pending_moderation server-side only
    - [x] Pagination params validated

- [x] Task 5.6: Auth flow and credential review
  - All items PASS:
    - [x] JWT/session tokens have appropriate expiry
    - [x] Portal credential AES-256-GCM encryption verified
    - [x] API key rotation procedure documented
    - [x] INTERNAL_API_KEY excluded from client-side code
    - [x] No secrets in frontend bundle

- [x] Task 5.7: Commit Phase 5
  - **Commit:** `ci(security): add OWASP ZAP, pip-audit, npm audit gates (mu-wave5)`

### Verification

- [x] OWASP ZAP workflow exists and is valid YAML
- [x] pip-audit runs in backend CI
- [x] npm audit runs in frontend CI (upgraded to high severity)
- [x] nh3 (not bleach) installed and used in CommunityService
- [x] Security checklists completed — 11 PASS, 1 medium-risk observation (raw text() with bind params)

---

## Phase 6: E2E Tests & Integration Validation

End-to-end tests and full system verification.

### Tasks

- [ ] Task 6.1: Write Playwright E2E test — dashboard tabs
  - **Files:** Create `frontend/e2e/dashboard-tabs.spec.ts`
  - **Tests:**
    - Navigate to /dashboard → "All Utilities" tab is active
    - Click "Electricity" tab → URL updates to `?tab=electricity`, content changes
    - Direct navigate to `/dashboard?tab=natural_gas` → correct tab active
  - **Run:** `cd frontend && npx playwright test dashboard-tabs`

- [ ] Task 6.2: Write Playwright E2E test — community flow
  - **Files:** Create `frontend/e2e/community.spec.ts`
  - **Tests:**
    - Navigate to /community → post list renders
    - Create post (if auth mock available) → appears in list
    - Vote on post → count updates
  - **Run:** `cd frontend && npx playwright test community`

- [ ] Task 6.3: Run full test suites
  - **Backend:** `.venv/bin/python -m pytest -v --tb=short`
  - **Frontend:** `cd frontend && npm test`
  - **E2E:** `cd frontend && npx playwright test`
  - **Expected:** All green, zero regressions

- [ ] Task 6.4: Verify feature flag integration
  - Test that disabling `utility_water` flag hides Water tab and Water card in All Utilities
  - Test that `utility_forecast` requires pro tier
  - Can be unit tests or manual verification

- [ ] Task 6.5: Commit Phase 6
  - **Commit:** `test(e2e): add dashboard tabs and community E2E tests (mu-wave5)`

### Verification

- [ ] E2E tests pass
- [ ] Full backend suite: ~2,460+ tests passing
- [ ] Full frontend suite: ~1,815+ tests passing
- [ ] Feature flags correctly control visibility

---

## Phase 7: Documentation, DSP Update & Final Ship

Update project documentation, DSP graph, and prepare for deployment.

### Tasks

- [ ] Task 7.1: Deploy migration 049 to production
  - Via Neon MCP or direct SQL execution
  - **Verify:** Tables exist in production DB

- [ ] Task 7.2: Update CLAUDE.md
  - Migration count: 049
  - Table count: 45 (42 + community_posts + community_votes + community_reports)
  - Test counts: updated totals
  - Add community endpoints to architecture reference
  - Add OWASP ZAP + pip-audit to CI section
  - Add nh3 to backend dependencies
  - Add Groq moderation (primary) + Gemini (fallback) to AI Agent section

- [ ] Task 7.3: Update conductor tech-stack.md
  - Update test counts
  - Add nh3 (not bleach) to backend dependencies
  - Add OWASP ZAP to infrastructure
  - Update table count to 45

- [ ] Task 7.4: Update DSP graph
  - Run: `python3 dsp-cli.py --root . scan`
  - New entities: community models, services, API routes, frontend components
  - **Verify:** No cycles

- [ ] Task 7.5: Update conductor tracks.md — mark Wave 5 complete
  - Change `[ ]` to `[x]` for `mu-wave5-unification_20260311`

- [ ] Task 7.6: Final commit
  - **Run:** Full test suites one last time
  - **Commit:** `docs: Wave 5 complete — unified dashboard, community, security hardening (mu-wave5)`
  - **Push:** To origin/main

### Verification

- [ ] Migration deployed to production
- [ ] CLAUDE.md reflects current state
- [ ] DSP graph updated, zero cycles
- [ ] Track marked complete in tracks.md
- [ ] All acceptance criteria from spec.md met
- [ ] Ready for Wave 6+ (deferred: API marketplace, white-label, enterprise)

---

## Test Budget Summary

| Phase | New Tests | Type |
|-------|-----------|------|
| Phase 1 | ~31 | Backend unit (community 20 + savings 6 + neighborhood 5) |
| Phase 2 | ~17 | Backend API (community 13 + savings 4) |
| Phase 3 | ~22 | Frontend unit (dashboard tabs, cards, smart default, mobile affordance) |
| Phase 4 | ~20 | Frontend unit (community components, pending states, edit/resubmit, consent) |
| Phase 6 | ~5 | E2E Playwright |
| **Total** | **~95** | |

---

_Generated by Conductor from brainstorming session design review. Tasks will be marked [~] in progress and [x] complete._
