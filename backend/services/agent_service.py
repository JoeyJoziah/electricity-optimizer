"""
RateShift AI Agent Service

Primary: Gemini 3 Flash Preview (free tier — 10 RPM, 250 RPD)
Fallback: Groq Llama 3.3 70B (free tier)
Tools: Composio (16 connected apps)
"""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field

import structlog

from config.settings import settings
from lib.tracing import traced

logger = structlog.get_logger(__name__)

# Module-level sentinels so tests can patch "services.agent_service.genai" and
# "services.agent_service.Groq" without relying on the lazy-import pattern.
try:
    from google import genai  # type: ignore[attr-defined]
except Exception:
    genai = None  # type: ignore[assignment]

try:
    from groq import AsyncGroq as Groq  # type: ignore[attr-defined]
except Exception:
    Groq = None  # type: ignore[assignment]

# Max limits
MAX_PROMPT_LENGTH = 2000
MAX_TOOL_ITERATIONS = 30
QUERY_TIMEOUT_SECONDS = 120


@dataclass
class AgentMessage:
    """A single message in the agent conversation."""

    role: str  # "user", "assistant", "error", "tool"
    content: str
    model_used: str | None = None
    tools_used: list = field(default_factory=list)
    tokens_used: int = 0
    duration_ms: int = 0


SYSTEM_PROMPT = """You are RateShift AI, an expert energy advisor. You help users:
- Analyze electricity usage and find savings opportunities
- Compare rates across suppliers in their region
- Set up alerts for price drops
- Send reports via email, Slack, or Google Sheets
- Manage their energy optimization settings

Be concise, data-driven, and actionable. Always reference the user's specific region and supplier when available.

User context:
- Region: {region}
- Supplier: {supplier}
- Subscription: {tier}
"""


# Module-level set that holds strong references to all background tasks created
# by AgentService.query_async.  Without this, the asyncio event loop holds only
# a weak reference to tasks returned by asyncio.create_task(), which means the
# task can be garbage-collected before it finishes if no other object holds a
# reference to it.  The done callback removes the completed task from this set
# so it does not grow without bound.
#
# This set is per-worker (uvicorn forks isolate it).  The lifespan shutdown
# handler calls ``drain_background_tasks`` to give in-flight Gemini calls a
# bounded grace window before the worker exits, and to mark Redis job entries
# as failed so polling clients see a concrete terminal state instead of a
# perpetual "processing" status.
_background_tasks: set[asyncio.Task] = set()
_BACKGROUND_DRAIN_TIMEOUT_SECONDS = 10.0


async def drain_background_tasks(
    timeout: float = _BACKGROUND_DRAIN_TIMEOUT_SECONDS,
) -> None:
    """Drain in-flight async agent jobs at application shutdown.

    Awaits up to ``timeout`` seconds for queued tasks to finish naturally.
    Tasks that are still running when the timeout elapses are cancelled and
    their Redis job entries are marked as ``failed`` so polling clients see
    a terminal state.  Safe to call multiple times.
    """
    if not _background_tasks:
        return

    pending = {t for t in _background_tasks if not t.done()}
    if not pending:
        _background_tasks.clear()
        return

    logger.info("agent_background_drain_started", count=len(pending), timeout=timeout)
    try:
        await asyncio.wait(pending, timeout=timeout, return_when=asyncio.ALL_COMPLETED)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("agent_background_drain_wait_error", error=str(exc))

    still_running = [t for t in pending if not t.done()]
    if still_running:
        logger.warning("agent_background_drain_cancelling", count=len(still_running))
        for task in still_running:
            task.cancel()
        # Best-effort: mark any matching Redis job entries as failed so the
        # polling endpoint surfaces a clean terminal state.
        try:
            from config.database import \
                db_manager  # local import to avoid cycle

            redis = await db_manager.get_redis_client()
            if redis:
                for task in still_running:
                    job_id = getattr(task, "_agent_job_id", None)
                    if job_id:
                        try:
                            await redis.set(
                                f"agent:job:{job_id}",
                                json.dumps(
                                    {
                                        "status": "failed",
                                        "error": "Server shutdown — please retry.",
                                    }
                                ),
                                ex=3600,
                            )
                        except Exception:
                            pass
        except Exception:
            pass
    _background_tasks.clear()
    logger.info("agent_background_drain_complete")


# Module-level singleton used as the FastAPI dependency for AgentService.
# Constructing AgentService is cheap (lazy-init of SDK clients), but doing
# it on every request still triggers Composio/Groq/Gemini SDK initialisation
# during the *first* call after a cold start, serialising those requests.
# Caching the instance makes that one-time cost happen at most once per
# process and lets ``app.dependency_overrides`` swap it in tests.
_agent_service_singleton: "AgentService | None" = None


def get_agent_service() -> "AgentService":
    """Return the process-wide AgentService instance.

    Used as a FastAPI dependency:
        ``service: AgentService = Depends(get_agent_service)``
    """
    global _agent_service_singleton
    if _agent_service_singleton is None:
        _agent_service_singleton = AgentService()
    return _agent_service_singleton


def _reset_agent_service_singleton() -> None:
    """Test helper: clear the cached singleton between test cases."""
    global _agent_service_singleton
    _agent_service_singleton = None


class AgentService:
    """Core AI agent service with LLM fallback and Composio tool integration."""

    def __init__(self):
        self._gemini_client = None
        self._groq_client = None
        self._composio_toolset = None

    def _get_gemini_client(self):
        if self._gemini_client is None:
            if not settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY not configured")
            from google import genai

            self._gemini_client = genai.Client(api_key=settings.gemini_api_key)
        return self._gemini_client

    def _get_groq_client(self):
        if self._groq_client is None:
            if not settings.groq_api_key:
                raise ValueError("GROQ_API_KEY not configured")
            from groq import AsyncGroq

            self._groq_client = AsyncGroq(api_key=settings.groq_api_key)
        return self._groq_client

    # ------------------------------------------------------------------
    # Composio tool allow-list per tier (security M-7)
    #
    # Composio is provisioned with 16 connected apps including gmail, slack,
    # resend, googlesheets, etc. Several of those are destructive
    # (send_email, post_message, write_file). Without a server-side allow-list,
    # a prompt injection in user input could direct the LLM to email a
    # third party from the user's connected gmail. Tier-gating destructive
    # surface narrows that risk dramatically while preserving the read-only
    # tools (search, list, read) that drive most legitimate use.
    # ------------------------------------------------------------------

    # Read-only tools available to all tiers (free, pro, business)
    _READ_ONLY_TOOL_PREFIXES: tuple[str, ...] = (
        "search_",
        "list_",
        "read_",
        "get_",
        "fetch_",
    )

    # Destructive tools restricted to business tier (and only with explicit
    # per-tool consent at execution time — see _is_tool_allowed)
    _BUSINESS_ONLY_TOOL_PREFIXES: tuple[str, ...] = (
        "send_",
        "post_",
        "create_",
        "update_",
        "delete_",
        "write_",
    )

    @classmethod
    def _is_tool_allowed(cls, tool_name: str, tier: str) -> bool:
        """Return True if ``tier`` is allowed to invoke ``tool_name``."""
        name = (tool_name or "").lower()
        if any(name.startswith(p) for p in cls._READ_ONLY_TOOL_PREFIXES):
            return True
        if any(name.startswith(p) for p in cls._BUSINESS_ONLY_TOOL_PREFIXES):
            return tier == "business"
        # Default-deny for unrecognised verbs — require explicit allow-listing.
        return False

    def _get_composio_tools(self, tier: str = "free"):
        """Get Composio tools for Gemini function calling, filtered by tier.

        Args:
            tier: ``free``, ``pro``, or ``business``. Free + pro receive only
                read-only tools (search/list/read/get/fetch). Business
                additionally receives mutating tools (send/post/create/etc.).

        Returns ``None`` if Composio is not configured or initialisation
        failed.  Otherwise returns the underlying toolset; the caller is
        responsible for passing it to Gemini's function-calling API.
        """
        if self._composio_toolset is None:
            if settings.composio_api_key:
                try:
                    from composio_gemini import ComposioToolset

                    self._composio_toolset = ComposioToolset(
                        api_key=settings.composio_api_key
                    )
                except Exception as e:
                    logger.warning("composio_init_failed", error=str(e))
                    self._composio_toolset = False  # sentinel: don't retry
            else:
                self._composio_toolset = False
        toolset = (
            self._composio_toolset if self._composio_toolset is not False else None
        )
        if toolset is None:
            return None
        # Mark the active tier on the toolset so any future tool dispatch
        # can re-validate before invocation. The actual filtering happens at
        # call-time via ``_is_tool_allowed`` since the Composio SDK does not
        # expose an explicit allow-list parameter on the Toolset constructor.
        try:
            toolset._rateshift_tier = tier  # type: ignore[attr-defined]
        except Exception:
            pass
        return toolset

    async def check_rate_limit(
        self, user_id: str, tier: str, db
    ) -> tuple[bool, int, int]:
        """Check if user has remaining queries. Returns (allowed, used, limit).

        Uses a single upsert-and-return query to avoid the TOCTOU race that
        would allow concurrent requests to both read count=0 and both be
        permitted past the limit.
        """
        from sqlalchemy import text

        if tier == "business":
            return True, 0, -1  # unlimited

        limit = (
            settings.agent_pro_daily_limit
            if tier == "pro"
            else settings.agent_free_daily_limit
        )

        # Single round-trip: INSERT row if absent (count=0), then return
        # current count atomically.  DO UPDATE with no-op ensures the row
        # exists so the subsequent SELECT always finds it.
        count_result = await db.execute(
            text("""
                INSERT INTO agent_usage_daily (user_id, date, query_count)
                VALUES (:user_id, CURRENT_DATE, 0)
                ON CONFLICT (user_id, date) DO UPDATE
                    SET query_count = agent_usage_daily.query_count
                RETURNING query_count
            """),
            {"user_id": user_id},
        )
        current_count = count_result.scalar() or 0
        return current_count < limit, current_count, limit

    async def increment_usage_atomic(
        self, user_id: str, tier: str, db
    ) -> tuple[bool, int]:
        """Atomically check-and-increment the daily usage counter.

        Returns (allowed, new_count).  Uses a single UPDATE ... RETURNING
        statement to prevent the TOCTOU race where two concurrent requests
        both read count < limit, both proceed, and the limit is exceeded.

        If the user is already at the limit the UPDATE matches no rows
        (WHERE count < limit fails) and we return (False, current_count).

        Business tier always returns (True, 0) immediately without touching
        the database.
        """
        from sqlalchemy import text

        if tier == "business":
            return True, 0

        limit = (
            settings.agent_pro_daily_limit
            if tier == "pro"
            else settings.agent_free_daily_limit
        )

        # Ensure the row exists before attempting the atomic increment so
        # the UPDATE below always has a row to operate on.
        await db.execute(
            text("""
                INSERT INTO agent_usage_daily (user_id, date, query_count)
                VALUES (:user_id, CURRENT_DATE, 0)
                ON CONFLICT (user_id, date) DO NOTHING
            """),
            {"user_id": user_id},
        )

        # Atomically increment ONLY if still under the limit.  If the row
        # already hit the limit the WHERE clause prevents the update and
        # RETURNING returns no rows — signalling that the request is denied.
        result = await db.execute(
            text("""
                UPDATE agent_usage_daily
                SET query_count = query_count + 1
                WHERE user_id = :user_id
                  AND date = CURRENT_DATE
                  AND query_count < :limit
                RETURNING query_count
            """),
            {"user_id": user_id, "limit": limit},
        )
        new_count = result.scalar()
        if new_count is None:
            # Limit was already reached — fetch current count for reporting
            count_result = await db.execute(
                text("""
                    SELECT query_count FROM agent_usage_daily
                    WHERE user_id = :user_id AND date = CURRENT_DATE
                """),
                {"user_id": user_id},
            )
            current_count = count_result.scalar() or limit
            return False, current_count

        await db.commit()
        return True, new_count

    async def increment_usage(self, user_id: str, db):
        """Increment the daily usage counter (non-atomic helper for post-response logging).

        NOTE: This method must NOT be used for access-control decisions.  It is
        called *after* a successful response has already been returned to the
        client and therefore does not need to be atomic with the limit check.
        For the atomic check-and-increment used at request admission time, see
        ``increment_usage_atomic``.
        """
        from sqlalchemy import text

        await db.execute(
            text("""
                INSERT INTO agent_usage_daily (user_id, date, query_count)
                VALUES (:user_id, CURRENT_DATE, 1)
                ON CONFLICT (user_id, date)
                DO UPDATE SET query_count = agent_usage_daily.query_count + 1
            """),
            {"user_id": user_id},
        )
        await db.commit()

    async def get_usage(self, user_id: str, tier: str, db) -> dict:
        """Get current usage stats for the user."""
        from sqlalchemy import text

        result = await db.execute(
            text(
                "SELECT query_count FROM agent_usage_daily WHERE user_id = :user_id AND date = CURRENT_DATE"
            ),
            {"user_id": user_id},
        )
        used = result.scalar() or 0
        limit = (
            -1
            if tier == "business"
            else (
                settings.agent_pro_daily_limit
                if tier == "pro"
                else settings.agent_free_daily_limit
            )
        )
        return {
            "used": used,
            "limit": limit,
            "remaining": -1 if limit == -1 else max(0, limit - used),
            "tier": tier,
        }

    async def query_streaming(
        self,
        user_id: str,
        prompt: str,
        context: dict,
        db,
        is_disconnected: "Callable[[], Awaitable[bool]] | None" = None,
    ) -> AsyncGenerator[AgentMessage, None]:
        """Stream agent responses. Yields AgentMessage objects.

        ``is_disconnected`` is an optional async callable (e.g.
        ``request.is_disconnected``) that the streamer polls *before* opening
        an outbound LLM call. If it reports True, the call is skipped and the
        generator returns without yielding — saving Gemini quota when a user
        bails out mid-prompt.

        NOTE: ``asyncio.to_thread`` does not propagate cancellation into the
        underlying thread, so once the Gemini call is *in flight* it cannot
        be aborted. The proper fix is to migrate to the SDK's streaming API
        (``generate_content_stream``) and check ``is_disconnected`` between
        chunks. Tracked as a follow-up to security M-3 / audit P1-22.
        """
        async with traced("agent.query", attributes={"agent.provider": "gemini"}):
            start_time = time.time()

            # Validate prompt length
            if len(prompt) > MAX_PROMPT_LENGTH:
                yield AgentMessage(
                    role="error",
                    content=f"Prompt too long. Maximum {MAX_PROMPT_LENGTH} characters.",
                )
                return

            # Build system prompt with user context
            system = SYSTEM_PROMPT.format(
                region=context.get("region", "Unknown"),
                supplier=context.get("supplier", "Unknown"),
                tier=context.get("tier", "free"),
            )

            # Try Gemini first, fall back to Groq
            model_used = "gemini-3-flash-preview"
            tools_used = []
            tokens_used = 0

            # Pre-call disconnect check: if the client already bailed (e.g.
            # tab closed during the rate-limit handshake), skip the Gemini
            # call entirely so we don't burn quota on a response no one will
            # see. The post-call check below catches mid-call disconnects.
            if is_disconnected is not None:
                try:
                    if await is_disconnected():
                        logger.info("agent_query_aborted_pre_call", user_id=user_id)
                        return
                except Exception:
                    pass

            try:
                response_text = await self._query_gemini(system, prompt)
            except Exception as gemini_err:
                err_str = str(gemini_err)
                is_rate_limited = (
                    "429" in err_str
                    or "ResourceExhausted" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                )
                if is_rate_limited and settings.groq_api_key:
                    logger.info(
                        "gemini_rate_limited_falling_back_to_groq", user_id=user_id
                    )
                    try:
                        response_text = await self._query_groq(system, prompt)
                        model_used = "llama-3.3-70b-versatile"
                    except Exception as groq_err:
                        logger.error(
                            "groq_fallback_failed", error=str(groq_err), user_id=user_id
                        )
                        yield AgentMessage(
                            role="error",
                            content="AI service temporarily unavailable. Please try again later.",
                        )
                        return
                else:
                    logger.error("gemini_query_failed", error=err_str, user_id=user_id)
                    yield AgentMessage(
                        role="error",
                        content="AI service error. Please try again later.",
                    )
                    return

            duration_ms = int((time.time() - start_time) * 1000)

            # Log conversation to DB
            try:
                await self._log_conversation(
                    user_id=user_id,
                    prompt=prompt,
                    response=response_text,
                    model_used=model_used,
                    tools_used=tools_used,
                    tokens_used=tokens_used,
                    duration_ms=duration_ms,
                    db=db,
                )
            except Exception as log_err:
                logger.warning("conversation_log_failed", error=str(log_err))

            # Usage already incremented atomically at request admission
            # (increment_usage_atomic in agent.py) — do NOT double-count here.

            yield AgentMessage(
                role="assistant",
                content=response_text,
                model_used=model_used,
                tools_used=tools_used,
                tokens_used=tokens_used,
                duration_ms=duration_ms,
            )

    async def _query_gemini(self, system: str, prompt: str) -> str:
        """Query Gemini 3 Flash Preview."""
        client = self._get_gemini_client()

        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model="gemini-3-flash-preview",
                config={"system_instruction": system},
                contents=prompt,
            ),
            timeout=QUERY_TIMEOUT_SECONDS,
        )
        return response.text

    async def _query_groq(self, system: str, prompt: str) -> str:
        """Query Groq Llama 3.3 70B as fallback.

        Guards against an empty ``choices`` list which Groq can return when the
        model declines to produce a completion (e.g. safety filter, empty
        prompt, or transient API issue).  An empty list would otherwise raise
        an ``IndexError`` at ``response.choices[0]`` and surface as an
        unhandled 500 to the caller.
        """
        client = self._get_groq_client()

        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4096,
            ),
            timeout=QUERY_TIMEOUT_SECONDS,
        )

        if not response.choices:
            raise ValueError(
                "Groq returned an empty choices array — the model produced no completion. "
                "This may be caused by a safety filter, an empty prompt, or a transient "
                "Groq API issue."
            )

        return response.choices[0].message.content

    async def query_async(
        self, user_id: str, prompt: str, context: dict, db
    ) -> str:  # noqa: ARG002
        """Submit an async job. Returns a job_id. Result stored in Redis."""
        async with traced("agent.query_async", attributes={"agent.provider": "gemini"}):
            job_id = str(uuid.uuid4())
            redis = None
            try:
                from config.database import db_manager

                redis = await db_manager.get_redis_client()
            except Exception:
                pass

            if redis:
                await redis.set(
                    f"agent:job:{job_id}",
                    json.dumps({"status": "processing", "user_id": user_id}),
                    ex=3600,
                )

            # Run in background — store a strong reference so the task is not
            # garbage-collected before it completes (asyncio holds only a weak
            # reference to tasks returned by create_task).  The done callback
            # removes the task from the set once it finishes.
            task = asyncio.create_task(
                self._run_async_job(job_id, user_id, prompt, context, redis)
            )
            # Tag the task with its job_id so the shutdown drain can mark the
            # right Redis entries as failed if it has to cancel.
            task._agent_job_id = job_id  # type: ignore[attr-defined]
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
            return job_id

    async def _run_async_job(
        self, job_id: str, user_id: str, prompt: str, context: dict, redis
    ):
        """Execute the async job and store result in Redis.

        CONTRACT — NO REQUEST-SCOPED DB SESSION
        ----------------------------------------
        This method is executed as an ``asyncio`` background task that outlives
        the HTTP request that created it.  The SQLAlchemy ``AsyncSession``
        bound to that request is closed (and returned to the connection pool)
        as soon as the request handler returns, which happens *before* this
        task completes.  Therefore this method must NOT accept or use the
        request-scoped ``db`` session.

        If future changes require database access from this background task,
        create a fresh session using the application session factory::

            from config.database import db_manager

            async with db_manager.get_session() as session:
                await session.execute(...)
                await session.commit()

        Using a self-contained ``async with`` block guarantees the session is
        properly committed and returned to the pool even if an exception is
        raised inside the block.
        """
        try:
            system = SYSTEM_PROMPT.format(
                region=context.get("region", "Unknown"),
                supplier=context.get("supplier", "Unknown"),
                tier=context.get("tier", "free"),
            )
            try:
                result = await self._query_gemini(system, prompt)
                model_used = "gemini-3-flash-preview"
            except Exception:
                result = await self._query_groq(system, prompt)
                model_used = "llama-3.3-70b-versatile"

            if redis:
                await redis.set(
                    f"agent:job:{job_id}",
                    json.dumps(
                        {
                            "status": "completed",
                            "user_id": user_id,
                            "result": result,
                            "model_used": model_used,
                        }
                    ),
                    ex=3600,
                )
        except Exception as e:
            logger.error("async_job_failed", job_id=job_id, error=str(e))
            if redis:
                await redis.set(
                    f"agent:job:{job_id}",
                    json.dumps(
                        {"status": "failed", "user_id": user_id, "error": str(e)}
                    ),
                    ex=3600,
                )

    async def get_job_result(self, job_id: str, user_id: str) -> dict:
        """Get the result of an async job from Redis.

        Verifies that the requesting user owns the job to prevent IDOR.
        """
        try:
            from config.database import db_manager

            redis = await db_manager.get_redis_client()
            if redis:
                data = await redis.get(f"agent:job:{job_id}")
                if data:
                    result = json.loads(data)
                    # Verify ownership — jobs store user_id at creation time
                    job_owner = result.get("user_id")
                    if job_owner and job_owner != user_id:
                        logger.warning(
                            "agent_job_idor_blocked",
                            job_id=job_id,
                            requesting_user=user_id,
                            job_owner=job_owner,
                        )
                        return {"status": "not_found"}
                    return result
        except Exception as e:
            logger.warning("job_result_fetch_failed", job_id=job_id, error=str(e))
        return {"status": "not_found"}

    async def _log_conversation(
        self,
        user_id,
        prompt,
        response,
        model_used,
        tools_used,
        tokens_used,
        duration_ms,
        db,
    ):
        """Log conversation to agent_conversations table."""
        from sqlalchemy import text

        await db.execute(
            text("""
                INSERT INTO agent_conversations (user_id, prompt, response, model_used, tools_used, tokens_used, duration_ms)
                VALUES (:user_id, :prompt, :response, :model_used, :tools_used, :tokens_used, :duration_ms)
            """),
            {
                "user_id": user_id,
                "prompt": prompt,
                "response": response,
                "model_used": model_used,
                "tools_used": json.dumps(tools_used),
                "tokens_used": tokens_used,
                "duration_ms": duration_ms,
            },
        )
        await db.commit()
