/**
 * Tests for the circuit breaker in the API client.
 *
 * When the CF Worker gateway returns repeated 502/503 errors,
 * the client should automatically switch to calling the Render
 * backend directly (fallback URL) and switch back when it recovers.
 */

import {
  CircuitBreaker,
  CircuitState,
} from '@/lib/api/circuit-breaker'

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

const PRIMARY_URL = '/api/v1'
const FALLBACK_URL = 'https://electricity-optimizer.onrender.com/api/v1'

let breaker: CircuitBreaker

beforeEach(() => {
  breaker = new CircuitBreaker({
    failureThreshold: 3,
    resetTimeoutMs: 30_000,
    fallbackUrl: FALLBACK_URL,
    primaryUrl: PRIMARY_URL,
  })
})

// ---------------------------------------------------------------------------
// State transitions
// ---------------------------------------------------------------------------

describe('CircuitBreaker state transitions', () => {
  it('starts in CLOSED state', () => {
    expect(breaker.state).toBe(CircuitState.CLOSED)
  })

  it('stays CLOSED after fewer than threshold failures', () => {
    breaker.recordFailure()
    breaker.recordFailure()
    expect(breaker.state).toBe(CircuitState.CLOSED)
  })

  it('opens after reaching failure threshold', () => {
    breaker.recordFailure()
    breaker.recordFailure()
    breaker.recordFailure()
    expect(breaker.state).toBe(CircuitState.OPEN)
  })

  it('resets failure count on success in CLOSED state', () => {
    breaker.recordFailure()
    breaker.recordFailure()
    breaker.recordSuccess()
    // After success, failure count resets — 3 more failures needed to open
    breaker.recordFailure()
    breaker.recordFailure()
    expect(breaker.state).toBe(CircuitState.CLOSED)
  })

  it('transitions from OPEN to HALF_OPEN after reset timeout', () => {
    breaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 100, // Short timeout for testing
      fallbackUrl: FALLBACK_URL,
      primaryUrl: PRIMARY_URL,
    })

    // Open the circuit
    breaker.recordFailure()
    breaker.recordFailure()
    breaker.recordFailure()
    expect(breaker.state).toBe(CircuitState.OPEN)

    // Fast-forward past the reset timeout
    jest.useFakeTimers()
    jest.advanceTimersByTime(150)

    expect(breaker.state).toBe(CircuitState.HALF_OPEN)

    jest.useRealTimers()
  })

  it('closes circuit on success in HALF_OPEN state', () => {
    breaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 100,
      fallbackUrl: FALLBACK_URL,
      primaryUrl: PRIMARY_URL,
    })

    // Open then transition to half-open
    breaker.recordFailure()
    breaker.recordFailure()
    breaker.recordFailure()

    jest.useFakeTimers()
    jest.advanceTimersByTime(150)
    expect(breaker.state).toBe(CircuitState.HALF_OPEN)

    // Success in half-open → closed
    breaker.recordSuccess()
    expect(breaker.state).toBe(CircuitState.CLOSED)

    jest.useRealTimers()
  })

  it('re-opens circuit on failure in HALF_OPEN state', () => {
    breaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 100,
      fallbackUrl: FALLBACK_URL,
      primaryUrl: PRIMARY_URL,
    })

    // Open then transition to half-open
    breaker.recordFailure()
    breaker.recordFailure()
    breaker.recordFailure()

    jest.useFakeTimers()
    jest.advanceTimersByTime(150)
    expect(breaker.state).toBe(CircuitState.HALF_OPEN)

    // Failure in half-open → back to open
    breaker.recordFailure()
    expect(breaker.state).toBe(CircuitState.OPEN)

    jest.useRealTimers()
  })
})

// ---------------------------------------------------------------------------
// URL resolution
// ---------------------------------------------------------------------------

describe('CircuitBreaker URL resolution', () => {
  it('returns primary URL when circuit is CLOSED', () => {
    expect(breaker.getBaseUrl()).toBe(PRIMARY_URL)
  })

  it('returns fallback URL when circuit is OPEN', () => {
    breaker.recordFailure()
    breaker.recordFailure()
    breaker.recordFailure()
    expect(breaker.getBaseUrl()).toBe(FALLBACK_URL)
  })

  it('returns primary URL when circuit is HALF_OPEN (probe attempt)', () => {
    breaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 100,
      fallbackUrl: FALLBACK_URL,
      primaryUrl: PRIMARY_URL,
    })

    breaker.recordFailure()
    breaker.recordFailure()
    breaker.recordFailure()

    jest.useFakeTimers()
    jest.advanceTimersByTime(150)

    // In HALF_OPEN, should try primary to probe
    expect(breaker.getBaseUrl()).toBe(PRIMARY_URL)

    jest.useRealTimers()
  })
})

// ---------------------------------------------------------------------------
// Fallback mode detection
// ---------------------------------------------------------------------------

describe('CircuitBreaker fallback mode', () => {
  it('isFallbackMode returns false when CLOSED', () => {
    expect(breaker.isFallbackMode()).toBe(false)
  })

  it('isFallbackMode returns true when OPEN', () => {
    breaker.recordFailure()
    breaker.recordFailure()
    breaker.recordFailure()
    expect(breaker.isFallbackMode()).toBe(true)
  })

  it('isFallbackMode returns false when HALF_OPEN', () => {
    breaker = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 100,
      fallbackUrl: FALLBACK_URL,
      primaryUrl: PRIMARY_URL,
    })

    breaker.recordFailure()
    breaker.recordFailure()
    breaker.recordFailure()

    jest.useFakeTimers()
    jest.advanceTimersByTime(150)

    expect(breaker.isFallbackMode()).toBe(false)

    jest.useRealTimers()
  })
})

// ---------------------------------------------------------------------------
// Gateway error detection
// ---------------------------------------------------------------------------

describe('CircuitBreaker.isGatewayError', () => {
  it('identifies 502 as a gateway error', () => {
    expect(CircuitBreaker.isGatewayError(502)).toBe(true)
  })

  it('identifies 503 as a gateway error', () => {
    expect(CircuitBreaker.isGatewayError(503)).toBe(true)
  })

  it('identifies 1027 as a gateway error (CF daily limit)', () => {
    expect(CircuitBreaker.isGatewayError(1027)).toBe(true)
  })

  it('does NOT treat 500 as a gateway error', () => {
    expect(CircuitBreaker.isGatewayError(500)).toBe(false)
  })

  it('does NOT treat 404 as a gateway error', () => {
    expect(CircuitBreaker.isGatewayError(404)).toBe(false)
  })

  it('does NOT treat 429 as a gateway error', () => {
    expect(CircuitBreaker.isGatewayError(429)).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// No fallback URL configured
// ---------------------------------------------------------------------------

describe('CircuitBreaker without fallback URL', () => {
  it('always returns primary URL even after failures', () => {
    const noFallback = new CircuitBreaker({
      failureThreshold: 3,
      resetTimeoutMs: 30_000,
      fallbackUrl: '',
      primaryUrl: PRIMARY_URL,
    })

    noFallback.recordFailure()
    noFallback.recordFailure()
    noFallback.recordFailure()

    // Without fallback URL, circuit never truly "opens" — stays on primary
    expect(noFallback.getBaseUrl()).toBe(PRIMARY_URL)
    expect(noFallback.isFallbackMode()).toBe(false)
  })
})
