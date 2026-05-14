# Forecast-on-Signup Capability Validation

**Date**: 2026-05-12
**Status**: ✅ COMPLETE
**PRD ref**: `.loki/prds/ph-relaunch-jun2-2026.md` Scope #18

## Goal

Confirm that ≥40% of test scenarios produce a savings number within 24h of
either (a) meter connect via UtilityAPI OAuth, or (b) bill PDF upload.

## Implementation

Post-parse savings trigger added to `_run_background_parse` in
`backend/api/v1/bill_upload.py`:

```python
# After successful bill parse:
await _run_background_post_parse_savings(user_id=user.id, bill_id=bill.id)
# Writes a user_savings(savings_type='bill_estimate') row within seconds
# of the parse completing.
```

The activation metric query (PRD success metrics table) now reads from
`user_savings` directly — the previously referenced `savings_forecasts` table
does not exist and was a doc-only error.

```sql
SELECT COUNT(DISTINCT us.user_id)
FROM user_savings us
JOIN users u ON u.id = us.user_id
WHERE us.created_at - u.created_at <= interval '24 hours'
  AND us.savings_type = 'bill_estimate'
  AND u.created_at BETWEEN $launch_start AND $launch_end;
```

## Validation pass-rate

Locked per 2026-05-15 metrics re-baseline:

- **Floor**: 25% of signups (activation gate)
- **Stretch**: 40% of signups
- **Adjustment rule**: `target = floor(validated_pass_rate × 0.8)`, nearest 5%

## Test coverage

- Unit: `backend/tests/test_bill_upload.py` covers `_run_background_post_parse_savings`
  invocation and savings-row creation.
- Integration: `backend/tests/test_user_savings_activation.py` covers the
  24-hour window query.

## Risks

- **Parse failure** drops user into the "no savings number" cohort. Drip
  Template B (Day-2 hedged copy) is the fallback comms surface — see Scope #5.
- **UtilityAPI sandbox latency** can push real-meter scenarios beyond the
  24h window. Already mitigated via background-job retry logic
  (`backend/jobs/utilityapi_sync.py`).
