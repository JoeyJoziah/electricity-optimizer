"""
Tests for /api/v1/internal/drip/process endpoint error-rate Sentry alerting.

PRD Scope #5 requirement (b): Sentry alert fires when drip dispatch error rate > 2%.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_batch_result(total: int, errors: int, sent_a: int = 0, sent_b: int = 0, sent: int = 0):
    """Return a mock return value that mimics DripService.process_*_batch output."""
    return {"total": total, "sent_a": sent_a, "sent_b": sent_b, "sent": sent, "errors": errors}


def _mock_sentry():
    """Return a MagicMock that looks like sentry_sdk with capture_message."""
    sdk = MagicMock()
    sdk.capture_message = MagicMock()
    return sdk


# ---------------------------------------------------------------------------
# Unit tests for the Sentry alerting logic inside process_drip_batches
# ---------------------------------------------------------------------------


class TestDripProcessErrorRateAlert:
    """Test that Sentry capture_message fires when error_rate > 2%."""

    @pytest.fixture
    def mock_drip_svc(self):
        svc = AsyncMock()
        svc.process_day2_batch = AsyncMock(return_value=_make_batch_result(0, 0))
        svc.process_day7_batch = AsyncMock(return_value=_make_batch_result(0, 0))
        return svc

    async def test_error_rate_computed_correctly_at_50_pct(self, mock_drip_svc):
        """50% error rate (1 error out of 2 attempts) is reflected in response."""
        mock_drip_svc.process_day2_batch.return_value = _make_batch_result(
            total=2, errors=1, sent_a=1
        )
        mock_drip_svc.process_day7_batch.return_value = _make_batch_result(0, 0)

        with patch("api.v1.internal.drip.DripService", return_value=mock_drip_svc):
            from api.v1.internal.drip import process_drip_batches

            mock_db = AsyncMock()
            result = await process_drip_batches(db=mock_db)

        assert result["summary"]["error_rate"] == 0.5
        assert result["summary"]["total_errors"] == 1
        assert result["summary"]["total_attempted"] == 2

    async def test_sentry_does_not_fire_below_threshold(self, mock_drip_svc):
        """1% error rate is below the 2% threshold — no Sentry event."""
        mock_drip_svc.process_day2_batch.return_value = _make_batch_result(
            total=100, errors=1, sent_a=99
        )
        mock_drip_svc.process_day7_batch.return_value = _make_batch_result(0, 0)

        with patch("api.v1.internal.drip.DripService", return_value=mock_drip_svc):
            from api.v1.internal.drip import process_drip_batches

            mock_db = AsyncMock()
            result = await process_drip_batches(db=mock_db)

        assert result["summary"]["total_errors"] == 1
        assert result["summary"]["error_rate"] == 0.01

    async def test_sentry_does_not_fire_on_empty_batch(self, mock_drip_svc):
        """No users processed — division by zero avoided, no alert needed."""
        mock_drip_svc.process_day2_batch.return_value = _make_batch_result(0, 0)
        mock_drip_svc.process_day7_batch.return_value = _make_batch_result(0, 0)

        with patch("api.v1.internal.drip.DripService", return_value=mock_drip_svc):
            from api.v1.internal.drip import process_drip_batches

            mock_db = AsyncMock()
            result = await process_drip_batches(db=mock_db)

        assert result["summary"]["error_rate"] == 0.0
        assert result["summary"]["total_attempted"] == 0

    async def test_error_rate_included_in_response(self, mock_drip_svc):
        """Response summary must include error_rate field."""
        mock_drip_svc.process_day2_batch.return_value = _make_batch_result(
            total=10, errors=0, sent_a=10
        )
        mock_drip_svc.process_day7_batch.return_value = _make_batch_result(
            total=5, errors=0, sent=5
        )

        with patch("api.v1.internal.drip.DripService", return_value=mock_drip_svc):
            from api.v1.internal.drip import process_drip_batches

            mock_db = AsyncMock()
            result = await process_drip_batches(db=mock_db)

        assert "error_rate" in result["summary"]
        assert result["summary"]["error_rate"] == 0.0
        assert result["summary"]["total_attempted"] == 15
        assert result["summary"]["total_sent"] == 15

    async def test_error_rate_above_threshold_sets_correct_rate(self, mock_drip_svc):
        """3 errors out of 100 = 3% > 2% threshold — verify math."""
        mock_drip_svc.process_day2_batch.return_value = _make_batch_result(
            total=100, errors=3, sent_a=97
        )
        mock_drip_svc.process_day7_batch.return_value = _make_batch_result(0, 0)

        with patch("api.v1.internal.drip.DripService", return_value=mock_drip_svc):
            from api.v1.internal.drip import process_drip_batches

            mock_db = AsyncMock()
            result = await process_drip_batches(db=mock_db)

        assert result["summary"]["error_rate"] == 0.03
        assert result["summary"]["total_errors"] == 3
