"""
Tests for ML pipeline tracing — LearningService, ObservationService, ModelVersionService.

RED phase — these tests assert that custom spans are created with correct
attributes when ML service methods are called. They will FAIL until Task 1.5
adds traced() calls to the services.
"""

from __future__ import annotations

import os

os.environ.setdefault("ENVIRONMENT", "test")

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


# ---------------------------------------------------------------------------
# OTel state reset
# ---------------------------------------------------------------------------


def _reset_tracer_provider() -> None:
    import opentelemetry.trace as _trace

    _trace._TRACER_PROVIDER = None  # type: ignore[attr-defined]
    try:
        _trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
    except AttributeError:
        pass


@pytest.fixture(autouse=True)
def reset_otel_state():
    _reset_tracer_provider()
    yield
    _reset_tracer_provider()


def _install_recording_provider():
    """Install a real TracerProvider and return an in-memory exporter."""
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (SimpleSpanProcessor,
                                                SpanExporter, SpanExportResult)

    class _InMemoryExporter(SpanExporter):
        def __init__(self):
            self.spans = []

        def export(self, spans):
            self.spans.extend(spans)
            return SpanExportResult.SUCCESS

        def shutdown(self):
            pass

    exporter = _InMemoryExporter()
    resource = Resource.create({SERVICE_NAME: "test"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return exporter


# ---------------------------------------------------------------------------
# LearningService tracing tests
# ---------------------------------------------------------------------------


class TestLearningServiceTracing:
    """LearningService methods should create spans with ML attributes."""

    async def test_compute_rolling_accuracy_creates_span(self):
        """compute_rolling_accuracy() should create a 'ml.compute_accuracy' span."""
        exporter = _install_recording_provider()

        mock_obs = AsyncMock()
        mock_obs.get_forecast_accuracy = AsyncMock(return_value={"mape": 0.05})
        mock_vs = MagicMock()

        from services.learning_service import LearningService

        svc = LearningService(observation_service=mock_obs, vector_store=mock_vs)
        await svc.compute_rolling_accuracy("NY", days=7)

        ml_spans = [s for s in exporter.spans if s.name.startswith("ml.")]
        assert len(ml_spans) >= 1, f"Expected ml.* span, got: {[s.name for s in exporter.spans]}"
        span = ml_spans[0]
        assert span.attributes.get("ml.region") == "NY"

    async def test_update_ensemble_weights_creates_span(self):
        """update_ensemble_weights() should create a 'ml.update_weights' span."""
        exporter = _install_recording_provider()

        mock_obs = AsyncMock()
        mock_obs.get_model_accuracy_by_version = AsyncMock(
            return_value=[{"model_version": "v1", "mape": 0.05}]
        )
        mock_vs = MagicMock()

        from services.learning_service import LearningService

        svc = LearningService(
            observation_service=mock_obs, vector_store=mock_vs, db_session=AsyncMock()
        )
        await svc.update_ensemble_weights("CA", days=7)

        ml_spans = [s for s in exporter.spans if s.name.startswith("ml.")]
        assert len(ml_spans) >= 1, f"Expected ml.* span, got: {[s.name for s in exporter.spans]}"
        span = ml_spans[0]
        assert span.attributes.get("ml.region") == "CA"


# ---------------------------------------------------------------------------
# ObservationService tracing tests
# ---------------------------------------------------------------------------


class TestObservationServiceTracing:
    """ObservationService methods should create spans with observation attributes."""

    async def test_record_forecast_creates_span(self):
        """record_forecast() should create a 'ml.record_forecast' span."""
        exporter = _install_recording_provider()

        mock_db = AsyncMock()
        # Patch the repository to avoid DB calls
        with patch("services.observation_service.ForecastObservationRepository") as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.insert_forecasts = AsyncMock(return_value=5)
            MockRepo.return_value = mock_repo

            from services.observation_service import ObservationService

            svc = ObservationService(db=mock_db)
            count = await svc.record_forecast("f1", "TX", [{"h": 1}])

        ml_spans = [s for s in exporter.spans if s.name.startswith("ml.")]
        assert len(ml_spans) >= 1, f"Expected ml.* span, got: {[s.name for s in exporter.spans]}"
        span = ml_spans[0]
        assert span.attributes.get("ml.region") == "TX"

    async def test_observe_actuals_batch_creates_span(self):
        """observe_actuals_batch() should create a 'ml.observe_actuals' span."""
        exporter = _install_recording_provider()

        mock_db = AsyncMock()
        with patch("services.observation_service.ForecastObservationRepository") as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.backfill_actuals = AsyncMock(return_value=10)
            MockRepo.return_value = mock_repo

            from services.observation_service import ObservationService

            svc = ObservationService(db=mock_db)
            await svc.observe_actuals_batch("FL")

        ml_spans = [s for s in exporter.spans if s.name.startswith("ml.")]
        assert len(ml_spans) >= 1, f"Expected ml.* span, got: {[s.name for s in exporter.spans]}"
        span = ml_spans[0]
        assert span.attributes.get("ml.region") == "FL"


# ---------------------------------------------------------------------------
# ModelVersionService tracing tests
# ---------------------------------------------------------------------------


class TestModelVersionServiceTracing:
    """ModelVersionService methods should create spans with versioning attributes."""

    async def test_create_version_creates_span(self):
        """create_version() should create a 'ml.create_version' span."""
        exporter = _install_recording_provider()

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock())

        from services.model_version_service import ModelVersionService

        svc = ModelVersionService(db=mock_db)

        # Mock the execute to return a fake row
        mock_row = MagicMock()
        mock_row.id = "test-id"
        mock_row.model_name = "ensemble"
        mock_row.version_tag = "v1"
        mock_row.config = "{}"
        mock_row.metrics = "{}"
        mock_row.is_active = False
        mock_row.created_at = None
        mock_row.promoted_at = None
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        try:
            await svc.create_version("ensemble", config={}, metrics={})
        except Exception:
            pass  # DB mock may not perfectly match — we only care about span creation

        ml_spans = [s for s in exporter.spans if s.name.startswith("ml.")]
        assert len(ml_spans) >= 1, f"Expected ml.* span, got: {[s.name for s in exporter.spans]}"
        span = ml_spans[0]
        assert span.attributes.get("ml.model_name") == "ensemble"

    async def test_promote_version_creates_span(self):
        """promote_version() should create a 'ml.promote_version' span."""
        exporter = _install_recording_provider()

        mock_db = AsyncMock()
        mock_row = MagicMock()
        mock_row.id = "v-id"
        mock_row.model_name = "ensemble"
        mock_row.version_tag = "v1"
        mock_row.config = "{}"
        mock_row.metrics = "{}"
        mock_row.is_active = True
        mock_row.created_at = None
        mock_row.promoted_at = None
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        from services.model_version_service import ModelVersionService

        svc = ModelVersionService(db=mock_db)

        try:
            await svc.promote_version("v-id")
        except Exception:
            pass

        ml_spans = [s for s in exporter.spans if s.name.startswith("ml.")]
        assert len(ml_spans) >= 1, f"Expected ml.* span, got: {[s.name for s in exporter.spans]}"
