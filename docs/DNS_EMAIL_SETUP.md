# DNS & Email Setup — rateshift.app

> **STATUS (2026-03-10):** Domain `rateshift.app` purchased via Cloudflare Registrar.
> Currently using Gmail SMTP fallback with `RateShift <autodailynewsletterintake@gmail.com>`.
> Follow this guide to configure DNS, email, and SSL.

> Purpose: Configure DNS for frontend/backend, set up Resend custom domain email,
> and provision SSL -- all in one actionable checklist.
>
> Last updated: 2026-03-10

---

## Pre-Purchase Checklist

- [x] Budget approved for `.app` domain (~$14-20/year via Cloudflare Registrar)
- [x] Cloudflare account created
- [x] `rateshift.app` purchased (2026-03-10)
- [ ] Access to Resend dashboard (https://resend.com/domains) — add domain, copy DKIM records
- [ ] Access to Render + Vercel env var settings — update EMAIL_FROM_ADDRESS after domain verified

---

## Step 0.5 — Configure Cloudflare DNS (Frontend + Backend)

After the domain is active in Cloudflare, add these DNS records to route traffic to Render (backend) and Vercel (frontend).

### Frontend (Vercel)

| Type  | Name | Value                          | Proxy | TTL  |
|-------|------|--------------------------------|-------|------|
| CNAME | `@`  | `cname.vercel-dns.com`         | DNS only (gray cloud) | Auto |
| CNAME | `www` | `cname.vercel-dns.com`        | DNS only (gray cloud) | Auto |

Then in Vercel dashboard: **Settings > Domains** -- add `rateshift.app` and `www.rateshift.app`. Vercel will auto-provision SSL.

> **Note**: Vercel requires DNS-only mode (gray cloud) for their SSL provisioning to work. Do NOT enable Cloudflare proxy (orange cloud) for Vercel domains.

### Backend (Render)

| Type  | Name  | Value                                    | Proxy | TTL  |
|-------|-------|------------------------------------------|-------|------|
| CNAME | `api` | `electricity-optimizer.onrender.com`     | DNS only (gray cloud) | Auto |

Then in Render dashboard: **Settings > Custom Domains** -- add `api.rateshift.app`. Render will auto-provision SSL.

### Verification

```bash
dig rateshift.app CNAME +short
dig www.rateshift.app CNAME +short
dig api.rateshift.app CNAME +short
```

---

## Step 1 — SSL Certificates

SSL is handled automatically:

- **Cloudflare**: Free Universal SSL for any proxied records (if you later enable orange cloud)
- **Vercel**: Auto-provisions Let's Encrypt certs for custom domains
- **Render**: Auto-provisions Let's Encrypt certs for custom domains
- **`.app` TLD**: HSTS-preloaded by Google -- browsers will ONLY connect via HTTPS (no action needed)

No manual certificate configuration is required.

---

## Step 2 — Add the Domain in Resend

1. Go to https://resend.com/domains
2. Click **Add Domain** and enter `rateshift.app`
3. Resend will display three DKIM CNAME records unique to your account.
   Copy those values before leaving the page — you need them for Step 3.

---

## Step 3 — DNS Records for Email (Cloudflare DNS Panel)

Add all records below in Cloudflare DNS management for `rateshift.app`.

### SPF — authorize Resend's sending servers

| Type | Name | Value                            | TTL  |
|------|------|----------------------------------|------|
| TXT  | `@`  | `v=spf1 include:_spf.resend.com ~all` | Auto |

If an SPF record already exists for the root domain, **do not create a second
one** — merge the include into the existing record:

```
v=spf1 include:_spf.resend.com [existing includes] ~all
```

---

### DKIM — cryptographic signing (values from Resend dashboard)

Resend provides three CNAME records. The names follow the pattern
`resend._domainkey.<selector>.rateshift.app` but the exact selector
strings come from your Resend dashboard (Step 1).

| Type  | Host / Name                         | Value (from Resend dashboard)      | TTL  |
|-------|-------------------------------------|------------------------------------|------|
| CNAME | `resend._domainkey` (or full name)  | `<dkim-value-1>.dkim.resend.com`   | 3600 |
| CNAME | `<selector2>._domainkey`            | `<dkim-value-2>.dkim.resend.com`   | 3600 |
| CNAME | `<selector3>._domainkey`            | `<dkim-value-3>.dkim.resend.com`   | 3600 |

> The Resend dashboard shows the exact host and value strings to copy — do not
> guess these values.

---

### Return-Path / Bounce Domain

Resend handles bounces through its own subdomain by default. If the Resend
dashboard shows a custom bounce domain record (some accounts require it), add:

| Type  | Host / Name              | Value                                   | TTL  |
|-------|--------------------------|-----------------------------------------|------|
| CNAME | `bounces.rateshift.app` | `feedback-smtp.us-east-1.amazonses.com` | 3600 |

Check the Resend dashboard — this record is only required if Resend explicitly
lists it for your account.

---

### DMARC — policy and aggregate reporting

DMARC tells receiving mail servers what to do with messages that fail SPF/DKIM.

| Type | Name     | Value                                                                           | TTL  |
|------|----------|---------------------------------------------------------------------------------|------|
| TXT  | `_dmarc` | `v=DMARC1; p=quarantine; rua=mailto:dmarc@rateshift.app`            | Auto |

Policy progression (tighten over time):
1. `p=none` — monitor, no action
2. `p=quarantine` — suspicious mail goes to spam (recommended starting point)
3. `p=reject` — unauthenticated mail is refused (after 2-4 weeks of clean reports)

---

## Step 4 — Verify Domain in Resend

After all records are published:

1. Return to https://resend.com/domains
2. Click **Verify** next to `rateshift.app`
3. Resend checks SPF and DKIM automatically — all three DKIM CNAMEs must
   resolve correctly before the domain status changes to **Verified**.

---

## Step 5 — Propagation Checks

DNS propagation can take a few minutes to 48 hours. Use these commands to
confirm each record is live.

```bash
# SPF
dig rateshift.app TXT +short

# DKIM (replace <selector> with the value from Resend dashboard)
dig <selector>._domainkey.rateshift.app CNAME +short

# DMARC
dig _dmarc.rateshift.app TXT +short

# MX (not strictly required for sending, but good to verify no conflicts)
dig rateshift.app MX +short
```

You can also use https://mxtoolbox.com/SuperTool.aspx for a web-based check.

---

## Step 6 — Update Environment Variables

Once the domain is verified in Resend, update `EMAIL_FROM_ADDRESS` on **both** Render and Vercel to use the new domain:

### Render (Backend)

1. Go to Render dashboard > `srv-d649uhur433s73d557cg` > Environment
2. Update: `EMAIL_FROM_ADDRESS=RateShift <noreply@rateshift.app>`
3. Redeploy the service

### Vercel (Frontend)

1. Go to Vercel dashboard > Settings > Environment Variables
2. Update: `EMAIL_FROM_ADDRESS=RateShift <noreply@rateshift.app>`
3. Redeploy (or push a commit to trigger)

### Other env vars to verify

```
RESEND_API_KEY=re_xxxxxxxxxxxx          # from https://resend.com/api-keys (unchanged)
NEXT_PUBLIC_APP_URL=https://rateshift.app   # if used anywhere
BACKEND_URL=https://api.rateshift.app       # if migrating from .onrender.com
```

### Implementation Notes:

- `RESEND_API_KEY` is used by the backend (FastAPI) when sending emails via `resend.emails.send()`
- `RESEND_API_KEY` is also used by the frontend (Next.js) in `lib/email/send.ts` for email verification, magic links, and password reset
- `EMAIL_FROM_ADDRESS` is used by the frontend (Next.js) in `lib/email/send.ts` (defaults to the domain email if not set)
- The `EMAIL_FROM_ADDRESS` value must use the verified domain -- using an unverified domain will cause Resend to reject send requests
- **CRITICAL**: `RESEND_API_KEY` must be non-empty in both Render and Vercel environment variables. If empty or missing:
  - Email verification will fail silently (no error, but emails won't be sent)
  - Magic links will fail
  - Password reset will fail
  - After setting the variable, verify with `vercel env pull` (frontend) and Render dashboard (backend)
- Store both secrets in 1Password ("Electricity Optimizer" vault) and set them as environment variables in Vercel and Render

See `/frontend/.env.example` for reference, and `/backend/config/settings.py` for backend email configuration.

---

## Step 7 — Update Deploy Workflow URLs (if applicable)

If migrating the backend from `electricity-optimizer.onrender.com` to `api.rateshift.app`:

1. Update `BACKEND_URL` in Vercel env vars
2. Update `secrets.BACKEND_URL` in GitHub Actions repository secrets
3. Update any hardcoded URLs in `.github/workflows/deploy-production.yml`
4. Verify all GHA cron workflows still reach the backend (check `/internal/health-data`)

---

## Code Status (as of 2026-03-10)

The codebase has been updated to use `noreply@rateshift.app` as the default sender.

### What was changed

| File | Change |
|------|--------|
| `frontend/lib/email/send.ts` | Default `FROM_ADDRESS` changed from `autodailynewsletterintake@gmail.com` to `noreply@rateshift.app` |
| `backend/config/settings.py` | `email_from_address` default changed from `onboarding@resend.dev` to `noreply@rateshift.app` |
| `backend/config/settings.py` | `email_from_name` default changed from `Electricity Optimizer` to `RateShift` |
| `backend/templates/emails/welcome_beta.html` | Brand name + all URLs updated to rateshift.app |
| `backend/templates/emails/price_alert.html` | Dashboard link + footer updated to rateshift.app |
| `backend/templates/emails/dunning_soft.html` | Footer brand name updated to RateShift |
| `backend/templates/emails/dunning_final.html` | Footer brand name updated to RateShift |

### How the fallback chain works

1. If `RESEND_API_KEY` is set and Resend is reachable: sends via Resend using `EMAIL_FROM_ADDRESS` (must be a verified domain on your Resend account)
2. If Resend fails: falls back to SMTP using `EMAIL_FROM_ADDRESS` (any value works — Gmail SMTP does not enforce domain matching)
3. If neither is configured: throws an error

### Sender address matrix

| State | Sender shown to recipients |
|-------|---------------------------|
| `EMAIL_FROM_ADDRESS` env var set | Whatever value is in the env var |
| Env var not set, Resend path | `RateShift <noreply@rateshift.app>` (code default) |
| Env var not set, SMTP path | `RateShift <noreply@rateshift.app>` (code default) — Gmail SMTP rewrites display name but keeps the address |

> **IMPORTANT**: The Resend path will reject sends from `noreply@rateshift.app` until the domain is verified in the Resend dashboard (Steps 2-4 above). Until then, keep `EMAIL_FROM_ADDRESS=RateShift <autodailynewsletterintake@gmail.com>` in your environment, or use SMTP-only mode.

---

## Gmail SMTP Fallback (No Domain Required)

While the Resend custom domain setup above is the ideal long-term solution, Gmail SMTP works as an immediate fallback that requires no domain purchase or DNS configuration.

### How It Works

The backend email service (`backend/services/email_service.py`) uses Resend as the primary provider and falls back to Gmail SMTP when Resend is unavailable or fails. Gmail SMTP sends email directly from a Gmail address.

### Configuration

| Setting | Value |
|---------|-------|
| SMTP Host | `smtp.gmail.com` |
| SMTP Port | `587` (STARTTLS) |
| Authentication | Gmail App Password (NOT the regular Gmail password) |
| Daily Send Limit | 500 emails/day (Google free tier) |

### Prerequisites

1. **2FA must be enabled** on the Google account used for sending
2. Generate an **App Password** at https://myaccount.google.com/apppasswords
   - Select "Mail" as the app and your device type
   - Google generates a 16-character password
3. Use that App Password as `SMTP_PASSWORD` (not the account password)

### Environment Variables

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-gmail@gmail.com
SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx    # App Password from Google
# Use the Gmail address until rateshift.app is verified in Resend:
EMAIL_FROM_ADDRESS=RateShift <autodailynewsletterintake@gmail.com>
```

These are set on Render backend (34 env vars total) alongside the Resend variables. The email service tries Resend first, then falls back to SMTP.

### Limitations

- 500 emails/day sending limit (sufficient for early-stage)
- Emails come from a `@gmail.com` address (less professional than a custom domain)
- Google may flag high-volume sending or require CAPTCHA verification
- Not suitable for production scale -- migrate to Resend with a verified custom domain once a domain is purchased

---

## Summary Checklist

### Domain & DNS
- [x] `rateshift.app` purchased via Cloudflare Registrar (2026-03-10)
- [ ] Cloudflare DNS: CNAME `@` and `www` pointing to `cname.vercel-dns.com`
- [ ] Cloudflare DNS: CNAME `api` pointing to `electricity-optimizer.onrender.com`
- [ ] Vercel custom domain added (`rateshift.app` + `www`)
- [ ] Render custom domain added (`api.rateshift.app`)
- [ ] SSL certificates auto-provisioned (Vercel + Render)

### Email (Resend)
- [ ] Domain added in Resend dashboard (https://resend.com/domains)
- [ ] SPF TXT record: `v=spf1 include:_spf.resend.com ~all`
- [ ] All three DKIM CNAME records added (values from Resend dashboard)
- [ ] DMARC TXT record: `v=DMARC1; p=quarantine; rua=mailto:dmarc@rateshift.app`
- [ ] Return-path CNAME added if required by Resend for your account
- [ ] Resend domain status shows **Verified**

### Environment Variables
- [ ] `EMAIL_FROM_ADDRESS` updated to `RateShift <noreply@rateshift.app>` on Render
- [ ] `EMAIL_FROM_ADDRESS` updated to `RateShift <noreply@rateshift.app>` on Vercel
- [ ] `RESEND_API_KEY` verified non-empty in both Render and Vercel
- [ ] `BACKEND_URL` updated if migrating to `api.rateshift.app`
- [ ] `secrets.BACKEND_URL` updated in GitHub Actions if applicable
- [ ] Both services redeployed after env var changes

### Verification
- [ ] `dig rateshift.app CNAME +short` resolves correctly
- [ ] `dig api.rateshift.app CNAME +short` resolves correctly
- [ ] `dig rateshift.app TXT +short` shows SPF record
- [ ] `dig _dmarc.rateshift.app TXT +short` shows DMARC record
- [ ] Test email sent and received successfully via Resend
