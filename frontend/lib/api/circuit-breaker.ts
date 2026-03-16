/**
 * Circuit breaker for API gateway resilience.
 *
 * When the CF Worker gateway returns repeated 502/503/1027 errors,
 * the circuit opens and requests automatically fall back to calling
 * the Render backend directly. After a cooldown period, the circuit
 * transitions to HALF_OPEN and probes the primary to check recovery.
 */

export enum CircuitState {
  /** Normal operation — requests go to primary URL */
  CLOSED = 'CLOSED',
  /** Gateway is down — requests go to fallback URL */
  OPEN = 'OPEN',
  /** Probing primary after cooldown — next request tests recovery */
  HALF_OPEN = 'HALF_OPEN',
}

export interface CircuitBreakerOptions {
  /** Number of consecutive gateway errors before opening the circuit */
  failureThreshold: number
  /** Milliseconds to wait before probing the primary again */
  resetTimeoutMs: number
  /** Direct Render backend URL to use as fallback */
  fallbackUrl: string
  /** Primary CF Worker gateway URL */
  primaryUrl: string
  /**
   * Number of consecutive successes required while in HALF_OPEN state before
   * the circuit fully closes.  Defaults to 3.  One success is not enough to
   * trust a service that had 5+ failures.
   */
  halfOpenSuccessThreshold?: number
}

/** HTTP status codes that indicate a gateway-level failure (not origin) */
const GATEWAY_ERROR_CODES = new Set([502, 503, 1027])

export class CircuitBreaker {
  private _state: CircuitState = CircuitState.CLOSED
  private _failureCount = 0
  private _halfOpenSuccessCount = 0
  private _lastFailureTime = 0
  private readonly _options: CircuitBreakerOptions

  constructor(options: CircuitBreakerOptions) {
    this._options = options
  }

  /** Current circuit state, accounting for automatic OPEN → HALF_OPEN transition */
  get state(): CircuitState {
    if (
      this._state === CircuitState.OPEN &&
      Date.now() - this._lastFailureTime >= this._options.resetTimeoutMs
    ) {
      this._state = CircuitState.HALF_OPEN
    }
    return this._state
  }

  /** Record a gateway failure. May transition CLOSED → OPEN or HALF_OPEN → OPEN. */
  recordFailure(): void {
    // Read state BEFORE updating _lastFailureTime so that the lazy
    // OPEN → HALF_OPEN transition in the `state` getter can still fire (it
    // compares against the OLD _lastFailureTime, not the fresh one).
    const currentState = this.state

    this._failureCount++
    this._lastFailureTime = Date.now()

    if (currentState === CircuitState.HALF_OPEN) {
      // Probe failed — re-open and clear the in-progress recovery count so
      // the next HALF_OPEN window requires a fresh run of consecutive successes.
      this._halfOpenSuccessCount = 0
      this._state = CircuitState.OPEN
    } else if (this._failureCount >= this._options.failureThreshold) {
      this._state = CircuitState.OPEN
    }
  }

  /**
   * Record a successful request.
   *
   * - CLOSED state: simply resets the failure counter (normal operation).
   * - HALF_OPEN state: accumulates consecutive successes; only transitions to
   *   CLOSED once the configured threshold (default 3) is reached.  A single
   *   success after repeated failures is not sufficient evidence that the
   *   upstream service has fully recovered.
   */
  recordSuccess(): void {
    // Use the public `state` getter so that the lazy OPEN → HALF_OPEN
    // transition is materialised before we branch on the current state.
    const currentState = this.state
    if (currentState === CircuitState.HALF_OPEN) {
      this._halfOpenSuccessCount++
      const threshold = this._options.halfOpenSuccessThreshold ?? 3
      if (this._halfOpenSuccessCount >= threshold) {
        // Enough consecutive probe-successes — close the circuit
        this._failureCount = 0
        this._halfOpenSuccessCount = 0
        this._state = CircuitState.CLOSED
      }
      // Otherwise stay in HALF_OPEN and keep accumulating
    } else {
      // CLOSED state: reset failure counter, no state change needed
      this._failureCount = 0
      this._halfOpenSuccessCount = 0
    }
  }

  /**
   * Get the base URL to use for the next request.
   * - CLOSED / HALF_OPEN → primary (in HALF_OPEN, this is a probe)
   * - OPEN → fallback (if configured)
   */
  getBaseUrl(): string {
    if (!this._options.fallbackUrl) {
      return this._options.primaryUrl
    }

    // Check state (which may auto-transition OPEN → HALF_OPEN)
    const currentState = this.state

    if (currentState === CircuitState.OPEN) {
      return this._options.fallbackUrl
    }

    return this._options.primaryUrl
  }

  /** True when requests are being routed to the fallback URL */
  isFallbackMode(): boolean {
    if (!this._options.fallbackUrl) return false
    return this.state === CircuitState.OPEN
  }

  /** Check if an HTTP status code represents a gateway-level error */
  static isGatewayError(status: number): boolean {
    return GATEWAY_ERROR_CODES.has(status)
  }

  /** @internal Reset to initial state and optionally reconfigure — exposed for tests only */
  _resetForTesting(overrides?: Partial<CircuitBreakerOptions>): void {
    this._state = CircuitState.CLOSED
    this._failureCount = 0
    this._halfOpenSuccessCount = 0
    this._lastFailureTime = 0
    if (overrides) {
      Object.assign(this._options, overrides)
    }
  }
}
