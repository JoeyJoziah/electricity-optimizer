import { describe, it, expect, vi, beforeEach } from "vitest";
import { handleScheduled } from "../src/handlers/scheduled";

// Mock global fetch
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

function createMockEnv() {
  return {
    ORIGIN_URL: "https://electricity-optimizer.onrender.com",
    INTERNAL_API_KEY: "test-api-key",
    ALLOWED_ORIGINS: "https://rateshift.app",
    CACHE: {} as KVNamespace,
    RATE_LIMITER_STANDARD: { limit: vi.fn() },
    RATE_LIMITER_STRICT: { limit: vi.fn() },
    RATE_LIMITER_INTERNAL: { limit: vi.fn() },
  } as any;
}

function createMockController(cron = "0 */3 * * *"): ScheduledController {
  return {
    scheduledTime: Date.now(),
    cron,
    noRetry: vi.fn(),
  };
}

function createMockCtx(): ExecutionContext {
  return {
    waitUntil: vi.fn(),
    passThroughOnException: vi.fn(),
  } as any;
}

describe("handleScheduled", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, "log").mockImplementation(() => {});
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  describe("cron routing", () => {
    it("should route check-alerts cron to /internal/check-alerts", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      await handleScheduled(
        createMockController("0 */3 * * *"),
        createMockEnv(),
        createMockCtx()
      );

      expect(mockFetch).toHaveBeenCalledWith(
        "https://electricity-optimizer.onrender.com/api/v1/internal/check-alerts",
        expect.objectContaining({ method: "POST" })
      );
    });

    it("should route price-sync cron to /prices/refresh", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      await handleScheduled(
        createMockController("0 */6 * * *"),
        createMockEnv(),
        createMockCtx()
      );

      expect(mockFetch).toHaveBeenCalledWith(
        "https://electricity-optimizer.onrender.com/api/v1/prices/refresh",
        expect.objectContaining({ method: "POST" })
      );
      expect(console.log).toHaveBeenCalledWith(
        "price-sync completed successfully"
      );
    });

    it("should route observe-forecasts cron to /internal/observe-forecasts", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      await handleScheduled(
        createMockController("30 */6 * * *"),
        createMockEnv(),
        createMockCtx()
      );

      expect(mockFetch).toHaveBeenCalledWith(
        "https://electricity-optimizer.onrender.com/api/v1/internal/observe-forecasts",
        expect.objectContaining({ method: "POST" })
      );
      expect(console.log).toHaveBeenCalledWith(
        "observe-forecasts completed successfully"
      );
    });

    it("should log error and return for unknown cron expression", async () => {
      await handleScheduled(
        createMockController("0 0 * * *"),
        createMockEnv(),
        createMockCtx()
      );

      expect(mockFetch).not.toHaveBeenCalled();
      expect(console.error).toHaveBeenCalledWith(
        "Unknown cron expression: 0 0 * * *"
      );
    });
  });

  describe("request format", () => {
    it("should POST with correct headers and body", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const env = createMockEnv();
      await handleScheduled(createMockController(), env, createMockCtx());

      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(mockFetch).toHaveBeenCalledWith(
        "https://electricity-optimizer.onrender.com/api/v1/internal/check-alerts",
        expect.objectContaining({
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-API-Key": "test-api-key",
          },
          body: "{}",
        })
      );
    });

    it("should use empty string for missing INTERNAL_API_KEY", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const env = createMockEnv();
      delete env.INTERNAL_API_KEY;

      await handleScheduled(createMockController(), env, createMockCtx());

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            "X-API-Key": "",
          }),
        })
      );
    });
  });

  describe("success and error logging", () => {
    it("should log success on 200 response", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      await handleScheduled(
        createMockController(),
        createMockEnv(),
        createMockCtx()
      );

      expect(console.log).toHaveBeenCalledWith(
        "check-alerts completed successfully"
      );
      expect(console.error).not.toHaveBeenCalled();
    });

    it("should not retry on 4xx errors", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response("Unauthorized", { status: 401, statusText: "Unauthorized" })
      );

      await handleScheduled(
        createMockController(),
        createMockEnv(),
        createMockCtx()
      );

      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(console.error).toHaveBeenCalledWith(
        expect.stringContaining("check-alerts failed: 401")
      );
    });

    it("should handle fetch errors gracefully", async () => {
      mockFetch.mockRejectedValueOnce(new Error("Network error"));

      await handleScheduled(
        createMockController(),
        createMockEnv(),
        createMockCtx()
      );

      expect(console.error).toHaveBeenCalledWith(
        "check-alerts fetch error:",
        "Network error"
      );
    });
  });

  describe("retry on cold start (502/503/504)", () => {
    it("should retry once on 502 (Render cold start)", async () => {
      vi.useFakeTimers();

      mockFetch
        .mockResolvedValueOnce(new Response("Bad Gateway", { status: 502 }))
        .mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const promise = handleScheduled(
        createMockController(),
        createMockEnv(),
        createMockCtx()
      );

      await vi.advanceTimersByTimeAsync(35_000);
      await promise;

      expect(mockFetch).toHaveBeenCalledTimes(2);
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining("retrying in 35s")
      );

      vi.useRealTimers();
    });

    it("should retry once on 503", async () => {
      vi.useFakeTimers();

      mockFetch
        .mockResolvedValueOnce(
          new Response("Service Unavailable", { status: 503 })
        )
        .mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const promise = handleScheduled(
        createMockController(),
        createMockEnv(),
        createMockCtx()
      );

      await vi.advanceTimersByTimeAsync(35_000);
      await promise;

      expect(mockFetch).toHaveBeenCalledTimes(2);

      vi.useRealTimers();
    });

    it("should log error if retry also fails", async () => {
      vi.useFakeTimers();

      mockFetch
        .mockResolvedValueOnce(new Response("Bad Gateway", { status: 502 }))
        .mockResolvedValueOnce(
          new Response("Still down", { status: 502, statusText: "Bad Gateway" })
        );

      const promise = handleScheduled(
        createMockController(),
        createMockEnv(),
        createMockCtx()
      );

      await vi.advanceTimersByTimeAsync(35_000);
      await promise;

      expect(mockFetch).toHaveBeenCalledTimes(2);
      expect(console.error).toHaveBeenCalledWith(
        expect.stringContaining("check-alerts failed: 502")
      );

      vi.useRealTimers();
    });

    it("should retry price-sync on cold start too", async () => {
      vi.useFakeTimers();

      mockFetch
        .mockResolvedValueOnce(new Response("Bad Gateway", { status: 502 }))
        .mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const promise = handleScheduled(
        createMockController("0 */6 * * *"),
        createMockEnv(),
        createMockCtx()
      );

      await vi.advanceTimersByTimeAsync(35_000);
      await promise;

      expect(mockFetch).toHaveBeenCalledTimes(2);
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining("price-sync")
      );
      expect(console.log).toHaveBeenCalledWith(
        "price-sync completed successfully"
      );

      vi.useRealTimers();
    });
  });
});
