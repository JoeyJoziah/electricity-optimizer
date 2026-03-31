"""
Tests for PushNotificationService (backend/services/push_notification_service.py)

Coverage:
- is_configured property (True when both keys set, False otherwise)
- send_push: returns True on success (201/200 from OneSignal)
- send_push: returns False when not configured (no API call made)
- send_push: returns False on HTTP error (4xx/5xx)
- send_push: returns False on network exception
- send_push: request payload matches OneSignal spec (include_external_user_ids, headings, contents)
- send_price_alert: delegates to send_push with correct title and message format
- send_push: data defaults to empty dict when not provided
- send_push: custom data is forwarded as-is
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from services.push_notification_service import (ONESIGNAL_API_URL,
                                                PushNotificationService)

# =============================================================================
# Fixtures
# =============================================================================

TEST_USER_ID = str(uuid4())
_APP_ID = "test-app-id-1234"
_REST_KEY = "test-rest-api-key-5678"


def _configured_settings() -> MagicMock:
    settings = MagicMock()
    settings.onesignal_app_id = _APP_ID
    settings.onesignal_rest_api_key = _REST_KEY
    return settings


def _unconfigured_settings(missing: str = "both") -> MagicMock:
    settings = MagicMock()
    if missing == "app_id":
        settings.onesignal_app_id = None
        settings.onesignal_rest_api_key = _REST_KEY
    elif missing == "rest_key":
        settings.onesignal_app_id = _APP_ID
        settings.onesignal_rest_api_key = None
    else:
        settings.onesignal_app_id = None
        settings.onesignal_rest_api_key = None
    return settings


def _mock_http_response(status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    else:
        resp.raise_for_status.return_value = None
    return resp


# =============================================================================
# TestIsConfigured
# =============================================================================


class TestIsConfigured:
    def test_true_when_both_keys_present(self):
        svc = PushNotificationService(settings=_configured_settings())
        assert svc.is_configured is True

    def test_false_when_app_id_missing(self):
        svc = PushNotificationService(settings=_unconfigured_settings("app_id"))
        assert svc.is_configured is False

    def test_false_when_rest_key_missing(self):
        svc = PushNotificationService(settings=_unconfigured_settings("rest_key"))
        assert svc.is_configured is False

    def test_false_when_both_missing(self):
        svc = PushNotificationService(settings=_unconfigured_settings("both"))
        assert svc.is_configured is False


# =============================================================================
# TestSendPush
# =============================================================================


class TestSendPush:
    async def test_returns_true_on_success(self):
        svc = PushNotificationService(settings=_configured_settings())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_http_response(200))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.push_notification_service.httpx.AsyncClient", return_value=mock_client
        ):
            result = await svc.send_push(
                user_id=TEST_USER_ID,
                title="Test",
                message="Hello!",
            )

        assert result is True

    async def test_returns_false_when_not_configured(self):
        svc = PushNotificationService(settings=_unconfigured_settings())
        with patch("services.push_notification_service.httpx.AsyncClient") as mock_cls:
            result = await svc.send_push(
                user_id=TEST_USER_ID,
                title="Test",
                message="Hello!",
            )
            # No HTTP call should be made
            mock_cls.assert_not_called()

        assert result is False

    async def test_returns_false_on_http_4xx(self):
        svc = PushNotificationService(settings=_configured_settings())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_http_response(400))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.push_notification_service.httpx.AsyncClient", return_value=mock_client
        ):
            result = await svc.send_push(
                user_id=TEST_USER_ID,
                title="Test",
                message="Bad request!",
            )

        assert result is False

    async def test_returns_false_on_network_exception(self):
        svc = PushNotificationService(settings=_configured_settings())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.push_notification_service.httpx.AsyncClient", return_value=mock_client
        ):
            result = await svc.send_push(
                user_id=TEST_USER_ID,
                title="Test",
                message="Network error!",
            )

        assert result is False

    async def test_request_payload_matches_onesignal_spec(self):
        svc = PushNotificationService(settings=_configured_settings())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_http_response(200))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        custom_data = {"type": "price_alert", "region": "CT"}

        with patch(
            "services.push_notification_service.httpx.AsyncClient", return_value=mock_client
        ):
            await svc.send_push(
                user_id=TEST_USER_ID,
                title="Price Alert",
                message="Price dropped!",
                data=custom_data,
            )

        mock_client.post.assert_awaited_once()
        call_kwargs = mock_client.post.call_args
        url_arg = (
            call_kwargs.args[0]
            if call_kwargs.args
            else call_kwargs.kwargs.get("url", call_kwargs.args[0] if call_kwargs.args else None)
        )
        # Verify the URL is the OneSignal endpoint
        assert ONESIGNAL_API_URL in str(call_kwargs)

        json_body = call_kwargs.kwargs.get("json", {})
        assert json_body["app_id"] == _APP_ID
        assert TEST_USER_ID in json_body["include_external_user_ids"]
        assert json_body["headings"]["en"] == "Price Alert"
        assert json_body["contents"]["en"] == "Price dropped!"
        assert json_body["data"] == custom_data

    async def test_authorization_header_uses_rest_key(self):
        svc = PushNotificationService(settings=_configured_settings())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_http_response(200))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.push_notification_service.httpx.AsyncClient", return_value=mock_client
        ):
            await svc.send_push(
                user_id=TEST_USER_ID,
                title="T",
                message="M",
            )

        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers.get("Authorization") == f"Basic {_REST_KEY}"

    async def test_data_defaults_to_empty_dict(self):
        svc = PushNotificationService(settings=_configured_settings())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_http_response(200))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.push_notification_service.httpx.AsyncClient", return_value=mock_client
        ):
            await svc.send_push(
                user_id=TEST_USER_ID,
                title="T",
                message="M",
                # data intentionally omitted
            )

        json_body = mock_client.post.call_args.kwargs.get("json", {})
        assert json_body["data"] == {}

    async def test_returns_false_on_500(self):
        svc = PushNotificationService(settings=_configured_settings())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_http_response(500))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.push_notification_service.httpx.AsyncClient", return_value=mock_client
        ):
            result = await svc.send_push(
                user_id=TEST_USER_ID,
                title="T",
                message="M",
            )

        assert result is False


# =============================================================================
# TestSendPriceAlert
# =============================================================================


class TestSendPriceAlert:
    async def test_delegates_to_send_push(self):
        svc = PushNotificationService(settings=_configured_settings())
        with patch.object(svc, "send_push", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            result = await svc.send_price_alert(
                user_id=TEST_USER_ID,
                region="CT",
                current_price=0.0812,
                threshold=0.1000,
            )

        assert result is True
        mock_send.assert_awaited_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["user_id"] == TEST_USER_ID
        assert call_kwargs["title"] == "Price Alert"

    async def test_message_includes_region_and_price(self):
        svc = PushNotificationService(settings=_configured_settings())
        with patch.object(svc, "send_push", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await svc.send_price_alert(
                user_id=TEST_USER_ID,
                region="MA",
                current_price=0.0750,
                threshold=0.0800,
            )

        message = mock_send.call_args.kwargs["message"]
        assert "MA" in message
        assert "0.0750" in message
        assert "0.0800" in message

    async def test_data_includes_type_and_region(self):
        svc = PushNotificationService(settings=_configured_settings())
        with patch.object(svc, "send_push", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await svc.send_price_alert(
                user_id=TEST_USER_ID,
                region="NY",
                current_price=0.09,
                threshold=0.10,
            )

        data = mock_send.call_args.kwargs.get("data", {})
        assert data.get("type") == "price_alert"
        assert data.get("region") == "NY"

    async def test_propagates_false_on_failure(self):
        svc = PushNotificationService(settings=_configured_settings())
        with patch.object(svc, "send_push", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = False
            result = await svc.send_price_alert(
                user_id=TEST_USER_ID,
                region="CA",
                current_price=0.15,
                threshold=0.12,
            )

        assert result is False
