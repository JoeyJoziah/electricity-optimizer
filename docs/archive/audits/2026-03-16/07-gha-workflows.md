# GHA Workflow Security & Quality Audit

**Date**: 2026-03-16
**Scope**: All 31 workflow files under `.github/workflows/` + 7 composite actions under `.github/actions/`
**Auditor**: DevOps Engineer (Claude Code)

---

## Summary

| Severity | Count |
|----------|-------|
| P0 (Critical) | 3 |
| P1 (High) | 9 |
| P2 (Medium) | 14 |
| P3 (Low) | 8 |
| **Total** | **34** |

---

## P0 — Critical

### P0-01: Hardcoded Cloudflare Account ID in workflow

**File**: `.github/workflows/gateway-health.yml` (line 71)

```yaml
CF_ACCOUNT_ID: b41be0d03c76c0b2cc91efccdb7a10df
```

**Description**: The Cloudflare account ID is hardcoded as a plaintext environment variable directly in the workflow YAML. While an account ID alone is not a credential, it reduces the effort required for a targeted attack against the Cloudflare account and is a reconnaissance data point visible to every person with read access to the repository (including any future public leak). It also appears verbatim in the CLAUDE.md project file, doubling the exposure surface.

**Fix**: Move to a repository variable (`vars.CF_ACCOUNT_ID`) or secret (`secrets.CF_ACCOUNT_ID`).

```yaml
# Before
CF_ACCOUNT_ID: b41be0d03c76c0b2cc91efccdb7a10df

# After
CF_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}
```

---

### P0-02: Hardcoded Render service ID in workflow

**File**: `.github/workflows/deploy-production.yml` (lines 194–195)

```yaml
RENDER_API_BASE: https://api.render.com/v1
BACKEND_SERVICE_ID: srv-d649uhur433s73d557cg
```

**Description**: The Render backend service ID `srv-d649uhur433s73d557cg` is hardcoded in the rollback job. Combined with the `RENDER_API_KEY` secret, an attacker who compromises that key can immediately identify and target the exact service without any additional discovery. The same value is repeated in CLAUDE.md. Service IDs should be treated as semi-sensitive configuration that belongs in repository variables.

**Fix**: Move to a repository variable.

```yaml
# Before
BACKEND_SERVICE_ID: srv-d649uhur433s73d557cg

# After
BACKEND_SERVICE_ID: ${{ vars.RENDER_BACKEND_SERVICE_ID }}
```

---

### P0-03: Script injection risk via `matrix.workflow.name` in issue body

**File**: `.github/workflows/self-healing-monitor.yml` (lines 82–106)

```yaml
gh issue create \
  --title "Self-healing: ${{ matrix.workflow.name }} has ${{ steps.count.outputs.failures }} failures in 24h" \
  --body "$(cat <<'BODY'
  **Workflow**: ${{ matrix.workflow.name }} (`${{ matrix.workflow.file }}`)
```

**Description**: The `matrix.workflow.name` and `matrix.workflow.file` values are defined statically in the same workflow file, so the risk is low in the current configuration. However, the pattern of interpolating GitHub expressions directly into shell `--body` strings is dangerous. If this pattern were copied to a workflow that reads from untrusted inputs (PR titles, branch names, issue titles), the expression expansion happens before the shell sees the string, enabling injection. The `steps.count.outputs.failures` value, which comes from `gh run list` output, is also interpolated directly. A compromised workflow run returning a crafted failure count string could break the shell heredoc.

**Fix**: Pass dynamic values through environment variables and reference them in the shell body, rather than interpolating via `${{ }}` inside heredocs.

```yaml
# Before — expression expands before shell parses the heredoc
--body "$(cat <<'BODY'
**Failures**: ${{ steps.count.outputs.failures }}
BODY
)"

# After — env var is set by the runner, never inline-expanded into shell
- name: Create new issue
  env:
    WORKFLOW_NAME: ${{ matrix.workflow.name }}
    WORKFLOW_FILE: ${{ matrix.workflow.file }}
    FAILURE_COUNT: ${{ steps.count.outputs.failures }}
    WORKFLOW_SEVERITY: ${{ matrix.workflow.severity }}
  run: |
    gh issue create \
      --title "Self-healing: ${WORKFLOW_NAME} has ${FAILURE_COUNT} failures in 24h" \
      --label "self-healing,automated" \
      --body "**Workflow**: ${WORKFLOW_NAME} (\`${WORKFLOW_FILE}\`)
**Severity**: ${WORKFLOW_SEVERITY}
**Failures**: ${FAILURE_COUNT}"
```

---

## P1 — High

### P1-01: Third-party actions not pinned to SHA digests

**Files**: Multiple (see list below)

**Description**: Actions pinned to mutable tags (e.g., `@v3`, `@v4`) can be updated by the upstream maintainer at any time. If a maintainer's account is compromised or a malicious update is pushed, every workflow run will execute attacker-controlled code with full access to repository secrets. SHA pinning is the only tamper-evident guarantee.

The following third-party actions use tag-based pinning across the workflows:

| Action | Current Pin | File |
|--------|-------------|------|
| `dorny/paths-filter@v3` | tag | `ci.yml`, `e2e-tests.yml` |
| `codecov/codecov-action@v4` | tag | `_backend-tests.yml`, `ci.yml` |
| `docker/setup-buildx-action@v3` | tag | `_docker-build-push.yml`, `ci.yml` |
| `docker/login-action@v3` | tag | `_docker-build-push.yml` |
| `docker/metadata-action@v5` | tag | `_docker-build-push.yml` |
| `docker/build-push-action@v5` | tag | `_docker-build-push.yml`, `ci.yml` |
| `gitleaks/gitleaks-action@v2` | tag | `secret-scan.yml` |
| `zaproxy/action-baseline@v0.12.0` | tag | `owasp-zap.yml` |
| `actions/github-script@v7` | tag | `e2e-tests.yml` |

First-party `actions/*` actions (checkout, cache, upload-artifact, setup-python, setup-node) are also pinned to tags, though they carry lower risk due to GitHub's own supply-chain controls. They should still be pinned to SHAs in a high-security environment.

**Fix**: Pin every third-party action to its full commit SHA. Use `pin-github-action` or `actionlint --format` to automate this. Example:

```yaml
# Before
uses: dorny/paths-filter@v3

# After (SHA as of 2026-03)
uses: dorny/paths-filter@de90cc6415e9cf13c02a7de3e5d9a8a9e32bbb29  # v3.0.2
```

---

### P1-02: `ci.yml` `backend-lint` and `frontend-lint` use `contents: write` — overly broad on PRs from forks

**File**: `.github/workflows/ci.yml` (lines 64–66, 189–190)

```yaml
permissions:
  contents: write
```

**Description**: The lint jobs check out the PR branch and push auto-format commits back. The `contents: write` permission gives these jobs the ability to write to any ref in the repository. For PRs originating from forks, GitHub correctly restricts secrets and write permissions; however, for internal PRs the combination of `contents: write` plus the automatic commit/push creates a workflow-as-committer pattern that bypasses branch protection rules (depending on configuration). An attacker with write access who crafts a lint-fixable PR could coerce the bot into committing attacker-chosen content.

**Fix**: Scope `contents: write` only to the commit step, or use a dedicated PAT with minimal scope. Additionally, add a `CODEOWNERS` check and ensure branch protection requires human review even after bot commits.

```yaml
# Acceptable near-term mitigation: restrict to job-level
backend-lint:
  permissions:
    contents: write   # needed for bot commit only
    pull-requests: read
```

A stronger fix is to separate the format-check job (no write permissions) from the auto-format job, or to use `actions/create-pull-request` to open a child PR for format fixes instead of force-pushing.

---

### P1-03: `code-analysis.yml` installs `claude-flow@latest` at runtime

**File**: `.github/workflows/code-analysis.yml` (line 28)

```yaml
- name: Install claude-flow
  run: npm install -g claude-flow@latest
```

**Description**: Installing a package from npm at `@latest` during a workflow run introduces a supply-chain attack vector. A compromised or typosquatted `claude-flow` package would execute with access to the workflow's environment, including any secrets present in environment variables at that point. The `@latest` tag is mutable and can be updated without notice.

**Fix**: Pin to a specific version. Ideally, also verify the package checksum or use a lock file.

```yaml
run: npm install -g claude-flow@2.0.0  # pin to known-good version
```

Consider moving `claude-flow` to the project's `package.json` devDependencies so it is installed with a lockfile hash via `npm ci` and not fetched fresh on every run.

---

### P1-04: `gitleaks/gitleaks-action@v2` runs on `push` to `main` with full checkout depth — no job-level permissions block

**File**: `.github/workflows/secret-scan.yml` (lines 28–32)

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0

- name: Run gitleaks
  uses: gitleaks/gitleaks-action@v2
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Description**: The workflow itself sets `permissions: {}` at the top level (correct), but `gitleaks-action@v2` is pinned only to a major-version tag, meaning any patch update to the gitleaks action would run with access to `GITHUB_TOKEN`. The `fetch-depth: 0` full history checkout is necessary for a comprehensive scan but means the action has access to the entire commit history. This combination should at minimum be pinned to a specific SHA.

**Fix**: Pin `gitleaks-action` to a SHA digest and add an explicit job-level permissions block:

```yaml
jobs:
  gitleaks:
    permissions:
      contents: read
      security-events: write  # if uploading SARIF
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@<SHA>  # pin to digest
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

### P1-05: `owasp-zap.yml` missing concurrency control

**File**: `.github/workflows/owasp-zap.yml`

```yaml
on:
  schedule:
    - cron: '0 4 * * 0'
  workflow_dispatch: {}
# No concurrency: block
```

**Description**: The OWASP ZAP scan runs on a schedule and can also be triggered manually via `workflow_dispatch`. Without a `concurrency` block, a manual trigger fired while a scheduled run is in progress will spawn a second scanner simultaneously against the production backend at `https://api.rateshift.app`. Parallel ZAP scans against production can cause elevated 429 responses, trigger alerts in Cloudflare's WAF, and inflate false-positive counts in ZAP's report.

**Fix**: Add a concurrency block.

```yaml
concurrency:
  group: owasp-zap
  cancel-in-progress: false  # let running scan finish; queue the next
```

---

### P1-06: `deploy-worker.yml` missing `timeout-minutes` on `test` and `deploy` jobs

**File**: `.github/workflows/deploy-worker.yml` (lines 17–79)

```yaml
jobs:
  test:
    name: Test Worker
    runs-on: ubuntu-latest
    # No timeout-minutes

  deploy:
    name: Deploy to Cloudflare
    runs-on: ubuntu-latest
    # No timeout-minutes
```

**Description**: Both jobs in the Cloudflare Worker deploy workflow have no timeout. A hung `npm ci`, stalled `wrangler deploy`, or an infinite loop in the test suite will consume a GitHub Actions runner for up to the default 6-hour maximum, blocking the `deploy-worker` concurrency group and causing downstream dependency failures. Worker deployments should complete in under 5 minutes.

**Fix**: Add conservative timeouts.

```yaml
test:
  timeout-minutes: 10

deploy:
  timeout-minutes: 10
```

---

### P1-07: `detect-rate-changes.yml` missing `permissions` and `concurrency` blocks

**File**: `.github/workflows/detect-rate-changes.yml`

```yaml
on:
  schedule:
    - cron: '30 6 * * *'
  workflow_dispatch:

jobs:
  detect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
```

**Description**: This is the only cron workflow that is missing both a top-level `permissions: {}` block and a `concurrency` block. All other cron workflows have both. The missing `permissions` block means the workflow inherits the default token permissions (read for most resources, write for `contents` and `packages` depending on repository settings). The missing `concurrency` block allows multiple simultaneous runs if the workflow is triggered while a prior run is still executing.

Additionally, this workflow uses `vars.BACKEND_URL` (a repository variable) while all other cron workflows use `secrets.BACKEND_URL`. This inconsistency may indicate a misconfiguration — the URL should be consistently sourced.

**Fix**:

```yaml
permissions: {}

concurrency:
  group: detect-rate-changes
  cancel-in-progress: false
```

Standardise `BACKEND_URL` access: change `vars.BACKEND_URL` to `secrets.BACKEND_URL` to match every other cron workflow.

---

### P1-08: `fetch-heating-oil.yml` missing `permissions` block and uses inconsistent input key names

**File**: `.github/workflows/fetch-heating-oil.yml`

```yaml
on:
  schedule:
    - cron: '0 14 * * 1'
  workflow_dispatch: {}
# No permissions: block

      - name: Fetch heating oil prices
        uses: ./.github/actions/retry-curl
        with:
          api_key: ${{ secrets.INTERNAL_API_KEY }}  # underscore, not hyphen

      - name: Notify on failure
        uses: ./.github/actions/notify-slack
        with:
          webhook_url: ${{ secrets.SLACK_INCIDENTS_WEBHOOK_URL }}  # underscore
```

**Description**: This workflow is missing a `permissions: {}` block (all other production cron workflows have it). It also passes `api_key` (underscore) and `webhook_url` (underscore) to the composite actions, which define their inputs as `api-key` (hyphen) and `webhook-url` (hyphen). YAML input names in composite actions are case-sensitive and hyphen/underscore are not interchangeable. This means the `X-API-Key` header is silently omitted from retry-curl calls, and the Slack notification may not fire on failure — both silently broken rather than erroring.

**Fix**: Add `permissions: {}` and correct the input key names:

```yaml
permissions: {}

      - name: Fetch heating oil prices
        uses: ./.github/actions/retry-curl
        with:
          url: ${{ secrets.BACKEND_URL }}/api/v1/internal/fetch-heating-oil
          method: POST
          headers: |
            X-API-Key: ${{ secrets.INTERNAL_API_KEY }}
            Content-Type: application/json

      - name: Notify on failure
        uses: ./.github/actions/notify-slack
        with:
          webhook-url: ${{ secrets.SLACK_INCIDENTS_WEBHOOK_URL }}
          workflow-name: "Fetch Petroleum Prices"
          severity: warning
```

---

### P1-09: `e2e-tests.yml` `lighthouse` job has `pull-requests: write` with no scope justification or restriction

**File**: `.github/workflows/e2e-tests.yml` (lines 199–200)

```yaml
lighthouse:
  permissions:
    pull-requests: write
```

**Description**: The `pull-requests: write` permission is granted so the job can post a Lighthouse score comment on PRs. This is a legitimate use, but the permission is granted at the job level with no further restriction. Combined with the `actions/github-script@v7` action (pinned only to a major tag), a supply-chain compromise of `github-script` could exfiltrate PR data or post malicious comments using this elevated permission. The permission should be narrowed and the action should be SHA-pinned.

**Fix**: SHA-pin `actions/github-script` and document why `pull-requests: write` is needed:

```yaml
lighthouse:
  permissions:
    contents: read
    pull-requests: write  # required: posts Lighthouse score comment on PR
  steps:
    - uses: actions/github-script@60a0d83039c74a4aee543508d2ffcb1c3799cdea  # v7.0.1
```

---

## P2 — Medium

### P2-01: `warmup-backend` composite action uses inline expression interpolation in shell

**File**: `.github/actions/warmup-backend/action.yml` (lines 22–31)

```yaml
run: |
  echo "Warming up backend at ${{ inputs.backend-url }}..."
  MAX=${{ inputs.max-attempts }}
  DELAY=${{ inputs.delay-seconds }}
  ...
  "${{ inputs.backend-url }}/api/v1/" 2>/dev/null
```

**Description**: Composite action inputs are expanded by the expression engine before the shell sees the script. If the `backend-url` input ever contained shell metacharacters (backticks, `$(`, `&&`, etc.), the result could be shell injection. For a URL sourced from `secrets.BACKEND_URL` the risk is currently low, but this is an unsafe pattern. All composite actions should pass inputs through environment variables.

**Fix**: Use environment variables in all composite action `run:` steps:

```yaml
runs:
  using: composite
  steps:
    - name: Warmup backend service
      shell: bash
      env:
        BACKEND_URL: ${{ inputs.backend-url }}
        MAX_ATTEMPTS: ${{ inputs.max-attempts }}
        DELAY_SECONDS: ${{ inputs.delay-seconds }}
      run: |
        echo "Warming up backend at ${BACKEND_URL}..."
        MAX=${MAX_ATTEMPTS}
        DELAY=${DELAY_SECONDS}
        while [ $ATTEMPT -lt $MAX ]; do
          ...
          "${BACKEND_URL}/api/v1/" 2>/dev/null
```

The same pattern applies to `wait-for-service/action.yml` (lines 27–31), where `inputs.url`, `inputs.timeout`, `inputs.interval`, and `inputs.expected-status` are all interpolated directly into the shell script.

---

### P2-02: `wait-for-service` composite action uses inline expression interpolation

**File**: `.github/actions/wait-for-service/action.yml` (lines 27–31)

```yaml
run: |
  URL="${{ inputs.url }}"
  TIMEOUT=${{ inputs.timeout }}
  INTERVAL=${{ inputs.interval }}
  EXPECTED=${{ inputs.expected-status }}
```

**Description**: Same injection pattern as P2-01. URL from `secrets.PROD_API_URL` or `secrets.STAGING_API_URL` is interpolated into a shell variable assignment. Mitigate with env-var indirection (see P2-01 fix).

---

### P2-03: `validate-migrations` composite action uses inline expression interpolation

**File**: `.github/actions/validate-migrations/action.yml` (line 22)

```yaml
MIGRATION_DIR="${{ inputs.migration-dir }}"
```

**Description**: Same injection pattern as P2-01 and P2-02. The `migration-dir` input is user-controlled (callers can override the default `backend/migrations`). A malicious caller could inject `; rm -rf /` or similar. In the current codebase, callers always accept the default, but the pattern should be hardened.

**Fix**: Use env-var indirection:

```yaml
env:
  MIGRATION_DIR: ${{ inputs.migration-dir }}
run: |
  if [ ! -d "$MIGRATION_DIR" ]; then
```

---

### P2-04: `e2e-tests.yml` Lighthouse score thresholds use inline `${{ steps.lhci.outputs.* }}` in shell arithmetic

**File**: `.github/workflows/e2e-tests.yml` (lines 340–373)

```yaml
PERF=${{ steps.lhci.outputs.perf_score }}
A11Y=${{ steps.lhci.outputs.a11y_score }}
```

**Description**: Output values from a prior step are interpolated directly into shell arithmetic. A malicious or corrupted `lhci` run could set an output like `perf_score` to `100; malicious_command`. Although the expression engine processes this before the shell, the resulting bash code is `PERF=100; malicious_command`, which would execute. Lighthouse CI outputs are unlikely to be attacker-controlled in practice, but the pattern is dangerous for any step whose outputs come from external tool invocations.

**Fix**: Use environment variables:

```yaml
env:
  PERF: ${{ steps.lhci.outputs.perf_score }}
  A11Y: ${{ steps.lhci.outputs.a11y_score }}
  BP: ${{ steps.lhci.outputs.bp_score }}
  SEO: ${{ steps.lhci.outputs.seo_score }}
run: |
  if [ "${PERF}" -lt 85 ]; then
```

---

### P2-05: `ci.yml` and `e2e-tests.yml` checkout uses `github.head_ref` without sanitization

**File**: `.github/workflows/ci.yml` (line 70)

```yaml
ref: ${{ github.event_name == 'pull_request' && github.head_ref || github.ref }}
```

**Description**: `github.head_ref` contains the source branch name of a pull request, which is attacker-controlled for PRs from forks or from any branch with unconventional names. While `actions/checkout@v4` handles this safely when it resolves the ref, the pattern of using `github.head_ref` directly in expressions is flagged by static analysis tools (actionlint, StepSecurity) and can lead to injection if the value is later used in shell contexts. The `token: ${{ github.token }}` also grants the checkout write capability.

**Fix**: For the ref parameter specifically, using `github.head_ref` in `actions/checkout` is acceptable because checkout resolves it as a git ref. The more important fix is to ensure this value never flows into a `run:` shell step. Add a comment to document the intentional use:

```yaml
- uses: actions/checkout@v4
  with:
    # github.head_ref is safe here: only consumed by git, not by shell
    ref: ${{ github.event_name == 'pull_request' && github.head_ref || github.ref }}
    token: ${{ github.token }}
```

---

### P2-06: `self-healing-monitor.yml` exposes `GH_TOKEN` as a top-level `env` variable

**File**: `.github/workflows/self-healing-monitor.yml` (lines 17–18)

```yaml
env:
  GH_TOKEN: ${{ github.token }}
```

**Description**: Setting `GH_TOKEN` at the workflow `env` level makes the token available to every step of every job, including any third-party actions used in the workflow. In this case only the checkout action is used, but the pattern is an over-exposure. The `gh` CLI automatically uses `GH_TOKEN` if set, meaning any step that invokes `gh` inherits the token. Prefer setting the token only at the step or job level where it is needed.

**Fix**: Remove the top-level `env` block and set the token only where needed:

```yaml
# Remove top-level env: GH_TOKEN

# In each step that uses gh CLI:
- name: Count recent failures
  env:
    GH_TOKEN: ${{ github.token }}
  run: |
    gh run list ...
```

---

### P2-07: `model-retrain.yml` sets `ENVIRONMENT: production` in a runner context

**File**: `.github/workflows/model-retrain.yml` (lines 31–32)

```yaml
env:
  ENVIRONMENT: production
```

**Description**: The model retraining job sets `ENVIRONMENT=production` even though it runs on a GitHub Actions runner with no connection to the production database. The training script currently validates the pipeline without real data, but the `production` flag could activate different code paths in imported modules (e.g., different logging, error handling, or external API calls) that are not intended for the CI runner context. This creates a confusing dual environment state.

**Fix**: Use `ENVIRONMENT: ci` or remove the variable if not needed. If the model code requires a recognised environment name, add a `training` or `ci` option.

```yaml
env:
  ENVIRONMENT: ci
```

---

### P2-08: `code-analysis.yml` `security scan` step does not have `continue-on-error` but uses `||` to suppress non-zero exits inconsistently

**File**: `.github/workflows/code-analysis.yml` (lines 49–52)

```yaml
- name: Security scan
  run: |
    claude-flow security scan --format json > security.json
    echo "## Security Scan" >> $GITHUB_STEP_SUMMARY
    cat security.json >> $GITHUB_STEP_SUMMARY || echo "No security report generated" >> $GITHUB_STEP_SUMMARY
```

**Description**: The `claude-flow security scan` command does not have `|| true` appended, meaning a non-zero exit from the scan (e.g., CLI crash, network error) will fail the entire job. The subsequent `cat` command has `|| echo` to suppress its own errors, creating an inconsistent pattern. The job is used in PR checks against `main`, so a claude-flow CLI crash blocks all PRs.

**Fix**: Add `|| true` to the scan command or add `continue-on-error: true` to the step, and explicitly check results in the next step (which already exists):

```yaml
- name: Security scan
  run: |
    claude-flow security scan --format json > security.json || true
    echo "## Security Scan" >> $GITHUB_STEP_SUMMARY
    cat security.json >> $GITHUB_STEP_SUMMARY || echo "No security report generated" >> $GITHUB_STEP_SUMMARY
```

---

### P2-09: `deploy-production.yml` rollback step unconditionally sleeps 120 seconds

**File**: `.github/workflows/deploy-production.yml` (lines 246–249)

```yaml
- name: Wait for rollback to propagate
  run: |
    echo "Waiting 120 s for Render to complete rollback deploys..."
    sleep 120
```

**Description**: The rollback job unconditionally sleeps for 120 seconds before checking health. The subsequent health check step already implements its own retry loop with 15-second intervals across 10 attempts (150 seconds maximum). The unconditional sleep adds 2 minutes of dead time to every rollback, increasing the mean time to recovery (MTTR). Render rollbacks for small services typically complete in 30–60 seconds.

**Fix**: Remove the sleep step and rely entirely on the health-check retry loop, or reduce the initial sleep to 30 seconds:

```yaml
- name: Wait for rollback to propagate
  run: |
    echo "Waiting 30s initial propagation delay..."
    sleep 30
```

---

### P2-10: `deploy-production.yml` smoke test waits for backend but never waits for CF Worker

**File**: `.github/workflows/deploy-production.yml` (lines 142–171)

**Description**: The production smoke tests wait for `${{ secrets.PROD_API_URL }}/health` (the Render backend directly) and test `/api/v1/prices/current` (also Render). The Cloudflare Worker at `api.rateshift.app` — which is the actual user-facing entry point — is not verified after a Render deploy. A broken Cloudflare Worker cache or routing configuration would not be caught by these smoke tests, even though the Worker is tested in a separate `deploy-worker.yml`. A post-deploy smoke test should verify the production domain, not just the origin.

**Fix**: Add a smoke test step against the CF Worker endpoint:

```yaml
- name: Verify CF Worker (user-facing endpoint)
  uses: ./.github/actions/retry-curl
  with:
    url: https://api.rateshift.app/health
    method: GET
    max-retries: 3
    initial-delay: 10
```

---

### P2-11: `e2e-tests.yml` `security-tests` job not included in `notify-failure` `needs`

**File**: `.github/workflows/e2e-tests.yml` (lines 590–593)

```yaml
notify-failure:
  needs: [e2e-tests, lighthouse, security-tests]
  if: failure()
```

Actually the `security-tests` job IS included — but the `load-tests` job is not:

```yaml
# load-tests job (lines 462–522) has no failure notification path
load-tests:
  name: Load Tests (On Demand)
  runs-on: ubuntu-latest
  # Not included in notify-failure needs
```

**Description**: The `load-tests` job runs on `workflow_dispatch` or when a `load-test` label is applied to a PR. If it fails, there is no Slack notification and no way to be alerted other than checking the GitHub Actions UI. For a production SaaS, load test failures should be routed to the incidents channel.

**Fix**: Add `load-tests` to the `notify-failure` job's `needs` and use `if: failure()`:

```yaml
notify-failure:
  needs: [e2e-tests, lighthouse, security-tests, load-tests]
  if: failure()
```

---

### P2-12: `secret-scan.yml` does not have a `timeout-minutes` on the `gitleaks` job

**File**: `.github/workflows/secret-scan.yml`

```yaml
jobs:
  gitleaks:
    name: Gitleaks Secret Scan
    runs-on: ubuntu-latest
    timeout-minutes: 10  # ← PRESENT — this finding is a false alarm
```

Actually `timeout-minutes: 10` is present. See P2-13 instead.

---

### P2-12 (corrected): `fetch-heating-oil.yml` checkout fetches full tree, not sparse

**File**: `.github/workflows/fetch-heating-oil.yml` (line 17)

```yaml
- uses: actions/checkout@v4
  # No sparse-checkout: .github/actions
```

**Description**: Unlike all other cron workflows in the repository that only need local composite actions, `fetch-heating-oil.yml` does a full repository checkout instead of a sparse checkout scoped to `.github/actions`. This downloads the entire codebase (backend, frontend, ML code, migrations, etc.) unnecessarily on every weekly run, wasting runner time (~30–60 seconds) and bandwidth.

**Fix**: Use sparse checkout:

```yaml
- uses: actions/checkout@v4
  with:
    sparse-checkout: .github/actions
```

---

### P2-13: `owasp-zap.yml` does not have a failure notification

**File**: `.github/workflows/owasp-zap.yml`

```yaml
jobs:
  zap-scan:
    steps:
      - uses: zaproxy/action-baseline@v0.12.0
        with:
          fail_action: true
      # No notify-slack step on failure
```

**Description**: `fail_action: true` will cause the job to fail if ZAP finds issues above the configured threshold, but there is no Slack notification step for failures. The scan runs on Sunday at 4am UTC — a time when no one is monitoring the Actions UI. Security scan failures will silently sit in the GitHub Actions history until someone checks manually. Every other scheduled workflow in this repository sends a Slack alert on failure.

**Fix**: Add a failure notification job:

```yaml
  notify-failure:
    name: Notify ZAP Failure
    runs-on: ubuntu-latest
    needs: [zap-scan]
    if: failure()
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
        with:
          sparse-checkout: .github/actions
      - uses: ./.github/actions/notify-slack
        with:
          webhook-url: ${{ secrets.SLACK_INCIDENTS_WEBHOOK_URL }}
          workflow-name: "OWASP ZAP Baseline Scan"
          severity: critical
```

---

### P2-14: `deploy-staging.yml` staging URL in `environment.url` points to production domain

**File**: `.github/workflows/deploy-staging.yml` (line 72)

```yaml
environment:
  name: staging
  url: https://rateshift.app
```

**Description**: The staging deployment environment is configured to display `https://rateshift.app` as its URL, which is the production domain. GitHub displays this URL on the deployment status page and in PR checks. Engineers clicking the link from a staging deployment will land on production rather than staging. This can cause confusion during validation ("why does the PR look deployed but nothing has changed?") and may result in production being used for staging acceptance testing.

**Fix**: Use the staging URL variable:

```yaml
environment:
  name: staging
  url: ${{ vars.STAGING_FRONTEND_URL || 'https://staging.rateshift.app' }}
```

---

## P3 — Low

### P3-01: `ci.yml` `notify-failure` job checks out full repo just for the `notify-slack` action

**File**: `.github/workflows/ci.yml` (lines 436–438)

```yaml
- uses: actions/checkout@v4
  with:
    sparse-checkout: .github/actions
```

**Description**: The `sparse-checkout: .github/actions` pattern is used correctly and consistently to minimise checkout time. This is best practice and is noted here only because some cron workflows (e.g., `fetch-heating-oil.yml`, `detect-rate-changes.yml`) do a full checkout instead. No action required for `ci.yml` itself.

---

### P3-02: `_backend-tests.yml` uses hardcoded test credentials as plaintext env vars

**File**: `.github/workflows/_backend-tests.yml` (lines 72–78)

```yaml
env:
  JWT_SECRET: test_secret_key_for_ci_minimum_32_chars
  FLATPEAK_API_KEY: test_key
  NREL_API_KEY: test_key
  IEA_API_KEY: test_key
```

**Description**: These are deliberately dummy values used only for testing and have no production equivalents. This is standard practice. They are flagged here because secret-scanning tools (including gitleaks) may alert on values matching patterns for JWTs, API keys, etc. The `test_key` values should be clearly prefixed to allow easy suppression in scanner rules.

**Fix**: Consider using values that are clearly non-functional and match a suppression pattern already configured in `.gitleaks.toml` (if one exists):

```yaml
JWT_SECRET: ci-only-not-a-real-secret-do-not-use-in-prod
FLATPEAK_API_KEY: ci-placeholder-flatpeak
NREL_API_KEY: ci-placeholder-nrel
IEA_API_KEY: ci-placeholder-iea
```

---

### P3-03: `nightly-learning.yml` and `observe-forecasts.yml` have no warmup step for the Render backend

**Files**: `.github/workflows/nightly-learning.yml`, `.github/workflows/observe-forecasts.yml`

**Description**: Several cron workflows use the `warmup-backend` composite action to wake Render from cold-sleep before making internal API calls. However, `nightly-learning.yml` and `observe-forecasts.yml` call the internal API directly via `retry-curl` without first warming up the backend. On Render's free/starter tier, a cold start can take 30–60 seconds; the retry-curl default timeout of 120 seconds should cover this, but the first request will likely time out and consume one retry. This is a reliability concern rather than a security issue.

**Fix**: Add the `warmup-backend` step before the `retry-curl` step in both workflows, consistent with `check-alerts.yml`, `dunning-cycle.yml`, `kpi-report.yml`, etc.

---

### P3-04: `model-retrain.yml` installs ML requirements with `|| true`, silently swallowing errors

**File**: `.github/workflows/model-retrain.yml` (line 27)

```yaml
- name: Install ML dependencies
  run: pip install -r ml/requirements.txt 2>/dev/null || true
```

**Description**: The `|| true` means a failed pip install (broken dependency, network error, version conflict) is silently ignored. The subsequent Python script may then fail with an `ImportError` at the wrong point, producing a confusing error message that does not indicate the true root cause (dependency installation failure).

**Fix**: Remove `|| true` or use `continue-on-error: true` with explicit result checking:

```yaml
- name: Install ML dependencies
  run: pip install -r ml/requirements.txt
  continue-on-error: true
  id: install-deps

- name: Warn on missing deps
  if: steps.install-deps.outcome == 'failure'
  run: echo "::warning::ML dependency install failed — model validation may be incomplete"
```

---

### P3-05: `e2e-tests.yml` `load-tests` job missing service health checks on postgres/redis

**File**: `.github/workflows/e2e-tests.yml` (lines 466–480)

```yaml
services:
  postgres:
    image: postgres:15-alpine
    # No options: --health-cmd block

  redis:
    image: redis:7-alpine
    # No options: --health-cmd block
```

**Description**: The `e2e-tests` job's main services have health check options, but the `load-tests` job's service containers omit the `options: --health-cmd` blocks. Without health checks, the first step can start before the database is ready, causing intermittent failures. The `e2e-tests` job's own services correctly configure health checks.

**Fix**: Add health check options to both service containers in the `load-tests` job, matching the pattern from the `e2e-tests` job.

---

### P3-06: `deploy-worker.yml` hardcodes `https://api.rateshift.app/health` in smoke test

**File**: `.github/workflows/deploy-worker.yml` (line 74)

```yaml
STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://api.rateshift.app/health)
```

**Description**: The production domain is hardcoded in the smoke test rather than coming from a variable or secret. While `rateshift.app` is unlikely to change, this is inconsistent with all other workflows that reference the domain via `secrets.PROD_API_URL` or `secrets.BACKEND_URL`. A domain migration or a staging environment test would require editing the workflow file rather than just updating a secret or variable.

**Fix**: Use the secret consistently:

```yaml
env:
  PROD_API_URL: ${{ secrets.PROD_API_URL }}
run: |
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${PROD_API_URL}/health")
```

---

### P3-07: `self-healing-monitor.yml` matrix step `uses: actions/checkout@v4` is conditional and runs after non-checkout steps

**File**: `.github/workflows/self-healing-monitor.yml` (lines 115–119)

```yaml
- uses: actions/checkout@v4
  if: steps.count.outputs.failures >= env.FAILURE_THRESHOLD && steps.existing.outputs.issue == ''
  with:
    sparse-checkout: .github/actions

- name: Notify Slack on new issues
  if: steps.count.outputs.failures >= env.FAILURE_THRESHOLD && steps.existing.outputs.issue == ''
  uses: ./.github/actions/notify-slack
```

**Description**: The checkout step is placed after the `gh issue create` step rather than at the beginning of the job. This is a structural issue: if the Notify Slack step runs before the checkout step that makes the local action available, the `uses: ./.github/actions/notify-slack` will fail because the composite action definition file does not exist in the workspace. In practice, the `actions/checkout@v4` step occurs just before the notify step in the same conditional block, so the ordering is correct — but it is fragile. Adding any step between checkout and notify could break it.

**Fix**: Move the checkout step to the beginning of the job (unconditionally), scoped to `.github/actions`:

```yaml
steps:
  - uses: actions/checkout@v4
    with:
      sparse-checkout: .github/actions

  - name: Count recent failures
    ...
```

---

### P3-08: Inconsistent `cancel-in-progress` semantics across cron workflows

**Files**: `scan-emails.yml` (line 13), `scrape-portals.yml` (line 14) vs. all others

```yaml
# scan-emails.yml and scrape-portals.yml
concurrency:
  cancel-in-progress: true   # ← cancels overlapping runs

# All other cron workflows
concurrency:
  cancel-in-progress: false  # ← queues overlapping runs
```

**Description**: The choice of `cancel-in-progress: true` vs. `false` has different semantics. For `scan-emails.yml` (daily at 4am) and `scrape-portals.yml` (weekly Sunday), cancelling an in-progress run if a newer one fires means incomplete email scans or portal scrapes — potentially missing data for users. The rationale for `cancel-in-progress: true` on these two workflows is unclear and inconsistent with the rest of the cron fleet.

For comparison: `check-alerts.yml` (every 30 minutes) and `sync-connections.yml` (every 2 hours) use `cancel-in-progress: false`, which is the correct behaviour for idempotent data-fetch operations.

**Fix**: Change both to `cancel-in-progress: false` unless there is a deliberate reason to prefer cancellation over queuing, and document it with a comment:

```yaml
concurrency:
  group: scan-emails
  cancel-in-progress: false  # complete each scan before starting the next
```

---

## Appendix: Items Verified as Correctly Implemented

The following were specifically checked and found to be correctly implemented:

- **Secrets are never printed**: No workflow contains `echo ${{ secrets.* }}` or equivalent patterns that would expose secret values in logs.
- **INTERNAL_API_KEY passed via header, not URL**: All internal API calls use `X-API-Key` HTTP header, never query string parameters.
- **retry-curl uses environment variables**: The `retry-curl` composite action correctly passes all inputs through environment variables before using them in shell, avoiding injection.
- **Concurrency groups on all push/PR workflows**: `ci.yml`, `e2e-tests.yml`, `code-analysis.yml`, `secret-scan.yml`, `utility-type-tests.yml` all have `concurrency` blocks with `cancel-in-progress: true`.
- **Production deploy requires environment approval**: `deploy-production.yml` uses `environment: name: production` which can be configured to require manual approval in GitHub Environments settings.
- **Migration gate before deploy**: `deploy-production.yml` gates the deploy job on the `migration-gate` job, preventing deploys with malformed SQL.
- **Bandit runs at `--severity-level high`**: Only high-severity Bandit findings block the build; low/medium issues emit warnings without failing CI.
- **pip-audit runs with `--strict`**: Dependency audit in `_backend-tests.yml` uses `--strict --desc` and fails on any known vulnerability.
- **npm audit at `--audit-level=high`**: Frontend audit correctly targets high and critical severity, not just critical.
- **No workflow uses `--no-verify`** on git operations.
- **No `workflow_run` triggers on untrusted inputs**: No workflow uses `workflow_run` events without permission checks.
- **Docker images scanned by Trivy**: `_docker-build-push.yml` runs `aquasecurity/trivy-action@0.28.0` (tagged, though not SHA-pinned — covered under P1-01) after push.
