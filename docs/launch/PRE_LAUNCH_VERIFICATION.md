# Pre-Launch Verification Checklist

**Target launch**: Tue Jun 2, 2026 12:01am PT (Product Hunt)
**Dress rehearsal**: Tue May 26, 2026
**Document re-baselined**: 2026-05-12

> ℹ️ Structural test results carried forward from April 8, 2026 verification run (still valid). Manual checklist updated for June 2 launch. Supersedes the April 14, 2026 version.

---

## 1. Page Load Times (April 8 baseline — re-run before May 26 rehearsal)

| Page | Load Time | TTFB | HTTP | Status |
|------|-----------|------|------|--------|
| Landing (`/`) | 0.284s | 0.223s | 200 | PASS |
| Pricing (`/pricing`) | 0.284s | — | 200 | PASS |
| Signup (`/auth/signup`) | 0.331s | — | 200 | PASS |
| API Gateway | 0.221s | — | — | PASS |

**Target**: < 2s. **Baseline result**: All pages under 350ms. PASS.
**Action**: Re-run this section during May 26 dress rehearsal and record fresh numbers below.

| Page | Load Time | TTFB | HTTP | Status (May 26) |
|------|-----------|------|------|---------|
| Landing (`/`) | — | — | — | PENDING |
| Pricing (`/pricing`) | — | — | — | PENDING |
| Signup (`/auth/signup`) | — | — | — | PENDING |
| API Gateway | — | — | — | PENDING |

---

## 2. Security Headers

| Header | Value | Status |
|--------|-------|--------|
| `strict-transport-security` | max-age=63072000; includeSubDomains; preload | PASS |
| `x-frame-options` | DENY | PASS |
| `x-content-type-options` | nosniff | PASS |
| `content-security-policy` | Full CSP with nonce + strict-dynamic | PASS |
| `permissions-policy` | camera=(), microphone=(), geolocation=() | PASS |
| `referrer-policy` | strict-origin-when-cross-origin | PASS |

---

## 3. SSL / HTTPS

- Protocol: HTTP/2
- HSTS: Active with preload
- Certificate: Valid (Cloudflare)
- **Status**: PASS

---

## 4. API / CF Worker

| Check | Result | Status |
|-------|--------|--------|
| CF-Ray header present | `9e9527fac8ed6ccf-IAD` (April 8) | PASS |
| Rate limiting active | `x-ratelimit-limit: 120` | PASS |
| Rate limit remaining | 99/120 | PASS |
| Origin server | uvicorn (Render) | PASS |
| `/health` bypass (HEAD probe) | Not cached — bypassed at CF Worker | PASS (2026-05-11) |
| HEAD/GET cache collision fix | `storeInCache` gated to `GET` only | PASS (2026-05-11) |
| Origin timeout | `AbortSignal.timeout(25s)` + client signal | PASS (2026-05-11) |

---

## 5. Mobile Responsiveness

- Viewport meta tag: `width=device-width, initial-scale=1` — PASS
- Mobile landing page tested at 390x844 (iPhone) — PASS
- Hero text, CTAs, and nav all visible — PASS
- No horizontal overflow observed — PASS

---

## 6. Console Errors

| Page | Errors | Source | Severity |
|------|--------|--------|----------|
| Landing | 1 | Microsoft Clarity (`clarity.ms`) | LOW — third-party tracking script |
| Dashboard | 1 | Microsoft Clarity (`clarity.ms`) | LOW — third-party tracking script |

**App errors**: 0
**Status**: PASS (no app-level errors)

---

## 7. Infrastructure Pre-Checks (PRD Scope items — by Jun 2 go/no-go)

### 7.1 Backend Auto-Deploy Pipeline (Scope #10)
- [ ] **Soak: ≥3 additional green deploys** since 2026-05-11 pipeline creation
- [ ] **1 rollback drill completed** — pull previous image SHA, deploy, verify `/health` 200, re-deploy current
- [ ] `build-and-push-backend.yml` last run visible at: `https://github.com/dmpcg/electricity-optimizer/actions/workflows/build-and-push-backend.yml`

### 7.2 CF Worker Cache Soak (Scope #11)
- [ ] **Telemetry check at 2026-05-19**: cache hit rate, 504/499 error rates, KV cost trend stable
- [ ] `/internal/gateway-stats` endpoint returns healthy counters after 7 days

### 7.3 Key Rotation (Scope #3) — **Complete by 2026-05-20**
- [ ] `UNSUBSCRIBE_SECRET` set to `openssl rand -hex 32` value **FIRST** (CAN-SPAM protection)
- [ ] `INTERNAL_API_KEY` rotated
- [ ] `ML_MODEL_SIGNING_KEY` rotated
- [ ] `OAUTH_STATE_SECRET` rotated
- [ ] 13-day soak verified (rotation ≤ May 20 → launch Jun 2)
- [ ] Post-rotation validation: `curl -H "X-API-Key: $NEW_KEY" https://api.rateshift.app/api/v1/internal/drip/status` returns 200

### 7.4 Origin Shared Secret Activation (Scope #4) — **After Scope #3 completes**
- [ ] `openssl rand -hex 32` → new secret
- [ ] `wrangler secret put ORIGIN_SECRET` (CF Worker side)
- [ ] `CF_ORIGIN_SECRET` set in Render env vars (same value)
- [ ] Verify: direct `curl https://api.rateshift.app/api/v1/health` returns 200 (CF adds header)
- [ ] Verify: direct `curl -H "X-CF-Origin-Secret: wrong" https://electricity-optimizer.onrender.com/health` returns 403

### 7.5 Render Starter Upgrade (Scope #2) — **Complete by 2026-05-16**
- [ ] Upgraded to Render Starter plan
- [ ] Cold-start time < 2s verified (or Standard pre-committed if > 2s)

### 7.6 Load Test (Scope #8) — **Complete by 2026-05-22**
- [ ] k6 test run: `k6 run --env BASE_URL=https://api.rateshift.app loadtest/rateshift-staging.js`
- [ ] 300 RPS for 5 minutes against staging
- [ ] p95 latency recorded as baseline (column: p95_ms)
- [ ] 0 5xx errors during sustained load
- [ ] Neon connection count stayed under 60 during peak (97% headroom confirmed from Scope #9 audit)

---

## 8. Compliance Checks

### 8.1 CAN-SPAM (Scope #13) — ✅ COMPLETE
- [x] `user_drip_state.unsubscribed_at` column added (migration 068)
- [x] `GET /api/v1/public/unsubscribe` endpoint with HMAC-SHA256 token
- [x] `UNSUBSCRIBE_SECRET` env var added (decoupled from `INTERNAL_API_KEY`)
- [x] All 4 drip templates: physical address (PO Box 12345, Hartford CT 06101) + Unsubscribe link
- [x] Batch queries filter `AND unsubscribed_at IS NULL`
- [x] `/unsubscribed` confirmation page at `rateshift.app/unsubscribed`

### 8.2 Legal Pages (Scope #13 compliance) — ✅ COMPLETE
- [x] Terms of Service updated: UtilityAPI §6, NREL/EIA data sources, API key section, pricing ($4.99/$14.99)
- [x] Privacy Policy updated: GDPR §4, automated decision-making §6, 730-day retention
- [x] Legal contact: `legal@rateshift.app` in ToS
- [x] Privacy contact: `support@rateshift.app` in Privacy Policy

### 8.3 Waitlist Status (Scope #6) — ✅ AUDITED
- [x] `beta_signups` table exists in Neon (0 rows — no frontend form posts to it)
- [x] Domain warm-up skipped (threshold ≥200 not met)
- [x] Waitlist blast removed from launch sequence
- [x] Slip-comms plan updated to remove waitlist branch

---

## 9. Drip Email System (Scope #5) — ✅ COMPLETE

| Check | Status |
|-------|--------|
| Welcome email fires within 60s of signup | ✅ Better Auth `databaseHooks.user.create` → `enroll_user_drip` → Resend |
| Day-2 template selection by connection state (snapshot-time) | ✅ SQL query evaluates state at batch-pick time |
| Day-7 upgrade nudge | ✅ Template B (no discount code at launch) |
| Unsubscribe token signing via `effective_unsubscribe_secret` | ✅ Fallback to `INTERNAL_API_KEY` if `UNSUBSCRIBE_SECRET` unset |
| Sentry error-rate alerting >2% dispatch errors | ✅ `api/v1/internal/drip.py` |
| GHA cron uses `X-API-Key` (not `X-Internal-API-Key`) | ✅ Fixed 2026-05-12 |
| Better Auth enrollment hook uses `X-API-Key` | ✅ Fixed 2026-05-12 |

Manual verification before dress rehearsal:
- [ ] Send test signup → confirm welcome email arrives in inbox within 90s
- [ ] Verify Resend delivery log shows `delivered` (not `bounced`)
- [ ] Unsubscribe link in email resolves to `rateshift.app/unsubscribed` (not 404)

---

## 10. Monitoring / Observability

| Check | Status |
|-------|--------|
| UptimeRobot status page live | ✅ `stats.uptimerobot.com/d4sbPJ124X` — 4 monitors UP |
| Visual regression baselines committed | ✅ 12 chromium-linux baselines at `frontend/e2e/visual-regression.spec.ts-snapshots/` |
| Cost-cap alerts GHA cron active | ✅ `cost-cap-alerts.yml` 09:00 UTC daily → Slack #metrics |
| Slack channels configured | ✅ #incidents, #deployments, #metrics |
| Abort thresholds documented | ✅ `docs/LAUNCH_DAY_RUNBOOK.md` Appendix C |
| Slip-comms template ready | ✅ `docs/LAUNCH_DAY_RUNBOOK.md` Appendix D |

---

## 11. Pre-Rehearsal Checklist (By May 25)

- [ ] Scopes #2 (Render upgrade), #3 (key rotation), #4 (origin secret), #8 (load test) all **COMPLETE**
- [ ] Social handles @rateshift claimed on X, Bluesky, LinkedIn (Scope #1) — or copy sweep of `@rateshiftapp` fallback done
- [ ] 6 gallery screenshots refreshed (Scope #12) — post-audit sprint UI changes
- [ ] Activation target locked: Floor 25% / Stretch 40% (confirmed 2026-05-19 per PRD)
- [ ] `PRE_LAUNCH_VERIFICATION.md` page-load section re-run (§1 above, PENDING columns)
- [ ] One test signup end-to-end (free account → connect utility → see savings number)

---

## 12. Launch-Day Go/No-Go Gate (May 26 rehearsal verdict)

| Criterion | Required | Status |
|-----------|----------|--------|
| All Scope #1–#18 items complete OR explicitly waived | Yes | PENDING |
| Backend pipeline soak: ≥3 deploys + 1 rollback | Yes | PENDING |
| Load test p95 baseline captured | Yes | PENDING |
| Origin secret activated | Yes | PENDING |
| Key rotation ≥13-day soak | Yes | PENDING |
| Welcome email E2E verified | Yes | PENDING |
| Dress rehearsal verdict | Must PASS | PENDING |

**If any Required criterion is PENDING on Jun 2 morning**: do not submit to PH. Trigger slip-comms template (Appendix D of LAUNCH_DAY_RUNBOOK.md).

---

## Summary

| Category | Apr 8 Result | Jun 2 Status |
|----------|-------------|--------------|
| Page load < 2s | **PASS** (all < 350ms) | Re-run May 26 |
| Security headers | **PASS** (full suite) | Stable (no changes) |
| SSL/HTTPS | **PASS** (HTTP/2 + HSTS) | Stable |
| API gateway | **PASS** + cache fixes 2026-05-11 | Re-verify after origin-secret |
| Mobile responsive | **PASS** | Stable |
| Console errors | **PASS** (0 app errors) | Re-check after audit sprint UI changes |
| CAN-SPAM compliance | N/A | **COMPLETE** (2026-05-12) |
| Legal pages | N/A | **COMPLETE** (2026-05-12) |
| Drip email system | N/A | **COMPLETE** (2026-05-12) |
| Infra scopes (#2,#3,#4,#8) | N/A | PENDING — due by May 22 |
| Dress rehearsal | N/A | May 26 |
