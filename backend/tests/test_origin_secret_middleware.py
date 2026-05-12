"""
Tests for CFOriginSecretMiddleware.

Covers:
- Request allowed when CF_ORIGIN_SECRET is not configured (no-op mode)
- Request allowed when header matches configured secret
- Request rejected 403 when header is missing
- Request rejected 403 when header value is wrong
- /health bypassed even without the header
- /api/v1/webhooks/ bypassed even without the header
- /metrics bypassed even without the header
"""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.origin_secret import CFOriginSecretMiddleware


def _make_app(secret: str | None) -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/test")
    async def test_route():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/api/v1/webhooks/stripe")
    async def webhook():
        return {"received": True}

    @app.get("/metrics")
    async def metrics():
        return {"metrics": True}

    app.add_middleware(CFOriginSecretMiddleware)

    def _override_settings():
        s = type("S", (), {"cf_origin_secret": secret})()
        return s

    app.dependency_overrides = {}
    # Patch at the middleware module level
    return app, _override_settings


class TestOriginSecretMiddleware:
    def _client(self, secret: str | None) -> TestClient:
        app, _ = _make_app(secret)
        with patch("middleware.origin_secret.get_settings") as ms:
            ms.return_value.cf_origin_secret = secret
            return TestClient(app, raise_server_exceptions=False)

    def test_noop_when_no_secret_configured(self):
        with patch("middleware.origin_secret.get_settings") as ms:
            ms.return_value.cf_origin_secret = None
            app, _ = _make_app(None)
            client = TestClient(app)
            resp = client.get("/api/v1/test")
        assert resp.status_code == 200

    def test_allowed_with_correct_header(self):
        with patch("middleware.origin_secret.get_settings") as ms:
            ms.return_value.cf_origin_secret = "supersecret"
            app, _ = _make_app("supersecret")
            client = TestClient(app)
            resp = client.get("/api/v1/test", headers={"X-CF-Origin-Secret": "supersecret"})
        assert resp.status_code == 200

    def test_rejected_when_header_missing(self):
        with patch("middleware.origin_secret.get_settings") as ms:
            ms.return_value.cf_origin_secret = "supersecret"
            app, _ = _make_app("supersecret")
            client = TestClient(app)
            resp = client.get("/api/v1/test")
        assert resp.status_code == 403

    def test_rejected_when_header_wrong(self):
        with patch("middleware.origin_secret.get_settings") as ms:
            ms.return_value.cf_origin_secret = "supersecret"
            app, _ = _make_app("supersecret")
            client = TestClient(app)
            resp = client.get("/api/v1/test", headers={"X-CF-Origin-Secret": "wrongvalue"})
        assert resp.status_code == 403

    def test_health_bypassed(self):
        with patch("middleware.origin_secret.get_settings") as ms:
            ms.return_value.cf_origin_secret = "supersecret"
            app, _ = _make_app("supersecret")
            client = TestClient(app)
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_webhooks_bypassed(self):
        with patch("middleware.origin_secret.get_settings") as ms:
            ms.return_value.cf_origin_secret = "supersecret"
            app, _ = _make_app("supersecret")
            client = TestClient(app)
            resp = client.post("/api/v1/webhooks/stripe")
        assert resp.status_code == 200

    def test_metrics_bypassed(self):
        with patch("middleware.origin_secret.get_settings") as ms:
            ms.return_value.cf_origin_secret = "supersecret"
            app, _ = _make_app("supersecret")
            client = TestClient(app)
            resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_403_body_is_json(self):
        with patch("middleware.origin_secret.get_settings") as ms:
            ms.return_value.cf_origin_secret = "supersecret"
            app, _ = _make_app("supersecret")
            client = TestClient(app)
            resp = client.get("/api/v1/test")
        assert resp.headers["content-type"] == "application/json"
        assert resp.json() == {"detail": "Forbidden"}
