"""
Tests for AgentService — RateShift AI agent.

Covers:
- Prompt validation (too long)
- Missing API keys
- User context injection
- Gemini 429 → Groq fallback
- Rate limiting per tier (free/pro/business)
- Async job creation + retrieval
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from services.agent_service import AgentService, AgentMessage, MAX_PROMPT_LENGTH


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def agent_service():
    return AgentService()


@pytest.fixture
def mock_db():
    """Mock AsyncSession with execute/commit."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def user_context():
    return {"region": "us_ct", "supplier": "Eversource", "tier": "pro"}


# =============================================================================
# Prompt validation
# =============================================================================


@pytest.mark.asyncio
async def test_prompt_too_long_yields_error(agent_service, mock_db, user_context):
    """Prompt exceeding MAX_PROMPT_LENGTH should yield an error message."""
    long_prompt = "x" * (MAX_PROMPT_LENGTH + 1)

    messages = []
    async for msg in agent_service.query_streaming(
        user_id=str(uuid.uuid4()),
        prompt=long_prompt,
        context=user_context,
        db=mock_db,
    ):
        messages.append(msg)

    assert len(messages) == 1
    assert messages[0].role == "error"
    assert "too long" in messages[0].content.lower()


# =============================================================================
# Missing API keys
# =============================================================================


@pytest.mark.asyncio
async def test_missing_gemini_key_yields_error(agent_service, mock_db, user_context):
    """Missing Gemini API key should yield an error, not crash."""
    with patch("services.agent_service.settings") as mock_settings:
        mock_settings.gemini_api_key = None
        mock_settings.groq_api_key = None
        mock_settings.composio_api_key = None
        mock_settings.agent_free_daily_limit = 3
        mock_settings.agent_pro_daily_limit = 20

        # Reset cached clients
        agent_service._gemini_client = None
        agent_service._groq_client = None

        messages = []
        async for msg in agent_service.query_streaming(
            user_id=str(uuid.uuid4()),
            prompt="What are my rates?",
            context=user_context,
            db=mock_db,
        ):
            messages.append(msg)

        assert len(messages) >= 1
        assert any(m.role == "error" for m in messages)


# =============================================================================
# User context injection
# =============================================================================


@pytest.mark.asyncio
async def test_query_with_user_context(agent_service, mock_db, user_context):
    """Agent should incorporate user context (region, supplier) into the query."""
    mock_response = MagicMock()
    mock_response.text = "Based on rates in Connecticut from Eversource, you could save $15/month."

    with patch("services.agent_service.settings") as mock_settings:
        mock_settings.gemini_api_key = "test-key"
        mock_settings.groq_api_key = None
        mock_settings.composio_api_key = None
        mock_settings.agent_free_daily_limit = 3
        mock_settings.agent_pro_daily_limit = 20

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        agent_service._gemini_client = mock_client

        messages = []
        async for msg in agent_service.query_streaming(
            user_id=str(uuid.uuid4()),
            prompt="How can I save?",
            context=user_context,
            db=mock_db,
        ):
            messages.append(msg)

        assert any(m.role == "assistant" for m in messages)
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0].model_used == "gemini-3-flash-preview"

        # Verify system prompt included user context (passed via config.system_instruction)
        call_args = mock_client.models.generate_content.call_args
        config = call_args.kwargs.get("config", {})
        system_instruction = config.get("system_instruction", "")
        assert "us_ct" in system_instruction or "Connecticut" in system_instruction or "Eversource" in system_instruction
        # User prompt should be passed separately as contents
        contents = call_args.kwargs.get("contents") or call_args[1].get("contents", "")
        assert contents == "How can I save?"


# =============================================================================
# Gemini 429 → Groq fallback
# =============================================================================


@pytest.mark.asyncio
async def test_gemini_429_falls_back_to_groq(agent_service, mock_db, user_context):
    """When Gemini returns 429, the service should transparently fall back to Groq."""
    with patch("services.agent_service.settings") as mock_settings:
        mock_settings.gemini_api_key = "test-key"
        mock_settings.groq_api_key = "test-groq-key"
        mock_settings.composio_api_key = None
        mock_settings.agent_free_daily_limit = 3
        mock_settings.agent_pro_daily_limit = 20

        # Gemini raises 429
        mock_gemini = MagicMock()
        mock_gemini.models.generate_content.side_effect = Exception("429 Resource Exhausted")
        agent_service._gemini_client = mock_gemini

        # Groq returns successfully
        mock_groq_response = MagicMock()
        mock_groq_response.choices = [MagicMock()]
        mock_groq_response.choices[0].message.content = "Groq says you can save money."

        mock_groq = AsyncMock()
        mock_groq.chat.completions.create = AsyncMock(return_value=mock_groq_response)
        agent_service._groq_client = mock_groq

        messages = []
        async for msg in agent_service.query_streaming(
            user_id=str(uuid.uuid4()),
            prompt="How can I save?",
            context=user_context,
            db=mock_db,
        ):
            messages.append(msg)

        assert any(m.role == "assistant" for m in messages)
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        assert assistant_msgs[0].model_used == "llama-3.3-70b-versatile"
        assert "save" in assistant_msgs[0].content.lower()


@pytest.mark.asyncio
async def test_gemini_non_429_error_no_fallback(agent_service, mock_db, user_context):
    """Non-429 Gemini errors should yield error, not fallback to Groq."""
    with patch("services.agent_service.settings") as mock_settings:
        mock_settings.gemini_api_key = "test-key"
        mock_settings.groq_api_key = "test-groq-key"
        mock_settings.composio_api_key = None
        mock_settings.agent_free_daily_limit = 3
        mock_settings.agent_pro_daily_limit = 20

        mock_gemini = MagicMock()
        mock_gemini.models.generate_content.side_effect = Exception("500 Internal Server Error")
        agent_service._gemini_client = mock_gemini

        messages = []
        async for msg in agent_service.query_streaming(
            user_id=str(uuid.uuid4()),
            prompt="How can I save?",
            context=user_context,
            db=mock_db,
        ):
            messages.append(msg)

        assert any(m.role == "error" for m in messages)


# =============================================================================
# Rate limiting per tier
# =============================================================================


@pytest.mark.asyncio
async def test_rate_limit_free_tier(agent_service, mock_db):
    """Free tier should be limited to agent_free_daily_limit."""
    with patch("services.agent_service.settings") as mock_settings:
        mock_settings.agent_free_daily_limit = 3
        mock_settings.agent_pro_daily_limit = 20

        # Simulate 3 queries already used
        mock_db.execute.return_value = MagicMock(scalar=MagicMock(return_value=3))

        allowed, used, limit = await agent_service.check_rate_limit(
            str(uuid.uuid4()), "free", mock_db
        )
        assert not allowed
        assert used == 3
        assert limit == 3


@pytest.mark.asyncio
async def test_rate_limit_pro_tier(agent_service, mock_db):
    """Pro tier should allow more queries."""
    with patch("services.agent_service.settings") as mock_settings:
        mock_settings.agent_free_daily_limit = 3
        mock_settings.agent_pro_daily_limit = 20

        # Simulate 5 queries used (within pro limit)
        mock_db.execute.return_value = MagicMock(scalar=MagicMock(return_value=5))

        allowed, used, limit = await agent_service.check_rate_limit(
            str(uuid.uuid4()), "pro", mock_db
        )
        assert allowed
        assert used == 5
        assert limit == 20


@pytest.mark.asyncio
async def test_rate_limit_business_unlimited(agent_service, mock_db):
    """Business tier should have unlimited queries."""
    allowed, used, limit = await agent_service.check_rate_limit(
        str(uuid.uuid4()), "business", mock_db
    )
    assert allowed
    assert limit == -1


# =============================================================================
# Usage stats
# =============================================================================


@pytest.mark.asyncio
async def test_get_usage_free_tier(agent_service, mock_db):
    """get_usage should return correct stats for free tier."""
    with patch("services.agent_service.settings") as mock_settings:
        mock_settings.agent_free_daily_limit = 3
        mock_settings.agent_pro_daily_limit = 20

        mock_db.execute.return_value = MagicMock(scalar=MagicMock(return_value=2))

        usage = await agent_service.get_usage(str(uuid.uuid4()), "free", mock_db)
        assert usage["used"] == 2
        assert usage["limit"] == 3
        assert usage["remaining"] == 1
        assert usage["tier"] == "free"


@pytest.mark.asyncio
async def test_get_usage_business_unlimited(agent_service, mock_db):
    """Business tier usage should show unlimited."""
    with patch("services.agent_service.settings") as mock_settings:
        mock_settings.agent_free_daily_limit = 3
        mock_settings.agent_pro_daily_limit = 20

        mock_db.execute.return_value = MagicMock(scalar=MagicMock(return_value=50))

        usage = await agent_service.get_usage(str(uuid.uuid4()), "business", mock_db)
        assert usage["limit"] == -1
        assert usage["remaining"] == -1


# =============================================================================
# Async job
# =============================================================================


@pytest.mark.asyncio
async def test_async_job_creation(agent_service, mock_db, user_context):
    """query_async should return a job_id string."""
    with patch("config.database.db_manager") as mock_dbm:
        mock_dbm.get_redis_client = AsyncMock(return_value=None)

        with patch.object(agent_service, "_run_async_job", new_callable=AsyncMock):
            job_id = await agent_service.query_async(
                user_id=str(uuid.uuid4()),
                prompt="Send me a report",
                context=user_context,
                db=mock_db,
            )

        assert isinstance(job_id, str)
        # Should be a valid UUID
        uuid.UUID(job_id)


@pytest.mark.asyncio
async def test_get_job_result_not_found(agent_service):
    """get_job_result should return not_found for unknown jobs."""
    with patch("config.database.db_manager") as mock_dbm:
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_dbm.get_redis_client = AsyncMock(return_value=mock_redis)

        result = await agent_service.get_job_result("nonexistent-job-id", user_id=str(uuid.uuid4()))
        assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_get_job_result_completed(agent_service):
    """get_job_result should return completed job data when user owns the job."""
    owner_id = str(uuid.uuid4())
    with patch("config.database.db_manager") as mock_dbm:
        mock_redis = AsyncMock()
        job_data = json.dumps({
            "status": "completed",
            "user_id": owner_id,
            "result": "Your report is ready.",
            "model_used": "gemini-3-flash-preview",
        })
        mock_redis.get = AsyncMock(return_value=job_data)
        mock_dbm.get_redis_client = AsyncMock(return_value=mock_redis)

        result = await agent_service.get_job_result("some-job-id", user_id=owner_id)
        assert result["status"] == "completed"
        assert result["result"] == "Your report is ready."


@pytest.mark.asyncio
async def test_get_job_result_idor_blocked(agent_service):
    """IDOR protection: requesting another user's job returns not_found."""
    owner_id = str(uuid.uuid4())
    attacker_id = str(uuid.uuid4())
    with patch("config.database.db_manager") as mock_dbm:
        mock_redis = AsyncMock()
        job_data = json.dumps({
            "status": "completed",
            "user_id": owner_id,
            "result": "Sensitive data.",
            "model_used": "gemini-3-flash-preview",
        })
        mock_redis.get = AsyncMock(return_value=job_data)
        mock_dbm.get_redis_client = AsyncMock(return_value=mock_redis)

        result = await agent_service.get_job_result("some-job-id", user_id=attacker_id)
        assert result["status"] == "not_found"
