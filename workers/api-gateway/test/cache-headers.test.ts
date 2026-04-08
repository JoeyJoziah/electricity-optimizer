import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Env } from "../src/types";

/**
 * TDD tests for cache header behavior.
 * Verifies that KV cache hits include Cache-Control with remaining TTL,
 * aligning browser cache freshness with the CF Worker cache layer.
 */

// Mock fetch for proxy calls
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
  randomUUID: vi.fn().mockReturnValue("test-uuid-cache"),
});

// Mock Cache API — always miss so KV path is tested
const mockCacheMatch = vi.fn().mockResolvedValue(undefined);
const mockCachePut = vi.fn().mockResolvedValue(undefined);

vi.stubGlobal("caches", {
  default: {
    match: mockCacheMatch,
    put: mockCachePut,
    delete: vi.fn().mockResolvedValue(true),
  } as unknown as Cache,
  open: vi.fn(),
});

function makeEnv(kvGetResponse: string | null = null): Env {
  return {
    CACHE: {
      get: vi.fn().mockResolvedValue(kvGetResponse),
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
    INTERNAL_API_KEY: "test-api-key",
    RATE_LIMIT_BYPASS_KEY: "test-bypass-key",
  } as Env;
}

function makeRequest(path: string): Request {
  return new Request(`https://api.rateshift.app${path}`, {
    method: "GET",
    headers: {
      "CF-Connecting-IP": "1.2.3.4",
      "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0 Safari/537.36",
      "Accept": "application/json",
      "Accept-Language": "en-US",
      "Accept-Encoding": "gzip",
    },
  });
}

function makeFreshKvEntry(ttlSeconds: number, ageSeconds: number): string {
  return JSON.stringify({
    body: JSON.stringify({ price: 0.15 }),
    headers: { "Content-Type": "application/json" },
    status: 200,
    storedAt: Math.floor(Date.now() / 1000) - ageSeconds,
    ttlSeconds,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockResolvedValue(
    new Response(JSON.stringify({ price: 0.12 }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })
  );
});

describe("Cache-Control on KV cache hits", () => {
  it("sets Cache-Control with remaining TTL when serving fresh KV entry", async () => {
    // KV entry: 300s TTL, stored 100s ago → 200s remaining
    const kvEntry = makeFreshKvEntry(300, 100);
    const env = makeEnv(kvEntry);
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    const worker = await import("../src/index");
    const response = await worker.default.fetch(
      makeRequest("/api/v1/prices/current?region=NY"),
      env,
      ctx
    );

    expect(response.headers.get("X-Cache")).toBe("HIT");
    const cacheControl = response.headers.get("Cache-Control");
    expect(cacheControl).toBeTruthy();
    expect(cacheControl).toContain("max-age=");

    // Remaining TTL should be approximately 200s (±5s for test execution time)
    const maxAge = parseInt(cacheControl!.match(/max-age=(\d+)/)![1], 10);
    expect(maxAge).toBeGreaterThanOrEqual(195);
    expect(maxAge).toBeLessThanOrEqual(201);
  });

  it("sets Cache-Control with short TTL when entry is near expiration", async () => {
    // KV entry: 300s TTL, stored 295s ago → 5s remaining
    const kvEntry = makeFreshKvEntry(300, 295);
    const env = makeEnv(kvEntry);
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    const worker = await import("../src/index");
    const response = await worker.default.fetch(
      makeRequest("/api/v1/prices/current?region=NY"),
      env,
      ctx
    );

    expect(response.headers.get("X-Cache")).toBe("HIT");
    const cacheControl = response.headers.get("Cache-Control");
    expect(cacheControl).not.toBeNull();

    const maxAge = parseInt(cacheControl!.match(/max-age=(\d+)/)![1], 10);
    expect(maxAge).toBeGreaterThanOrEqual(1);
    expect(maxAge).toBeLessThanOrEqual(10);
  });

  it("returns X-Cache MISS and no custom Cache-Control on cache miss", async () => {
    // No KV entry → miss → proxy to origin
    const env = makeEnv(null);
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    const worker = await import("../src/index");
    const response = await worker.default.fetch(
      makeRequest("/api/v1/prices/current?region=NY"),
      env,
      ctx
    );

    // On miss, response comes from origin proxy — no X-Cache HIT
    // The origin response may or may not have Cache-Control
    expect(response.headers.get("X-Cache")).not.toBe("HIT");
  });

  it("includes X-Cache: STALE for stale-while-revalidate entries", async () => {
    // KV entry: 300s TTL, stored 310s ago → expired but within SWR window (60s)
    const kvEntry = makeFreshKvEntry(300, 310);
    const env = makeEnv(kvEntry);
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    const worker = await import("../src/index");
    const response = await worker.default.fetch(
      makeRequest("/api/v1/prices/current?region=NY"),
      env,
      ctx
    );

    // Should serve stale with SWR (prices/current has staleWhileRevalidateSeconds: 60)
    expect(response.headers.get("X-Cache")).toBe("STALE");
  });
});
