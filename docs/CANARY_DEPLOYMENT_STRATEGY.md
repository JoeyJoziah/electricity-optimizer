# Canary Deployment Strategy for Utility-Specific Changes

> Status: **Documentation only** (Wave 4). Implementation planned for Wave 5+.

## Overview

When deploying changes that affect specific utility types (electricity, gas, heating oil, propane, solar, water), use a phased rollout via feature flags to limit blast radius.

## Feature Flag-Based Canary

Each utility type has a dedicated feature flag in the `feature_flags` table:

| Flag Name | Description |
|-----------|-------------|
| `utility_electricity` | Electricity rates and pricing |
| `utility_natural_gas` | Natural gas rates and pricing |
| `utility_heating_oil` | Heating oil price tracking |
| `utility_propane` | Propane price tracking |
| `utility_community_solar` | Community solar programs |
| `utility_water` | Water rate benchmarking |
| `utility_forecast` | Rate forecasting (Pro tier) |
| `utility_export` | Data export (Business tier) |

## Rollout Phases

### Phase 1: Internal Testing (percentage: 0, enabled: true)
- Deploy code changes behind the feature flag
- Only internal users (via admin override) can access
- Run integration tests against staging

### Phase 2: Percentage Rollout (percentage: 10-25)
- Enable for 10-25% of users via deterministic hash
- Monitor error rates, latency, and user feedback
- Duration: 24-48 hours minimum

### Phase 3: Expanded Rollout (percentage: 50-75)
- Increase to 50-75% if Phase 2 metrics are healthy
- Duration: 24 hours minimum

### Phase 4: Full Rollout (percentage: 100)
- Enable for all users
- Continue monitoring for 48 hours

## Rollback Criteria

Immediately roll back (set `enabled: false`) if any of these occur:

| Metric | Threshold |
|--------|-----------|
| Error rate (5xx) | > 1% of requests |
| P95 latency | > 2x baseline |
| Data accuracy | Any incorrect rate data |
| User reports | > 3 complaints about same issue |

### Rollback Procedure

```bash
# Via internal API (requires INTERNAL_API_KEY)
curl -X PUT https://api.rateshift.app/api/v1/internal/flags/utility_<type> \
  -H "X-API-Key: $INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

Or reduce percentage for gradual rollback:
```bash
curl -X PUT https://api.rateshift.app/api/v1/internal/flags/utility_<type> \
  -H "X-API-Key: $INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"percentage": 0}'
```

## Monitoring Checklist

Before advancing each rollout phase, verify:

- [ ] No new Sentry errors related to the utility type
- [ ] API response times within baseline (check Render metrics)
- [ ] Database query performance normal (check Neon dashboard)
- [ ] Cron jobs for the utility type completing successfully
- [ ] No Slack alerts in #incidents channel
- [ ] Feature flag evaluation count matches expected user percentage

## Utility-Specific Considerations

### Electricity & Natural Gas
- Highest traffic volume — use smaller initial percentage (10%)
- Monitor `electricity_prices` table query performance
- Check scrape-rates and check-alerts crons

### Heating Oil & Propane
- Seasonal demand — verify historical data availability
- Monitor EIA API rate limits during rollout

### Community Solar
- State-specific programs — test across multiple states
- Verify CCA program data integrity

### Water
- Municipal rate sources vary widely — monitor data quality
- Benchmark calculations sensitive to tier structure changes

## Implementation Notes (Wave 5+)

When implementing the automated canary system:

1. Add `POST /internal/canary/start` endpoint to begin phased rollout
2. Add `GET /internal/canary/status` to check rollout health
3. Integrate with GitHub Actions for automated rollback on CI failure
4. Add Slack notifications for each rollout phase transition
5. Consider integration with Render's native canary deployment features
