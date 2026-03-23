import { describe, it, expect } from "vitest";
import {
  calculateBotScore,
  shouldBlockBot,
  getSecurityHeaders,
} from "../src/middleware/security";

function makeRequest(headers: Record<string, string> = {}): Request {
  return new Request("https://api.rateshift.app/test", {
    headers: new Headers(headers),
  });
}

describe("calculateBotScore", () => {
  it("gives high score to browser-like requests", () => {
    const request = makeRequest({
      "User-Agent":
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      Accept: "text/html,application/json",
      "Accept-Language": "en-US,en;q=0.9",
      "Accept-Encoding": "gzip, deflate, br",
    });
    const score = calculateBotScore(request);
    expect(score).toBeGreaterThan(50);
  });

  it("gives low score to requests with no User-Agent", () => {
    const request = makeRequest({});
    const score = calculateBotScore(request);
    expect(score).toBeLessThan(20);
  });

  it("penalizes bot-like User-Agents", () => {
    const request = makeRequest({
      "User-Agent": "python-requests/2.28.0",
      Accept: "application/json",
    });
    const score = calculateBotScore(request);
    expect(score).toBeLessThanOrEqual(50);
  });

  it("penalizes curl", () => {
    const request = makeRequest({
      "User-Agent": "curl/7.88.1",
    });
    const score = calculateBotScore(request);
    expect(score).toBeLessThanOrEqual(50);
  });

  it("gives moderate score to API clients with Accept header", () => {
    const request = makeRequest({
      "User-Agent": "MyApp/1.0",
      Accept: "application/json",
      "Accept-Encoding": "gzip",
    });
    const score = calculateBotScore(request);
    expect(score).toBeGreaterThanOrEqual(20); // not blocked
  });
});

describe("shouldBlockBot", () => {
  it("blocks scores below 20", () => {
    expect(shouldBlockBot(19)).toBe(true);
    expect(shouldBlockBot(0)).toBe(true);
  });

  it("does not block scores at or above 20", () => {
    expect(shouldBlockBot(20)).toBe(false);
    expect(shouldBlockBot(50)).toBe(false);
    expect(shouldBlockBot(100)).toBe(false);
  });
});

describe("getSecurityHeaders", () => {
  it("includes all required security headers", () => {
    const headers = getSecurityHeaders("test-id-123", "EWR");
    expect(headers["X-Content-Type-Options"]).toBe("nosniff");
    expect(headers["X-Frame-Options"]).toBe("DENY");
    expect(headers["Strict-Transport-Security"]).toContain("max-age=");
    expect(headers["Strict-Transport-Security"]).toContain("preload");
    expect(headers["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
    expect(headers["X-Request-ID"]).toBe("test-id-123");
    expect(headers["X-Edge-Colo"]).toBe("EWR");
  });

  it("includes Permissions-Policy header", () => {
    const headers = getSecurityHeaders("test-id", "EWR");
    expect(headers["Permissions-Policy"]).toBeDefined();
    expect(headers["Permissions-Policy"]).toContain("camera=()");
    expect(headers["Permissions-Policy"]).toContain("microphone=()");
  });

  it("includes Content-Security-Policy header", () => {
    const headers = getSecurityHeaders("test-id", "EWR");
    expect(headers["Content-Security-Policy"]).toBeDefined();
    expect(headers["Content-Security-Policy"]).toContain("default-src");
    expect(headers["Content-Security-Policy"]).toContain("frame-ancestors 'none'");
  });

  it("sets X-XSS-Protection to 0 (modern best practice)", () => {
    const headers = getSecurityHeaders("test-id", "EWR");
    expect(headers["X-XSS-Protection"]).toBe("0");
  });
});
