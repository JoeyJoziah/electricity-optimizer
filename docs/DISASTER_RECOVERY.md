# RateShift Disaster Recovery Runbook

> **PURPOSE**: Executable recovery procedures for 6 critical failure scenarios ranked by likelihood.
>
> **LAST UPDATED**: 2026-04-27
> **STATUS**: Production-ready
> **OWNER**: Devin McGrath (devmcgrath@gmail.com)
> **SLACK**: `#incidents` in `electricityoptimizer.slack.com`

---

## Table of Contents

1. [Render Origin Down or Stuck](#1-render-origin-down-or-stuck)
2. [Cloudflare Worker Outage or Misconfig](#2-cloudflare-worker-outage-or-misconfig)
3. [Neon Database Corruption or Schema Change](#3-neon-database-corruption-or-schema-change)
4. [Stripe State Out-of-Sync](#4-stripe-state-out-of-sync)
5. [ML Pipeline Staleness or Training Failure](#5-ml-pipeline-staleness-or-training-failure)
6. [Email Delivery Failure](#6-email-delivery-failure)

---

## 1. Render Origin Down or Stuck

**Likelihood**: HIGH (free tier sleep, deploy hangs, OOM crashes)

### Symptoms
- All API calls return 502/503 Bad Gateway
- CF Worker `gateway-stats` endpoint returns `degraded: true`
- User reports "app is broken"
- Render dashboard shows service unhealthy or inactive (gray status icon)

### Detection: Where to Look First

1. **Cloudflare Worker logs** (immediate):
   ```bash
   wrangler tail --project-name rateshift-api-gateway --format json | head -20
   ```
   Look for: `origin_fetch_error`, `upstream_error`, status 502/503.

2. **gateway-health.yml run logs**:
   - GitHub Actions → Workflows → `gateway-health.yml` → latest run
   - Check `gateway-stats` response for `degraded` flag and error messages

3. **Render dashboard**:
   - Go to https://dashboard.render.com
   - Service: `srv-d649uhur433s73d557cg` (api.rateshift.app)
   - Check "Overview" tab: status (Active/Inactive), last deploy time, CPU/RAM usage
   - If Inactive, it likely slept due to inactivity (free tier)

4. **Slack #incidents**:
   - Search for recent alerts mentioning "502" or "origin"

### Mitigation (≤5 minutes)

**Option A: Trigger Render Redeploy via Dashboard (fastest)**
1. Log into https://dashboard.render.com
2. Select service `srv-d649uhur433s73d557cg`
3. Click **Logs** tab → scroll to top → confirm last deploy time
4. Click **Manual Deploy** button → select branch `main`
5. Confirm redeploy. Render will start the backend in ~30–60 seconds.
6. Check Slack #deployments for auto-notification (Rube `rcp_9f8mVE2Z_DSP` fires every hour)

**Option B: Trigger via RENDER_DEPLOY_HOOK (scriptable, fast — pulls current `:latest` from Docker Hub)**
```bash
curl -X POST https://api.render.com/deploy/srv-d649uhur433s73d557cg \
  -H "Authorization: Bearer ${RENDER_DEPLOY_HOOK}" \
  -H "Content-Type: application/json" \
  -d '{"ref":"main"}'
```
(RENDER_DEPLOY_HOOK stored in 1Password "RateShift" vault under "Render Deploy Hook")

> ⚠️ This only redeploys whatever `dmpcg/electricity-optimizer-backend:latest` is currently on Docker Hub. If the incident requires a code fix to ship, use Option C to force an image rebuild first.

**Option C: Force fresh image build + push + deploy (when a code fix must ship)**
```bash
gh workflow run build-and-push-backend.yml --ref main --repo JoeyJoziah/electricity-optimizer
```
This is the same pipeline that runs automatically on every `backend/**` merge to `main` (added 2026-05-11). It rebuilds the Docker image, pushes `:latest` to Docker Hub, then hits the Render deploy hook. ~5–8 minutes end-to-end.

**If persisting after redeploy**:
1. Check Render system status: https://status.render.com
2. If Render infrastructure is down, use mitigation for scenario #2 (DNS bypass)

### Recovery (full restoration)

1. **Wait 2–5 minutes** for redeploy to complete (Render cold start on free tier ~10 min worst case)
2. Monitor logs during startup:
   ```bash
   wrangler tail --project-name rateshift-api-gateway --format json | grep -i "error\|origin_ok"
   ```
3. Once startup complete, Render will emit "Build successful" to #deployments
4. CF Worker will automatically mark `degraded: false` on next cron run (max 10 min, via keep-alive trigger)

### Validation

- **CF Worker health endpoint**:
  ```bash
  curl https://api.rateshift.app/health
  # Expected: 200 OK, JSON: {"status":"ok","degraded":false}
  ```

- **Smoke test key endpoints**:
  ```bash
  curl https://api.rateshift.app/api/v1/prices/current?region=CAISO_NORTH
  # Expected: 200 OK, JSON price data
  
  curl https://api.rateshift.app/api/v1/health
  # Expected: 200 OK
  ```

- **Frontend**: https://rateshift.app loads without 502 errors in browser console

### Post-Incident

1. **Log**: In `docs/incidents/YYYY-MM-DD-render-recovery.md`, record:
   - Time detected, time mitigated, root cause (sleep? OOM? deploy hung?)
   - Render logs/metrics snapshot
   - Duration of user impact
2. **Notify**: Post summary to Slack #incidents (use template from `incident-response.md`)
3. **Action item**: If free tier sleep is cause, flag for Render upgrade to Starter ($7/mo, no sleep)

---

## 2. Cloudflare Worker Outage or Misconfig

**Likelihood**: MEDIUM (deploy broke routing, KV down, bindings unavailable)

### Symptoms
- All requests to `api.rateshift.app/*` return 524 (timeout) or 530 (internal error)
- Wrangler tail shows `Error: Uncaught SyntaxError` or `ReferenceError` in worker code
- Cloudflare dashboard reports "Deployment Failed"
- Frontend falls back to direct Render origin (circuit breaker: only public endpoints like `/prices/current`)

### Detection: Where to Look First

1. **Wrangler live tail**:
   ```bash
   wrangler tail --project-name rateshift-api-gateway --format pretty
   ```
   Look for: `Error:`, `SyntaxError`, `ReferenceError`, red exception traces.

2. **Cloudflare Workers dashboard**:
   - Go to https://dash.cloudflare.com
   - Account: `b41be0d03c76c0b2cc91efccdb7a10df`
   - Workers & Pages → rateshift-api-gateway
   - Recent Deployments tab: check latest deploy status (green = OK, red = failed)
   - Deployment details: error logs from edge

3. **GitHub Actions**:
   - Workflows → `deploy-worker.yml` → latest run
   - Check "Deploy Worker" step for build/upload errors

### Mitigation (≤5 minutes)

**Option A: Rollback to Previous Deployment (safest & fastest)**
```bash
wrangler rollback --project-name rateshift-api-gateway --message "Emergency rollback from DR scenario"
```
Wrangler will show list of recent deployments; select the previous stable one and confirm.

**Option B: Emergency DNS Bypass (if rollback fails)**
If wrangler is unavailable or broken, temporarily bypass the CF Worker:

1. Go to Cloudflare DNS console: https://dash.cloudflare.com/ac03dd28616da6d1c4b894c298c1da58/dns
   - Zone: rateshift.app
2. Find DNS record `api.rateshift.app` (currently CNAME → CF Worker)
3. **Temporarily** change CNAME target from CF Worker to Render origin:
   - Update to: `rateshift-api-gateway.onrender.com` (Render service domain)
   - Wait for DNS propagation (usually <1 min for CF-managed zone)
   - **Critical**: Comment in DNS record: "EMERGENCY BYPASS — revert after CF Worker fix"

4. **Afterward, rotate INTERNAL_API_KEY**:
   - The bypass exposes the Render origin directly; internal auth is now visible
   - Update `INTERNAL_API_KEY` in Render env vars (via dashboard)
   - Update CF Worker secrets: `wrangler secret put INTERNAL_API_KEY`
   - Revert DNS to CF Worker CNAME once CF Worker is fixed

### Recovery (full restoration)

1. **If rollback was used**:
   - Monitor `wrangler tail` to confirm the old deployment is stable
   - Once stable, file a bug for what broke in the latest deploy (see `incident-response.md` PIR template)
   - Fix the bug, test locally with `wrangler dev`, and redeploy when ready

2. **If DNS bypass was used**:
   - Fix the CF Worker issue (usually: syntax error in code, missing binding, invalid KV key)
   - Test locally: `wrangler dev`
   - Redeploy: `npm run deploy` (from `workers/api-gateway/`)
   - Monitor `wrangler tail` to confirm new deploy is healthy
   - Revert DNS CNAME back to CF Worker
   - Rotate INTERNAL_API_KEY (see step 4 above)

### Validation

- **CF health endpoint** (via CF Worker):
  ```bash
  curl https://api.rateshift.app/health
  # Expected: 200 OK, {"status":"ok"}, no timeouts
  ```

- **Wrangler tail** shows clean logs (no errors in last 5 min):
  ```bash
  wrangler tail --project-name rateshift-api-gateway --format json | tail -20
  ```

- **Frontend**: https://rateshift.app responsive, no 524/530 errors in browser console

### Post-Incident

1. **Log**: `docs/incidents/YYYY-MM-DD-worker-recovery.md`
   - What broke (code bug? binding? KV?)
   - Was rollback or DNS bypass used?
   - Time to mitigation and full recovery
2. **Review**: The failing deploy (look at `git log` or GitHub Actions logs)
   - Did it pass local tests? If not, add test that would catch this
   - Should it have failed CI? Update `deploy-worker.yml` checks
3. **Action item**: Add pre-deploy validation (e.g., `wrangler build` in CI before deploy)

---

## 3. Neon Database Corruption or Schema Change

**Likelihood**: MEDIUM (accidental migration, data corruption, backup needed)

### Symptoms
- API responses return 5xx with `OperationalError` or `IntegrityError` in logs
- Sentry alerts spike for `psycopg2.OperationalError` or `sqlalchemy.exc.IntegrityError`
- Specific table queries fail (e.g., "relation does not exist")
- Neon console shows write errors or query slowness (100%+ CPU)

### Detection: Where to Look First

1. **Sentry dashboard**:
   - https://sentry.io/organizations/rateshift/
   - Look for `OperationalError`, `IntegrityError`, or `ProgrammingError` with high rate
   - Click alert to see stack trace (which table/query failed)

2. **Neon console**:
   - https://console.neon.tech/projects/cold-rice-23455092
   - Select branch "main" (production)
   - Operations tab: check for failed queries or schema changes
   - Monitoring tab: check CPU, storage, connections

3. **Render backend logs**:
   ```bash
   # Via Render dashboard:
   # Logs tab → filter by "error" or "ERROR"
   ```

4. **Slack #incidents**: Search for "database" or "schema"

### Mitigation (≤5 minutes)

**STOP ALL WRITES IMMEDIATELY**:
1. Put site in maintenance mode (optional but safer):
   - Frontend: set feature flag `MAINTENANCE_MODE=true` (not currently implemented; skip if missing)
   - CF Worker: add temporary route matcher for 503 response (optional)

2. **Get the affected schema details**:
   ```bash
   # From Neon console, check recent operations:
   # Operations → Recent queries → identify what changed
   ```

3. **Decide: Point-in-Time Restore (PITR) vs Fix in Place**
   - **If recent data corruption** (last few minutes): PITR is safest
   - **If just schema mismatch** (migration didn't run): fix migrations and redeploy
   - **If data is intact but one column bad**: fix data manually (SQL)

### Recovery (full restoration)

**Path A: Point-in-Time Restore (if corruption recent)**

1. Go to Neon console:
   - Project: cold-rice-23455092 → Branches
   - Current branch: "main"
   - Click **Restore** → Choose restore point (max 7 days back on free tier)
   - Neon will create a temporary branch with your chosen point-in-time state

2. Test the restored branch:
   ```bash
   # Temporarily switch backend to restored branch connection string
   # (Neon shows connection string in branch details)
   # Run smoke test:
   curl https://api.rateshift.app/api/v1/health
   ```

3. Once validated:
   - Neon merges restored branch back to "main" (or you manually restore)
   - Monitor backend logs to confirm recovery

**Path B: Migration Rollback (if schema is the issue)**

1. Identify the failing migration:
   ```bash
   # From Neon console, find the last applied migration number
   # Example: schema shows table "X" but code expects "Y"
   ```

2. Create a reverse migration:
   ```bash
   # In backend repo:
   cd backend
   
   # Create new migration file (backward):
   .venv/bin/alembic revision -m "rollback_from_NNNN" --rev-id 999_reverse
   
   # Edit backend/migrations/versions/999_reverse.py
   # Copy SQL from the breaking migration and reverse it (DROP vs CREATE, etc.)
   ```

3. Apply the reverse migration:
   ```bash
   .venv/bin/alembic downgrade -1  # or -2 if multiple migrations broke
   ```

4. Verify:
   ```bash
   .venv/bin/python -m pytest backend/tests/ -k "smoke" -v
   ```

**Path C: Data Repair (if schema is OK but data is corrupted)**

1. Identify the corrupt column/table from Sentry alert
2. Query to find bad rows:
   ```sql
   SELECT id, column_name FROM table_name WHERE column_name IS NULL AND should_not_be; -- example
   ```

3. Repair (carefully!):
   ```sql
   UPDATE table_name SET column_name = default_value WHERE corrupt_condition;
   ```

4. Verify repair:
   ```bash
   .venv/bin/python -m pytest backend/tests/ -k "smoke"
   ```

### Validation

- **Smoke tests pass**:
  ```bash
  cd /Users/devinmcgrath/projects/electricity-optimizer
  .venv/bin/python -m pytest backend/tests/ -k "smoke" -v
  # Expected: all pass, no SQL errors
  ```

- **API endpoints healthy**:
  ```bash
  curl https://api.rateshift.app/api/v1/health
  curl https://api.rateshift.app/api/v1/prices/current?region=CAISO_NORTH
  # Expected: 200 OK, no 5xx errors
  ```

- **Sentry error rate drops**:
  - Sentry dashboard: errors timeline should show clear downward spike

### Post-Incident

1. **Log**: `docs/incidents/YYYY-MM-DD-db-recovery.md`
   - Root cause: corruption? migration? operator error?
   - PITR time point used (if applicable)
   - Data loss (if any) and scope
2. **Stripe billing rebuild** (if needed):
   - Idempotency table `stripe_processed_events` prevents duplicate webhook effects
   - Use Stripe dashboard Webhooks → Resend events for the affected time window
3. **Action item**: Implement pre-migration validation (schema diff check in CI)

---

## 4. Stripe State Out-of-Sync

**Likelihood**: MEDIUM (webhook delivery failed, tier mismatch, missing subscription items)

### Symptoms
- User reports "I paid but I'm still on Free tier"
- Stripe shows subscription active but `users.subscription_tier` is 'free'
- `OperationError` in logs mentioning stripe_customer_id lookups
- Chargeback or dispute filed; billing ops alert missing

### Detection: Where to Look First

1. **Check specific user via Stripe dashboard**:
   - Go to https://dashboard.stripe.com/customers
   - Search by email (user reports issue email)
   - Check "Subscriptions" tab: status (active/canceled), plan (Pro/Business), next billing date

2. **Check user record in backend**:
   ```bash
   # SSH into Render or query Neon directly:
   psql postgresql://...@ep-withered-morning.us-east-1.neon.tech/energyoptimize
   
   SELECT id, email, subscription_tier, stripe_customer_id FROM users WHERE email = 'user@example.com';
   # Compare tier with Stripe dashboard
   ```

3. **Check webhook delivery logs**:
   - Stripe dashboard → Developers → Webhooks
   - Select endpoint for `https://api.rateshift.app/billing/webhook`
   - Recent webhook deliveries: filter for `invoice.payment_succeeded`, `customer.subscription.updated`
   - Look for failed deliveries (red status) in the window when user says they paid

4. **Sentry alerts**: Search for `payment_` or `stripe_customer_id` errors

### Mitigation (≤5 minutes)

**Confirm the discrepancy**:
1. Get user's `stripe_customer_id` from Stripe dashboard (see step 1 above)
2. Query backend:
   ```bash
   SELECT subscription_tier FROM users WHERE stripe_customer_id = 'cus_XXXXX';
   ```
3. Compare with Stripe subscription status

**DO NOT manually UPDATE users table unless you verify Stripe subscription is valid** (see Recovery).

### Recovery (full restoration)

**Path A: Replay Missed Webhooks (idempotency-safe)**

1. Open Stripe dashboard → Developers → Webhooks → select rateshift.app endpoint
2. In the **Events** tab, find the event that should have updated the user:
   - Usually `invoice.payment_succeeded` or `customer.subscription.updated`
   - Look for events in the window when user says they paid (±2 hours)

3. Click the event → **Resend** button
   - Stripe will redeliver the webhook to `https://api.rateshift.app/billing/webhook`
   - Idempotency table `stripe_processed_events` prevents duplicate effects

4. Verify user record updated:
   ```bash
   SELECT subscription_tier FROM users WHERE stripe_customer_id = 'cus_XXXXX';
   # Should now show 'pro' or 'business'
   ```

**Path B: Manual Override (only after Stripe verification)**

1. **Verify Stripe subscription is truly active** (repeat step 1 under Detection):
   - Stripe dashboard shows subscription.status = "active"
   - Next billing date is in the future
   - No payment issues

2. **Only then**, update user record:
   ```sql
   UPDATE users 
   SET subscription_tier = 'pro' 
   WHERE email = 'user@example.com' 
   AND stripe_customer_id = 'cus_XXXXX';
   ```

3. Verify update took effect:
   ```bash
   SELECT subscription_tier FROM users WHERE email = 'user@example.com';
   # Should now show 'pro'
   ```

**Path C: Reconcile All Users (script, if widespread)**

If the issue affects multiple users, run a reconciliation script:
```bash
# Create backend/scripts/reconcile_stripe.py (if missing):
cat > backend/scripts/reconcile_stripe.py <<'EOF'
"""Reconcile user subscription tiers with Stripe."""
import stripe
from backend.models import User
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

stripe.api_key = os.getenv("STRIPE_API_KEY")
engine = create_engine(os.getenv("DATABASE_URL"))

with Session(engine) as session:
    # Fetch all users with stripe_customer_id
    users = session.query(User).filter(User.stripe_customer_id.isnot(None)).all()
    
    for user in users:
        cust = stripe.Customer.retrieve(user.stripe_customer_id)
        subs = cust.get("subscriptions", {}).data
        
        if not subs:
            expected_tier = "free"
        else:
            sub = subs[0]  # Assume 1 active subscription
            expected_tier = "pro" if "pro" in sub.items.data[0].plan.id else "business"
        
        if user.subscription_tier != expected_tier:
            print(f"MISMATCH: {user.email} - db={user.subscription_tier}, stripe={expected_tier}")
            user.subscription_tier = expected_tier
            session.add(user)
    
    session.commit()
    print("Reconciliation complete")
EOF

# Run the script:
.venv/bin/python backend/scripts/reconcile_stripe.py
```

### Validation

- **User can access paid features**:
  - Frontend: user logs in, no "upgrade required" banner
  - API: `GET /api/v1/prices/forecast` returns 200 (not 402 Forbidden for free tier)

- **Stripe and DB agree**:
  ```sql
  SELECT email, subscription_tier FROM users WHERE stripe_customer_id = 'cus_XXXXX';
  # Cross-check with Stripe dashboard
  ```

- **No error spikes in Sentry** for stripe operations

### Post-Incident

1. **Log**: `docs/incidents/YYYY-MM-DD-stripe-recovery.md`
   - Number of users affected
   - Root cause (webhook delivery? deploy?)
   - Manual overrides applied (if any)
2. **Review Stripe webhook delivery logs**:
   - Did delivery fail? Why? (network? endpoint error? timeout?)
   - Stripe status page (https://status.stripe.com): was there an outage during the failure window?
3. **Action item**: Set up Stripe webhook delivery alerting (e.g., Sentry catch on repeated 5xx from webhook endpoint)

---

## 5. ML Pipeline Staleness or Training Failure

**Likelihood**: LOW-MEDIUM (nightly retraining fails, forecasts wildly off)

### Symptoms
- Nightly `model-retrain.yml` GHA workflow shows red (failed)
- Self-healing monitor (`self-healing-monitor.yml`) fires alert for `model-retrain.yml` failure
- User reports price forecasts are "completely off" vs realized prices
- Forecast accuracy (MAPE) spikes in logs or Sentry alerts

### Detection: Where to Look First

1. **Self-healing monitor**:
   - Slack #incidents: search for "model-retrain" or "workflow failed"
   - Or manually check GitHub Actions → `self-healing-monitor.yml` → latest run

2. **GitHub Actions workflow**:
   - Workflows → `model-retrain.yml` → latest run
   - Check logs: look for `Error:`, `AssertionError`, OOM, or missing data

3. **Forecast accuracy metrics**:
   - Sentry: search for `forecast_accuracy`, `MAPE`, or `prediction_error`
   - Backend logs: filter for `ml.update_weights` or `ml.compute_accuracy` spans

4. **Model artifact availability**:
   - GitHub Actions → `model-retrain.yml` → Artifacts section
   - Check if artifact was uploaded (even if workflow failed)

### Mitigation (≤5 minutes)

**Option A: Freeze Forecasts (feature flag)**
If forecasts are dangerously inaccurate, disable them immediately:

1. Set environment variable in Render:
   ```bash
   # Via Render dashboard: environment variables section
   ENABLE_FORECASTS=false
   ```

2. Frontend will show message: "Forecasts temporarily unavailable" on `/forecast` page (if implemented)
3. API endpoint `GET /api/v1/prices/forecast` returns 503 (or 200 with flag: `available: false`)

**Option B: Rollback Model (quick recovery)**

1. Go to GitHub Actions → `model-retrain.yml` → **Artifacts** section
2. List of recent artifacts: find the **second-most-recent** successful run
3. Download that artifact (usually `model.pkl` or directory `ml/models/current/`)

4. Manually push to ML service:
   ```bash
   # If model is stored in S3/GCS or Neon blob:
   # Copy the artifact back to the model store
   
   # If model is in the repo (ml/models/current/):
   cp model.pkl ml/models/current/model.pkl
   git add ml/models/current/
   git commit -m "rollback: restore previous ML model (DR scenario)"
   git push origin main
   ```

5. Render will auto-redeploy the backend (if configured for auto-deploy on push)
6. Monitor logs:
   ```bash
   # Render logs: filter for "model_load" or "ml"
   ```

### Recovery (full restoration)

1. **Investigate the training failure** (while forecasts are disabled/rolled back):
   ```bash
   # Check the failed workflow logs for root cause:
   # - Missing data: EIA API rate limit? Data quality issue?
   # - OOM: model too large? Increase Render RAM (upgrade from free tier)
   # - Dependency: missing package in requirements.txt?
   ```

2. **Run training locally** (to reproduce and fix):
   ```bash
   cd /Users/devinmcgrath/projects/electricity-optimizer
   .venv/bin/python ml/train.py --debug --save-model
   
   # If successful: commit and push to trigger GHA
   # If fails: debug locally, fix, then push
   ```

3. **Re-enable forecasts**:
   ```bash
   # Render environment variables:
   ENABLE_FORECASTS=true
   ```

4. **Verify accuracy**:
   - Run test suite:
     ```bash
     .venv/bin/python -m pytest ml/ -k "predictor" -v
     ```
   - Check Sentry: forecast_accuracy MAPE should return to baseline

### Validation

- **Smoke test passes**:
  ```bash
  .venv/bin/python -m pytest ml/ -k "predictor" -v
  # Expected: all pass, no NaN or Inf predictions
  ```

- **Forecast endpoint responds**:
  ```bash
  curl 'https://api.rateshift.app/api/v1/prices/forecast?region=CAISO_NORTH'
  # Expected: 200 OK, array of forecast objects with reasonable values
  ```

- **Latest model-retrain.yml workflow runs green**:
  - Force a manual run (GitHub UI button) or wait for next cron (usually nightly)
  - Verify: workflow completes successfully, artifact uploaded

### Post-Incident

1. **Log**: `docs/incidents/YYYY-MM-DD-ml-recovery.md`
   - Root cause (API rate limit? data quality? dependency?)
   - How long forecasts were disabled
   - Model rollback point used
2. **Add test**: If data quality was the issue, add a data validation step to `model-retrain.yml` that fails early
3. **Action item**: Consider upgrading Render to Starter tier if OOM is frequent (ML training needs more memory)

---

## 6. Email Delivery Failure

**Likelihood**: LOW (Resend domain issue, credentials rotated, account suspended)

### Symptoms
- Alert emails not received by users
- `resend_send_failed` or `email_delivery_error` counter spiking in Sentry
- Resend dashboard shows domain verification failure (DKIM/SPF/DMARC not configured)
- Resend API returns 401 (auth failed) or 422 (domain issue)

### Detection: Where to Look First

1. **Sentry alerts**:
   - Search for `resend`, `email_delivery`, or `smtp`
   - Check error rate and recent failures

2. **Resend dashboard**:
   - Go to https://resend.com
   - Emails tab: find your recent sent emails, check status (Success/Failed)
   - Domains tab: check `rateshift.app` domain status (verified? DKIM/SPF/DMARC green?)
   - API Keys tab: confirm API key is active (not revoked)

3. **Backend logs**:
   ```bash
   # Render logs: filter for "resend" or "email"
   # Look for: status codes, auth errors, domain errors
   ```

4. **Gmail SMTP fallback status**:
   - Check Render env vars: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` all set?
   - If Resend fails, backend should already fallback to Gmail SMTP (see code: `backend/services/email_service.py`)

### Mitigation (≤5 minutes)

**Option A: Test the Fallback (Gmail SMTP)**

1. Verify env vars in Render:
   - `SMTP_HOST=smtp.gmail.com`
   - `SMTP_PORT=587`
   - `SMTP_USER=<gmail-address>`
   - `SMTP_PASSWORD=<app-password>` (Gmail App Password, not account password)

2. If missing, add them via Render dashboard (Environment Variables section)

3. Force a test email send:
   ```bash
   # Trigger via API (if test endpoint exists):
   curl -X POST https://api.rateshift.app/internal/test-email \
     -H "X-Internal-Key: ${INTERNAL_API_KEY}" \
     -H "Content-Type: application/json" \
     -d '{"to":"devmcgrath@gmail.com","subject":"Test"}'
   
   # Or manually test the service:
   .venv/bin/python -c "
   from backend.services.email_service import EmailService
   service = EmailService()
   service.send('test@example.com', 'Test', 'Hello')
   "
   ```

4. Check if email arrives (check spam folder too)

**Option B: Check Resend Domain Configuration**

1. Go to https://resend.com → Domains → rateshift.app
2. Verify status: all green checkmarks for:
   - **DKIM**: Copy key to Cloudflare DNS (or provider)
   - **SPF**: TXT record `v=spf1 include:resend.com ~all`
   - **DMARC**: TXT record `v=DMARC1; p=none;`
3. If any are red: click **Edit** and follow Resend's instructions to update DNS

### Recovery (full restoration)

**Path A: Fix Resend Domain (if configuration issue)**

1. Get your domain credentials from Resend:
   - Resend dashboard → Domains → rateshift.app
   - Copy DKIM, SPF, DMARC records provided by Resend

2. Update DNS in Cloudflare:
   - Go to https://dash.cloudflare.com/ac03dd28616da6d1c4b894c298c1da58/dns
   - Zone: rateshift.app
   - Create/update TXT records:
     - DKIM: `default._domainkey.rateshift.app` → (Resend's DKIM string)
     - SPF: `rateshift.app` → `v=spf1 include:resend.com ~all`
     - DMARC: `_dmarc.rateshift.app` → `v=DMARC1; p=none;`

3. Wait for DNS propagation (usually <5 min on Cloudflare)
4. Return to Resend dashboard → Domains → rateshift.app → **Verify** button
5. Once verified, test sending an email (see step 3 under "Option A" above)

**Path B: Re-authenticate Resend (if API key issue)**

1. Check Resend API key in 1Password:
   - Vault: "RateShift"
   - Item: "Resend API Key"
   - Copy the key

2. Update Render env var:
   ```bash
   # Via Render dashboard: Environment Variables
   RESEND_API_KEY=re_XXXXX...
   ```

3. Verify by testing an email send (see step 3 under "Option A")

**Path C: Gmail SMTP as Permanent Fallback (if Resend still broken)**

1. Confirm Gmail SMTP credentials in Render:
   - `SMTP_HOST=smtp.gmail.com`
   - `SMTP_PORT=587`
   - `SMTP_USER=<gmail-address>`
   - `SMTP_PASSWORD=<app-password>`

2. If email still doesn't arrive:
   - Check Gmail account settings: 2FA enabled? App Password created? (search "Gmail app password")
   - Verify credentials locally (copy to `.env.local` and test)

3. Update email sender address (if needed):
   - Code: `backend/services/email_service.py` → sender = "RateShift <noreply@rateshift.app>"
   - For Gmail, if domain not verified, may need to use `devmcgrath@gmail.com` as From address instead

### Validation

- **Email sends via Resend successfully**:
  ```bash
  # Check Resend dashboard:
  # Emails tab → filter by date (today)
  # Status should show "Sent" for recent emails
  ```

- **Test email arrives**:
  - Send test email to yourself (devmcgrath@gmail.com)
  - Check inbox (and spam folder)

- **Domain verification green in Resend**:
  - Resend dashboard → Domains → rateshift.app
  - All checkmarks (DKIM, SPF, DMARC) green

- **Backend logs clean**:
  ```bash
  # Render logs: filter for "resend" or "email"
  # No 401 or 422 errors
  ```

### Post-Incident

1. **Log**: `docs/incidents/YYYY-MM-DD-email-recovery.md`
   - Root cause (domain? credentials? account suspension?)
   - Emails missed (rough count)
   - Whether Gmail SMTP fallback was used

2. **DNS record documentation**: Add comment to Cloudflare DNS records with last verified date:
   ```
   # Example TXT record comment (in Cloudflare):
   "Last verified: 2026-04-27 – Resend DKIM. See DISASTER_RECOVERY.md for renewal instructions."
   ```

3. **Action item**: Set up Sentry alerts for email delivery errors, and calendar reminder to verify Resend domain config monthly

---

## Quick Reference: Contacts & URLs

| Resource | Link | Contact |
|----------|------|---------|
| **Render Dashboard** | https://dashboard.render.com | Service: `srv-d649uhur433s73d557cg` |
| **Neon Console** | https://console.neon.tech | Project: `cold-rice-23455092` ("energyoptimize") |
| **Cloudflare Workers** | https://dash.cloudflare.com | Account: `b41be0d03c76c0b2cc91efccdb7a10df` |
| **Stripe Dashboard** | https://dashboard.stripe.com | Webhook: `https://api.rateshift.app/billing/webhook` |
| **Sentry** | https://sentry.io/organizations/rateshift/ | Alert: all services |
| **Resend** | https://resend.com | Domain: rateshift.app, ID: `20c95ef2-42f4-4040-be75-2026e97e35c9` |
| **Slack** | electricityoptimizer.slack.com | Channels: #incidents, #deployments, #metrics |
| **1Password** | https://1password.com | Vault: "RateShift" |
| **GitHub** | https://github.com/JoeyJoziah/electricity-optimizer | Workflows, deployments, code |
| **Owner** | devmcgrath@gmail.com | Devin McGrath (solo founder) |

---

## Appendix: Testing Disaster Recovery Procedures

To ensure these procedures work under pressure, run a quarterly DR test:

1. Pick one scenario (e.g., "Render origin down")
2. Simulate the failure (e.g., stop the Render service temporarily)
3. Follow the mitigation steps exactly as written
4. Document time taken and any friction points
5. Update procedures if anything was unclear or slow
6. Restore (undoing the simulation)
7. File a PR with updates to this runbook

**Last DR test**: [PLACEHOLDER — add date and notes from your test run]

---

## Appendix: Key Rotation Runbook (PRD Scope #3 — due 2026-05-20)

> **Prerequisite**: Scope #4 (CF Worker origin-secret header middleware) must be **deployed** before executing key rotation, but **not yet activated** (both CF and Render sides unset). Activate ORIGIN_SECRET as the final step below after all other secrets have soaked for 24h.
>
> **Soak rule**: ≥13 days between rotation completion and PH launch (2026-06-02). Rotation must complete by 2026-05-20.

### Secrets to Rotate

| Secret | Current location | Rotation method | Rollback method |
|--------|-----------------|-----------------|-----------------|
| `INTERNAL_API_KEY` | Render env + CF Worker secret + 1Password | Generate new; deploy Render first, then CF Worker | Restore old value from 1Password; redeploy both |
| `ML_MODEL_SIGNING_KEY` | Render env + 1Password | Generate new; deploy Render | Restore from 1Password |
| `OAUTH_STATE_SECRET` | Render env + 1Password | Generate new; deploy Render | Restore from 1Password; in-flight OAuth sessions will fail once (acceptable) |
| `CF_ORIGIN_SECRET` / `ORIGIN_SECRET` | Render env (not yet set) + CF Worker secret (not yet set) | Set both simultaneously (see activation step) | Remove both sides; middleware falls back to no-op |

> **Not rotating at this time**: Stripe keys (separate rotation cadence, requires Stripe dashboard), Neon connection string (requires coordinated migration), Resend API key (separate rotation, requires domain re-verification).

### Pre-rotation Checklist

- [ ] Confirm last green deploy on `build-and-push-backend.yml` within 24h (pipeline is trusted)
- [ ] Note current `INTERNAL_API_KEY` value in 1Password (Vault: "RateShift", item: "Render Env Vars") as rollback point
- [ ] Confirm UptimeRobot monitors are UP (all 4 green)
- [ ] Pin current git SHA: `git rev-parse HEAD` → record in this doc as `PRE_ROTATION_SHA`

**PRE_ROTATION_SHA**: `[fill in before execution]`

### Rotation Procedure

**Step 1 — Generate new secrets**

```bash
# Run locally; never commit output
NEW_INTERNAL_KEY=$(openssl rand -hex 32)
NEW_ML_SIGNING_KEY=$(openssl rand -hex 32)
NEW_OAUTH_STATE=$(openssl rand -hex 32)
NEW_ORIGIN_SECRET=$(openssl rand -hex 32)

echo "INTERNAL_API_KEY=$NEW_INTERNAL_KEY"
echo "ML_MODEL_SIGNING_KEY=$NEW_ML_SIGNING_KEY"
echo "OAUTH_STATE_SECRET=$NEW_OAUTH_STATE"
echo "CF_ORIGIN_SECRET=$NEW_ORIGIN_SECRET"
echo "ORIGIN_SECRET=$NEW_ORIGIN_SECRET  (same value for CF Worker)"
```

Save all four values in 1Password (Vault: "RateShift") as "Key Rotation 2026-05-20 (new)" before proceeding.

**Step 2 — Rotate INTERNAL_API_KEY**

1. Render Dashboard → `electricity-optimizer-backend` → Environment → update `INTERNAL_API_KEY` to `$NEW_INTERNAL_KEY` → Save (triggers redeploy)
2. Wait for redeploy green (≤5 min); confirm `/health` 200
3. `wrangler secret put INTERNAL_API_KEY` → paste `$NEW_INTERNAL_KEY`
4. Verify CF Worker still routes correctly: `curl -s https://api.rateshift.app/health | jq .`
5. Update 1Password item with new value

**Step 3 — Rotate ML_MODEL_SIGNING_KEY**

1. Render → update `ML_MODEL_SIGNING_KEY` → Save (triggers redeploy)
2. Wait for green; confirm `/health` 200
3. Update 1Password

**Step 4 — Rotate OAUTH_STATE_SECRET**

> ⚠️ In-flight OAuth sessions (Google/GitHub/Outlook) will fail once the old secret expires. Schedule during off-peak hours (e.g., 02:00–04:00 PT).

1. Render → update `OAUTH_STATE_SECRET` → Save (triggers redeploy)
2. Wait for green; test a full OAuth login flow (Google) to confirm new secret works
3. Update 1Password

**Step 5 — Activate ORIGIN_SECRET (Scope #4 activation)**

This is the final step — only execute after Steps 2–4 have soaked for ≥24h:

1. `wrangler secret put ORIGIN_SECRET` → paste `$NEW_ORIGIN_SECRET`
2. Render → add `CF_ORIGIN_SECRET` env var = `$NEW_ORIGIN_SECRET` → Save (triggers redeploy)
3. Wait for green; test: `curl -s https://api.rateshift.app/health | jq .` (should still return 200 — CF Worker injects the header automatically)
4. Test a direct Render URL (without CF Worker): should get 403 (origin-secret middleware rejecting direct access)
5. Update 1Password

### Post-rotation Validation

```bash
# 1. Backend health
curl -s https://api.rateshift.app/health

# 2. Internal API key works (drip enrollment dry run)
curl -X POST https://api.rateshift.app/api/v1/internal/drip/process \
  -H "X-Internal-API-Key: $NEW_INTERNAL_KEY" \
  -H "Content-Type: application/json" \
  -d '{}' | jq .summary

# 3. CF Worker passes origin secret (no 403 on CF-proxied request)
curl -s -o /dev/null -w "%{http_code}" https://api.rateshift.app/api/v1/health

# 4. Direct Render URL blocked (expects 403)
curl -s -o /dev/null -w "%{http_code}" https://electricity-optimizer.onrender.com/api/v1/health
# Expected: 403 (CF_ORIGIN_SECRET not present in direct request)
```

All checks must pass before soak window begins.

### Rollback Procedure

If any rotation step causes a production outage:

1. Revert the changed secret in Render (restore from 1Password "Key Rotation 2026-05-20 (old)" item) → Save → wait for redeploy green
2. If CF Worker secret was changed: `wrangler secret put <SECRET_NAME>` with old value
3. If ORIGIN_SECRET was activated and is causing 403s: remove `CF_ORIGIN_SECRET` from Render env; the middleware falls back to no-op
4. Verify `/health` 200 and run post-rotation validation checks above
5. Document the failure in this runbook under "Rotation Issues Log" before re-attempting

### Rotation Issues Log

| Date | Secret | Issue | Resolution |
|------|--------|-------|------------|
| *(none yet)* | — | — | — |
