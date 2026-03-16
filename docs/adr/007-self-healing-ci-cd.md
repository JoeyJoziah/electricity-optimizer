# ADR-007: Self-Healing CI/CD Pipeline

**Status**: Accepted
**Date**: 2026-03-06
**Decision Makers**: Devin McGrath

## Context

With 31 GitHub Actions workflows (12 cron-triggered), transient failures in
external services (Render API, Neon, npm registry) caused noisy red badges and
required manual re-runs. We needed automated resilience without masking real
failures.

Options considered: manual re-runs, GitHub Actions retry action (third-party),
custom composite actions, no change.

## Decision

Build three **composite actions** and a **self-healing monitor** workflow:

1. **`retry-curl`** (`/.github/actions/retry-curl/action.yml`): Exponential
   backoff with jitter for HTTP calls. Retries on 5xx/429/408/000; fails
   immediately on 4xx (except 429/408). Default 3 retries.
2. **`notify-slack`** (`/.github/actions/notify-slack/action.yml`):
   Color-coded severity alerts to `#incidents` (C0AKV2TK257). Uses
   `SLACK_INCIDENTS_WEBHOOK_URL` secret.
3. **`validate-migrations`** (`/.github/actions/validate-migrations/action.yml`):
   Checks sequential numbering, `IF NOT EXISTS`, `neondb_owner` grants, no
   `SERIAL` types.
4. **`self-healing-monitor.yml`**: Daily 9am UTC cron. Checks 16 workflows for
   3+ consecutive failures, auto-creates GitHub issues with `self-healing`
   label, auto-closes when failures resolve.

All 12 cron workflows use `retry-curl` + `notify-slack`. CI auto-formats
(Black + isort) on PRs with a commit bot.

## Consequences

### Positive
- Transient failures self-resolve without human intervention.
- Real failures surface as GitHub issues with clear context.
- Slack alerts provide immediate visibility for on-call awareness.
- Migration validation prevents common schema errors pre-deploy.

### Negative
- Retry logic can delay failure detection by up to ~30s per call.
- Self-healing monitor adds one daily API call per monitored workflow.
- `SLACK_INCIDENTS_WEBHOOK_URL` secret required in all environments.
