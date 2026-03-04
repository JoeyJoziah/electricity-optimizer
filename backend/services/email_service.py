"""
Email Service

Provides email sending with Resend as primary and SMTP as fallback.
Includes Jinja2 template rendering for HTML emails.
"""

import os
from typing import Optional

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = structlog.get_logger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates", "emails")


class EmailService:
    """
    Email service with Resend primary and SMTP fallback.

    Usage:
        service = EmailService()
        html = service.render_template("welcome_beta.html", name="Alice", betaCode="BETA-123")
        await service.send("alice@example.com", "Welcome!", html)
    """

    def __init__(self):
        from config.settings import settings

        self._settings = settings
        self._jinja_env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=select_autoescape(["html"]),
        )

    def render_template(self, template_name: str, **context) -> str:
        """Render an HTML email template with the given context."""
        template = self._jinja_env.get_template(template_name)
        return template.render(**context)

    async def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
    ) -> bool:
        """
        Send an email. Tries Resend first, falls back to SMTP.

        Returns True on success, False on failure.
        """
        if self._settings.resend_api_key:
            if await self._send_via_resend(to, subject, html_body, text_body):
                return True

        if self._settings.smtp_host:
            if await self._send_via_smtp(to, subject, html_body, text_body):
                return True

        logger.warning(
            "email_send_no_provider",
            to=to,
            subject=subject,
            message="No email provider configured (set RESEND_API_KEY or SMTP_HOST)",
        )
        return False

    async def _send_via_resend(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
    ) -> bool:
        """Send email via Resend API."""
        try:
            import resend

            resend.api_key = self._settings.resend_api_key

            from_address = f"{self._settings.email_from_name} <{self._settings.email_from_address}>"

            params = {
                "from": from_address,
                "to": [to],
                "subject": subject,
                "html": html_body,
            }

            if text_body:
                params["text"] = text_body

            resend.Emails.send(params)

            logger.info(
                "email_sent_resend",
                to=to,
                subject=subject,
            )
            return True

        except Exception as e:
            logger.error("email_resend_failed", to=to, error=str(e))
            return False

    async def _send_via_smtp(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
    ) -> bool:
        """Send email via SMTP (fallback)."""
        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            import aiosmtplib

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self._settings.email_from_name} <{self._settings.email_from_address}>"
            msg["To"] = to

            if text_body:
                msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            await aiosmtplib.send(
                msg,
                hostname=self._settings.smtp_host,
                port=self._settings.smtp_port,
                username=self._settings.smtp_username,
                password=self._settings.smtp_password,
                start_tls=True,
            )

            logger.info("email_sent_smtp", to=to, subject=subject)
            return True

        except Exception as e:
            logger.error("email_smtp_failed", to=to, error=str(e))
            return False
