#!/usr/bin/env bash
# CF Worker Cache Soak Check — PRD Scope #11
#
# Purpose: Verify CF Worker cache health at the 7-day soak mark (2026-05-19).
# Run manually: bash scripts/cf-worker-soak-check.sh
#
# Checks:
#   1. Gateway stats endpoint (cache hit rate, request counts)
#   2. Spot-check 504/499 error rates via direct curl timing
#   3. HEAD /health to confirm cache bypass is working (no stale health responses)
#   4. GET /api/v1/prices/current — should be a cache HIT on second call
#
# Prerequisites:
#   - INTERNAL_API_KEY: gateway internal auth key (from 1Password "RateShift — INTERNAL_API_KEY")
#   - curl, jq

set -euo pipefail

GATEWAY="https://api.rateshift.app"
INTERNAL_KEY="${INTERNAL_API_KEY:-}"

# ---------------------------------------------------------------------------
echo "=== CF Worker Cache Soak Check ($(date -u '+%Y-%m-%dT%H:%M:%SZ')) ==="
echo ""

# ---------------------------------------------------------------------------
# 1. Gateway stats (requires internal key)
# ---------------------------------------------------------------------------
echo "--- 1. Gateway stats ---"
if [ -z "${INTERNAL_KEY}" ]; then
  echo "  ⚠️  INTERNAL_API_KEY not set — skipping gateway-stats endpoint."
  echo "     Export: INTERNAL_API_KEY=\$(op read 'op://RateShift/INTERNAL_API_KEY/credential')"
else
  STATS=$(curl -sf -H "X-Internal-API-Key: ${INTERNAL_KEY}" \
    "${GATEWAY}/internal/gateway-stats" 2>&1 || echo "ERROR: $?")

  if echo "${STATS}" | jq . >/dev/null 2>&1; then
    echo "  Raw stats JSON:"
    echo "${STATS}" | jq '{
      cache_hit_rate:    .cache_hit_rate,
      total_requests:    .total_requests,
      cache_hits:        .cache_hits,
      cache_misses:      .cache_misses,
      errors_504:        .errors_504,
      errors_499:        .errors_499,
      kv_cost_trend:     .kv_cost_trend
    }'

    HIT_RATE=$(echo "${STATS}" | jq -r '.cache_hit_rate // "N/A"')
    echo ""
    echo "  Cache hit rate: ${HIT_RATE}"

    # Warn if below 70% threshold from load test spec
    if [ "${HIT_RATE}" != "N/A" ]; then
      RATE_INT=$(echo "${HIT_RATE}" | sed 's/%//' | cut -d. -f1)
      if [ "${RATE_INT}" -lt 70 ] 2>/dev/null; then
        echo "  ⚠️  WARN: Cache hit rate ${HIT_RATE} is below 70% threshold. Review caching headers."
      else
        echo "  ✓ Cache hit rate is acceptable (≥70%)."
      fi
    fi
  else
    echo "  ✗ Could not parse gateway stats: ${STATS}"
  fi
fi

echo ""

# ---------------------------------------------------------------------------
# 2. HEAD /health — must NOT be cached (bypass rule)
# ---------------------------------------------------------------------------
echo "--- 2. /health HEAD probe (should not be cached) ---"
HEALTH_HEADERS=$(curl -sI -X HEAD "${GATEWAY}/health" 2>&1)
echo "${HEALTH_HEADERS}" | grep -iE "cf-cache-status|cache-control|x-cache" || echo "  (no cache headers found)"
CF_STATUS=$(echo "${HEALTH_HEADERS}" | grep -i "cf-cache-status" | awk '{print $2}' | tr -d '\r')
if [ "${CF_STATUS}" = "HIT" ]; then
  echo "  ✗ ERROR: /health is being cached (CF-Cache-Status: HIT). Cache bypass rule is broken!"
elif [ -n "${CF_STATUS}" ]; then
  echo "  ✓ /health cache status: ${CF_STATUS} (expected BYPASS or MISS, not HIT)"
else
  echo "  ℹ️  No CF-Cache-Status header on /health (may be Cloudflare plan limitation)"
fi
echo ""

# ---------------------------------------------------------------------------
# 3. GET /api/v1/prices/current — second call should be cached
# ---------------------------------------------------------------------------
echo "--- 3. GET /api/v1/prices/current (two calls — expect second = HIT) ---"
echo "  Call 1:"
R1=$(curl -sI "${GATEWAY}/api/v1/prices/current" 2>&1)
echo "${R1}" | grep -iE "cf-cache-status|cache-control|http/[12]" || true

echo "  Call 2 (1s later):"
sleep 1
R2=$(curl -sI "${GATEWAY}/api/v1/prices/current" 2>&1)
echo "${R2}" | grep -iE "cf-cache-status|cache-control|http/[12]" || true

CF2=$(echo "${R2}" | grep -i "cf-cache-status" | awk '{print $2}' | tr -d '\r')
if [ "${CF2}" = "HIT" ]; then
  echo "  ✓ Second call is a cache HIT — cache is working."
elif [ "${CF2}" = "MISS" ]; then
  echo "  ⚠️  Second call is a cache MISS — prices/current may not be cacheable. Check Cache-Control header."
elif [ -n "${CF2}" ]; then
  echo "  ℹ️  Second call CF-Cache-Status: ${CF2}"
else
  echo "  ℹ️  No CF-Cache-Status on prices/current"
fi
echo ""

# ---------------------------------------------------------------------------
# 4. Latency spot-check (3 requests, report p95 estimate)
# ---------------------------------------------------------------------------
echo "--- 4. Latency spot-check (3 requests to /api/v1/prices/current) ---"
TIMES=()
for i in 1 2 3; do
  T=$(curl -so /dev/null -w "%{time_total}" "${GATEWAY}/api/v1/prices/current")
  echo "  Request ${i}: ${T}s"
  TIMES+=("${T}")
done
# Simple max as p100 proxy (bash doesn't do floats natively)
MAX=$(printf '%s\n' "${TIMES[@]}" | sort -rn | head -1)
echo "  Max latency: ${MAX}s (target p95 < 3.0s)"
echo ""

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------
echo "=== Soak Check Summary ==="
echo "  Date:     $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "  Gateway:  ${GATEWAY}"
echo "  Soak started: 2026-05-11 (CF Worker cache tuning deployed)"
echo "  Check date:   $(date -u '+%Y-%m-%d') (target: 2026-05-19)"
echo ""
echo "  ✅ Actions to record in docs/launch/cf-worker-soak-results.md:"
echo "     - Cache hit rate from step 1"
echo "     - /health cache bypass confirmed (step 2)"
echo "     - prices/current caching status (step 3)"
echo "     - Max latency observed (step 4)"
echo ""
echo "  If all green: mark Scope #11 COMPLETE in PRD checklist."
echo "  If any failure: open GitHub issue tagged 'launch-blocker'."
