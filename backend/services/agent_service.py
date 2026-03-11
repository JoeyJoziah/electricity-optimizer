"""
RateShift AI Agent Service

Primary: Gemini 2.5 Flash (free tier)
Fallback: Groq Llama 3.3 70B (free tier)
Tools: Composio (16 connected apps)
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional

import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)

# Max limits
MAX_PROMPT_LENGTH = 2000
MAX_TOOL_ITERATIONS = 30
QUERY_TIMEOUT_SECONDS = 120


@dataclass
class AgentMessage:
    """A single message in the agent conversation."""

    role: str  # "user", "assistant", "error", "tool"
    content: str
    model_used: Optional[str] = None
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

    def _get_composio_tools(self):
        """Get Composio tools for Gemini function calling."""
        if self._composio_toolset is None:
            if settings.composio_api_key:
                try:
                    from composio_gemini import ComposioToolset

                    self._composio_toolset = ComposioToolset(api_key=settings.composio_api_key)
                except Exception as e:
                    logger.warning("composio_init_failed", error=str(e))
                    self._composio_toolset = False  # sentinel: don't retry
            else:
                self._composio_toolset = False
        return self._composio_toolset if self._composio_toolset is not False else None

    async def check_rate_limit(self, user_id: str, tier: str, db) -> tuple[bool, int, int]:
        """Check if user has remaining queries. Returns (allowed, used, limit)."""
        from sqlalchemy import text

        if tier == "business":
            return True, 0, -1  # unlimited

        limit = settings.agent_pro_daily_limit if tier == "pro" else settings.agent_free_daily_limit

        await db.execute(
            text("""
                INSERT INTO agent_usage_daily (user_id, date, query_count)
                VALUES (:user_id, CURRENT_DATE, 0)
                ON CONFLICT (user_id, date) DO NOTHING
                RETURNING query_count
            """),
            {"user_id": user_id},
        )
        # Fetch current count
        count_result = await db.execute(
            text("SELECT query_count FROM agent_usage_daily WHERE user_id = :user_id AND date = CURRENT_DATE"),
            {"user_id": user_id},
        )
        current_count = count_result.scalar() or 0
        return current_count < limit, current_count, limit

    async def increment_usage(self, user_id: str, db):
        """Increment the daily usage counter."""
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
            text("SELECT query_count FROM agent_usage_daily WHERE user_id = :user_id AND date = CURRENT_DATE"),
            {"user_id": user_id},
        )
        used = result.scalar() or 0
        limit = -1 if tier == "business" else (
            settings.agent_pro_daily_limit if tier == "pro" else settings.agent_free_daily_limit
        )
        return {
            "used": used,
            "limit": limit,
            "remaining": -1 if limit == -1 else max(0, limit - used),
            "tier": tier,
        }

    async def query_streaming(
        self, user_id: str, prompt: str, context: dict, db
    ) -> AsyncGenerator[AgentMessage, None]:
        """Stream agent responses. Yields AgentMessage objects."""
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
                logger.info("gemini_rate_limited_falling_back_to_groq", user_id=user_id)
                try:
                    response_text = await self._query_groq(system, prompt)
                    model_used = "llama-3.3-70b-versatile"
                except Exception as groq_err:
                    logger.error("groq_fallback_failed", error=str(groq_err), user_id=user_id)
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

        # Increment usage
        await self.increment_usage(user_id, db)

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
                contents=f"{system}\n\nUser: {prompt}",
            ),
            timeout=QUERY_TIMEOUT_SECONDS,
        )
        return response.text

    async def _query_groq(self, system: str, prompt: str) -> str:
        """Query Groq Llama 3.3 70B as fallback."""
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
        return response.choices[0].message.content

    async def query_async(self, user_id: str, prompt: str, context: dict, db) -> str:
        """Submit an async job. Returns a job_id. Result stored in Redis."""
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

        # Run in background
        asyncio.create_task(self._run_async_job(job_id, user_id, prompt, context, redis))
        return job_id

    async def _run_async_job(self, job_id: str, user_id: str, prompt: str, context: dict, redis):
        """Execute the async job and store result in Redis."""
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
                    json.dumps({"status": "completed", "result": result, "model_used": model_used}),
                    ex=3600,
                )
        except Exception as e:
            logger.error("async_job_failed", job_id=job_id, error=str(e))
            if redis:
                await redis.set(
                    f"agent:job:{job_id}",
                    json.dumps({"status": "failed", "error": str(e)}),
                    ex=3600,
                )

    async def get_job_result(self, job_id: str) -> dict:
        """Get the result of an async job from Redis."""
        try:
            from config.database import db_manager

            redis = await db_manager.get_redis_client()
            if redis:
                data = await redis.get(f"agent:job:{job_id}")
                if data:
                    return json.loads(data)
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
