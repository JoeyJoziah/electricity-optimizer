"""
Email Service

Provides email sending with SendGrid as primary and SMTP as fallback.
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
    Email service with SendGrid primary and SMTP fallback.

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
        Send an email. Tries SendGrid first, falls back to SMTP.

        Returns True on success, False on failure.
        """
        if self._settings.sendgrid_api_key:
            if await self._send_via_sendgrid(to, subject, html_body, text_body):
                return True

        if self._settings.smtp_host:
            if await self._send_via_smtp(to, subject, html_body, text_body):
                return True

        logger.warning(
            "email_send_no_provider",
            to=to,
            subject=subject,
            message="No email provider configured (set SENDGRID_API_KEY or SMTP_HOST)",
        )
        return False

    async def _send_via_sendgrid(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
    ) -> bool:
        """Send email via SendGrid API."""
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail, Email, To, Content

            message = Mail(
                from_email=Email(
                    self._settings.email_from_address,
                    self._settings.email_from_name,
                ),
                to_emails=To(to),
                subject=subject,
                html_content=Content("text/html", html_body),
            )

            if text_body:
                message.add_content(Content("text/plain", text_body))

            sg = SendGridAPIClient(self._settings.sendgrid_api_key)
            response = sg.send(message)

            logger.info(
                "email_sent_sendgrid",
                to=to,
                subject=subject,
                status_code=response.status_code,
            )
            return True

        except Exception as e:
            logger.error("email_sendgrid_failed", to=to, error=str(e))
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
