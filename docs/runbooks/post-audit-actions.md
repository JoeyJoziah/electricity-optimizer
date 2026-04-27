# Post-Audit Action Runbook (User-Only Items)

> Source: 2026-04-27 comprehensive audit. Companion to `.audit-2026-04-27/CONSOLIDATED.md`.
> These four items can't be completed by an AI agent — they touch production
> secrets, billing tier upgrades, or third-party console config.
> Estimated total user time: **~45 minutes**. Estimated monthly spend: **~$32**.

---

## P0-6 — Pin Render origin to Cloudflare IPs + rotate INTERNAL_API_KEY

> **Why P0**: Without this, the CF Worker security layer (rate limit / bot
> detection / internal-auth) can be bypassed by a direct hit on the Render
> origin URL. The audit (security H-3) classed this as HIGH because the
> origin URL has likely leaked at least once via deployment logs or DNS history.

### Steps

1. **Render Firewall rule** (~5 min)
   - Render dashboard → service `rateshift-api` → Settings → Network
   - Add inbound rule: allow only Cloudflare IP ranges
     - Source: `https://www.cloudflare.com/ips-v4/` (CSV) and `https://www.cloudflare.com/ips-v6/`
     - As of 2026: 15 IPv4 ranges + 7 IPv6 ranges
     - Render currently does not auto-update CF IP lists; set a quarterly calendar reminder to refresh
   - Apply

2. **Rotate `INTERNAL_API_KEY`** (~10 min)
   - Generate: `python -c "import secrets; print(secrets.token_hex(32))"`
   - Store in 1Password under "RateShift / INTERNAL_API_KEY" (replace existing entry, add a date stamp to the previous version's note)
   - Update three places **in this order** (CF first, then Render, then verify):
     1. Cloudflare: `wrangler secret put INTERNAL_API_KEY --name rateshift-api-gateway` then paste the new value
     2. Render dashboard → service env vars → `INTERNAL_API_KEY` → set new value → trigger redeploy
     3. After Render deploy completes (~3-5 min), test:
        - `curl https://api.rateshift.app/api/v1/internal/check-alerts -H "X-Internal-API-Key: $NEW_KEY" -X POST` should return 200
        - Same call with the OLD key should now return 401

3. **Verify firewall is enforcing** (~5 min)
   - From a machine outside Cloudflare's IPs, try to hit the Render origin URL directly (find it in the Render dashboard). It should refuse the connection.
   - Inside Cloudflare (via `curl https://api.rateshift.app/health`), it should still work.

### Validation

- `wrangler tail` shows `internal_auth_check_passed` after the rotation
- `gateway-health.yml` GHA workflow passes (runs every 12h)
- No 401 spike in Sentry on `/api/v1/internal/*`

---

## P1-7 — Cloudflare Turnstile site setup

> **Why P1**: Frontend widget is shipped (see `frontend/components/auth/TurnstileWidget.tsx`). It renders nothing until the env var is set. Backend signup must validate the token to actually block bots.

### Steps

1. **Create the Turnstile site** (~3 min)
   - Cloudflare dashboard → Turnstile → Add site
   - Name: "RateShift Auth"
   - Domain: `rateshift.app`
   - Widget mode: **Managed** (recommended) — invisible by default, shows challenge on suspicion
   - Save
   - Copy: **Site key** (public, starts with `0x4`) and **Secret key** (server, starts with `0x4`)

2. **Set env vars** (~5 min)
   - **Vercel** (frontend): add `NEXT_PUBLIC_TURNSTILE_SITE_KEY` = the site key. Trigger redeploy.
   - **Render** (backend): add `TURNSTILE_SECRET_KEY` = the secret key. Trigger redeploy.
   - Store both in 1Password under "RateShift / Turnstile"

3. **Backend validator** (this part is also code — flag for next dev cycle)
   - `backend/auth/neon_auth.py` (or wherever signup lands) should check `request.headers.get("X-Turnstile-Token")` and POST it to `https://challenges.cloudflare.com/turnstile/v0/siteverify` with `secret={settings.turnstile_secret_key}` before creating the user. If `success: false`, return 400.
   - Until this is wired, the frontend gate is presentational only — the user can still bypass it with a direct API call. Track as a follow-up commit.

### Validation

- Sign up via the live form: Turnstile widget renders, the form submits, and the new account is created.
- Try to sign up via `curl` without the header: should fail (after backend validator is wired).

---

## P1-19 — Render Starter tier ($7/mo)

> **Why P1**: Free tier sleeps after 15 min idle (mitigated by 10-min keep-alive cron, but still flaky). Single instance, no HA, no zero-downtime deploy. Becomes a problem the first time traffic actually spikes.

### Steps

1. Render dashboard → service `rateshift-api` → Settings → Plan
2. Change to **Starter** ($7/mo, no annual discount available at this tier)
3. Confirm billing
4. Restart the service to take effect
5. Optional: set `web.numInstances: 2` once on Starter for zero-downtime deploys (additional $7/mo per extra instance)

### Validation

- `gateway-health.yml` shows `degraded=false` consistently
- 10-min keep-alive cron can be relaxed to 30-min or removed (Starter doesn't sleep)
- `services.healthCheckPath: /health` returns 200 within 30s of deploy

---

## P1-20 — GitHub Team or pay-as-you-go ($25/mo budget)

> **Why P1**: 35 GHA workflows are at the margin of the 2,000 free-minute monthly cap. One traffic spike of deploy-heavy days breaches it; CI silently stops running after that.

### Steps

**Option A: GitHub Team** ($4/user/mo, includes 3,000 min/mo per user)
- For solo founder: $4/mo + overages
- Best for predictable cost

**Option B: Pay-as-you-go** ($0.008/min after free tier)
- Estimated current burn: 1,560-2,120 min/mo → potential overage 0-120 min → $0-1/mo
- Spike risk: 5x consumption on busy weeks → $25/mo cap recommended

### Steps

1. GitHub.com → Billing & plans → Spending limit → set to $25/mo to cap blast radius
2. (Option A) Upgrade to Team via Billing → Plan → GitHub Team
3. Enable "Cost reports" notification at 50% / 75% / 90% of cap

### Validation

- After 7 days, GitHub Insights → Actions usage shows total min/mo
- No "workflow disabled due to billing" emails

---

## Action checklist

Run these in this order:

- [ ] **Day 1, 30 min**: P0-6 (firewall + key rotation). Most security value, lowest cost.
- [ ] **Day 1, 10 min**: P1-19 (Render Starter $7/mo). Stabilizes everything else.
- [ ] **Day 2, 5 min**: P1-20 (GHA $25 cap). Caps risk before next deploy spike.
- [ ] **Day 3, 15 min**: P1-7 (Turnstile site + env vars + backend validator). Frontend already shipped; just needs CF zone + env config + a small backend code follow-up.

**Total user time**: ~60 minutes spread over 3 days
**Total monthly spend after**: ~$32 (Render $7 + GitHub $25)

---

## What's already done in code (no action needed)

The 2026-04-27 audit completion sprint shipped:
- 7 P0 fixes (silent fallbacks, customer-id resolution, Decimal money, etc.)
- 14 P1 backend changes (auth, DI, drain, Composio gate, request cancellation, dispatch refactor)
- AutoSwitcherContent split (894 → 139 LOC)
- 94 new service tests + integration test scaffolding (skips without DATABASE_URL)
- 4 runbooks (this one + DR + Incident Response + Auto Rate Switcher kill-switch)
- ADR template + ADR-011 (silent-fallback ban)
- Turnstile frontend widget (this doc covers the CF zone bits)
- Worker observability stanza
- Doc drift fixes + auto-rate-switcher specs moved to `docs/specs/`
- Ruff target py312 + drop UP045 + remove vestigial black config

See `.audit-2026-04-27/CONSOLIDATED.md` for the full breakdown.
