ARCHIVED (2026-03-16) — Wave 2 infrastructure upgrades are complete. The project has moved beyond free tier to Render paid, Neon paid (cold-rice-23455092), and Cloudflare Workers with native rate limiting. For current infrastructure details, see `docs/INFRASTRUCTURE.md` and `docs/DEPLOYMENT.md`.

---

# Infrastructure Upgrade Runbook — Wave 2

**Created:** 2026-03-11
**Context:** Multi-utility expansion (gas + community solar + onboarding v2 + data quality)

---

## Current State (Free Tier)

| Service | Plan | Cost | Limits |
|---------|------|------|--------|
| Neon PostgreSQL | Free | $0/mo | 0.5 GiB storage, 1 compute (0.25 vCPU) |
| Render | Free | $0/mo | 512 MB RAM, spins down after 15 min idle |
| Vercel | Hobby | $0/mo | 100 GB bandwidth |
| Cloudflare | Free + Workers | $0/mo | 100K requests/day |

**Total: $0/mo**

---

## Upgrade Triggers

### Neon: Free -> Pro ($19/mo)

**When to upgrade:**
- Storage exceeds 450 MiB (Free limit: 512 MiB, buffer at ~88%)
- Compute hours exceed 150h/mo (Free limit: ~191h)
- Need for branching (dev/staging branches)

**What you get:**
- 10 GiB storage included
- 300 compute hours/mo
- Autoscaling (0-4 vCPU)
- Point-in-time restore (7 days)
- IP Allow Lists

**Monitoring:**
```sql
-- Check current storage
SELECT pg_size_pretty(pg_database_size('neondb'));

-- Check table sizes
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC
LIMIT 10;
```

**Upgrade steps:**
1. Go to Neon Console > Project `cold-rice-23455092` > Billing
2. Switch to Pro plan
3. Verify compute endpoint `ep-withered-morning` still active
4. No migration needed — data stays in place

**Rollback:**
- Downgrade via Neon Console (data preserved up to free tier limits)
- If over 512 MiB, must reduce data first

### Render: Free -> Starter ($7/mo)

**When to upgrade:**
- Memory pressure detected (OOM kills in logs)
- Cold start latency unacceptable for cron jobs
- Need persistent disk or always-on

**What you get:**
- 512 MB RAM (same, but always-on)
- No spin-down on idle
- Persistent disk option
- Custom health checks

**Monitoring:**
```bash
# Check Render service metrics
# Dashboard: https://dashboard.render.com/
# Look for: memory usage %, restart count, response times
```

**Upgrade steps:**
1. Render Dashboard > rateshift-api > Settings > Instance Type
2. Switch from Free to Starter
3. Verify health endpoint responds: `curl https://api.rateshift.app/health`

**Rollback:**
- Switch back to Free tier in Render Dashboard
- Service will start spinning down after 15 min idle again

---

## Wave 2 Impact Assessment

### New data volume (estimated monthly)
- Gas rates: ~16 states x daily = ~480 rows/mo
- Community solar: ~15 programs, updated monthly = ~15 rows/mo
- Data quality metrics: read-only queries, no new storage
- Total new storage: < 1 MiB/mo additional

### Recommendation
- **Neon**: Stay on Free for now. Wave 2 adds minimal storage. Monitor at 400 MiB.
- **Render**: Stay on Free for now. If cron jobs fail due to cold starts, upgrade.
- **Review at**: Wave 3 (heating oil + propane) or when storage hits 400 MiB

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-11 | Stay Free for Wave 2 | New data volume < 1 MiB/mo, well within limits |
| — | Upgrade Neon at 400 MiB | Provides buffer before 512 MiB hard limit |
| — | Upgrade Render on OOM | Only if memory pressure observed |
