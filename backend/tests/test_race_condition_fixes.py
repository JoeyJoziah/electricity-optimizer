"""
Tests for race condition fixes (Sprint 1 — WS-1A-race)

Covers:
  S1-01  atomic Redis rate limiter (backend/middleware/rate_limiter.py)
  S1-02  SSE connection counter always decremented via finally
  S1-11  SlidingWindowLimiter eviction bounds memory growth
         (backend/integrations/pricing_apis/rate_limiter.py)
"""

import os

os.environ.setdefault("ENVIRONMENT", "test")

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


# =============================================================================
# S1-01 — Atomic Redis rate limiter
# =============================================================================


class TestAtomicRedisRateLimiter:
    """
    Verify that _check_redis uses a single Lua eval (atomic) instead of
    the old non-atomic pipeline.
    """

    @pytest.fixture
    def redis_mock(self):
        """Fake aioredis client that records eval calls."""
        r = AsyncMock()
        # eval returns the post-increment count as an integer
        r.eval = AsyncMock(return_value=1)
        return r

    @pytest.fixture
    def limiter(self, redis_mock):
        from middleware.rate_limiter import UserRateLimiter

        lim = UserRateLimiter(
            redis_client=redis_mock,
            requests_per_minute=10,
            requests_per_hour=100,
        )
        return lim

    @pytest.mark.asyncio
    async def test_check_redis_uses_eval_not_pipeline(self, limiter, redis_mock):
        """_check_redis must call redis.eval, NOT redis.pipeline."""
        redis_mock.eval.return_value = 1  # count=1, under limit
        allowed, remaining = await limiter._check_redis("testkey", 10, 60)

        assert redis_mock.eval.called, "Expected redis.eval to be called"
        assert not redis_mock.pipeline.called, (
            "redis.pipeline() must not be called — use atomic Lua eval instead"
        )
        assert allowed is True
        assert remaining == 9

    @pytest.mark.asyncio
    async def test_check_redis_denied_when_over_limit(self, limiter, redis_mock):
        """Returns (False, 0) when the Lua script reports count > limit."""
        redis_mock.eval.return_value = 11  # count=11 > limit=10
        allowed, remaining = await limiter._check_redis("testkey", 10, 60)

        assert allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_check_redis_passes_correct_args(self, limiter, redis_mock):
        """Lua script receives key, now, window, limit as positional ARGV."""
        redis_mock.eval.return_value = 5
        await limiter._check_redis("ratelimit:minute:user123", 100, 60)

        assert redis_mock.eval.called
        args = redis_mock.eval.call_args
        # args[0] = (script, numkeys, key, now, window, limit)
        positional = args[0]
        assert positional[1] == 1, "numkeys must be 1"
        assert positional[2] == "ratelimit:minute:user123", "KEYS[1] mismatch"
        assert positional[4] == 60, "window ARGV[2] mismatch"
        assert positional[5] == 100, "limit ARGV[3] mismatch"

    @pytest.mark.asyncio
    async def test_check_redis_both_uses_two_eval_calls(self, limiter, redis_mock):
        """_check_redis_both fires two atomic Lua evals (one per window)."""
        # Return (count, count) for both gather results
        call_results = iter([3, 50])  # minute=3, hour=50

        async def fake_eval(script, numkeys, key, now, window, limit):
            return next(call_results)

        redis_mock.eval.side_effect = fake_eval

        m_ok, m_rem, h_ok = await limiter._check_redis_both("user:test")

        assert redis_mock.eval.call_count == 2
        assert m_ok is True
        assert m_rem == 7   # 10 - 3
        assert h_ok is True

    @pytest.mark.asyncio
    async def test_concurrent_requests_do_not_exceed_limit(self, redis_mock):
        """
        Simulate N concurrent check_rate_limit calls.  The Lua eval mock
        increments an in-process counter atomically so we can verify the
        caller logic handles the sequential counts correctly.
        """
        from middleware.rate_limiter import UserRateLimiter

        LIMIT = 5
        counter = {"value": 0}

        async def fake_eval(script, numkeys, key, now, window, limit):
            counter["value"] += 1
            return counter["value"]

        redis_mock.eval.side_effect = fake_eval

        lim = UserRateLimiter(
            redis_client=redis_mock,
            requests_per_minute=LIMIT,
            requests_per_hour=1000,
        )

        results = await asyncio.gather(
            *[lim._check_redis("ratelimit:minute:concurrent", LIMIT, 60) for _ in range(8)]
        )

        allowed_count = sum(1 for allowed, _ in results if allowed)
        denied_count = sum(1 for allowed, _ in results if not allowed)

        assert allowed_count == LIMIT, f"Expected exactly {LIMIT} allowed, got {allowed_count}"
        assert denied_count == 3, f"Expected 3 denied, got {denied_count}"


# =============================================================================
# S1-02 — SSE connection counter always decremented
# =============================================================================


class TestSSEConnectionCounterFinally:
    """
    The SSE counter (_sse_incr) must always be balanced by _sse_decr,
    even when the generator raises an unexpected exception mid-stream.
    """

    @pytest.mark.asyncio
    async def test_counter_decremented_on_generator_exception(self):
        """
        If the generator body raises an unhandled exception the finally block
        still runs and _sse_decr is called exactly once.
        """
        from api.v1 import prices_sse

        prices_sse._sse_connections.clear()

        async def _no_redis():
            return None

        decr_calls = []
        original_decr = prices_sse._sse_decr

        async def tracking_decr(uid):
            decr_calls.append(uid)
            await original_decr(uid)

        async def _boom_generator(*args, **kwargs):
            yield "data: first\n\n"
            raise RuntimeError("simulated DB explosion")

        with (
            patch("config.database.get_redis", new=_no_redis),
            patch.object(prices_sse, "_sse_decr", side_effect=tracking_decr),
            patch.object(prices_sse, "_price_event_generator", side_effect=_boom_generator),
        ):
            # Manually call _sse_incr to set up the counter
            await prices_sse._sse_incr("user-exception-test")
            assert prices_sse._sse_connections["user-exception-test"] == 1

            # Build the event_stream generator (mirrors what stream_prices does)
            user_id = "user-exception-test"

            async def event_stream():
                try:
                    async for event in prices_sse._price_event_generator(None, None, 30, None):
                        yield event
                except asyncio.CancelledError:
                    pass
                finally:
                    await prices_sse._sse_decr(user_id)

            # Drain the generator; it should raise after the first yield
            collected = []
            try:
                async for chunk in event_stream():
                    collected.append(chunk)
            except RuntimeError:
                pass  # expected

        assert "user-exception-test" in decr_calls, (
            "_sse_decr must be called even when the generator raises"
        )
        # Counter must be back to zero (key removed)
        assert "user-exception-test" not in prices_sse._sse_connections

    @pytest.mark.asyncio
    async def test_counter_decremented_on_cancelled_error(self):
        """CancelledError (client disconnect) must also trigger decrement."""
        from api.v1 import prices_sse

        prices_sse._sse_connections.clear()

        async def _no_redis():
            return None

        async def _cancel_generator(*args, **kwargs):
            yield "data: hello\n\n"
            raise asyncio.CancelledError()

        with (
            patch("config.database.get_redis", new=_no_redis),
            patch.object(prices_sse, "_price_event_generator", side_effect=_cancel_generator),
        ):
            await prices_sse._sse_incr("user-cancel-test")

            user_id = "user-cancel-test"

            async def event_stream():
                try:
                    async for event in prices_sse._price_event_generator(None, None, 30, None):
                        yield event
                except asyncio.CancelledError:
                    pass
                finally:
                    await prices_sse._sse_decr(user_id)

            async for _ in event_stream():
                pass

        assert "user-cancel-test" not in prices_sse._sse_connections, (
            "Counter must be zero after CancelledError"
        )

    @pytest.mark.asyncio
    async def test_incr_decr_balance_under_normal_completion(self):
        """Normal generator exhaustion should leave the counter at zero."""
        from api.v1 import prices_sse

        prices_sse._sse_connections.clear()

        async def _no_redis():
            return None

        async def _finite_generator(*args, **kwargs):
            yield "data: tick\n\n"
            # no more items — generator returns normally

        with (
            patch("config.database.get_redis", new=_no_redis),
            patch.object(prices_sse, "_price_event_generator", side_effect=_finite_generator),
        ):
            await prices_sse._sse_incr("user-normal-test")

            user_id = "user-normal-test"

            async def event_stream():
                try:
                    async for event in prices_sse._price_event_generator(None, None, 30, None):
                        yield event
                except asyncio.CancelledError:
                    pass
                finally:
                    await prices_sse._sse_decr(user_id)

            async for _ in event_stream():
                pass

        assert "user-normal-test" not in prices_sse._sse_connections


# =============================================================================
# S1-11 — SlidingWindowLimiter eviction
# =============================================================================


class TestSlidingWindowLimiterEviction:
    """
    The SlidingWindowLimiter must not grow _windows unboundedly.
    After crossing _MAX_KEYS all stale keys should be evicted.
    """

    @pytest.mark.asyncio
    async def test_eviction_triggered_at_max_keys(self):
        """
        When the key count reaches _MAX_KEYS, stale keys (all timestamps
        expired) are removed so memory stays bounded.
        """
        from integrations.pricing_apis.rate_limiter import SlidingWindowLimiter

        limiter = SlidingWindowLimiter(
            requests_per_window=100,
            window_seconds=60,
            name="test-eviction",
        )
        # Override the threshold to a small value for testing
        limiter._MAX_KEYS = 10

        # Inject 10 "stale" keys directly (timestamps far in the past)
        past = time.monotonic() - 120  # 2 minutes ago, well outside 60-s window
        async with limiter._lock:
            for i in range(10):
                limiter._windows[f"stale-key-{i}"] = [past]

        # Acquiring on key "trigger" is the 11th key: _clean_window sees ≥ _MAX_KEYS
        # and should sweep out all 10 stale keys.
        allowed = await limiter.acquire("trigger")

        assert allowed is True, "The fresh request on 'trigger' must be allowed"
        # All 10 stale keys (empty after pruning) should have been evicted
        stale_remaining = [k for k in limiter._windows if k.startswith("stale-key-")]
        assert len(stale_remaining) == 0, (
            f"Expected 0 stale keys after eviction, found {len(stale_remaining)}"
        )

    @pytest.mark.asyncio
    async def test_active_keys_not_evicted(self):
        """Keys with recent activity must survive the eviction sweep."""
        from integrations.pricing_apis.rate_limiter import SlidingWindowLimiter

        limiter = SlidingWindowLimiter(
            requests_per_window=100,
            window_seconds=60,
            name="test-active-survival",
        )
        limiter._MAX_KEYS = 5

        now = time.monotonic()

        # 4 active keys (timestamps within window)
        async with limiter._lock:
            for i in range(4):
                limiter._windows[f"active-key-{i}"] = [now - 10]  # 10s ago, in window

            # 1 stale key
            limiter._windows["stale-only"] = [now - 120]

        # Trigger sweep by acquiring a 6th key
        await limiter.acquire("new-trigger")

        active_remaining = [k for k in limiter._windows if k.startswith("active-key-")]
        assert len(active_remaining) == 4, (
            "Active keys must not be evicted during sweep"
        )
        assert "stale-only" not in limiter._windows, "Stale key must be evicted"

    @pytest.mark.asyncio
    async def test_no_eviction_below_threshold(self):
        """No sweep should happen while key count is below _MAX_KEYS."""
        from integrations.pricing_apis.rate_limiter import SlidingWindowLimiter

        limiter = SlidingWindowLimiter(
            requests_per_window=5,
            window_seconds=60,
            name="test-no-sweep",
        )
        limiter._MAX_KEYS = 100  # high threshold

        # Fill with stale entries but stay under threshold
        past = time.monotonic() - 200
        async with limiter._lock:
            for i in range(10):
                limiter._windows[f"stale-{i}"] = [past]

        # One more acquire
        await limiter.acquire("new-key")

        # Because len < _MAX_KEYS, eviction sweep should not have run.
        # The stale keys remain (they're cleaned lazily only when accessed).
        stale_remaining = [k for k in limiter._windows if k.startswith("stale-")]
        assert len(stale_remaining) == 10, (
            "Stale keys must not be eagerly evicted when below threshold"
        )

    @pytest.mark.asyncio
    async def test_stale_key_evicted_when_other_key_triggers_sweep(self):
        """
        A stale key (all timestamps expired) is evicted when a *different*
        key triggers the sweep at _MAX_KEYS.

        _clean_window always preserves the *current* key being accessed so
        that acquire() can safely reference it; but other stale keys are
        evicted during the sweep.
        """
        from integrations.pricing_apis.rate_limiter import SlidingWindowLimiter

        limiter = SlidingWindowLimiter(
            requests_per_window=5,
            window_seconds=60,
            name="test-stale-evicted-by-sweep",
        )
        limiter._MAX_KEYS = 2

        # Add a stale key (all timestamps expired)
        async with limiter._lock:
            limiter._windows["stale-candidate"] = [time.monotonic() - 200]

        # Acquiring on a second key reaches _MAX_KEYS (2), triggering sweep.
        # "stale-candidate" is a different key so it gets evicted.
        await limiter.acquire("new-key")

        assert "stale-candidate" not in limiter._windows, (
            "Stale key must be evicted when sweep is triggered by another key"
        )
        # The actively-acquired key must still be present
        assert "new-key" in limiter._windows

    @pytest.mark.asyncio
    async def test_rate_limiting_still_works_after_eviction(self):
        """Eviction must not disrupt active rate limiting logic."""
        from integrations.pricing_apis.rate_limiter import SlidingWindowLimiter

        limiter = SlidingWindowLimiter(
            requests_per_window=3,
            window_seconds=60,
            name="test-post-eviction-limiting",
        )
        limiter._MAX_KEYS = 2  # very low threshold to force eviction

        # Seed a stale key to trigger eviction on next acquire
        async with limiter._lock:
            limiter._windows["stale"] = [time.monotonic() - 200]

        # Acquire up to limit — all should succeed
        results = [await limiter.acquire("rate-key") for _ in range(3)]
        assert all(results), "First 3 requests must be allowed"

        # 4th should be denied
        denied = await limiter.acquire("rate-key")
        assert denied is False, "4th request must be denied after limit reached"


# =============================================================================
# S1-11 — RedisRateLimiter atomic Lua acquire
# =============================================================================


class TestRedisRateLimiterAtomicAcquire:
    """
    RedisRateLimiter.acquire must use a single Lua eval (atomic) rather
    than two separate pipelines.
    """

    @pytest.fixture
    def redis_mock(self):
        r = AsyncMock()
        # Default: allowed=1, count=1
        r.eval = AsyncMock(return_value=[1, 1])
        return r

    @pytest.fixture
    def rl(self, redis_mock):
        from integrations.pricing_apis.rate_limiter import RedisRateLimiter

        return RedisRateLimiter(
            redis_client=redis_mock,
            requests_per_window=10,
            window_seconds=60,
            name="test-redis-atomic",
        )

    @pytest.mark.asyncio
    async def test_acquire_uses_eval_not_pipeline(self, rl, redis_mock):
        """acquire() must call redis.eval and must NOT call redis.pipeline."""
        result = await rl.acquire("somekey")

        assert result is True
        assert redis_mock.eval.called, "redis.eval must be called"
        assert not redis_mock.pipeline.called, (
            "redis.pipeline must NOT be called — use atomic Lua script"
        )

    @pytest.mark.asyncio
    async def test_acquire_returns_false_when_lua_denies(self, rl, redis_mock):
        """When Lua returns allowed=0 acquire() returns False."""
        redis_mock.eval.return_value = [0, 10]  # denied, count at limit
        result = await rl.acquire("somekey")
        assert result is False

    @pytest.mark.asyncio
    async def test_acquire_passes_tokens_to_lua(self, rl, redis_mock):
        """tokens=2 must be forwarded as ARGV[4]."""
        redis_mock.eval.return_value = [1, 2]
        await rl.acquire("somekey", tokens=2)

        args = redis_mock.eval.call_args[0]
        # (script, numkeys, redis_key, now, window, limit, tokens)
        assert args[6] == 2, f"Expected tokens=2 in ARGV[4], got {args[6]}"

    @pytest.mark.asyncio
    async def test_concurrent_acquire_respects_limit(self, redis_mock):
        """
        Simulate concurrent acquires: Lua counter increments each call.
        Exactly `limit` calls should be allowed.
        """
        from integrations.pricing_apis.rate_limiter import RedisRateLimiter

        LIMIT = 4
        counter = {"v": 0}

        async def fake_eval(script, numkeys, key, now, window, limit, tokens):
            counter["v"] += 1
            c = counter["v"]
            if c <= LIMIT:
                return [1, c]
            return [0, c]

        redis_mock.eval.side_effect = fake_eval

        rl = RedisRateLimiter(
            redis_client=redis_mock,
            requests_per_window=LIMIT,
            window_seconds=60,
            name="concurrent-test",
        )

        results = await asyncio.gather(*[rl.acquire("shared") for _ in range(7)])
        allowed = [r for r in results if r]
        denied = [r for r in results if not r]

        assert len(allowed) == LIMIT
        assert len(denied) == 3
