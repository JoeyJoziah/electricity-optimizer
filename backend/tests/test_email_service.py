"""
Tests for the Email Service (backend/services/email_service.py)

Tests cover:
- Resend sending path
- SMTP fallback chain
- Template rendering
- Error handling and fallback behavior
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_service(
    resend_api_key=None,
    smtp_host=None,
    smtp_port=587,
    smtp_username="user",
    smtp_password="pass",
    email_from_address="noreply@test.com",
    email_from_name="Test App",
):
    """Construct an EmailService without calling __init__ (avoids real settings import)."""
    from services.email_service import EmailService

    service = object.__new__(EmailService)
    mock_settings = MagicMock()
    mock_settings.resend_api_key = resend_api_key
    mock_settings.smtp_host = smtp_host
    mock_settings.smtp_port = smtp_port
    mock_settings.smtp_username = smtp_username
    mock_settings.smtp_password = smtp_password
    mock_settings.email_from_address = email_from_address
    mock_settings.email_from_name = email_from_name
    service._settings = mock_settings

    # Mock Jinja2 environment
    mock_env = MagicMock()
    mock_template = MagicMock()
    mock_template.render.return_value = "<html>Hello</html>"
    mock_env.get_template.return_value = mock_template
    service._jinja_env = mock_env

    return service


# =============================================================================
# TEMPLATE RENDERING
# =============================================================================


class TestTemplateRendering:
    """Tests for EmailService.render_template()."""

    def test_render_template_calls_jinja(self):
        """render_template should load and render the named template."""
        service = _make_service()
        result = service.render_template("welcome_beta.html", name="Alice")
        service._jinja_env.get_template.assert_called_once_with("welcome_beta.html")
        assert result == "<html>Hello</html>"

    def test_render_template_passes_context(self):
        """Template context variables should be forwarded."""
        service = _make_service()
        service.render_template("test.html", name="Bob", code="ABC")
        template = service._jinja_env.get_template.return_value
        template.render.assert_called_once_with(name="Bob", code="ABC")

    def test_render_template_missing_raises(self):
        """Missing template should propagate the exception."""
        from jinja2 import TemplateNotFound

        service = _make_service()
        service._jinja_env.get_template.side_effect = TemplateNotFound("missing.html")
        with pytest.raises(TemplateNotFound):
            service.render_template("missing.html")


# =============================================================================
# RESEND PATH
# =============================================================================


class TestResendPath:
    """Tests for the Resend code path in EmailService.send()."""

    async def test_resend_success(self):
        """When Resend is configured and succeeds, send() returns True."""
        service = _make_service(resend_api_key="re_test-key")

        with patch.object(service, "_send_via_resend", return_value=True):
            result = await service.send(
                to="user@example.com",
                subject="Test",
                html_body="<p>Hello</p>",
            )
        assert result is True

    async def test_resend_failure_falls_back_to_smtp(self):
        """When Resend fails and SMTP is configured, SMTP should be tried."""
        service = _make_service(resend_api_key="re_test-key", smtp_host="smtp.test.com")

        with (
            patch.object(service, "_send_via_resend", return_value=False),
            patch.object(service, "_send_via_smtp", return_value=True) as mock_smtp,
        ):
            result = await service.send(
                to="user@example.com",
                subject="Test",
                html_body="<p>Hello</p>",
            )
        assert result is True
        mock_smtp.assert_called_once()

    async def test_resend_not_configured_skips(self):
        """When Resend is not configured, _send_via_resend should not be called."""
        service = _make_service(resend_api_key=None, smtp_host="smtp.test.com")

        with (
            patch.object(service, "_send_via_resend") as mock_resend,
            patch.object(service, "_send_via_smtp", return_value=True),
        ):
            result = await service.send(
                to="user@example.com",
                subject="Test",
                html_body="<p>Hello</p>",
            )
        assert result is True
        mock_resend.assert_not_called()


# =============================================================================
# SMTP FALLBACK PATH
# =============================================================================


class TestSMTPPath:
    """Tests for the SMTP code path in EmailService.send()."""

    async def test_smtp_success(self):
        """When SMTP is configured and succeeds, send() returns True."""
        service = _make_service(smtp_host="smtp.test.com")

        with patch.object(service, "_send_via_smtp", return_value=True):
            result = await service.send(
                to="user@example.com",
                subject="Test Subject",
                html_body="<p>Content</p>",
            )
        assert result is True

    async def test_smtp_failure_returns_false(self):
        """When SMTP fails, send() returns False."""
        service = _make_service(smtp_host="smtp.test.com")

        with patch.object(service, "_send_via_smtp", return_value=False):
            result = await service.send(
                to="user@example.com",
                subject="Test",
                html_body="<p>Hello</p>",
            )
        assert result is False


# =============================================================================
# NO PROVIDER CONFIGURED
# =============================================================================


class TestNoProvider:
    """Tests for when no email provider is configured."""

    async def test_no_provider_returns_false(self):
        """When neither Resend nor SMTP is configured, send() returns False."""
        service = _make_service(resend_api_key=None, smtp_host=None)

        result = await service.send(
            to="user@example.com",
            subject="Test",
            html_body="<p>Hello</p>",
        )
        assert result is False


# =============================================================================
# ERROR HANDLING
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in email sending."""

    async def test_resend_internal_exception_returns_false(self):
        """_send_via_resend should catch exceptions and return False."""
        service = _make_service(resend_api_key="re_key")

        # Patch the resend module so Emails.send raises
        mock_resend = MagicMock()
        mock_resend.Emails.send.side_effect = Exception("Resend API error")
        with patch.dict("sys.modules", {"resend": mock_resend}):
            # _send_via_resend has its own try/except that returns False
            result = await service._send_via_resend(
                to="user@example.com",
                subject="Test",
                html_body="<p>Hello</p>",
            )
        assert result is False

    async def test_both_providers_fail_returns_false(self):
        """When both Resend and SMTP fail, send() returns False."""
        service = _make_service(resend_api_key="re_key", smtp_host="smtp.test.com")

        with (
            patch.object(service, "_send_via_resend", return_value=False),
            patch.object(service, "_send_via_smtp", return_value=False),
        ):
            result = await service.send(
                to="user@example.com",
                subject="Test",
                html_body="<p>Hello</p>",
            )
        assert result is False

    async def test_send_with_text_body(self):
        """Passing text_body should forward it to the provider method."""
        service = _make_service(smtp_host="smtp.test.com")

        with patch.object(service, "_send_via_smtp", return_value=True) as mock_smtp:
            result = await service.send(
                to="user@example.com",
                subject="Test",
                html_body="<p>Hello</p>",
                text_body="Hello plain text",
            )
        assert result is True
        mock_smtp.assert_called_once_with(
            "user@example.com", "Test", "<p>Hello</p>", "Hello plain text"
        )

    async def test_smtp_exception_returns_false(self):
        """_send_via_smtp should catch exceptions and return False."""
        service = _make_service(smtp_host="smtp.test.com")

        # Patch aiosmtplib to raise inside _send_via_smtp
        with patch.dict("sys.modules", {"aiosmtplib": MagicMock()}):
            import sys

            sys.modules["aiosmtplib"].send = AsyncMock(
                side_effect=Exception("SMTP connect failed")
            )
            result = await service._send_via_smtp(
                to="user@example.com",
                subject="Test",
                html_body="<p>Hello</p>",
            )
        assert result is False
