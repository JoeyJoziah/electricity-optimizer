# Decision Log: Wave 5 — Unified Dashboard, Community & Security Hardening

**Track ID:** mu-wave5-unification_20260311
**Session Date:** 2026-03-11

---

## D1: Dashboard Layout Approach

**Decision:** Tabbed redesign — "All Utilities" default tab + one tab per active utility type

**Alternatives Considered:**
- **Replace existing dashboard** — Risk breaking existing electricity users' workflow
- **New separate page** — Fragments navigation, users must manage two dashboard URLs

**Why chosen:** Preserves existing electricity UX as-is (becomes the Electricity tab with zero code changes). "All Utilities" combined view is the new default. Deep-linkable via URL params. Feature flags naturally hide/show tabs.

---

## D2: Community Feature Scope

**Decision:** Full community — all 4 features (crowdsourcing, neighborhood comparison, social proof, discussion/tips forums)

**Alternatives Considered:**
- **Social proof only** — Minimal effort but no user engagement
- **Crowdsourcing + social proof** — Missing discussion which drives return visits

**Why chosen:** User wants complete community experience from day one. All 4 features share the same `community_posts` table with different `post_type` values, so incremental cost of adding all 4 is low.

---

## D3: Content Moderation Approach (Revised per Review)

**Decision:** AI auto-moderation (Groq primary + Gemini fallback, fail-closed with 30s timeout) + user report button (5 unique reporters)

**Alternatives Considered:**
- **Pre-moderation queue** — All posts held until human review. Too slow for engagement, requires moderator staffing
- **Post-moderation only (fail-open)** — Reactive, bad content visible until flagged. Poor user experience, especially at low scale where single bad post has outsized impact
- **Gemini primary** — Would contend with existing AI Agent's 10 RPM/250 RPD quota

**Why chosen:** Groq as primary avoids Gemini rate limit contention with the AI Agent. Fail-closed design holds posts as `is_pending_moderation=true` until classified, with 30s timeout auto-unhide as safety valve. At low scale, brief hold is acceptable; a single toxic post has outsized impact. Report button requires 5 unique reporters (composite PK dedup prevents single-user abuse). Flagged posts offer edit/resubmit flow for authors. Retroactive re-moderation on service recovery handles timeout cases.

---

## D4: Security Approach

**Decision:** Automated scanning (OWASP ZAP + pip-audit + npm audit) + light manual review of auth flows, encryption, key rotation

**Alternatives Considered:**
- **Automated only** — Misses business logic vulnerabilities in auth and credential handling
- **Full external penetration test** — Expensive ($5-15K+), overkill for current scale and timeline

**Why chosen:** Automated scanning catches 80%+ of common vulnerabilities. Manual review focuses on the highest-risk areas specific to RateShift (portal credential encryption, session handling, internal API key security). External pentest deferred to post-launch when budget allows.

---

## D5: Savings Metric Scope

**Decision:** All monitored utilities included in combined savings calculation

**Alternatives Considered:**
- **Switchable-only utilities** — Excludes water, heating oil where savings come from conservation/timing
- **User-configured** — Adds UI complexity for selecting which utilities to include

**Why chosen:** All utilities contribute meaningfully — electricity/gas via switching, water via conservation alerts, oil/propane via purchase timing optimization. Including all gives the most impressive and accurate savings number. Simpler backend (no per-user config).

---

## D6: Scale Assumption

**Decision:** Low scale (< 1,000 community posts in first 3 months)

**Alternatives Considered:**
- **Medium (1K-10K posts)** — Would need cursor pagination, possibly denormalized counters
- **High (10K+ posts)** — Would need full-text search, caching layer, materialized views

**Why chosen:** Early adopter phase. Simple offset pagination, no caching, no denormalized counters. Easy to upgrade later if growth exceeds expectations. YAGNI principle — build for known load, not hypothetical.

---

## D7: Architecture Pattern

**Decision:** Frontend-First Composition (Approach A) — dashboard aggregates client-side via existing React Query hooks

**Alternatives Considered:**
- **Backend aggregation API** — New `/dashboard/overview` endpoint that aggregates all utilities server-side. More efficient for mobile but adds backend complexity and coupling
- **BFF (Backend-For-Frontend)** — Dedicated backend layer tailored to dashboard needs. Best for multiple clients but over-engineered for single web frontend

**Why chosen:** Simplest path with zero new backend endpoints for the dashboard (except combined savings which genuinely needs server-side aggregation). Each utility card in "All Utilities" tab fires its own React Query request — independent caching, loading, and error states. One utility API failing doesn't break others. Leverages existing hooks without modification.

---

## Understanding Summary (Confirmed)

- **What:** Tabbed multi-utility dashboard + community features + security hardening
- **Why:** Unify the 7 utility types into a cohesive experience, drive engagement via community, harden security for expanded surface
- **Who:** Existing RateShift users with multiple utility accounts
- **Constraints:** Low scale, existing tech stack, reuse Gemini/Groq for moderation
- **Non-goals:** Threaded comments, real-time updates, user profiles/reputation, admin mod panel, external pentest

## Assumptions (Documented)

1. Existing per-utility React Query hooks composable without new backend aggregation
2. Simple community schema — flat posts, no threading
3. `optimization_report_service.py` extensible for combined savings
4. AI moderation via existing agent service with classification prompt
5. Community posts scoped by state (Region enum) + utility type
6. Minimum 5 users in region for neighborhood comparison
7. No caching needed at low scale

---

_Brainstorming exit criteria met: Understanding Lock confirmed, Approach A accepted, assumptions documented, risks acknowledged, Decision Log complete._

---

## Multi-Agent Review Addendum (2026-03-11)

**Review Process:** 3 specialized reviewers + 1 arbiter (multi-agent-brainstorming skill)

### Skeptic/Challenger Findings (17 objections → 14 accepted, 2 partial, 1 rejected)

Key revisions:
- `region_enum` PostgreSQL type → `VARCHAR(50)` (enum doesn't exist in our DB)
- `utility_type` unconstrained → `CHECK` constraint with 7 valid values + 'general'
- Fail-open → fail-closed with 30s timeout auto-unhide
- `bleach` → `nh3` (bleach is deprecated, nh3 is Rust-based successor)
- `report_count` counter → `community_reports` table with composite PK (prevents Sybil attack)
- 3 reports threshold → 5 unique reporters
- `rate_kwh` → `rate_per_unit` + `rate_unit` (multi-utility support)
- `upvotes` stored counter → derived via COUNT(*) (prevents drift)
- Rejected: tier-gating community features (already handled by existing tier system)

### Constraint Guardian Findings (12 concerns → 2 blocking fixed, 7 warnings addressed)

Key revisions:
- Gemini contention → Groq primary for moderation (dedicated `classify_content()`)
- Fail-closed under AI failure → 30s timeout auto-unhide + retroactive re-moderation
- Connection pool concern → acknowledged (monitor Neon dashboard)
- OWASP ZAP → weekly cron only, against Render directly (not CF Worker)
- `community_reports` table added to migration (was missing)
- `nh3` confirmed (bleach/nh3 inconsistency resolved)

### User Advocate Findings (12 concerns → all accepted)

Key revisions:
- Smart tab default: single-utility users land on their utility tab
- Flagged post edit/resubmit flow for authors
- Mobile tab gradient fade affordance
- VoteButton error toast (not silent failure)
- "Deferred" label for pending moderation (visible only to author)
- Percentile context: "You pay $X.XX vs. state average $Y.YY"
- Neighborhood null state: "We need a few more neighbors..."
- Consent text on PostForm
- Stats attribution: "Based on X users reporting since [date]"
- Post type explanation chips/tooltips
- Report confirmation with feedback

### Arbiter Verdict

**APPROVED WITH CONDITIONS** (2026-03-11)

- Condition 1 (BLOCKING): Sync on-disk documents — **COMPLETED** (this update)
- Condition 2 (ADVISORY): Validate migration on vercel-dev branch first — added to plan Task 1.1
- Condition 3 (ADVISORY): Document Groq moderation prompt — added to spec Technical Notes
