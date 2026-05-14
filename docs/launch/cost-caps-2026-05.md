# Cost Caps — Launch Window

**Date**: 2026-05-12
**Status**: ✅ COMPLETE
**PRD ref**: `.loki/prds/ph-relaunch-jun2-2026.md` Scope #14

## Caps (monthly)

| Service | Cap | Proxy metric | Source |
|---------|-----|--------------|--------|
| Resend  | $20 | sends/day × $0.0008 | Resend dashboard API |
| Neon    | $30 | compute-seconds × tier rate | Neon dashboard API |
| CF Worker | $20 | requests + KV reads | CF Analytics |
| Render  | $7  | flat (Starter) | n/a — flat fee |

## Alerting

- **Endpoint**: `POST /api/v1/internal/cost-caps/check` evaluates all proxies.
- **Breach levels**:
  - `warning_low`  ≥ 50% of cap
  - `warning_high` ≥ 80%
  - `critical`     ≥ 100%
- **GHA cron**: `.github/workflows/cost-cap-alerts.yml` runs daily at 09:00 UTC.
- **Sink**: Slack `#metrics` with colour-coded blocks (green/yellow/red).
- **Tests**: 14 passing in `backend/tests/test_cost_caps.py`.

## Stripe chargeback / dispute exposure

Uncapped (no monthly ceiling), but **alert on any single dispute event** during
the launch window (Jun 1 17:00 PT → Jun 4 00:00 PT). Disputes are rare but
warrant attention given the 48-hour conversion target.

- Webhook: `charge.dispute.created` → Slack `#incidents` with deep link.
- Source: `backend/services/stripe_webhook_service.py`.

## Verification

```bash
curl -X POST -H "X-API-Key: $INTERNAL_API_KEY" \
  https://api.rateshift.app/api/v1/internal/cost-caps/check | jq
# expect: { "checks": [...], "any_breached": false }
```
