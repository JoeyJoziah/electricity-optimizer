import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Env } from "../src/types";

/**
 * Tests for Phase 2: Middleware reordering.
 * After reordering, cache hits should skip rate limiting entirely (zero KV ops).
 * Cache misses still go through rate limiting as before.
 */

// Mock fetch globally for proxy calls
const mockFetch = vi.fn().mockResolvedValue(
  new Response(JSON.stringify({ price: 0.12 }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
);
vi.stubGlobal("fetch", mockFetch);

// Mock crypto.randomUUID
vi.stubGlobal("crypto", {
  ...crypto,
  randomUUID: vi.fn().mockReturnValue("test-uuid-1234"),
});

// Mock Cache API
const mockCacheMatch = vi.fn().mockResolvedValue(undefined);
const mockCachePut = vi.fn().mockResolvedValue(undefined);
const mockCacheDelete = vi.fn().mockResolvedValue(true);

const mockCache = {
  match: mockCacheMatch,
  put: mockCachePut,
  delete: mockCacheDelete,
} as unknown as Cache;

vi.stubGlobal("caches", {
  default: mockCache,
  open: vi.fn().mockResolvedValue(mockCache),
});

function makeEnv(overrides: Partial<Env> = {}): Env {
  return {
    CACHE: {
      get: vi.fn().mockResolvedValue(null),
      put: vi.fn().mockResolvedValue(undefined),
      delete: vi.fn().mockResolvedValue(undefined),
      list: vi.fn().mockResolvedValue({ keys: [], list_complete: true, cursor: "" }),
      getWithMetadata: vi.fn().mockResolvedValue({ value: null, metadata: null }),
    } as unknown as KVNamespace,
    RATE_LIMITER_STANDARD: {
      limit: vi.fn().mockResolvedValue({ success: true }),
    },
    RATE_LIMITER_STRICT: {
      limit: vi.fn().mockResolvedValue({ success: true }),
    },
    RATE_LIMITER_INTERNAL: {
      limit: vi.fn().mockResolvedValue({ success: true }),
    },
    ORIGIN_URL: "https://test-origin.example.com",
    ALLOWED_ORIGINS: "https://rateshift.app",
    ...overrides,
  } as Env;
}

function makeRequest(
  path = "/api/v1/prices/current?region=NY",
  method = "GET"
): Request {
  return new Request(`https://api.rateshift.app${path}`, {
    method,
    headers: {
      "User-Agent": "Mozilla/5.0 Test Chrome/120",
      Accept: "application/json",
      "Accept-Language": "en-US",
      "Accept-Encoding": "gzip",
      Origin: "https://rateshift.app",
    },
  });
}

function makeCachedKvEntry(ttlSeconds = 300, ageSeconds = 60): string {
  return JSON.stringify({
    body: JSON.stringify({ price: 0.12, region: "NY" }),
    headers: { "Content-Type": "application/json" },
    status: 200,
    storedAt: Math.floor(Date.now() / 1000) - ageSeconds,
    ttlSeconds,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockCacheMatch.mockResolvedValue(undefined);
  mockCachePut.mockResolvedValue(undefined);
  mockCacheDelete.mockResolvedValue(true);
  mockFetch.mockResolvedValue(
    new Response(JSON.stringify({ price: 0.12 }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })
  );
});

describe("Middleware ordering: cache before rate limiting", () => {
  it("cache HIT skips ALL rate limiter operations", async () => {
    const env = makeEnv();
    // Simulate a fresh KV cache hit
    (env.CACHE.get as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeCachedKvEntry(300, 60)
    );

    const worker = await import("../src/index");
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    const response = await worker.default.fetch(
      makeRequest("/api/v1/prices/current?region=NY"),
      env,
      ctx
    );

    expect(response.status).toBe(200);
    // Rate limiter should NOT have been touched
    expect(env.RATE_LIMITER_STANDARD.limit).not.toHaveBeenCalled();
    expect(env.RATE_LIMITER_STRICT.limit).not.toHaveBeenCalled();
  });

  it("cache HIT via Cache API skips ALL rate limiter operations", async () => {
    const env = makeEnv();
    // Cache API returns a hit — no KV needed at all
    mockCacheMatch.mockResolvedValue(
      new Response(JSON.stringify({ price: 0.12 }), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "X-Cache": "HIT",
        },
      })
    );

    const worker = await import("../src/index");
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    const response = await worker.default.fetch(
      makeRequest("/api/v1/prices/current?region=NY"),
      env,
      ctx
    );

    expect(response.status).toBe(200);
    // Neither cache KV nor rate limiter should be touched
    expect(env.CACHE.get).not.toHaveBeenCalled();
    expect(env.RATE_LIMITER_STANDARD.limit).not.toHaveBeenCalled();
  });

  it("cache MISS still triggers rate limiting", async () => {
    const env = makeEnv();
    // No cache hit — rate limiter should be used

    const worker = await import("../src/index");
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    const response = await worker.default.fetch(
      makeRequest("/api/v1/prices/current?region=NY"),
      env,
      ctx
    );

    expect(response.status).toBe(200);
    // Rate limiter should have been called on cache miss
    expect(env.RATE_LIMITER_STANDARD.limit).toHaveBeenCalled();
  });

  it("cache STALE still triggers rate limiting (background refresh needs gating)", async () => {
    const env = makeEnv();
    // Simulate a stale KV cache entry (age > ttl, within SWR window)
    (env.CACHE.get as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeCachedKvEntry(300, 330) // 330s old, ttl=300, SWR=60 → stale but within window
    );

    const worker = await import("../src/index");
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    const response = await worker.default.fetch(
      makeRequest("/api/v1/prices/current?region=NY"),
      env,
      ctx
    );

    expect(response.status).toBe(200);
    // Rate limiter should be called for stale responses (background refresh needs gating)
    expect(env.RATE_LIMITER_STANDARD.limit).toHaveBeenCalled();
  });

  it("non-cacheable routes still use rate limiting", async () => {
    const env = makeEnv();

    const worker = await import("../src/index");
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    // Auth endpoint: strict rate limit, no cache
    await worker.default.fetch(
      makeRequest("/api/v1/auth/login", "GET"),
      env,
      ctx
    );

    // Rate limiter should be called for non-cacheable routes
    expect(env.RATE_LIMITER_STRICT.limit).toHaveBeenCalled();
  });

  it("POST requests bypass cache but still rate limit", async () => {
    const env = makeEnv();

    const worker = await import("../src/index");
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    await worker.default.fetch(
      makeRequest("/api/v1/feedback", "POST"),
      env,
      ctx
    );

    // Rate limiter should be called for POST
    expect(env.RATE_LIMITER_STRICT.limit).toHaveBeenCalled();
  });

  it("cache HIT response includes X-Cache: HIT header", async () => {
    const env = makeEnv();
    (env.CACHE.get as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeCachedKvEntry(300, 60)
    );

    const worker = await import("../src/index");
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    const response = await worker.default.fetch(
      makeRequest("/api/v1/prices/current?region=NY"),
      env,
      ctx
    );

    expect(response.headers.get("X-Cache")).toBe("HIT");
  });

  it("cache HIT does NOT include rate limit headers (no RL check occurred)", async () => {
    const env = makeEnv();
    (env.CACHE.get as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeCachedKvEntry(300, 60)
    );

    const worker = await import("../src/index");
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    const response = await worker.default.fetch(
      makeRequest("/api/v1/prices/current?region=NY"),
      env,
      ctx
    );

    // Since rate limiting was skipped, no RL headers should be present
    expect(response.headers.has("X-RateLimit-Limit")).toBe(false);
  });
});

describe("KV cacheTtl optimization", () => {
  it("CACHE.get() is called with cacheTtl option", async () => {
    const env = makeEnv();

    const worker = await import("../src/index");
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    await worker.default.fetch(
      makeRequest("/api/v1/prices/current?region=NY"),
      env,
      ctx
    );

    // Verify CACHE.get() was called with cacheTtl
    expect(env.CACHE.get).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ cacheTtl: 30 })
    );
  });
});

describe("Native rate limiter binding", () => {
  it("calls binding.limit() with client IP as key", async () => {
    const env = makeEnv();

    const worker = await import("../src/index");
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    // Non-cacheable route to force rate limiter path
    await worker.default.fetch(
      makeRequest("/api/v1/auth/login"),
      env,
      ctx
    );

    expect(env.RATE_LIMITER_STRICT.limit).toHaveBeenCalledWith({
      key: "unknown", // no CF-Connecting-IP in test
    });
  });

  it("returns 429 when binding returns success: false", async () => {
    const env = makeEnv();
    (env.RATE_LIMITER_STRICT.limit as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: false,
    });

    const worker = await import("../src/index");
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    const response = await worker.default.fetch(
      makeRequest("/api/v1/auth/login"),
      env,
      ctx
    );

    expect(response.status).toBe(429);
  });
});
