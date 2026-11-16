"""
Tests for DripService (backend/services/drip_service.py)

Covers:
- enroll_user inserts row and sends welcome email
- enroll_user is idempotent (no double-send on conflict)
- process_day2_batch selects Template A when connected, Template B otherwise
- process_day2_batch forwards potential_savings_annual to Template A context (None when no data)
- process_day2_batch skips users enrolled < 2 days ago
- process_day2_batch records errors without aborting the batch
- process_day7_batch sends upgrade nudge and marks sent
- process_day7_batch skips users enrolled < 7 days ago
- DISPATCH_ERROR_RATE_THRESHOLD constant is 0.02
- claim-first sends: an overlapping run sends nothing; a failed send releases the claim
- process_welcome_retry_batch re-sends failed welcomes inside a bounded window
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from services.drip_service import (
    DAY2_DELAY,
    DAY7_DELAY,
    DISPATCH_ERROR_RATE_THRESHOLD,
    WELCOME_RETRY_GRACE,
    WELCOME_RETRY_WINDOW,
    DripService,
)

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


def _batch_result(rows):
    """Batch SELECT rows; fetchone is truthy so the follow-up claim UPDATE succeeds."""
    return _make_execute_result(fetchone_val=("uid",), mappings_rows=rows)


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
        mock_db.execute.return_value = _batch_result([row])

        result = await svc.process_day2_batch()

        assert result["sent_a"] == 1
        assert result["sent_b"] == 0
        call_args = mock_email.render_template.call_args_list[0]
        assert call_args.args[0] == "drip_day2_connected.html"

    async def test_template_b_when_bill_uploaded(self, svc, mock_db, mock_email):
        row = self._make_user_row(has_connection=False, has_bill=True)
        mock_db.execute.return_value = _batch_result([row])

        result = await svc.process_day2_batch()

        assert result["sent_a"] == 1  # bill counts as connected
        assert result["sent_b"] == 0

    async def test_template_b_when_no_data(self, svc, mock_db, mock_email):
        row = self._make_user_row(has_connection=False, has_bill=False)
        mock_db.execute.return_value = _batch_result([row])

        result = await svc.process_day2_batch()

        assert result["sent_a"] == 0
        assert result["sent_b"] == 1
        call_args = mock_email.render_template.call_args_list[0]
        assert call_args.args[0] == "drip_day2_pending.html"

    async def test_empty_batch_returns_zero_counts(self, svc, mock_db):
        mock_db.execute.return_value = _batch_result([])

        result = await svc.process_day2_batch()

        assert result == {"total": 0, "sent_a": 0, "sent_b": 0, "errors": 0}

    async def test_error_in_one_user_increments_errors(self, svc, mock_db, mock_email):
        row = self._make_user_row(has_connection=True, has_bill=False)
        mock_db.execute.return_value = _batch_result([row])
        mock_email.send.side_effect = Exception("SMTP timeout")

        result = await svc.process_day2_batch()

        assert result["errors"] == 1
        assert result["sent_a"] == 0

    async def test_template_a_forwards_potential_savings_annual(self, svc, mock_db, mock_email):
        # Verifies that potential_savings_annual from the SQL row reaches the
        # render_template call — this value drives the savings headline in Template A.
        row = self._make_user_row(
            has_connection=True, has_bill=False, potential_savings_annual=120.0
        )
        mock_db.execute.return_value = _batch_result([row])

        await svc.process_day2_batch()

        call_kwargs = mock_email.render_template.call_args.kwargs
        assert call_kwargs.get("potential_savings_annual") == 120.0

    async def test_template_a_forwards_none_when_no_savings_data(self, svc, mock_db, mock_email):
        # No bill_estimate rows in user_savings → SQL returns NULL → passed as None.
        # Template A must handle None gracefully (show generic copy, not "None savings").
        row = self._make_user_row(
            has_connection=True, has_bill=False, potential_savings_annual=None
        )
        mock_db.execute.return_value = _batch_result([row])

        await svc.process_day2_batch()

        call_kwargs = mock_email.render_template.call_args.kwargs
        assert call_kwargs.get("potential_savings_annual") is None

    async def test_template_a_forwards_region(self, svc, mock_db, mock_email):
        # region drives rate-zone copy in Template A — must reach the template context.
        row = self._make_user_row(has_connection=True, has_bill=False)
        mock_db.execute.return_value = _batch_result([row])

        await svc.process_day2_batch()

        call_kwargs = mock_email.render_template.call_args.kwargs
        assert call_kwargs.get("region") == "CT"


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
        mock_db.execute.return_value = _batch_result([self._make_row()])

        result = await svc.process_day7_batch()

        assert result["sent"] == 1
        assert result["errors"] == 0
        call_args = mock_email.render_template.call_args_list[0]
        assert call_args.args[0] == "drip_day7_upgrade.html"

    async def test_empty_batch(self, svc, mock_db):
        mock_db.execute.return_value = _batch_result([])

        result = await svc.process_day7_batch()

        assert result == {"total": 0, "sent": 0, "errors": 0}

    async def test_error_increments_counter(self, svc, mock_db, mock_email):
        mock_db.execute.return_value = _batch_result([self._make_row()])
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
        mock_db.execute.return_value = _batch_result([row])

        with patch("services.drip_service.get_settings") as ms:
            ms.return_value.effective_unsubscribe_secret = "test"
            await svc.process_day2_batch()

        kwargs = mock_email.render_template.call_args.kwargs
        assert "unsubscribe_url" in kwargs
        assert "uid=" in kwargs["unsubscribe_url"]

    async def test_day2_pending_passes_unsubscribe_url(self, svc, mock_db, mock_email):
        row = self._make_user_row(has_connection=False)
        mock_db.execute.return_value = _batch_result([row])

        with patch("services.drip_service.get_settings") as ms:
            ms.return_value.effective_unsubscribe_secret = "test"
            await svc.process_day2_batch()

        kwargs = mock_email.render_template.call_args.kwargs
        assert "unsubscribe_url" in kwargs

    async def test_day7_passes_unsubscribe_url(self, svc, mock_db, mock_email):
        mock_db.execute.return_value = _batch_result([self._make_day7_row()])

        with patch("services.drip_service.get_settings") as ms:
            ms.return_value.effective_unsubscribe_secret = "test"
            await svc.process_day7_batch()

        kwargs = mock_email.render_template.call_args.kwargs
        assert "unsubscribe_url" in kwargs


# =============================================================================
# Claim-first sends (D6) and welcome retry (D10)
# =============================================================================


class _FakeDripDb:
    """
    Minimal stateful stand-in for the user_drip_state table.

    SELECTs always return every user, which models the worst case of two
    overlapping runs that both read the batch before either one wrote. Claim
    and release UPDATEs behave like Postgres: a claim only matches while the
    column is NULL. ``events`` records the order of DB writes and sends.
    """

    def __init__(self, user_ids: list[str], events: list[str] | None = None) -> None:
        self.state: dict[str, dict[str, Any]] = {
            uid: {"welcome_sent_at": None, "day2_sent_at": None, "day7_sent_at": None}
            for uid in user_ids
        }
        self.events = events if events is not None else []
        self.selects: list[tuple[str, dict]] = []
        self.rollback = AsyncMock()

    @staticmethod
    def _column(sql: str) -> str:
        for col in ("welcome_sent_at", "day2_sent_at", "day7_sent_at"):
            if f"SET {col} =" in sql:
                return col
        raise AssertionError(f"unexpected UPDATE: {sql}")

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        if sql.startswith("SELECT"):
            self.selects.append((sql, params))
            rows = [
                {
                    "user_id": uid,
                    "email": f"{uid}@example.com",
                    "name": "User",
                    "region": "CT",
                    "has_connection": True,
                    "has_bill": False,
                    "potential_savings_annual": None,
                }
                for uid in self.state
            ]
            return _make_execute_result(mappings_rows=rows)

        assert sql.startswith("UPDATE user_drip_state"), sql
        col = self._column(sql)
        uid = params["user_id"]
        if f"SET {col} = NULL" in sql:
            self.state[uid][col] = None
            self.events.append(f"release:{col}:{uid}")
            return _make_execute_result(fetchone_val=None)

        assert f"{col} IS NULL" in sql, "claim must be conditional on the column being NULL"
        assert "RETURNING user_id" in sql
        if self.state[uid][col] is None:
            self.state[uid][col] = "claimed"
            self.events.append(f"claim:{col}:{uid}")
            return _make_execute_result(fetchone_val=(uid,))
        return _make_execute_result(fetchone_val=None)

    async def commit(self):
        self.events.append("commit")


def _email_mock(events: list[str] | None = None, *, send_result: Any = True) -> MagicMock:
    email = MagicMock()
    email.render_template = MagicMock(return_value="<html/>")

    async def _send(**kwargs):
        if events is not None:
            events.append(f"send:{kwargs['to']}")
        if isinstance(send_result, Exception):
            raise send_result
        return send_result

    email.send = AsyncMock(side_effect=_send)
    return email


def _service(db, email) -> DripService:
    with patch("services.drip_service.EmailService", return_value=email):
        return DripService(db)


_BATCHES = [
    ("process_day2_batch", "day2_sent_at"),
    ("process_day7_batch", "day7_sent_at"),
    ("process_welcome_retry_batch", "welcome_sent_at"),
]


class TestClaimFirstSends:
    @pytest.mark.parametrize("method,column", _BATCHES)
    async def test_overlapping_run_sends_nothing(self, method, column):
        """Two runs that both selected the same user send exactly one email."""
        db = _FakeDripDb(["u1"])
        email = _email_mock()
        first = _service(db, email)
        second = _service(db, email)

        await getattr(first, method)()
        result = await getattr(second, method)()

        assert email.send.await_count == 1
        assert result["errors"] == 0
        assert result.get("sent", 0) == 0
        assert result.get("sent_a", 0) == 0
        assert db.state["u1"][column] == "claimed"

    @pytest.mark.parametrize("method,column", _BATCHES)
    async def test_claim_is_committed_before_send(self, method, column):
        """The claim must be visible to a concurrent run before the email leaves."""
        events: list[str] = []
        db = _FakeDripDb(["u1"], events)
        svc = _service(db, _email_mock(events))

        await getattr(svc, method)()

        assert events[:3] == [f"claim:{column}:u1", "commit", "send:u1@example.com"]

    @pytest.mark.parametrize("method,column", _BATCHES)
    async def test_failed_send_releases_claim_for_next_run(self, method, column):
        """send() returning False resets the column so the next run retries."""
        db = _FakeDripDb(["u1"])
        failing = _email_mock(send_result=False)
        await getattr(_service(db, failing), method)()

        assert db.state["u1"][column] is None

        working = _email_mock()
        await getattr(_service(db, working), method)()

        assert working.send.await_count == 1
        assert db.state["u1"][column] == "claimed"

    @pytest.mark.parametrize("method,column", _BATCHES)
    async def test_send_exception_releases_claim_and_batch_continues(self, method, column):
        """One user's send raising must not strand their claim or stop the batch."""
        db = _FakeDripDb(["u1", "u2"])
        email = _email_mock()
        calls = {"n": 0}

        async def _send(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("SMTP timeout")
            return True

        email.send = AsyncMock(side_effect=_send)

        result = await getattr(_service(db, email), method)()

        assert result["errors"] == 1
        assert result["total"] == 2
        assert email.send.await_count == 2
        assert db.state["u1"][column] is None
        assert db.state["u2"][column] == "claimed"


class TestWelcomeRetryBatch:
    async def test_sends_welcome_template(self):
        db = _FakeDripDb(["u1"])
        email = _email_mock()

        result = await _service(db, email).process_welcome_retry_batch()

        assert result == {"total": 1, "sent": 1, "errors": 0}
        assert email.render_template.call_args.args[0] == "welcome_signup.html"
        assert "Welcome" in email.send.call_args.kwargs["subject"]

    async def test_query_is_bounded_to_recent_unsent_enrollments(self):
        db = _FakeDripDb([])
        before = datetime.now(UTC)

        result = await _service(db, _email_mock()).process_welcome_retry_batch()

        after = datetime.now(UTC)
        assert result == {"total": 0, "sent": 0, "errors": 0}
        sql, params = db.selects[0]
        assert "ds.welcome_sent_at IS NULL" in sql
        assert "ds.unsubscribed_at IS NULL" in sql
        assert "ds.enrolled_at >= :oldest" in sql
        assert "ds.enrolled_at <= :newest" in sql
        # Old rows (enrolled more than 7 days ago) never get a surprise welcome.
        assert before - WELCOME_RETRY_WINDOW <= params["oldest"] <= after - WELCOME_RETRY_WINDOW
        # Fresh rows are left to enroll_user()'s inline send.
        assert before - WELCOME_RETRY_GRACE <= params["newest"] <= after - WELCOME_RETRY_GRACE

    def test_window_constants(self):
        assert timedelta(days=7) == WELCOME_RETRY_WINDOW
        assert timedelta(0) < WELCOME_RETRY_GRACE < timedelta(hours=1)
