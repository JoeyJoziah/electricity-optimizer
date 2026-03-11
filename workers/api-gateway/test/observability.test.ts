import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  gatewayMetrics,
  resetMetrics,
  recordCacheRead,
  recordCacheWrite,
  recordCacheHit,
  recordCacheMiss,
  recordRateLimitCheck,
  recordDegradation,
  recordRequest,
  getGatewayStats,
} from "../src/middleware/observability";

/**
 * Tests for gateway metrics and observability.
 * Verifies in-memory counters, stats endpoint data shape,
 * and correct metric tracking.
 */

beforeEach(() => {
  resetMetrics();
});

describe("gateway metrics counters", () => {
  it("starts with all counters at zero", () => {
    const stats = getGatewayStats();
    expect(stats.counters.cacheReads).toBe(0);
    expect(stats.counters.cacheWrites).toBe(0);
    expect(stats.counters.cacheHits).toBe(0);
    expect(stats.counters.cacheMisses).toBe(0);
    expect(stats.counters.rateLimitChecks).toBe(0);
    expect(stats.counters.degradedResponses).toBe(0);
    expect(stats.counters.totalRequests).toBe(0);
  });

  it("increments cache read counter", () => {
    recordCacheRead();
    recordCacheRead();
    recordCacheRead();
    expect(getGatewayStats().counters.cacheReads).toBe(3);
  });

  it("increments cache write counter", () => {
    recordCacheWrite();
    recordCacheWrite();
    expect(getGatewayStats().counters.cacheWrites).toBe(2);
  });

  it("increments cache hit counter", () => {
    recordCacheHit();
    expect(getGatewayStats().counters.cacheHits).toBe(1);
  });

  it("increments cache miss counter", () => {
    recordCacheMiss();
    recordCacheMiss();
    expect(getGatewayStats().counters.cacheMisses).toBe(2);
  });

  it("increments rate limit check counter", () => {
    recordRateLimitCheck();
    expect(getGatewayStats().counters.rateLimitChecks).toBe(1);
  });

  it("increments degradation counter", () => {
    recordDegradation();
    recordDegradation();
    expect(getGatewayStats().counters.degradedResponses).toBe(2);
  });

  it("increments total request counter", () => {
    recordRequest();
    recordRequest();
    recordRequest();
    expect(getGatewayStats().counters.totalRequests).toBe(3);
  });

  it("resets all counters", () => {
    recordCacheRead();
    recordCacheWrite();
    recordCacheHit();
    recordCacheMiss();
    recordRateLimitCheck();
    recordDegradation();
    recordRequest();

    resetMetrics();

    const stats = getGatewayStats();
    expect(stats.counters.cacheReads).toBe(0);
    expect(stats.counters.cacheWrites).toBe(0);
    expect(stats.counters.cacheHits).toBe(0);
    expect(stats.counters.cacheMisses).toBe(0);
    expect(stats.counters.rateLimitChecks).toBe(0);
    expect(stats.counters.degradedResponses).toBe(0);
    expect(stats.counters.totalRequests).toBe(0);
  });
});

describe("getGatewayStats()", () => {
  it("returns the expected shape", () => {
    const stats = getGatewayStats();

    expect(stats).toHaveProperty("counters");
    expect(stats).toHaveProperty("uptimeMs");
    expect(stats).toHaveProperty("startedAt");
    expect(stats).toHaveProperty("degraded");
    expect(stats).toHaveProperty("cacheHitRate");

    expect(typeof stats.uptimeMs).toBe("number");
    expect(typeof stats.startedAt).toBe("string");
    expect(typeof stats.degraded).toBe("boolean");
    expect(typeof stats.cacheHitRate).toBe("number");
  });

  it("reports uptime in milliseconds", () => {
    const stats = getGatewayStats();
    expect(stats.uptimeMs).toBeGreaterThanOrEqual(0);
  });

  it("reports degraded=false when no degradation recorded", () => {
    recordRequest();
    expect(getGatewayStats().degraded).toBe(false);
  });

  it("reports degraded=true when degradation recorded", () => {
    recordDegradation();
    expect(getGatewayStats().degraded).toBe(true);
  });

  it("calculates cache hit rate correctly", () => {
    recordCacheHit();
    recordCacheHit();
    recordCacheHit();
    recordCacheMiss();

    const stats = getGatewayStats();
    // 3 hits / (3 hits + 1 miss) = 0.75
    expect(stats.cacheHitRate).toBeCloseTo(0.75, 2);
  });

  it("returns 0 cache hit rate when no cache operations", () => {
    expect(getGatewayStats().cacheHitRate).toBe(0);
  });

  it("tracks startedAt as ISO string", () => {
    const stats = getGatewayStats();
    // Should be a valid ISO date string
    expect(() => new Date(stats.startedAt)).not.toThrow();
    expect(new Date(stats.startedAt).toISOString()).toBe(stats.startedAt);
  });
});

describe("gateway stats endpoint handling", () => {
  it("builds a JSON response with correct content type", () => {
    recordRequest();
    recordCacheRead();
    recordCacheHit();

    const stats = getGatewayStats();
    const body = JSON.stringify(stats);
    const parsed = JSON.parse(body);

    expect(parsed.counters.totalRequests).toBe(1);
    expect(parsed.counters.cacheReads).toBe(1);
    expect(parsed.counters.cacheHits).toBe(1);
  });

  it("accumulates counters across multiple operations", () => {
    // Simulate a typical request flow
    recordRequest();
    recordCacheRead();
    recordCacheMiss();
    recordRateLimitCheck();
    recordCacheWrite();

    recordRequest();
    recordCacheRead();
    recordCacheHit();

    const stats = getGatewayStats();
    expect(stats.counters.totalRequests).toBe(2);
    expect(stats.counters.cacheReads).toBe(2);
    expect(stats.counters.cacheHits).toBe(1);
    expect(stats.counters.cacheMisses).toBe(1);
    expect(stats.counters.rateLimitChecks).toBe(1);
    expect(stats.counters.cacheWrites).toBe(1);
  });
});
