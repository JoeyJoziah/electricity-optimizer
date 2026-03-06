# DNS & Email Setup — electricity-optimizer.app

> **STATUS (2026-03-06):** Domain `electricity-optimizer.app` has NOT been purchased yet (NXDOMAIN).
> Currently using Gmail SMTP fallback with `Electricity Optimizer <autodailynewsletterintake@gmail.com>`.
> This delivers to any recipient via Gmail SMTP (500/day free). Follow this guide end-to-end once ready to purchase.

> Purpose: Purchase domain, configure DNS for frontend/backend, set up Resend custom domain email,
> and provision SSL -- all in one actionable checklist.
>
> Last updated: 2026-03-06

---

## Pre-Purchase Checklist

- [ ] Budget approved for `.app` domain (~$14-20/year via Cloudflare Registrar)
- [ ] Cloudflare account created (free plan is sufficient)
- [ ] Access to Resend dashboard (https://resend.com/domains)
- [ ] Access to Render + Vercel env var settings

---

## Step 0 — Purchase the Domain

1. Go to [Cloudflare Registrar](https://dash.cloudflare.com/?to=/:account/domains/register) (recommended -- at-cost pricing, integrated DNS)
2. Search for `electricity-optimizer.app`
3. Complete purchase (`.app` domains enforce HTTPS by default via HSTS preload)
4. Domain will be automatically added to your Cloudflare account with DNS management

> **Alternative registrars**: Namecheap, Google Domains, Porkbun. If using a non-Cloudflare registrar, add the domain to Cloudflare afterward and update nameservers to Cloudflare's (for free DNS + CDN + SSL).

---

## Step 0.5 — Configure Cloudflare DNS (Frontend + Backend)

After the domain is active in Cloudflare, add these DNS records to route traffic to Render (backend) and Vercel (frontend).

### Frontend (Vercel)

| Type  | Name | Value                          | Proxy | TTL  |
|-------|------|--------------------------------|-------|------|
| CNAME | `@`  | `cname.vercel-dns.com`         | DNS only (gray cloud) | Auto |
| CNAME | `www` | `cname.vercel-dns.com`        | DNS only (gray cloud) | Auto |

Then in Vercel dashboard: **Settings > Domains** -- add `electricity-optimizer.app` and `www.electricity-optimizer.app`. Vercel will auto-provision SSL.

> **Note**: Vercel requires DNS-only mode (gray cloud) for their SSL provisioning to work. Do NOT enable Cloudflare proxy (orange cloud) for Vercel domains.

### Backend (Render)

| Type  | Name  | Value                                    | Proxy | TTL  |
|-------|-------|------------------------------------------|-------|------|
| CNAME | `api` | `electricity-optimizer.onrender.com`     | DNS only (gray cloud) | Auto |

Then in Render dashboard: **Settings > Custom Domains** -- add `api.electricity-optimizer.app`. Render will auto-provision SSL.

### Verification

```bash
dig electricity-optimizer.app CNAME +short
dig www.electricity-optimizer.app CNAME +short
dig api.electricity-optimizer.app CNAME +short
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
2. Click **Add Domain** and enter `electricity-optimizer.app`
3. Resend will display three DKIM CNAME records unique to your account.
   Copy those values before leaving the page — you need them for Step 3.

---

## Step 3 — DNS Records for Email (Cloudflare DNS Panel)

Add all records below in Cloudflare DNS management for `electricity-optimizer.app`.

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
`resend._domainkey.<selector>.electricity-optimizer.app` but the exact selector
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
| CNAME | `bounces.electricity-optimizer.app` | `feedback-smtp.us-east-1.amazonses.com` | 3600 |

Check the Resend dashboard — this record is only required if Resend explicitly
lists it for your account.

---

### DMARC — policy and aggregate reporting

DMARC tells receiving mail servers what to do with messages that fail SPF/DKIM.

| Type | Name     | Value                                                                           | TTL  |
|------|----------|---------------------------------------------------------------------------------|------|
| TXT  | `_dmarc` | `v=DMARC1; p=quarantine; rua=mailto:dmarc@electricity-optimizer.app`            | Auto |

Policy progression (tighten over time):
1. `p=none` — monitor, no action
2. `p=quarantine` — suspicious mail goes to spam (recommended starting point)
3. `p=reject` — unauthenticated mail is refused (after 2-4 weeks of clean reports)

---

## Step 4 — Verify Domain in Resend

After all records are published:

1. Return to https://resend.com/domains
2. Click **Verify** next to `electricity-optimizer.app`
3. Resend checks SPF and DKIM automatically — all three DKIM CNAMEs must
   resolve correctly before the domain status changes to **Verified**.

---

## Step 5 — Propagation Checks

DNS propagation can take a few minutes to 48 hours. Use these commands to
confirm each record is live.

```bash
# SPF
dig electricity-optimizer.app TXT +short

# DKIM (replace <selector> with the value from Resend dashboard)
dig <selector>._domainkey.electricity-optimizer.app CNAME +short

# DMARC
dig _dmarc.electricity-optimizer.app TXT +short

# MX (not strictly required for sending, but good to verify no conflicts)
dig electricity-optimizer.app MX +short
```

You can also use https://mxtoolbox.com/SuperTool.aspx for a web-based check.

---

## Step 6 — Update Environment Variables

Once the domain is verified in Resend, update `EMAIL_FROM_ADDRESS` on **both** Render and Vercel to use the new domain:

### Render (Backend)

1. Go to Render dashboard > `srv-d649uhur433s73d557cg` > Environment
2. Update: `EMAIL_FROM_ADDRESS=Electricity Optimizer <noreply@electricity-optimizer.app>`
3. Redeploy the service

### Vercel (Frontend)

1. Go to Vercel dashboard > Settings > Environment Variables
2. Update: `EMAIL_FROM_ADDRESS=Electricity Optimizer <noreply@electricity-optimizer.app>`
3. Redeploy (or push a commit to trigger)

### Other env vars to verify

```
RESEND_API_KEY=re_xxxxxxxxxxxx          # from https://resend.com/api-keys (unchanged)
NEXT_PUBLIC_APP_URL=https://electricity-optimizer.app   # if used anywhere
BACKEND_URL=https://api.electricity-optimizer.app       # if migrating from .onrender.com
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

If migrating the backend from `electricity-optimizer.onrender.com` to `api.electricity-optimizer.app`:

1. Update `BACKEND_URL` in Vercel env vars
2. Update `secrets.BACKEND_URL` in GitHub Actions repository secrets
3. Update any hardcoded URLs in `.github/workflows/deploy-production.yml`
4. Verify all GHA cron workflows still reach the backend (check `/internal/health-data`)

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
EMAIL_FROM_ADDRESS=Electricity Optimizer <your-gmail@gmail.com>
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
- [ ] `electricity-optimizer.app` purchased via Cloudflare Registrar
- [ ] Cloudflare DNS: CNAME `@` and `www` pointing to `cname.vercel-dns.com`
- [ ] Cloudflare DNS: CNAME `api` pointing to `electricity-optimizer.onrender.com`
- [ ] Vercel custom domain added (`electricity-optimizer.app` + `www`)
- [ ] Render custom domain added (`api.electricity-optimizer.app`)
- [ ] SSL certificates auto-provisioned (Vercel + Render)

### Email (Resend)
- [ ] Domain added in Resend dashboard (https://resend.com/domains)
- [ ] SPF TXT record: `v=spf1 include:_spf.resend.com ~all`
- [ ] All three DKIM CNAME records added (values from Resend dashboard)
- [ ] DMARC TXT record: `v=DMARC1; p=quarantine; rua=mailto:dmarc@electricity-optimizer.app`
- [ ] Return-path CNAME added if required by Resend for your account
- [ ] Resend domain status shows **Verified**

### Environment Variables
- [ ] `EMAIL_FROM_ADDRESS` updated to `Electricity Optimizer <noreply@electricity-optimizer.app>` on Render
- [ ] `EMAIL_FROM_ADDRESS` updated to `Electricity Optimizer <noreply@electricity-optimizer.app>` on Vercel
- [ ] `RESEND_API_KEY` verified non-empty in both Render and Vercel
- [ ] `BACKEND_URL` updated if migrating to `api.electricity-optimizer.app`
- [ ] `secrets.BACKEND_URL` updated in GitHub Actions if applicable
- [ ] Both services redeployed after env var changes

### Verification
- [ ] `dig electricity-optimizer.app CNAME +short` resolves correctly
- [ ] `dig api.electricity-optimizer.app CNAME +short` resolves correctly
- [ ] `dig electricity-optimizer.app TXT +short` shows SPF record
- [ ] `dig _dmarc.electricity-optimizer.app TXT +short` shows DMARC record
- [ ] Test email sent and received successfully via Resend
