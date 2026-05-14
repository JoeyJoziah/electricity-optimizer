# Waitlist Inventory

**Date**: 2026-05-12
**Status**: ✅ COMPLETE (Scope #6a — locate AND count)
**PRD ref**: `.loki/prds/ph-relaunch-jun2-2026.md` Scope #6, Appendix A

## Storage location

- **Database**: Neon project `cold-rice-23455092` (energyoptimize)
- **Table**: `public.beta_signups`
- **Ingestion endpoint**: `POST /api/v1/beta/signup`
- **Source**: `backend/api/v1/beta.py`

## Count (as of 2026-05-12)

```sql
SELECT count(*) AS waitlist_count FROM beta_signups;
-- result: 0
```

**Zero rows.** No frontend form is currently wired to `POST /api/v1/beta/signup` —
top-of-funnel leak documented and explicitly accepted as out-of-scope for the
Jun 2 launch (see PRD Scope "Out").

## Consequences for launch

1. **Drip warm-up (Scope #5)**: dropped. Threshold ≥200 not met; rely on
   existing `rateshift.app` sender reputation via Resend.
2. **Launch-day email blast**: waitlist branch removed from sequence.
   Existing app signups only.
3. **Slip-comms (Scope #17)**: simplified — no waitlist segment to notify.

## Future work (post-launch)

- Wire `/api/v1/beta/signup` to a marketing-page form (Q3 candidate).
- Backfill is impossible — no historical email captures exist.
