"""
Tests for NotificationDispatcher (backend/services/notification_dispatcher.py)

Coverage:
- send() dispatches to all channels by default
- send() respects explicit channel list
- dedup check blocks send within cooldown window
- dedup check allows send after cooldown expires (or when no prior record)
- push channel is skipped gracefully when OneSignal is not configured
- email channel is skipped when email_to is not provided
- email channel uses email_subject when provided; falls back to title
- in-app channel failure is isolated (does not abort other channels)
- push channel failure is isolated (does not abort other channels)
- email channel failure is isolated (does not abort other channels)
- dedup query failure defaults to allow delivery (fail-open)
- dedup_key stored in metadata on in-app notifications
- channel routing with user preferences (explicit channel subset)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from services.notification_dispatcher import (_DEFAULT_COOLDOWN_SECONDS,
                                              ALL_CHANNELS,
                                              NotificationChannel,
                                              NotificationDispatcher)

# =============================================================================
# Fixtures
# =============================================================================


TEST_USER_ID = str(uuid4())


@pytest.fixture
def mock_db():
    """Mock AsyncSession with execute/commit as AsyncMock."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_notification_service():
    """Mock NotificationService."""
    svc = AsyncMock()
    svc.create = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def mock_push_service():
    """Mock PushNotificationService — configured by default."""
    svc = AsyncMock()
    svc.is_configured = True
    svc.send_push = AsyncMock(return_value=True)
    return svc


@pytest.fixture
def mock_email_service():
    """Mock EmailService."""
    svc = AsyncMock()
    svc.send = AsyncMock(return_value=True)
    return svc


@pytest.fixture
def dispatcher(mock_db, mock_notification_service, mock_push_service, mock_email_service):
    """NotificationDispatcher with all mocked dependencies."""
    return NotificationDispatcher(
        db=mock_db,
        notification_service=mock_notification_service,
        push_service=mock_push_service,
        email_service=mock_email_service,
    )


def _dedup_result(found: bool) -> MagicMock:
    """Return a mock execute() result for the dedup query."""
    result = MagicMock()
    result.first.return_value = MagicMock() if found else None
    return result


def _no_dedup_result() -> MagicMock:
    """Mock for dedup query returning no match (allow send)."""
    return _dedup_result(found=False)


def _dup_found_result() -> MagicMock:
    """Mock for dedup query returning a match (suppress send)."""
    return _dedup_result(found=True)


def _insert_result() -> MagicMock:
    """Mock for a successful INSERT execute."""
    result = MagicMock()
    result.rowcount = 1
    return result


# =============================================================================
# TestSendAllChannels — all-channel default routing
# =============================================================================


class TestSendAllChannels:

    @pytest.mark.asyncio
    async def test_sends_to_all_three_channels_by_default(
        self, dispatcher, mock_notification_service, mock_push_service, mock_email_service
    ):
        """When channels is None, all three channels should be attempted."""
        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="Test notification",
            body="Body text",
            email_to="user@example.com",
        )

        assert result["skipped_dedup"] is False
        channels = result["channels"]
        assert NotificationChannel.IN_APP.value in channels
        assert NotificationChannel.PUSH.value in channels
        assert NotificationChannel.EMAIL.value in channels

    @pytest.mark.asyncio
    async def test_all_channels_succeed(self, dispatcher, mock_push_service, mock_email_service):
        """All three channels should report True on success."""
        mock_push_service.send_push.return_value = True
        mock_email_service.send.return_value = True

        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="price_alert",
            title="Low price!",
            body="Price dropped to $0.08/kWh",
            email_to="user@example.com",
        )

        assert result["channels"][NotificationChannel.IN_APP.value] is True
        assert result["channels"][NotificationChannel.PUSH.value] is True
        assert result["channels"][NotificationChannel.EMAIL.value] is True

    @pytest.mark.asyncio
    async def test_all_channels_constant_is_correct(self):
        """ALL_CHANNELS should contain all three enum values."""
        assert NotificationChannel.IN_APP in ALL_CHANNELS
        assert NotificationChannel.PUSH in ALL_CHANNELS
        assert NotificationChannel.EMAIL in ALL_CHANNELS
        assert len(ALL_CHANNELS) == 3


# =============================================================================
# TestChannelRouting — explicit channel selection
# =============================================================================


class TestChannelRouting:

    @pytest.mark.asyncio
    async def test_only_in_app_when_specified(
        self, dispatcher, mock_notification_service, mock_push_service, mock_email_service
    ):
        """Only in_app channel should fire when [IN_APP] is passed."""
        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="In-app only",
            channels=[NotificationChannel.IN_APP],
        )

        assert result["channels"].get(NotificationChannel.IN_APP.value) is True
        assert NotificationChannel.PUSH.value not in result["channels"]
        assert NotificationChannel.EMAIL.value not in result["channels"]
        mock_push_service.send_push.assert_not_awaited()
        mock_email_service.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_only_push_when_specified(self, dispatcher, mock_db, mock_push_service):
        """Only push channel should fire when [PUSH] is passed."""
        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="alert",
            title="Push only",
            channels=[NotificationChannel.PUSH],
        )

        assert result["channels"].get(NotificationChannel.PUSH.value) is True
        assert NotificationChannel.IN_APP.value not in result["channels"]
        mock_push_service.send_push.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_only_email_when_specified(self, dispatcher, mock_email_service):
        """Only email channel should fire when [EMAIL] is passed."""
        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="Email only",
            channels=[NotificationChannel.EMAIL],
            email_to="user@example.com",
        )

        assert result["channels"].get(NotificationChannel.EMAIL.value) is True
        mock_email_service.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_in_app_and_push_without_email(
        self, dispatcher, mock_db, mock_push_service, mock_email_service
    ):
        """Routing to [IN_APP, PUSH] should not call email service."""
        mock_db.execute.return_value = _insert_result()

        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="No email",
            channels=[NotificationChannel.IN_APP, NotificationChannel.PUSH],
        )

        assert NotificationChannel.EMAIL.value not in result["channels"]
        mock_email_service.send.assert_not_awaited()


# =============================================================================
# TestDeduplication — cooldown-based send suppression
# =============================================================================


class TestDeduplication:

    @pytest.mark.asyncio
    async def test_dedup_blocks_send_within_cooldown(
        self, dispatcher, mock_db, mock_push_service, mock_email_service
    ):
        """When a matching dedup_key exists within cooldown, send is skipped."""
        mock_db.execute.return_value = _dup_found_result()

        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="price_alert",
            title="Duplicate",
            dedup_key="price_alert:us_ct",
            cooldown_seconds=3600,
            email_to="user@example.com",
        )

        assert result["skipped_dedup"] is True
        assert result["channels"] == {}
        mock_push_service.send_push.assert_not_awaited()
        mock_email_service.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dedup_allows_send_when_no_prior_record(self, dispatcher, mock_db):
        """When no prior notification exists, send should proceed."""
        # First call: dedup SELECT returns no row; second call: INSERT succeeds.
        mock_db.execute.side_effect = [_no_dedup_result(), _insert_result()]

        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="price_alert",
            title="First alert",
            channels=[NotificationChannel.IN_APP],
            dedup_key="price_alert:us_ct",
            cooldown_seconds=3600,
        )

        assert result["skipped_dedup"] is False
        assert result["channels"][NotificationChannel.IN_APP.value] is True

    @pytest.mark.asyncio
    async def test_dedup_uses_default_cooldown_when_not_specified(self, dispatcher, mock_db):
        """When cooldown_seconds is omitted, _DEFAULT_COOLDOWN_SECONDS is used."""
        mock_db.execute.return_value = _dup_found_result()

        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="Dup with default cooldown",
            channels=[NotificationChannel.IN_APP],
            dedup_key="some_key",
            # cooldown_seconds intentionally omitted
        )

        assert result["skipped_dedup"] is True
        # Verify the dedup query was made (execute called once for the SELECT)
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_dedup_check_when_key_not_provided(
        self, dispatcher, mock_db, mock_notification_service
    ):
        """When dedup_key is None, the dedup SELECT should never be issued.

        The dispatcher now always uses a direct INSERT with delivery tracking
        columns rather than delegating to NotificationService.create().
        We verify: skipped_dedup is False, the in-app channel succeeds, and
        the INSERT (db.execute) was called exactly once with no dedup SELECT.
        """
        mock_db.execute.return_value = _insert_result()

        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="No dedup",
            channels=[NotificationChannel.IN_APP],
            # dedup_key intentionally omitted
        )

        assert result["skipped_dedup"] is False
        assert result["channels"][NotificationChannel.IN_APP.value] is True
        # db.execute was called (for the INSERT), but never for a dedup SELECT
        mock_db.execute.assert_awaited_once()
        # The single execute call should be an INSERT, not a dedup SELECT
        call_sql = str(mock_db.execute.call_args.args[0])
        assert (
            "INSERT" in call_sql.upper()
        ), "Expected the sole db.execute call to be an INSERT, not a dedup SELECT"

    @pytest.mark.asyncio
    async def test_dedup_key_stored_in_metadata(self, dispatcher, mock_db):
        """The dedup_key should be written into the notification metadata column."""
        mock_db.execute.side_effect = [_no_dedup_result(), _insert_result()]

        await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="Stored dedup key",
            channels=[NotificationChannel.IN_APP],
            dedup_key="my_unique_key",
            cooldown_seconds=600,
        )

        # The second execute call should be the INSERT with metadata
        insert_call = mock_db.execute.call_args_list[1]
        # params dict is positional arg index 1
        params = insert_call.args[1] if insert_call.args else insert_call.kwargs.get("params", {})
        import json

        meta = json.loads(params["meta"])
        assert meta["dedup_key"] == "my_unique_key"


# =============================================================================
# TestFallbackChain — channel-level failure isolation
# =============================================================================


class TestFallbackChain:

    @pytest.mark.asyncio
    async def test_push_failure_does_not_abort_email(
        self, dispatcher, mock_push_service, mock_email_service
    ):
        """A push failure should not prevent email delivery."""
        mock_push_service.send_push.return_value = False

        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="alert",
            title="Partial delivery",
            email_to="user@example.com",
        )

        assert result["channels"][NotificationChannel.PUSH.value] is False
        assert result["channels"][NotificationChannel.EMAIL.value] is True

    @pytest.mark.asyncio
    async def test_in_app_exception_does_not_abort_push_or_email(
        self, dispatcher, mock_db, mock_push_service, mock_email_service
    ):
        """An exception in the in-app channel should be caught; push and email proceed.

        The dispatcher now always writes the in-app row via db.execute directly
        (not via notification_service.create).  We trigger the failure by making
        db.execute raise on the INSERT call.
        """
        mock_db.execute.side_effect = Exception("DB connection lost")
        mock_push_service.send_push.return_value = True
        mock_email_service.send.return_value = True

        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="alert",
            title="DB error but others succeed",
            email_to="user@example.com",
        )

        assert result["channels"][NotificationChannel.IN_APP.value] is False
        assert result["channels"][NotificationChannel.PUSH.value] is True
        assert result["channels"][NotificationChannel.EMAIL.value] is True

    @pytest.mark.asyncio
    async def test_email_exception_does_not_abort_in_app_or_push(
        self, dispatcher, mock_push_service, mock_email_service
    ):
        """An exception in the email channel should be caught; in-app and push succeed."""
        mock_push_service.send_push.return_value = True
        mock_email_service.send.side_effect = Exception("SMTP timeout")

        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="alert",
            title="Email fails but others succeed",
            email_to="user@example.com",
        )

        assert result["channels"][NotificationChannel.IN_APP.value] is True
        assert result["channels"][NotificationChannel.PUSH.value] is True
        assert result["channels"][NotificationChannel.EMAIL.value] is False

    @pytest.mark.asyncio
    async def test_push_exception_is_caught_and_returns_false(self, dispatcher, mock_push_service):
        """An exception raised by push_service.send_push is caught and returns False."""
        mock_push_service.send_push.side_effect = Exception("OneSignal unreachable")

        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="Push crash test",
            channels=[NotificationChannel.PUSH],
        )

        assert result["channels"][NotificationChannel.PUSH.value] is False


# =============================================================================
# TestPushNotConfigured — graceful degradation
# =============================================================================


class TestPushNotConfigured:

    @pytest.mark.asyncio
    async def test_push_skipped_when_not_configured(self, dispatcher, mock_push_service):
        """Push channel should return False without calling send_push when not configured."""
        mock_push_service.is_configured = False

        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="No OneSignal",
            channels=[NotificationChannel.PUSH],
        )

        assert result["channels"][NotificationChannel.PUSH.value] is False
        mock_push_service.send_push.assert_not_awaited()


# =============================================================================
# TestEmailChannel — email-specific behaviour
# =============================================================================


class TestEmailChannel:

    @pytest.mark.asyncio
    async def test_email_skipped_when_no_address_provided(self, dispatcher, mock_email_service):
        """EMAIL channel should report False and not call send() when email_to is missing."""
        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="No email address",
            channels=[NotificationChannel.EMAIL],
            # email_to intentionally omitted
        )

        assert result["channels"][NotificationChannel.EMAIL.value] is False
        mock_email_service.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_email_uses_custom_subject(self, dispatcher, mock_email_service):
        """email_subject should override the title as the email subject."""
        await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="Default Title",
            channels=[NotificationChannel.EMAIL],
            email_to="user@example.com",
            email_subject="Custom Subject Line",
        )

        call_kwargs = mock_email_service.send.call_args.kwargs
        assert call_kwargs.get("subject") == "Custom Subject Line"

    @pytest.mark.asyncio
    async def test_email_falls_back_to_title_as_subject(self, dispatcher, mock_email_service):
        """When email_subject is not provided, title should be used as subject."""
        await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="Alert Title",
            channels=[NotificationChannel.EMAIL],
            email_to="user@example.com",
        )

        call_kwargs = mock_email_service.send.call_args.kwargs
        assert call_kwargs.get("subject") == "Alert Title"

    @pytest.mark.asyncio
    async def test_email_uses_custom_html(self, dispatcher, mock_email_service):
        """email_html should be passed as html_body to the email service."""
        custom_html = "<h1>Custom Template</h1><p>Price dropped!</p>"

        await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="HTML email test",
            channels=[NotificationChannel.EMAIL],
            email_to="user@example.com",
            email_html=custom_html,
        )

        call_kwargs = mock_email_service.send.call_args.kwargs
        assert call_kwargs.get("html_body") == custom_html

    @pytest.mark.asyncio
    async def test_email_builds_html_from_body_when_no_html_provided(
        self, dispatcher, mock_email_service
    ):
        """Without email_html, body should be wrapped in <p> tags as html_body."""
        await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="Title",
            body="Plain body text",
            channels=[NotificationChannel.EMAIL],
            email_to="user@example.com",
        )

        call_kwargs = mock_email_service.send.call_args.kwargs
        assert "<p>Plain body text</p>" in call_kwargs.get("html_body", "")


# =============================================================================
# TestDedupFailOpen — dedup query exception handling
# =============================================================================


class TestDedupFailOpen:

    @pytest.mark.asyncio
    async def test_dedup_query_exception_allows_delivery(self, dispatcher, mock_db):
        """If the dedup SELECT raises an exception, delivery should proceed (fail-open)."""
        # First execute raises; second execute succeeds (the INSERT)
        mock_db.execute.side_effect = [
            Exception("DB unreachable"),
            _insert_result(),
        ]

        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="Dedup failure",
            channels=[NotificationChannel.IN_APP],
            dedup_key="key_that_errors",
            cooldown_seconds=3600,
        )

        # skipped_dedup should be False — we fail open
        assert result["skipped_dedup"] is False

    @pytest.mark.asyncio
    async def test_dedup_failure_still_delivers_in_app(self, dispatcher, mock_db):
        """After a dedup check failure, in-app delivery is attempted."""
        # Dedup query fails → fail open → in-app INSERT succeeds
        mock_db.execute.side_effect = [
            Exception("Query timeout"),
            _insert_result(),
        ]

        result = await dispatcher.send(
            user_id=TEST_USER_ID,
            type="warning",
            title="Fail-open delivery",
            channels=[NotificationChannel.IN_APP],
            dedup_key="fail_open_key",
        )

        assert result["channels"].get(NotificationChannel.IN_APP.value) is True


# =============================================================================
# TestMetadataPassthrough
# =============================================================================


class TestMetadataPassthrough:

    @pytest.mark.asyncio
    async def test_metadata_passed_to_push_service(self, dispatcher, mock_push_service):
        """Custom metadata should be forwarded to push_service.send_push as data."""
        custom_meta = {"region": "us_ct", "price": 0.08}

        await dispatcher.send(
            user_id=TEST_USER_ID,
            type="price_alert",
            title="Metadata test",
            channels=[NotificationChannel.PUSH],
            metadata=custom_meta,
        )

        mock_push_service.send_push.assert_awaited_once()
        push_call = mock_push_service.send_push.call_args
        data_arg = push_call.kwargs.get("data", {})
        assert data_arg.get("region") == "us_ct"
        assert data_arg.get("price") == 0.08

    @pytest.mark.asyncio
    async def test_dedup_key_merged_into_existing_metadata(self, dispatcher, mock_db):
        """dedup_key should be added to user-supplied metadata without overwriting it."""
        mock_db.execute.side_effect = [_no_dedup_result(), _insert_result()]

        await dispatcher.send(
            user_id=TEST_USER_ID,
            type="info",
            title="Merged metadata",
            channels=[NotificationChannel.IN_APP],
            metadata={"region": "us_ma"},
            dedup_key="merged_key",
            cooldown_seconds=300,
        )

        insert_call = mock_db.execute.call_args_list[1]
        params = insert_call.args[1] if insert_call.args else {}
        import json

        meta = json.loads(params["meta"])
        # Both the original metadata and dedup_key should be present
        assert meta["region"] == "us_ma"
        assert meta["dedup_key"] == "merged_key"
