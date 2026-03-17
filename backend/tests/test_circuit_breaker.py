"""
Tests for backend/lib/circuit_breaker.py — generic circuit breaker.

Zenith P0 H-16-02: Ensure the circuit breaker correctly transitions
between CLOSED → OPEN → HALF_OPEN → CLOSED states.
"""

import asyncio
import time
from unittest.mock import patch

import pytest

from lib.circuit_breaker import (CircuitBreaker, CircuitBreakerOpen,
                                 CircuitState)


class TestCircuitBreakerStates:
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_failure_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        for _ in range(3):
            await cb.record_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_fast_fails_when_open(self):
        cb = CircuitBreaker("test", failure_threshold=2)
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

        async def dummy():
            return "should not run"

        with pytest.raises(CircuitBreakerOpen) as exc_info:
            await cb.call(dummy())
        assert "test" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.0)
        await cb.record_failure()
        await cb.record_failure()
        assert cb._state == CircuitState.OPEN
        # With recovery_timeout=0, it should transition to HALF_OPEN immediately
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_closes_on_successful_half_open_call(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.0)
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.HALF_OPEN

        # Successful call in HALF_OPEN should close the breaker
        async def success():
            return "ok"

        result = await cb.call(success())
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_reopens_on_failed_half_open_call(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.0)
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.HALF_OPEN

        async def fail():
            raise RuntimeError("still broken")

        with pytest.raises(RuntimeError, match="still broken"):
            await cb.call(fail())
        assert cb._state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_resets_failure_count_on_success(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        await cb.record_failure()
        await cb.record_failure()
        assert cb._failure_count == 2
        await cb.record_success()
        assert cb._failure_count == 0
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_call_wrapper_records_success_and_failure(self):
        cb = CircuitBreaker("test", failure_threshold=5)

        async def succeed():
            return 42

        result = await cb.call(succeed())
        assert result == 42
        assert cb._failure_count == 0

        async def fail():
            raise ValueError("bad")

        with pytest.raises(ValueError):
            await cb.call(fail())
        assert cb._failure_count == 1

    @pytest.mark.asyncio
    async def test_manual_reset(self):
        cb = CircuitBreaker("test", failure_threshold=2)
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

        await cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0

    @pytest.mark.asyncio
    async def test_half_open_max_limits_probe_calls(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.0, half_open_max=1)
        await cb.record_failure()
        assert cb.state == CircuitState.HALF_OPEN

        # First probe call should be allowed (and fail, reopening)
        async def fail():
            raise RuntimeError("probe fail")

        with pytest.raises(RuntimeError):
            await cb.call(fail())

        # Breaker should be open again
        assert cb._state == CircuitState.OPEN
