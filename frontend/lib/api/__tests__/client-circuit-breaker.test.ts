/**
 * Integration tests for circuit breaker behavior in the API client.
 *
 * Verifies that the apiClient switches to fallback URL after repeated
 * gateway failures and switches back on recovery.
 */

import {
  apiClient,
  circuitBreaker,
  _resetRedirectState,
  _resetBackendCooldown,
} from "@/lib/api/client";
import { CircuitState } from "@/lib/api/circuit-breaker";

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>;
const FALLBACK_URL = "https://electricity-optimizer.onrender.com/api/v1";

function mockJsonResponse(
  body: unknown,
  status = 200,
  statusText = "OK",
): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: jest.fn().mockResolvedValue(body),
    headers: new Headers(),
    redirected: false,
    type: "basic",
    url: "",
    clone: jest.fn(),
    body: null,
    bodyUsed: false,
    arrayBuffer: jest.fn(),
    blob: jest.fn(),
    formData: jest.fn(),
    text: jest.fn(),
    bytes: jest.fn(),
  } as unknown as Response;
}

beforeEach(() => {
  mockFetch.mockReset();
  _resetRedirectState();
  _resetBackendCooldown();
  // Reset circuit breaker with fallback URL configured for testing
  circuitBreaker._resetForTesting({ fallbackUrl: FALLBACK_URL });
});

// ---------------------------------------------------------------------------
// Circuit breaker integration with apiClient
// ---------------------------------------------------------------------------

describe("apiClient circuit breaker integration", () => {
  it("uses primary URL under normal operation", async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ data: "ok" }));

    await apiClient.get("/prices");

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/api/v1/prices");
    expect(calledUrl).not.toContain("onrender.com");
  });

  it("records success on successful response", async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ data: "ok" }));

    await apiClient.get("/prices");

    expect(circuitBreaker.state).toBe(CircuitState.CLOSED);
  });

  it("does not open circuit on non-gateway errors (404, 500)", async () => {
    // 404 errors — not a gateway failure
    mockFetch.mockResolvedValue(mockJsonResponse({ detail: "Not found" }, 404));

    try {
      await apiClient.get("/missing");
    } catch {
      /* expected */
    }
    try {
      await apiClient.get("/missing");
    } catch {
      /* expected */
    }
    try {
      await apiClient.get("/missing");
    } catch {
      /* expected */
    }

    expect(circuitBreaker.state).toBe(CircuitState.CLOSED);
  });

  it("opens circuit after 3 consecutive 502 errors (after retries)", async () => {
    mockFetch.mockResolvedValue(
      mockJsonResponse({ error: "Bad Gateway" }, 502, "Bad Gateway"),
    );

    try {
      await apiClient.get("/prices");
    } catch {
      /* expected */
    }
    try {
      await apiClient.get("/prices");
    } catch {
      /* expected */
    }
    try {
      await apiClient.get("/prices");
    } catch {
      /* expected */
    }

    expect(circuitBreaker.state).toBe(CircuitState.OPEN);
  });

  it("uses fallback URL when circuit is open", async () => {
    // Open the circuit
    mockFetch.mockResolvedValue(
      mockJsonResponse({ error: "Bad Gateway" }, 502, "Bad Gateway"),
    );
    try {
      await apiClient.get("/prices");
    } catch {
      /* expected */
    }
    try {
      await apiClient.get("/prices");
    } catch {
      /* expected */
    }
    try {
      await apiClient.get("/prices");
    } catch {
      /* expected */
    }

    expect(circuitBreaker.state).toBe(CircuitState.OPEN);

    // Next call should use fallback URL
    mockFetch.mockReset();
    mockFetch.mockResolvedValue(mockJsonResponse({ data: "ok" }));

    await apiClient.get("/prices");

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("onrender.com");
    expect(calledUrl).toContain("/api/v1/prices");
  });

  it("sends X-Fallback-Mode header when circuit is open", async () => {
    // Open the circuit
    mockFetch.mockResolvedValue(
      mockJsonResponse({ error: "Bad Gateway" }, 502, "Bad Gateway"),
    );
    try {
      await apiClient.get("/prices");
    } catch {
      /* expected */
    }
    try {
      await apiClient.get("/prices");
    } catch {
      /* expected */
    }
    try {
      await apiClient.get("/prices");
    } catch {
      /* expected */
    }

    expect(circuitBreaker.isFallbackMode()).toBe(true);

    // Next call should include fallback header
    mockFetch.mockReset();
    mockFetch.mockResolvedValue(mockJsonResponse({ data: "ok" }));

    await apiClient.get("/prices");

    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit;
    const headers = calledOptions.headers as Record<string, string>;
    expect(headers["X-Fallback-Mode"]).toBe("true");
  });

  it("does NOT send X-Fallback-Mode header when circuit is closed", async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ data: "ok" }));

    await apiClient.get("/prices");

    const calledOptions = mockFetch.mock.calls[0][1] as RequestInit;
    const headers = calledOptions.headers as Record<string, string>;
    expect(headers["X-Fallback-Mode"]).toBeUndefined();
  });

  it("recovers circuit after consecutive successes in half-open (gradual recovery)", async () => {
    // Use short reset timeout for testing
    circuitBreaker._resetForTesting({
      fallbackUrl: FALLBACK_URL,
      resetTimeoutMs: 100,
    });

    // Open the circuit
    mockFetch.mockResolvedValue(
      mockJsonResponse({ error: "Bad Gateway" }, 502, "Bad Gateway"),
    );
    try {
      await apiClient.get("/prices");
    } catch {
      /* expected */
    }
    try {
      await apiClient.get("/prices");
    } catch {
      /* expected */
    }
    try {
      await apiClient.get("/prices");
    } catch {
      /* expected */
    }

    expect(circuitBreaker.state).toBe(CircuitState.OPEN);

    // Simulate time passing past the reset timeout
    const realDateNow = Date.now;
    Date.now = jest.fn().mockReturnValue(realDateNow() + 200);

    expect(circuitBreaker.state).toBe(CircuitState.HALF_OPEN);

    // Gradual recovery: need 3 consecutive successes (default halfOpenSuccessThreshold)
    mockFetch.mockReset();
    mockFetch.mockResolvedValue(mockJsonResponse({ data: "recovered" }));

    // First success — still HALF_OPEN (1 of 3)
    await apiClient.get("/prices");
    expect(circuitBreaker.state).toBe(CircuitState.HALF_OPEN);

    // Second success — still HALF_OPEN (2 of 3)
    await apiClient.get("/prices");
    expect(circuitBreaker.state).toBe(CircuitState.HALF_OPEN);

    // Third success — threshold met, circuit closes
    await apiClient.get("/prices");
    expect(circuitBreaker.state).toBe(CircuitState.CLOSED);

    // Restore Date.now
    Date.now = realDateNow;
  });

  it("works for POST requests too", async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ success: true }));

    await apiClient.post("/feedback", { message: "great app" });

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/api/v1/feedback");
  });

  it("works for PUT requests", async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ updated: true }));

    await apiClient.put("/profile", { name: "Test" });

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/api/v1/profile");
  });

  it("works for DELETE requests", async () => {
    mockFetch.mockResolvedValue(mockJsonResponse({ deleted: true }));

    await apiClient.delete("/alerts/123");

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/api/v1/alerts/123");
  });
});

// ---------------------------------------------------------------------------
// 503 errors
// ---------------------------------------------------------------------------

describe("apiClient circuit breaker with 503 errors", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    // Use a long reset timeout so fake-timer advances don't trip HALF_OPEN
    circuitBreaker._resetForTesting({
      fallbackUrl: FALLBACK_URL,
      resetTimeoutMs: 600_000,
    });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("opens circuit after 3 consecutive 503 errors", async () => {
    mockFetch.mockResolvedValue(
      mockJsonResponse(
        { error: "Service Unavailable" },
        503,
        "Service Unavailable",
      ),
    );

    // Each apiClient.get retries with 3s cooldown delays.
    // Use fake timers to advance through the delays instantly.
    async function callAndDrain() {
      const p = apiClient.get("/prices").catch(() => {});
      for (let i = 0; i < 4; i++) {
        await jest.advanceTimersByTimeAsync(3_500);
      }
      await p;
      _resetBackendCooldown();
    }

    await callAndDrain();
    await callAndDrain();
    await callAndDrain();

    expect(circuitBreaker.state).toBe(CircuitState.OPEN);
  });
});
