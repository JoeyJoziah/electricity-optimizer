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

from services.agent_service import MAX_PROMPT_LENGTH, AgentService

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
        assert (
            "us_ct" in system_instruction
            or "Connecticut" in system_instruction
            or "Eversource" in system_instruction
        )
        # User prompt should be passed separately as contents
        contents = call_args.kwargs.get("contents") or call_args[1].get("contents", "")
        assert contents == "How can I save?"


# =============================================================================
# Gemini 429 → Groq fallback
# =============================================================================


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


async def test_get_job_result_not_found(agent_service):
    """get_job_result should return not_found for unknown jobs."""
    with patch("config.database.db_manager") as mock_dbm:
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_dbm.get_redis_client = AsyncMock(return_value=mock_redis)

        result = await agent_service.get_job_result("nonexistent-job-id", user_id=str(uuid.uuid4()))
        assert result["status"] == "not_found"


async def test_get_job_result_completed(agent_service):
    """get_job_result should return completed job data when user owns the job."""
    owner_id = str(uuid.uuid4())
    with patch("config.database.db_manager") as mock_dbm:
        mock_redis = AsyncMock()
        job_data = json.dumps(
            {
                "status": "completed",
                "user_id": owner_id,
                "result": "Your report is ready.",
                "model_used": "gemini-3-flash-preview",
            }
        )
        mock_redis.get = AsyncMock(return_value=job_data)
        mock_dbm.get_redis_client = AsyncMock(return_value=mock_redis)

        result = await agent_service.get_job_result("some-job-id", user_id=owner_id)
        assert result["status"] == "completed"
        assert result["result"] == "Your report is ready."


async def test_get_job_result_idor_blocked(agent_service):
    """IDOR protection: requesting another user's job returns not_found."""
    owner_id = str(uuid.uuid4())
    attacker_id = str(uuid.uuid4())
    with patch("config.database.db_manager") as mock_dbm:
        mock_redis = AsyncMock()
        job_data = json.dumps(
            {
                "status": "completed",
                "user_id": owner_id,
                "result": "Sensitive data.",
                "model_used": "gemini-3-flash-preview",
            }
        )
        mock_redis.get = AsyncMock(return_value=job_data)
        mock_dbm.get_redis_client = AsyncMock(return_value=mock_redis)

        result = await agent_service.get_job_result("some-job-id", user_id=attacker_id)
        assert result["status"] == "not_found"


# =============================================================================
# S3-2: Groq empty choices guard
# =============================================================================


async def test_groq_empty_choices_raises_value_error(agent_service):
    """S3-2: _query_groq must raise ValueError when choices is empty, not IndexError."""
    mock_response = MagicMock()
    mock_response.choices = []  # empty — no completion produced

    mock_groq = AsyncMock()
    mock_groq.chat.completions.create = AsyncMock(return_value=mock_response)
    agent_service._groq_client = mock_groq

    with pytest.raises(ValueError, match="empty choices array"):
        await agent_service._query_groq("system prompt", "user prompt")


async def test_groq_empty_choices_surfaced_as_error_message(agent_service, mock_db, user_context):
    """S3-2: When Groq returns empty choices during a streaming query the caller
    receives an 'error' role message, not an unhandled 500."""
    with patch("services.agent_service.settings") as mock_settings:
        mock_settings.gemini_api_key = "test-key"
        mock_settings.groq_api_key = "test-groq-key"
        mock_settings.composio_api_key = None
        mock_settings.agent_free_daily_limit = 3
        mock_settings.agent_pro_daily_limit = 20

        # Gemini raises 429 so we fall through to Groq
        mock_gemini = MagicMock()
        mock_gemini.models.generate_content.side_effect = Exception("429 Resource Exhausted")
        agent_service._gemini_client = mock_gemini

        # Groq returns a response with no choices
        mock_groq_response = MagicMock()
        mock_groq_response.choices = []

        mock_groq = AsyncMock()
        mock_groq.chat.completions.create = AsyncMock(return_value=mock_groq_response)
        agent_service._groq_client = mock_groq

        messages = []
        async for msg in agent_service.query_streaming(
            user_id=str(uuid.uuid4()),
            prompt="What are my rates?",
            context=user_context,
            db=mock_db,
        ):
            messages.append(msg)

    assert any(m.role == "error" for m in messages), "Expected error role when choices is empty"
    # Must not have raised IndexError — reaching this line proves it
    error_msgs = [m for m in messages if m.role == "error"]
    assert error_msgs, "Should have at least one error message"


async def test_groq_non_empty_choices_returns_content(agent_service):
    """S3-2: _query_groq returns content when choices is non-empty (regression guard)."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Your rate is 12 cents/kWh."

    mock_groq = AsyncMock()
    mock_groq.chat.completions.create = AsyncMock(return_value=mock_response)
    agent_service._groq_client = mock_groq

    result = await agent_service._query_groq("system prompt", "user prompt")
    assert result == "Your rate is 12 cents/kWh."


# =============================================================================
# S3-4: Atomic rate-limit check-and-increment
# =============================================================================


async def test_increment_usage_atomic_allowed(agent_service, mock_db):
    """S3-4: increment_usage_atomic returns (True, new_count) when under the limit."""
    with patch("services.agent_service.settings") as mock_settings:
        mock_settings.agent_free_daily_limit = 3
        mock_settings.agent_pro_daily_limit = 20

        # First execute: INSERT DO NOTHING (no return value needed)
        # Second execute: UPDATE RETURNING — returns new count of 2
        insert_result = MagicMock()
        insert_result.scalar = MagicMock(return_value=None)
        update_result = MagicMock()
        update_result.scalar = MagicMock(return_value=2)

        mock_db.execute = AsyncMock(side_effect=[insert_result, update_result])

        allowed, new_count = await agent_service.increment_usage_atomic(
            str(uuid.uuid4()), "free", mock_db
        )

    assert allowed is True
    assert new_count == 2
    mock_db.commit.assert_called_once()


async def test_increment_usage_atomic_denied_at_limit(agent_service, mock_db):
    """S3-4: increment_usage_atomic returns (False, current_count) when at the limit."""
    with patch("services.agent_service.settings") as mock_settings:
        mock_settings.agent_free_daily_limit = 3
        mock_settings.agent_pro_daily_limit = 20

        # INSERT DO NOTHING
        insert_result = MagicMock()
        insert_result.scalar = MagicMock(return_value=None)
        # UPDATE RETURNING — returns None (WHERE count < limit was false)
        update_result = MagicMock()
        update_result.scalar = MagicMock(return_value=None)
        # Fallback SELECT — returns current count (already at limit)
        select_result = MagicMock()
        select_result.scalar = MagicMock(return_value=3)

        mock_db.execute = AsyncMock(side_effect=[insert_result, update_result, select_result])

        allowed, current_count = await agent_service.increment_usage_atomic(
            str(uuid.uuid4()), "free", mock_db
        )

    assert allowed is False
    assert current_count == 3
    # commit must NOT have been called — no increment happened
    mock_db.commit.assert_not_called()


async def test_increment_usage_atomic_business_tier_skips_db(agent_service, mock_db):
    """S3-4: Business tier returns (True, 0) immediately without touching the DB."""
    allowed, count = await agent_service.increment_usage_atomic(
        str(uuid.uuid4()), "business", mock_db
    )
    assert allowed is True
    assert count == 0
    mock_db.execute.assert_not_called()


async def test_increment_usage_atomic_pro_tier_uses_pro_limit(agent_service, mock_db):
    """S3-4: Pro tier uses agent_pro_daily_limit, not the free limit."""
    with patch("services.agent_service.settings") as mock_settings:
        mock_settings.agent_free_daily_limit = 3
        mock_settings.agent_pro_daily_limit = 20

        insert_result = MagicMock()
        insert_result.scalar = MagicMock(return_value=None)
        # UPDATE succeeds — returns count 15 (well within pro limit)
        update_result = MagicMock()
        update_result.scalar = MagicMock(return_value=15)

        mock_db.execute = AsyncMock(side_effect=[insert_result, update_result])

        allowed, new_count = await agent_service.increment_usage_atomic(
            str(uuid.uuid4()), "pro", mock_db
        )

    assert allowed is True
    assert new_count == 15
    # Verify the UPDATE was called with limit=20 (pro), not 3 (free)
    update_call_kwargs = mock_db.execute.call_args_list[1]
    params = update_call_kwargs[0][1]  # positional args: (text_obj, params_dict)
    assert params["limit"] == 20


# =============================================================================
# S3-5: Background task session lifecycle contract
# =============================================================================


async def test_run_async_job_no_db_param(agent_service):
    """S3-5: _run_async_job must not accept a 'db' parameter — it is a background
    task and must not use a request-scoped session."""
    import inspect

    sig = inspect.signature(agent_service._run_async_job)
    assert "db" not in sig.parameters, (
        "_run_async_job must not have a 'db' parameter because the request-scoped "
        "AsyncSession is closed before the background task completes."
    )


async def test_run_async_job_docstring_documents_no_db_contract(agent_service):
    """S3-5: The no-DB contract must be documented in the method docstring so
    future developers understand the session lifecycle constraint."""
    docstring = agent_service._run_async_job.__doc__ or ""
    assert (
        "db" in docstring.lower() or "session" in docstring.lower()
    ), "_run_async_job docstring should reference the DB/session lifecycle contract"
    assert (
        "request" in docstring.lower() or "background" in docstring.lower()
    ), "_run_async_job docstring should mention it is a background task"


async def test_run_async_job_completes_without_db_session(agent_service):
    """S3-5: _run_async_job runs successfully with only the redis parameter —
    no DB session is passed or required."""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()

    with patch.object(
        agent_service,
        "_query_gemini",
        new=AsyncMock(return_value="Energy tip: shift usage to off-peak hours."),
    ):
        # Must not raise even though no db session is supplied
        await agent_service._run_async_job(
            job_id="test-job-123",
            user_id=str(uuid.uuid4()),
            prompt="Give me energy saving tips",
            context={"region": "us_ct", "supplier": "Eversource", "tier": "free"},
            redis=mock_redis,
        )

    mock_redis.set.assert_called_once()
    stored = json.loads(mock_redis.set.call_args[0][1])
    assert stored["status"] == "completed"
    assert "Energy tip" in stored["result"]


async def test_run_async_job_stores_failure_without_db_session(agent_service):
    """S3-5: When both LLM providers fail, _run_async_job records the failure
    in Redis without needing a DB session."""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()

    with (
        patch.object(
            agent_service, "_query_gemini", new=AsyncMock(side_effect=Exception("Gemini down"))
        ),
        patch.object(
            agent_service, "_query_groq", new=AsyncMock(side_effect=Exception("Groq down"))
        ),
    ):
        await agent_service._run_async_job(
            job_id="fail-job-456",
            user_id=str(uuid.uuid4()),
            prompt="What are peak hours?",
            context={"region": "us_ny", "supplier": "ConEd", "tier": "pro"},
            redis=mock_redis,
        )

    mock_redis.set.assert_called_once()
    stored = json.loads(mock_redis.set.call_args[0][1])
    assert stored["status"] == "failed"
    assert "error" in stored
