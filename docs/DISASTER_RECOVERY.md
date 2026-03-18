# RateShift — Disaster Recovery Runbook

> Last updated: 2026-03-18
> Status: Production-ready
> Scope: Database backup strategy, restore procedures, and recovery targets

---

## Table of Contents

1. [Recovery Objectives](#1-recovery-objectives)
2. [Backup Strategy](#2-backup-strategy)
3. [Backup Storage — Cloudflare R2](#3-backup-storage--cloudflare-r2)
4. [Required Secrets](#4-required-secrets)
5. [Restore Procedure](#5-restore-procedure)
6. [Partial Restore (Single Table)](#6-partial-restore-single-table)
7. [Self-Healing Monitor Integration](#7-self-healing-monitor-integration)
8. [Testing the Runbook](#8-testing-the-runbook)
9. [Known Limitations](#9-known-limitations)

---

## 1. Recovery Objectives

| Metric | Target | Basis |
|--------|--------|-------|
| **RTO** (Recovery Time Objective) | < 1 hour | Time to download latest backup from R2 (~3 min) + create Neon branch (~1 min) + `pg_restore` into branch (~5 min) + promote/reconnect backend (~10 min). Total well under 1h. |
| **RPO** (Recovery Point Objective) | < 7 days | Backups run weekly. Worst case: a failure occurs Sunday at 01:59 UTC — data loss is capped at the interval since the previous Sunday's backup. |
| **Backup frequency** | Weekly (Sunday 2am UTC) | Automated via `.github/workflows/db-backup.yml` |
| **Retention** | 30 most-recent backups | Automated rotation step in backup workflow |
| **Backup format** | `pg_dump --format=custom --compress=9` | Supports selective table restores via `pg_restore -t <table>` |

---

## 2. Backup Strategy

### Automated Backup Workflow

File: `.github/workflows/db-backup.yml`

The workflow runs two jobs every Sunday at 2am UTC (and supports `workflow_dispatch` for manual runs):

**Job 1 — `backup` (blocking)**

1. Installs `postgresql-client-16` on the runner.
2. Connects to Neon's pooled endpoint using `NEON_CONNECTION_STRING`.
3. Runs `pg_dump --format=custom --compress=9` and writes the output to `/tmp/`.
4. Uploads the `.dump` file to Cloudflare R2 under the `backups/` prefix.
5. Rotates old objects so only the newest 30 are retained.
6. Sends a Slack `#incidents` alert on any failure (`severity: critical`).

Backup filename pattern: `rateshift-backup-YYYYMMDD-HHMMSS.dump`
R2 key pattern: `backups/rateshift-backup-YYYYMMDD-HHMMSS.dump`

**Job 2 — `verify` (continue-on-error: true)**

1. Downloads the just-uploaded file from R2.
2. Validates the archive is structurally sound via `pg_restore --list`.
3. Creates an ephemeral Neon branch via the Neon REST API.
4. Runs a full `pg_restore` into the ephemeral branch.
5. Smoke-tests the restored schema (expects >= 44 public tables).
6. Deletes the ephemeral branch in an `if: always()` step so it never leaks.
7. Sends a Slack `#incidents` alert on verification failure (`severity: warning`).

The verify job is `continue-on-error: true` — a verification failure does not invalidate the uploaded backup artifact but surfaces as a Slack warning and a yellow check in the Actions UI.

---

## 3. Backup Storage — Cloudflare R2

| Property | Value |
|----------|-------|
| Provider | Cloudflare R2 (S3-compatible) |
| Region | Auto (Cloudflare global) |
| Bucket | Configured via `R2_BUCKET_NAME` secret |
| Path prefix | `backups/` |
| Access method | AWS CLI with `--endpoint-url` pointing to the R2 S3 endpoint |
| Encryption | At-rest encryption is included in R2 by default (AES-256) |
| Egress cost | $0 — R2 does not charge egress fees |

---

## 4. Required Secrets

Add these in GitHub → Settings → Secrets → Actions:

| Secret | Description |
|--------|-------------|
| `NEON_CONNECTION_STRING` | Full Neon PostgreSQL connection string including credentials. Use the **direct** (non-pooled) endpoint for pg_dump: `postgresql://user:pass@ep-withered-morning-aix83cfw.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require` |
| `NEON_API_KEY` | Neon personal API token (console.neon.tech → Account → API Keys). Required for the verify job's branch create/delete calls. |
| `R2_ACCESS_KEY_ID` | Cloudflare R2 API token → Access Key ID |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 API token → Secret Access Key |
| `R2_ENDPOINT` | Full HTTPS endpoint for your R2 account: `https://<CF_ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `R2_BUCKET_NAME` | R2 bucket name (e.g. `rateshift-backups`) |
| `SLACK_INCIDENTS_WEBHOOK_URL` | Already present — used by `notify-slack` composite action |

> Note: `NEON_CONNECTION_STRING` should point to the **direct** endpoint (`ep-withered-morning-aix83cfw.c-4.us-east-1.aws.neon.tech`) rather than the pooler (`-pooler.c-4.us-east-1.aws.neon.tech`). `pg_dump` uses non-multiplexed connections and does not work correctly through PgBouncer.

---

## 5. Restore Procedure

This procedure covers full database restoration from a backup stored in R2.

### Prerequisites

- `psql` and `pg_restore` (PostgreSQL 16 client tools)
- `aws` CLI configured with R2 credentials (or `rclone`)
- Access to the Neon console (https://console.neon.tech)
- 1Password vault "RateShift" for all credentials

### Step 1 — Identify the target backup

```bash
# List available backups (newest last)
aws s3 ls s3://<R2_BUCKET_NAME>/backups/ \
  --endpoint-url https://<CF_ACCOUNT_ID>.r2.cloudflarestorage.com \
  --profile r2 \
  | sort

# Pick the filename — e.g. rateshift-backup-20260316-020012.dump
export BACKUP_FILE="rateshift-backup-20260316-020012.dump"
```

### Step 2 — Download the backup file

```bash
aws s3 cp "s3://<R2_BUCKET_NAME>/backups/${BACKUP_FILE}" "/tmp/${BACKUP_FILE}" \
  --endpoint-url https://<CF_ACCOUNT_ID>.r2.cloudflarestorage.com \
  --profile r2

# Verify the file is a valid pg_dump archive before proceeding
pg_restore --list "/tmp/${BACKUP_FILE}" | head -20
```

### Step 3 — Create a new Neon branch (restore target)

Create the branch in the Neon console or via API:

```bash
# Via Neon REST API
curl -fsS -X POST \
  -H "Authorization: Bearer ${NEON_API_KEY}" \
  -H "Content-Type: application/json" \
  "https://console.neon.tech/api/v2/projects/cold-rice-23455092/branches" \
  -d '{
    "branch": {"name": "restore-20260316"},
    "endpoints": [{"type": "read_write"}]
  }' | jq '{branch_id: .branch.id, host: .endpoints[0].host}'
```

Wait approximately 30 seconds for the endpoint to become ready.

### Step 4 — Restore into the new branch

```bash
export BRANCH_DSN="postgresql://<user>:<pass>@<branch-host>/neondb?sslmode=require"

pg_restore \
  --no-owner \
  --no-privileges \
  --exit-on-error \
  --dbname "${BRANCH_DSN}" \
  "/tmp/${BACKUP_FILE}"
```

`--no-owner` and `--no-privileges` prevent restore failures from ownership differences between the dump source and the restore target.

### Step 5 — Verify the restored database

```bash
# Count public tables (expect 44)
psql "${BRANCH_DSN}" -c \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"

# Spot-check a few critical tables
psql "${BRANCH_DSN}" -c \
  "SELECT count(*) FROM users; SELECT count(*) FROM electricity_prices; SELECT count(*) FROM price_alerts;"
```

### Step 6 — Promote the branch to production

Two options depending on the failure scenario:

**Option A — Reset the production branch to this point-in-time** (preferred for total data loss)

In the Neon console: navigate to Branches → select `production` → "Reset from parent" and point to the restore branch, or reassign the compute endpoint.

**Option B — Update the backend connection string** (minimal downtime)

1. In Render dashboard → Backend service → Environment → update `DATABASE_URL` to the new branch connection string.
2. Trigger a new Render deploy to pick up the new connection string.
3. Verify health: `curl https://api.rateshift.app/health`

### Step 7 — Clean up

```bash
# Delete the temporary restore branch once production is confirmed healthy
curl -fsS -X DELETE \
  -H "Authorization: Bearer ${NEON_API_KEY}" \
  "https://console.neon.tech/api/v2/projects/cold-rice-23455092/branches/<branch_id>"
```

---

## 6. Partial Restore (Single Table)

`pg_dump --format=custom` supports selective table restores without restoring the full database.

```bash
# List all objects in the archive to find the table's OID or name
pg_restore --list "/tmp/${BACKUP_FILE}" | grep -i "<table_name>"

# Restore only the target table
pg_restore \
  --no-owner \
  --no-privileges \
  --table <table_name> \
  --dbname "${BRANCH_DSN}" \
  "/tmp/${BACKUP_FILE}"
```

---

## 7. Self-Healing Monitor Integration

Add `db-backup.yml` to the self-healing monitor matrix in `.github/workflows/self-healing-monitor.yml`:

```yaml
- { file: "db-backup.yml", name: "Database Backup", severity: "critical" }
```

The monitor checks for repeated failures over a 24-hour window. A backup failure is `severity: critical` because it degrades the project's ability to recover from data loss.

The corresponding `auto-close-resolved` case block in `self-healing-monitor.yml`:

```bash
*"Database Backup"*) WORKFLOW_FILE="db-backup.yml" ;;
```

---

## 8. Testing the Runbook

Run the backup workflow manually at any time:

```bash
# Via gh CLI
gh workflow run db-backup.yml --repo JoeyJoziah/electricity-optimizer

# Verify the run completed
gh run list --workflow db-backup.yml --limit 5
```

To test the full restore path without touching production, use the verify job output. The ephemeral Neon branch created during verification exercises the complete download → restore → smoke-test sequence.

---

## 9. Known Limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Weekly cadence | Up to 7 days of data loss (RPO) | Acceptable for current free-tier constraints. Can be tightened to daily if GHA minutes budget allows, or implemented as a CF Worker cron at no additional cost. |
| Neon free tier: 0.5 GB storage | Very large databases may hit storage limits | Monitor `COST_ANALYSIS.md`; upgrade Neon tier if DB approaches 400 MB. |
| Verify job is `continue-on-error` | A silent restore failure won't block CI | Slack warning is fired; check `#incidents` weekly. |
| `pg_dump` targets direct endpoint only | Pooler endpoint causes `pg_dump` errors | `NEON_CONNECTION_STRING` must use the direct (non-pooler) host. |
| neon_auth schema (9 tables) | Owned by the `neon_auth` internal role; may produce harmless ownership warnings during restore | Use `--no-owner` flag on `pg_restore` (already in the procedure above). |
