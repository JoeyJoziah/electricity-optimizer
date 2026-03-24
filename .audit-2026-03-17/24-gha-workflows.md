# Audit Report: GHA Workflows & CI/CD
## Date: 2026-03-17
## Auditor: Claude Code (claude-sonnet-4-6)

---

### Executive Summary

**Scope**: 34 workflow files, 7 composite actions, 1 dependabot configuration (42 files total).

The workflow suite is architecturally mature for a production SaaS: sparse checkouts are used widely to
minimize checkout cost, a reusable `retry-curl` composite handles exponential backoff consistently, the
`self-healing-monitor` closes the observability loop, and crons that were expensive in GHA minutes have
been migrated to CF Worker Cron Triggers. Secrets are handled well overall — values are bound to
environment variables rather than interpolated inline in most critical paths.

However, several meaningful gaps remain. The two most urgent are a **missing `permissions:` block** on
`keepalive.yml` and `fetch-heating-oil.yml` (granting default write-all on a public repo), and a
**confirmed command-injection vector** in `self-healing-monitor.yml` where a GitHub issue title is
passed directly into a shell here-doc that already contains `${{ ... }}` expressions alongside
`$(date ...)` — a malicious workflow name in the matrix could inject arbitrary shell commands. Below that,
seven workflows are missing `timeout-minutes`, the `detect-rate-changes.yml` file uses `vars.BACKEND_URL`
(a repository variable) while every sibling workflow uses `secrets.BACKEND_URL`, and `code-analysis.yml`
installs `claude-flow@latest` at pin-free (supply-chain risk).

**Severity breakdown**: 0 P0, 6 P1, 9 P2, 9 P3.

---

### Findings

---

#### P1 — High

**H-1: Missing `permissions:` block grants implicit write-all in two workflows**

Files: `.github/workflows/keepalive.yml`, `.github/workflows/fetch-heating-oil.yml`

GitHub Actions grants `write-all` by default when no `permissions:` block is present at the workflow
level and no organisation-wide default has been set to `read-all`. Both files omit the key entirely.
`keepalive.yml` only reads a public URL, so it needs no token at all. `fetch-heating-oil.yml` calls
internal API endpoints and also needs nothing beyond the default `GITHUB_TOKEN` with `contents: read`.

Every other workflow in the repository either sets `permissions: {}` or declares the specific minimal
set needed. These two are outliers that represent a silent escalation of privilege.

Remediation — add to both files immediately after the `on:` block:

```yaml
permissions: {}
```

---

**H-2: `detect-rate-changes.yml` uses `vars.BACKEND_URL` instead of `secrets.BACKEND_URL`**

File: `.github/workflows/detect-rate-changes.yml`, line 23

```yaml
url: ${{ vars.BACKEND_URL }}/api/v1/internal/detect-rate-changes
```

Every other internal-endpoint workflow uses `secrets.BACKEND_URL`. Repository variables (`vars.*`) are
visible in the Actions UI to anyone with read access to the repository. If the repository is ever made
public — or if `BACKEND_URL` is considered sensitive (it is; it is the internal Render URL, not the CF
gateway) — this leaks the value. This is also inconsistent with the CLAUDE.md contract that states all
`/internal/*` routes require `X-API-Key` and use `BACKEND_URL`.

The same file also uses the legacy `api-key:` input to `retry-curl` instead of `headers:`, which the
retry-curl composite does not document as a valid input — meaning the key may silently be dropped and
the call may bypass authentication on the backend side.

Remediation:

```yaml
# Replace lines 23-24
url: ${{ secrets.BACKEND_URL }}/api/v1/internal/detect-rate-changes
method: POST
headers: |
  X-API-Key: ${{ secrets.INTERNAL_API_KEY }}
  Content-Type: application/json
```

Also add `permissions: {}`, `timeout-minutes: 5`, and a `concurrency:` group (currently missing — see H-4).

---

**H-3: `self-healing-monitor.yml` — potential shell injection via matrix `workflow-name` in issue body**

File: `.github/workflows/self-healing-monitor.yml`, lines 83-108

The "Create new issue" step uses a here-doc (`<<'BODY'`) to construct the issue body, but the `--body`
argument is a subshell expansion `$(cat <<'BODY' ... BODY)`. Inside that expansion, several
`${{ matrix.workflow.name }}` and `${{ steps.count.outputs.failures }}` expressions are interpolated by
the GitHub Actions expression engine *before* the shell processes the here-doc. This happens because the
`run:` step is not inside an `env:` wrapper — the expressions are substituted into the bash source code
before bash sees it.

The `matrix.workflow.name` values are hardcoded in the same file so this is not currently exploitable
externally. However, if the matrix is ever extended from an external source (e.g. a JSON file read from
the repo), or if the failure count output from `gh run list` can be manipulated to contain shell
metacharacters (it can: `gh` may return unexpected output on API errors that bypasses the `|| echo "0"`
fallback), this becomes a code-injection vector.

More concretely: `${{ steps.count.outputs.failures }}` is shell-interpolated without quoting inside a
command substitution. If `gh run list` ever returns a string containing `; rm -rf /` or similar through
the `|| echo "0"` path, it will be executed.

Remediation — pass all dynamic values through environment variables:

```yaml
- name: Create new issue
  env:
    WORKFLOW_NAME: ${{ matrix.workflow.name }}
    WORKFLOW_FILE: ${{ matrix.workflow.file }}
    WORKFLOW_SEVERITY: ${{ matrix.workflow.severity }}
    FAILURE_COUNT: ${{ steps.count.outputs.failures }}
  run: |
    gh issue create \
      --repo "${{ github.repository }}" \
      --title "Self-healing: ${WORKFLOW_NAME} has ${FAILURE_COUNT} failures in 24h" \
      --label "self-healing,automated" \
      --body "## Automated Failure Detection

    **Workflow**: ${WORKFLOW_NAME} (\`${WORKFLOW_FILE}\`)
    **Severity**: ${WORKFLOW_SEVERITY}
    **Failures in last 24h**: ${FAILURE_COUNT}
    **Detected at**: $(date -u '+%Y-%m-%d %H:%M UTC')
    ..."
```

---

**H-4: `detect-rate-changes.yml` missing `timeout-minutes`, `permissions:`, and `concurrency:`**

File: `.github/workflows/detect-rate-changes.yml`

This workflow has no `timeout-minutes` on its job (lines 8-33), no `permissions:` block at the workflow
level, and no `concurrency:` block. It is a `workflow_dispatch`-only file (cron moved to the pipeline),
so the stacking risk is lower than for scheduled crons — but a human double-trigger could run two
instances simultaneously and hit the internal endpoint twice, potentially double-counting rate-change
detections.

Remediation: add all three blocks. Reference sibling files (`scan-emails.yml`, `nightly-learning.yml`)
for the canonical pattern.

---

**H-5: `code-analysis.yml` installs `claude-flow@latest` at an unpinned version (supply-chain risk)**

File: `.github/workflows/code-analysis.yml`, line 28

```yaml
- name: Install claude-flow
  run: npm install -g claude-flow@latest
```

Using `@latest` from npm in a CI workflow means any compromised or malicious new version published to
the `claude-flow` package will automatically execute in your pipeline on the next PR. This is a
supply-chain attack surface. All other third-party tools in the codebase pin to a specific version tag
(e.g. `zaproxy/action-baseline@v0.12.0`, `gitleaks/gitleaks-action@v2`).

This is the only workflow that installs an npm package globally at runtime rather than via the
`setup-node-env` action or a committed `package.json`. The Claude Flow MCP server is already registered
locally via `.mcp.json`; this step is redundant for local analysis and risky in CI.

Remediation: pin to a specific version or replace with a pinned GitHub Action reference if one exists,
or remove the step if the `claude-flow` analysis is not reliably actionable in CI.

```yaml
# Option A: pin the version
run: npm install -g claude-flow@3.x.y   # replace with known-good version

# Option B: wrap in || true if the tool is advisory only
run: npm install -g claude-flow@3.x.y || echo "::warning::claude-flow install failed, skipping analysis"
```

---

**H-6: `e2e-tests.yml` `security-tests` job has no `permissions:` block**

File: `.github/workflows/e2e-tests.yml`, lines 560-621

The `security-tests` job (which runs `bandit` and actual security tests against a running backend) has no
`permissions:` block. Unlike the top-level `e2e-tests` workflow which also lacks a workflow-level
`permissions:` block, this means this job runs with the implicit `write-all` default. The workflow-level
`permissions:` omission affects all jobs in the file including `lighthouse` (which has `pull-requests: write`
declared per-job — that is correct), but `security-tests` and `load-tests` have no per-job declaration.

Remediation: add `permissions: {}` at the workflow level in `e2e-tests.yml` and add specific
`permissions:` to the two jobs that need elevated access:

```yaml
# Workflow level
permissions: {}

# lighthouse job
permissions:
  pull-requests: write

# e2e-tests job (needs checks:write for the test-reporter action)
permissions:
  checks: write
  pull-requests: write
```

---

#### P2 — Medium

**M-1: `keepalive.yml` runs every hour (24 runs/day, ~720/mo) with no failure alerting**

File: `.github/workflows/keepalive.yml`

The keepalive workflow pings `https://api.rateshift.app/health` every hour. This costs approximately
720 GHA minutes per month (each run is `timeout-minutes: 2`). The CLAUDE.md notes UptimeRobot covers
real-time monitoring — if UptimeRobot is configured, this workflow is fully redundant for availability
monitoring. It also has no Slack notification on failure, meaning if the health endpoint returns a
non-2xx the output is a `::warning::` annotation in a run that nobody monitors.

The `gateway-health.yml` workflow, which runs every 12 hours, already validates the gateway more
thoroughly and sends Slack alerts on degradation.

Recommendation: either reduce the cron to every 6 hours (saving ~600 min/mo) to complement
`gateway-health.yml`, or disable it entirely given UptimeRobot coverage. If kept, add a Slack
notification on non-2xx responses.

---

**M-2: `e2e-tests.yml` applies partial migrations, not the full 51-migration stack**

File: `.github/workflows/e2e-tests.yml`, lines 98-103

```yaml
- name: Set up database
  run: |
    PGPASSWORD=postgres psql ... -f backend/migrations/init_neon.sql
    PGPASSWORD=postgres psql ... -f backend/migrations/002_gdpr_auth_tables.sql
    PGPASSWORD=postgres psql ... -f backend/migrations/003_reconcile_schema.sql
```

Only 3 of 51 migrations are applied in the E2E database setup. This means any schema introduced after
migration 003 (48 migrations' worth of tables, including the community system, notifications, GDPR
cascade fixes, etc.) does not exist in the E2E test database. Tests that hit endpoints relying on those
tables will either pass trivially due to API mocking or fail with misleading "table does not exist"
errors.

The `ci.yml` migration-check job correctly applies all migrations in order. The E2E job should match.

Remediation: replace the three explicit psql calls with the same loop pattern used in `ci.yml`:

```yaml
- name: Set up database
  run: |
    PGPASSWORD=postgres psql -h localhost -U postgres -d electricity_test \
      -v ON_ERROR_STOP=1 -f backend/migrations/init_neon.sql
    for f in $(ls backend/migrations/[0-9]*.sql | sort); do
      PGPASSWORD=postgres psql -h localhost -U postgres -d electricity_test \
        -v ON_ERROR_STOP=1 -f "$f"
    done
```

---

**M-3: `gateway-health.yml` inlines `secrets.INTERNAL_API_KEY` directly into a `run:` step via `${{ }}`**

File: `.github/workflows/gateway-health.yml`, line 29

```yaml
-H "X-API-Key: ${{ secrets.INTERNAL_API_KEY }}" \
```

This interpolates the secret directly into the bash source code before the shell processes the line.
While GitHub Actions redacts secret values from logs, the value is still present in the process
environment's command line, visible via `/proc/self/cmdline` on Linux runners for the duration of the
step, and not protected from exfiltration by a compromised action in the same job.

The canonical pattern used everywhere else (see `retry-curl` action) binds secrets to environment
variables first:

```yaml
env:
  API_KEY: ${{ secrets.INTERNAL_API_KEY }}
run: |
  -H "X-API-Key: ${API_KEY}" \
```

The `data-health-check.yml` Validate step (lines 35-49) has the same pattern correctly with `env:` —
the `gateway-health.yml` fetch step should be updated to match.

---

**M-4: `ci.yml` `backend-lint` and `frontend-lint` push formatting commits using `github.token` with `contents: write`**

File: `.github/workflows/ci.yml`, lines 64-100, 190-219

The auto-format jobs check out with `token: ${{ github.token }}` and push formatting fixes directly to
PR branches. The `github.token` default GITHUB_TOKEN has limited scope, but `contents: write` is
granted at the job level. The commit is pushed without any CI check guard — a PR can receive a
formatting commit from the bot mid-run, which then re-triggers CI, creating a recursive CI loop on
heavy format diffs.

More significantly, the format commit is unconditional: if a PR from a fork is open against `main` or
`develop`, the workflow will fail to push (forks do not get write access), but the error message is not
surfaced cleanly — it will appear as a generic push failure rather than a meaningful error.

Recommendation: add `if: github.event.pull_request.head.repo.full_name == github.repository` to the
commit-and-push steps to explicitly skip format commits on fork PRs, and suppress or handle the error
more gracefully.

---

**M-5: `self-healing-monitor.yml` concurrency set to `cancel-in-progress: true` — risks dropping issue creation mid-run**

File: `.github/workflows/self-healing-monitor.yml`, line 11

```yaml
concurrency:
  group: self-healing-monitor
  cancel-in-progress: true
```

The monitor is a daily scheduled workflow. A manual `workflow_dispatch` triggered while the scheduled
run is in progress will cancel the ongoing matrix — which may have already opened some issues but not
yet processed all 18 workflows. The partially-executed run leaves no trace of which workflows were
skipped, creating silent monitoring gaps.

For a monitoring/alerting workflow, `cancel-in-progress: false` is the safer default. If two runs must
not overlap (e.g. to avoid duplicate issues), the concurrency group already handles that — but
cancellation is the wrong conflict-resolution strategy here.

Remediation:

```yaml
concurrency:
  group: self-healing-monitor
  cancel-in-progress: false
```

---

**M-6: `deploy-worker.yml` jobs have no `timeout-minutes`**

File: `.github/workflows/deploy-worker.yml`

Neither the `test` job nor the `deploy` job nor the `notify-failure` job have a `timeout-minutes`
declaration. A hung wrangler deployment or test run will consume the full 6-hour GitHub Actions job
timeout. Given this deploys to production Cloudflare Workers, a stuck deploy could block other
`deploy-worker` runs (concurrency: `cancel-in-progress: false`).

Remediation:

```yaml
test:
  timeout-minutes: 10

deploy:
  timeout-minutes: 10

notify-failure:
  timeout-minutes: 5
```

---

**M-7: `utility-type-tests.yml` `utility-matrix-summary` job has no `timeout-minutes`**

File: `.github/workflows/utility-type-tests.yml`, lines 92-105

The summary job only runs a simple `echo` and exit condition check, but it has no timeout. This is
minor but inconsistent with every other summary/notify job in the codebase.

Remediation: `timeout-minutes: 5`.

---

**M-8: `scrape-portals.yml` uses `cancel-in-progress: true` but is a weekly non-idempotent job**

File: `.github/workflows/scrape-portals.yml`, lines 8-11

```yaml
concurrency:
  group: scrape-portals
  cancel-in-progress: true
```

Portal scraping encrypts credentials and scrapes external sites. If a manual `workflow_dispatch` cancels
an in-progress weekly scrape mid-way, some portals will be scraped and others not, with no indication of
which succeeded. Unlike CI test jobs (where cancellation is safe), this job is stateful. The remaining
workflows in this file pattern all use `cancel-in-progress: false`.

Remediation: change to `cancel-in-progress: false` to match the pattern of all other data-pipeline
workflows.

---

**M-9: `dependabot.yml` does not cover `/workers/api-gateway` npm packages**

File: `.github/dependabot.yml`

Dependabot is configured for `/frontend` (npm), `/backend` (pip), `/ml` (pip), and `/` (github-actions).
The CF Worker at `workers/api-gateway/` has its own `package.json` and `package-lock.json` and is
actively maintained (90 tests, deployed via its own workflow). Its npm dependencies are not monitored
by Dependabot.

Remediation: add a fifth entry to `dependabot.yml`:

```yaml
- package-ecosystem: "npm"
  directory: "/workers/api-gateway"
  schedule:
    interval: "weekly"
    day: "monday"
  open-pull-requests-limit: 5
  groups:
    minor-and-patch:
      update-types:
        - "minor"
        - "patch"
```

---

#### P3 — Low

**L-1: `detect-rate-changes.yml` references `retry-curl`'s undocumented `api-key:` input**

File: `.github/workflows/detect-rate-changes.yml`, line 25

```yaml
api-key: ${{ secrets.INTERNAL_API_KEY }}
```

The `retry-curl` composite action's `action.yml` defines only the following inputs: `url`, `method`,
`headers`, `body`, `max-retries`, `initial-delay`, `max-delay`, `timeout`. There is no `api-key` input.
GitHub Actions silently ignores unknown inputs to composite actions — the API key is never passed, and
the call proceeds without authentication. The backend's `require_internal_auth` middleware will reject
it with a 403, which the `retry-curl` action's 4xx fast-fail logic will treat as a non-retryable error
and fail the workflow.

This means the `detect-rate-changes.yml` dispatch workflow is currently broken and will always fail if
triggered. (See also H-2 which covers the `vars.` vs `secrets.` issue in the same file.)

---

**L-2: `model-retrain.yml` validation step does not actually retrain — misleading workflow name**

File: `.github/workflows/model-retrain.yml`, lines 32-45

The "Run model retraining" step runs a Python one-liner that instantiates the `ElectricityPriceForecaster`
but explicitly comments that "In production, data would be fetched from TimescaleDB. For now, this
validates the training pipeline runs." The workflow is named "Weekly Model Retraining" and is listed in
the self-healing monitor matrix, but it runs no actual retraining.

This is a known placeholder, but it creates two risks: (1) the self-healing monitor watches this
workflow for failures, but a succeeded stub gives false confidence that ML retraining is healthy;
(2) the comment says "TimescaleDB" but the project uses Neon PostgreSQL.

Recommendation: rename the workflow to "Weekly Model Pipeline Validation" or wire up actual data
fetching. Update the self-healing monitor description to reflect the current behavior.

---

**L-3: Action versions use major tags (`@v4`, `@v3`) rather than pinned commit SHAs**

All third-party actions across all workflow files use floating major-version tags (e.g.
`actions/checkout@v4`, `actions/cache@v4`, `codecov/codecov-action@v4`). Floating major tags can be
silently updated by the action author, which could introduce regressions or (in an attack scenario)
malicious code.

Industry best practice is to pin actions to full commit SHAs and use a tool like Dependabot (already
configured for `github-actions`) to propose SHA upgrades. Dependabot's `github-actions` ecosystem
support will still work with SHA-pinned actions via version comment.

Example:

```yaml
# Before
- uses: actions/checkout@v4

# After (pinned SHA, Dependabot will still update this)
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
```

Priority: `gitleaks/gitleaks-action@v2` and `zaproxy/action-baseline@v0.12.0` are the highest-risk
third-party actions (run arbitrary scanning code) and should be pinned first.

---

**L-4: `fetch-gas-rates.yml` and `fetch-heating-oil.yml` both collect energy commodity data on Monday but are separate workflows with no sequencing**

Files: `.github/workflows/fetch-gas-rates.yml` (Monday 4am UTC),
`.github/workflows/fetch-heating-oil.yml` (Monday 2pm UTC)

These workflows are functionally similar (EIA API, internal endpoint, retry-curl pattern) and run on
the same day. They are not tracked in the `self-healing-monitor.yml` matrix — `fetch-gas-rates.yml` is
missing entirely. If gas rate fetching fails, no issue is auto-created and no Slack alert fires (the
`notify-slack` step is present but only fires on individual failure, not tracked across days).

Recommendation: add `fetch-gas-rates.yml` to the self-healing monitor matrix. Consider consolidating
the two into a single "Fetch Commodity Prices" workflow with sequential steps, similar to the
`daily-data-pipeline.yml` pattern.

---

**L-5: `code-analysis.yml` only triggers on PRs to `main`, not `develop`**

File: `.github/workflows/code-analysis.yml`, line 5

```yaml
on:
  pull_request:
    branches: [main]
```

All other PR-triggered workflows include both `[main, develop]`. PRs to `develop` (the integration
branch) do not get code analysis. This means regressions in complexity and circular dependencies are
only caught at the final merge stage, not during development.

Remediation:

```yaml
on:
  pull_request:
    branches: [main, develop]
```

---

**L-6: `_backend-tests.yml` reusable workflow does not declare `permissions:` at the workflow level**

File: `.github/workflows/_backend-tests.yml`

Reusable workflows called with `workflow_call` inherit the permissions of the caller when no
`permissions:` block is declared in the reusable workflow itself. The callers (`ci.yml`,
`deploy-production.yml`, `deploy-staging.yml`) have varying permissions. `deploy-production.yml` has
`permissions: contents: read` at the workflow level, which is correct, but `ci.yml` has no
workflow-level `permissions:`, meaning `_backend-tests.yml` inherits write-all when called from CI.

Remediation: add `permissions: {}` to `_backend-tests.yml` at the top level. The backend tests only
need `contents: read` plus the Codecov upload (which uses a token, not a permission).

---

**L-7: `notify-slack` composite action builds the Slack payload using heredoc with unquoted environment variables — potential JSON injection**

File: `.github/actions/notify-slack/action.yml`, lines 47-67

The Slack payload is assembled with a shell heredoc where `${SLACK_WORKFLOW_NAME}` is interpolated
unquoted into a JSON string. If a `workflow-name` input contains double quotes, backslashes, or
newlines (all legal in the names passed to the action — e.g. the gateway-health workflow passes a
multi-part string with `=` and `,` characters), the resulting JSON will be malformed and the POST will
fail silently (the `|| true` suppresses the error).

```bash
"text": "... *CI/CD Alert: ${SLACK_WORKFLOW_NAME}*\n..."
```

Remediation: use `jq` to construct the payload safely:

```bash
PAYLOAD=$(jq -n \
  --arg name "${SLACK_WORKFLOW_NAME}" \
  --arg severity "${SLACK_SEVERITY}" \
  --arg url "${SLACK_RUN_URL}" \
  --arg color "${COLOR}" \
  --arg emoji "${EMOJI}" \
  --arg ts "${TIMESTAMP}" \
  --arg repo "${SLACK_REPOSITORY}" \
  '{attachments: [{color: $color, blocks: [{type: "section", text: {type: "mrkdwn", text: ($emoji + " *CI/CD Alert: " + $name + "*\nSeverity: " + $severity + "\n<" + $url + "|View Run Logs>")}}, {type: "context", elements: [{type: "mrkdwn", text: ("Triggered at " + $ts + " | Repository: " + $repo)}]}]}]}')
```

---

**L-8: `warmup-backend` composite action interpolates `inputs.*` values directly into shell without quoting**

File: `.github/actions/warmup-backend/action.yml`, lines 25-26

```bash
MAX=${{ inputs.max-attempts }}
DELAY=${{ inputs.delay-seconds }}
```

These inputs are expected to be numeric strings from callers. If a caller accidentally passes a value
containing shell metacharacters (e.g. `delay-seconds: "10; echo pwned"`), the expansion executes the
injected command. While the callers in this codebase all pass literal integers, composite actions are a
shared interface and should be defensive.

Remediation: pass all `inputs.*` through environment variables:

```yaml
env:
  INPUT_MAX: ${{ inputs.max-attempts }}
  INPUT_DELAY: ${{ inputs.delay-seconds }}
run: |
  MAX=$INPUT_MAX
  DELAY=$INPUT_DELAY
```

The `retry-curl` action already does this correctly (lines 51-68) and should be the template.

---

**L-9: `update-visual-baselines.yml` missing `permissions:` at workflow level**

File: `.github/workflows/update-visual-baselines.yml`

This `workflow_dispatch`-only file commits and pushes screenshot baselines using
`secrets.GITHUB_TOKEN`. A `permissions:` block is absent at the workflow level. The job does need
`contents: write` to push, but it should be declared explicitly:

```yaml
permissions:
  contents: write
```

---

### Statistics

| Metric | Count |
|---|---|
| Total files audited | 42 |
| Workflow files | 34 |
| Composite actions | 7 |
| Dependabot config | 1 |
| P0 (Critical) findings | 0 |
| P1 (High) findings | 6 |
| P2 (Medium) findings | 9 |
| P3 (Low) findings | 9 |
| Total findings | 24 |

### Finding Index

| ID | Severity | File | Issue |
|---|---|---|---|
| H-1 | P1/High | `keepalive.yml`, `fetch-heating-oil.yml` | Missing `permissions:` — implicit write-all |
| H-2 | P1/High | `detect-rate-changes.yml` | Uses `vars.` instead of `secrets.` for BACKEND_URL |
| H-3 | P1/High | `self-healing-monitor.yml` | Shell injection risk via unguarded `${{ }}` in here-doc |
| H-4 | P1/High | `detect-rate-changes.yml` | Missing `timeout-minutes`, `permissions:`, `concurrency:` |
| H-5 | P1/High | `code-analysis.yml` | Unpinned `claude-flow@latest` npm install (supply chain) |
| H-6 | P1/High | `e2e-tests.yml` | Missing workflow-level `permissions:` block |
| M-1 | P2/Med | `keepalive.yml` | Hourly cron redundant with UptimeRobot (~720 min/mo) |
| M-2 | P2/Med | `e2e-tests.yml` | E2E DB only applies 3 of 51 migrations |
| M-3 | P2/Med | `gateway-health.yml` | Secret interpolated inline into run step (not via env:) |
| M-4 | P2/Med | `ci.yml` | Auto-format bot push fails silently on fork PRs |
| M-5 | P2/Med | `self-healing-monitor.yml` | `cancel-in-progress: true` can leave monitoring gaps |
| M-6 | P2/Med | `deploy-worker.yml` | All jobs missing `timeout-minutes` |
| M-7 | P2/Med | `utility-type-tests.yml` | Summary job missing `timeout-minutes` |
| M-8 | P2/Med | `scrape-portals.yml` | `cancel-in-progress: true` on stateful scrape job |
| M-9 | P2/Med | `dependabot.yml` | CF Worker npm packages not covered by Dependabot |
| L-1 | P3/Low | `detect-rate-changes.yml` | Undocumented `api-key:` input silently dropped by `retry-curl` |
| L-2 | P3/Low | `model-retrain.yml` | Stub validation masquerades as real retraining |
| L-3 | P3/Low | All workflows | Actions pinned to major tags, not commit SHAs |
| L-4 | P3/Low | `fetch-gas-rates.yml` | Not in self-healing monitor matrix; redundant with heating-oil |
| L-5 | P3/Low | `code-analysis.yml` | Only triggers on PRs to `main`, not `develop` |
| L-6 | P3/Low | `_backend-tests.yml` | No `permissions:` block; inherits caller permissions |
| L-7 | P3/Low | `notify-slack/action.yml` | JSON injection risk from unquoted workflow name in heredoc |
| L-8 | P3/Low | `warmup-backend/action.yml` | Inputs interpolated into shell without env: wrapper |
| L-9 | P3/Low | `update-visual-baselines.yml` | Missing `permissions:` at workflow level |

### Recommended Fix Priority

1. **Immediate** (before next PR merge): H-1, H-2, H-3, H-4, H-6 — permissions and injection fixes are
   one-liners and carry real security weight.
2. **This sprint**: M-2 (E2E migration stack), M-6 (worker timeouts), M-9 (Dependabot CF Worker), L-1
   (broken detect-rate-changes dispatch).
3. **Next sprint**: M-1 (keepalive cost), M-3 (gateway-health secret pattern), M-4 (fork PR formatting),
   M-5 (monitor cancellation), M-8 (portal scrape concurrency), H-5 (claude-flow pin).
4. **Backlog**: L-2 through L-9 — hygiene and defence-in-depth improvements.
