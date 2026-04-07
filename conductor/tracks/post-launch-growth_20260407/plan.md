# Implementation Plan: Post-Launch Growth & Scaling

**Track ID:** post-launch-growth_20260407
**Created:** 2026-04-07
**Status:** [ ] Pending
**Depends on:** launch-execution_20260407 (launch must happen first)

## Overview

Scaling infrastructure, product expansion, and long-term roadmap items. 18 tasks across 4 categories: growth-triggered infrastructure upgrades (5, 2 already done at T-24h), product expansion (7), community/GTM (5), and housekeeping (1). Remaining infrastructure tasks are gated by specific metrics triggers — do NOT execute until trigger condition is met.

**Categories covered:** D (Scaling Infrastructure) + E (Future Product) + Post-launch community/PR

---

## Category D: Infrastructure Scaling (Trigger-Gated)

Each task has a specific metric trigger. Monitor via Grafana dashboards and service dashboards.

- [x] Task D.1: Upgrade Render Free → Starter ($7/mo) — **DONE AT T-24h (Track 2 Task 3.1)**
  - **Moved to pre-launch:** Cold starts on Render free tier (15min spin-down) would give PH visitors a blank screen on first visit. Upgraded at T-24h per Monitoring Runbook and multi-agent review (CR-2, UX-7).
  - **Downgrade trigger:** If monthly cost pressure arises and DAU drops below 10, consider downgrading back to free tier and re-enabling keepalive cron
  - **Budget:** +$7/mo

- [x] Task D.2: Upgrade Resend Free → Starter ($20/mo) — **DONE AT T-24h (Track 2 Task 3.1)**
  - **Moved to pre-launch:** Free tier (100/day + 500 Gmail SMTP = 600/day) insufficient for launch day email blast to 300+ contacts plus welcome emails for new signups. Upgraded at T-24h per Monitoring Runbook.
  - **Downgrade trigger:** If signups plateau below 50/day and email volume stays under 500/day, consider downgrading
  - **Budget:** +$20/mo

- [ ] Task D.3: Add Upstash Redis
  - **Trigger:** Deploy 2+ Uvicorn workers (200+ DAU) OR rate limiter needs shared state
  - **Source:** Deferred table, Roadmap
  - **Action:**
    - Provision Upstash Redis instance (free tier: 10K commands/day)
    - Update `backend/config/settings.py` Redis URL
    - Migrate rate limiter from in-memory to Redis
    - Migrate session cache from in-memory to Redis
    - Update Render env var: `REDIS_URL`
  - **Test:** Rate limiter tests with Redis backend
  - **Budget:** $0 (Upstash free tier) initially

- [ ] Task D.4: Upgrade Neon Free → Launch ($19/mo)
  - **Trigger:** >60 compute-hours/month OR storage approaching 0.5 GB limit
  - **Source:** Capacity Audit
  - **Action:** Neon console → Project settings → Upgrade to Launch ($19/mo)
  - **Impact:** 300 compute-hours, 10 GB storage, point-in-time restore
  - **Budget:** +$19/mo

- [ ] Task D.5: Upgrade Render Starter → Standard ($25/mo)
  - **Trigger:** 500+ DAU OR API latency p95 >500ms consistently
  - **Source:** Scaling Plan
  - **Action:** Render dashboard → Upgrade → Standard ($25/mo)
  - **Impact:** More CPU/RAM, autoscaling, zero-downtime deploys
  - **Budget:** +$18/mo over Starter

---

## Category E: Product Expansion (Post-Launch Roadmap)

### E.1: Near-Term (Month 1-2 post-launch)

- [ ] Task E.1: Account deletion modal (replace `window.confirm`)
  - **Trigger:** UX audit or user feedback about deletion flow
  - **Source:** Deferred table
  - **Est. effort:** 2h
  - **Spec:** Replace `window.confirm` in account deletion with proper Modal component (shadcn/ui AlertDialog). Add confirmation input ("type DELETE to confirm"). Already have Modal pattern from connection delete flow.
  - **Test:** E2E test for deletion flow with modal

- [ ] Task E.2: AI query counter in UI
  - **Trigger:** User feedback signals demand for visibility into usage
  - **Source:** Deferred table
  - **Est. effort:** 1h
  - **Spec:** Show remaining AI queries for current period (Free: 3/day, Pro: 20/day, Business: unlimited). Add to AgentChat header or sidebar. Data already available via `GET /agent/usage`.

- [ ] Task E.3: Sidebar IA redesign (progressive disclosure)
  - **Trigger:** Post-launch user research shows navigation confusion
  - **Source:** Deferred table
  - **Est. effort:** 4-6h
  - **Spec:** Current: 16 flat sidebar items. Redesign: Group into categories (Home, Rates & Forecasts, Connections, Tools, Settings). Collapsible sections. Pin most-used items. Mobile: bottom tab bar with 5 top-level items.
  - **Test:** E2E navigation tests, mobile viewport tests

### E.2: Medium-Term (Month 2-4 post-launch)

- [ ] Task E.4: ESLint 8 → 9 flat config migration
  - **Trigger:** Next.js releases eslint-config-next with ESLint 9/10 support
  - **Source:** ESLint Migration Plan (`docs/ESLINT_MIGRATION_PLAN.md`)
  - **Est. effort:** 2-3h
  - **Spec:** Phase 1: Create `eslint.config.mjs` (flat config). Phase 2: Upgrade ESLint 8→9. Phase 3: Eventually ESLint 10. See migration plan for full details.
  - **Blocked by:** External — Next.js eslint-config-next compatibility

- [ ] Task E.5: Repository layer extraction
  - **Trigger:** Any service file exceeds 500 lines OR 3+ queries against same table in one service
  - **Source:** Refactoring Roadmap (Future section)
  - **Est. effort:** 8-12h (phased)
  - **Spec:** Phase 1: AlertRepository + CommunityRepository (highest query density). Phase 2: Standardize interface pattern. Phase 3: Remaining services. See `docs/REFACTORING_ROADMAP.md` "Future: Repository Layer Strategic Plan".

- [ ] Task E.6: Geographic expansion (Canada, UK)
  - **Trigger:** Launch feedback shows international demand OR 500+ US DAU
  - **Source:** Roadmap 4.4
  - **Est. effort:** 2-3 weeks per country
  - **Spec:**
    - Canada: Ontario/Alberta deregulated markets. New Region enum values, IESO/AESO data sources, CAD pricing
    - UK: Ofgem price cap, Octopus/Bulb switching APIs, GBP pricing
    - Requires: regulatory research, new data pipelines, localized pricing UI, compliance review
  - **Dependencies:** International payment support (Stripe already supports CAD/GBP)

- [ ] Task E.7: Mobile strategy evaluation
  - **Trigger:** >40% mobile traffic OR 500+ DAU
  - **Source:** Roadmap 4.5
  - **Spec:**
    - Option A: PWA (low cost, already partially configured via `manifest.ts`)
    - Option B: React Native (higher cost, better push notifications UX)
    - Decision criteria: % mobile users, push notification engagement rates, App Store presence value
  - **Deliverable:** Decision document with recommendation

### E.3: Long-Term (6+ months post-launch)

- [ ] Task E.8: B2B enterprise tier
  - **Trigger:** Inbound enterprise interest (multiple companies asking)
  - **Source:** Deferred table
  - **Spec:** Different product for property managers, energy brokers. Multi-tenant, bulk switching, API access, SLA.

- [ ] Task E.9: API marketplace / platform play
  - **Trigger:** 1,000+ DAU, developer community forming
  - **Source:** Deferred table
  - **Spec:** Public API for electricity price data, switching orchestration. Revenue: API subscriptions.

- [ ] Task E.10: Time-based DB partitioning
  - **Trigger:** `electricity_prices` table >10M rows OR query p95 >200ms
  - **Source:** Deferred table
  - **Spec:** Partition `electricity_prices` by month using PostgreSQL native partitioning. Migrate with zero downtime using pg_partman extension.

---

## Category F: Community & GTM (Post-Launch)

- [ ] Task F.1: Community building
  - **Trigger:** 100+ active users
  - **Source:** Launch checklist Week 2+ section
  - **Action:**
    - Start Discord or Slack community for power users
    - Host weekly office hours (live Zoom)
    - Create beta tester program (early access to features)
    - Ambassador program (free Pro for 10 active users)

- [ ] Task F.2: Press & PR outreach
  - **Trigger:** After PH launch results are in (T+3 days)
  - **Source:** Launch checklist Week 2+ section
  - **Action:**
    - Reach out to 20+ relevant journalists (energy, fintech, consumer tech)
    - Prepare press kit (screenshots, metrics, founder bio)
    - Seek podcast interview opportunities
    - Consider Medium/Substack guest posts

- [ ] Task F.3: Content marketing pipeline
  - **Source:** Launch checklist Week 1 section
  - **Action:**
    - Blog: "How we shipped RateShift to Product Hunt"
    - Twitter thread: "Building for deregulated electricity markets"
    - User testimonials: 3-5 beta user quotes with photos
    - Case study: Detailed before/after savings story

- [ ] Task F.4: Ongoing analytics optimization
  - **Trigger:** Week 2 post-launch
  - **Source:** Launch checklist Analytics section
  - **Action:**
    - Weekly retention analysis
    - A/B test onboarding flow
    - Optimize conversion funnel (forecast → switch)
    - Reduce customer acquisition cost (CAC)

- [ ] Task F.5: Feature prioritization from feedback
  - **Trigger:** T+3 days post-launch
  - **Source:** Launch checklist Post-Launch section
  - **Action:**
    - Prioritize top 3 feature requests from PH feedback
    - Assign to sprint
    - Ship weekly updates
    - Post "shipping update" on PH every 3-5 days

---

## Housekeeping (Non-Triggered)

- [ ] Task H.1: Wire CF Data Quality Phase 6 into pre-session.sh
  - **Source:** cf-data-quality-plan.md Phase 6 (moved from pre-launch Track 1 Task 1.4 — not launch-blocking)
  - **Est. effort:** 0.5h
  - **Spec:**
    - Add call to `execute-work-orders.sh` in `~/.claude/skills/token-efficiency/scripts/pre-session.sh`
    - Add daily marker guard (separate from session marker): check `~/.claude/skills/token-efficiency/state/last-workorder-exec.txt`
    - Must exit 0 on failure (never block sessions)
  - **Verify:** Run `pre-session.sh` manually, confirm work order executor runs once then skips on repeat

---

## Completion Criteria

This track is never "complete" — it's an ongoing backlog. Individual tasks are completed as their triggers fire. Review monthly.

**Monthly review checklist:**
- [ ] Check all trigger conditions against current metrics
- [ ] Move any triggered tasks to active sprint
- [ ] Update budget forecast based on activated upgrades
- [ ] Review post-launch feedback for new items to add
