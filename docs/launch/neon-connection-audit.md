# Neon Connection-Budget Audit

**Date**: 2026-05-12
**Status**: ✅ COMPLETE
**PRD ref**: `.loki/prds/ph-relaunch-jun2-2026.md` Scope #9

## Findings

- **Neon pooler `max_connections`**: 901
- **Backend workers**: 2 uvicorn workers
- **Per-worker pool**: SQLAlchemy `pool_size=5` + `max_overflow=10` = 15 max
- **Worst-case usage**: 2 × 15 = **30 connections**
- **Headroom**: 871 / 901 = **97% free**

## Failure branch

If a noisy-neighbor on the shared pooler ever pushes us toward the cap:

1. Render env: drop `WEB_CONCURRENCY` from 2 → 1 (halves connections, ~30%
   throughput hit, acceptable for launch-day mitigation).
2. SQLAlchemy: drop `max_overflow` 10 → 0 in `backend/db/session.py` and
   redeploy. Reverts after the spike clears.
3. Escalation: open Neon ticket; consider dedicated compute upgrade
   (currently on free tier `ep-withered-morning`).

## Action

**No change required for launch.** Settings.py comment corrected to reflect
accurate pooler limit (was previously documented as 100 — wrong).

## Verification

```sql
-- run against ep-withered-morning
SELECT setting::int AS max_connections FROM pg_settings WHERE name = 'max_connections';
-- expect: 901
```
