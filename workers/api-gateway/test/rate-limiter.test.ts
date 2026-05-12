import { describe, it, expect, vi } from "vitest";
import { checkRateLimit, rateLimitHeaders, rateLimitResponse } from "../src/middleware/rate-limiter";
import type { Env, RateLimitBinding } from "../src/types";

function makeBinding(success: boolean): RateLimitBinding {
  return { limit: vi.fn().mockResolvedValue({ success }) };
}

function makeFailingBinding(): RateLimitBinding {
  return { limit: vi.fn().mockRejectedValue(new Error("binding unavailable")) };
}

function makeEnv(overrides: Partial<Env> = {}): Env {
  return {
    RATE_LIMITER_STANDARD: makeBinding(true),
    RATE_LIMITER_STRICT: makeBinding(true),
    RATE_LIMITER_INTERNAL: makeBinding(true),
    RATE_LIMIT_BYPASS_KEY: "bypass-key-abc",
    ORIGIN_URL: "https://render-origin.example.com",
    ALLOWED_ORIGINS: "https://rateshift.app",
    ...overrides,
  } as unknown as Env;
}

function makeRequest(headers: Record<string, string> = {}): Request {
  return new Request("https://api.rateshift.app/api/v1/prices", { headers });
}

describe("checkRateLimit", () => {
  describe("bypass tier", () => {
    it("always allows without calling any binding", async () => {
      const env = makeEnv();
      const result = await checkRateLimit("1.2.3.4", "bypass", makeRequest(), env);
      expect(result.allowed).toBe(true);
      expect(result.limit).toBe(Infinity);
      expect((env.RATE_LIMITER_STANDARD.limit as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(0);
    });
  });

  describe("internal tier — bypass header", () => {
    it("allows when X-RateLimit-Bypass matches RATE_LIMIT_BYPASS_KEY", async () => {
      const env = makeEnv();
      const req = makeRequest({ "X-RateLimit-Bypass": "bypass-key-abc" });
      const result = await checkRateLimit("1.2.3.4", "internal", req, env);
      expect(result.allowed).toBe(true);
      expect(result.limit).toBe(Infinity);
    });

    it("falls through to binding when bypass key is wrong", async () => {
      const env = makeEnv({
        RATE_LIMITER_INTERNAL: makeBinding(true),
      });
      const req = makeRequest({ "X-RateLimit-Bypass": "wrong-key" });
      const result = await checkRateLimit("1.2.3.4", "internal", req, env);
      expect(result.allowed).toBe(true);
      expect((env.RATE_LIMITER_INTERNAL.limit as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(1);
    });

    it("does NOT allow bypass on strict tier even with correct key", async () => {
      const env = makeEnv({
        RATE_LIMITER_STRICT: makeBinding(true),
      });
      const req = makeRequest({ "X-RateLimit-Bypass": "bypass-key-abc" });
      const result = await checkRateLimit("1.2.3.4", "strict", req, env);
      // bypass key is only honored on internal tier — strict binding must be called
      expect((env.RATE_LIMITER_STRICT.limit as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(1);
    });
  });

  describe("native binding — allowed", () => {
    it("returns allowed=true when binding succeeds", async () => {
      const env = makeEnv({ RATE_LIMITER_STANDARD: makeBinding(true) });
      const result = await checkRateLimit("1.2.3.4", "standard", makeRequest(), env);
      expect(result.allowed).toBe(true);
      expect(result.limit).toBe(120);
    });

    it("returns allowed=true for strict tier with limit=30", async () => {
      const env = makeEnv({ RATE_LIMITER_STRICT: makeBinding(true) });
      const result = await checkRateLimit("1.2.3.4", "strict", makeRequest(), env);
      expect(result.allowed).toBe(true);
      expect(result.limit).toBe(30);
    });

    it("returns allowed=true for internal tier with limit=600", async () => {
      const env = makeEnv({ RATE_LIMITER_INTERNAL: makeBinding(true) });
      const result = await checkRateLimit("1.2.3.4", "internal", makeRequest(), env);
      expect(result.allowed).toBe(true);
      expect(result.limit).toBe(600);
    });
  });

  describe("native binding — rate limited", () => {
    it("returns allowed=false and remaining=0 when binding returns success=false", async () => {
      const env = makeEnv({ RATE_LIMITER_STANDARD: makeBinding(false) });
      const result = await checkRateLimit("5.6.7.8", "standard", makeRequest(), env);
      expect(result.allowed).toBe(false);
      expect(result.remaining).toBe(0);
      expect(result.limit).toBe(120);
      expect(result.resetAt).toBeGreaterThan(0);
    });
  });

  describe("fail-open on binding error", () => {
    it("allows the request and sets degraded=true when binding throws", async () => {
      const env = makeEnv({ RATE_LIMITER_STANDARD: makeFailingBinding() });
      const result = await checkRateLimit("1.2.3.4", "standard", makeRequest(), env);
      expect(result.allowed).toBe(true);
      expect(result.degraded).toBe(true);
    });
  });
});

describe("rateLimitHeaders", () => {
  it("returns empty object for bypass tier (Infinity limit)", () => {
    const headers = rateLimitHeaders({ allowed: true, remaining: Infinity, limit: Infinity, resetAt: 0 });
    expect(headers).toEqual({});
  });

  it("includes X-RateLimit-Limit and X-RateLimit-Reset for finite limit", () => {
    const headers = rateLimitHeaders({ allowed: true, remaining: 10, limit: 120, resetAt: 1700000060 });
    expect(headers["X-RateLimit-Limit"]).toBe("120");
    expect(headers["X-RateLimit-Reset"]).toBe("1700000060");
  });

  it("includes X-RateLimit-Remaining when remaining >= 0", () => {
    const headers = rateLimitHeaders({ allowed: true, remaining: 5, limit: 120, resetAt: 1700000060 });
    expect(headers["X-RateLimit-Remaining"]).toBe("5");
  });

  it("omits X-RateLimit-Remaining when remaining is -1 (native binding)", () => {
    const headers = rateLimitHeaders({ allowed: true, remaining: -1, limit: 120, resetAt: 1700000060 });
    expect(headers["X-RateLimit-Remaining"]).toBeUndefined();
  });
});

describe("rateLimitResponse", () => {
  it("returns HTTP 429", () => {
    const result = { allowed: false, remaining: 0, limit: 120, resetAt: Math.floor(Date.now() / 1000) + 30 };
    const response = rateLimitResponse(result);
    expect(response.status).toBe(429);
  });

  it("body contains error and retryAfter", async () => {
    const result = { allowed: false, remaining: 0, limit: 120, resetAt: Math.floor(Date.now() / 1000) + 30 };
    const response = rateLimitResponse(result);
    const body = await response.json<{ error: string; retryAfter: number }>();
    expect(body.error).toBe("Too Many Requests");
    expect(body.retryAfter).toBeGreaterThan(0);
  });

  it("includes Retry-After header", () => {
    const result = { allowed: false, remaining: 0, limit: 120, resetAt: Math.floor(Date.now() / 1000) + 45 };
    const response = rateLimitResponse(result);
    const retryAfter = Number(response.headers.get("Retry-After"));
    expect(retryAfter).toBeGreaterThan(0);
  });

  it("clamps Retry-After to minimum 1 second", () => {
    // resetAt in the past — retryAfter should still be at least 1
    const result = { allowed: false, remaining: 0, limit: 120, resetAt: 0 };
    const response = rateLimitResponse(result);
    expect(Number(response.headers.get("Retry-After"))).toBeGreaterThanOrEqual(1);
  });
});
