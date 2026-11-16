/**
 * Tests for the circuit breaker in the API client.
 *
 * When the CF Worker gateway returns repeated 502/503 errors,
 * the client should automatically switch to calling the Render
 * backend directly (fallback URL) and switch back when it recovers.
 */

import { CircuitBreaker, CircuitState } from "@/lib/api/circuit-breaker";

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

const PRIMARY_URL = "/api/v1";
const FALLBACK_URL = "https://electricity-optimizer.onrender.com/api/v1";

let breaker: CircuitBreaker;

beforeEach(() => {
  breaker = new CircuitBreaker({
    failureThreshold: 3,
    resetTimeoutMs: 30_000,
    fallbackUrl: FALLBACK_URL,
    primaryUrl: PRIMARY_URL,
  });
});

// ---------------------------------------------------------------------------
// State transitions
// ---------------------------------------------------------------------------

describe("CircuitBreaker state transitions", () => {
  it("starts in CLOSED state", () => {
    expect(breaker.state).toBe(CircuitState.CLOSED);
  });

  it("stays CLOSED after fewer than threshold failures", () => {
    breaker.recordFailure();
    breaker.recordFailure();
    expect(breaker.state).toBe(CircuitState.CLOSED);
  });

  it("opens after reaching failure threshold", () => {
    breaker.recordFailure();
    breaker.recordFailure();
    breaker.recordFailure();
    expect(breaker.state).toBe(CircuitState.OPEN);
  });

  it("resets failure count on success in CLOSED state", () => {
    breaker.recordFailure();
    breaker.recordFailure();
    breaker.recordSuccess();
    // After success, failure count resets — 3 more failures needed to open
    breaker.recordFailure();
    breaker.recordFailure();
    expect(breaker.state).toBe(CircuitState.CLOSED);
  });

  it("transitions from OPEN to HALF_OPEN after reset timeout", () => {
    breaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 100, // Short timeout for testing
      fallbackUrl: FALLBACK_URL,
      primaryUrl: PRIMARY_URL,
    });

    // Open the circuit
    breaker.recordFailure();
    breaker.recordFailure();
    breaker.recordFailure();
    expect(breaker.state).toBe(CircuitState.OPEN);

    // Fast-forward past the reset timeout
    jest.useFakeTimers();
    jest.advanceTimersByTime(150);

    expect(breaker.state).toBe(CircuitState.HALF_OPEN);

    jest.useRealTimers();
  });

  it("stays HALF_OPEN after fewer than halfOpenSuccessThreshold successes", () => {
    breaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 100,
      fallbackUrl: FALLBACK_URL,
      primaryUrl: PRIMARY_URL,
      halfOpenSuccessThreshold: 3,
    });

    breaker.recordFailure();
    breaker.recordFailure();
    breaker.recordFailure();

    jest.useFakeTimers();
    jest.advanceTimersByTime(150);
    expect(breaker.state).toBe(CircuitState.HALF_OPEN);

    // First and second successes are not enough
    breaker.recordSuccess();
    expect(breaker.state).toBe(CircuitState.HALF_OPEN);
    breaker.recordSuccess();
    expect(breaker.state).toBe(CircuitState.HALF_OPEN);

    jest.useRealTimers();
  });

  it("closes circuit after reaching halfOpenSuccessThreshold consecutive successes", () => {
    breaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 100,
      fallbackUrl: FALLBACK_URL,
      primaryUrl: PRIMARY_URL,
      halfOpenSuccessThreshold: 3,
    });

    breaker.recordFailure();
    breaker.recordFailure();
    breaker.recordFailure();

    jest.useFakeTimers();
    jest.advanceTimersByTime(150);
    expect(breaker.state).toBe(CircuitState.HALF_OPEN);

    // Three consecutive successes close the circuit
    breaker.recordSuccess();
    breaker.recordSuccess();
    breaker.recordSuccess();
    expect(breaker.state).toBe(CircuitState.CLOSED);

    jest.useRealTimers();
  });

  it("closes circuit on success in HALF_OPEN state with default threshold of 3", () => {
    breaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 100,
      fallbackUrl: FALLBACK_URL,
      primaryUrl: PRIMARY_URL,
      // halfOpenSuccessThreshold not set — defaults to 3
    });

    // Open then transition to half-open
    breaker.recordFailure();
    breaker.recordFailure();
    breaker.recordFailure();

    jest.useFakeTimers();
    jest.advanceTimersByTime(150);
    expect(breaker.state).toBe(CircuitState.HALF_OPEN);

    // One success is no longer enough
    breaker.recordSuccess();
    expect(breaker.state).toBe(CircuitState.HALF_OPEN);

    // Three total successes close it
    breaker.recordSuccess();
    breaker.recordSuccess();
    expect(breaker.state).toBe(CircuitState.CLOSED);

    jest.useRealTimers();
  });

  it("resets half-open success count when failure re-opens the circuit", () => {
    breaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 100,
      fallbackUrl: FALLBACK_URL,
      primaryUrl: PRIMARY_URL,
      halfOpenSuccessThreshold: 3,
    });

    breaker.recordFailure();
    breaker.recordFailure();
    breaker.recordFailure();

    jest.useFakeTimers();
    jest.advanceTimersByTime(150);
    expect(breaker.state).toBe(CircuitState.HALF_OPEN);

    // Two successes, then a failure re-opens
    breaker.recordSuccess();
    breaker.recordSuccess();
    expect(breaker.state).toBe(CircuitState.HALF_OPEN);

    breaker.recordFailure();
    expect(breaker.state).toBe(CircuitState.OPEN);

    // After another cooldown, we need 3 fresh successes again
    jest.advanceTimersByTime(150);
    expect(breaker.state).toBe(CircuitState.HALF_OPEN);

    breaker.recordSuccess();
    expect(breaker.state).toBe(CircuitState.HALF_OPEN);

    jest.useRealTimers();
  });

  it("re-opens circuit on failure in HALF_OPEN state", () => {
    breaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 100,
      fallbackUrl: FALLBACK_URL,
      primaryUrl: PRIMARY_URL,
    });

    // Open then transition to half-open
    breaker.recordFailure();
    breaker.recordFailure();
    breaker.recordFailure();

    jest.useFakeTimers();
    jest.advanceTimersByTime(150);
    expect(breaker.state).toBe(CircuitState.HALF_OPEN);

    // Failure in half-open → back to open
    breaker.recordFailure();
    expect(breaker.state).toBe(CircuitState.OPEN);

    jest.useRealTimers();
  });
});

// ---------------------------------------------------------------------------
// URL resolution
// ---------------------------------------------------------------------------

describe("CircuitBreaker URL resolution", () => {
  it("returns primary URL when circuit is CLOSED", () => {
    expect(breaker.getBaseUrl()).toBe(PRIMARY_URL);
  });

  it("returns fallback URL when circuit is OPEN", () => {
    breaker.recordFailure();
    breaker.recordFailure();
    breaker.recordFailure();
    expect(breaker.getBaseUrl()).toBe(FALLBACK_URL);
  });

  it("returns primary URL when circuit is HALF_OPEN (probe attempt)", () => {
    breaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 100,
      fallbackUrl: FALLBACK_URL,
      primaryUrl: PRIMARY_URL,
    });

    breaker.recordFailure();
    breaker.recordFailure();
    breaker.recordFailure();

    jest.useFakeTimers();
    jest.advanceTimersByTime(150);

    // In HALF_OPEN, should try primary to probe
    expect(breaker.getBaseUrl()).toBe(PRIMARY_URL);

    jest.useRealTimers();
  });
});

// ---------------------------------------------------------------------------
// Fallback mode detection
// ---------------------------------------------------------------------------

describe("CircuitBreaker fallback mode", () => {
  it("isFallbackMode returns false when CLOSED", () => {
    expect(breaker.isFallbackMode()).toBe(false);
  });

  it("isFallbackMode returns true when OPEN", () => {
    breaker.recordFailure();
    breaker.recordFailure();
    breaker.recordFailure();
    expect(breaker.isFallbackMode()).toBe(true);
  });

  it("isFallbackMode returns false when HALF_OPEN", () => {
    breaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 100,
      fallbackUrl: FALLBACK_URL,
      primaryUrl: PRIMARY_URL,
    });

    breaker.recordFailure();
    breaker.recordFailure();
    breaker.recordFailure();

    jest.useFakeTimers();
    jest.advanceTimersByTime(150);

    expect(breaker.isFallbackMode()).toBe(false);

    jest.useRealTimers();
  });
});

// ---------------------------------------------------------------------------
// Gateway error detection
// ---------------------------------------------------------------------------

describe("CircuitBreaker.isGatewayError", () => {
  it("identifies 502 as a gateway error", () => {
    expect(CircuitBreaker.isGatewayError(502)).toBe(true);
  });

  it("identifies 503 as a gateway error", () => {
    expect(CircuitBreaker.isGatewayError(503)).toBe(true);
  });

  it("identifies 1027 as a gateway error (CF daily limit)", () => {
    expect(CircuitBreaker.isGatewayError(1027)).toBe(true);
  });

  it("does NOT treat 500 as a gateway error", () => {
    expect(CircuitBreaker.isGatewayError(500)).toBe(false);
  });

  it("does NOT treat 404 as a gateway error", () => {
    expect(CircuitBreaker.isGatewayError(404)).toBe(false);
  });

  it("does NOT treat 429 as a gateway error", () => {
    expect(CircuitBreaker.isGatewayError(429)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// No fallback URL configured
// ---------------------------------------------------------------------------

describe("CircuitBreaker without fallback URL", () => {
  it("always returns primary URL even after failures", () => {
    const noFallback = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 30_000,
      fallbackUrl: "",
      primaryUrl: PRIMARY_URL,
    });

    noFallback.recordFailure();
    noFallback.recordFailure();
    noFallback.recordFailure();

    // Without fallback URL, circuit never truly "opens" — stays on primary
    expect(noFallback.getBaseUrl()).toBe(PRIMARY_URL);
    expect(noFallback.isFallbackMode()).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Cases merged from __tests__/lib/circuit-breaker.test.ts (block-scoped so its helpers do not
// collide with the ones above)
// ---------------------------------------------------------------------------
{
  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function makeBreaker(
    overrides: Partial<
      Parameters<(typeof CircuitBreaker)["prototype"]["_resetForTesting"]>[0]
    > = {},
  ) {
    const cb = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 5000,
      fallbackUrl: "https://fallback.example.com",
      primaryUrl: "https://primary.example.com",
    });
    if (Object.keys(overrides).length) {
      cb._resetForTesting(overrides);
    }
    return cb;
  }

  function failN(cb: CircuitBreaker, n: number) {
    for (let i = 0; i < n; i++) cb.recordFailure();
  }

  // ---------------------------------------------------------------------------
  // Initial state
  // ---------------------------------------------------------------------------

  describe("CircuitBreaker — initial state", () => {
    it("starts CLOSED", () => {
      const cb = makeBreaker();
      expect(cb.state).toBe(CircuitState.CLOSED);
    });

    it("uses primary URL when CLOSED", () => {
      const cb = makeBreaker();
      expect(cb.getBaseUrl()).toBe("https://primary.example.com");
    });

    it("isFallbackMode is false initially", () => {
      const cb = makeBreaker();
      expect(cb.isFallbackMode()).toBe(false);
    });
  });

  // ---------------------------------------------------------------------------
  // CLOSED → OPEN transition
  // ---------------------------------------------------------------------------

  describe("CircuitBreaker — CLOSED to OPEN", () => {
    it("stays CLOSED below failure threshold", () => {
      const cb = makeBreaker();
      failN(cb, 2);
      expect(cb.state).toBe(CircuitState.CLOSED);
    });

    it("opens after reaching failure threshold", () => {
      const cb = makeBreaker();
      failN(cb, 3);
      expect(cb.state).toBe(CircuitState.OPEN);
    });

    it("uses fallback URL when OPEN", () => {
      const cb = makeBreaker();
      failN(cb, 3);
      expect(cb.getBaseUrl()).toBe("https://fallback.example.com");
    });

    it("isFallbackMode is true when OPEN", () => {
      const cb = makeBreaker();
      failN(cb, 3);
      expect(cb.isFallbackMode()).toBe(true);
    });

    it("success in CLOSED state resets failure count", () => {
      const cb = makeBreaker();
      failN(cb, 2);
      cb.recordSuccess();
      // Now 2 more failures should NOT open (count was reset)
      failN(cb, 2);
      expect(cb.state).toBe(CircuitState.CLOSED);
    });
  });

  // ---------------------------------------------------------------------------
  // OPEN → HALF_OPEN lazy transition
  // ---------------------------------------------------------------------------

  describe("CircuitBreaker — OPEN to HALF_OPEN (lazy transition)", () => {
    it("transitions to HALF_OPEN after resetTimeoutMs passes", () => {
      const cb = new CircuitBreaker({
        failureThreshold: 1,
        resetTimeoutMs: 0, // immediate for testing
        fallbackUrl: "https://fallback.example.com",
        primaryUrl: "https://primary.example.com",
      });
      cb.recordFailure(); // opens circuit
      // resetTimeoutMs=0 → next state read should be HALF_OPEN
      expect(cb.state).toBe(CircuitState.HALF_OPEN);
    });

    it("stays OPEN before resetTimeoutMs passes", () => {
      const cb = makeBreaker(); // resetTimeoutMs=5000
      failN(cb, 3);
      expect(cb.state).toBe(CircuitState.OPEN);
    });

    it("uses primary URL in HALF_OPEN (probe request)", () => {
      const cb = new CircuitBreaker({
        failureThreshold: 1,
        resetTimeoutMs: 0,
        fallbackUrl: "https://fallback.example.com",
        primaryUrl: "https://primary.example.com",
      });
      cb.recordFailure();
      // Transition to HALF_OPEN
      expect(cb.state).toBe(CircuitState.HALF_OPEN);
      expect(cb.getBaseUrl()).toBe("https://primary.example.com");
    });
  });

  // ---------------------------------------------------------------------------
  // HALF_OPEN recovery (success threshold)
  // ---------------------------------------------------------------------------

  describe("CircuitBreaker — HALF_OPEN recovery", () => {
    function makeHalfOpenBreaker(halfOpenSuccessThreshold = 3) {
      const cb = new CircuitBreaker({
        failureThreshold: 1,
        resetTimeoutMs: 0,
        fallbackUrl: "https://fallback.example.com",
        primaryUrl: "https://primary.example.com",
        halfOpenSuccessThreshold,
      });
      cb.recordFailure(); // open
      void cb.state; // trigger lazy OPEN → HALF_OPEN
      return cb;
    }

    it("stays HALF_OPEN with fewer successes than threshold", () => {
      const cb = makeHalfOpenBreaker(3);
      cb.recordSuccess();
      cb.recordSuccess();
      expect(cb.state).toBe(CircuitState.HALF_OPEN);
    });

    it("closes after reaching halfOpenSuccessThreshold", () => {
      const cb = makeHalfOpenBreaker(3);
      cb.recordSuccess();
      cb.recordSuccess();
      cb.recordSuccess();
      expect(cb.state).toBe(CircuitState.CLOSED);
    });

    it("defaults halfOpenSuccessThreshold to 3 when not set", () => {
      const cb = new CircuitBreaker({
        failureThreshold: 1,
        resetTimeoutMs: 0,
        fallbackUrl: "https://fallback.example.com",
        primaryUrl: "https://primary.example.com",
        // halfOpenSuccessThreshold omitted — defaults to 3
      });
      cb.recordFailure();
      void cb.state;
      cb.recordSuccess();
      cb.recordSuccess();
      expect(cb.state).toBe(CircuitState.HALF_OPEN); // 2 of 3 — still open
      cb.recordSuccess();
      expect(cb.state).toBe(CircuitState.CLOSED);
    });

    it("re-opens on failure during HALF_OPEN (not CLOSED — resets progress)", () => {
      // With resetTimeoutMs=0 the lazy getter immediately transitions OPEN→HALF_OPEN,
      // but the key observable is that the circuit is NOT CLOSED and requires a
      // fresh 3 successes — verified fully by the 'resets halfOpenSuccessCount' test.
      const cb = makeHalfOpenBreaker(3);
      cb.recordSuccess(); // partial progress (1/3)
      cb.recordFailure(); // probe failed
      // State is HALF_OPEN (not CLOSED) — recovery counter was reset
      expect(cb.state).not.toBe(CircuitState.CLOSED);
    });

    it("resets halfOpenSuccessCount when probe fails", () => {
      const cb = makeHalfOpenBreaker(3);
      cb.recordSuccess();
      cb.recordSuccess(); // 2/3 — almost recovered
      cb.recordFailure(); // re-opens, count reset

      // Force transition to HALF_OPEN again (resetTimeoutMs=0)
      void cb.state;

      // Now need 3 fresh successes, not just 1
      cb.recordSuccess();
      cb.recordSuccess();
      expect(cb.state).toBe(CircuitState.HALF_OPEN); // still needs 3rd
      cb.recordSuccess();
      expect(cb.state).toBe(CircuitState.CLOSED);
    });
  });

  // ---------------------------------------------------------------------------
  // Static helpers
  // ---------------------------------------------------------------------------

  describe("CircuitBreaker.isGatewayError", () => {
    it("returns true for 502", () => {
      expect(CircuitBreaker.isGatewayError(502)).toBe(true);
    });

    it("returns true for 503", () => {
      expect(CircuitBreaker.isGatewayError(503)).toBe(true);
    });

    it("returns true for 1027 (CF-specific)", () => {
      expect(CircuitBreaker.isGatewayError(1027)).toBe(true);
    });

    it("returns false for 200", () => {
      expect(CircuitBreaker.isGatewayError(200)).toBe(false);
    });

    it("returns false for 500", () => {
      expect(CircuitBreaker.isGatewayError(500)).toBe(false);
    });

    it("returns false for 401", () => {
      expect(CircuitBreaker.isGatewayError(401)).toBe(false);
    });
  });

  // ---------------------------------------------------------------------------
  // No-fallback mode
  // ---------------------------------------------------------------------------

  describe("CircuitBreaker — no fallback configured", () => {
    it("always returns primary URL even when OPEN", () => {
      const cb = new CircuitBreaker({
        failureThreshold: 1,
        resetTimeoutMs: 9999,
        fallbackUrl: "",
        primaryUrl: "https://primary.example.com",
      });
      cb.recordFailure();
      expect(cb.getBaseUrl()).toBe("https://primary.example.com");
    });

    it("isFallbackMode is always false without fallbackUrl", () => {
      const cb = new CircuitBreaker({
        failureThreshold: 1,
        resetTimeoutMs: 9999,
        fallbackUrl: "",
        primaryUrl: "https://primary.example.com",
      });
      cb.recordFailure();
      expect(cb.isFallbackMode()).toBe(false);
    });
  });
}
