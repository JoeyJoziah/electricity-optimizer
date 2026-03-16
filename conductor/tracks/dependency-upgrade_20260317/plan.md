# Implementation Plan

See full detailed plan at: [docs/plans/2026-03-17-dependency-upgrade.md](../../../docs/plans/2026-03-17-dependency-upgrade.md)

## Task Summary

| Task | Description | Phase | Risk |
|------|-------------|-------|------|
| 0 | Baseline test counts | Pre-flight | - |
| 1 | Upgrade jest 29→30 (fixes 7 npm vulns) | 1 | Low |
| 2 | Bump safe Python patch versions (17 packages) | 1 | Low |
| 3 | Bump safe frontend minor versions (11 packages) | 1 | Low |
| 4 | Update httpx version cap | 1 | Low |
| 5 | Upgrade Sentry SDK v1→v2 | 2 | Medium |
| 6 | Upgrade Stripe v7→v14 | 2 | Medium |
| 7 | Upgrade Redis v5→v7 | 2 | Medium |
| 8 | Upgrade remaining backend dev tools | 2 | Medium |
| 9 | Upgrade lucide-react | 3 | Low |
| 10 | Upgrade better-auth 1.4→1.5 | 3 | Low |
| 11 | Upgrade zustand v4→v5 | 3 | Medium |
| 12 | Upgrade date-fns v3→v4 | 3 | Low |
| 13 | Upgrade recharts v2→v3 | 3 | Medium |
| 14 | Upgrade tailwind-merge v2→v3 | 3 | Low |
| 15 | Upgrade ESLint v8→v10 | DEFERRED | High |
| 16 | Upgrade numpy v1→v2 | 4 | High |
| 17 | Upgrade pandas v2→v3 | 4 | High |
| 18 | Final audit + deployment validation | Post | Low |
