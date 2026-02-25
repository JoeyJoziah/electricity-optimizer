"""
Security Headers Middleware

Adds security headers to all responses to protect against common web vulnerabilities.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send

from config.settings import settings


class SecurityHeadersMiddleware:
    """
    Pure ASGI middleware to add security headers to all responses.

    Headers added:
    - Content-Security-Policy (CSP)
    - X-Frame-Options
    - X-Content-Type-Options
    - X-XSS-Protection
    - Strict-Transport-Security (HSTS)
    - Referrer-Policy
    - Permissions-Policy
    """

    def __init__(
        self,
        app: ASGIApp,
        csp_policy: str = None,
        hsts_max_age: int = 31536000,  # 1 year
        include_subdomains: bool = True,
    ):
        """
        Initialize security headers middleware.

        Args:
            app: ASGI application
            csp_policy: Custom Content-Security-Policy
            hsts_max_age: HSTS max-age in seconds
            include_subdomains: Include subdomains in HSTS
        """
        self.app = app
        self.csp_policy = csp_policy or self._default_csp()
        self.hsts_max_age = hsts_max_age
        self.include_subdomains = include_subdomains

    def _default_csp(self) -> str:
        """Generate default Content-Security-Policy"""
        if settings.is_development:
            # More permissive for development
            return (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self' data:; "
                "connect-src 'self' ws: wss: http: https:; "
                "frame-ancestors 'none'"
            )
        else:
            # Strict for production
            return (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self' data: https:; "
                "font-src 'self'; "
                "connect-src 'self' https:; "
                "frame-ancestors 'none'; "
                "form-action 'self'; "
                "base-uri 'self'"
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Add security headers to response."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        is_api_path = path.startswith("/api/")

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)

                # X-Frame-Options: Prevent clickjacking
                headers["X-Frame-Options"] = "DENY"

                # X-Content-Type-Options: Prevent MIME type sniffing
                headers["X-Content-Type-Options"] = "nosniff"

                # X-XSS-Protection: Enable browser XSS filtering
                headers["X-XSS-Protection"] = "1; mode=block"

                # Content-Security-Policy
                headers["Content-Security-Policy"] = self.csp_policy

                # Referrer-Policy: Control referrer information
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

                # Permissions-Policy: Disable unnecessary browser features
                headers["Permissions-Policy"] = (
                    "accelerometer=(), "
                    "camera=(), "
                    "geolocation=(), "
                    "gyroscope=(), "
                    "magnetometer=(), "
                    "microphone=(), "
                    "payment=(), "
                    "usb=()"
                )

                # Strict-Transport-Security (HSTS): Force HTTPS
                # Only add in production (HTTPS required)
                if settings.is_production:
                    hsts_value = f"max-age={self.hsts_max_age}"
                    if self.include_subdomains:
                        hsts_value += "; includeSubDomains"
                    hsts_value += "; preload"
                    headers["Strict-Transport-Security"] = hsts_value

                # Cache-Control: Prevent caching of sensitive data
                if is_api_path:
                    headers["Cache-Control"] = (
                        "no-store, no-cache, must-revalidate, private"
                    )
                    headers["Pragma"] = "no-cache"
                    headers["Expires"] = "0"

            await send(message)

        await self.app(scope, receive, send_wrapper)


def add_security_headers(response) -> None:
    """
    Utility function to add security headers to a response.

    Can be used directly on individual responses if middleware is not used.

    Args:
        response: Response object to add headers to
    """
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
