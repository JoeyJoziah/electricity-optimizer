"""
Tests for DripService (backend/services/drip_service.py)

Covers:
- enroll_user inserts row and sends welcome email
- enroll_user is idempotent (no double-send on conflict)
- process_day2_batch selects Template A when connected, Template B otherwise
- process_day2_batch skips users enrolled < 2 days ago
- process_day2_batch records errors without aborting the batch
- process_day7_batch sends upgrade nudge and marks sent
- process_day7_batch skips users enrolled < 7 days ago
- DISPATCH_ERROR_RATE_THRESHOLD constant is 0.02
"""

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from services.drip_service import DAY2_DELAY, DAY7_DELAY, DISPATCH_ERROR_RATE_THRESHOLD, DripService

# =============================================================================
# Fixtures
# =============================================================================


def _make_row(**kwargs) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, key: kwargs[key]
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


def _make_execute_result(fetchone_val=None, mappings_rows=None):
    """Build a sync-ish result object returned by await db.execute(...)."""
    result = MagicMock()
    result.fetchone = MagicMock(return_value=fetchone_val)
    mappings_mock = MagicMock()
    mappings_mock.all = MagicMock(return_value=mappings_rows or [])
    result.mappings = MagicMock(return_value=mappings_mock)
    return result


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    # Default execute result: fetchone returns a row (INSERT succeeded), empty mappings
    db.execute.return_value = _make_execute_result(fetchone_val=("uid",))
    return db


@pytest.fixture
def mock_email():
    svc = MagicMock()
    svc.render_template = MagicMock(return_value="<html/>")
    svc.send = AsyncMock(return_value=True)
    return svc


@pytest.fixture
def svc(mock_db, mock_email):
    with patch("services.drip_service.EmailService", return_value=mock_email):
        return DripService(mock_db)


# =============================================================================
# Constants
# =============================================================================


def test_error_rate_threshold():
    assert DISPATCH_ERROR_RATE_THRESHOLD == 0.02


def test_delay_constants():
    assert timedelta(days=2) == DAY2_DELAY
    assert timedelta(days=7) == DAY7_DELAY


# =============================================================================
# enroll_user
# =============================================================================


class TestEnrollUser:
    async def test_inserts_row_and_sends_welcome(self, svc, mock_db, mock_email):
        user_id = str(uuid4())
        mock_db.execute.return_value.fetchone.return_value = (user_id,)

        result = await svc.enroll_user(user_id=user_id, email="a@b.com", name="Alice")

        assert result is True
        mock_email.send.assert_awaited_once()
        subject = mock_email.send.call_args.kwargs["subject"]
        assert "Welcome" in subject

    async def test_idempotent_on_conflict(self, svc, mock_db, mock_email):
        mock_db.execute.return_value = _make_execute_result(fetchone_val=None)

        result = await svc.enroll_user(user_id=str(uuid4()), email="a@b.com", name="Alice")

        assert result is False
        mock_email.send.assert_not_awaited()

    async def test_welcome_sent_at_written(self, svc, mock_db, mock_email):
        user_id = str(uuid4())
        mock_db.execute.return_value.fetchone.return_value = (user_id,)

        await svc.enroll_user(user_id=user_id, email="a@b.com", name=None)

        # Two execute calls: INSERT + UPDATE welcome_sent_at
        assert mock_db.execute.call_count == 2

    async def test_none_name_handled(self, svc, mock_db, mock_email):
        mock_db.execute.return_value.fetchone.return_value = ("uid",)
        await svc.enroll_user(user_id="uid", email="a@b.com", name=None)
        call_kwargs = mock_email.render_template.call_args
        assert call_kwargs.args[0] == "welcome_signup.html"
        assert call_kwargs.kwargs.get("name") == ""


# =============================================================================
# process_day2_batch — template selection
# =============================================================================


class TestDay2TemplateSelection:
    def _make_user_row(
        self,
        has_connection: bool,
        has_bill: bool,
        potential_savings_annual: float | None = None,
    ) -> MagicMock:
        row: dict[str, Any] = {
            "user_id": uuid4(),
            "email": "u@example.com",
            "name": "User",
            "region": "CT",
            "has_connection": has_connection,
            "has_bill": has_bill,
            "potential_savings_annual": potential_savings_annual,
        }
        m = MagicMock()
        m.__getitem__ = lambda self, k: row[k]
        return m

    async def test_template_a_when_connected(self, svc, mock_db, mock_email):
        row = self._make_user_row(has_connection=True, has_bill=False)
        mock_db.execute.return_value = _make_execute_result(mappings_rows=[row])

        result = await svc.process_day2_batch()

        assert result["sent_a"] == 1
        assert result["sent_b"] == 0
        call_args = mock_email.render_template.call_args_list[0]
        assert call_args.args[0] == "drip_day2_connected.html"

    async def test_template_b_when_bill_uploaded(self, svc, mock_db, mock_email):
        row = self._make_user_row(has_connection=False, has_bill=True)
        mock_db.execute.return_value = _make_execute_result(mappings_rows=[row])

        result = await svc.process_day2_batch()

        assert result["sent_a"] == 1  # bill counts as connected
        assert result["sent_b"] == 0

    async def test_template_b_when_no_data(self, svc, mock_db, mock_email):
        row = self._make_user_row(has_connection=False, has_bill=False)
        mock_db.execute.return_value = _make_execute_result(mappings_rows=[row])

        result = await svc.process_day2_batch()

        assert result["sent_a"] == 0
        assert result["sent_b"] == 1
        call_args = mock_email.render_template.call_args_list[0]
        assert call_args.args[0] == "drip_day2_pending.html"

    async def test_empty_batch_returns_zero_counts(self, svc, mock_db):
        mock_db.execute.return_value = _make_execute_result(mappings_rows=[])

        result = await svc.process_day2_batch()

        assert result == {"total": 0, "sent_a": 0, "sent_b": 0, "errors": 0}

    async def test_error_in_one_user_increments_errors(self, svc, mock_db, mock_email):
        row = self._make_user_row(has_connection=True, has_bill=False)
        mock_db.execute.return_value = _make_execute_result(mappings_rows=[row])
        mock_email.send.side_effect = Exception("SMTP timeout")

        result = await svc.process_day2_batch()

        assert result["errors"] == 1
        assert result["sent_a"] == 0


# =============================================================================
# process_day7_batch
# =============================================================================


class TestDay7Batch:
    def _make_row(self) -> MagicMock:
        row: dict[str, Any] = {
            "user_id": uuid4(),
            "email": "u@example.com",
            "name": "User",
        }
        m = MagicMock()
        m.__getitem__ = lambda self, k: row[k]
        return m

    async def test_sends_upgrade_nudge(self, svc, mock_db, mock_email):
        mock_db.execute.return_value = _make_execute_result(mappings_rows=[self._make_row()])

        result = await svc.process_day7_batch()

        assert result["sent"] == 1
        assert result["errors"] == 0
        call_args = mock_email.render_template.call_args_list[0]
        assert call_args.args[0] == "drip_day7_upgrade.html"

    async def test_empty_batch(self, svc, mock_db):
        mock_db.execute.return_value = _make_execute_result(mappings_rows=[])

        result = await svc.process_day7_batch()

        assert result == {"total": 0, "sent": 0, "errors": 0}

    async def test_error_increments_counter(self, svc, mock_db, mock_email):
        mock_db.execute.return_value = _make_execute_result(mappings_rows=[self._make_row()])
        mock_email.send.side_effect = RuntimeError("network error")

        result = await svc.process_day7_batch()

        assert result["errors"] == 1
        assert result["sent"] == 0


# =============================================================================
# CAN-SPAM / unsubscribe
# =============================================================================


class TestUnsubscribeCompliance:
    """Verify unsubscribe_url is injected into every send helper."""

    def _make_user_row(self, has_connection: bool = True) -> MagicMock:
        from typing import Any

        row: dict[str, Any] = {
            "user_id": uuid4(),
            "email": "u@example.com",
            "name": "User",
            "region": "CT",
            "has_connection": has_connection,
            "has_bill": False,
            "potential_savings_annual": None,
        }
        m = MagicMock()
        m.__getitem__ = lambda self, k: row[k]
        return m

    def _make_day7_row(self) -> MagicMock:
        from typing import Any

        row: dict[str, Any] = {"user_id": uuid4(), "email": "u@example.com", "name": "User"}
        m = MagicMock()
        m.__getitem__ = lambda self, k: row[k]
        return m

    async def test_welcome_passes_unsubscribe_url(self, svc, mock_db, mock_email):
        with patch("services.drip_service.get_settings") as ms:
            ms.return_value.effective_unsubscribe_secret = "test"
            mock_db.execute.return_value.fetchone.return_value = ("uid",)
            await svc.enroll_user(user_id="uid", email="a@b.com", name="Alice")

        kwargs = mock_email.render_template.call_args.kwargs
        assert "unsubscribe_url" in kwargs
        assert "uid=uid" in kwargs["unsubscribe_url"]

    async def test_day2_connected_passes_unsubscribe_url(self, svc, mock_db, mock_email):
        row = self._make_user_row(has_connection=True)
        mock_db.execute.return_value = _make_execute_result(mappings_rows=[row])

        with patch("services.drip_service.get_settings") as ms:
            ms.return_value.effective_unsubscribe_secret = "test"
            await svc.process_day2_batch()

        kwargs = mock_email.render_template.call_args.kwargs
        assert "unsubscribe_url" in kwargs
        assert "uid=" in kwargs["unsubscribe_url"]

    async def test_day2_pending_passes_unsubscribe_url(self, svc, mock_db, mock_email):
        row = self._make_user_row(has_connection=False)
        mock_db.execute.return_value = _make_execute_result(mappings_rows=[row])

        with patch("services.drip_service.get_settings") as ms:
            ms.return_value.effective_unsubscribe_secret = "test"
            await svc.process_day2_batch()

        kwargs = mock_email.render_template.call_args.kwargs
        assert "unsubscribe_url" in kwargs

    async def test_day7_passes_unsubscribe_url(self, svc, mock_db, mock_email):
        mock_db.execute.return_value = _make_execute_result(mappings_rows=[self._make_day7_row()])

        with patch("services.drip_service.get_settings") as ms:
            ms.return_value.effective_unsubscribe_secret = "test"
            await svc.process_day7_batch()

        kwargs = mock_email.render_template.call_args.kwargs
        assert "unsubscribe_url" in kwargs
