"""
Tests for backend/auth/neon_auth.py — session validation and caching.

Zenith P0 H-15-01: Verify session cache TTL is 60s (not the original 300s)
to limit the stale-session window for banned users.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auth.neon_auth import (_SESSION_CACHE_TTL, SessionData,
                            _get_session_from_token, invalidate_session_cache)


class TestSessionCacheTTL:
    """Zenith H-15-01: session cache TTL must be 60 seconds."""

    def test_session_cache_ttl_is_60(self):
        assert (
            _SESSION_CACHE_TTL == 60
        ), f"Expected _SESSION_CACHE_TTL=60 (Zenith H-15-01), got {_SESSION_CACHE_TTL}"

    @pytest.mark.asyncio
    async def test_session_cached_with_correct_ttl(self):
        """Verify Redis setex is called with TTL=60 when caching a session."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # Cache miss
        mock_redis.setex = AsyncMock()

        mock_db = AsyncMock()
        # Simulate a valid session row
        mock_row = MagicMock()
        mock_row.user_id = "user-123"
        mock_row.email = "test@example.com"
        mock_row.name = "Test User"
        mock_row.email_verified = True
        mock_row.role = "user"

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        session = await _get_session_from_token("test-session-token", mock_db, redis=mock_redis)

        assert session is not None
        assert session.user_id == "user-123"
        assert session.email == "test@example.com"

        # Verify setex was called with TTL=60
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 60, f"Expected setex TTL=60, got {call_args[0][1]}"

    @pytest.mark.asyncio
    async def test_session_returned_from_cache(self):
        """Verify cached sessions are returned without hitting DB."""
        cached_data = json.dumps(
            {
                "user_id": "cached-user",
                "email": "cached@example.com",
                "name": "Cached",
                "email_verified": True,
                "role": None,
            }
        )
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=cached_data)

        mock_db = AsyncMock()

        session = await _get_session_from_token("cached-token", mock_db, redis=mock_redis)

        assert session is not None
        assert session.user_id == "cached-user"
        # DB should NOT have been called
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalidate_session_cache(self):
        """Verify cache invalidation deletes the correct key."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)

        result = await invalidate_session_cache("some-token", redis=mock_redis)

        assert result is True
        mock_redis.delete.assert_called_once()
