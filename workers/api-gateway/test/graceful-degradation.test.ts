import { describe, it, expect, vi, beforeEach } from "vitest";
import { checkRateLimit } from "../src/middleware/rate-limiter";
import { tryCache, storeInCache, invalidatePriceCache } from "../src/middleware/cache";
import type { Env } from "../src/types";

/**
 * Tests for graceful degradation when KV/binding operations fail.
 * All failures should result in fail-open behavior, NOT 502 errors.
 */

// Mock the global caches API (not available in vitest/node environment)
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

function makeRequest(path = "/api/v1/test"): Request {
  return new Request(`https://api.rateshift.app${path}`, {
    headers: {
      "User-Agent": "Mozilla/5.0 Test",
      Accept: "application/json",
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockCacheMatch.mockResolvedValue(undefined);
  mockCachePut.mockResolvedValue(undefined);
  mockCacheDelete.mockResolvedValue(true);
});

describe("Rate Limiter graceful degradation", () => {
  it("fails open when native binding throws", async () => {
    const env = makeEnv();
    (env.RATE_LIMITER_STANDARD.limit as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("Binding unavailable")
    );

    const result = await checkRateLimit("1.2.3.4", "standard", makeRequest(), env);

    expect(result.allowed).toBe(true);
  });

  it("sets degraded flag when binding throws", async () => {
    const env = makeEnv();
    (env.RATE_LIMITER_STANDARD.limit as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("Binding unavailable")
    );

    const result = await checkRateLimit("1.2.3.4", "standard", makeRequest(), env);

    expect(result.allowed).toBe(true);
    expect(result.degraded).toBe(true);
  });

  it("returns not allowed when binding returns success: false", async () => {
    const env = makeEnv();
    (env.RATE_LIMITER_STANDARD.limit as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: false,
    });

    const result = await checkRateLimit("1.2.3.4", "standard", makeRequest(), env);

    expect(result.allowed).toBe(false);
    expect(result.remaining).toBe(0);
  });

  it("uses correct binding for strict tier", async () => {
    const env = makeEnv();

    await checkRateLimit("1.2.3.4", "strict", makeRequest(), env);

    expect(env.RATE_LIMITER_STRICT.limit).toHaveBeenCalledWith({ key: "1.2.3.4" });
    expect(env.RATE_LIMITER_STANDARD.limit).not.toHaveBeenCalled();
  });

  it("uses correct binding for internal tier", async () => {
    const env = makeEnv();

    await checkRateLimit("1.2.3.4", "internal", makeRequest(), env);

    expect(env.RATE_LIMITER_INTERNAL.limit).toHaveBeenCalledWith({ key: "1.2.3.4" });
    expect(env.RATE_LIMITER_STANDARD.limit).not.toHaveBeenCalled();
  });

  it("bypass tier is unaffected by binding state", async () => {
    const env = makeEnv();
    const result = await checkRateLimit("1.2.3.4", "bypass", makeRequest(), env);

    expect(result.allowed).toBe(true);
    expect(env.RATE_LIMITER_STANDARD.limit).not.toHaveBeenCalled();
    expect(env.RATE_LIMITER_STRICT.limit).not.toHaveBeenCalled();
    expect(env.RATE_LIMITER_INTERNAL.limit).not.toHaveBeenCalled();
  });
});

describe("Cache graceful degradation", () => {
  it("returns MISS when CACHE.get() throws", async () => {
    const env = makeEnv();
    (env.CACHE.get as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("KV read limit exceeded")
    );

    const url = new URL("https://api.rateshift.app/api/v1/prices/current?region=NY");
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    const [response, status] = await tryCache(
      makeRequest("/api/v1/prices/current?region=NY"),
      { ttlSeconds: 300, varyOn: ["region"] },
      url,
      env,
      ctx
    );

    expect(response).toBeNull();
    expect(status).toBe("MISS");
  });

  it("returns MISS when Cache API throws (falls through to KV)", async () => {
    mockCacheMatch.mockRejectedValue(new Error("Cache API unavailable"));

    const env = makeEnv();
    const url = new URL("https://api.rateshift.app/api/v1/prices/current?region=NY");
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    const [response, status] = await tryCache(
      makeRequest("/api/v1/prices/current?region=NY"),
      { ttlSeconds: 300, varyOn: ["region"] },
      url,
      env,
      ctx
    );

    // Should still try KV (which returns null), then MISS
    expect(response).toBeNull();
    expect(status).toBe("MISS");
    // KV should still have been attempted
    expect(env.CACHE.get).toHaveBeenCalled();
  });

  it("does not throw when CACHE.put() fails in storeInCache", async () => {
    const env = makeEnv();
    (env.CACHE.put as ReturnType<typeof vi.fn>).mockImplementation(() => {
      throw new Error("KV write limit exceeded");
    });

    const url = new URL("https://api.rateshift.app/api/v1/prices/current?region=NY");
    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;
    const response = new Response(JSON.stringify({ price: 0.12 }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });

    // Should not throw
    await expect(
      storeInCache(response, { ttlSeconds: 300, varyOn: ["region"] }, url, env, ctx)
    ).resolves.not.toThrow();
  });

  it("does not throw when CACHE.list() fails in invalidatePriceCache", async () => {
    const env = makeEnv();
    (env.CACHE.list as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("KV list limit exceeded")
    );

    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    await expect(invalidatePriceCache(env, ctx)).resolves.not.toThrow();
  });

  it("does not throw when CACHE.delete() fails in invalidatePriceCache", async () => {
    const env = makeEnv();
    (env.CACHE.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      keys: [{ name: "rsgw:/api/v1/prices/current" }],
      list_complete: true,
      cursor: "",
    });
    (env.CACHE.delete as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("KV delete limit exceeded")
    );

    const ctx = { waitUntil: vi.fn() } as unknown as ExecutionContext;

    await expect(invalidatePriceCache(env, ctx)).resolves.not.toThrow();
  });
});
