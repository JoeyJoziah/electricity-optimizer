"""
Tests for GitHub webhook endpoint.

Covers:
- Signature verification (valid, invalid, missing)
- Event type handling
- Secret not configured (503)
"""

import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from config.settings import settings

_TEST_WEBHOOK_SECRET = "test_webhook_secret_for_unit_tests"


def _make_signature(payload: bytes, secret: str) -> str:
    """Generate a valid X-Hub-Signature-256 header value."""
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture
def webhook_client():
    """Client with a configured webhook secret."""
    with patch.object(settings, "github_webhook_secret", _TEST_WEBHOOK_SECRET):
        from main import app
        with TestClient(app) as client:
            yield client


@pytest.fixture
def unconfigured_client():
    """Client without a webhook secret."""
    with patch.object(settings, "github_webhook_secret", None):
        from main import app
        with TestClient(app) as client:
            yield client


# --- Signature verification ---

class TestGitHubWebhookSignature:
    """Tests for webhook signature verification."""

    def test_valid_signature_returns_200(self, webhook_client):
        payload = json.dumps({"action": "opened"}).encode()
        sig = _make_signature(payload, _TEST_WEBHOOK_SECRET)
        response = webhook_client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "push",
                "X-GitHub-Delivery": "abc-123",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["received"] is True
        assert data["event"] == "push"

    def test_invalid_signature_returns_400(self, webhook_client):
        payload = json.dumps({"action": "opened"}).encode()
        response = webhook_client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000",
                "X-GitHub-Event": "push",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 400

    def test_missing_signature_returns_400(self, webhook_client):
        payload = json.dumps({"action": "opened"}).encode()
        response = webhook_client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "push",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 400

    def test_malformed_signature_format_returns_400(self, webhook_client):
        payload = json.dumps({"action": "opened"}).encode()
        response = webhook_client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "X-Hub-Signature-256": "md5=badhash",
                "X-GitHub-Event": "push",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 400


# --- Secret not configured ---

class TestWebhookNotConfigured:
    """When GITHUB_WEBHOOK_SECRET is not set, endpoint returns 503."""

    def test_unconfigured_returns_503(self, unconfigured_client):
        payload = json.dumps({"action": "opened"}).encode()
        response = unconfigured_client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "X-GitHub-Event": "push",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 503


# --- Event types ---

class TestWebhookEventTypes:
    """Various GitHub event types are accepted."""

    @pytest.mark.parametrize("event_type", ["push", "pull_request", "issues", "ping"])
    def test_various_events_accepted(self, webhook_client, event_type):
        payload = json.dumps({"action": "opened"}).encode()
        sig = _make_signature(payload, _TEST_WEBHOOK_SECRET)
        response = webhook_client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": event_type,
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200
        assert response.json()["event"] == event_type
