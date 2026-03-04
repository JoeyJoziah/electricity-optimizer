#!/usr/bin/env bash
# verification-loop-full.sh — 6-phase full verification with truth score
#
# Runs build, types, lint, tests, security, and diff checks.
# Outputs a weighted truth score (0.0-1.0).
# Designed for manual invocation or session-end quality gates.

set -uo pipefail

REPO_ROOT="/Users/devinmcgrath/projects/electricity-optimizer"
LOG_FILE="$REPO_ROOT/.claude/logs/verification-full.log"
PI_FAILURES="$REPO_ROOT/.project-intelligence/signals/QUALITY_GATE_FAILURES.log"

mkdir -p "$(dirname "$LOG_FILE")"

TIMESTAMP="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# Score tracking
declare -A scores
declare -A weights
weights[tests]=40
weights[build]=20
weights[types]=15
weights[lint]=10
weights[security]=10
weights[diff]=5

pass_phase() { scores[$1]=1; log "  PASS: $1"; }
fail_phase() { scores[$1]=0; log "  FAIL: $1 — $2"; }

log "=== Full Verification Loop ($TIMESTAMP) ==="

# ── Phase 1: Build ─────────────────────────────────────────────────────
log "Phase 1/6: Build check"
if (cd "$REPO_ROOT/frontend" && npm run build 2>&1 | tail -5) >> "$LOG_FILE" 2>&1; then
    pass_phase "build"
else
    fail_phase "build" "Next.js build failed"
fi

# ── Phase 2: Types ─────────────────────────────────────────────────────
log "Phase 2/6: Type check"
if (cd "$REPO_ROOT/frontend" && npx tsc --noEmit 2>&1 | tail -5) >> "$LOG_FILE" 2>&1; then
    pass_phase "types"
else
    fail_phase "types" "TypeScript errors found"
fi

# ── Phase 3: Lint ──────────────────────────────────────────────────────
log "Phase 3/6: Lint check"
lint_pass=true

if (cd "$REPO_ROOT/frontend" && npx next lint --quiet 2>&1 | tail -5) >> "$LOG_FILE" 2>&1; then
    log "  Frontend lint: OK"
else
    log "  Frontend lint: issues found"
    lint_pass=false
fi

if "$REPO_ROOT/.venv/bin/python" -m ruff check "$REPO_ROOT/backend/" 2>&1 | tail -5 >> "$LOG_FILE" 2>&1; then
    log "  Backend lint: OK"
else
    log "  Backend lint: issues found"
    lint_pass=false
fi

if $lint_pass; then
    pass_phase "lint"
else
    fail_phase "lint" "Lint issues in frontend or backend"
fi

# ── Phase 4: Tests ─────────────────────────────────────────────────────
log "Phase 4/6: Test suites"
tests_pass=true

if "$REPO_ROOT/.venv/bin/python" -m pytest "$REPO_ROOT/backend/tests/" -q --tb=no 2>&1 | tail -5 >> "$LOG_FILE" 2>&1; then
    log "  Backend tests: PASS"
else
    log "  Backend tests: FAIL"
    tests_pass=false
fi

if (cd "$REPO_ROOT/frontend" && npx jest --silent 2>&1 | tail -5) >> "$LOG_FILE" 2>&1; then
    log "  Frontend tests: PASS"
else
    log "  Frontend tests: FAIL"
    tests_pass=false
fi

if $tests_pass; then
    pass_phase "tests"
else
    fail_phase "tests" "Test failures in backend or frontend"
fi

# ── Phase 5: Security ─────────────────────────────────────────────────
log "Phase 5/6: Security scan"
security_pass=true

# Check for leaked secrets patterns
if grep -rn "AKIA[0-9A-Z]\{16\}\|sk-[a-zA-Z0-9]\{20,\}\|-----BEGIN.*PRIVATE KEY" \
    "$REPO_ROOT/backend/" "$REPO_ROOT/frontend/lib/" "$REPO_ROOT/frontend/app/" \
    --include="*.py" --include="*.ts" --include="*.tsx" \
    2>/dev/null | grep -v "node_modules" | grep -v ".env" | head -5; then
    log "  WARN: Potential secret patterns found"
    security_pass=false
fi

# Check for console.log in production code (not test files)
console_count=$(grep -rn "console\.log" "$REPO_ROOT/frontend/app/" "$REPO_ROOT/frontend/lib/" \
    --include="*.ts" --include="*.tsx" 2>/dev/null | \
    grep -v "__tests__" | grep -v ".test." | grep -v ".spec." | wc -l | tr -d ' ')
if (( console_count > 10 )); then
    log "  WARN: $console_count console.log statements in production code"
    security_pass=false
fi

if $security_pass; then
    pass_phase "security"
else
    fail_phase "security" "Security concerns found"
fi

# ── Phase 6: Diff ──────────────────────────────────────────────────────
log "Phase 6/6: Diff analysis"
dirty_count=$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
if (( dirty_count < 50 )); then
    pass_phase "diff"
    log "  Uncommitted changes: $dirty_count files"
else
    fail_phase "diff" "$dirty_count uncommitted files (threshold: 50)"
fi

# ── Calculate truth score ──────────────────────────────────────────────
total_weight=0
weighted_score=0

for phase in tests build types lint security diff; do
    w=${weights[$phase]}
    s=${scores[$phase]:-0}
    total_weight=$((total_weight + w))
    weighted_score=$((weighted_score + w * s))
done

# Output as percentage with 2 decimal places
if (( total_weight > 0 )); then
    truth_score=$(echo "scale=2; $weighted_score / $total_weight" | bc)
else
    truth_score="0.00"
fi

log ""
log "=== TRUTH SCORE: $truth_score ==="
log "  Tests(40%):${scores[tests]:-0} Build(20%):${scores[build]:-0} Types(15%):${scores[types]:-0}"
log "  Lint(10%):${scores[lint]:-0} Security(10%):${scores[security]:-0} Diff(5%):${scores[diff]:-0}"
log ""

# Output truth score to stdout for callers
echo "$truth_score"

# Log failure if below threshold
if [[ "$truth_score" != "1.00" ]] && [[ -d "$(dirname "$PI_FAILURES")" ]]; then
    echo "[$TIMESTAMP] TRUTH_SCORE=$truth_score phases: tests=${scores[tests]:-0} build=${scores[build]:-0} types=${scores[types]:-0} lint=${scores[lint]:-0} security=${scores[security]:-0} diff=${scores[diff]:-0}" >> "$PI_FAILURES" 2>/dev/null || true
fi

exit 0
