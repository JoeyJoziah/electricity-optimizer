#!/usr/bin/env bash
# loki-cleanup.sh — Prune stale Loki state files to prevent unbounded growth
# Usage: bash scripts/loki-cleanup.sh [--dry-run]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOKI_DIR="$REPO_ROOT/.loki"
DRY_RUN=false

[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

deleted=0
retained=0

log() { echo "[loki-cleanup] $*"; }

# 1. Prune event archives older than 30 days
ARCHIVE_DIR="$LOKI_DIR/events/archive"
if [[ -d "$ARCHIVE_DIR" ]]; then
  old_archives=$(find "$ARCHIVE_DIR" -type f -mtime +30 2>/dev/null | wc -l | tr -d ' ')
  total_archives=$(find "$ARCHIVE_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')
  if $DRY_RUN; then
    log "DRY-RUN: Would delete $old_archives/$total_archives event archive files (>30 days)"
  else
    find "$ARCHIVE_DIR" -type f -mtime +30 -delete 2>/dev/null || true
    log "Deleted $old_archives/$total_archives event archive files (>30 days)"
  fi
  deleted=$((deleted + old_archives))
  retained=$((retained + total_archives - old_archives))
fi

# 2. Prune episodic memory entries older than 90 days
EPISODIC_DIR="$LOKI_DIR/memory/episodic"
if [[ -d "$EPISODIC_DIR" ]]; then
  old_episodic=$(find "$EPISODIC_DIR" -type f -mtime +90 2>/dev/null | wc -l | tr -d ' ')
  total_episodic=$(find "$EPISODIC_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')
  if $DRY_RUN; then
    log "DRY-RUN: Would delete $old_episodic/$total_episodic episodic entries (>90 days)"
  else
    find "$EPISODIC_DIR" -type f -mtime +90 -delete 2>/dev/null || true
    log "Deleted $old_episodic/$total_episodic episodic entries (>90 days)"
  fi
  deleted=$((deleted + old_episodic))
  retained=$((retained + total_episodic - old_episodic))
fi

# 3. Compact timeline.json — prune entries older than 60 days
TIMELINE="$LOKI_DIR/memory/timeline.json"
if [[ -f "$TIMELINE" ]]; then
  size_before=$(wc -c < "$TIMELINE" | tr -d ' ')
  cutoff=$(date -v-60d +%s 2>/dev/null || date -d '60 days ago' +%s 2>/dev/null || echo 0)

  if [[ "$cutoff" -gt 0 ]]; then
    if $DRY_RUN; then
      log "DRY-RUN: Would compact timeline.json (currently ${size_before} bytes, pruning entries >60 days)"
    else
      python3 - "$TIMELINE" "$cutoff" <<'PYEOF'
import json, sys
timeline_path = sys.argv[1]
cutoff = int(sys.argv[2])
with open(timeline_path) as f:
    data = json.load(f)
if isinstance(data, list):
    kept = [e for e in data if e.get('timestamp', 0) >= cutoff]
    with open(timeline_path, 'w') as f:
        json.dump(kept, f, separators=(',', ':'))
    print(f'Compacted timeline.json: {len(data)} -> {len(kept)} entries')
elif isinstance(data, dict):
    compacted = False
    for key in ('entries', 'recent_actions'):
        if key in data and isinstance(data[key], list):
            original = len(data[key])
            data[key] = [e for e in data[key] if e.get('timestamp', 0) >= cutoff]
            if original != len(data[key]):
                compacted = True
            print(f'  {key}: {original} -> {len(data[key])} entries')
    if compacted:
        with open(timeline_path, 'w') as f:
            json.dump(data, f, separators=(',', ':'))
        print('Compacted timeline.json')
    else:
        print('timeline.json: no entries to prune')
else:
    print('timeline.json format not recognized, skipping')
PYEOF
      [[ $? -ne 0 ]] && log "Warning: timeline.json compaction failed (non-fatal)"
      size_after=$(wc -c < "$TIMELINE" | tr -d ' ')
      log "timeline.json: ${size_before} -> ${size_after} bytes"
    fi
  fi
fi

log "Summary: deleted=$deleted, retained=$retained"
$DRY_RUN && log "(no files were actually deleted — dry run)"
