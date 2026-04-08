#!/usr/bin/env bash
# test-optimizations.sh — TDD tests for optimization scripts and hooks
# Usage: bash scripts/test-optimizations.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

# ---------------------------------------------------------------------------
# Test 1: post-edit-sync.sh cooldown (60s rate limiting)
# ---------------------------------------------------------------------------
echo "--- Test: post-edit-sync.sh cooldown ---"

TMPDIR_TEST=$(mktemp -d)
trap "rm -rf $TMPDIR_TEST" EXIT

# Create a mock git repo context
mkdir -p "$TMPDIR_TEST/repo/.claude"
cd "$TMPDIR_TEST/repo"
git init -q
QUEUE_FILE="$TMPDIR_TEST/repo/.claude/.board-sync-queue"

# Simulate first run — should append
SCRIPT="$REPO_ROOT/.claude/hooks/board-sync/post-edit-sync.sh"
bash "$SCRIPT" 2>/dev/null
if [[ -f "$QUEUE_FILE" ]]; then
  pass "First run creates queue entry"
else
  fail "First run should create queue entry"
fi

# Simulate rapid second run — should be rate-limited (queue modified <60s ago)
LINE_COUNT_BEFORE=$(wc -l < "$QUEUE_FILE" | tr -d ' ')
bash "$SCRIPT" 2>/dev/null
LINE_COUNT_AFTER=$(wc -l < "$QUEUE_FILE" | tr -d ' ')
if [[ "$LINE_COUNT_AFTER" -eq "$LINE_COUNT_BEFORE" ]]; then
  pass "Second run within 60s is rate-limited (no new entry)"
else
  fail "Second run within 60s should NOT append (got $LINE_COUNT_AFTER, expected $LINE_COUNT_BEFORE)"
fi

# Simulate run after cooldown expires — backdate file modification time
touch -t 202601010000 "$QUEUE_FILE"  # Set to Jan 1 2026 (>60s ago)
bash "$SCRIPT" 2>/dev/null
LINE_COUNT_FINAL=$(wc -l < "$QUEUE_FILE" | tr -d ' ')
if [[ "$LINE_COUNT_FINAL" -gt "$LINE_COUNT_BEFORE" ]]; then
  pass "Run after cooldown expires appends new entry"
else
  fail "Run after cooldown should append (got $LINE_COUNT_FINAL, expected > $LINE_COUNT_BEFORE)"
fi

cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Test 2: loki-cleanup.sh dry-run mode
# ---------------------------------------------------------------------------
echo "--- Test: loki-cleanup.sh dry-run ---"

OUTPUT=$(bash "$REPO_ROOT/scripts/loki-cleanup.sh" --dry-run 2>&1)
if echo "$OUTPUT" | grep -q "DRY-RUN"; then
  pass "Dry-run mode prints DRY-RUN indicator"
else
  fail "Dry-run output should contain DRY-RUN"
fi

if echo "$OUTPUT" | grep -q "no files were actually deleted"; then
  pass "Dry-run confirms no deletions"
else
  fail "Dry-run should confirm no actual deletions"
fi

if echo "$OUTPUT" | grep -q "Summary:"; then
  pass "Dry-run prints summary with counts"
else
  fail "Dry-run should print summary"
fi

# ---------------------------------------------------------------------------
# Test 3: dsp-archive.sh dry-run mode
# ---------------------------------------------------------------------------
echo "--- Test: dsp-archive.sh dry-run ---"

OUTPUT=$(bash "$REPO_ROOT/scripts/dsp-archive.sh" --dry-run 2>&1)
if echo "$OUTPUT" | grep -q "Summary:"; then
  pass "DSP archive dry-run prints summary"
else
  fail "DSP archive dry-run should print summary"
fi

if echo "$OUTPUT" | grep -q "no files were actually moved"; then
  pass "DSP archive dry-run confirms no moves"
else
  fail "DSP archive dry-run should confirm no actual moves"
fi

# ---------------------------------------------------------------------------
# Test 4: loki-event-sync.sh archive pruning
# ---------------------------------------------------------------------------
echo "--- Test: loki-event-sync.sh archive pruning ---"

EVENTS_ARCHIVE="$REPO_ROOT/.loki/events/archive"
LOG_FILE="$REPO_ROOT/.claude/logs/loki-board-sync.log"
if [[ -d "$EVENTS_ARCHIVE" ]]; then
  OLD_COUNT=$(find "$EVENTS_ARCHIVE" -type f -mtime +7 2>/dev/null | wc -l | tr -d ' ')
  TOTAL_COUNT=$(find "$EVENTS_ARCHIVE" -type f 2>/dev/null | wc -l | tr -d ' ')

  # Clear log, run dry-run, check log output (log() writes to file, not stdout)
  : > "$LOG_FILE" 2>/dev/null || true
  bash "$REPO_ROOT/.claude/hooks/board-sync/loki-event-sync.sh" --dry-run 2>/dev/null

  if [[ "$OLD_COUNT" -gt 0 ]]; then
    if grep -q "prune.*archived events" "$LOG_FILE" 2>/dev/null; then
      pass "Event sync dry-run reports prunable archives ($OLD_COUNT/$TOTAL_COUNT)"
    else
      fail "Event sync dry-run should report prunable archives in log"
    fi
  else
    pass "No old archives to prune (all within 7-day retention)"
  fi
else
  pass "No archive directory — pruning step skipped correctly"
fi

# ---------------------------------------------------------------------------
# Test 5: CLAUDE.md size reduction
# ---------------------------------------------------------------------------
echo "--- Test: CLAUDE.md context optimization ---"

CLAUDE_LINES=$(wc -l < "$REPO_ROOT/CLAUDE.md" | tr -d ' ')
if [[ "$CLAUDE_LINES" -lt 150 ]]; then
  pass "CLAUDE.md reduced to $CLAUDE_LINES lines (was 177)"
else
  fail "CLAUDE.md should be <150 lines (got $CLAUDE_LINES)"
fi

if [[ -f "$REPO_ROOT/REMINDERS.md" ]]; then
  REMINDER_LINES=$(wc -l < "$REPO_ROOT/REMINDERS.md" | tr -d ' ')
  pass "REMINDERS.md exists ($REMINDER_LINES lines)"
else
  fail "REMINDERS.md should exist"
fi

if grep -q "REMINDERS.md" "$REPO_ROOT/CLAUDE.md"; then
  pass "CLAUDE.md references REMINDERS.md"
else
  fail "CLAUDE.md should reference REMINDERS.md"
fi

# ---------------------------------------------------------------------------
# Test 6: MEMORY.md deduplication
# ---------------------------------------------------------------------------
echo "--- Test: MEMORY.md deduplication ---"

MEMORY_FILE="$HOME/.claude/projects/-Users-devinmcgrath-projects-electricity-optimizer/memory/MEMORY.md"
if ! grep -q "## Infrastructure" "$MEMORY_FILE"; then
  pass "MEMORY.md no longer has Infrastructure section (was duplicate)"
else
  fail "MEMORY.md should not contain Infrastructure section"
fi

if ! grep -q "## Critical Patterns" "$MEMORY_FILE"; then
  pass "MEMORY.md no longer has Critical Patterns section (was duplicate)"
else
  fail "MEMORY.md should not contain Critical Patterns section"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]] && echo "All tests passed!" || exit 1
