#!/usr/bin/env bash
# RateShift load test runner — PRD Scope #8
# Usage: ./loadtest/run.sh [--quick]
#
# --quick  Runs a 30s smoke test at 30 VUs instead of the full 300 RPS / 5 min
#          profile. Use to verify k6 is wired before the real run.
#
# Required env vars:
#   BASE_URL      Target base URL (default: https://api.rateshift.app)
#   STAGING_KEY   Value of RATE_LIMIT_BYPASS_KEY (bypass rate limiting in staging)
#
# Optional:
#   K6_RESULTS_DIR  Directory to write result files (default: loadtest/results/)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BASE_URL="${BASE_URL:-https://api.rateshift.app}"
STAGING_KEY="${STAGING_KEY:-}"
RESULTS_DIR="${K6_RESULTS_DIR:-${PROJECT_ROOT}/loadtest/results}"
QUICK="${1:-}"

if ! command -v k6 &>/dev/null; then
  echo "❌  k6 not found. Install with:"
  echo "      brew install k6           # macOS"
  echo "      sudo apt install k6       # Debian/Ubuntu"
  echo "      choco install k6          # Windows"
  exit 1
fi

mkdir -p "${RESULTS_DIR}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
RESULT_FILE="${RESULTS_DIR}/run-${TIMESTAMP}.json"

echo "╔══════════════════════════════════════════════════╗"
echo "║  RateShift Load Test — PRD Scope #8              ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║  Target : ${BASE_URL}"
echo "║  Profile: $([ -n "${QUICK}" ] && echo '30s smoke (--quick)' || echo '300 RPS × 5 min (full)')"
echo "║  Results: ${RESULT_FILE}"
echo "╚══════════════════════════════════════════════════╝"
echo ""

if [ -z "${STAGING_KEY}" ]; then
  echo "⚠️  STAGING_KEY not set — rate limiting will not be bypassed."
  echo "   Set STAGING_KEY=<RATE_LIMIT_BYPASS_KEY> to avoid 429s distorting results."
  echo ""
fi

EXTRA_ARGS=()
if [ -n "${QUICK}" ]; then
  EXTRA_ARGS+=(
    "--stage" "0:30s:30"
    "--stage" "30s:30s:30"
    "--stage" "0:10s:0"
  )
fi

BASE_URL="${BASE_URL}" \
STAGING_KEY="${STAGING_KEY}" \
k6 run \
  --out "json=${RESULT_FILE}" \
  "${EXTRA_ARGS[@]}" \
  "${SCRIPT_DIR}/rateshift-staging.js"

EXIT_CODE=$?

echo ""
echo "Results written to: ${RESULT_FILE}"
echo "Symlinked to:       ${RESULTS_DIR}/latest.json"
ln -sf "run-${TIMESTAMP}.json" "${RESULTS_DIR}/latest.json"

exit ${EXIT_CODE}
