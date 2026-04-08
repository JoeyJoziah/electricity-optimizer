# Launch Day Monitoring Setup
**Complete before: April 13, 2026 (T-24h)**

---

## 1. GA4 Product Hunt Referrer Filter

### Setup Steps
1. Go to [analytics.google.com](https://analytics.google.com)
2. Navigate to **Reports > Acquisition > Traffic acquisition**
3. Add filter: `Session source = producthunt.com`
4. Save as custom report: "Product Hunt Launch Traffic"
5. Add secondary dimension: "Landing page"

### UTM Tracking
Add to all PH-related links:
```
?utm_source=producthunt&utm_medium=post&utm_campaign=launch_apr2026
```

### Key Metrics to Watch
- Sessions from PH referrer
- Signup conversion rate (events: `sign_up`)
- Pages per session (engagement depth)
- Bounce rate on landing page

---

## 2. Vote & Comment Tracking Spreadsheet

### Google Sheets Template

Create a sheet with these columns:

| Time (ET) | PH Votes | PH Rank | Comments | Signups (GA4) | Sentiment (+/0/-) | Notes |
|-----------|----------|---------|----------|---------------|-------------------|-------|
| 3:00 AM | 0 | — | 0 | 0 | — | Launch |
| 4:00 AM | | | | | | |
| 5:00 AM | | | | | | |
| ... | | | | | | |
| 11:00 PM | | | | | | |

**Update cadence**: Every hour for first 12 hours, every 2 hours after that.

---

## 3. Slack Alerts

### Channels
- `#incidents` (C0AKV2TK257) — production issues
- `#deployments` (C0AKCN6T02Z) — deploy notifications
- `#metrics` (C0AKDD7P2HX) — performance alerts

### Verify Webhook
```bash
# Test fire to #incidents
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"[TEST] Launch monitoring active. This is a test alert."}' \
  "$SLACK_INCIDENTS_WEBHOOK_URL"
```

### What Triggers Alerts
- UptimeRobot: rateshift.app down > 30s
- GHA self-healing monitor: workflow failures
- CF Worker: error rate > 5% (via cron check)

---

## 4. Infrastructure Dashboards (Bookmark These)

Open all in a browser folder for quick access:

| Dashboard | URL | What to Watch |
|-----------|-----|---------------|
| **Render** | https://dashboard.render.com | CPU, RAM, request count, errors |
| **Neon** | https://console.neon.tech/app/projects/cold-rice-23455092 | Active connections, compute hours used |
| **Cloudflare** | https://dash.cloudflare.com (zone ac03dd28) | Requests, cache hit ratio, rate limiting |
| **Vercel** | https://vercel.com/dashboard | Deployment status, edge function invocations |
| **GA4** | https://analytics.google.com | Real-time users, PH referrer traffic |
| **Resend** | https://resend.com/emails | Email delivery rate, bounces, complaints |
| **Stripe** | https://dashboard.stripe.com | New subscriptions, payment failures |
| **OneSignal** | https://app.onesignal.com | Push notification delivery |
| **UptimeRobot** | https://uptimerobot.com/dashboard | Uptime status, response times |
| **GitHub Actions** | https://github.com/[repo]/actions | Workflow status, minutes used |

---

## 5. Real-Time Monitoring Checklist (Launch Day)

### Every 30 Minutes (Hours 0-6)
- [ ] Check PH vote count and ranking
- [ ] Respond to new comments (< 5 min SLA)
- [ ] Glance at Render CPU/RAM (should be < 80%)
- [ ] Check GA4 real-time for traffic anomalies

### Every Hour (Hours 6-24)
- [ ] Log metrics in tracking spreadsheet
- [ ] Check Slack #incidents for alerts
- [ ] Verify email delivery in Resend dashboard
- [ ] Check Neon compute hours (budget: 100h/mo)

### Red Flags (Act Immediately)
| Signal | Action |
|--------|--------|
| Render CPU > 90% for 5+ min | Consider Render Starter+ ($25/mo) upgrade |
| Neon connections > 90 | Verify pooler endpoint is in use |
| Email bounce rate > 5% | Check Resend domain verification |
| CF Worker error rate > 5% | Check `api.rateshift.app/internal/gateway-stats` |
| Site fully down | Check Render → CF Worker → Neon in order |
| Stripe webhook failures | Check webhook endpoint logs in Render |

---

## 6. Post-Launch Metrics Snapshot (End of Day 1)

Capture these at midnight ET April 14:

```
PH Final Rank: #___
PH Votes (24h): ___
PH Comments: ___
Total Signups: ___
Pro Trial Starts: ___
Unique Visitors (GA4): ___
Bounce Rate: ___%
Avg Session Duration: ___
Emails Sent: ___
Email Delivery Rate: ___%
API Requests (CF): ___
Cache Hit Ratio: ___%
Peak Concurrent Users: ___
Uptime: ___%
Errors Logged: ___
```

Save this to `docs/launch/DAY1_METRICS.md` after launch.
