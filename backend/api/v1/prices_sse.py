"""
Price SSE Streaming Endpoints

Server-Sent Events for real-time price updates.
Streams actual price data from the database, falling back to mock data
when the DB is unavailable.
"""

import asyncio
import collections
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from api.dependencies import SessionData, get_price_service, require_tier
from config.settings import get_settings
from models.price import PriceRegion
from services.price_service import PriceService

logger = structlog.get_logger(__name__)
settings = get_settings()

router = APIRouter(tags=["Price Streaming"])

# ---------------------------------------------------------------------------
# Connection tracking (Redis-backed with in-memory fallback)
# ---------------------------------------------------------------------------

_sse_connections: dict[str, int] = collections.defaultdict(int)
_sse_lock = asyncio.Lock()
_SSE_MAX_CONNECTIONS_PER_USER = 3
_SSE_REDIS_TTL = 3600  # Safety TTL: auto-expire leaked keys after 1 hour


async def _sse_incr(user_id: str) -> int:
    """Increment SSE connection count. Uses Redis if available, else in-memory."""
    from config.database import get_redis

    redis = await get_redis()
    if redis:
        key = f"sse:conn:{user_id}"
        count = await redis.incr(key)
        await redis.expire(key, _SSE_REDIS_TTL)
        return int(count)
    async with _sse_lock:
        _sse_connections[user_id] += 1
        return _sse_connections[user_id]


async def _sse_decr(user_id: str) -> None:
    """Decrement SSE connection count."""
    from config.database import get_redis

    redis = await get_redis()
    if redis:
        key = f"sse:conn:{user_id}"
        val = await redis.decr(key)
        if val <= 0:
            await redis.delete(key)
        return
    async with _sse_lock:
        _sse_connections[user_id] -= 1
        if _sse_connections[user_id] <= 0:
            del _sse_connections[user_id]


# ---------------------------------------------------------------------------
# Event generator
# ---------------------------------------------------------------------------


async def _price_event_generator(
    region: PriceRegion,
    price_service: PriceService,
    interval_seconds: int = 30,
    request: Request | None = None,
) -> AsyncGenerator[str, None]:
    """
    Generate SSE events with latest price data.

    Queries the database for real prices via PriceService. Falls back to
    mock data when the DB is unavailable. Sends a heartbeat comment every
    15 seconds to keep proxies alive. Checks for client disconnection
    promptly.

    Timing rationale:
    - heartbeat_interval (15s) must be LESS THAN interval_seconds (30s) so
      that the inner sleep loop actually reaches the heartbeat threshold
      before a data event is emitted.  With a 45s heartbeat and 30s data
      interval the heartbeat was never sent (elapsed 30 < threshold 45).
    - 15s is safely below Cloudflare's 100s idle timeout and Render's ~60s
      proxy timeout, ensuring the TCP connection is kept alive between data
      events regardless of the requested update interval.
    """
    heartbeat_interval = 15
    elapsed_since_heartbeat = 0

    while True:
        if request is not None and await request.is_disconnected():
            break

        try:
            now = datetime.now(UTC)
            prices = await price_service.get_current_prices(region, limit=3)
            source = "live"

            if not prices:
                # No prices in DB — use mock fallback
                from api.v1.prices import _generate_mock_prices

                prices = _generate_mock_prices(region.value, 1)
                source = "fallback"

            if prices:
                price = prices[0]
                data = {
                    "region": region.value,
                    "supplier": price.supplier,
                    "price_per_kwh": str(price.price_per_kwh),
                    "currency": price.currency,
                    "is_peak": price.is_peak,
                    "timestamp": now.isoformat(),
                    "source": source,
                }
                yield f"data: {json.dumps(data)}\n\n"
        except Exception as e:
            # DB unavailable — fall back to mock data
            logger.warning("sse_event_error", error=str(e), fallback="mock")
            try:
                from api.v1.prices import _generate_mock_prices

                now = datetime.now(UTC)
                mock = _generate_mock_prices(region.value, 1)
                if mock:
                    price = mock[0]
                    data = {
                        "region": region.value,
                        "supplier": price.supplier,
                        "price_per_kwh": str(price.price_per_kwh),
                        "currency": price.currency,
                        "is_peak": price.is_peak,
                        "timestamp": now.isoformat(),
                        "source": "fallback",
                    }
                    yield f"data: {json.dumps(data)}\n\n"
            except Exception:
                yield f"event: error\ndata: {json.dumps({'error': 'Failed to fetch price'})}\n\n"

        sleep_remaining = interval_seconds
        while sleep_remaining > 0:
            sleep_chunk = min(sleep_remaining, heartbeat_interval)
            await asyncio.sleep(sleep_chunk)
            sleep_remaining -= sleep_chunk
            elapsed_since_heartbeat += sleep_chunk

            if request is not None and await request.is_disconnected():
                return

            if elapsed_since_heartbeat >= heartbeat_interval:
                yield ": heartbeat\n\n"
                elapsed_since_heartbeat = 0


# ---------------------------------------------------------------------------
# SSE endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/stream",
    summary="Stream real-time price updates (SSE)",
    responses={
        200: {
            "description": "Server-Sent Events stream of price updates",
            "content": {"text/event-stream": {}},
        },
        401: {"description": "Authentication required"},
        429: {"description": "Too many concurrent SSE connections"},
    },
)
async def stream_prices(
    request: Request,
    region: PriceRegion = Query(..., description="Price region"),
    interval: int = Query(30, ge=10, le=300, description="Update interval in seconds"),
    current_user: SessionData = Depends(require_tier("business")),
    price_service: PriceService = Depends(get_price_service),
):
    """
    Stream real-time electricity price updates via Server-Sent Events.

    Requires authentication. Max 3 concurrent connections per user.
    Streams actual prices from the database, falling back to mock data
    when the DB is unavailable.
    """
    user_id = current_user.user_id

    count = await _sse_incr(user_id)

    # Guard: if we are already at the connection cap, decrement immediately
    # (the increment above already happened) and reject.
    if count > _SSE_MAX_CONNECTIONS_PER_USER:
        await _sse_decr(user_id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Maximum of {_SSE_MAX_CONNECTIONS_PER_USER} concurrent SSE connections allowed",
        )

    logger.info("sse_connection_opened", user_id=user_id, region=region.value)

    # The counter MUST be decremented regardless of how the stream ends:
    #   - normal generator exhaustion
    #   - client disconnect (CancelledError / GeneratorExit)
    #   - any unhandled exception raised inside the generator
    #   - the rare case where the StreamingResponse body is never iterated
    #     (e.g. an exception is raised after this point but before ASGI sends
    #     the body — the outer try/finally covers that path).
    incremented = True  # flag so the outer finally knows to decrement

    async def event_stream():
        nonlocal incremented
        try:
            async for event in _price_event_generator(region, price_service, interval, request):
                yield event
        except asyncio.CancelledError:
            pass
        finally:
            # The generator finally always runs when the async iterator is
            # closed, covering normal completion, cancellation, and exceptions.
            incremented = False  # prevent double-decrement from the outer path
            await _sse_decr(user_id)
            logger.info("sse_connection_closed", user_id=user_id, region=region.value)

    try:
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception:
        # If StreamingResponse construction itself raises (extremely unlikely
        # but possible), ensure the counter is corrected before re-raising.
        if incremented:
            await _sse_decr(user_id)
            logger.info("sse_connection_closed_on_error", user_id=user_id)
        raise
