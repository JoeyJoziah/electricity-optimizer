# DNS Email Setup — electricity-optimizer.app

> Purpose: Configure DNS records so Resend can send transactional email from
> `noreply@electricity-optimizer.app` (email verification, magic links).
>
> Last updated: 2026-03-04

---

## Current DNS State

Run these commands to check what is already published before making any changes.

```bash
dig electricity-optimizer.app MX
dig electricity-optimizer.app TXT
dig _dmarc.electricity-optimizer.app TXT
```

At time of writing no MX, SPF, DKIM, or DMARC records were confirmed — add all
four record groups below.

---

## Step 1 — Add the Domain in Resend

1. Go to https://resend.com/domains
2. Click **Add Domain** and enter `electricity-optimizer.app`
3. Resend will display three DKIM CNAME records unique to your account.
   Copy those values before leaving the page — you need them for Step 2.

---

## Step 2 — DNS Records to Add at Your Registrar

Add all records below in your DNS provider's control panel
(Cloudflare, Namecheap, Google Domains, etc.).

### SPF — authorize Resend's sending servers

Resend routes through Amazon SES infrastructure.

| Type | Host / Name           | Value                            | TTL  |
|------|-----------------------|----------------------------------|------|
| TXT  | `electricity-optimizer.app` (or `@`) | `v=spf1 include:amazonses.com ~all` | 3600 |

If an SPF record already exists for the root domain, **do not create a second
one** — merge the include into the existing record:

```
v=spf1 include:amazonses.com [existing includes] ~all
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
Start with `p=none` (monitor only) and tighten after confirming delivery works.

| Type | Host / Name                          | Value                                                                      | TTL  |
|------|--------------------------------------|----------------------------------------------------------------------------|------|
| TXT  | `_dmarc.electricity-optimizer.app`   | `v=DMARC1; p=none; rua=mailto:dmarc@electricity-optimizer.app`             | 3600 |

Policy progression once verified:
1. `p=none` — monitor, no action (start here)
2. `p=quarantine` — suspicious mail goes to spam
3. `p=reject` — unauthenticated mail is refused

---

## Step 3 — Verify Domain in Resend

After all records are published:

1. Return to https://resend.com/domains
2. Click **Verify** next to `electricity-optimizer.app`
3. Resend checks SPF and DKIM automatically — all three DKIM CNAMEs must
   resolve correctly before the domain status changes to **Verified**.

---

## Step 4 — Propagation Checks

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

## Environment Variables

Once the domain is verified, set these in your deployment environment
(1Password vault: "Electricity Optimizer"):

```
RESEND_API_KEY=re_xxxxxxxxxxxx          # from https://resend.com/api-keys
EMAIL_FROM_ADDRESS=Electricity Optimizer <noreply@electricity-optimizer.app>
```

The `EMAIL_FROM_ADDRESS` value must use the verified domain. Using an
unverified domain will cause Resend to reject all send requests.

See `frontend/.env.example` for the full environment variable reference.

---

## Summary Checklist

- [ ] Domain added in Resend dashboard (https://resend.com/domains)
- [ ] SPF TXT record added at root domain
- [ ] All three DKIM CNAME records added (values from Resend dashboard)
- [ ] Return-path CNAME added if required by Resend for your account
- [ ] DMARC TXT record added at `_dmarc` subdomain
- [ ] Resend domain status shows **Verified**
- [ ] `RESEND_API_KEY` set in production environment (Render + local `.env.local`)
- [ ] `EMAIL_FROM_ADDRESS` set to `Electricity Optimizer <noreply@electricity-optimizer.app>`
- [ ] Test email sent and received successfully
