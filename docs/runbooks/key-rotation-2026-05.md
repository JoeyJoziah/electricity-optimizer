# Key Rotation Runbook — 2026-05

**Date**: 2026-05-12 (draft)
**Execution window**: 2026-05-14 → 2026-05-20 (≥13-day soak before Jun 2 launch)
**Owner**: Devin
**Status**: Draft — pending execution
**PRD ref**: `.loki/prds/ph-relaunch-jun2-2026.md` Scope #3 (P0-6)

## Goal

Rotate every long-lived secret that has been in service >90 days, harden
the Render firewall, and verify the new credentials are working before the
PH launch window opens.

## Sequencing constraint

This runbook MUST complete BEFORE Scope #4 (CF_ORIGIN_SECRET activation).
Two concurrent secrets-management changes in a single soak window doubles the
blast radius if one fails. Order:

1. Rotate keys per this runbook (this week)
2. Verify all systems green for ≥48h
3. Activate `CF_ORIGIN_SECRET` end-to-end (`wrangler secret put` + Render env)

## Secrets to rotate

| Secret | Owner | Where used | Rotation method |
|--------|-------|------------|------------------|
| `DATABASE_URL` | Neon | backend, scripts | New role with same grants; swap; revoke old after 24h |
| `INTERNAL_API_KEY` | self-issued | GHA workflows, CF Worker, BE | `openssl rand -hex 32`; rotate in 1Password; redeploy callers |
| `STRIPE_WEBHOOK_SECRET` | Stripe | webhook handler | Stripe dashboard → Rotate; update Render env |
| `RESEND_API_KEY` | Resend | drip + transactional | Resend dashboard → new key; update Render env |
| `ONESIGNAL_REST_API_KEY` | OneSignal | push notifications | Dashboard regenerate |
| `OAUTH_STATE_SECRET` | self-issued | Better Auth | `openssl rand -hex 32` |
| `ML_MODEL_SIGNING_KEY` | self-issued | ML pipeline | `openssl rand -hex 32` |
| `RATE_LIMIT_BYPASS_KEY` | self-issued | CF Worker | `openssl rand -hex 32`; `wrangler secret put` |
| `DRIP_UNSUBSCRIBE_SECRET` | self-issued | unsubscribe HMAC | `openssl rand -hex 32` — coordinated with #5 templates |

## Firewall hardening

After rotation, lock the Render origin to Cloudflare IPs ONLY (P0-6 partial):

- **In scope now**: Cloudflare egress IP allowlist on Render firewall.
- **Out of scope** (deferred to P1-7): full custom-domain CF-IP lockdown.

Source for CF IPs: https://www.cloudflare.com/ips-v4/ (refresh on rotation).

## Per-secret procedure (template)

1. Generate new value (method per table).
2. Stage in 1Password vault under `RateShift / Production / <secret-name>-v2`.
3. Update Render env var (or CF Worker secret).
4. Trigger deploy / wrangler publish.
5. Smoke test: hit endpoint that exercises the secret.
6. Wait 60s; check Sentry for spike in 401/403/500.
7. If green: archive old value in 1Password (do NOT delete for 24h).
8. If red: redeploy with old value, debug, restart.

## Rollback

Each secret has a corresponding `-v1` (current) entry in 1Password kept
read-only for 24h post-rotation. Rollback = redeploy with `-v1` value.

The DR runbook (`docs/DISASTER_RECOVERY.md` §Key Rotation) lists the
end-to-end rollback for catastrophic failure: revert all 9 secrets in
reverse order, redeploy each system, then re-verify.

## Verification checklist

- [ ] All 9 secrets generated & staged in 1Password
- [ ] Each rotated one-at-a-time with 5-min soak between
- [ ] No Sentry 401/403/500 spike >2× baseline during window
- [ ] Cloudflare IP allowlist applied to Render
- [ ] `/health` 200 OK from CF Worker post-rotation
- [ ] One full GHA `build-and-push-backend.yml` cycle succeeds
- [ ] One internal `cost-cap-alerts.yml` cron succeeds (validates `INTERNAL_API_KEY`)
- [ ] Stripe test webhook fires & verifies signature
- [ ] Resend transactional send completes
- [ ] OneSignal push test delivers
- [ ] `wrangler secret list` matches expected names
- [ ] 24h post-rotation: old values purged from 1Password

## Acceptance

Complete when all 11 verification checkboxes are ticked AND no rollback was
required during the 13-day soak window (2026-05-20 → 2026-06-02).
