# Scripts & E2E Audit — 2026-03-16

**Auditor:** test-automator (Claude Sonnet 4.6)
**Scope:** `scripts/` (22 files), `frontend/e2e/` (17 spec files), `.github/actions/` (7 composite actions)

---

## Summary

| Severity | Scripts | E2E | Actions | Total |
|----------|---------|-----|---------|-------|
| P0 (Critical) | 4 | 0 | 0 | 4 |
| P1 (High) | 8 | 3 | 2 | 13 |
| P2 (Medium) | 9 | 7 | 2 | 18 |
| P3 (Low) | 5 | 5 | 1 | 11 |
| **Total** | **26** | **15** | **5** | **46** |

---

## Scripts Findings

### P0 — Critical

---

**SCRIPTS-P0-001**
**File:** `scripts/backup.sh`
**Line:** 85
**Title:** Migration script silently swallows psql errors with `|| true`

```bash
PGPASSWORD="${POSTGRES_PASSWORD}" psql -h postgres -U postgres -d electricity -f "$migration" 2>&1 || true
```

**Description:** The `|| true` suppresses all psql exit codes. A failed migration — corrupt SQL, duplicate table, wrong permissions — produces no error, no non-zero exit, and the script logs "Migrations completed successfully!" regardless. A partially applied migration leaves the database in an inconsistent state with no alert raised. This is in `docker-entrypoint.sh` line 85, not backup.sh — same pattern in both.

**Fix:** Remove `|| true`. Capture return code explicitly and fail the entrypoint if any migration fails:

```bash
if ! PGPASSWORD="${POSTGRES_PASSWORD}" psql -h postgres -U postgres -d electricity -f "$migration" 2>&1; then
    log_error "Migration failed: $(basename "$migration"). Aborting startup."
    exit 1
fi
```

---

**SCRIPTS-P0-002**
**File:** `scripts/backup.sh`
**Lines:** 56, 83
**Title:** `.env` sourced inside backup and entrypoint scripts — credential leakage and injection risk

```bash
source "$(dirname "$0")/../.env" 2>/dev/null || true
```

**Description:** Sourcing `.env` directly in a script running in a Docker container or CI context means arbitrary shell code in `.env` executes with the script's privileges. The `2>/dev/null || true` swallows all errors, so a missing or malformed `.env` passes silently. In `backup.sh` the sourced `REDIS_PASSWORD` is then passed as a CLI argument (`-a "$REDIS_PASSWORD"`), which exposes the credential in the process list visible via `ps aux` on multi-tenant hosts. Additionally, credentials loaded this way are not scrubbed from the environment after use.

**Fix:** Pass credentials through environment variables set by Docker/orchestration rather than sourcing `.env`. Use `--pass-stdin` for redis-cli passwords:

```bash
echo "$REDIS_PASSWORD" | redis-cli -h redis --no-auth-warning -p 6379 --stdin BGSAVE
```

---

**SCRIPTS-P0-003**
**File:** `scripts/docker-entrypoint.sh`
**Line:** 85
**Title:** Migration runner has no atomicity — partial migration leaves database corrupted

**Description:** `run_migrations()` iterates over SQL files and executes each with `|| true`. If migration 010 fails mid-execution after 009 succeeded, the next container restart re-attempts all migrations including 009 again (no applied-migration tracking table). The `IF NOT EXISTS` convention partially protects table creation but does not protect data migrations, index changes, or `ALTER TABLE` statements. There is no rollback mechanism.

**Fix:** Add a `schema_migrations` tracking table and wrap each migration in a transaction:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ DEFAULT now()
);
```

Check `SELECT 1 FROM schema_migrations WHERE version = $filename` before applying each file.

---

**SCRIPTS-P0-004**
**File:** `scripts/production-deploy.sh`
**Lines:** 74–79
**Title:** Production deploy script uses system `python3` not `.venv`, breaking test isolation

```bash
cd backend
python3 -m pytest --tb=short -q 2>/dev/null
```

**Description:** The CLAUDE.md critical reminder explicitly states "Always use `.venv/bin/python -m pytest`, never system Python." The production deploy script uses system `python3` which may resolve to a different interpreter than the one used by CI. If the system Python lacks project dependencies, pytest will silently collect zero tests (the `2>/dev/null` hides this) and the script logs "Backend tests passed" — deploying untested code to production. The `2>/dev/null` suppression is the root amplifier.

**Fix:** Replace all test invocations in `production-deploy.sh` and restore stderr:

```bash
cd "$PROJECT_DIR/backend"
"$PROJECT_DIR/.venv/bin/python" -m pytest --tb=short -q
```

Remove `2>/dev/null` from all test runner calls in this script.

---

### P1 — High

---

**SCRIPTS-P1-001**
**File:** `scripts/backup.sh`
**Line:** 89
**Title:** Redis BGSAVE uses fixed 5-second sleep — race condition on large datasets

```bash
sleep 5
docker cp redis:/data/dump.rdb "$backup_file"
```

**Description:** BGSAVE is asynchronous. The 5-second sleep is a guess. On a Redis instance with a large dataset or high write rate, the background save may not complete in 5 seconds, resulting in a partial or zero-byte backup being copied and verified as "successful" because `[ -f "$backup_file" ]` only checks existence, not RDB completeness.

**Fix:** Poll `BGSAVE` status until `LASTSAVE` changes or `BGSAVE` reports completion:

```bash
BEFORE=$(docker exec redis redis-cli LASTSAVE)
docker exec redis redis-cli -a "$REDIS_PASSWORD" BGSAVE
for _ in $(seq 1 30); do
    sleep 2
    AFTER=$(docker exec redis redis-cli LASTSAVE)
    [ "$AFTER" != "$BEFORE" ] && break
done
docker cp redis:/data/dump.rdb "$backup_file"
```

---

**SCRIPTS-P1-002**
**File:** `scripts/deploy.sh`
**Line:** 107
**Title:** ML tests run with `cd ml && python -m pytest` — system Python, no error handling for directory change failure

```bash
cd ml && python -m pytest -q && cd ..
```

**Description:** If `cd ml` fails (directory does not exist), the `&&` chain stops but `set -e` does not trigger because `cd` failure in a `&&` chain is treated as a conditional, not a pipeline error in some shells. The use of `cd ..` to return is fragile — if `python -m pytest` changes the working directory the script silently continues from the wrong location. Additionally, system `python` is used instead of `.venv/bin/python`.

**Fix:**

```bash
(cd "$PROJECT_DIR/ml" && "$PROJECT_DIR/.venv/bin/python" -m pytest -q) || {
    log_error "ML tests failed"
    exit 1
}
```

---

**SCRIPTS-P1-003**
**File:** `scripts/loki-feature.sh`
**Lines:** 262–288
**Title:** `--dangerously-skip-permissions` flag passed to Claude CLI without user acknowledgment

```bash
echo "$prompt" | claude --dangerously-skip-permissions 2>>"$LOG_FILE" || {
```

**Description:** The Loki pipeline passes `--dangerously-skip-permissions` to every Claude invocation unconditionally. This flag bypasses tool-use permission prompts. When the pipeline runs autonomously (not under direct human supervision), Claude can execute arbitrary shell commands, write files, make git commits, and push branches without any confirmation gate. Combined with the `|| { log "non-zero (may be partial success)" }` error suppression, a failed or misbehaving Claude invocation continues the pipeline to the PR creation stage.

**Fix:** Remove `--dangerously-skip-permissions` from automated invocations. Require explicit `--dry-run` confirmation before any autonomous pipeline execution. Add a `--require-approval` flag that pauses before each RARV cycle ACT phase.

---

**SCRIPTS-P1-004**
**File:** `scripts/loki-feature.sh`
**Line:** 201**
**Title:** Branch name injection from PRD title — shell injection risk

```bash
branch_name="loki/$(echo "$title" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd 'a-z0-9-' | head -c 50)"
git -C "$PROJECT_DIR" checkout -b "$branch_name"
```

**Description:** `$title` comes from a JSON file generated by parsing a PRD file. If a PRD file contains a crafted title (e.g., `'; rm -rf /;'`), the `tr` chain does strip most dangerous chars but the `head -c 50` and the unquoted interpolation into `git checkout -b` could still produce unexpected branch names on edge inputs. More critically, the `title` extraction via `python3 -c "..."` inline embeds the raw value into a shell string without escaping.

**Fix:** Validate `branch_name` with an allowlist regex before use:

```bash
if ! [[ "$branch_name" =~ ^loki/[a-z0-9-]{1,50}$ ]]; then
    log "Error: derived branch name '$branch_name' is invalid"
    exit 1
fi
```

---

**SCRIPTS-P1-005**
**File:** `scripts/run_migrations_007_019.py`
**Lines:** 170–183
**Title:** Leaked connection reference `temp_conn` used after potential exception before close

```python
try:
    temp_conn = await asyncpg.connect(self.database_url)
    await temp_conn.execute(stmt)
    await temp_conn.close()
except asyncpg.exceptions.DuplicateObjectError:
    ...
    if temp_conn and not temp_conn.is_closed():
        await temp_conn.close()
except Exception as e:
    ...
    if temp_conn and not temp_conn.is_closed():
        await temp_conn.close()
    else:
        raise
```

**Description:** `temp_conn` is referenced in exception handlers before it is guaranteed to be bound. If `asyncpg.connect()` itself raises (e.g., connection refused, authentication failure), `temp_conn` is an unbound name and the `NameError` in the exception handler masks the original connection error. This leaves a dangling connection leak path.

**Fix:** Initialize to `None` before the try block and use a `finally` clause:

```python
temp_conn = None
try:
    temp_conn = await asyncpg.connect(self.database_url)
    await temp_conn.execute(stmt)
finally:
    if temp_conn and not temp_conn.is_closed():
        await temp_conn.close()
```

---

**SCRIPTS-P1-006**
**File:** `scripts/verification-loop-full.sh`
**Line:** 8
**Title:** Missing `set -e` — script continues on phase failures and produces misleading truth score

```bash
set -uo pipefail
```

**Description:** `set -uo pipefail` is present but `set -e` is absent. Each phase is manually gated with `pass_phase`/`fail_phase`, which is correct, but unguarded subshell commands (e.g., `bc` for truth score calculation, `git status`) that fail will silently continue. More critically, if `bc` is not installed, `truth_score` becomes empty, the comparison `[[ "$truth_score" != "1.00" ]]` evaluates unexpectedly, and the log append to `$PI_FAILURES` never fires — the quality gate appears to pass silently.

**Fix:** Add `set -e` and guard `bc` usage:

```bash
set -euo pipefail
...
if command -v bc &>/dev/null; then
    truth_score=$(echo "scale=2; $weighted_score / $total_weight" | bc)
else
    truth_score="0.00"
    log "WARN: bc not installed — truth score defaulting to 0.00"
fi
```

---

**SCRIPTS-P1-007**
**File:** `scripts/project-intelligence-sync.sh`
**Line:** 10
**Title:** Hardcoded absolute path — script non-portable and will fail in any other checkout location

```bash
REPO_ROOT="/Users/devinmcgrath/projects/electricity-optimizer"
```

**Description:** The repository root is hardcoded to a developer's local machine path. Any other developer or CI runner that checks out the repo to a different path will silently create symlinks and directory structures pointing at non-existent locations. The script is also referenced from the CLAUDE.md session initialization, meaning session initialization will silently fail on any machine that is not Devin's.

**Fix:** Derive the repo root dynamically:

```bash
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
```

---

**SCRIPTS-P1-008**
**File:** `scripts/dsp_bootstrap.py`
**Line:** 9
**Title:** Hardcoded absolute path to project root — same machine-specific breakage pattern

```python
ROOT = "/Users/devinmcgrath/projects/electricity-optimizer"
```

**Description:** Same issue as SCRIPTS-P1-007. Every path in this script — the CLI reference, all file registrations, all UID lookups — is built from this hardcoded constant. The script fails completely on any other machine or CI runner. Unlike `dsp_auto_bootstrap.py` which correctly uses `Path(__file__).resolve().parent.parent`, this original bootstrap file was never updated.

**Fix:**

```python
ROOT = str(Path(__file__).resolve().parent.parent)
```

---

### P2 — Medium

---

**SCRIPTS-P2-001**
**File:** `scripts/backup.sh`
**Line:** 189
**Title:** Glob in `ls` expands to error if no files exist — unguarded brace expansion

```bash
ls -lh "$BACKUP_DIR"/*.{sql.gz,rdb} 2>/dev/null | tail -10
```

**Description:** Brace expansion `*.{sql.gz,rdb}` produces two glob patterns. If neither matches any files in `$BACKUP_DIR`, `ls` exits with status 2 (suppressed by `2>/dev/null`) but the pipeline still proceeds. On some shells and locales this produces a literal `*.sql.gz *.rdb` argument to ls. This is a cosmetic issue but demonstrates a pattern of suppressing errors rather than handling them.

**Fix:** Use two separate `ls` calls with null guards, or use `find`.

---

**SCRIPTS-P2-002**
**File:** `scripts/deploy.sh`
**Line:** 139
**Title:** Fixed 30-second sleep for service readiness — not health-driven

```bash
sleep 30
```

**Description:** After `docker compose up -d`, the script waits exactly 30 seconds before running health checks. Depending on the host machine speed, image pull time, and database initialization, 30 seconds may be too short (services not ready, health check fails) or wasteful (services up in 5 seconds). There is no exponential backoff or readiness polling.

**Fix:** Use the `wait-for-service` composite action already present in `.github/actions/wait-for-service/`, or implement a poll loop:

```bash
for i in $(seq 1 30); do
    docker compose exec backend curl -sf http://localhost:8000/health/live && break
    sleep 2
done
```

---

**SCRIPTS-P2-003**
**File:** `scripts/restore.sh`
**Lines:** 53–56
**Title:** Database dropped and recreated without backup of current state before restore

```bash
docker exec postgres psql -U postgres -c "DROP DATABASE IF EXISTS electricity;"
docker exec postgres psql -U postgres -c "CREATE DATABASE electricity;"
```

**Description:** The restore script drops the live database immediately after the user confirms "yes." There is no automatic snapshot of the current database state before destruction. If the restoration fails mid-way (e.g., the backup file is corrupt), data is permanently lost. The only pre-restore prompt is a generic "This will overwrite existing data" warning.

**Fix:** Before dropping the database, create a quick pg_dump snapshot:

```bash
pre_restore_backup="$BACKUP_DIR/pre_restore_$(date +%Y%m%d_%H%M%S).sql.gz"
docker exec postgres pg_dump -U postgres -d electricity --no-owner | gzip > "$pre_restore_backup"
log_info "Pre-restore snapshot created: $pre_restore_backup"
```

---

**SCRIPTS-P2-004**
**File:** `scripts/loki-verify.sh`
**Lines:** 92–98
**Title:** Frontend test output parsing is fragile — `grep -oE` extracts same pattern for both count and suite count

```bash
count=$(echo "$output" | grep -oE '[0-9]+ passed' | head -1 | grep -oE '[0-9]+' || echo "0")
suites=$(echo "$output" | grep -oE '[0-9]+ passed' | tail -1 | grep -oE '[0-9]+' || echo "0")
```

**Description:** Jest's output format changes between versions, and the "N passed" pattern can appear multiple times in the output (once for tests, once for test suites, or not at all in `--silent` mode). When `--silent` is used, Jest suppresses test result output and `count` and `suites` will both be `"0"` even on a successful run. The event payload will contain incorrect counts. More critically, the `|| echo "0"` means a complete test runner failure (non-zero exit from `grep`) is indistinguishable from zero tests found.

**Fix:** Parse Jest's JSON output using `--json`:

```bash
output=$(cd "$PROJECT_DIR/frontend" && npx jest --json 2>/dev/null)
count=$(echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['numPassedTests'])" 2>/dev/null || echo "0")
```

---

**SCRIPTS-P2-005**
**File:** `scripts/loki-feature.sh`
**Lines:** 248–253
**Title:** In-line Python modifies JSON state file without atomic write — data corruption risk on interruption

```python
python3 -c "
import json
d = json.load(open('$TASKS_FILE'))
d['tasks'][$i]['status'] = 'in_progress'
json.dump(d, open('$TASKS_FILE', 'w'), indent=2)
"
```

**Description:** The state file is opened for writing immediately after reading. If the script is interrupted (SIGTERM, Ctrl-C, host crash) between `open('$TASKS_FILE', 'w')` truncating the file and `json.dump()` completing the write, the tasks file becomes an empty or partial JSON document. The `--resume` flag would then fail with a JSON parse error.

**Fix:** Write to a temp file and atomically rename:

```python
import json, os, tempfile
d = json.load(open('$TASKS_FILE'))
d['tasks'][$i]['status'] = 'in_progress'
tmp = '$TASKS_FILE' + '.tmp'
with open(tmp, 'w') as f:
    json.dump(d, f, indent=2)
os.replace(tmp, '$TASKS_FILE')
```

---

**SCRIPTS-P2-006**
**File:** `scripts/notion_hub_setup.py`
**Lines:** 30–38 (inferred from preview)**
**Title:** API key loaded from plaintext file at `~/.config/notion/api_key` — no fallback to env var

```python
API_KEY_PATH = os.path.expanduser("~/.config/notion/api_key")

def get_api_key() -> str:
    with open(API_KEY_PATH) as f:
        return f.read().strip()
```

**Description:** The script reads the Notion API key from a plaintext file rather than from an environment variable or the project's established 1Password vault. There is no fallback to `NOTION_API_KEY` env var. If the file does not exist the script raises an unhandled `FileNotFoundError` with no user-friendly error message. The plaintext file path is also not documented in the CLAUDE.md credentials inventory.

**Fix:**

```python
def get_api_key() -> str:
    key = os.environ.get("NOTION_API_KEY")
    if key:
        return key
    if os.path.exists(API_KEY_PATH):
        with open(API_KEY_PATH) as f:
            return f.read().strip()
    raise SystemExit("ERROR: NOTION_API_KEY env var not set and ~/.config/notion/api_key not found.")
```

---

**SCRIPTS-P2-007**
**File:** `scripts/webapp_test.py`
**Line:** 17
**Title:** Hardcoded production URL — test always hits live production site, no local/staging override

```python
BASE_URL = "https://rateshift.app"
```

**Description:** The webapp smoke test is hardcoded to always hit the production URL. There is no `--url` CLI argument or `WEBAPP_TEST_URL` environment variable. Running this script during development will fire real requests at production (including the performance test which navigates twice and waits for `networkidle`). If this script is ever added to CI, it would count against production rate limits on every PR.

**Fix:**

```python
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--url", default=os.environ.get("WEBAPP_TEST_URL", "https://rateshift.app"))
args = parser.parse_args()
BASE_URL = args.url
```

---

**SCRIPTS-P2-008**
**File:** `scripts/webapp_test.py`
**Lines:** 46–47
**Title:** Screenshot saved to hardcoded `/tmp/eo-homepage.png` — conflicts in parallel CI runs

```python
page.screenshot(path="/tmp/eo-homepage.png", full_page=True)
```

**Description:** Multiple concurrent CI runs on the same machine (or any parallel test invocation) will overwrite each other's screenshots. The JSON results file is also written to `/tmp/eo-webapp-results.json`. When CI artifacts are collected, only the last run's outputs survive.

**Fix:** Use a unique temp directory per run:

```python
import tempfile
RUN_DIR = tempfile.mkdtemp(prefix="webapp-test-")
page.screenshot(path=f"{RUN_DIR}/homepage.png", full_page=True)
```

---

**SCRIPTS-P2-009**
**File:** `scripts/health-check.sh`
**Line:** 9
**Title:** `set -e` causes premature exit on first failed health check — remaining services not checked

```bash
set -e
```

**Description:** The `check_service` and `check_redis` functions return 1 on failure, and the caller uses `|| FAILED=$((FAILED + 1))`. However, with `set -e`, any unguarded non-zero return code in the script body exits immediately. If `check_service "Backend API"` at line 82 fails, the script exits before checking Frontend and Redis, so the failure summary (`$FAILED service(s) failed`) never reports all failures — it always reports exactly the first one.

**Fix:** Remove `set -e` from this script and rely entirely on the manual `FAILED` counter pattern already in place, which is the correct approach for health-check scripts that must enumerate all failures:

```bash
#!/bin/bash
# No set -e here — we want to enumerate all failures
```

---

### P3 — Low

---

**SCRIPTS-P3-001**
**File:** `scripts/deploy.sh`
**Lines:** 161–163
**Title:** Rollback function is a stub with TODO — error trap calls unimplemented rollback

```bash
rollback() {
    docker compose down
    # TODO: Implement rollback to previous version
    log_warn "Rollback not fully implemented"
}
trap 'log_error "Deployment failed!"; rollback' ERR
```

**Description:** The ERR trap calls `rollback`, which only runs `docker compose down` and prints a warning. There is no actual rollback to a previous image or state. The trap gives the impression of automated rollback when none exists, and the `log_warn` is insufficient given this fires during a production deployment failure.

**Fix:** Either implement rollback (store previous image tag before pull, re-tag and restart on failure) or change the trap to clearly communicate that manual intervention is required:

```bash
trap 'log_error "Deployment FAILED. Services may be down. Manual intervention required. Previous tag was: $PREVIOUS_TAG"' ERR
```

---

**SCRIPTS-P3-002**
**File:** `scripts/production-deploy.sh`
**Lines:** 285–298
**Title:** Git tag created before deployment success is confirmed — tag persists on failed deploy

```bash
git tag -a "$TAG_NAME" -m "Production deployment: $CURRENT_DATE"
```

**Description:** The release tag is created at step 8, after health checks pass (step 6), but if the smoke tests at step 7 produce a warning (which is non-fatal — `echo -e "... ${YELLOW}Warning..."` does not `exit 1`), the tag is still created. Tags in git are not automatically deleted on script failure because there is no `trap` in this script, meaning a partially successful deploy will always have a tag that implies full success.

**Fix:** Move tagging to after all verification steps complete, add a trap to delete the tag on error:

```bash
trap 'git tag -d "$TAG_NAME" 2>/dev/null || true; log_error "Tag $TAG_NAME removed due to deployment failure"' ERR
```

---

**SCRIPTS-P3-003**
**File:** `scripts/stream-chain-run.sh`
**Lines:** 86–89
**Title:** `waitForTimeout` usage in pipeline prompt parsing — newlines in prompts corrupt step boundaries

```bash
while IFS= read -r line; do
    PROMPTS+=("$line")
done < <(echo "$PIPELINE_DATA" | tail -n +2)
```

**Description:** If any prompt in the pipeline config contains a literal newline, the `while read -r line` loop treats each line as a separate prompt. Prompts with embedded newlines (multi-line instructions) will be silently split into multiple entries, increasing `STEP_COUNT` beyond the intended number. The pipeline then passes incorrect prompts to `npx claude-flow stream-chain run`.

**Fix:** Use a NUL-delimited format for prompts in the config and parse with `read -d ''`, or use a JSON array format and parse with `jq` or `python3`.

---

**SCRIPTS-P3-004**
**File:** `scripts/verification-loop-full.sh`
**Lines:** 103–109
**Title:** Secret detection regex is incomplete — misses common secret formats in the codebase

```bash
grep -rn "AKIA[0-9A-Z]\{16\}\|sk-[a-zA-Z0-9]\{20,\}\|-----BEGIN.*PRIVATE KEY"
```

**Description:** The secret scanning only checks for AWS Access Key IDs (`AKIA...`), OpenAI-style keys (`sk-...`), and private key headers. It misses: Stripe secret keys (`sk_live_`, `rk_live_`), Groq API keys (`gsk_...`), Gemini API keys (`AIza...`), JWT secrets (long random strings), Neon connection strings containing passwords, and Composio tokens. The scan also excludes `.env` files which should never be committed but where such patterns would appear.

**Fix:** Extend the pattern list and add Trufflehog or gitleaks to the security phase for comprehensive secret detection.

---

**SCRIPTS-P3-005**
**File:** `.github/actions/notify-slack/action.yml`
**Line:** 72
**Title:** Slack webhook failure silently swallowed — CI continues without notification on notification failure

```bash
curl -fsS -X POST ... "${SLACK_WEBHOOK_URL}" || true
```

**Description:** The `|| true` at the end of the Slack notification curl command means if the Slack webhook is misconfigured, expired, or rate-limited, the notification silently fails and the composite action exits with code 0. The calling workflow has no way to know notifications are broken. Over time, alerting can silently rot without any indication.

**Fix:** Log a warning when the curl fails without failing the overall action:

```bash
if ! curl -fsS -X POST -H 'Content-Type: application/json' -d "${PAYLOAD}" "${SLACK_WEBHOOK_URL}"; then
    echo "WARNING: Slack notification failed. Check SLACK_INCIDENTS_WEBHOOK_URL." >&2
fi
```

---

## E2E Test Findings

### P1 — High

---

**E2E-P1-001**
**File:** `frontend/e2e/authentication.spec.ts`
**Lines:** 302–309
**Title:** `waitForTimeout` used as the primary assertion mechanism for redirect loop detection

```typescript
await page.waitForTimeout(2000)
expect(page.url()).toContain('/auth/login')
```

**Description:** This pattern appears in `authentication.spec.ts` lines 302-309 and `page-load.spec.ts` lines 563-568, 578-583, 598-604. Using fixed `waitForTimeout` durations to verify absence of redirect loops is inherently flaky. On a slow CI runner, a 2-second wait may not be sufficient to observe a redirect that takes 3+ seconds. On a fast local machine, the fixed wait wastes execution time. The assertion is also weak — it only checks that the URL contains a string at one moment, not that the URL stabilized.

**Fix:** Use `page.waitForURL()` with a stable URL pattern and set an explicit timeout. For loop-absence tests, use route interception to count redirect events:

```typescript
let redirectCount = 0
page.on('response', r => { if (r.status() >= 300 && r.status() < 400) redirectCount++ })
await page.goto('/auth/login', { waitUntil: 'domcontentloaded' })
await page.waitForURL('/auth/login', { timeout: 5000 })
expect(redirectCount).toBeLessThan(3)
```

---

**E2E-P1-002**
**File:** `frontend/e2e/authentication.spec.ts`
**Lines:** 336–350
**Title:** Rate-limit test uses `waitForTimeout(300)` between form submissions — timing-dependent and fragile

```typescript
for (let i = 0; i < 6; i++) {
    await page.fill('#email', 'test@example.com')
    await page.fill('#password', 'WrongPass!')
    await page.click('button[type="submit"]')
    await page.waitForTimeout(300)
}
```

**Description:** Submitting the form 6 times with only 300ms between submissions may not be sufficient on a slow CI runner to complete each form submission cycle before the next begins. The test could end up firing overlapping requests. The 8-second timeout for the subsequent `isVisible` check also means a slow CI run could pass even if rate limiting is never triggered within the observation window.

**Fix:** Wait for each submission to complete (loading state ends) before the next:

```typescript
for (let i = 0; i < 6; i++) {
    await page.fill('#email', 'test@example.com')
    await page.fill('#password', 'WrongPass!')
    await page.click('button[type="submit"]')
    await page.waitForFunction(() => !document.querySelector('button[type="submit"][disabled]'))
}
```

---

**E2E-P1-003**
**File:** `frontend/e2e/page-load.spec.ts`
**Lines:** 744–786
**Title:** Transient API failure test uses `mockAllApis` after the first-failure route — route precedence is inverted

```typescript
await page.route('**/api/v1/prices/current**', async (route) => {
    // First call fails, subsequent succeed
    ...
})
// Mock remaining APIs normally
await mockAllApis(page)
```

**Description:** Playwright uses LIFO (Last In First Out) route matching — the most recently registered route for a pattern takes precedence. `mockAllApis(page)` registers `**/api/v1/prices/current**` again after the callCount-based mock, which means `mockAllApis`'s handler takes precedence over the custom failure handler for every request. The test never actually sees the first failure — it always succeeds on the first call.

**Fix:** Register `mockAllApis` first, then override the specific route:

```typescript
await mockAllApis(page)
// Override prices/current with failure behavior (registered last = highest priority)
await page.route('**/api/v1/prices/current**', async (route) => { ... })
```

This matches the pattern already documented in `page-load.spec.ts` line 74 ("Register catch-all FIRST").

---

### P2 — Medium

---

**E2E-P2-001**
**File:** `frontend/e2e/community.spec.ts`
**Lines:** 153–166
**Title:** Community vote test asserts optimistic update count without waiting for UI re-render

```typescript
await firstVote.click()
// Vote count should update (optimistic: 5 → 6)
await expect(firstVote).toContainText('6')
```

**Description:** There is no `await` or retry mechanism between the click and the assertion. If the React state update or re-render takes more than a frame to complete, `toContainText('6')` may fail. Playwright's `expect` does auto-retry for `toContainText` assertions but the retry timeout is not explicitly set, falling back to the global `expect` timeout. If the optimistic update implementation uses a debounce or batches state updates, the default timeout may be insufficient.

**Fix:** Add an explicit timeout or wait for a network response:

```typescript
await firstVote.click()
await expect(firstVote).toContainText('6', { timeout: 5000 })
```

---

**E2E-P2-002**
**File:** `frontend/e2e/dashboard-tabs.spec.ts`
**Lines:** 38–45
**Title:** Catch-all API mock registered after specific mock — route LIFO inversion makes catch-all take priority

```typescript
await page.route('**/api/v1/prices/current**', async (route) => { ... }) // specific
await page.route('**/api/v1/**', async (route) => { ... })               // catch-all (registered LAST = highest priority)
```

**Description:** In `dashboard-tabs.spec.ts`, the specific `prices/current` mock is registered first, then the catch-all `**/api/v1/**` is registered second. Due to Playwright's LIFO matching, the catch-all will intercept `prices/current` requests before the specific handler. The specific mock for prices/current will never be called. This means the dashboard tabs tests run with a blank `{}` response for price data rather than the crafted price payload.

**Fix:** Register catch-all first, specific routes last (consistent with the pattern established in `page-load.spec.ts`):

```typescript
await page.route('**/api/v1/**', async (route) => { /* catch-all */ })
// Specific routes registered after (higher priority):
await page.route('**/api/v1/prices/current**', async (route) => { /* specific */ })
```

---

**E2E-P2-003**
**File:** Multiple E2E files
**Lines:** Various `beforeEach` blocks
**Title:** Massive route mock duplication across 8+ test files — maintenance burden and drift risk

**Description:** The same set of 8-12 API route mocks (prices/current, prices/history, prices/forecast, suppliers, users/profile, user/supplier, savings/summary, prices/optimal-periods) is copy-pasted verbatim in:
- `authentication.spec.ts` (lines 10–98)
- `dashboard.spec.ts` (lines 29–154)
- `full-journey.spec.ts` (lines 10–244)
- `sse-streaming.spec.ts` (lines 25–134)
- `billing-flow.spec.ts` (lines 148–243, 326–420)
- `settings.spec.ts` (lines 57–86)

This is 6 independent copies of the same ~80 lines of mock setup. When an API response shape changes (as happened in the connection features fix on 2026-03-16), every copy must be updated. The `page-load.spec.ts` correctly extracts this into `mockAllApis()`, but the other files do not use it.

**Fix:** Extract shared mock setup into `frontend/e2e/helpers/api-mocks.ts` and import in all test files. The `mockAllApis` function from `page-load.spec.ts` already serves this role and should be moved to the helpers module.

---

**E2E-P2-004**
**File:** `frontend/e2e/full-journey.spec.ts`
**Lines:** 246–265
**Title:** Landing page text assertions are hardcoded to exact copy — fragile on content changes

```typescript
await expect(page.getByText('Save Money on')).toBeVisible()
await expect(page.getByText('Your Electricity Bills', { exact: true })).toBeVisible()
await expect(page.getByText(/AI-powered price optimization/)).toBeVisible()
await expect(page.getByRole('link', { name: 'Start Saving Today' })).toBeVisible()
await expect(page.getByRole('link', { name: 'View Demo' })).toBeVisible()
```

**Description:** Five assertions check for exact marketing copy strings. Any copy change (A/B test, rebrand, localization, CTA update) immediately fails these tests. The test file has 14 similar hardcoded copy assertions in the landing page section alone. These will need constant maintenance and create false urgency in CI when only copy changed.

**Fix:** Assert semantic structure (heading level, ARIA roles, landmark regions) rather than exact copy:

```typescript
await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
await expect(page.getByRole('link', { name: /start|get started|sign up/i }).first()).toBeVisible()
```

---

**E2E-P2-005**
**File:** `frontend/e2e/gdpr-compliance.spec.ts`
**Lines:** 16–49
**Title:** Entire GDPR suite is skipped with `test.skip()` — 4 unimplemented tests tracked as "existing coverage"

```typescript
test.describe('GDPR Compliance Flow', () => {
    test.skip()
    ...
    test('user can export all data', ...)
    test('user can view consent settings', ...)
    test('user can delete all data with confirmation', ...)
```

**Description:** The GDPR compliance test suite is fully skipped. The comment says these are "planned but not yet implemented." These 4 tests appear in test counts and coverage reports as "E2E coverage exists" when in fact they are permanently no-ops. Privacy feature testing (data export, consent management, deletion) is a compliance requirement, not optional coverage. The suite has been in the codebase since before Wave 5 without progress.

**Fix:** Either implement the GDPR features and unskip, or remove the suite entirely and create a GitHub issue tracking the missing coverage. Do not count skipped tests toward coverage metrics.

---

**E2E-P2-006**
**File:** `frontend/e2e/` (all files)
**Title:** No accessibility (a11y) testing in any E2E spec

**Description:** None of the 17 E2E spec files include any accessibility assertions. The `page-load.spec.ts` file's comment header mentions "No JavaScript console errors" and "Reasonable load time" but not accessibility. Given the project is Wave 5 complete with 15 sidebar nav items and community features, there is no automated test for:
- ARIA landmark regions
- Keyboard navigation (tab order)
- Color contrast (even basic)
- Screen reader accessible form labels
- Focus management after navigation

The GDPR page (which is skipped) has no a11y tests either.

**Fix:** Add `@axe-core/playwright` and run axe on every protected page in the page-load suite:

```typescript
import AxeBuilder from '@axe-core/playwright'
const results = await new AxeBuilder({ page }).analyze()
expect(results.violations).toEqual([])
```

---

**E2E-P2-007**
**File:** `frontend/e2e/page-load.spec.ts`
**Lines:** 529–549
**Title:** Protected pages redirection test missing coverage for Water, Propane, Heating Oil, Community pages

```typescript
const protectedPages = [
    '/dashboard', '/prices', '/suppliers', '/connections',
    '/optimize', '/settings', '/alerts', '/assistant', '/onboarding',
]
```

**Description:** The CLAUDE.md documents 15 sidebar nav items as of Wave 5. The protected pages redirection test only covers 9. Missing: `/community`, `/water`, `/propane`, `/heating-oil`, `/gas`, and `/rates/*`. These pages were added in Waves 3-5 but were never added to the auth-redirect test list. Any regression in their auth guard would go undetected by E2E.

**Fix:** Add all app routes to the protected pages list. Derive the list from a shared constant or from Next.js middleware config to prevent future drift:

```typescript
const protectedPages = [
    '/dashboard', '/prices', '/suppliers', '/connections',
    '/optimize', '/settings', '/alerts', '/assistant', '/onboarding',
    '/community', '/water', '/propane', '/heating-oil', '/gas',
]
```

---

### P3 — Low

---

**E2E-P3-001**
**File:** `frontend/e2e/authentication.spec.ts`
**Lines:** 143–151
**Title:** Email format validation test skipped — HTML5 native validation not tested by any mechanism

```typescript
test.skip('validates email format', async ({ page }) => {
    // HTML5 email validation shows native browser tooltip, not visible text
```

**Description:** The test is skipped because HTML5 native browser validation (`:invalid` pseudo-class + tooltip) is not captured by Playwright's `getByText`. However, the validation is important for UX and security. Native HTML5 validation is Playwright-testable via `page.evaluate()` and form validity checks.

**Fix:** Test email validation via JavaScript validity API instead of text assertion:

```typescript
test('rejects invalid email format before submission', async ({ page }) => {
    await page.goto('/auth/login')
    await page.fill('#email', 'invalid-email')
    await page.fill('#password', 'TestPass123!')
    const isValid = await page.$eval('#email', (el: HTMLInputElement) => el.validity.valid)
    expect(isValid).toBe(false)
})
```

---

**E2E-P3-002**
**File:** `frontend/e2e/authentication.spec.ts`
**Lines:** 192–201, 354–376
**Title:** Webkit logout test skipped without a documented tracking issue

```typescript
test.skip(browserName === 'webkit', 'Webkit sign-out redirect exceeds test timeout')
```

**Description:** The webkit logout test skip appears twice (logout and "clears sensitive data on logout"). The comment explains the symptom but not the root cause or tracking issue. There is no GitHub issue link, no workaround attempt, and no timeline for fixing. This creates a long-term coverage gap for Safari users logging out — which is a security-sensitive operation.

**Fix:** Investigate the webkit timeout root cause (likely a race between cookie clearing and navigation). In the interim, create a GitHub issue and add its number to the skip comment:

```typescript
test.skip(browserName === 'webkit', 'GH #XXX: webkit cookie clearing race condition in logout')
```

---

**E2E-P3-003**
**File:** `frontend/e2e/dashboard.spec.ts`
**Line:** 228
**Title:** Mobile responsiveness test asserts sidebar is not visible, but selector is too broad

```typescript
await expect(page.getByRole('navigation')).not.toBeVisible()
```

**Description:** `getByRole('navigation')` matches any `<nav>` element on the page. The page likely has multiple navigation elements (sidebar, breadcrumbs, pagination). The test asserts that no `<nav>` is visible on mobile, but this may be incorrect — a mobile hamburger menu trigger or bottom navigation may still be present and visible. The assertion passes as long as _one_ nav element is hidden, but may not catch regressions in mobile layout.

**Fix:** Use a more specific selector targeting the sidebar navigation:

```typescript
await expect(page.locator('[data-testid="sidebar"]')).not.toBeVisible()
```

---

**E2E-P3-004**
**File:** `frontend/e2e/sse-streaming.spec.ts`
**Lines:** 252–287
**Title:** Multiple SSE price update test does not assert that prices actually update in the DOM

**Description:** The test sends 5 SSE events with prices from 0.25 down to 0.21, but only asserts `await expect(page.getByTestId('current-price').first()).toBeVisible()`. It never asserts that the price displayed reflects the SSE data. The test would pass even if the SSE handler completely ignores incoming data, making it a smoke test that validates rendering but not SSE data processing.

**Fix:** After sending events, assert the current price reflects the latest SSE value:

```typescript
// The last SSE event sent price "0.21"
await expect(page.getByTestId('current-price').first()).toContainText('0.21', { timeout: 5000 })
```

---

**E2E-P3-005**
**File:** `frontend/e2e/` (all files)
**Title:** No E2E tests for the connections page flows — critical Wave 5 feature has zero interaction coverage

**Description:** The `page-load.spec.ts` verifies `/connections` loads without errors, but there are no E2E tests for:
- Creating a new connection (any of the 5 types)
- Connection status display
- Manual connection sync trigger
- Error states (invalid credentials, expired token)
- The `PortalConnectionFlow` multi-step form

This was identified as a critical area (connection features were fully repaired in commit 4947cf9 on 2026-03-16). Without E2E coverage, regressions in the most recently touched critical feature will only be caught by unit tests.

**Fix:** Add `frontend/e2e/connections.spec.ts` with connection creation flows mocked at the API level.

---

## Composite Actions Findings

### P1 — High

---

**ACTIONS-P1-001**
**File:** `.github/actions/validate-migrations/action.yml`
**Lines:** 33–52
**Title:** Sequential numbering check uses `xargs -n1 basename` — fails if migration directory has spaces in path

```bash
NUMBERED_FILES=$(ls "$MIGRATION_DIR"/*.sql 2>/dev/null \
    | xargs -n1 basename \
    | grep -E '^[0-9]{3}_' \
    | sort)
```

**Description:** `ls` output piped to `xargs` breaks on filenames or paths containing spaces. While migration filenames are unlikely to have spaces, the `$MIGRATION_DIR` path input could contain spaces if the action is called from a workflow that sets a custom `migration-dir` with spaces. Additionally, parsing `ls` output is explicitly discouraged by shellcheck (SC2012) because it can fail in edge cases with special characters.

**Fix:** Use `find` with NUL-delimited output:

```bash
NUMBERED_FILES=$(find "$MIGRATION_DIR" -maxdepth 1 -name '[0-9][0-9][0-9]_*.sql' -printf '%f\n' | sort)
```

---

**ACTIONS-P1-002**
**File:** `.github/actions/validate-migrations/action.yml`
**Lines:** 98–109
**Title:** SERIAL/BIGSERIAL check flag fires on comment lines and string literals

```bash
while IFS=: read -r lineno line; do
    stripped=$(echo "$line" | sed 's/^[[:space:]]*//')
    echo "$stripped" | grep -q '^--' && continue
    VIOLATIONS="${VIOLATIONS}${filename}:${lineno}: SERIAL/BIGSERIAL found..."
done < <(grep -in '\bBIGSERIAL\b\|\bSERIAL\b' "$filepath" || true)
```

**Description:** The check first uses `grep -in` to find all lines containing `SERIAL` or `BIGSERIAL`, including lines within comments and string literals (e.g., `-- migration from SERIAL to UUID` or `description TEXT DEFAULT 'User serial number'`). The `echo "$stripped" | grep -q '^--' && continue` only skips lines that start with `--` after stripping leading whitespace, but the `grep -in` piped output already filtered to matching lines — it does not re-emit the full line with correct leading whitespace for the `^--` check to work reliably. This can produce false-positive SERIAL violations from comment lines.

**Fix:** Use a more precise grep pattern that excludes comment lines from the initial search:

```bash
grep -in '\bBIGSERIAL\b\|\bSERIAL\b' "$filepath" | grep -v '^\s*--' || true
```

---

### P2 — Medium

---

**ACTIONS-P2-001**
**File:** `.github/actions/retry-curl/action.yml`
**Lines:** 75–76
**Title:** Temp file for request body uses mktemp but trap only handles EXIT — SIGKILL leaves temp file on disk

```bash
BODY_FILE=$(mktemp)
printf '%s' "$BODY" > "$BODY_FILE"
trap "rm -f '$BODY_FILE'" EXIT
```

**Description:** The `EXIT` trap correctly cleans up on normal exit and signals that trigger exit, but SIGKILL (kill -9) bypasses all traps. On GitHub Actions runners, force-stopping a job sends SIGKILL, leaving the temp file on disk. While GitHub Actions runners are ephemeral and this is unlikely to cause a persistent leak, the body content (which may include API keys or JSON payloads with sensitive data) persists in `/tmp` for the remainder of the runner's lifetime until it is recycled.

**Fix:** Use `mktemp` in the runner's working directory rather than `/tmp`, and explicitly set a short lifetime by naming the file descriptively so runner cleanup catches it. Also add `SIGTERM` and `SIGINT` traps:

```bash
BODY_FILE=$(mktemp "${RUNNER_TEMP}/retry-curl-body.XXXXXX")
trap "rm -f '${BODY_FILE}'" EXIT INT TERM
```

---

**ACTIONS-P2-002**
**File:** `.github/actions/validate-migrations/action.yml`
**Lines:** 117–124
**Title:** Multi-line violations encoded with `%0A` substitution — breaks if violations contain `%0A` literally

```bash
VIOLATIONS_ENCODED=$(printf "%b" "$VIOLATIONS" | sed ':a;N;$!ba;s/\n/%0A/g')
echo "violations=${VIOLATIONS_ENCODED}" >> "$GITHUB_OUTPUT"
```

**Description:** The GitHub Actions output encoding replaces newlines with `%0A` for multi-line output. However, if any violation message itself contains `%0A` (e.g., a filename or SQL snippet with a URL-encoded newline), the output becomes ambiguous. The `sed` one-liner is also fragile on macOS BSD `sed` (which is used in local testing) versus GNU `sed` in GitHub Actions runners — the `:a;N;$!ba` idiom behaves differently across implementations.

**Fix:** Use the modern GitHub Actions multi-line output format with a heredoc delimiter:

```bash
{
    echo "violations<<VIOLATIONS_EOF"
    printf "%b" "$VIOLATIONS"
    echo "VIOLATIONS_EOF"
} >> "$GITHUB_OUTPUT"
```

---

### P3 — Low

---

**ACTIONS-P3-001**
**File:** `.github/actions/validate-migrations/action.yml`
**Lines:** 43–52
**Title:** Sequential numbering check treats `init_neon.sql` as migration #1 but does not validate its name or content

```bash
PREV_NUM=1
# ... loop from 002 onward
if [ ! -f "$MIGRATION_DIR/init_neon.sql" ]; then
    VIOLATIONS="${VIOLATIONS}Missing: init_neon.sql..."
```

**Description:** The check hardcodes `init_neon.sql` as migration #1, but this coupling is not documented and any rename of the init file (e.g., to `001_init.sql` following a naming convention change) would silently break the sequential numbering logic. The `PREV_NUM=1` initialization means migration 002 is considered the next expected migration — if `init_neon.sql` is renamed to `001_init.sql`, the check would suddenly see a gap from `001` to `002` as invalid.

**Fix:** Document the `init_neon.sql` special case explicitly in the action's description and add a comment in the check:

```bash
# init_neon.sql is treated as migration #1 (the initial schema bootstrap).
# Numbered migrations start at 002. PREV_NUM=1 seeds the sequential check.
PREV_NUM=1
```

---

## Pages With Missing E2E Coverage

The following app pages have been confirmed (from CLAUDE.md and sidebar nav of 15 items) but have zero dedicated E2E interaction tests (only smoke-load coverage from `page-load.spec.ts`):

| Page | Route | Status |
|------|-------|--------|
| Community | `/community` | Partial: `community.spec.ts` covers load + vote only; no post creation end-to-end, no report flow, no moderation flow |
| Water Dashboard | `/water` | Load-only (page-load.spec.ts does not even include it) |
| Propane Dashboard | `/propane` | Load-only |
| Heating Oil | `/heating-oil` | No coverage |
| Natural Gas | `/gas` | No coverage |
| Connections | `/connections` | Load-only; zero flow tests for any of the 5 connection types |
| Assistant (AI Agent) | `/assistant` | Load-only; no query submission, no streaming response test |
| Onboarding | `/onboarding` | Load-only; no step progression test |
| SEO Rate Pages | `/rates/[state]/[type]` | No E2E coverage for ISR pages |

---

## Quick-Fix Priority Order

### Immediate (before next production deploy)

1. **SCRIPTS-P0-001** — Remove `|| true` from docker-entrypoint migration runner; failed migrations must abort startup.
2. **SCRIPTS-P0-004** — Fix production-deploy.sh to use `.venv/bin/python` and remove `2>/dev/null` from test calls.
3. **E2E-P1-003** — Fix route LIFO inversion in transient failure test so the failure scenario actually fires.
4. **E2E-P2-002** — Fix LIFO inversion in dashboard-tabs mock setup.

### This Sprint

5. **SCRIPTS-P0-003** — Add migration tracking table to prevent re-running applied migrations.
6. **SCRIPTS-P1-007** — Replace hardcoded `/Users/devinmcgrath/...` path in `project-intelligence-sync.sh`.
7. **SCRIPTS-P1-008** — Replace hardcoded path in `dsp_bootstrap.py`.
8. **SCRIPTS-P1-005** — Fix `temp_conn` unbound name in `run_migrations_007_019.py`.
9. **E2E-P2-003** — Extract duplicate mock setup into `frontend/e2e/helpers/api-mocks.ts`.
10. **E2E-P2-007** — Add missing Wave 3-5 pages to protected-pages auth redirect test.

### Backlog

11. **SCRIPTS-P0-002** — Replace `.env` sourcing with proper environment variable injection.
12. **SCRIPTS-P1-003** — Add `--dangerously-skip-permissions` governance in loki-feature.sh.
13. **ACTIONS-P1-001** — Fix `ls | xargs` anti-pattern in validate-migrations action.
14. **E2E-P2-005** — Remove or implement the GDPR skipped test suite.
15. **E2E-P2-006** — Add axe-core accessibility scanning to page-load suite.
16. **E2E-P3-005** — Create `connections.spec.ts` with flow tests for all 5 connection types.
