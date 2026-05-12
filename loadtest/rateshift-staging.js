/**
 * RateShift Staging Load Test
 *
 * Target: 300 RPS sustained for 5 minutes against the CF Worker / Render Starter stack.
 * PRD Scope #8 — must complete by 2026-05-22; results gate the Jun 2 PH rehearsal.
 *
 * Design notes
 * ------------
 * - 300 RPS = 2× estimated PH-day peak (~150 RPS) for B2C tools (safety margin)
 * - 30% cache-miss ratio: signup/forecast endpoints bypass CF cache, so 90 of
 *   300 RPS reaches Render origin. This is the stress vector.
 * - Endpoint mix reflects realistic PH-day traffic (heavy on /health, prices,
 *   auth/signup; zero real user writes in staging — fake data only)
 * - Thresholds match PRD abort thresholds §15:
 *     - http_req_failed rate < 5%
 *     - p95 < 3 000 ms (matches "p95 >3s → page + roll back" abort rule)
 * - /health probes are high-frequency but cheap; they stress the rate limiter
 *   bypass path (rateLimit:"bypass") and confirm Render is alive throughout
 *
 * Run instructions
 * ----------------
 *   brew install k6                          # macOS
 *   export BASE_URL=https://api.rateshift.app
 *   export STAGING_KEY=<RATE_LIMIT_BYPASS_KEY>
 *   k6 run --out json=results.json loadtest/rateshift-staging.js
 *
 * Interpreting results
 * --------------------
 * Pass criteria (both must be green):
 *   ✅  http_req_failed  < 5%   (p50/p95/p99 < 5000ms is implied by the threshold below)
 *   ✅  http_req_duration p95 < 3 000 ms
 * Record the p95 value as the "p95 baseline" in the PRD success metrics table.
 *
 * If test fails
 * -------------
 *   1. Check CF Worker /api/v1/internal/gateway-stats for cache hit rate drop
 *   2. Check Render metrics for CPU/memory saturation (Starter = 512MB RAM)
 *   3. Reduce VUs to find the saturation point — report as "max sustainable RPS"
 *   4. If origin p95 > 3s → recommend Render Standard upgrade (Scope #2)
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const BASE_URL = __ENV.BASE_URL || "https://api.rateshift.app";
// Pass as env var; never hardcode bypass key in source
const BYPASS_KEY = __ENV.STAGING_KEY || "";

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------

const cacheHitRate = new Rate("cache_hit_rate");
const originLatency = new Trend("origin_latency_ms");
const errorRate = new Rate("error_rate");

// ---------------------------------------------------------------------------
// Load profile
//
// Ramp: 0 → 300 VUs over 60s (gradual to prevent cold-start spike distortion)
// Sustain: 300 VUs for 5 min (captures steady-state throughput + p95)
// Ramp-down: 300 → 0 over 30s (graceful drain)
//
// Approximate RPS at 300 VUs with ~1s average request time + minimal sleep:
//   300 VUs × ~1 req/s = ~300 RPS
// ---------------------------------------------------------------------------

export const options = {
  stages: [
    { duration: "60s", target: 300 },
    { duration: "300s", target: 300 },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    // PRD abort threshold: p95 > 3s → rollback
    http_req_duration: ["p(95)<3000"],
    // PRD abort threshold: error rate > 5% over 10 min → investigate
    http_req_failed: ["rate<0.05"],
    error_rate: ["rate<0.05"],
  },
};

// ---------------------------------------------------------------------------
// Endpoint pool
//
// Mix represents realistic PH-day traffic distribution.
// Cacheable endpoints use random query params to exercise both HIT and MISS paths.
// Cache-miss ratio target: ~30% (90/300 RPS reach origin).
// ---------------------------------------------------------------------------

const STATES = ["us_ct", "us_ny", "us_ma", "us_pa", "us_nj"];
const UTILITY_TYPES = ["electric", "gas"];

function randomState() {
  return STATES[Math.floor(Math.random() * STATES.length)];
}

function randomUtility() {
  return UTILITY_TYPES[Math.floor(Math.random() * UTILITY_TYPES.length)];
}

// ---------------------------------------------------------------------------
// Request helpers
// ---------------------------------------------------------------------------

function getHeaders(extraHeaders = {}) {
  const h = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  if (BYPASS_KEY) {
    h["X-Rate-Limit-Bypass"] = BYPASS_KEY;
  }
  return Object.assign(h, extraHeaders);
}

function recordMetrics(res) {
  const isCacheHit = res.headers["X-Cache"] === "HIT";
  const isError = res.status >= 500;
  const isFailed = res.status >= 400;
  cacheHitRate.add(isCacheHit ? 1 : 0);
  errorRate.add(isFailed ? 1 : 0);
  if (!isCacheHit) {
    originLatency.add(res.timings.duration);
  }
  return { isCacheHit, isError };
}

// ---------------------------------------------------------------------------
// VU scenario
//
// Each VU randomly picks from the endpoint pool on each iteration.
// The distribution below approximates PH-day traffic:
//   35% — /health (cheap, high-frequency; exercises bypass path)
//   25% — /api/v1/prices/current (cacheable; populates cache on first miss)
//   15% — /api/v1/prices/history (cacheable, less frequent)
//   10% — /api/v1/suppliers (cacheable)
//    5% — /api/v1/public/rates/<state>/<utility_type> (SEO endpoint, cacheable)
//    5% — /api/v1/auth/session (non-cacheable, strict rate limit)
//    5% — /api/v1/public/unsubscribe?uid=test&tok=invalid (expects 400, tests bypass)
// ---------------------------------------------------------------------------

export default function () {
  const rand = Math.random();

  if (rand < 0.35) {
    // /health — bypass rate limit, never cached
    const res = http.get(`${BASE_URL}/health`, { headers: getHeaders() });
    const { isError } = recordMetrics(res);
    check(res, { "/health 200": (r) => r.status === 200 });
    if (isError) {
      console.error(`/health returned ${res.status}`);
    }
  } else if (rand < 0.60) {
    // /prices/current — cacheable (5 min TTL), vary on region + utility_type
    const state = randomState();
    const util = randomUtility();
    const res = http.get(
      `${BASE_URL}/api/v1/prices/current?region=${state}&utility_type=${util}`,
      { headers: getHeaders() }
    );
    recordMetrics(res);
    check(res, {
      "prices/current 2xx": (r) => r.status >= 200 && r.status < 300,
    });
  } else if (rand < 0.75) {
    // /prices/history — cacheable (30 min TTL)
    const state = randomState();
    const res = http.get(
      `${BASE_URL}/api/v1/prices/history?region=${state}&days=30`,
      { headers: getHeaders() }
    );
    recordMetrics(res);
    check(res, {
      "prices/history 2xx": (r) => r.status >= 200 && r.status < 300,
    });
  } else if (rand < 0.85) {
    // /suppliers — cacheable (1 hr TTL)
    const state = randomState();
    const util = randomUtility();
    const res = http.get(
      `${BASE_URL}/api/v1/suppliers?region=${state}&utility_type=${util}`,
      { headers: getHeaders() }
    );
    recordMetrics(res);
    check(res, {
      "suppliers 2xx": (r) => r.status >= 200 && r.status < 300,
    });
  } else if (rand < 0.90) {
    // /public/rates — SEO endpoint, cacheable
    const state = randomState();
    const util = randomUtility();
    const res = http.get(
      `${BASE_URL}/api/v1/public/rates/${state}/${util}`,
      { headers: getHeaders() }
    );
    recordMetrics(res);
    check(res, {
      "public/rates 2xx/404": (r) => r.status === 200 || r.status === 404,
    });
  } else if (rand < 0.95) {
    // /auth/session — non-cacheable, strict rate limit
    // Uses GET (read-only, no session side-effect)
    const res = http.get(`${BASE_URL}/api/v1/auth/session`, {
      headers: getHeaders(),
    });
    recordMetrics(res);
    // Expects 401 in staging (not authenticated) — still validates the path returns quickly
    check(res, {
      "auth/session responds": (r) => r.status === 401 || r.status === 200,
    });
  } else {
    // /public/unsubscribe with invalid token — validates 400 fast path
    const res = http.get(
      `${BASE_URL}/api/v1/public/unsubscribe?uid=00000000-0000-0000-0000-000000000000&tok=invalid00000000000000000000000000`,
      { headers: getHeaders() }
    );
    recordMetrics(res);
    check(res, { "unsubscribe 400": (r) => r.status === 400 });
  }

  // Minimal think-time: 0–100ms random jitter to avoid thundering-herd
  // Keep it short so 300 VUs sustain ~300 RPS (not limited by sleep)
  sleep(Math.random() * 0.1);
}

// ---------------------------------------------------------------------------
// Summary handler — print pass/fail against PRD thresholds
// ---------------------------------------------------------------------------

export function handleSummary(data) {
  const p95 = data.metrics.http_req_duration?.values?.["p(95)"] ?? 0;
  const failRate = data.metrics.http_req_failed?.values?.rate ?? 0;
  const hitRate = data.metrics.cache_hit_rate?.values?.rate ?? 0;
  const originP95 = data.metrics.origin_latency_ms?.values?.["p(95)"] ?? 0;

  const p95Pass = p95 < 3000;
  const failPass = failRate < 0.05;

  const summary = [
    "",
    "═══════════════════════════════════════════════════════",
    " RateShift Load Test — PRD Scope #8 Results",
    "═══════════════════════════════════════════════════════",
    `  http p95 latency  : ${p95.toFixed(0)} ms   ${p95Pass ? "✅ PASS" : "❌ FAIL (threshold: <3000ms)"}`,
    `  http error rate   : ${(failRate * 100).toFixed(2)}%    ${failPass ? "✅ PASS" : "❌ FAIL (threshold: <5%)"}`,
    `  CF cache hit rate : ${(hitRate * 100).toFixed(1)}%`,
    `  origin p95        : ${originP95.toFixed(0)} ms  (cache-miss requests only)`,
    "",
    p95Pass && failPass
      ? "  🚀 OVERALL: PASS — proceed to PRD §11 telemetry check"
      : "  🛑 OVERALL: FAIL — see runbook docs/runbooks/load-test.md",
    "═══════════════════════════════════════════════════════",
    "",
  ].join("\n");

  console.log(summary);

  return {
    stdout: summary,
    "loadtest/results-latest.json": JSON.stringify(data, null, 2),
  };
}
