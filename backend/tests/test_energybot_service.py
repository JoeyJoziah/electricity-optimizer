"""
Tests for EnergyBot API Service

All external HTTP calls are mocked. No real network traffic is made.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.energybot_service import (
    MAX_RETRIES,
    EnergyBotAuthError,
    EnergyBotError,
    EnergyBotRateLimitError,
    EnergyBotService,
    EnrollmentRequest,
    EnrollmentResult,
    EnrollmentStatus,
)

# =============================================================================
# Helpers
# =============================================================================


def _make_httpx_response(
    status_code: int = 200,
    json_data: dict | None = None,
) -> AsyncMock:
    """Build a mock httpx.Response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data or {}
    # raise_for_status() should be a no-op for 2xx; raise for 4xx/5xx
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=response,
        )
    else:
        response.raise_for_status.return_value = None
    return response


def _make_mapping_result(rows: list[dict]) -> MagicMock:
    """Build a mock SQLAlchemy result with .mappings()."""
    mock_result = MagicMock()
    mock_mappings = MagicMock()
    mock_mappings.all.return_value = rows
    mock_mappings.first.return_value = rows[0] if rows else None
    mock_result.mappings.return_value = mock_mappings
    return mock_result


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock async SQLAlchemy session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> EnergyBotService:
    """EnergyBotService with a mock DB and a patched API key."""
    svc = EnergyBotService(mock_db)
    svc._api_key = "test-api-key"
    return svc


@pytest.fixture
def mock_client() -> AsyncMock:
    """Mock httpx.AsyncClient."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.is_closed = False
    return client


@pytest.fixture
def sample_plans() -> list[dict]:
    """Two sample plan dicts representative of an EnergyBot response."""
    return [
        {
            "id": "plan_abc123",
            "plan_name": "Green Energy 12",
            "provider_name": "Acme Energy",
            "utility_code": "PECO",
            "state": "PA",
            "rate_kwh": 0.0899,
            "fixed_charge": 9.95,
            "term_months": 12,
            "etf_amount": 0.0,
            "renewable_pct": 100,
            "plan_url": "https://acme.example.com/plan/green12",
        },
        {
            "id": "plan_xyz789",
            "plan_name": "Budget Flex",
            "provider_name": "Budget Power Co",
            "utility_code": "PECO",
            "state": "PA",
            "rate_kwh": 0.0799,
            "fixed_charge": 0.0,
            "term_months": 1,
            "etf_amount": 0.0,
            "renewable_pct": 0,
            "plan_url": "https://budget.example.com/plan/flex",
        },
    ]


@pytest.fixture
def enrollment_request() -> EnrollmentRequest:
    """A valid EnrollmentRequest for tests."""
    return EnrollmentRequest(
        plan_id="plan_abc123",
        user_name="Jane Doe",
        service_address="123 Main St",
        zip_code="19103",
        utility_account_number="ACC-987654",
        idempotency_key="idem-key-001",
    )


# =============================================================================
# fetch_plans — success paths
# =============================================================================


class TestFetchPlansSuccess:
    @pytest.mark.asyncio
    async def test_returns_plans_on_success(
        self, service: EnergyBotService, mock_client: AsyncMock, sample_plans: list[dict]
    ) -> None:
        """fetch_plans returns the plans list from the API response."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            return_value=_make_httpx_response(200, {"plans": sample_plans})
        )

        with patch.object(service, "_cache_plans", new_callable=AsyncMock) as mock_cache:
            result = await service.fetch_plans("19103")

        assert result == sample_plans
        mock_cache.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(
        self, service: EnergyBotService, mock_client: AsyncMock
    ) -> None:
        """fetch_plans returns [] when the API returns no plans."""
        service._client = mock_client
        mock_client.request = AsyncMock(return_value=_make_httpx_response(200, {"plans": []}))

        with patch.object(service, "_cache_plans", new_callable=AsyncMock) as mock_cache:
            result = await service.fetch_plans("99999")

        assert result == []
        # Cache should NOT be called when there are no plans.
        mock_cache.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_passes_utility_code_as_query_param(
        self, service: EnergyBotService, mock_client: AsyncMock, sample_plans: list[dict]
    ) -> None:
        """fetch_plans includes utility_code in the request params when provided."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            return_value=_make_httpx_response(200, {"plans": sample_plans})
        )

        with patch.object(service, "_cache_plans", new_callable=AsyncMock):
            await service.fetch_plans("19103", utility_code="PECO")

        call_kwargs = mock_client.request.call_args.kwargs
        assert call_kwargs["params"]["utility"] == "PECO"

    @pytest.mark.asyncio
    async def test_caches_plans_to_available_plans_table(
        self,
        service: EnergyBotService,
        mock_db: AsyncMock,
        mock_client: AsyncMock,
        sample_plans: list[dict],
    ) -> None:
        """fetch_plans writes returned plans into the available_plans table."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            return_value=_make_httpx_response(200, {"plans": sample_plans})
        )
        # execute is called: 1 DELETE + 1 bulk INSERT
        mock_db.execute.return_value = MagicMock()

        await service.fetch_plans("19103", utility_code="PECO")

        # DELETE + 1 bulk INSERT = 2 execute calls
        assert mock_db.execute.call_count == 2
        mock_db.commit.assert_awaited_once()


# =============================================================================
# fetch_plans — retry behaviour
# =============================================================================


class TestFetchPlansRetry:
    @pytest.mark.asyncio
    async def test_retries_on_429_then_succeeds(
        self, service: EnergyBotService, mock_client: AsyncMock, sample_plans: list[dict]
    ) -> None:
        """fetch_plans retries on HTTP 429 and succeeds on the second attempt."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            side_effect=[
                _make_httpx_response(429),
                _make_httpx_response(200, {"plans": sample_plans}),
            ]
        )

        with (
            patch("services.energybot_service.asyncio.sleep", new_callable=AsyncMock),
            patch.object(service, "_cache_plans", new_callable=AsyncMock),
        ):
            result = await service.fetch_plans("19103")

        assert result == sample_plans
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_503_then_succeeds(
        self, service: EnergyBotService, mock_client: AsyncMock, sample_plans: list[dict]
    ) -> None:
        """fetch_plans retries on HTTP 503 and succeeds on the second attempt."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            side_effect=[
                _make_httpx_response(503),
                _make_httpx_response(200, {"plans": sample_plans}),
            ]
        )

        with (
            patch("services.energybot_service.asyncio.sleep", new_callable=AsyncMock),
            patch.object(service, "_cache_plans", new_callable=AsyncMock),
        ):
            result = await service.fetch_plans("19103")

        assert result == sample_plans


# =============================================================================
# get_plan_details
# =============================================================================


class TestGetPlanDetails:
    @pytest.mark.asyncio
    async def test_returns_plan_detail_on_success(
        self, service: EnergyBotService, mock_client: AsyncMock
    ) -> None:
        """get_plan_details returns the full detail dict from the API."""
        detail = {"id": "plan_abc123", "plan_name": "Green Energy 12", "rate_kwh": 0.0899}
        service._client = mock_client
        mock_client.request = AsyncMock(return_value=_make_httpx_response(200, detail))

        result = await service.get_plan_details("plan_abc123")

        assert result == detail
        call_args = mock_client.request.call_args
        assert call_args.args[1] == "/plans/plan_abc123"

    @pytest.mark.asyncio
    async def test_raises_on_404(self, service: EnergyBotService, mock_client: AsyncMock) -> None:
        """get_plan_details raises EnergyBotError when the plan is not found (404)."""
        service._client = mock_client
        # 404 triggers raise_for_status which raises HTTPStatusError,
        # which the service wraps as EnergyBotError via the httpx.HTTPError handler.
        response = _make_httpx_response(404)
        # 404 is not caught by the 401/429/5xx guards; raise_for_status fires.
        mock_client.request = AsyncMock(return_value=response)

        with pytest.raises(EnergyBotError):
            await service.get_plan_details("plan_nonexistent")


# =============================================================================
# create_enrollment
# =============================================================================


class TestCreateEnrollment:
    @pytest.mark.asyncio
    async def test_success_returns_enrollment_result(
        self,
        service: EnergyBotService,
        mock_client: AsyncMock,
        enrollment_request: EnrollmentRequest,
    ) -> None:
        """create_enrollment returns a populated EnrollmentResult on success."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            return_value=_make_httpx_response(
                200,
                {
                    "enrollment_id": "enroll_001",
                    "status": "submitted",
                    "estimated_switch_date": "2026-05-01T00:00:00",
                    "message": "Enrollment received",
                },
            )
        )

        result = await service.create_enrollment(enrollment_request, "idem-key-001")

        assert isinstance(result, EnrollmentResult)
        assert result.enrollment_id == "enroll_001"
        assert result.status == "submitted"
        assert result.message == "Enrollment received"
        assert result.estimated_switch_date is not None

    @pytest.mark.asyncio
    async def test_idempotency_key_is_sent_in_request_body(
        self,
        service: EnergyBotService,
        mock_client: AsyncMock,
        enrollment_request: EnrollmentRequest,
    ) -> None:
        """create_enrollment forwards the idempotency_key in the JSON body."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            return_value=_make_httpx_response(
                200, {"enrollment_id": "enroll_002", "status": "submitted"}
            )
        )

        await service.create_enrollment(enrollment_request, "unique-idem-key-xyz")

        sent_json = mock_client.request.call_args.kwargs["json"]
        assert sent_json["idempotency_key"] == "unique-idem-key-xyz"

    @pytest.mark.asyncio
    async def test_rejected_enrollment_still_returns_result(
        self,
        service: EnergyBotService,
        mock_client: AsyncMock,
        enrollment_request: EnrollmentRequest,
    ) -> None:
        """A rejected enrollment from the API is surfaced as an EnrollmentResult (not an exception)."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            return_value=_make_httpx_response(
                200,
                {
                    "enrollment_id": "enroll_rejected",
                    "status": "rejected",
                    "message": "Account number invalid",
                },
            )
        )

        result = await service.create_enrollment(enrollment_request, "idem-rej")

        assert result.status == "rejected"
        assert result.enrollment_id == "enroll_rejected"

    @pytest.mark.asyncio
    async def test_server_error_raises_energybot_error(
        self,
        service: EnergyBotService,
        mock_client: AsyncMock,
        enrollment_request: EnrollmentRequest,
    ) -> None:
        """create_enrollment propagates EnergyBotError on 5xx after retries."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            side_effect=[
                _make_httpx_response(500),
                _make_httpx_response(500),
                _make_httpx_response(500),
            ]
        )

        with (
            patch("services.energybot_service.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(EnergyBotError),
        ):
            await service.create_enrollment(enrollment_request, "idem-500")

    @pytest.mark.asyncio
    async def test_estimated_switch_date_is_none_when_absent(
        self,
        service: EnergyBotService,
        mock_client: AsyncMock,
        enrollment_request: EnrollmentRequest,
    ) -> None:
        """estimated_switch_date is None when the API omits the field."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            return_value=_make_httpx_response(
                200, {"enrollment_id": "enroll_003", "status": "processing"}
            )
        )

        result = await service.create_enrollment(enrollment_request, "idem-003")

        assert result.estimated_switch_date is None


# =============================================================================
# check_enrollment_status
# =============================================================================


class TestCheckEnrollmentStatus:
    @pytest.mark.asyncio
    async def test_submitted_status(
        self, service: EnergyBotService, mock_client: AsyncMock
    ) -> None:
        """Returns EnrollmentStatus with status='submitted'."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            return_value=_make_httpx_response(200, {"status": "submitted"})
        )

        status = await service.check_enrollment_status("enroll_sub")

        assert isinstance(status, EnrollmentStatus)
        assert status.status == "submitted"
        assert status.enrollment_id == "enroll_sub"

    @pytest.mark.asyncio
    async def test_accepted_status(self, service: EnergyBotService, mock_client: AsyncMock) -> None:
        """Returns EnrollmentStatus with status='accepted'."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            return_value=_make_httpx_response(200, {"status": "accepted"})
        )

        status = await service.check_enrollment_status("enroll_acc")

        assert status.status == "accepted"

    @pytest.mark.asyncio
    async def test_active_status_with_switch_date(
        self, service: EnergyBotService, mock_client: AsyncMock
    ) -> None:
        """Active enrollment includes a parsed switch_date."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            return_value=_make_httpx_response(
                200,
                {"status": "active", "switch_date": "2026-05-01T00:00:00"},
            )
        )

        status = await service.check_enrollment_status("enroll_act")

        assert status.status == "active"
        assert status.switch_date is not None
        assert status.switch_date.year == 2026
        assert status.switch_date.month == 5

    @pytest.mark.asyncio
    async def test_rejected_status_includes_reason(
        self, service: EnergyBotService, mock_client: AsyncMock
    ) -> None:
        """Rejected enrollment exposes the rejection_reason field."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            return_value=_make_httpx_response(
                200,
                {
                    "status": "rejected",
                    "rejection_reason": "Utility account not found",
                },
            )
        )

        status = await service.check_enrollment_status("enroll_rej")

        assert status.status == "rejected"
        assert status.rejection_reason == "Utility account not found"


# =============================================================================
# cancel_enrollment
# =============================================================================


class TestCancelEnrollment:
    @pytest.mark.asyncio
    async def test_returns_true_on_successful_cancellation(
        self, service: EnergyBotService, mock_client: AsyncMock
    ) -> None:
        """cancel_enrollment returns True when the API confirms cancellation."""
        service._client = mock_client
        mock_client.request = AsyncMock(return_value=_make_httpx_response(200, {"cancelled": True}))

        result = await service.cancel_enrollment("enroll_cancel")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_already_processed(
        self, service: EnergyBotService, mock_client: AsyncMock
    ) -> None:
        """cancel_enrollment returns False when the API says cancelled=False (already processed)."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            return_value=_make_httpx_response(200, {"cancelled": False, "reason": "Already active"})
        )

        result = await service.cancel_enrollment("enroll_active")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_api_error(
        self, service: EnergyBotService, mock_client: AsyncMock
    ) -> None:
        """cancel_enrollment returns False (never raises) when the API fails."""
        service._client = mock_client
        mock_client.request = AsyncMock(
            side_effect=[
                _make_httpx_response(500),
                _make_httpx_response(500),
                _make_httpx_response(500),
            ]
        )

        with patch("services.energybot_service.asyncio.sleep", new_callable=AsyncMock):
            result = await service.cancel_enrollment("enroll_error")

        assert result is False


# =============================================================================
# _request — error handling and retry mechanics
# =============================================================================


class TestRequestErrorHandling:
    @pytest.mark.asyncio
    async def test_auth_error_raises_immediately_without_retry(
        self, service: EnergyBotService, mock_client: AsyncMock
    ) -> None:
        """A 401 response raises EnergyBotAuthError immediately, no retries attempted."""
        service._client = mock_client
        mock_client.request = AsyncMock(return_value=_make_httpx_response(401))

        with pytest.raises(EnergyBotAuthError) as exc_info:
            await service._request("GET", "/plans")

        assert exc_info.value.status_code == 401
        # Only one attempt — never retried.
        assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_timeout_triggers_retry_then_raises(
        self, service: EnergyBotService, mock_client: AsyncMock
    ) -> None:
        """TimeoutException triggers the retry loop and ultimately raises EnergyBotError."""
        service._client = mock_client
        mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with (
            patch("services.energybot_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            pytest.raises(EnergyBotError, match="timed out"),
        ):
            await service._request("GET", "/plans")

        # MAX_RETRIES=3, so 2 sleep calls between 3 attempts.
        assert mock_sleep.await_count == MAX_RETRIES - 1
        assert mock_client.request.call_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_max_retries_exceeded_raises_last_error(
        self, service: EnergyBotService, mock_client: AsyncMock
    ) -> None:
        """After MAX_RETRIES exhausted on 429, the final EnergyBotRateLimitError propagates."""
        service._client = mock_client
        mock_client.request = AsyncMock(side_effect=[_make_httpx_response(429)] * MAX_RETRIES)

        with (
            patch("services.energybot_service.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(EnergyBotRateLimitError),
        ):
            await service._request("GET", "/plans")

        assert mock_client.request.call_count == MAX_RETRIES


# =============================================================================
# HTTP client lifecycle
# =============================================================================


class TestClientLifecycle:
    @pytest.mark.asyncio
    async def test_client_reuse_singleton(self, service: EnergyBotService) -> None:
        """_get_client returns the same client instance on repeated calls."""
        client_a = await service._get_client()
        client_b = await service._get_client()

        assert client_a is client_b

    @pytest.mark.asyncio
    async def test_close_acloses_client(
        self, service: EnergyBotService, mock_client: AsyncMock
    ) -> None:
        """close() calls aclose() on the underlying httpx client."""
        service._client = mock_client
        mock_client.is_closed = False

        await service.close()

        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_noop_when_client_already_closed(
        self, service: EnergyBotService, mock_client: AsyncMock
    ) -> None:
        """close() is safe to call when the client is already closed."""
        service._client = mock_client
        mock_client.is_closed = True

        await service.close()

        mock_client.aclose.assert_not_awaited()


# =============================================================================
# create_enrollment — timeout handling
# =============================================================================


class TestCreateEnrollmentTimeout:
    @pytest.mark.asyncio
    async def test_timeout_wraps_as_energybot_error(
        self,
        service: EnergyBotService,
        mock_client: AsyncMock,
        enrollment_request: EnrollmentRequest,
    ) -> None:
        """A timeout during create_enrollment propagates as EnergyBotError after retries."""
        service._client = mock_client
        mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("connect timeout"))

        with (
            patch("services.energybot_service.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(EnergyBotError, match="timed out"),
        ):
            await service.create_enrollment(enrollment_request, "idem-timeout")

        # All MAX_RETRIES attempts were made.
        assert mock_client.request.call_count == MAX_RETRIES
