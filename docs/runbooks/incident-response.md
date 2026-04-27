# RateShift Incident Response Runbook

> **PURPOSE**: Incident severity definitions, SLAs, escalation tree, communication templates, and PIR procedures.
>
> **LAST UPDATED**: 2026-04-27
> **STATUS**: Production-ready
> **OWNER**: Devin McGrath (devmcgrath@gmail.com)
> **SOLO FOUNDER**: All escalation paths terminate at owner

---

## Table of Contents

1. [Severity Definitions](#severity-definitions)
2. [Response SLAs](#response-slas)
3. [Escalation Tree](#escalation-tree)
4. [Comms Templates](#comms-templates)
5. [Post-Incident Review (PIR)](#post-incident-review-pir)
6. [Worked Example: Stripe Webhook Backlog](#worked-example-stripe-webhook-backlog)

---

## Severity Definitions

| Level | Name | Criteria | Examples |
|-------|------|----------|----------|
| **P0** | **CRITICAL** | All users blocked / data loss / autonomous money movement broken / security breach | Database completely down. Stripe billing broken (users cannot subscribe). Rate Switcher executing wrong transactions. All authentication failed. Payment processing hung. Sensitive data exposed. |
| **P1** | **HIGH** | Single feature down / >25% users affected / degraded core path | API responses all 502. Email delivery failed for 3+ hours. ML forecasts returning NaN. Single region down. Metrics collection unavailable. |
| **P2** | **MEDIUM** | Degraded UX / specific cohort affected / <25% users / workaround exists | Frontend slow (>5s load). One region's rates stale >4h. Dashboard missing charts. Non-critical API endpoint down. |
| **P3** | **LOW** | Cosmetic / typo / minor bug / single user report | UI text alignment. Color picker off-by-one. Example in docs outdated. Single user reports intermittent API timeouts. |

---

## Response SLAs

| Severity | Ack SLA | Mitigation SLA | Investigation SLA | Owner |
|----------|---------|---------------|--------------------|-------|
| **P0** | 15 min | 1 hour | Continuous until resolved | Devin McGrath (devmcgrath@gmail.com) |
| **P1** | 1 hour | 4 hours | Next business day | Devin McGrath (same) |
| **P2** | Next business day | 1 week | Next sprint | Backlog / roadmap priority |
| **P3** | Next sprint | 30 days | As resources permit | Backlog / low priority |

**Notes**:
- **Ack SLA**: Time to confirm receipt and begin initial investigation
- **Mitigation SLA**: Time to deploy a fix or workaround (even if partial)
- **Investigation SLA**: Time to publish root-cause findings
- Solo founder: all escalation paths terminate at Devin. No external support SLAs yet (future work: document Anthropic/Render/Cloudflare support contacts if available)

---

## Escalation Tree

```
Incident Detected (Any Channel)
    ↓
File P0/P1/P2/P3 in Slack #incidents thread
    ↓
Assign severity (see Severity Definitions above)
    ↓
Page Devin McGrath → devmcgrath@gmail.com + Slack DM (@devinmcgrath)
    ↓
Devin acknowledges (within SLA)
    ↓
Triage → mitigation → validation → PIR
    ↓
Resolution (file in docs/incidents/, update this runbook)
```

### Escalation Contacts

| Contact | Channel | Role | SLA Response |
|---------|---------|------|--------------|
| **Devin McGrath** | devmcgrath@gmail.com | Solo founder, incident commander | See SLAs above |
| **Slack** | @devinmcgrath in workspace `electricityoptimizer.slack.com` | Backup to email | 15 min (P0) |

### Future External Escalations (Post-Series-A)

Once product reaches scale, add:
- **Anthropic (Claude Support)**: If AI Agent service fails (Gemini 3 Flash fallback to Groq)
- **Render (Support)**: If backend SLA breached (upgrade to Starter tier $7/mo with 99.5% SLA)
- **Cloudflare (Enterprise)**: If CF Worker outages (currently Pro tier, no SLA)
- **Stripe (Support)**: If webhook delivery backlog >1h (Enterprise plan includes priority support)
- **Neon (Support)**: If database is unavailable >15 min (free tier has no SLA; upgrade to paid)

---

## Comms Templates

### 1. Internal Slack #incidents Thread Template

Post immediately when P0/P1 detected:

```
SEVERITY: [P0/P1/P2/P3]
COMPONENT: [e.g., "Backend API", "Database", "Email", "Stripe Billing", "ML Pipeline"]
STATUS: INVESTIGATING

WHAT HAPPENED
[1-2 sentences describing the issue from user perspective]

SCOPE
- [e.g., All users / Pro tier only / Single region]
- Estimated users affected: [number]
- Started: [timestamp UTC]

SUSPECTED CAUSE
[Initial hypothesis; update as investigation progresses]

CURRENT ACTION
- [Step 1]
- [Step 2]
- [Step 3]

NEXT UPDATE
[e.g., "15 min" or "within SLA"]

---

Thread: Use this thread for all updates. React with 🟢 when resolved.
PIR: Will file at docs/incidents/YYYY-MM-DD-{slug}.md
```

**Example P0 post**:
```
SEVERITY: P0
COMPONENT: Backend API / Stripe Billing
STATUS: INVESTIGATING

WHAT HAPPENED
Users report "payment failed" and are downgraded to Free tier even though they subscribed successfully.

SCOPE
- All new subscribers in the last 2 hours
- Estimated users affected: ~12
- Started: 2026-04-27 14:35 UTC

SUSPECTED CAUSE
Stripe webhook delivery backlog after Render redeploy. Webhooks queued but not processed.

CURRENT ACTION
1. Checking Stripe dashboard for webhook delivery logs
2. Will manually replay missed `payment_succeeded` events
3. Verifying user subscription_tier updates in database

NEXT UPDATE
10 min (within 15 min SLA)
```

### 2. User-Facing Status Page Template

Post to `status.rateshift.app` (if it exists; otherwise skip or use Twitter):

**Title**: [Service] - Service Disruption

**Content**:
```
We're currently experiencing issues with [component]. Our team is investigating and working on a fix.

Started: [timestamp]
Last updated: [timestamp]
Status: [Investigating / Mitigation in Progress / Resolved]

What we're doing:
- [Action 1]
- [Action 2]
- [Action 3]

We'll post updates every 30 minutes. Thank you for your patience.
```

**Example**:
```
Pricing Data - Service Disruption

We're currently experiencing issues with real-time price data updates for some regions. Our team is investigating.

Started: 2026-04-27 14:35 UTC
Status: Mitigation in progress

What we're doing:
- Investigating stale data in ML pipeline
- Rolling back to previous model version
- Validating forecast accuracy

We'll post updates every 30 minutes.
```

**Note**: Status page may not exist yet. Create `status.rateshift.app` as future work if outages become frequent.

### 3. Email Template for Affected Users (P0 Billing/Data Loss)

**To**: All affected users (via Resend + Gmail SMTP fallback)
**From**: RateShift <noreply@rateshift.app>
**Subject**: Important: Your RateShift Account

```
Hi [Name],

We experienced a brief service disruption that affected your account. 
We've resolved the issue and want to make sure everything is working correctly for you.

WHAT HAPPENED
[1-2 sentences explaining in user-friendly terms, e.g., 
"Your payment was processed successfully, but a temporary system issue 
prevented your account tier from updating immediately."]

WHAT WE DID
[What was fixed, e.g., "We've now restored your Pro tier access and 
confirmed all your settings are intact."]

YOUR ACCOUNT STATUS
- Subscription Tier: [Pro / Business]
- Next Billing Date: [date]
- Access: [All features available / [List restored features]]

NEXT STEPS
1. Log in to confirm everything looks correct: https://rateshift.app
2. Check your billing history: https://rateshift.app/account/billing
3. Contact us if anything seems wrong: devmcgrath@gmail.com

We apologize for any inconvenience. Our infrastructure is designed to prevent 
this from happening again.

Best regards,
The RateShift Team
```

**Example**:
```
Hi Alice,

We experienced a brief service disruption that affected new subscriber activations 
between 14:35–14:52 UTC. We've resolved the issue and restored all accounts.

WHAT HAPPENED
Your Pro subscription was charged successfully on April 27 at 14:41 UTC, 
but a temporary Stripe webhook processing delay prevented your account tier 
from updating in our system immediately.

WHAT WE DID
We've manually verified and restored your Pro tier access, and confirmed all 
your alerts and settings are intact. All future payments will process normally.

YOUR ACCOUNT STATUS
- Subscription Tier: Pro
- Next Billing Date: May 27, 2026
- Access: All features available (Forecasts, Savings, Recommendations)

NEXT STEPS
1. Log in to confirm: https://rateshift.app
2. Review your billing history: https://rateshift.app/account/billing
3. Email us if anything seems off: devmcgrath@gmail.com

We apologize for the inconvenience.

Best regards,
The RateShift Team
```

### 4. Stripe Customer Comms Template (Billing Incident)

**Use**: When P0/P1 involves incorrect charges, downgraded tiers, or payment failures

**Channel**: Email (via Resend) + Stripe dashboard note

**Subject**: Your RateShift Payment & Account Status

```
Hi [Customer Name],

Following up on the [DATE] incident that affected RateShift billing.

YOUR PAYMENT
- Amount charged: $[amount]
- Date: [date]
- Status: [Processed / Refunded / Adjusted]

YOUR ACCOUNT
- Previous tier: [Free / Pro / Business]
- Current tier: [Free / Pro / Business]
- Changes made: [e.g., "Manually restored Pro tier after webhook delay"]

VERIFICATION
We've verified with your subscription in Stripe that everything is now in sync:
- Stripe status: [Active / Cancelled]
- Next billing date: [date]
- Refunds (if any): [None / Issued on [date]]

NEXT BILLING
[Your next charge of $X will be on DATE / No further charges will be made]

If you have questions or need anything, reply to this email or contact us at devmcgrath@gmail.com.

Best regards,
RateShift Support
```

---

## Post-Incident Review (PIR)

### Template: `docs/incidents/YYYY-MM-DD-{slug}.md`

Create a new file for every P0, P1, and P2 incident. Format:

```markdown
# Incident Report: [Title]

Date: YYYY-MM-DD
Severity: [P0/P1/P2]
Author: [Name]
Reviewers: [Names]

## Summary

[1-paragraph executive summary: what happened, how long, how many affected, root cause]

## Timeline

| Time (UTC) | Event |
|----------|-------|
| HH:MM | Incident started (user reports / alert fired / system detected) |
| HH:MM | Acknowledged by Devin |
| HH:MM | Mitigation step 1 taken |
| HH:MM | Mitigation step 2 taken |
| HH:MM | Validation passed |
| HH:MM | Incident resolved |

**Total Duration**: X minutes
**Time to Ack**: X minutes
**Time to Mitigation**: X minutes

## Root Cause Analysis

### What Happened (Symptom)
[What the user or monitoring system observed]

### Why It Happened (Root Cause)
[Deep explanation: code bug? infrastructure? operator error? dependency?]

### Contributing Factors
- [Factor 1: e.g., "No error handling for webhook delivery timeout"]
- [Factor 2: e.g., "Insufficient monitoring on Stripe event queue"]
- [Factor 3: e.g., "Manual override without logging"]

## Impact

- **Users Affected**: [Number or percentage]
- **Scope**: [Which regions/features/tiers]
- **Data Loss**: [None / Some user data / Financial impact]
- **SLA Breach**: [Yes / No] (if yes, which SLA)

## Remediation

### Immediate Actions Taken
1. [Action and rationale]
2. [Action and rationale]

### Post-Incident Remediations (Action Items)

| Item | Owner | Target Date | Status |
|------|-------|------------|--------|
| [e.g., "Add error handling for Stripe webhook timeout"] | Devin | [Date] | [ ] |
| [e.g., "Set up Sentry alert for webhook processing delay"] | Devin | [Date] | [ ] |
| [e.g., "Document manual override procedures in runbook"] | Devin | [Date] | [ ] |

### How to Prevent This Again

1. **Code**: [Changes to make]
2. **Monitoring**: [New alerts / dashboards]
3. **Documentation**: [Runbooks / FAQs]
4. **Process**: [New checks / procedures]

## Lessons Learned

### What Went Well
- [e.g., "Slack alerting was fast and clear"]
- [e.g., "Stripe idempotency table prevented duplicate charges"]

### What Could Be Better
- [e.g., "Manual replay should log which webhooks were resent"]
- [e.g., "No alert for webhook delivery delay >5min"]

## Appendix

### Relevant Links
- [Slack thread](https://link)
- [GitHub issue](https://link)
- [Sentry alert](https://link)

### Logs / Artifacts
- Sentry error rate graph (2026-04-27 14:30–15:00 UTC)
- Stripe webhook delivery logs
- Render backend logs snippet
```

### Example PIR: Stripe Webhook Backlog

See [Worked Example](#worked-example-stripe-webhook-backlog) below.

### PIR Review Checklist

Before closing an incident:

- [ ] Timeline is accurate (timestamps in UTC)
- [ ] Root cause is identified (not just "webhook failed" but WHY)
- [ ] Contributing factors are listed (what made it worse?)
- [ ] Action items have owners and target dates
- [ ] Prevention strategy is specific (not vague "improve monitoring")
- [ ] Worked example or test case added to prevent regression
- [ ] Runbook updated if procedure was unclear
- [ ] Slack thread links to final PIR

---

## Worked Example: Stripe Webhook Backlog

**Scenario**: After a Render redeploy, Stripe webhook delivery backs up and some users' subscriptions don't update for 2+ hours.

### Incident Timeline

```
2026-04-27 14:30 UTC — Render backend redeploy triggered (auto via GitHub merge to main)
2026-04-27 14:35 UTC — Render completes redeploy (~5 min startup time)
2026-04-27 14:35 UTC — First user reports "I paid but still on Free tier"
2026-04-27 14:37 UTC — Slack alert fires: "Stripe webhook processing delay detected"
2026-04-27 14:40 UTC — Devin sees alert, begins investigation (within 5 min, well under 15 min P0 SLA)
2026-04-27 14:42 UTC — Devin posts to #incidents: P0 CRITICAL, investigating
2026-04-27 14:45 UTC — Root cause identified: webhook endpoint was returning 429 during redeploy startup
2026-04-27 14:48 UTC — Mitigation: manually resend webhooks via Stripe dashboard for 14:35–14:45 window
2026-04-27 14:52 UTC — Validation: user reports "I see Pro tier now!", Stripe shows 12 users fixed
2026-04-27 15:00 UTC — All webhooks caught up, incident resolved
```

**Total Duration**: 30 minutes
**Time to Ack**: 5 minutes (within 15 min SLA)
**Time to Mitigation**: 17 minutes (within 1 hour SLA)

### Incident Report

**File**: `docs/incidents/2026-04-27-stripe-webhook-backlog.md`

```markdown
# Incident Report: Stripe Webhook Delivery Backlog After Redeploy

Date: 2026-04-27
Severity: P0 (Billing broken, users cannot activate subscriptions)
Author: Devin McGrath
Reviewers: [None — solo founder]

## Summary

After a scheduled Render backend redeploy (14:30 UTC), the Stripe webhook endpoint 
returned 429 (too many requests) during the 5-minute startup window (14:30–14:35). 
Stripe queued ~47 pending webhooks. During this window, 12 users subscribed via the 
frontend but their `users.subscription_tier` was not updated. 

Root cause: Missing rate-limit handling on the webhook endpoint during cold starts. 
Fixed via manual webhook resend via Stripe dashboard (14:48 UTC). All 12 affected 
users' accounts restored by 14:52 UTC.

## Timeline

| Time (UTC) | Event |
|----------|-------|
| 14:30 | Render redeploy triggered (auto-deploy from GitHub merge) |
| 14:35 | Render backend online, but cold start CPU spike (short-lived queue backlog) |
| 14:35 | 1st user: "I paid but still on Free tier" (Slack DM to Devin) |
| 14:37 | Sentry alert: "stripe_webhook_processing_delay > 5 min" |
| 14:40 | Devin sees alert, opens #incidents, posts P0 triage |
| 14:42 | Dashboard check: Stripe showing 47 pending webhook deliveries, all 429s |
| 14:45 | Root cause confirmed: `/billing/webhook` endpoint rate-limited during startup |
| 14:48 | Mitigation: Devin opens Stripe dashboard, manually resends webhook batch for 14:30–14:50 window |
| 14:52 | User confirms "Pro tier restored!"; database shows all 12 users updated |
| 15:00 | No new webhook delays, incident resolved |

**Total Duration**: 30 minutes
**Time to Ack**: 5 minutes (within 15 min P0 SLA ✓)
**Time to Mitigation**: 17 minutes (within 1 hour P0 SLA ✓)

## Root Cause Analysis

### What Happened (Symptom)
Users successfully paid via Stripe but were not upgraded to Pro/Business tier. 
Slack alerts and Sentry logged high webhook processing latency (429 errors).

### Why It Happened (Root Cause)
1. Render backend redeploy completed at 14:35 UTC (5 min startup time)
2. During startup, FastAPI cold start + model loading caused CPU spike
3. Webhook endpoint `/billing/webhook` was not rate-limited internally, so every 
   concurrent request consumed a DB connection
4. Under load (12 simultaneous webhook deliveries), DB connection pool exhausted
5. Stripe received 429 responses and queued retries exponentially
6. Retries caught up only after load subsided (15 min post-startup)

### Contributing Factors
- **No circuit breaker on webhook endpoint**: Should have rejected early if queue > 50
- **No startup detection**: Backend doesn't tell Stripe "I'm cold-starting, retry harder"
- **Insufficient monitoring**: Alert fired at T+7 min, but mitigation was manual (T+18 min)
- **No automated webhook replay**: Had to manually resend via Stripe dashboard (error-prone)

## Impact

- **Users Affected**: 12 (all who subscribed during 14:30–14:45 UTC window)
- **Scope**: All tiers (Pro and Business)
- **Data Loss**: None (all charges succeeded in Stripe; just tier mismatch in app DB)
- **Financial Impact**: None (charges already processed; users just lacked feature access)
- **SLA Breach**: No (mitigated within 1 hour P0 SLA)

## Remediation

### Immediate Actions Taken
1. **Webhook Replay** (14:48 UTC): Manually resent all 47 pending webhooks from Stripe dashboard for the 14:30–14:50 window using Stripe's webhook resend feature
   - **Rationale**: Idempotency table (`stripe_processed_events`) ensures duplicate processing is safe
   - **Result**: All 12 users' subscription_tier updated to correct value within 4 minutes

### Post-Incident Action Items

| Item | Owner | Target Date | Status |
|------|-------|------------|--------|
| Add rate-limit circuit breaker to `/billing/webhook` endpoint (reject if queue > 100) | Devin | 2026-05-02 | [ ] |
| Set up Sentry alert: webhook processing delay > 3 min (vs current 5 min) | Devin | 2026-05-02 | [ ] |
| Implement automated webhook replay if idempotency table detects gaps | Devin | 2026-05-09 | [ ] |
| Add pre-deploy health check: run curl on webhook endpoint with dummy payload | Devin | 2026-05-02 | [ ] |
| Document webhook replay procedure in DISASTER_RECOVERY.md | Devin | 2026-05-02 | [ ] |

### How to Prevent This Again

1. **Code**:
   - Add asyncio.Semaphore to webhook handler to limit concurrent DB writes (max 50)
   - Raise 503 Service Unavailable if semaphore queue > 100 (let Stripe retry after 30s)
   - Log every webhook processing attempt with (event_id, status, duration)

2. **Monitoring**:
   - Add Sentry alert: `stripe.webhook.processing_delay > 180s` (3 min, vs current 5 min)
   - Add dashboard: webhook delivery latency percentiles (p50, p95, p99)
   - Add metric: failed webhook deliveries (429/5xx) per minute

3. **Documentation**:
   - Update DISASTER_RECOVERY.md section "Stripe State Out-of-Sync" with webhook replay steps
   - Add incident-response.md worked example (this document)

4. **Process**:
   - Pre-deploy: Run `./scripts/health-check-webhook.sh` in CI before deploying backend
   - Post-deploy: Render notifies Slack #deployments with "Backend ready, webhook verified"

## Lessons Learned

### What Went Well
- ✓ Slack alert fired quickly (T+7 min) and was specific ("webhook_processing_delay")
- ✓ Stripe idempotency table prevented duplicate charges (users were not double-billed)
- ✓ User reached out immediately, surface issue quickly
- ✓ Manual webhook resend via Stripe dashboard worked well (no custom code needed)
- ✓ SLA targets were met (ack in 5 min, mitigation in 17 min)

### What Could Be Better
- Alert threshold too high (5 min → should be 3 min)
- No automated replay (required manual Stripe dashboard navigation, error-prone at scale)
- Cold-start rate-limiting not documented in runbook (ops person would have to guess)
- No metric for "webhook queue depth" (only saw backlog via Stripe, not in app logs)

## Appendix

### Relevant Logs / Artifacts

**Sentry Alert** (2026-04-27 14:37 UTC):
```
stripe_webhook_processing_delay_seconds = 429 (timestamp 14:37)
Alert rule: webhook_processing_time > 300s
Affected endpoint: POST /billing/webhook
```

**Stripe Dashboard** (Webhooks → Event Deliveries):
```
Event: invoice.payment_succeeded (ID: evt_1QxAbc...)
Delivery attempts:
  14:35:22 — Failed (429 Webhook endpoint returned 429)
  14:36:08 — Failed (429)
  14:37:55 — Failed (429)
  14:39:42 — Success (200 OK)
```

**Render Logs** (2026-04-27 14:30–14:40):
```
[14:30:15] Build started
[14:35:04] Build successful, server starting
[14:35:22] POST /billing/webhook — 200 OK (15ms) — 1/50 concurrent
[14:35:23] POST /billing/webhook — 429 Too Many Requests (50ms) — 50/50 concurrent
[14:35:24] POST /billing/webhook — 429 Too Many Requests (80ms) — DB pool exhausted
```

### Files Changed for Prevention
- `backend/api/v1/billing.py` — add Semaphore to webhook handler
- `.github/workflows/deploy-backend.yml` — add health check step
- `docs/DISASTER_RECOVERY.md` — add webhook replay section
- `scripts/health-check-webhook.sh` — new pre-deploy validation script
```

---

## Quick Reference Checklist

### When an Incident is Reported

- [ ] **Classify**: P0 / P1 / P2 / P3
- [ ] **Post**: Slack #incidents thread with template
- [ ] **Page**: Devin (@devinmcgrath on Slack + devmcgrath@gmail.com)
- [ ] **Investigate**: Check DISASTER_RECOVERY.md for this scenario
- [ ] **Mitigate**: Follow recovery steps
- [ ] **Validate**: Confirm fix with smoke tests
- [ ] **Notify**: Update Slack thread, post status page if P0/P1
- [ ] **File**: PIR in docs/incidents/YYYY-MM-DD-{slug}.md
- [ ] **Follow-up**: Track action items to completion

### Incident Commander Responsibilities (Devin)

1. **Ack** (within SLA): Confirm receipt in Slack
2. **Triage**: Assign severity, identify on-call expert (currently Devin)
3. **Coordinate**: Post updates every 15 min (P0) or 1 hour (P1)
4. **Mitigate**: Follow runbook or decide on custom response
5. **Validate**: Confirm fix with tests/dashboards
6. **Comms**: Notify users if P0 (email + status page)
7. **Document**: File PIR before moving on

### Post-Incident Duty

1. **PIR**: Complete within 3 business days
2. **Action Items**: Assign owner and target date
3. **Prevention**: Update runbook or add test
4. **Communication**: Share PIR with team (Slack thread)
5. **Blameless**: Focus on systems, not people

---

## Appendix: External Support Contacts (Future)

### When to Escalate to Vendor Support

**Render (Backend Infrastructure)**
- Contact: support@render.com or Slack @Render (if Slack workspace joined)
- Condition: Backend 5xx errors persist after 15 min, or Render status page shows incident
- SLA: Response time depends on Render plan (currently free tier = no SLA; Starter $7/mo = 99.5% uptime)

**Cloudflare (Edge Layer / CF Worker)**
- Contact: support@cloudflare.com or Slack (if Cloudflare workspace joined)
- Condition: CF Worker deployment failed, rollback doesn't work, or status page shows incident
- SLA: Pro tier = business hours support; Enterprise = 24/7 (currently Pro)

**Stripe (Payments)**
- Contact: support@stripe.com or dashboard support chat
- Condition: Webhook delivery backlog >1 hour, or Stripe status page shows incident
- SLA: Standard = business hours; Premium/Enterprise = 24/7 response (currently Standard)

**Neon (Database)**
- Contact: support@neon.tech or docs feedback
- Condition: Database unavailable >10 min, restore failed, or Neon status page shows incident
- SLA: Free tier = no SLA; Paid = support available (currently free tier)

---

## Document Version History

| Date | Author | Change |
|------|--------|--------|
| 2026-04-27 | Devin McGrath | Initial version: severity definitions, SLAs, templates, PIR format, worked example |
