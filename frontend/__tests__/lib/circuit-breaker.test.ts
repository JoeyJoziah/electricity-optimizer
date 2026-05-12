import { CircuitBreaker, CircuitState } from "@/lib/api/circuit-breaker";

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
