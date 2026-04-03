"""
Tests for Arcadia Arc API Service

All Arcadia HTTP calls are mocked — the API contract is not yet in place.
Tests verify retry logic, error classification, DB interactions, and batch
insert behaviour using only pytest + unittest.mock (no live network calls).
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.arcadia_service import (
    MAX_RETRIES,
    ArcadiaAuthError,
    ArcadiaError,
    ArcadiaRateLimitError,
    ArcadiaService,
)

# =============================================================================
# Helpers
# =============================================================================


def _make_mapping_result(rows: list[dict]) -> MagicMock:
    """Return a mock SQLAlchemy result whose ``.mappings().first()`` resolves."""
    mock_result = MagicMock()
    mock_mappings = MagicMock()
    mock_mappings.first.return_value = rows[0] if rows else None
    mock_mappings.all.return_value = rows
    mock_result.mappings.return_value = mock_mappings
    return mock_result


def _make_httpx_response(
    status_code: int = 200,
    json_data: dict | None = None,
) -> MagicMock:
    """Build a minimal mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    return resp


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db() -> AsyncMock:
    """Async DB session stub."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> ArcadiaService:
    """ArcadiaService wired to the mock DB."""
    return ArcadiaService(mock_db)


@pytest.fixture
def mock_client() -> AsyncMock:
    """A mock httpx.AsyncClient whose ``.request()`` is an AsyncMock."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.is_closed = False
    return client


# =============================================================================
# connect_account
# =============================================================================


class TestConnectAccount:
    @pytest.mark.asyncio
    async def test_success(self, service: ArcadiaService, mock_client: AsyncMock) -> None:
        """Returns the parsed account object on 200."""
        mock_client.request.return_value = _make_httpx_response(
            200, {"account_id": "arc_acc_1", "status": "active"}
        )
        service._client = mock_client

        result = await service.connect_account("user_1", "auth_code_abc")

        assert result["account_id"] == "arc_acc_1"
        mock_client.request.assert_awaited_once()
        call_kwargs = mock_client.request.call_args
        assert call_kwargs.args[0] == "POST"
        assert "/accounts/connect" in call_kwargs.args[1]

    @pytest.mark.asyncio
    async def test_auth_failure_401(self, service: ArcadiaService, mock_client: AsyncMock) -> None:
        """Raises ArcadiaAuthError on HTTP 401."""
        mock_client.request.return_value = _make_httpx_response(401)
        service._client = mock_client

        with pytest.raises(ArcadiaAuthError) as exc_info:
            await service.connect_account("user_1", "bad_code")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_auth_code_returns_auth_error(
        self, service: ArcadiaService, mock_client: AsyncMock
    ) -> None:
        """An invalid auth code from Arcadia surfaces as ArcadiaAuthError."""
        mock_client.request.return_value = _make_httpx_response(401, {"error": "invalid_code"})
        service._client = mock_client

        with pytest.raises(ArcadiaAuthError):
            await service.connect_account("user_1", "totally_wrong_code")


# =============================================================================
# fetch_interval_data
# =============================================================================


class TestFetchIntervalData:
    @pytest.mark.asyncio
    async def test_success_with_data(self, service: ArcadiaService, mock_client: AsyncMock) -> None:
        """Returns the intervals list from the response payload."""
        intervals = [
            {"timestamp": "2024-06-01T00:00:00", "kwh": 1.2, "interval_minutes": 60},
            {"timestamp": "2024-06-01T01:00:00", "kwh": 0.9, "interval_minutes": 60},
        ]
        mock_client.request.return_value = _make_httpx_response(200, {"intervals": intervals})
        service._client = mock_client

        start = datetime(2024, 6, 1)
        end = datetime(2024, 6, 2)
        result = await service.fetch_interval_data("acc_1", start, end)

        assert result == intervals
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_result(self, service: ArcadiaService, mock_client: AsyncMock) -> None:
        """Returns an empty list when the API returns no intervals."""
        mock_client.request.return_value = _make_httpx_response(200, {"intervals": []})
        service._client = mock_client

        result = await service.fetch_interval_data(
            "acc_empty", datetime(2024, 1, 1), datetime(2024, 1, 2)
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_date_range_passed_as_params(
        self, service: ArcadiaService, mock_client: AsyncMock
    ) -> None:
        """ISO-formatted start/end are forwarded as query parameters."""
        mock_client.request.return_value = _make_httpx_response(200, {"intervals": []})
        service._client = mock_client

        start = datetime(2024, 3, 10, 8, 0, 0)
        end = datetime(2024, 3, 11, 8, 0, 0)
        await service.fetch_interval_data("acc_dt", start, end)

        call_kwargs = mock_client.request.call_args.kwargs
        params = call_kwargs["params"]
        assert params["start"] == start.isoformat()
        assert params["end"] == end.isoformat()

    @pytest.mark.asyncio
    async def test_rate_limit_retry_succeeds(
        self, service: ArcadiaService, mock_client: AsyncMock
    ) -> None:
        """Retries on 429 and returns data after a successful retry."""
        mock_client.request.side_effect = [
            _make_httpx_response(429),
            _make_httpx_response(200, {"intervals": [{"timestamp": "t", "kwh": 1.0}]}),
        ]
        service._client = mock_client

        with patch("services.arcadia_service.asyncio.sleep", new_callable=AsyncMock):
            result = await service.fetch_interval_data(
                "acc_rl", datetime(2024, 1, 1), datetime(2024, 1, 2)
            )

        assert len(result) == 1
        assert mock_client.request.await_count == 2

    @pytest.mark.asyncio
    async def test_server_error_retry_succeeds(
        self, service: ArcadiaService, mock_client: AsyncMock
    ) -> None:
        """Retries on 503 and returns data on a successful follow-up call."""
        mock_client.request.side_effect = [
            _make_httpx_response(503),
            _make_httpx_response(200, {"intervals": [{"timestamp": "t", "kwh": 0.5}]}),
        ]
        service._client = mock_client

        with patch("services.arcadia_service.asyncio.sleep", new_callable=AsyncMock):
            result = await service.fetch_interval_data(
                "acc_503", datetime(2024, 1, 1), datetime(2024, 1, 2)
            )

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_timeout_retry_then_error(
        self, service: ArcadiaService, mock_client: AsyncMock
    ) -> None:
        """Exhausts retries on repeated timeouts and raises ArcadiaError."""
        mock_client.request.side_effect = httpx.TimeoutException("timed out")
        service._client = mock_client

        with patch("services.arcadia_service.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ArcadiaError, match="timed out"):
                await service.fetch_interval_data(
                    "acc_to", datetime(2024, 1, 1), datetime(2024, 1, 2)
                )

        assert mock_client.request.await_count == MAX_RETRIES


# =============================================================================
# fetch_bills
# =============================================================================


class TestFetchBills:
    @pytest.mark.asyncio
    async def test_success(self, service: ArcadiaService, mock_client: AsyncMock) -> None:
        """Returns the bills list from the response payload."""
        bills = [
            {"bill_id": "b1", "amount": 120.50, "period_start": "2024-05-01"},
            {"bill_id": "b2", "amount": 98.00, "period_start": "2024-04-01"},
        ]
        mock_client.request.return_value = _make_httpx_response(200, {"bills": bills})
        service._client = mock_client

        result = await service.fetch_bills("acc_bills")

        assert result == bills
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_bills(self, service: ArcadiaService, mock_client: AsyncMock) -> None:
        """Returns an empty list when there are no bills."""
        mock_client.request.return_value = _make_httpx_response(200, {"bills": []})
        service._client = mock_client

        result = await service.fetch_bills("acc_no_bills")

        assert result == []


# =============================================================================
# sync_meter_readings
# =============================================================================


class TestSyncMeterReadings:
    @pytest.mark.asyncio
    async def test_success_inserts_readings(
        self, service: ArcadiaService, mock_db: AsyncMock, mock_client: AsyncMock
    ) -> None:
        """Inserts interval data into meter_readings and returns the count."""
        mock_db.execute.side_effect = [
            _make_mapping_result(
                [
                    {
                        "id": "conn_1",
                        "metadata": {"provider": "arcadia", "arcadia_account_id": "arc_1"},
                    }
                ]
            ),
            _make_mapping_result([{"last_time": None}]),
            MagicMock(),  # INSERT
        ]
        mock_client.request.return_value = _make_httpx_response(
            200,
            {
                "intervals": [
                    {"timestamp": "2024-06-01T00:00:00", "kwh": 1.2, "interval_minutes": 60},
                    {"timestamp": "2024-06-01T01:00:00", "kwh": 0.9, "interval_minutes": 60},
                ]
            },
        )
        service._client = mock_client

        count = await service.sync_meter_readings("user_sync")

        assert count == 2
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_connection_returns_zero(
        self, service: ArcadiaService, mock_db: AsyncMock
    ) -> None:
        """Returns 0 and makes no HTTP calls when no Arcadia connection exists."""
        mock_db.execute.return_value = _make_mapping_result([])

        count = await service.sync_meter_readings("user_no_conn")

        assert count == 0
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_account_id_in_metadata_returns_zero(
        self, service: ArcadiaService, mock_db: AsyncMock
    ) -> None:
        """Returns 0 when the connection row has no arcadia_account_id."""
        mock_db.execute.return_value = _make_mapping_result(
            [{"id": "conn_2", "metadata": {"provider": "arcadia"}}]
        )

        count = await service.sync_meter_readings("user_no_acc_id")

        assert count == 0
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_intervals_returns_zero(
        self, service: ArcadiaService, mock_db: AsyncMock, mock_client: AsyncMock
    ) -> None:
        """Returns 0 when the API returns an empty intervals list."""
        mock_db.execute.side_effect = [
            _make_mapping_result(
                [
                    {
                        "id": "conn_3",
                        "metadata": {"provider": "arcadia", "arcadia_account_id": "arc_3"},
                    }
                ]
            ),
            _make_mapping_result([{"last_time": None}]),
        ]
        mock_client.request.return_value = _make_httpx_response(200, {"intervals": []})
        service._client = mock_client

        count = await service.sync_meter_readings("user_empty")

        assert count == 0
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_batch_insert_over_500_readings(
        self, service: ArcadiaService, mock_db: AsyncMock, mock_client: AsyncMock
    ) -> None:
        """Splits > 500 intervals into multiple INSERT statements."""
        intervals = [
            {"timestamp": f"2024-01-01T{i:05d}", "kwh": 0.5, "interval_minutes": 30}
            for i in range(750)
        ]
        mock_db.execute.side_effect = [
            _make_mapping_result(
                [
                    {
                        "id": "conn_batch",
                        "metadata": {"provider": "arcadia", "arcadia_account_id": "arc_b"},
                    }
                ]
            ),
            _make_mapping_result([{"last_time": None}]),
            MagicMock(),  # first batch (500)
            MagicMock(),  # second batch (250)
        ]
        mock_client.request.return_value = _make_httpx_response(200, {"intervals": intervals})
        service._client = mock_client

        count = await service.sync_meter_readings("user_batch")

        # 2 SELECT calls (connection lookup + last reading) + 2 INSERT calls
        # (500-row batch + 250-row batch) = 4 total execute calls.
        assert mock_db.execute.await_count == 4
        assert count == 750
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_incremental_sync_uses_last_reading_time(
        self, service: ArcadiaService, mock_db: AsyncMock, mock_client: AsyncMock
    ) -> None:
        """Uses the stored MAX(reading_time) as the start of the fetch window."""
        last_time = datetime(2024, 5, 15, 12, 0, 0)
        mock_db.execute.side_effect = [
            _make_mapping_result(
                [
                    {
                        "id": "conn_inc",
                        "metadata": {"provider": "arcadia", "arcadia_account_id": "arc_i"},
                    }
                ]
            ),
            _make_mapping_result([{"last_time": last_time}]),
            MagicMock(),  # INSERT
        ]
        mock_client.request.return_value = _make_httpx_response(
            200,
            {
                "intervals": [
                    {"timestamp": "2024-05-15T13:00:00", "kwh": 1.1, "interval_minutes": 60}
                ]
            },
        )
        service._client = mock_client

        await service.sync_meter_readings("user_inc")

        request_call = mock_client.request.call_args
        params = request_call.kwargs["params"]
        assert params["start"] == last_time.isoformat()


# =============================================================================
# _request — retry and error-classification logic
# =============================================================================


class TestRequestRetryLogic:
    @pytest.mark.asyncio
    async def test_retries_on_429(self, service: ArcadiaService, mock_client: AsyncMock) -> None:
        """_request retries up to MAX_RETRIES on 429 responses."""
        # All attempts return 429 → should exhaust and raise.
        mock_client.request.return_value = _make_httpx_response(429)
        service._client = mock_client

        with patch("services.arcadia_service.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ArcadiaRateLimitError):
                await service._request("GET", "/test")

        assert mock_client.request.await_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_retries_on_503(self, service: ArcadiaService, mock_client: AsyncMock) -> None:
        """_request retries up to MAX_RETRIES on 503 responses."""
        mock_client.request.return_value = _make_httpx_response(503)
        service._client = mock_client

        with patch("services.arcadia_service.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ArcadiaError) as exc_info:
                await service._request("GET", "/test")

        assert exc_info.value.status_code == 503
        assert mock_client.request.await_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_no_retry_on_401(self, service: ArcadiaService, mock_client: AsyncMock) -> None:
        """_request does not retry on HTTP 401 — raises ArcadiaAuthError immediately."""
        mock_client.request.return_value = _make_httpx_response(401)
        service._client = mock_client

        with pytest.raises(ArcadiaAuthError):
            await service._request("GET", "/test")

        mock_client.request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self, service: ArcadiaService, mock_client: AsyncMock) -> None:
        """_request raises ArcadiaError immediately on 400 (bad request)."""
        bad_resp = _make_httpx_response(400)
        bad_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "bad request", request=MagicMock(), response=bad_resp
        )
        mock_client.request.return_value = bad_resp
        service._client = mock_client

        with pytest.raises((ArcadiaError, httpx.HTTPStatusError)):
            await service._request("GET", "/test")

        mock_client.request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_max_retries_exceeded_raises(
        self, service: ArcadiaService, mock_client: AsyncMock
    ) -> None:
        """After MAX_RETRIES failures the last exception is re-raised."""
        mock_client.request.return_value = _make_httpx_response(503)
        service._client = mock_client

        with patch("services.arcadia_service.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ArcadiaError):
                await service._request("GET", "/exhausted")

        assert mock_client.request.await_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_timeout_handling(self, service: ArcadiaService, mock_client: AsyncMock) -> None:
        """TimeoutException is wrapped in ArcadiaError after all retries."""
        mock_client.request.side_effect = httpx.TimeoutException("timeout")
        service._client = mock_client

        with patch("services.arcadia_service.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ArcadiaError, match="timed out"):
                await service._request("GET", "/timeout")

        assert mock_client.request.await_count == MAX_RETRIES


# =============================================================================
# close
# =============================================================================


class TestClose:
    @pytest.mark.asyncio
    async def test_close_closes_client(
        self, service: ArcadiaService, mock_client: AsyncMock
    ) -> None:
        """close() calls aclose() on the underlying httpx client."""
        mock_client.is_closed = False
        service._client = mock_client

        await service.close()

        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_no_op_when_client_is_none(self, service: ArcadiaService) -> None:
        """close() is a no-op when no client has been initialised yet."""
        service._client = None

        # Should not raise.
        await service.close()

    @pytest.mark.asyncio
    async def test_close_no_op_when_already_closed(
        self, service: ArcadiaService, mock_client: AsyncMock
    ) -> None:
        """close() is a no-op when the client is already closed."""
        mock_client.is_closed = True
        service._client = mock_client

        await service.close()

        mock_client.aclose.assert_not_awaited()


# =============================================================================
# Client singleton / reuse
# =============================================================================


class TestClientSingleton:
    @pytest.mark.asyncio
    async def test_client_reused_across_calls(
        self, service: ArcadiaService, mock_client: AsyncMock
    ) -> None:
        """The same httpx client instance is reused for successive requests."""
        mock_client.request.return_value = _make_httpx_response(200, {"intervals": []})
        service._client = mock_client

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 2)

        await service.fetch_interval_data("acc_reuse", start, end)
        await service.fetch_interval_data("acc_reuse", start, end)

        # Both calls used the same client — request was called twice, not once
        # on a freshly-created client.
        assert mock_client.request.await_count == 2

    @pytest.mark.asyncio
    async def test_new_client_created_when_previous_is_closed(
        self, service: ArcadiaService
    ) -> None:
        """_get_client() creates a new instance if the existing one is closed."""
        closed_client = MagicMock(spec=httpx.AsyncClient)
        closed_client.is_closed = True
        service._client = closed_client

        new_client = await service._get_client()

        # A fresh AsyncClient should have been created.
        assert new_client is not closed_client
        assert isinstance(new_client, httpx.AsyncClient)
        # Properly close it to avoid ResourceWarning.
        await new_client.aclose()
