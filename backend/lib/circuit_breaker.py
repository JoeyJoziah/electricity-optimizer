"""
Generic Circuit Breaker — Zenith P0 H-16-02

Reusable circuit breaker for any async service call. Mirrors the pattern
established by WeatherCircuitBreaker (weather_service.py) and the pricing
BasePricingClient breaker (pricing_apis/base.py), but lives in a shared
location for use by PricingService and UtilityAPIClient.

States:
  CLOSED    → requests pass through; failures are counted.
  OPEN      → requests fast-fail with CircuitBreakerOpen.
  HALF_OPEN → one probe request is allowed; success closes, failure re-opens.

Thread-safe via asyncio.Lock.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Coroutine
from enum import StrEnum
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is open and requests are rejected."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Circuit breaker '{name}' is open")


class CircuitBreaker:
    """
    Async-safe circuit breaker.

    Args:
        name:              Identifier used in log messages.
        failure_threshold: Consecutive failures before opening (default 5).
        recovery_timeout:  Seconds to wait before transitioning OPEN → HALF_OPEN (default 60).
        half_open_max:     Probe calls allowed in HALF_OPEN state (default 1).
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        """Current state (checks timeout for OPEN → HALF_OPEN transition)."""
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                return CircuitState.HALF_OPEN
        return self._state

    async def call(self, coro: Coroutine[Any, Any, T]) -> T:
        """
        Execute *coro* through the circuit breaker.

        Raises CircuitBreakerOpen if the breaker is open (fast-fail).
        On success, records success. On exception, records failure and re-raises.
        """
        async with self._lock:
            current = self.state
            if current == CircuitState.OPEN:
                # Don't await the coroutine — close it to avoid warnings
                coro.close()
                raise CircuitBreakerOpen(self.name)
            if current == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max:
                    coro.close()
                    raise CircuitBreakerOpen(self.name)
                self._half_open_calls += 1

        try:
            result = await coro
        except Exception:
            await self.record_failure()
            raise
        else:
            await self.record_success()
            return result

    async def record_success(self) -> None:
        async with self._lock:
            current = self.state
            if current == CircuitState.HALF_OPEN:
                self._transition_to_closed()
            elif current == CircuitState.CLOSED:
                self._failure_count = 0

    async def record_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            current = self.state
            if (
                current == CircuitState.HALF_OPEN
                or self._failure_count >= self.failure_threshold
            ):
                self._transition_to_open()

    async def reset(self) -> None:
        """Manually reset to CLOSED."""
        async with self._lock:
            self._transition_to_closed()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _transition_to_open(self) -> None:
        logger.warning(
            "circuit_breaker_opened",
            name=self.name,
            failure_count=self._failure_count,
        )
        self._state = CircuitState.OPEN
        self._half_open_calls = 0

    def _transition_to_closed(self) -> None:
        logger.info(
            "circuit_breaker_closed",
            name=self.name,
        )
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0
