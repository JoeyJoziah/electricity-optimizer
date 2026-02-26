#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# stream-chain-run.sh — Wrapper for claude-flow stream-chain pipelines
#
# Reads pipeline definitions from .claude-flow/config.json and invokes
# the stream-chain CLI with the correct prompts and timeout.
#
# Usage:
#   scripts/stream-chain-run.sh <pipeline>              # Run pipeline
#   scripts/stream-chain-run.sh <pipeline> --dry-run    # Show prompts
#   scripts/stream-chain-run.sh <pipeline> --bg         # Background
#   scripts/stream-chain-run.sh <pipeline> --verbose    # Verbose output
#   scripts/stream-chain-run.sh --list                  # List pipelines
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_FILE="$PROJECT_DIR/.claude-flow/config.json"
RUNS_DIR="$PROJECT_DIR/.claude-flow/memory/stream-chain/runs"
EVENTS_DIR="$PROJECT_DIR/.loki/events/pending"

# Parse args
PIPELINE=""
DRY_RUN=false
BACKGROUND=false
VERBOSE=false

for arg in "$@"; do
    case "$arg" in
        --dry-run)  DRY_RUN=true ;;
        --bg)       BACKGROUND=true ;;
        --verbose)  VERBOSE=true ;;
        --list)
            if [[ ! -f "$CONFIG_FILE" ]]; then
                echo "Error: Config not found at $CONFIG_FILE" >&2; exit 1
            fi
            echo "Available pipelines:"
            python3 -c "
import json, sys
with open('$CONFIG_FILE') as f:
    cfg = json.load(f)
for name, p in cfg['streamChain']['pipelines'].items():
    steps = len(p['steps'])
    timeout = p.get('timeout', cfg['streamChain']['defaultTimeout'])
    print(f'  {name:16s} {p[\"description\"]:52s} ({steps} steps, {timeout}s/step)')
"
            exit 0
            ;;
        -*)         echo "Unknown flag: $arg" >&2; exit 1 ;;
        *)          PIPELINE="$arg" ;;
    esac
done

if [[ -z "$PIPELINE" ]]; then
    echo "Usage: scripts/stream-chain-run.sh <pipeline> [--dry-run] [--bg] [--verbose]"
    echo "       scripts/stream-chain-run.sh --list"
    exit 1
fi

# Validate config exists
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Error: Config not found at $CONFIG_FILE" >&2
    exit 1
fi

# Extract pipeline prompts and timeout
PIPELINE_DATA=$(python3 -c "
import json, sys
with open('$CONFIG_FILE') as f:
    cfg = json.load(f)
pipelines = cfg['streamChain']['pipelines']
if '$PIPELINE' not in pipelines:
    print('ERROR: Pipeline \"$PIPELINE\" not found. Available:', ', '.join(pipelines.keys()), file=sys.stderr)
    sys.exit(1)
p = pipelines['$PIPELINE']
timeout = p.get('timeout', cfg['streamChain']['defaultTimeout'])
print(timeout)
for step in p['steps']:
    print(step['prompt'])
") || exit 1

# Parse: first line is timeout, rest are prompts (NUL-delimited for safety)
TIMEOUT=$(echo "$PIPELINE_DATA" | head -1)

PROMPTS=()
STEP_COUNT=0
while IFS= read -r line; do
    PROMPTS+=("$line")
    STEP_COUNT=$((STEP_COUNT + 1))
done < <(echo "$PIPELINE_DATA" | tail -n +2)

echo "Pipeline: $PIPELINE ($STEP_COUNT steps, ${TIMEOUT}s/step)"

# Dry run — print prompts and exit
if $DRY_RUN; then
    echo "--- DRY RUN ---"
    local_idx=1
    for prompt in "${PROMPTS[@]}"; do
        echo ""
        echo "Step $local_idx:"
        echo "  ${prompt:0:120}..."
        local_idx=$((local_idx + 1))
    done
    echo ""
    echo "Would run: npx claude-flow stream-chain run <prompts> --timeout $TIMEOUT"
    exit 0
fi

# Ensure output dirs exist
mkdir -p "$RUNS_DIR" "$EVENTS_DIR"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RUN_ID="${PIPELINE}-${TIMESTAMP}"
RESULT_FILE="$RUNS_DIR/${RUN_ID}.json"

echo "Run ID: $RUN_ID"
echo "Output: $RESULT_FILE"

# Build the command
CMD=(npx claude-flow stream-chain run)
for prompt in "${PROMPTS[@]}"; do
    CMD+=("$prompt")
done
CMD+=(--timeout "$TIMEOUT")

if $VERBOSE; then
    echo "Command: ${CMD[*]:0:200}..."
fi

# Execute
run_pipeline() {
    local start_time
    start_time=$(date +%s)
    local exit_code=0

    if "${CMD[@]}" > "$RUNS_DIR/${RUN_ID}-output.log" 2>&1; then
        exit_code=0
    else
        exit_code=$?
    fi

    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))

    # Write result summary
    python3 -c "
import json
result = {
    'runId': '$RUN_ID',
    'pipeline': '$PIPELINE',
    'steps': $STEP_COUNT,
    'timeout': $TIMEOUT,
    'exitCode': $exit_code,
    'durationSeconds': $duration,
    'status': 'success' if $exit_code == 0 else 'failed',
    'timestamp': '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
    'outputLog': '$RUNS_DIR/${RUN_ID}-output.log'
}
with open('$RESULT_FILE', 'w') as f:
    json.dump(result, f, indent=2)
print(json.dumps(result, indent=2))
"

    # Emit Loki event
    local event_file="$EVENTS_DIR/stream-chain-${RUN_ID}.json"
    python3 -c "
import json
status = 'success' if $exit_code == 0 else 'failed'
event = {
    'type': 'task_complete',
    'task': f'stream-chain/{status}: $PIPELINE ({$STEP_COUNT} steps, {$duration}s)',
    'source': 'stream-chain',
    'pipeline': '$PIPELINE',
    'runId': '$RUN_ID',
    'status': status,
    'durationSeconds': $duration,
    'timestamp': '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
}
with open('$event_file', 'w') as f:
    json.dump(event, f, indent=2)
"

    if [[ $exit_code -eq 0 ]]; then
        echo "Pipeline '$PIPELINE' completed successfully in ${duration}s"
    else
        echo "Pipeline '$PIPELINE' failed (exit code $exit_code) after ${duration}s" >&2
    fi

    return $exit_code
}

if $BACKGROUND; then
    echo "Running in background..."
    run_pipeline &
    echo "Background PID: $!"
else
    run_pipeline
fi
