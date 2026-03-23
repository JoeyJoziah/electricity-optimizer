import { describe, it, expect } from "vitest";
import { matchRoute, buildCacheKey } from "../src/router";

describe("matchRoute", () => {
  it("matches /health", () => {
    const route = matchRoute("/health");
    expect(route.rateLimit).toBe("bypass");
    expect(route.cache?.ttlSeconds).toBe(30);
  });

  it("matches /api/v1/prices/current", () => {
    const route = matchRoute("/api/v1/prices/current");
    expect(route.cache?.ttlSeconds).toBe(300);
    expect(route.cache?.varyOn).toContain("region");
    expect(route.rateLimit).toBe("standard");
  });

  it("matches /api/v1/prices/history", () => {
    const route = matchRoute("/api/v1/prices/history");
    expect(route.cache?.ttlSeconds).toBe(1800);
    expect(route.rateLimit).toBe("standard");
  });

  it("matches /api/v1/prices/analytics/trend", () => {
    const route = matchRoute("/api/v1/prices/analytics/trend");
    expect(route.cache?.ttlSeconds).toBe(3600);
  });

  it("matches /api/v1/prices/stream as passthrough", () => {
    const route = matchRoute("/api/v1/prices/stream");
    expect(route.passthrough).toBe(true);
  });

  it("matches /api/v1/internal/* with requireApiKey", () => {
    const route = matchRoute("/api/v1/internal/check-alerts");
    expect(route.requireApiKey).toBe(true);
    expect(route.rateLimit).toBe("internal");
    expect(route.cache).toBeUndefined();
  });

  it("matches /api/v1/webhooks/* with internal rate limit", () => {
    const route = matchRoute("/api/v1/webhooks/stripe");
    expect(route.rateLimit).toBe("internal");
    expect(route.passthrough).toBe(true);
  });

  it("matches /api/v1/suppliers/registry with long cache", () => {
    const route = matchRoute("/api/v1/suppliers/registry");
    expect(route.cache?.ttlSeconds).toBe(7200);
  });

  it("matches /api/v1/auth/* with strict rate limit", () => {
    const route = matchRoute("/api/v1/auth/login");
    expect(route.rateLimit).toBe("strict");
    expect(route.cache).toBeUndefined();
  });

  it("matches /api/v1/prices/refresh with internal rate limit and API key required", () => {
    const route = matchRoute("/api/v1/prices/refresh");
    expect(route.rateLimit).toBe("internal");
    expect(route.requireApiKey).toBe(true);
  });

  it("falls through to default for unknown routes", () => {
    const route = matchRoute("/api/v1/something/else");
    expect(route.rateLimit).toBe("standard");
  });
});

describe("buildCacheKey", () => {
  it("builds key without varyOn", () => {
    const params = new URLSearchParams();
    expect(buildCacheKey("/health", params)).toBe("rsgw:/health");
  });

  it("builds key with varyOn params (valid region)", () => {
    const params = new URLSearchParams("region=us_ny&days=30&extra=ignored");
    const key = buildCacheKey("/api/v1/prices/history", params, ["region", "days"]);
    expect(key).toBe("rsgw:/api/v1/prices/history|days=30|region=us_ny");
  });

  it("sorts varyOn params alphabetically", () => {
    const params = new URLSearchParams("region=us_ca&days=7");
    const key = buildCacheKey("/test", params, ["region", "days"]);
    expect(key).toBe("rsgw:/test|days=7|region=us_ca");
  });

  it("omits missing varyOn params", () => {
    const params = new URLSearchParams("region=us_tx");
    const key = buildCacheKey("/test", params, ["region", "days"]);
    expect(key).toBe("rsgw:/test|region=us_tx");
  });

  it("returns pathname-only key when no varyOn params present", () => {
    const params = new URLSearchParams("unrelated=value");
    const key = buildCacheKey("/test", params, ["region"]);
    expect(key).toBe("rsgw:/test");
  });

  it("handles empty varyOn array", () => {
    const params = new URLSearchParams("region=us_ny");
    const key = buildCacheKey("/test", params, []);
    expect(key).toBe("rsgw:/test");
  });

  it("replaces invalid region with 'unknown'", () => {
    const params = new URLSearchParams("region=INJECTION_ATTEMPT");
    const key = buildCacheKey("/test", params, ["region"]);
    expect(key).toBe("rsgw:/test|region=unknown");
  });

  it("truncates oversized parameter values to 64 chars", () => {
    const longValue = "a".repeat(200);
    const params = new URLSearchParams(`days=${longValue}`);
    const key = buildCacheKey("/test", params, ["days"]);
    const truncated = encodeURIComponent("a".repeat(64));
    expect(key).toBe(`rsgw:/test|days=${truncated}`);
  });

  it("does not validate non-region params against region enum", () => {
    const params = new URLSearchParams("utility_type=electricity");
    const key = buildCacheKey("/test", params, ["utility_type"]);
    expect(key).toBe("rsgw:/test|utility_type=electricity");
  });
});
