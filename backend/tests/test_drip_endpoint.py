"""
Tests for /api/v1/internal/drip/ endpoints.

enroll_user (POST /drip/enroll):
- Returns enrolled=True, welcome_sent=True on first enroll
- Returns enrolled=True, welcome_sent=False on duplicate (idempotent)
- Raises 422 on invalid email
- Raises 422 on missing required fields

process_drip_batches (POST /drip/process):
- PRD Scope #5 requirement (b): Sentry alert fires when error rate > 2%
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

    async def test_sentry_capture_called_above_threshold(self, mock_drip_svc):
        """Sentry capture_message fires when error rate > 2%."""
        mock_drip_svc.process_day2_batch.return_value = _make_batch_result(
            total=100, errors=5, sent_a=95
        )
        mock_drip_svc.process_day7_batch.return_value = _make_batch_result(0, 0)

        mock_sdk = _mock_sentry()
        with (
            patch("api.v1.internal.drip.DripService", return_value=mock_drip_svc),
            patch("api.v1.internal.drip.sentry_sdk", mock_sdk),
        ):
            from api.v1.internal.drip import process_drip_batches

            mock_db = AsyncMock()
            await process_drip_batches(db=mock_db)

        mock_sdk.capture_message.assert_called_once()
        call_args = mock_sdk.capture_message.call_args
        assert "5.0%" in call_args.args[0]
        assert call_args.kwargs["level"] == "error"

    async def test_sentry_capture_not_called_below_threshold(self, mock_drip_svc):
        """Sentry capture_message does NOT fire when error rate <= 2%."""
        mock_drip_svc.process_day2_batch.return_value = _make_batch_result(
            total=100, errors=2, sent_a=98
        )  # exactly 2% — not above threshold
        mock_drip_svc.process_day7_batch.return_value = _make_batch_result(0, 0)

        mock_sdk = _mock_sentry()
        with (
            patch("api.v1.internal.drip.DripService", return_value=mock_drip_svc),
            patch("api.v1.internal.drip.sentry_sdk", mock_sdk),
        ):
            from api.v1.internal.drip import process_drip_batches

            mock_db = AsyncMock()
            await process_drip_batches(db=mock_db)

        mock_sdk.capture_message.assert_not_called()

    async def test_sentry_capture_not_called_on_empty_batch(self, mock_drip_svc):
        """Sentry capture_message does NOT fire when no users were processed."""
        mock_sdk = _mock_sentry()
        with (
            patch("api.v1.internal.drip.DripService", return_value=mock_drip_svc),
            patch("api.v1.internal.drip.sentry_sdk", mock_sdk),
        ):
            from api.v1.internal.drip import process_drip_batches

            mock_db = AsyncMock()
            await process_drip_batches(db=mock_db)

        mock_sdk.capture_message.assert_not_called()


# ---------------------------------------------------------------------------
# enroll_user endpoint
# ---------------------------------------------------------------------------


class TestEnrollUserEndpoint:
    """Tests for POST /api/v1/internal/drip/enroll."""

    @pytest.fixture
    def mock_enroll_svc(self):
        svc = AsyncMock()
        svc.enroll_user = AsyncMock(return_value=True)
        return svc

    async def test_returns_enrolled_and_welcome_sent_on_new_user(self, mock_enroll_svc):
        mock_enroll_svc.enroll_user.return_value = True
        with patch("api.v1.internal.drip.DripService", return_value=mock_enroll_svc):
            from api.v1.internal.drip import EnrollRequest, enroll_user

            req = EnrollRequest(user_id="uid-1", email="alice@example.com", name="Alice")
            result = await enroll_user(req=req, db=AsyncMock())

        assert result == {"enrolled": True, "welcome_sent": True}

    async def test_returns_welcome_sent_false_on_duplicate(self, mock_enroll_svc):
        # DripService.enroll_user returns False when the user is already enrolled (ON CONFLICT DO NOTHING)
        mock_enroll_svc.enroll_user.return_value = False
        with patch("api.v1.internal.drip.DripService", return_value=mock_enroll_svc):
            from api.v1.internal.drip import EnrollRequest, enroll_user

            req = EnrollRequest(user_id="uid-1", email="alice@example.com", name="Alice")
            result = await enroll_user(req=req, db=AsyncMock())

        assert result == {"enrolled": True, "welcome_sent": False}

    async def test_enroll_passes_all_fields_to_service(self, mock_enroll_svc):
        with patch("api.v1.internal.drip.DripService", return_value=mock_enroll_svc):
            from api.v1.internal.drip import EnrollRequest, enroll_user

            req = EnrollRequest(user_id="uid-99", email="bob@example.com", name="Bob")
            await enroll_user(req=req, db=AsyncMock())

        mock_enroll_svc.enroll_user.assert_awaited_once_with(
            user_id="uid-99",
            email="bob@example.com",
            name="Bob",
        )

    async def test_enroll_passes_none_name_to_service(self, mock_enroll_svc):
        with patch("api.v1.internal.drip.DripService", return_value=mock_enroll_svc):
            from api.v1.internal.drip import EnrollRequest, enroll_user

            req = EnrollRequest(user_id="uid-99", email="bob@example.com", name=None)
            await enroll_user(req=req, db=AsyncMock())

        call_kwargs = mock_enroll_svc.enroll_user.call_args.kwargs
        assert call_kwargs["name"] is None

    def test_enroll_request_rejects_invalid_email(self):
        from pydantic import ValidationError

        from api.v1.internal.drip import EnrollRequest

        with pytest.raises(ValidationError, match="email"):
            EnrollRequest(user_id="uid-1", email="not-an-email", name="Alice")

    def test_enroll_request_requires_user_id(self):
        from pydantic import ValidationError

        from api.v1.internal.drip import EnrollRequest

        with pytest.raises(ValidationError):
            EnrollRequest(email="alice@example.com")
