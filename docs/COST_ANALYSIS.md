# RateShift — Cost Analysis & Infrastructure Budget

> Last updated: 2026-03-16

RateShift runs on an all-free-tier infrastructure stack. This document tracks actual resource consumption, identifies cost risks, and documents optimizations.

---

## 1. Current Cost Profile

| Service | Tier | Monthly Cost | Free Tier Limit | Usage Estimate | Risk |
|---------|------|-------------|-----------------|----------------|------|
| **Neon PostgreSQL** | Free | $0 | 0.5 GB storage, 100 compute-hours | ~25 compute-hours (est.) | Low |
| **Render** | Free | $0 | 750 hours, cold-sleeps after 15min | Always-on via cron wakeups | Medium |
| **Vercel** | Hobby | $0 | 100 GB bandwidth, 1000 serverless invocations | Well within limits | Low |
| **Cloudflare** | Free | $0 | 100K Worker requests/day, unlimited DNS | Well within limits | Low |
| **GitHub Actions** | Free | $0 | 2,000 min/mo (Linux) | ~2,700 min/mo (see below) | **High** |
| **Cloudflare Registrar** | — | ~$10/yr | N/A (domain registration) | Fixed cost | None |
| **Resend** | Free | $0 | 100 emails/day, 3K/mo | Low volume | Low |
| **OneSignal** | Free | $0 | 10K subscribers | Low volume | Low |
| **Sentry** | Free | $0 | 5K errors/mo | Low volume | Low |
| **Grafana Cloud** | Free | $0 | 50 GB traces, 10K metrics | Low volume | Low |
| **Total** | — | **~$0.83/mo** | — | — | — |

---

## 2. GitHub Actions Minutes Budget

### Free Tier: 2,000 min/mo (Linux runners)

### Workflow Inventory (Post-Optimization)

#### Cron-Triggered Workflows

| Workflow | Schedule | Runs/mo | Est. min/run | Est. min/mo |
|----------|----------|---------|-------------|-------------|
| `check-alerts.yml` | Every 2h | 360 | 2 | 720 |
| `fetch-weather.yml` | Every 6h | 120 | 2 | 240 |
| `sync-connections.yml` | Every 6h | 120 | 2 | 240 |
| `gateway-health.yml` | Every 12h | 60 | 2 | 120 |
| `daily-data-pipeline.yml` | Daily 3am | 30 | 5 | 150 |
| `market-research.yml` | Daily 2am | 30 | 3 | 90 |
| `kpi-report.yml` | Daily 6am | 30 | 2 | 60 |
| `dunning-cycle.yml` | Daily 7am | 30 | 2 | 60 |
| `self-healing-monitor.yml` | Daily 9am | 30 | 3 | 90 |
| `fetch-heating-oil.yml` | Weekly Mon | 4 | 2 | 8 |
| `scrape-portals.yml` | Weekly Sun | 4 | 3 | 12 |
| `owasp-zap.yml` | Weekly Sun | 4 | 5 | 20 |
| `db-maintenance.yml` | Weekly Sun | 4 | 2 | 8 |
| **Cron Subtotal** | | **826** | | **~1,818** |

#### Event-Triggered Workflows (variable)

| Workflow | Trigger | Est. runs/mo | Est. min/run | Est. min/mo |
|----------|---------|-------------|-------------|-------------|
| `ci.yml` | push/PR | 60 | 5 | 300 |
| `_backend-tests.yml` | called | 60 | 4 | 240 |
| `e2e-tests.yml` | push/PR | 20 | 15 | 300 |
| `deploy.yml` | push main | 15 | 3 | 45 |
| Other CI/CD | various | 10 | 2 | 20 |
| **Event Subtotal** | | **~165** | | **~905** |

#### **Total Estimated: ~2,723 min/mo**

> Still ~700 min over the 2K free limit. See [Future Optimizations](#6-future-optimizations) for closing the gap.

### Optimization History

| Date | Change | Saved (min/mo) |
|------|--------|---------------|
| 2026-03-16 | `check-alerts` 30min -> 2h | 2,160 |
| 2026-03-16 | `sync-connections` 2h -> 6h | 480 |
| 2026-03-16 | `gateway-health` 6h -> 12h | 120 |
| 2026-03-16 | `e2e-tests` remove daily cron | 450 |
| 2026-03-16 | Consolidate 4 daily workflows into 1 pipeline | 180 |
| 2026-03-16 | Reduce warmup overhead on high-freq workflows | ~240 |
| **Total Saved** | | **~3,630** |

---

## 3. External API Quota Dashboard

| API | Free Tier Limit | Usage Pattern | Est. Monthly Usage |
|-----|----------------|---------------|-------------------|
| **Gemini 3 Flash** | 10 RPM / 250 RPD | AI Agent queries + content moderation | ~100-200 calls |
| **Groq Llama 3.3 70B** | 30 RPM / 14.4K RPD | AI Agent fallback + content classification | ~50-100 calls |
| **Composio** | 1,000 actions/mo | Tool calls from AI Agent | ~50-200 actions |
| **Tavily** | 1,000 searches/mo | Market research (daily cron) | ~30 searches |
| **OpenWeatherMap** | 1,000 calls/day | Weather data (6h cron) | ~120 calls |
| **Diffbot** | 10K calls/mo | Rate extraction from scraped pages | ~30-60 calls |
| **EIA API** | Unlimited (gov) | Heating oil/propane prices | ~4-8 calls |
| **Nominatim** | 1 req/sec | Geocoding fallback | ~10-50 calls |
| **Sentry** | 5K errors/mo | Error tracking | ~100-500 events |
| **UptimeRobot** | 50 monitors | Health checks (5min interval) | Continuous |

---

## 4. Neon Compute Budget

### Free Tier: 100 compute-hours/month

#### Wake-Up Sources (Post-Optimization)

| Source | Frequency | Wake Duration (est.) | Hours/mo |
|--------|-----------|---------------------|----------|
| `check-alerts` cron | Every 2h | 1 min | 6h |
| `fetch-weather` cron | Every 6h | 1 min | 2h |
| `sync-connections` cron | Every 6h | 2 min | 4h |
| `daily-data-pipeline` | Daily | 5 min | 2.5h |
| `market-research` | Daily | 2 min | 1h |
| `kpi-report` / `dunning-cycle` | Daily | 1 min each | 1h |
| Weekly crons | Weekly | 2 min each | 0.5h |
| User traffic | Variable | Variable | ~5-10h |
| **Total Estimate** | | | **~22-27h** |

> Well within the 100h limit. Reducing cron frequency from Part 1 cut ~35 wake-ups/day.

---

## 5. Cost Scaling Projections

See also: `docs/SCALING_PLAN.md`

| Growth Milestone | First Paid Service | Est. Monthly Cost |
|-----------------|-------------------|------------------|
| 100 daily users | Render Starter ($7) | $7 |
| 500 daily users | + Neon Launch ($19) | $26 |
| 1K daily users | + Vercel Pro ($20) | $46 |
| 5K daily users | + dedicated runner, Redis | $80-120 |
| 10K+ daily users | Full paid stack | $200-400 |

### Render Starter ($7/mo) ROI Analysis

Upgrading to Render Starter eliminates cold-start delays and warmup steps:
- Removes ~500 min/mo of GHA warmup overhead
- Drops total GHA to ~2,200 min/mo (near free tier)
- Improves user experience (no 15-30s cold starts)
- **Break-even**: When cold-start complaints affect retention

---

## 6. Future Optimizations

### Option A: Self-Hosted ARM Runner (Oracle Cloud Free Tier)
- **Cost**: $0 (Oracle always-free ARM instance)
- **Benefit**: Unlimited GHA minutes for cron workflows
- **Effort**: Medium (setup, maintenance)
- **Risk**: Oracle free tier reliability

### Option B: Cloudflare Workers Cron Triggers
- **Cost**: $0 (5 free cron triggers on Workers free plan)
- **Benefit**: Move high-frequency crons off GHA entirely
- **Effort**: Low (extend existing CF Worker)
- **Best candidates**: `check-alerts`, `fetch-weather` (highest frequency)

### Option C: Batch Internal API Endpoint
- **Cost**: $0
- **Benefit**: Single `/internal/batch` call replaces multiple sequential calls
- **Effort**: Medium (new backend endpoint)
- **Savings**: Minor (mostly reduces warmup duplication)

### Option D: Render Starter Upgrade ($7/mo)
- **Cost**: $7/mo
- **Benefit**: Eliminates all warmup overhead (~500 min/mo GHA savings)
- **Effort**: None (config change)
- **Break-even**: When cold starts affect user experience

### Recommended Path
1. **Now**: Cron reduction + consolidation (this PR) — saves ~3,630 min/mo
2. **If still over 2K**: Move `check-alerts` to CF Worker Cron Trigger
3. **At 100 DAU**: Upgrade Render to Starter ($7/mo)
4. **At 500 DAU**: Evaluate self-hosted runner vs paid GHA

---

## 7. Monthly Review Checklist

1. [ ] Check GHA minutes: `github.com/JoeyJoziah/electricity-optimizer/settings/billing`
2. [ ] Check Neon compute hours: Neon console > project `cold-rice-23455092` > Usage
3. [ ] Check Vercel bandwidth: Vercel dashboard > Usage
4. [ ] Check Cloudflare Worker requests: CF dashboard > Workers > Analytics
5. [ ] Check Sentry error quota: Sentry > Settings > Subscription
6. [ ] Check Gemini/Groq API usage: respective dashboards
7. [ ] Check Composio action count: Composio dashboard
8. [ ] Review `self-healing-monitor` for recurring failures (wasted GHA minutes)
9. [ ] Check Resend email volume: Resend dashboard
10. [ ] Review Grafana Cloud trace ingestion: Grafana > Usage stats
