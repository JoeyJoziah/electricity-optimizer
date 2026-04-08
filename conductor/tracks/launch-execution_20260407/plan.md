# Implementation Plan: Product Hunt Launch Execution

**Track ID:** launch-execution_20260407
**Created:** 2026-04-07
**Status:** [~] In Progress
**Launch Date:** Tuesday April 14, 2026 (12:01 AM PT)
**Depends on:** pre-launch-completion_20260407 (Sprint 0 + Sprint 1.1 must be done)

## Overview

Execute the Product Hunt launch campaign. 10 tasks across 4 phases. Primarily manual/creative work with some tooling support. Materials already created in `docs/launch/` — this track covers the execution steps.

**Categories covered:** C (Launch Execution)

**Existing launch materials:**
- `docs/launch/PRODUCT_HUNT.md` — taglines, descriptions, templates, hour-by-hour plan
- `docs/launch/HN_REDDIT_POSTS.md` — HN Show + 5 Reddit templates
- `docs/launch/MONITORING_RUNBOOK.md` — 841-line operational runbook
- `docs/LAUNCH_CHECKLIST.md` — full checklist (this track operationalizes it)
- `docs/LAUNCH_MATERIALS.md` — go-to-market playbook

---

## Phase 0: PH Account & Identity (T-14 days, ~2h)

- [x] Task 0.1: Create and verify Product Hunt account
  - **Source:** Launch checklist, Marketing & Messaging section
  - **Priority:** P0
  - **Action:**
    - Create account at producthunt.com (use founder email)
    - Complete profile: bio, avatar, company logo
    - Verify email
    - Review PH maker guidelines
  - **Verify:** Account visible at producthunt.com/@username

- [x] Task 0.2: Set launch date and plan solo-founder schedule
  - **Source:** Launch checklist, Team Coordination section
  - **Priority:** P0
  - **Action:**
    - Pick specific launch date (Tuesday-Thursday recommended, 12:01 AM PT)
    - **Solo-founder reality**: Plan for one person covering all roles (PH comments, email support, monitoring, social media)
    - Set up monitoring dashboards in advance (Grafana, GA4 Realtime, Slack alerts) so they can be checked with a glance
    - Pre-write PH comment responses for common questions (pricing, coverage, security)
    - Block full calendar for launch day + day 2 — no other commitments
    - Prepare escalation plan: what gets delayed if overwhelmed (answer: social media posts, not PH comments)
  - **Decision needed:** Target date (Q2 2026 per checklist)

---

## Phase 1: Content & Messaging (T-14 to T-7 days, ~6h)

- [ ] Task 1.1: Finalize tagline, description, and founder story
  - **Source:** Launch checklist, Marketing & Messaging section
  - **Priority:** P0
  - **Action:**
    - Select from 3 taglines in `docs/launch/PRODUCT_HUNT.md`
    - Polish 260-char description
    - Write 3-4 paragraph founder story (first PH comment)
    - Identify 5 key features for messaging
    - Write maker background story
  - **Copy guardrails (from multi-agent review):**
    - Do NOT use "Join thousands of users" or similar unverified user count claims
    - Do NOT reference "private beta of 65+ users" as social proof — 65 is not impressive at PH scale
    - Do NOT claim "all 50 states" — say "deregulated electricity markets" or "17+ states"
    - Do NOT promise "dedicated account manager" — solo founder operation
    - DO lead with the savings hook: "Average household overpays $X/year on electricity"
    - DO be transparent about stage: "just launched" or "early-stage" is honest and PH-appropriate
  - **Deliverable:** Final copy in `docs/launch/FINAL_COPY.md`

- [ ] Task 1.2: Create content assets
  - **Source:** Launch checklist, Content Assets section
  - **Priority:** P1
  - **Action:**
    - Logo: 500x500 PNG, transparent background
    - Hero image: 1920x1080 product screenshot (dashboard with real data)
    - Gallery images (4-6): Dashboard, Price Forecast chart, Supplier comparison, Savings calculator, Mobile view, Auto-Switcher
    - Demo video: 30-60 sec screen recording (optional but recommended)
    - Press kit PDF: product info + screenshots + founder bio
    - Website: add PH launch badge
  - **Tools:** Screenshot via Chrome automation (`claude-in-chrome`), video via screen recorder
  - **Demo data sub-task:** Before capturing screenshots, seed dashboard with realistic demo data (real region, plausible forecast curve, sample savings). Empty-state screenshots will kill conversion. Use a test account with pre-populated data, NOT a fresh signup
  - **Deliverable:** All assets in `docs/launch/assets/` directory

- [ ] Task 1.3: Configure GA4 events and conversion funnels
  - **Source:** Launch checklist, Analytics & Tracking section
  - **Priority:** P1
  - **Depends on:** pre-launch-completion Task 1.1 (GA4 code deployed)
  - **Action:**
    - GA4 console: configure events (signup, login, forecast, switch, upgrade)
    - Set up conversion funnels: signup → forecast → switch
    - Create real-time dashboard for PH traffic source tracking
    - Establish metrics baseline (pre-launch numbers)
    - Create daily report template
  - **Verify:** GA4 Realtime view shows events from test navigation

---

## Phase 2: Network & Distribution (T-7 to T-1 days, ~4h)

- [ ] Task 2.1: Build and activate email list
  - **Source:** Launch checklist, Network Building section
  - **Priority:** P1
  - **Action:**
    - Curate beta user list (target: 65+ confirmed)
    - Newsletter subscriber list (target: 200+)
    - Friends/advisors list (target: 30+)
    - Total: 300+ people to email on launch day
    - Send pre-launch teaser email 7 days before (use template in Launch Checklist)
  - **Tools:** Resend for email delivery (100/day free + 500/day Gmail SMTP fallback = 600/day capacity)

- [ ] Task 2.2: Draft PH page and social media content
  - **Source:** Launch checklist, PH Launch Page Setup + Communications
  - **Priority:** P1
  - **Action:**
    - Draft PH page: tagline, description, 4-6 gallery images, demo video, category (Fintech), tags, FAQ (3-5 questions), website URL, promo code
    - Draft 7 launch tweets (templates in Launch Checklist lines 119-125)
    - Draft LinkedIn post (template in Launch Checklist lines 386-412)
    - Draft Reddit/HN submissions (templates in `docs/launch/HN_REDDIT_POSTS.md`)
    - Send support request emails to 20+ PH supporters
  - **Deliverable:** PH page in draft mode, social posts in scheduling tool

---

## Phase 3: Launch Day & Follow-Up (T-0 through T+7)

- [ ] Task 3.1: Execute launch day timeline
  - **Source:** Launch checklist, Launch Day section (lines 152-244)
  - **Priority:** P0
  - **Action:** Follow hour-by-hour timeline:
    - T-24h: **Upgrade Render Free → Starter ($7/mo)** — eliminates cold starts for PH visitors (see Track 3 D.1, now pre-launch)
    - T-24h: **Upgrade Resend Free → Starter ($20/mo)** — ensures email capacity for launch day signups (see Track 3 D.2, now pre-launch)
    - T-24h: **Email delivery smoke test** — send test welcome email via Resend, verify delivery to Gmail/Outlook/Yahoo within 60s. Check SPF/DKIM/DMARC alignment. If Resend fails, verify Gmail SMTP fallback still works
    - T-24h: Final code review, smoke tests, database health check, cache clear
    - T-1h: Verify website live, test signup, open Grafana, Slack tested
    - T-0 (12:01 AM PT): Publish PH page
    - T+1min: Post founder story comment
    - T+4min: Send beta user announcement email
    - T+6min: Tweet announcement
    - T+9min: Text 5 close friends/advisors
    - T+14min: Post LinkedIn
    - Hours 1-6: Respond to every PH comment within 10 minutes
    - Hours 6-18: Continue engagement, share metrics, consider AMA
    - Hours 18-24: Debrief, review support emails, prep day 2
  - **Monitoring:** Use `docs/launch/MONITORING_RUNBOOK.md` for system health tracking
  - **Metrics targets:** 250+ upvotes, 50+ comments, 200+ signups, 5000+ visitors

- [ ] Task 3.2: Post-launch engagement (Days 2-7)
  - **Source:** Launch checklist, Days 2-3 + Week 1 sections (lines 249-308)
  - **Priority:** P1
  - **Action:**
    - Day 2 AM: Post thank-you update on PH, share day 1 metrics
    - Day 2 PM: Send welcome email to all new signups
    - Day 3: Feature request summary post, ship one quick improvement
    - Day 4: Feature announcement based on feedback
    - Day 5: User story spotlight
    - Day 7: Week 1 wrap-up with numbers
  - **Content:** Blog post ("How we shipped RateShift to PH"), Twitter thread, testimonials
  - **Analytics:** Review traffic sources, segment by geography, analyze feature usage, day-7 retention, NPS survey

---

## Completion Criteria

- [ ] PH page published and receiving upvotes
- [ ] All launch day timeline items executed
- [ ] System uptime >99.8% during launch week
- [ ] All PH comments responded to within target time
- [ ] Day 7 metrics captured and shared
- [ ] Post-launch roadmap updated based on feedback
