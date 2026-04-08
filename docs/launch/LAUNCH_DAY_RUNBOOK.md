# RateShift Launch-Day Rehearsal Plan & Execution Runbook

**Launch Date**: Tuesday, April 14, 2026 at 12:01 AM PT / 3:01 AM ET
**Launch Platform**: Product Hunt
**Operator**: Devin (solo founder -- one person doing everything)
**Companion Docs**: `FINAL_COPY.md` (copy), `PRODUCT_HUNT.md` (playbook), `MONITORING_RUNBOOK.md` (infra), `HN_REDDIT_POSTS.md` (social)

---

## Table of Contents

1. [Rehearsal Checklist (April 12-13)](#1-rehearsal-checklist-april-12-13)
2. [Hour-by-Hour Execution Plan (April 13-14)](#2-hour-by-hour-execution-plan-april-13-14)
3. [Quick-Access Cheat Sheet](#3-quick-access-cheat-sheet)
4. [Metrics Tracking Template](#4-metrics-tracking-template)

---

## 1. Rehearsal Checklist (April 12-13)

Complete every item below before going to sleep on Sunday, April 13. Items are grouped by day. Check the box as you go. If any gate fails, fix it before moving on.

### Saturday, April 12 -- Dry Run Day

#### A. Product Hunt Draft Rehearsal

- [ ] Log in to producthunt.com, navigate to "Post a Product"
- [ ] Create a DRAFT listing (do NOT publish). Fill in every field:
  - Thumbnail (200x200 logo, high contrast, readable at small size)
  - Gallery (8 screenshots -- see status below)
  - Tagline: `AI finds you cheaper electricity rates -- automatically`
  - Description (258 chars -- copy verbatim from `FINAL_COPY.md` Section 2)
  - Topics: Artificial Intelligence, Productivity, Utilities, FinTech, Climate Tech
  - Website URL: `https://rateshift.app?utm_source=producthunt&utm_medium=post`
- [ ] Preview the listing. Confirm gallery renders correctly on desktop and mobile
- [ ] Delete the draft (or leave it as a draft -- PH allows one unpublished draft)

#### B. Gallery Screenshot Status

Current status: 3 of 8 done. Remaining 5 must be captured by end of day April 12.

| # | Screenshot | File | Status |
|---|-----------|------|--------|
| 1 | Landing page | `assets/01-landing.png` | DONE |
| 2 | Pricing page | `assets/02-pricing.png` | DONE |
| 3 | Prices with live data | `assets/03-prices.png` | DONE |
| 4 | ML Forecast graph | `assets/04-forecast.png` | TODO |
| 5 | Smart Alerts UI | `assets/05-alerts.png` | TODO |
| 6 | AI Assistant chat | `assets/06-assistant.png` | TODO |
| 7 | Mobile view (dashboard) | `assets/07-mobile.png` | TODO |
| 8 | Auto-Switcher settings | `assets/08-auto-switcher.png` | TODO |

Capture instructions:
- Use Chrome DevTools, set device to 1920x1440 (3:2), DPI 2x
- For mobile screenshot (#7): use iPhone 14 Pro emulation, then composite into a 1920x1440 canvas
- Light backgrounds, consistent color palette, RateShift logo on first and last

#### C. Maker Comment Timing Drill

- [ ] Open `FINAL_COPY.md` Section 3 (Maker Comment) on your phone AND laptop
- [ ] Open a text editor on each device. Paste the full maker comment into it
- [ ] Time yourself: from opening PH to pasting and submitting a comment. Target: under 90 seconds
- [ ] Repeat twice. You need muscle memory for 3:01 AM when your brain is foggy

#### D. Response Template Accessibility

- [ ] Bookmark `FINAL_COPY.md` Section 5 in your phone browser (Safari/Chrome)
- [ ] Bookmark `FINAL_COPY.md` Section 5 in your laptop browser
- [ ] Create a phone Note or clipboard manager entry with all 5 one-line template starters:
  - Technical: "Great question. We use an ensemble approach..."
  - Pricing: "Good catch. Free tier gets real-time tracking..."
  - Feature Request: "Love this. The short answer: yes, it's on the roadmap..."
  - Competitor: "I appreciate the directness. Here's the honest comparison..."
  - Praise: "This means the world. Seriously..."
- [ ] Verify you can find and copy-paste each template within 30 seconds on your phone

#### E. Monitoring Dashboard Verification

- [ ] Open every dashboard URL from `MONITORING_RUNBOOK.md` Section 2 in separate browser tabs
- [ ] Verify login works for each (Render, Vercel, Neon, Cloudflare, Resend, Gemini, Groq, Composio, GitHub, UptimeRobot, Grafana)
- [ ] Create a Chrome bookmark folder called "Launch Day" with all dashboard URLs
- [ ] Set Slack notifications to "All messages" for #incidents channel on both phone and laptop
- [ ] Run the quick health check:
  ```bash
  echo "=== Backend ===" && curl -s https://api.rateshift.app/health | python3 -m json.tool
  echo "=== Frontend ===" && curl -s -o /dev/null -w "HTTP %{http_code} (%{time_total}s)\n" https://rateshift.app
  echo "=== CF Gateway ===" && curl -s -o /dev/null -w "HTTP %{http_code} (%{time_total}s)\n" https://api.rateshift.app/api/v1/health
  ```
- [ ] Confirm all three return success responses

#### F. Slack Webhook Test

- [ ] Trigger a test alert to #incidents:
  ```bash
  curl -X POST -H 'Content-type: application/json' \
    --data '{"text":"LAUNCH REHEARSAL: Test alert. Ignore this message."}' \
    "$SLACK_INCIDENTS_WEBHOOK_URL"
  ```
- [ ] Verify it appears in #incidents on both laptop and phone Slack apps
- [ ] Confirm phone push notification fired

### Sunday, April 13 -- Final Prep Day

#### G. Infrastructure Upgrades (CRITICAL -- do by 6 PM ET)

These are from `MONITORING_RUNBOOK.md` Section 1. Do not skip.

- [ ] Upgrade Render to Starter tier ($7/mo) -- prevents cold-start sleep
  - Verify: `curl -s https://api.rateshift.app/health` returns healthy
- [ ] Upgrade Resend to Starter tier ($20/mo) -- 50K emails/mo capacity
  - Verify: Resend billing page shows "Starter"
- [ ] Check GitHub Actions minutes remaining (need 500+ for hotfix buffer)
- [ ] Verify UptimeRobot monitors all show UP status
- [ ] Optional: Upgrade Neon to Launch plan ($19/mo) for higher connection limits

#### H. End-to-End Smoke Test

- [ ] Sign up as a new user on rateshift.app (use a throwaway email)
- [ ] Verify welcome email arrives via Resend (check Resend dashboard)
- [ ] Navigate to /prices -- confirm live data loads
- [ ] Navigate to /assistant -- ask "What is the current electricity rate in CT?"
- [ ] Navigate to /alerts -- create a test alert, verify it saves
- [ ] Navigate to /pricing -- confirm all 3 tiers display correctly
- [ ] Test on phone (Safari): load rateshift.app, verify responsive layout

#### I. Social Posts Preparation

- [ ] HN post: Copy the Show HN title and body from `HN_REDDIT_POSTS.md` Section 1 into a draft document. Do NOT post yet
- [ ] Reddit posts: Copy all 5 subreddit posts into separate draft documents. Do NOT post yet
- [ ] Twitter/LinkedIn: Draft 3 tweet variations and 1 LinkedIn post. Save in Notes app
- [ ] Schedule: HN goes live April 15 (day after PH). Reddit posts stagger per timing strategy in `HN_REDDIT_POSTS.md` Section 3

#### J. Sleep Schedule Confirmation

This is non-negotiable. You are one person. You cannot run on zero sleep and respond coherently to PH comments for 18 hours.

**The Plan:**
- Sunday April 13, 6:00 PM ET: Start winding down evening prep
- Sunday April 13, 7:00 PM ET: All prep complete. Set 3 alarms (2:30 AM, 2:40 AM, 2:50 AM ET)
- Sunday April 13, 7:30 PM ET: In bed. Lights off. Phone on Do Not Disturb except alarms
- Monday April 14, 2:50 AM ET: Wake up. Coffee. Splash water on face
- Monday April 14, 3:01 AM ET: Launch

**Sleep target**: 7 hours (7:30 PM to 2:30 AM). This is early but essential.

**Backup**: If you cannot fall asleep by 9 PM, set alarms for 3:30 AM instead and accept a slightly delayed maker comment (within 5 minutes of launch rather than 2).

---

## 2. Hour-by-Hour Execution Plan (April 13-14)

All times are Eastern Time (ET). PT equivalents noted where critical.

### Phase 0: Pre-Launch Evening (Sunday April 13, 6:00 PM - 7:30 PM ET)

| Time (ET) | Action | Duration |
|-----------|--------|----------|
| 6:00 PM | Final health check (all endpoints, all dashboards) | 15 min |
| 6:15 PM | Pre-warm backend with 10 requests (see MONITORING_RUNBOOK.md) | 5 min |
| 6:20 PM | Open PH in browser, log in, confirm draft listing is ready | 5 min |
| 6:25 PM | Open maker comment in a text editor, ready to paste | 2 min |
| 6:27 PM | Set phone alarms: 2:30 AM, 2:40 AM, 2:50 AM | 3 min |
| 6:30 PM | Move laptop to bedside or desk near bed. Charger plugged in | 2 min |
| 6:32 PM | Set Slack #incidents to maximum notification level on phone | 2 min |
| 6:34 PM | Eat dinner. No caffeine after this point | 30 min |
| 7:00 PM | Final mental walkthrough: "Wake up, open laptop, publish, paste comment" | 5 min |
| 7:05 PM | Prepare coffee maker (set auto-brew for 2:45 AM if possible) | 5 min |
| 7:15 PM | Brush teeth, get ready for bed | 15 min |
| 7:30 PM | Lights off. Phone on Do Not Disturb (alarms still ring). Sleep | -- |

### Phase 1: Launch Window (Monday April 14, 2:50 AM - 4:00 AM ET)

This is the most critical 70 minutes. Every action is scripted.

| Time (ET) | Time (PT) | Action | Notes |
|-----------|-----------|--------|-------|
| 2:50 AM | 11:50 PM (Apr 13) | Wake up. Do NOT check phone yet. Get coffee | 5 min buffer |
| 2:55 AM | 11:55 PM | Open laptop. Open PH draft listing. Open maker comment text file | Have these ready from evening prep |
| 2:58 AM | 11:58 PM | Open Slack, Render dashboard, GA4 in background tabs | Do not get distracted reading anything |
| 3:00 AM | 12:00 AM | **HOLD**. Wait for clock to hit 3:01 AM ET exactly | PH new day starts at 12:01 AM PT |
| **3:01 AM** | **12:01 AM** | **PUBLISH the Product Hunt listing** | Click "Launch" button. Confirm it goes live |
| **3:02 AM** | **12:02 AM** | **Paste maker comment**. Submit immediately | Copy from text editor. Do not retype. Check for formatting breaks, then submit |
| 3:03 AM | 12:03 AM | Verify listing is live: refresh PH page, confirm public URL | Screenshot the live listing for records |
| 3:05 AM | 12:05 AM | Quick health check: backend, frontend, CF gateway all responding | Use the CLI one-liner from MONITORING_RUNBOOK.md |
| 3:07 AM | 12:07 AM | Tweet #1: "RateShift just launched on Product Hunt!" with PH link | Keep it simple. Link to PH, not to rateshift.app |
| 3:10 AM | 12:10 AM | Check PH for first comments. Respond to any within 5 minutes | Use response templates. Be warm, be brief |
| 3:15 AM | 12:15 AM | Check Render logs for any 5xx errors. Check Neon connections | Quick scan, not deep dive |
| 3:20 AM | 12:20 AM | Respond to any new PH comments | Prioritize questions over praise |
| 3:30 AM | 12:30 AM | Check Resend dashboard: are welcome emails delivering? | If blocked, check spam/DKIM status |
| 3:30-4:00 AM | 12:30-1:00 AM | **Active monitoring loop**: refresh PH every 5 min, respond to comments, watch Slack #incidents | This is peak engagement. Stay sharp |

### Phase 2: Sleep Window (Monday April 14, 4:00 AM - 8:00 AM ET)

You need 4 more hours of sleep. PH activity is low during 1-5 AM PT (4-8 AM ET). This is your window.

**Before sleeping (4:00 AM):**
- [ ] Respond to ALL pending PH comments (clear the queue)
- [ ] Log current metrics in the tracking template (Section 4): votes, comments, signups
- [ ] Verify no Slack #incidents alerts
- [ ] Verify Render/Neon/CF dashboards show green
- [ ] Set phone alarm for 8:00 AM ET
- [ ] Leave laptop open with PH tab visible (so you see it immediately on wake)
- [ ] Turn Slack #incidents notifications to LOUD on phone (override Do Not Disturb)

**What runs on autopilot while you sleep:**
- UptimeRobot monitors rateshift.app, api.rateshift.app, and prices endpoint. Alerts go to Slack #incidents AND your email
- CF Worker rate limiting protects against abuse (120 req/min)
- Resend delivers welcome emails automatically
- Cron jobs continue (keep-alive every 10 min, check-alerts every 3h)

**What does NOT run on autopilot:**
- PH comment responses (they will queue up -- this is OK for 4 hours)
- Bug reports (will wait until 8 AM unless Slack fires a critical alert)
- Social media (no posts during this window)

**Wake triggers (override sleep):**
- Slack #incidents alert on phone = site is down. Wake up and triage immediately
- If you naturally wake at 6-7 AM, do a quick PH comment sweep (10 min max), then go back to sleep

### Phase 3: Morning Shift (Monday April 14, 8:00 AM - 12:00 PM ET)

This is the most important sustained engagement window. US West Coast is waking up (5 AM PT). PH voting accelerates.

| Time (ET) | Action | Duration |
|-----------|--------|----------|
| 8:00 AM | Wake up. Coffee. Open laptop | 10 min |
| 8:10 AM | **Comment sweep**: Read and respond to ALL overnight PH comments | 30-45 min |
| 8:10 AM | Priority order: (1) questions, (2) bug reports, (3) feature requests, (4) praise | -- |
| 8:55 AM | Log metrics: votes, comments, signups, uptime | 5 min |
| 9:00 AM | Quick infra check: Render CPU/memory, Neon connections, CF error rate | 10 min |
| 9:10 AM | If any bugs reported on PH: triage severity. Fix critical bugs immediately. Acknowledge non-critical with "Looking into this, will update shortly" | variable |
| 9:30 AM | Post Twitter update #2: Share a specific user comment or stat from PH | 5 min |
| 9:35 AM | LinkedIn post: Founder story + PH link | 10 min |
| 9:45 AM | Return to PH. Respond to new comments. Target: <5 min response time | ongoing |
| 10:00 AM | **Engagement thread**: Post a new comment on your PH listing. Example: "Surprising stat from launch night: X% of signups are from Texas. Deregulation really matters there." | 5 min |
| 10:30 AM | Log metrics again | 5 min |
| 10:30-12:00 PM | **Continuous PH monitoring**: Check every 10 minutes. Respond to every comment. Ask follow-up questions to keep threads alive | 90 min |
| 11:00 AM | Mid-morning health check: all dashboards quick scan | 5 min |
| 11:30 AM | Eat a real meal. Keep PH open on phone while eating | 20 min |

### Phase 4: Afternoon Sustained Engagement (Monday April 14, 12:00 PM - 6:00 PM ET)

PH voting peaks around 9 AM - 2 PM PT (12 PM - 5 PM ET). This window determines final ranking.

| Time (ET) | Action | Duration |
|-----------|--------|----------|
| 12:00 PM | Log metrics (hourly from now on) | 5 min |
| 12:05 PM | Respond to all pending PH comments | 15 min |
| 12:20 PM | **Social proof drop**: Post a comment on PH with a real stat. Example: "We've had X signups in the first 9 hours. Most common region: [state]. The data nerd in me is fascinated." | 5 min |
| 12:30 PM | If ranking is top 5: consider emailing personal contacts for genuine upvotes. If ranking is top 20: stay focused on comment quality. If outside top 20: double down on response quality, not vote-chasing | 10 min |
| 1:00 PM | Log metrics | 5 min |
| 1:00-2:00 PM | Continuous PH comment monitoring (every 10 min) | 60 min |
| 2:00 PM | Log metrics | 5 min |
| 2:05 PM | **Behind-the-scenes comment**: Post about the tech stack, the solo-founder journey, or a specific design decision. PH loves transparency | 10 min |
| 2:15 PM | Infra health check: all dashboards | 10 min |
| 3:00 PM | Log metrics | 5 min |
| 3:00-5:00 PM | Continued monitoring. Response time target relaxes to <15 min | 120 min |
| 3:30 PM | Consider posting to r/personalfinance if PH is going well (or delay to Tuesday if PH needs full attention) | decision point |
| 4:00 PM | Log metrics | 5 min |
| 5:00 PM | Log metrics | 5 min |
| 5:00 PM | **Afternoon summary comment** on PH: "12 hours in. Here's what I've learned from your feedback so far: [top 3 themes]. Building [feature X] based on your input this week." | 10 min |

### Phase 5: Evening Wind-Down (Monday April 14, 6:00 PM - 11:00 PM ET)

PH voting slows after 5 PM PT (8 PM ET). Your ranking is mostly locked in by now.

| Time (ET) | Action | Duration |
|-----------|--------|----------|
| 6:00 PM | Log metrics. Take a snapshot of current PH ranking | 5 min |
| 6:00-7:00 PM | Final comment sweep. Respond to everything pending. Response time target: <1 hour | 30 min |
| 7:00 PM | Eat dinner. Step away from the screen for 30 minutes | 30 min |
| 7:30 PM | Quick PH check + infra check | 10 min |
| 8:00 PM | **Daily metrics snapshot** (see Section 4). Record all numbers | 15 min |
| 8:15 PM | Final PH comment sweep | 15 min |
| 8:30 PM | Tweet #3: End-of-day summary. "Day 1 on Product Hunt: X votes, Y comments, Z signups. Grateful for the feedback. Building [top request] this week." | 5 min |
| 9:00 PM | Plan tomorrow: What HN/Reddit posts go live? Any bugs to fix? Any quick wins from feedback? | 15 min |
| 9:15 PM | Set alarm for 7:00 AM Tuesday | 1 min |
| 9:30 PM | Last PH check. Respond if anything urgent | 5 min |
| 10:00 PM | Screen off. Sleep | -- |

### Phase 6: Day 2+ Cadence (Tuesday April 15 onward)

- **7:00 AM ET**: Wake, respond to overnight PH comments
- **8:00 AM ET**: Post Show HN (Tuesday is good for HN visibility)
- **9:00 AM - 12:00 PM ET**: Monitor PH + HN simultaneously (PH in tab 1, HN in tab 2)
- **12:00 PM ET**: Post to first Reddit subreddit (r/personalfinance)
- **Afternoon**: Stagger remaining Reddit posts per `HN_REDDIT_POSTS.md` Section 3 timing
- **Response priority**: PH > HN > Reddit (PH comments still rank-critical on Day 2)
- **Day 3+**: Reduce PH checks to every 2 hours. Focus on HN/Reddit engagement

---

## 3. Quick-Access Cheat Sheet

Print this section or keep it open on your phone during launch.

### Maker Comment (copy-paste ready)

```
I got a $487 electricity bill in January and spent an hour scrolling utility company websites. Turns out, in my state, I could've switched to a 40% cheaper plan for the same usage. I'd just... never checked.

That frustration became RateShift.

Here's what it does: RateShift pulls hourly electricity prices from NREL and EIA data feeds, runs an ensemble ML model to forecast 24-hour price movements (currently averaging 89% accuracy), and alerts you when switching saves real money. If you opt in, the auto-switcher handles the paperwork -- no more manual rate checking.

What makes it different:
- Built on public utility data, not a proprietary black box. You can see exactly why we're recommending a rate.
- The ML model isn't trained on marketing hype. It learns from actual electricity markets in deregulated states (17+ covered right now).
- Pricing reflects solo-founder reality: free tier for casual tracking, $4.99/mo for ML forecasts, $14.99/mo if you want the auto-switcher.

What I'm not claiming:
- This isn't available in all 50 states (deregulation is complicated).
- I'm not a team of 50. It's just me building and supporting this.
- I don't have a fancy sales pitch. I have a working product that finds cheaper rates.

This is an early-stage launch. I'm looking for your feedback, your edge cases, and your stories about how much you saved. If you spot a bug, tell me. If you have a feature idea, I want to hear it.

Let's fix the absurd problem of paying too much for electricity.
```

### Response Templates (one-line starters)

| Type | First Line | Full Template |
|------|-----------|---------------|
| Technical Q | "Great question. We use an ensemble approach (3-4 models)..." | FINAL_COPY.md Template A |
| Pricing Q | "Good catch. Free tier gets real-time tracking and one alert..." | FINAL_COPY.md Template B |
| Feature Req | "Love this. Short answer: yes, it's on the roadmap..." | FINAL_COPY.md Template C |
| Competitor Q | "I appreciate the directness. Here's the honest comparison..." | PRODUCT_HUNT.md Template D |
| Praise | "This means the world. Seriously. We built this because..." | FINAL_COPY.md Section 5 |

### Emergency Dashboards

| Service | URL | What to Check |
|---------|-----|---------------|
| Render (backend logs) | https://dashboard.render.com/web/srv-d649uhur433s73d557cg/logs | 5xx errors, OOM crashes |
| Neon (database) | https://console.neon.tech/app/projects/cold-rice-23455092/monitoring | Connection count, query latency |
| Cloudflare (worker) | https://dash.cloudflare.com/b41be0d03c76c0b2cc91efccdb7a10df/workers/services/view/rateshift-api-gateway/production/metrics | Error rate, request volume |
| Resend (email) | https://resend.com/emails | Delivery failures, bounce rate |
| Slack #incidents | https://electricityoptimizer.slack.com/archives/C0AKV2TK257 | Automated alerts |
| UptimeRobot | https://dashboard.uptimerobot.com | Uptime status (3 monitors) |
| GA4 | https://analytics.google.com (filter: source=producthunt) | Traffic, signups, conversions |
| Product Hunt | https://www.producthunt.com/posts/rateshift | Votes, comments, ranking |

### "If X Breaks, Do Y" -- Top 5 Failure Scenarios

**1. Site is completely down (502/503 on rateshift.app)**
- Check Render dashboard. If service crashed: click "Manual Deploy" to restart
- If Render is healthy: check Vercel deployments for frontend errors
- Post on PH: "We're experiencing a brief outage. Working on it now. Back in ~15 minutes."
- ETA: 5-15 minutes for Render restart, 2-3 minutes for Vercel redeploy

**2. Backend API returns 500 errors (signup/login broken)**
- Check Render logs for the stack trace
- If database-related: check Neon connection count (max 8 on free/launch plan)
- If auth-related: verify `BETTER_AUTH_SECRET` env var on Render
- Quick fix: restart Render service (Settings > Manual Deploy)
- Post on PH: "Some users are hitting an error on signup. Deploying a fix now."

**3. Welcome emails not sending (Resend quota or DKIM issue)**
- Check Resend dashboard for delivery status and error messages
- If quota hit: upgrade plan immediately (takes effect instantly)
- If DKIM/SPF failure: check Resend > Domains > rateshift.app for DNS status
- Fallback: Gmail SMTP is configured. Toggle `EMAIL_PROVIDER=smtp` in Render env vars and redeploy
- Non-critical for launch -- users can still use the product without welcome email

**4. AI Assistant (rateshift.app/assistant) not responding**
- Check Gemini API quota: https://aistudio.google.com/app/apikey (10 RPM / 250 RPD free tier)
- If Gemini rate-limited: Groq fallback should auto-trigger. Check Render logs for "Groq fallback"
- If both providers down: disable AI agent temporarily via `ENABLE_AI_AGENT=false` in Render env vars
- Post on PH: "AI assistant is temporarily unavailable. Core rate tracking and alerts work fine."

**5. Cloudflare Worker returning errors (rate limiting too aggressive)**
- Check CF Worker metrics for error rate
- If rate limiting is blocking legitimate users: increase limits in `workers/api-gateway/` and redeploy via `deploy-worker.yml` GHA workflow
- If KV is down: Worker fails open (designed for graceful degradation) -- monitor but no action needed
- Quick bypass: Frontend circuit breaker auto-falls back to Render origin on 502/503 for public endpoints

### CLI Health Check (run anytime)

```bash
echo "=== Backend ===" && curl -s https://api.rateshift.app/health | python3 -m json.tool
echo "=== Frontend ===" && curl -s -o /dev/null -w "HTTP %{http_code} (%{time_total}s)\n" https://rateshift.app
echo "=== CF Gateway ===" && curl -s -o /dev/null -w "HTTP %{http_code} (%{time_total}s)\n" https://api.rateshift.app/api/v1/health
```

---

## 4. Metrics Tracking Template

Copy this table into a spreadsheet or plain text file. Fill in each row at the scheduled times.

### Hourly Vote & Comment Log

| Time (ET) | PH Votes | PH Comments | PH Ranking | Signups (GA4) | Uptime | Notes |
|-----------|----------|-------------|------------|---------------|--------|-------|
| 3:01 AM (T+0) | 0 | 0 | -- | 0 | UP | Launch moment |
| 3:30 AM (T+0.5) | | | | | | |
| 4:00 AM (T+1) | | | | | | Pre-sleep snapshot |
| 8:00 AM (T+5) | | | | | | Wake up |
| 9:00 AM (T+6) | | | | | | |
| 10:00 AM (T+7) | | | | | | |
| 10:30 AM (T+7.5) | | | | | | |
| 11:00 AM (T+8) | | | | | | |
| 12:00 PM (T+9) | | | | | | |
| 1:00 PM (T+10) | | | | | | |
| 2:00 PM (T+11) | | | | | | |
| 3:00 PM (T+12) | | | | | | |
| 4:00 PM (T+13) | | | | | | |
| 5:00 PM (T+14) | | | | | | |
| 6:00 PM (T+15) | | | | | | |
| 8:00 PM (T+17) | | | | | | Daily snapshot |

### Comment Sentiment Tracker

| Time Window | Positive | Neutral | Negative | Key Themes |
|-------------|----------|---------|----------|------------|
| 3-4 AM (launch) | | | | |
| 8-10 AM | | | | |
| 10 AM-12 PM | | | | |
| 12-2 PM | | | | |
| 2-4 PM | | | | |
| 4-6 PM | | | | |
| 6-8 PM | | | | |
| **Day 1 Total** | | | | |

### Infrastructure Health Log

| Time (ET) | Render CPU | Render RAM | Neon Connections | CF Error Rate | Resend Delivered | Gemini RPD Used |
|-----------|-----------|-----------|-----------------|--------------|-----------------|----------------|
| 3:05 AM | | | | | | |
| 8:00 AM | | | | | | |
| 11:00 AM | | | | | | |
| 2:15 PM | | | | | | |
| 6:00 PM | | | | | | |
| 8:00 PM | | | | | | |

### Social Media Engagement Log

| Platform | Post Time (ET) | Impressions | Clicks | Replies | Link |
|----------|---------------|-------------|--------|---------|------|
| Twitter #1 | 3:07 AM | | | | |
| Twitter #2 | 9:30 AM | | | | |
| LinkedIn | 9:35 AM | | | | |
| Twitter #3 | 8:30 PM | | | | |
| Show HN (Day 2) | | | | | |
| Reddit (Day 2+) | | | | | |

### End-of-Day 1 Summary (fill at 8:00 PM ET)

```
Date: April 14, 2026
PH Final Ranking: #___
PH Total Votes: ___
PH Total Comments: ___
Comment Sentiment: ___% positive / ___% neutral / ___% negative
GA4 Signups: ___
GA4 Unique Visitors (from PH): ___
Trial Starts: ___
Pro Upgrades: ___
Uptime: ___%
Bugs Reported: ___
Bugs Fixed: ___
Top 3 Feature Requests:
  1. ___
  2. ___
  3. ___
Top 3 Positive Quotes:
  1. "___"
  2. "___"
  3. "___"
Critical Issues:
  - ___
Lessons Learned:
  - ___
Tomorrow's Priorities:
  1. ___
  2. ___
  3. ___
```

---

## Appendix A: Key Timing Reference

| Event | PT | ET | UTC |
|-------|----|----|-----|
| PH new day starts | 12:01 AM | 3:01 AM | 7:01 AM |
| Wake up | 11:50 PM (Apr 13) | 2:50 AM | 6:50 AM |
| Publish listing | 12:01 AM | 3:01 AM | 7:01 AM |
| Sleep window starts | 1:00 AM | 4:00 AM | 8:00 AM |
| Morning shift starts | 5:00 AM | 8:00 AM | 12:00 PM |
| US West Coast wakes | 6:00 AM | 9:00 AM | 1:00 PM |
| Peak voting window | 9:00 AM - 2:00 PM | 12:00 PM - 5:00 PM | 4:00 PM - 9:00 PM |
| Voting slows | 5:00 PM | 8:00 PM | 12:00 AM+1 |
| PH day ends | 11:59 PM | 2:59 AM+1 | 6:59 AM+1 |

## Appendix B: Files Quick Reference

| File | Purpose |
|------|---------|
| `docs/launch/FINAL_COPY.md` | Tagline, description, maker comment, FAQ, response templates |
| `docs/launch/PRODUCT_HUNT.md` | Full PH playbook, screenshot checklist, best practices |
| `docs/launch/HN_REDDIT_POSTS.md` | Show HN + 5 Reddit posts, comment response guide |
| `docs/launch/MONITORING_RUNBOOK.md` | Infrastructure monitoring, thresholds, incident playbooks |
| `docs/launch/assets/` | Gallery screenshots (01-08) |

## Appendix C: Do NOT Do List

- Do NOT launch on a different day "because you feel tired." Tuesday is optimal. Stick to the plan.
- Do NOT stay up all night. The 4 AM - 8 AM sleep window is mandatory. Exhaustion makes you write bad comments.
- Do NOT post to HN and Reddit on the same day as PH. You cannot monitor 3 platforms simultaneously as one person. PH is Day 1. HN is Day 2. Reddit is Day 2-3.
- Do NOT ask people to "please upvote." Ask for feedback. Votes follow good engagement.
- Do NOT delete negative comments or get defensive. Acknowledge, explain, invite the critic to help shape the product.
- Do NOT deploy new features during launch day. Code freeze from April 13, 6 PM ET through April 14, 8 PM ET. Hotfixes only.
- Do NOT forget to eat. Schedule meals at 6:30 PM (pre-launch), 11:30 AM, and 7:00 PM.
- Do NOT check competitor launches on PH during your launch. It will only distract you.
