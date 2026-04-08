#!/usr/bin/env bash
# dsp-archive.sh — Archive stale DSP entities to reduce active graph size
# Usage: bash scripts/dsp-archive.sh [--dry-run]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DSP_DIR="$REPO_ROOT/.dsp"
ARCHIVE_DIR="$DSP_DIR/.archive"
UID_MAP="$DSP_DIR/uid_map.json"
DRY_RUN=false

[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

log() { echo "[dsp-archive] $*"; }

if [[ ! -d "$DSP_DIR" ]]; then
  log "No .dsp/ directory found. Nothing to do."
  exit 0
fi

# Find obj-* directories not modified in 30+ days
archived=0
retained=0
total=0

for obj_dir in "$DSP_DIR"/obj-*; do
  [[ -d "$obj_dir" ]] || continue
  total=$((total + 1))

  # Check if any file in the directory was modified within 30 days
  recent=$(find "$obj_dir" -type f -mtime -30 2>/dev/null | head -1)

  if [[ -z "$recent" ]]; then
    # All files are older than 30 days — archive
    obj_name=$(basename "$obj_dir")
    if $DRY_RUN; then
      log "DRY-RUN: Would archive $obj_name"
    else
      mkdir -p "$ARCHIVE_DIR"
      mv "$obj_dir" "$ARCHIVE_DIR/$obj_name"
    fi
    archived=$((archived + 1))
  else
    retained=$((retained + 1))
  fi
done

# Update uid_map.json to exclude archived entries
if [[ $archived -gt 0 ]] && [[ -f "$UID_MAP" ]] && ! $DRY_RUN; then
  python3 - "$ARCHIVE_DIR" "$UID_MAP" <<'PYEOF'
import json, os, sys
archive_dir = sys.argv[1]
uid_map_path = sys.argv[2]
archived_names = set(os.listdir(archive_dir)) if os.path.isdir(archive_dir) else set()
with open(uid_map_path) as f:
    uid_map = json.load(f)
if isinstance(uid_map, dict):
    cleaned = {k: v for k, v in uid_map.items()
               if not any(a in str(v) for a in archived_names)}
    removed = len(uid_map) - len(cleaned)
    with open(uid_map_path, 'w') as f:
        json.dump(cleaned, f, indent=2)
    print(f'uid_map.json: removed {removed} stale entries')
PYEOF
  [[ $? -ne 0 ]] && log "Warning: uid_map.json cleanup failed (non-fatal)"
fi

log "Summary: total=$total, archived=$archived, retained=$retained"
$DRY_RUN && log "(no files were actually moved — dry run)"
