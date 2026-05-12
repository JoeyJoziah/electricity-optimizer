"""
Tests for /api/v1/internal/model-versions endpoints (TASK-MLDATA-003).

Covers:
- GET  /internal/model-versions        — list versions, empty list, DB error.
- POST /internal/model-versions/compare — valid comparison, 404 for unknown IDs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _noop_verify_api_key():
    """Bypass API key auth in tests."""
    return True


def _make_version_model(
    id="ver-1",
    model_name="ensemble",
    version_tag="v1.0",
    config=None,
    metrics=None,
    is_active=False,
    created_at=None,
    promoted_at=None,
):
    """Build a mock ModelVersion (matches the Pydantic model shape)."""
    from models.model_version import ModelVersion

    return ModelVersion(
        id=id,
        model_name=model_name,
        version_tag=version_tag,
        config=config or {},
        metrics=metrics or {"mape": 5.0},
        is_active=is_active,
        created_at=created_at or datetime(2026, 3, 10, tzinfo=UTC),
        promoted_at=promoted_at,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def api_client():
    """
    TestClient with:
    - API key auth bypassed
    - DB session stubbed (execute returns empty result by default)
    """
    from api.dependencies import get_db_session, verify_api_key
    from main import app

    db_session = AsyncMock()
    db_session.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: []))
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[verify_api_key] = _noop_verify_api_key

    with TestClient(app) as client:
        yield client, db_session

    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(verify_api_key, None)


# ---------------------------------------------------------------------------
# GET /internal/model-versions
# ---------------------------------------------------------------------------


class TestListModelVersions:
    """Tests for GET /api/v1/internal/model-versions"""

    def test_returns_200_with_empty_list(self, api_client):
        """Should return 200 with an empty versions list when no rows exist."""
        client, db = api_client
        with patch(
            "services.model_version_service.ModelVersionService.list_versions",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = client.get(
                "/api/v1/internal/model-versions",
                headers={"X-API-Key": "test-key"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["model_name"] == "ensemble"
        assert data["versions"] == []
        assert data["count"] == 0

    def test_returns_200_with_version_list(self, api_client):
        """Should return a list of version summaries when rows exist."""
        client, db = api_client
        versions = [
            _make_version_model(id="v1", version_tag="v2.0", is_active=True),
            _make_version_model(id="v2", version_tag="v1.0", is_active=False),
        ]
        with patch(
            "services.model_version_service.ModelVersionService.list_versions",
            new_callable=AsyncMock,
            return_value=versions,
        ):
            resp = client.get(
                "/api/v1/internal/model-versions",
                headers={"X-API-Key": "test-key"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert data["versions"][0]["version_tag"] == "v2.0"
        assert data["versions"][0]["is_active"] is True
        assert data["versions"][1]["is_active"] is False

    def test_version_response_contains_required_fields(self, api_client):
        """Each version entry must include id, version_tag, is_active, metrics, created_at."""
        client, db = api_client
        versions = [_make_version_model(id="v1", metrics={"mape": 4.8})]
        with patch(
            "services.model_version_service.ModelVersionService.list_versions",
            new_callable=AsyncMock,
            return_value=versions,
        ):
            resp = client.get(
                "/api/v1/internal/model-versions",
                headers={"X-API-Key": "test-key"},
            )

        entry = resp.json()["versions"][0]
        assert "id" in entry
        assert "version_tag" in entry
        assert "is_active" in entry
        assert "metrics" in entry
        assert "created_at" in entry
        assert entry["metrics"]["mape"] == 4.8

    def test_custom_model_name_passed_to_service(self, api_client):
        """model_name query param should be forwarded to the service."""
        client, db = api_client
        captured = {}

        async def _capture(self_inner, model_name, limit=10):
            captured["model_name"] = model_name
            return []

        with patch(
            "services.model_version_service.ModelVersionService.list_versions",
            new=_capture,
        ):
            client.get(
                "/api/v1/internal/model-versions?model_name=price_forecast",
                headers={"X-API-Key": "test-key"},
            )

        assert captured.get("model_name") == "price_forecast"

    def test_custom_limit_param(self, api_client):
        """limit query param should be forwarded to the service."""
        client, db = api_client
        captured = {}

        async def _capture(self_inner, model_name, limit=10):
            captured["limit"] = limit
            return []

        with patch(
            "services.model_version_service.ModelVersionService.list_versions",
            new=_capture,
        ):
            client.get(
                "/api/v1/internal/model-versions?limit=5",
                headers={"X-API-Key": "test-key"},
            )

        assert captured.get("limit") == 5


# ---------------------------------------------------------------------------
# POST /internal/model-versions/compare
# ---------------------------------------------------------------------------


class TestCompareModelVersions:
    """Tests for POST /api/v1/internal/model-versions/compare"""

    def test_returns_200_with_comparison_result(self, api_client):
        """Should return 200 with metric deltas when both versions exist."""
        from models.model_version import (ModelVersionResponse,
                                          VersionComparisonResult)

        client, db = api_client

        ver_a = ModelVersionResponse(
            id="ver-a",
            model_name="ensemble",
            version_tag="v1.0",
            config={},
            metrics={"mape": 5.0, "rmse": 0.02},
            is_active=False,
            created_at=datetime(2026, 3, 1, tzinfo=UTC),
            promoted_at=None,
        )
        ver_b = ModelVersionResponse(
            id="ver-b",
            model_name="ensemble",
            version_tag="v2.0",
            config={},
            metrics={"mape": 4.0, "rmse": 0.015},
            is_active=True,
            created_at=datetime(2026, 3, 10, tzinfo=UTC),
            promoted_at=datetime(2026, 3, 10, tzinfo=UTC),
        )
        comparison_result = VersionComparisonResult(
            version_a=ver_a,
            version_b=ver_b,
            metric_comparison={
                "mape": {"version_a": 5.0, "version_b": 4.0, "delta": -1.0},
                "rmse": {"version_a": 0.02, "version_b": 0.015, "delta": -0.005},
            },
        )

        with patch(
            "services.model_version_service.ModelVersionService.compare_versions",
            new_callable=AsyncMock,
            return_value=comparison_result,
        ):
            resp = client.post(
                "/api/v1/internal/model-versions/compare",
                json={
                    "model_name": "ensemble",
                    "version_a_id": "ver-a",
                    "version_b_id": "ver-b",
                },
                headers={"X-API-Key": "test-key"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["model_name"] == "ensemble"
        assert data["version_a"]["version_tag"] == "v1.0"
        assert data["version_b"]["version_tag"] == "v2.0"
        assert data["metric_comparison"]["mape"]["delta"] == pytest.approx(-1.0)

    def test_returns_404_when_version_not_found(self, api_client):
        """Should return 404 when compare_versions raises ValueError."""
        client, db = api_client

        with patch(
            "services.model_version_service.ModelVersionService.compare_versions",
            new_callable=AsyncMock,
            side_effect=ValueError("Model version not found: 'bad-id'"),
        ):
            resp = client.post(
                "/api/v1/internal/model-versions/compare",
                json={
                    "model_name": "ensemble",
                    "version_a_id": "bad-id",
                    "version_b_id": "ver-b",
                },
                headers={"X-API-Key": "test-key"},
            )

        assert resp.status_code == 404
        assert "Model version not found" in resp.json()["detail"]

    def test_requires_model_name_in_body(self, api_client):
        """Missing model_name should return 422 Unprocessable Entity."""
        client, db = api_client

        resp = client.post(
            "/api/v1/internal/model-versions/compare",
            json={"version_a_id": "ver-a", "version_b_id": "ver-b"},
            headers={"X-API-Key": "test-key"},
        )

        assert resp.status_code == 422

    def test_returns_comparison_with_metric_comparison_key(self, api_client):
        """Response must include a metric_comparison dict."""
        from models.model_version import (ModelVersionResponse,
                                          VersionComparisonResult)

        client, db = api_client

        ver_a = ModelVersionResponse(
            id="ver-a",
            model_name="ensemble",
            version_tag="v1.0",
            config={},
            metrics={},
            is_active=False,
            created_at=datetime(2026, 3, 1, tzinfo=UTC),
            promoted_at=None,
        )
        ver_b = ModelVersionResponse(
            id="ver-b",
            model_name="ensemble",
            version_tag="v2.0",
            config={},
            metrics={},
            is_active=True,
            created_at=datetime(2026, 3, 10, tzinfo=UTC),
            promoted_at=None,
        )
        comparison_result = VersionComparisonResult(
            version_a=ver_a,
            version_b=ver_b,
            metric_comparison={},
        )

        with patch(
            "services.model_version_service.ModelVersionService.compare_versions",
            new_callable=AsyncMock,
            return_value=comparison_result,
        ):
            resp = client.post(
                "/api/v1/internal/model-versions/compare",
                json={
                    "model_name": "ensemble",
                    "version_a_id": "ver-a",
                    "version_b_id": "ver-b",
                },
                headers={"X-API-Key": "test-key"},
            )

        assert resp.status_code == 200
        assert "metric_comparison" in resp.json()
