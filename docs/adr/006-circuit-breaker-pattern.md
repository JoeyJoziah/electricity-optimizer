# ADR-006: Circuit Breaker Pattern

**Status**: Accepted
**Date**: 2026-03-11
**Decision Makers**: Devin McGrath

## Context

Multiple external dependencies (Render backend, UtilityAPI, pricing APIs) can
become slow or unresponsive. Without protection, cascading failures propagate
through the stack: the frontend blocks on timeouts, backend threads exhaust
connection pools, and users see blank pages.

Options considered: simple retry with backoff, bulkhead isolation, circuit
breaker, no protection (let timeouts surface naturally).

## Decision

Adopt a **three-state circuit breaker** (CLOSED / OPEN / HALF_OPEN) at two
layers:

### Backend (`backend/lib/circuit_breaker.py`)
- Generic `CircuitBreaker` class with configurable failure threshold, reset
  timeout, and half-open probe count.
- Integrated into `PricingService` and `UtilityAPIClient`.
- On OPEN state, calls fail immediately with a cached or default response
  rather than waiting for a timeout.

### Frontend (`frontend/lib/circuitBreaker.ts`)
- Monitors CF Worker (`api.rateshift.app`) availability.
- On repeated 502/503 responses, switches to OPEN and routes public-endpoint
  traffic directly to Render backend as a fallback.
- HALF_OPEN probes the Worker periodically; on success, reverts to CLOSED.

## Consequences

### Positive
- Failing dependencies are detected quickly; users see degraded data instead
  of spinners or errors.
- Backend thread pools are protected from exhaustion.
- Frontend auto-recovers when the CF Worker comes back.

### Negative
- Adds state management complexity (timers, probe logic).
- Thresholds must be tuned per dependency (currently: 5 failures / 60s reset
  for backend, 3 failures / 30s reset for frontend).
- Stale cached responses may be served during OPEN state.
