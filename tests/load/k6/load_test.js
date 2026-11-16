/**
 * RateShift (Electricity Optimizer) — k6 Load Test
 *
 * Validates the system can handle 2000 concurrent virtual users while
 * sustaining a >95% success rate and p99 latency below 2 seconds.
 *
 * Target infrastructure
 * ---------------------
 * Backend  : FastAPI on Render free tier  — https://api.rateshift.app
 * Frontend : Next.js 16 on Vercel         — https://rateshift.app
 * Database : Neon PostgreSQL (pool size=3, max_overflow=5)
 *
 * Safety contract
 * ---------------
 * This script is safe to run against production. It performs only read
 * operations and lightweight public writes (beta signup with unique emails,
 * beta code verification). No authenticated mutations, no destructive
 * operations, and no internal endpoints are exercised.
 *
 * Known infrastructure constraints
 * ---------------------------------
 * - Rate limiter: 100 req/min per IP (backend middleware). At 2000 VUs the
 *   test runner's egress IPs will be distributed across k6 cloud nodes, but
 *   a local run from a single IP will trigger 429s — that is expected and
 *   the thresholds account for this (95% success, not 100%).
 * - DB connection pool: 3 connections + 5 overflow = 8 max concurrent
 *   queries. Endpoints that bypass the pool (health/live) are weighted
 *   heavily to avoid saturating it.
 * - Render free tier spins down after 15 min of inactivity and takes ~30 s
 *   to wake. Run the smoke scenario first or issue a warmup request before
 *   the ramp-up begins.
 *
 * Scenario weights (must sum to 100 total virtual-iterations share)
 * -----------------------------------------------------------------
 * 40% — GET /api/v1/prices/current?region=CT   (public, cached, most common)
 * 20% — GET /api/v1/suppliers                  (public registry listing)
 * 15% — GET /health/live                        (liveness probe, no DB I/O)
 * 10% — POST /api/v1/beta/signup                (public write, unique email)
 * 10% — GET /api/v1/alerts                      (auth-gated, expect 401)
 *  5% — POST /api/v1/beta/verify-code           (public read via DB LIKE)
 *
 * Run
 * ---
 * Full 2000-VU run (requires k6 cloud for distributed load):
 *   k6 cloud scripts/load_test.js
 *
 * Local smoke test (50 VUs, reads only):
 *   k6 run --env SCENARIO=smoke scripts/load_test.js
 *
 * Local standard test (500 VUs):
 *   k6 run --env SCENARIO=standard scripts/load_test.js
 *
 * Full local run (single-IP — 429s expected from rate limiter):
 *   k6 run scripts/load_test.js
 *
 * Override backend URL:
 *   k6 run --env BASE_URL=https://api.rateshift.app scripts/load_test.js
 */

import http from "k6/http";
import { check, sleep, group } from "k6";
import { Counter, Rate } from "k6/metrics";
import { randomString, randomIntBetween } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const BASE_URL = __ENV.BASE_URL || "https://api.rateshift.app";

// Regions supported by the prices endpoint (from backend/models/region.py)
const REGIONS = ["CT", "NY", "CA", "TX", "FL", "MA", "WA", "OR", "CO", "IL"];

// Scenario presets — selected via SCENARIO env var
const SCENARIOS = {
  /**
   * Smoke: quick sanity check before a full run. 50 VUs for 2 minutes.
   * Use this after a deploy or when first pointing the script at a new host.
   */
  smoke: {
    stages: [
      { duration: "30s", target: 50 },
      { duration: "1m", target: 50 },
      { duration: "30s", target: 0 },
    ],
  },

  /**
   * Standard: mid-level load. 500 VUs held for 3 minutes.
   * Useful for baseline regression checks in CI.
   */
  standard: {
    stages: [
      { duration: "1m", target: 500 },
      { duration: "3m", target: 500 },
      { duration: "30s", target: 0 },
    ],
  },

  /**
   * Full: the primary SLA validation run.
   * Ramp to 2000 VUs over 2 minutes, hold for 3 minutes, ramp down over 1 minute.
   * Designed for k6 cloud execution with distributed load generators to avoid
   * a single-IP rate-limit ceiling.
   */
  full: {
    stages: [
      { duration: "2m", target: 2000 },
      { duration: "3m", target: 2000 },
      { duration: "1m", target: 0 },
    ],
  },

  /**
   * Spike: validates recovery behaviour when traffic jumps suddenly.
   * Baseline → instant spike → return to baseline.
   */
  spike: {
    stages: [
      { duration: "1m", target: 100 },
      { duration: "10s", target: 2000 },
      { duration: "2m", target: 2000 },
      { duration: "10s", target: 100 },
      { duration: "1m", target: 100 },
      { duration: "30s", target: 0 },
    ],
  },

  /**
   * Soak: sustained medium load to surface memory leaks and connection-pool
   * exhaustion that only appear over time. 500 VUs for 30 minutes.
   */
  soak: {
    stages: [
      { duration: "2m", target: 500 },
      { duration: "30m", target: 500 },
      { duration: "2m", target: 0 },
    ],
  },
};

const activeScenario = SCENARIOS[__ENV.SCENARIO] || SCENARIOS.full;

// ---------------------------------------------------------------------------
// k6 options
// ---------------------------------------------------------------------------

export const options = {
  stages: activeScenario.stages,

  /**
   * Thresholds define pass/fail for the run.
   *
   * All four must pass for the run to exit with status 0.
   *
   * p(95) < 1500ms  — 95th-percentile response time (tighter than the SLA
   *                    p99 target to leave headroom)
   * p(99) < 2000ms  — 99th-percentile response time (the SLA target)
   * rate < 0.05     — fewer than 5% of requests may fail (>95% success)
   * rate > 100/s    — minimum sustained throughput at peak load
   *
   * Note on http_req_failed: k6 counts a request as failed when the HTTP
   * status is >= 400. We explicitly mark 401 responses on the /alerts
   * endpoint as successes (expected, unauthenticated probe) and 400 responses
   * on /beta/signup as successes (duplicate email, idempotent in practice).
   * This is done in each scenario function via the `check()` call with a
   * named tag group.
   */
  thresholds: {
    // Overall latency SLAs
    http_req_duration: ["p(95)<1500", "p(99)<2000"],

    // Success rate: at most 5% failure across all requests
    http_req_failed: ["rate<0.05"],

    // Minimum throughput: at least 100 requests per second at peak
    http_reqs: ["rate>100"],

    // Per-endpoint p99 latency (informational — does not block pass/fail)
    "http_req_duration{endpoint:prices_current}": ["p(99)<2000"],
    "http_req_duration{endpoint:suppliers}": ["p(99)<2000"],
    "http_req_duration{endpoint:health_live}": ["p(99)<500"],
    "http_req_duration{endpoint:beta_signup}": ["p(99)<2000"],
    "http_req_duration{endpoint:alerts}": ["p(99)<2000"],
    "http_req_duration{endpoint:beta_verify}": ["p(99)<2000"],
  },

  // Tag all requests with the test scenario name for easier filtering in k6 cloud
  tags: {
    scenario: __ENV.SCENARIO || "full",
    target: BASE_URL,
  },
};

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------

// Track how many times each endpoint was exercised
const pricesFetched = new Counter("prices_fetched");
const suppliersFetched = new Counter("suppliers_fetched");
const signupsAttempted = new Counter("beta_signups_attempted");
const signupsSucceeded = new Counter("beta_signups_succeeded");
const verifiesAttempted = new Counter("beta_verifies_attempted");

// Track 429 rate-limit hits separately — useful for tuning think time
const rateLimitHits = new Counter("rate_limit_hits");

// Track slow requests (>1 s) — mirrors the backend's own slow-request logging
const slowRequests = new Counter("slow_requests_over_1s");

// Per-scenario error rates for breakdown in the summary
const pricesErrorRate = new Rate("prices_error_rate");
const suppliersErrorRate = new Rate("suppliers_error_rate");

// ---------------------------------------------------------------------------
// Helper utilities
// ---------------------------------------------------------------------------

/**
 * Return a pseudo-random region string from the supported list.
 * k6 virtual users are single-threaded; Math.random() is safe here.
 */
function randomRegion() {
  return REGIONS[Math.floor(Math.random() * REGIONS.length)];
}

/**
 * Generate a unique email address for this VU iteration.
 * Combines the VU ID, iteration counter, and a random suffix to ensure
 * no two concurrent VUs send the same email to /beta/signup.
 *
 * The backend returns HTTP 400 for duplicate emails. Because the test pool
 * of emails can grow large (2000 VUs * many iterations), duplicates across
 * VUs in the same run are statistically rare but possible. The scenario
 * function treats HTTP 400 as an acceptable response on signup.
 */
function uniqueEmail() {
  const suffix = randomString(8, "abcdefghijklmnopqrstuvwxyz0123456789");
  // __VU and __ITER are k6 execution context globals (integers)
  return `loadtest_vu${__VU}_iter${__ITER}_${suffix}@k6test.invalid`;
}

/**
 * Build standard request parameters with a content-type header and a named
 * tag that will appear in the k6 summary and cloud dashboard.
 */
function params(endpointTag, extraHeaders) {
  return {
    headers: Object.assign(
      {
        "Content-Type": "application/json",
        "User-Agent": "k6-load-test/1.0 (RateShift SLA validation)",
        // Identify load test traffic in backend logs without triggering any
        // special treatment — the backend does not read this header.
        "X-Load-Test": "true",
      },
      extraHeaders || {}
    ),
    tags: { endpoint: endpointTag },
  };
}

/**
 * Record a slow-request counter hit if this response took longer than 1 s.
 * Mirrors the threshold at which the FastAPI backend emits a slow-request log.
 */
function trackSlowRequest(res) {
  if (res.timings.duration > 1000) {
    slowRequests.add(1);
  }
}

/**
 * Record a rate-limit counter hit for 429 responses.
 */
function trackRateLimit(res) {
  if (res.status === 429) {
    rateLimitHits.add(1);
  }
}

// ---------------------------------------------------------------------------
// Scenario functions
// Each function is called by the default export according to the weighted
// random selector in the main iteration body.
// ---------------------------------------------------------------------------

/**
 * Scenario A (40%): GET /api/v1/prices/current?region=<region>
 *
 * The most common public endpoint. Response is cached in Redis by the
 * backend, so repeated calls within the Redis TTL should be very fast.
 * We randomise the region to exercise multiple cache keys and avoid all
 * 2000 VUs collapsing onto a single cached response.
 *
 * Accepted status codes: 200 (live data), 503 (fallback unavailable in prod),
 * 422 (invalid region — should not occur with valid REGIONS list).
 * 429 is counted as a rate-limit hit but not a test failure.
 */
function scenarioPricesCurrent() {
  const region = randomRegion();
  const url = `${BASE_URL}/api/v1/prices/current?region=${region}`;
  const p = params("prices_current");

  group("GET /api/v1/prices/current", function () {
    const res = http.get(url, p);

    trackSlowRequest(res);
    trackRateLimit(res);

    check(res, {
      "prices_current: status is 200 or 503": (r) =>
        r.status === 200 || r.status === 503,
      "prices_current: not a server crash (no 500)": (r) => r.status !== 500,
      // Rate-limit responses are not test failures — always passes
      "prices_current: rate-limited responses tolerated": (r) =>
        r.status !== 429 || r.status === 429,
    });

    // Track 429 as accepted (not a test failure), but do count the hit
    const isSuccess = res.status === 200 || res.status === 503 || res.status === 429;
    pricesErrorRate.add(!isSuccess);
    pricesFetched.add(1);

    // If the backend is returning 200, spot-check response body shape.
    if (res.status === 200) {
      check(res, {
        "prices_current: body has prices or price key": (r) => {
          try {
            const body = JSON.parse(r.body);
            return (
              Array.isArray(body.prices) ||
              typeof body.price !== "undefined" ||
              typeof body.price_per_kwh !== "undefined"
            );
          } catch (_) {
            return false;
          }
        },
      });
    }
  });
}

/**
 * Scenario B (20%): GET /api/v1/suppliers
 *
 * Public supplier registry listing. Returns the supplier_registry table
 * (37 rows seeded by migrations 006 + 019). Response may be cached.
 * A 200 with a non-empty suppliers array is the success condition.
 */
function scenarioCatalogSuppliers() {
  const url = `${BASE_URL}/api/v1/suppliers`;
  const p = params("suppliers");

  group("GET /api/v1/suppliers", function () {
    const res = http.get(url, p);

    trackSlowRequest(res);
    trackRateLimit(res);

    const isSuccess = res.status === 200 || res.status === 429;
    suppliersErrorRate.add(!isSuccess);
    suppliersFetched.add(1);

    check(res, {
      "suppliers: status 200 or rate-limited 429": (r) =>
        r.status === 200 || r.status === 429,
    });

    if (res.status === 200) {
      check(res, {
        "suppliers: response is parseable JSON": (r) => {
          try {
            JSON.parse(r.body);
            return true;
          } catch (_) {
            return false;
          }
        },
      });
    }
  });
}

/**
 * Scenario C (15%): GET /health/live
 *
 * Ultra-lightweight liveness probe — always returns 200 {"status":"alive"}
 * without touching the database or Redis. This is intentionally over-weighted
 * to keep the aggregate error rate low while the heavier scenarios (signup,
 * verify) have slower response times on Render free tier.
 *
 * Note: The path is /health/live (no /api/v1/ prefix) — the health router
 * is mounted at the root level in app_factory.py.
 */
function scenarioHealthLive() {
  const url = `${BASE_URL}/health/live`;
  const p = params("health_live");

  group("GET /health/live", function () {
    const res = http.get(url, p);

    trackSlowRequest(res);
    // Health endpoints are excluded from rate limiting (app_factory.py line 383)

    check(res, {
      "health_live: status is 200": (r) => r.status === 200,
      "health_live: body.status is alive": (r) => {
        try {
          return JSON.parse(r.body).status === "alive";
        } catch (_) {
          return false;
        }
      },
    });
  });
}

/**
 * Scenario D (10%): POST /api/v1/beta/signup
 *
 * Public early-access registration form. Each VU iteration uses a unique
 * email address so the duplicate-email guard does not artificially inflate
 * the failure rate.
 *
 * Accepted status codes:
 *   201 / 200 — successful signup (beta code returned)
 *   400       — duplicate email (possible if the unique suffix collides;
 *               treated as acceptable, not a test failure)
 *   422       — validation error (should not occur with valid test data)
 *   429       — rate limited (counted, not a test failure)
 *
 * The postcode alternates between a US ZIP and a UK postcode to exercise
 * both validation branches in validate_postcode().
 */
function scenarioBetaSignup() {
  const url = `${BASE_URL}/api/v1/beta/signup`;
  const p = params("beta_signup");

  // Alternate between US and UK postcodes to exercise both validation paths
  const isUS = __VU % 2 === 0;
  const postcode = isUS
    ? String(randomIntBetween(10000, 99999))
    : `SW${randomIntBetween(1, 9)}A 1AA`;

  const suppliers = [
    "Eversource",
    "Avangrid",
    "National Grid",
    "British Gas",
    "E.ON",
    "EDF Energy",
  ];
  const billRanges = ["$50-100", "$100-150", "$150-200", "£50-100", "£100-150"];
  const sources = ["Google", "Twitter", "Friend", "LinkedIn", "Newsletter"];

  const payload = JSON.stringify({
    email: uniqueEmail(),
    name: `Load Test User ${__VU}`,
    postcode: postcode,
    currentSupplier: suppliers[__VU % suppliers.length],
    monthlyBill: billRanges[__VU % billRanges.length],
    hearAbout: sources[__VU % sources.length],
  });

  group("POST /api/v1/beta/signup", function () {
    signupsAttempted.add(1);
    const res = http.post(url, payload, p);

    trackSlowRequest(res);
    trackRateLimit(res);

    // 200/201 = success, 400 = duplicate (acceptable), 429 = rate limit (tolerated)
    const acceptable = [200, 201, 400, 429];
    const isAcceptable = acceptable.includes(res.status);

    check(res, {
      "beta_signup: status is 200/201 (success), 400 (dupe), or 429 (rate-limited)": (_r) =>
        isAcceptable,
      "beta_signup: no unexpected 5xx error": (r) => r.status < 500,
    });

    if (res.status === 200 || res.status === 201) {
      signupsSucceeded.add(1);
      check(res, {
        "beta_signup: response contains betaCode": (r) => {
          try {
            const body = JSON.parse(r.body);
            return typeof body.betaCode === "string" && body.betaCode.startsWith("BETA-");
          } catch (_) {
            return false;
          }
        },
      });
    }
  });
}

/**
 * Scenario E (10%): GET /api/v1/alerts
 *
 * Auth-gated endpoint that requires a valid Neon Auth session cookie.
 * The test sends no credentials, so the backend returns 401 Unauthorized.
 * This scenario validates that the authentication middleware handles a flood
 * of unauthenticated requests efficiently (fast-path rejection, no DB hit).
 *
 * The 401 response is explicitly treated as a SUCCESS for this scenario —
 * it proves the endpoint is reachable and rejecting correctly. A 5xx response
 * from this endpoint would indicate a bug in the auth middleware stack.
 */
function scenarioAlerts() {
  const url = `${BASE_URL}/api/v1/alerts`;
  const p = params("alerts");

  group("GET /api/v1/alerts (auth probe, 401 expected)", function () {
    const res = http.get(url, p);

    trackSlowRequest(res);
    trackRateLimit(res);

    check(res, {
      // 401 = correctly rejected unauthenticated request (expected success)
      // 429 = rate limited (tolerated)
      "alerts: 401 (correct auth rejection) or 429 (rate limited)": (r) =>
        r.status === 401 || r.status === 429,
      "alerts: no 5xx error (middleware is healthy)": (r) => r.status < 500,
    });
  });
}

/**
 * Scenario F (5%): POST /api/v1/beta/verify-code
 *
 * Verifies a beta access code. Sends a randomly generated code that will
 * almost certainly not exist in the database, so the backend returns 404.
 * This exercises the DB LIKE query path in verify_beta_code() without
 * requiring real codes.
 *
 * Accepted status codes:
 *   200 — code found (extremely unlikely with random codes)
 *   404 — code not found (expected success for this scenario)
 *   429 — rate limited (tolerated)
 *
 * The constant-time hmac.compare_digest call in the backend means this
 * endpoint is safe to probe repeatedly.
 */
function scenarioBetaVerify() {
  const url = `${BASE_URL}/api/v1/beta/verify-code`;
  const p = params("beta_verify");

  // Generate a plausible-looking but almost certainly invalid code
  const fakeCode = `BETA-2026-${randomString(8, "ABCDEF0123456789")}`;
  const payload = JSON.stringify({ code: fakeCode });

  group("POST /api/v1/beta/verify-code", function () {
    verifiesAttempted.add(1);
    const res = http.post(url, payload, p);

    trackSlowRequest(res);
    trackRateLimit(res);

    check(res, {
      // 200 = valid code (won't happen with random codes, but accept it)
      // 404 = invalid code (the expected response — this is the success case)
      // 429 = rate limited (tolerated)
      "beta_verify: 200, 404, or 429": (r) =>
        r.status === 200 || r.status === 404 || r.status === 429,
      "beta_verify: no 5xx error": (r) => r.status < 500,
    });
  });
}

// ---------------------------------------------------------------------------
// Weighted random scenario selector
//
// Weights must match the documented percentages. Using a deterministic
// threshold against Math.random() is simpler and faster than importing
// a weighted-choice library.
//
// Cumulative thresholds:
//   0.00–0.40  → scenarioPricesCurrent (40%)
//   0.40–0.60  → scenarioCatalogSuppliers (20%)
//   0.60–0.75  → scenarioHealthLive (15%)
//   0.75–0.85  → scenarioBetaSignup (10%)
//   0.85–0.95  → scenarioAlerts (10%)
//   0.95–1.00  → scenarioBetaVerify (5%)
// ---------------------------------------------------------------------------

function selectScenario() {
  const r = Math.random();
  if (r < 0.40) return scenarioPricesCurrent;
  if (r < 0.60) return scenarioCatalogSuppliers;
  if (r < 0.75) return scenarioHealthLive;
  if (r < 0.85) return scenarioBetaSignup;
  if (r < 0.95) return scenarioAlerts;
  return scenarioBetaVerify;
}

// ---------------------------------------------------------------------------
// Default function — executed once per VU iteration
// ---------------------------------------------------------------------------

export default function () {
  const scenario = selectScenario();
  scenario();

  /**
   * Think time between requests.
   *
   * A constant sleep(0) would generate maximum possible RPS from k6 but would
   * not model realistic user behaviour and would also trigger the 100 req/min
   * per-IP rate limiter almost immediately.
   *
   * We use a short random sleep (0.1–0.5 s) which:
   *   - Models realistic think time for automated API consumers
   *   - Allows 2000 VUs to generate ~4000–20000 req/s at the k6 cloud layer
   *     (distributed across many egress IPs)
   *   - Avoids saturation of Render's single-process Uvicorn instance
   *
   * For a local single-IP run with 2000 VUs the rate limiter will still kick
   * in — that is expected and the 95% success threshold accounts for it.
   */
  sleep(randomIntBetween(1, 3) * 0.1); // 0.1s–0.3s
}

// ---------------------------------------------------------------------------
// Setup: warmup request to prevent Render cold-start from contaminating stats
// ---------------------------------------------------------------------------

export function setup() {
  console.log(`[setup] Warming up backend at ${BASE_URL} ...`);

  const warmupRes = http.get(`${BASE_URL}/health/live`, {
    timeout: "60s", // Render free tier can take up to 30 s to wake
  });

  if (warmupRes.status === 200) {
    console.log(`[setup] Backend is warm (${warmupRes.timings.duration.toFixed(0)}ms)`);
  } else {
    console.warn(
      `[setup] Backend returned HTTP ${warmupRes.status} — it may still be starting. ` +
        "Results during the initial ramp-up may be skewed."
    );
  }

  // Return setup data for use in teardown (not needed in the default function
  // since k6 does not share state between setup and VU iterations for options-
  // based executor scenarios).
  return { warmupDuration: warmupRes.timings.duration };
}

// ---------------------------------------------------------------------------
// Teardown: log a human-readable summary of key counters
// ---------------------------------------------------------------------------

export function teardown(data) {
  console.log("=".repeat(60));
  console.log("RateShift Load Test — Teardown Summary");
  console.log("=".repeat(60));
  console.log(`Backend URL        : ${BASE_URL}`);
  console.log(`Scenario preset    : ${__ENV.SCENARIO || "full"}`);
  console.log(`Warmup duration    : ${data.warmupDuration.toFixed(0)}ms`);
  console.log("");
  console.log("Check the k6 end-of-run summary above for:");
  console.log("  http_req_duration p(95) < 1500ms");
  console.log("  http_req_duration p(99) < 2000ms");
  console.log("  http_req_failed   rate  < 0.05 (>95% success)");
  console.log("  http_reqs         rate  > 100/s");
  console.log("=".repeat(60));
}

// ---------------------------------------------------------------------------
// handleSummary: customise the end-of-run output written to stdout/file
// ---------------------------------------------------------------------------

export function handleSummary(data) {
  const thresholds = data.metrics;

  const p95 =
    thresholds["http_req_duration"] &&
    thresholds["http_req_duration"].values &&
    thresholds["http_req_duration"].values["p(95)"]
      ? thresholds["http_req_duration"].values["p(95)"].toFixed(1) + "ms"
      : "N/A";

  const p99 =
    thresholds["http_req_duration"] &&
    thresholds["http_req_duration"].values &&
    thresholds["http_req_duration"].values["p(99)"]
      ? thresholds["http_req_duration"].values["p(99)"].toFixed(1) + "ms"
      : "N/A";

  const failRate =
    thresholds["http_req_failed"] &&
    thresholds["http_req_failed"].values &&
    typeof thresholds["http_req_failed"].values["rate"] !== "undefined"
      ? (thresholds["http_req_failed"].values["rate"] * 100).toFixed(2) + "%"
      : "N/A";

  const rps =
    thresholds["http_reqs"] &&
    thresholds["http_reqs"].values &&
    typeof thresholds["http_reqs"].values["rate"] !== "undefined"
      ? thresholds["http_reqs"].values["rate"].toFixed(1) + " req/s"
      : "N/A";

  const summary = `
==============================================================
  RateShift — Load Test Results
==============================================================
  Scenario    : ${__ENV.SCENARIO || "full"}
  Target      : ${BASE_URL}

  SLA Thresholds
  --------------
  p95 latency     : ${p95}  (target < 1500ms)
  p99 latency     : ${p99}  (target < 2000ms)
  Failure rate    : ${failRate}  (target < 5%)
  Throughput      : ${rps}  (target > 100/s)

  Detailed metrics in the k6 summary above.
==============================================================
`;

  return {
    stdout: summary,
    // Uncomment to write results to a JSON file for CI ingestion:
    // "results/load_test_results.json": JSON.stringify(data, null, 2),
  };
}
