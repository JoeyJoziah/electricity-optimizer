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

    it("should abort without fetch when INTERNAL_API_KEY is undefined (fail-closed)", async () => {
      const env = createMockEnv();
      delete env.INTERNAL_API_KEY;

      await handleScheduled(createMockController(), env, createMockCtx());

      // Should NOT make any fetch calls
      expect(mockFetch).not.toHaveBeenCalled();
      // Should log an error explaining the abort
      expect(console.error).toHaveBeenCalledWith(
        "check-alerts: INTERNAL_API_KEY not configured — aborting scheduled task"
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

  describe("Slack alert on final failure", () => {
    const WEBHOOK = "https://hooks.slack.test/services/T000/B000/XXXX";

    function envWithWebhook() {
      return { ...createMockEnv(), SLACK_INCIDENTS_WEBHOOK_URL: WEBHOOK };
    }

    function slackCalls() {
      return mockFetch.mock.calls.filter(([url]) => url === WEBHOOK);
    }

    beforeEach(() => {
      vi.spyOn(console, "warn").mockImplementation(() => {});
    });

    it("should post once to Slack when a route fails with a non-2xx", async () => {
      mockFetch
        .mockResolvedValueOnce(
          new Response("Unauthorized", { status: 401, statusText: "Unauthorized" })
        )
        .mockResolvedValueOnce(new Response("ok", { status: 200 }));

      await handleScheduled(
        createMockController(),
        envWithWebhook(),
        createMockCtx()
      );

      expect(slackCalls()).toHaveLength(1);
      const [, init] = slackCalls()[0];
      expect(init.method).toBe("POST");
      expect(init.signal).toBeInstanceOf(AbortSignal);
      const text = JSON.parse(init.body).text as string;
      expect(text).toContain("check-alerts");
      expect(text).toContain("HTTP 401");
      expect(text).toMatch(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
      // No secrets and no origin URL in the alert
      expect(init.body).not.toContain("onrender.com");
      expect(init.body).not.toContain("test-api-key");
      expect(init.body).not.toContain(WEBHOOK);
    });

    it("should post once after the cold-start retry also fails", async () => {
      vi.useFakeTimers();

      mockFetch
        .mockResolvedValueOnce(new Response("Bad Gateway", { status: 502 }))
        .mockResolvedValueOnce(new Response("Still down", { status: 503 }))
        .mockResolvedValueOnce(new Response("ok", { status: 200 }));

      const promise = handleScheduled(
        createMockController("0 */6 * * *"),
        envWithWebhook(),
        createMockCtx()
      );
      await vi.advanceTimersByTimeAsync(35_000);
      await promise;

      expect(mockFetch).toHaveBeenCalledTimes(3);
      expect(slackCalls()).toHaveLength(1);
      const text = JSON.parse(slackCalls()[0][1].body).text as string;
      expect(text).toContain("price-sync");
      expect(text).toContain("HTTP 503");

      vi.useRealTimers();
    });

    it("should post once to Slack when the origin fetch throws", async () => {
      mockFetch
        .mockRejectedValueOnce(
          new Error("connect failed https://electricity-optimizer.onrender.com")
        )
        .mockResolvedValueOnce(new Response("ok", { status: 200 }));

      await handleScheduled(
        createMockController("30 */6 * * *"),
        envWithWebhook(),
        createMockCtx()
      );

      expect(slackCalls()).toHaveLength(1);
      const body = slackCalls()[0][1].body as string;
      expect(JSON.parse(body).text).toContain("observe-forecasts");
      expect(JSON.parse(body).text).toContain("fetch error");
      expect(body).not.toContain("onrender.com");
    });

    it("should post nothing on success", async () => {
      mockFetch.mockResolvedValueOnce(new Response("{}", { status: 200 }));

      await handleScheduled(
        createMockController(),
        envWithWebhook(),
        createMockCtx()
      );

      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(slackCalls()).toHaveLength(0);
    });

    it("should post nothing when a cold-start retry succeeds", async () => {
      vi.useFakeTimers();

      mockFetch
        .mockResolvedValueOnce(new Response("Bad Gateway", { status: 502 }))
        .mockResolvedValueOnce(new Response("{}", { status: 200 }));

      const promise = handleScheduled(
        createMockController(),
        envWithWebhook(),
        createMockCtx()
      );
      await vi.advanceTimersByTimeAsync(35_000);
      await promise;

      expect(mockFetch).toHaveBeenCalledTimes(2);
      expect(slackCalls()).toHaveLength(0);

      vi.useRealTimers();
    });

    it("should post nothing when the webhook secret is unset", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response("Server Error", { status: 500 })
      );

      await handleScheduled(
        createMockController(),
        createMockEnv(),
        createMockCtx()
      );

      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(console.error).toHaveBeenCalledWith(
        expect.stringContaining("check-alerts failed: 500")
      );
    });

    it("should swallow a rejected webhook fetch", async () => {
      mockFetch
        .mockResolvedValueOnce(new Response("Server Error", { status: 500 }))
        .mockRejectedValueOnce(new Error(`timeout calling ${WEBHOOK}`));

      await expect(
        handleScheduled(
          createMockController(),
          envWithWebhook(),
          createMockCtx()
        )
      ).resolves.toBeUndefined();

      expect(slackCalls()).toHaveLength(1);
      // The swallowed error must not leak the webhook URL into logs
      const logged = JSON.stringify([
        ...(console.warn as any).mock.calls,
        ...(console.error as any).mock.calls,
      ]);
      expect(logged).not.toContain(WEBHOOK);
    });

    it("should swallow a non-2xx webhook response", async () => {
      mockFetch
        .mockResolvedValueOnce(new Response("Server Error", { status: 500 }))
        .mockResolvedValueOnce(new Response("no_service", { status: 404 }));

      await expect(
        handleScheduled(
          createMockController(),
          envWithWebhook(),
          createMockCtx()
        )
      ).resolves.toBeUndefined();

      expect(slackCalls()).toHaveLength(1);
    });

    it("should never alert for the keep-alive route", async () => {
      mockFetch.mockRejectedValueOnce(new Error("Network error"));

      await handleScheduled(
        createMockController("*/10 * * * *"),
        envWithWebhook(),
        createMockCtx()
      );

      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(slackCalls()).toHaveLength(0);
    });
  });
});
