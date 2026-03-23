"""
Tests for OTLP export integration — Phase 3 of OTel distributed tracing.

Validates that OTLPSpanExporter is properly configured when an OTLP endpoint
is set, verifies the export payload structure, and confirms that the
OTEL_EXPORTER_OTLP_HEADERS env var is respected by the SDK.

These tests mock the HTTP transport layer (no real network calls) and assert
the exporter is wired into the TracerProvider pipeline correctly.
"""

from __future__ import annotations

import os

os.environ.setdefault("ENVIRONMENT", "test")

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


# ---------------------------------------------------------------------------
# OTel state reset (same pattern as test_observability.py)
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

    for instrumentor_path in (
        "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor",
        "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor",
    ):
        try:
            module_path, cls_name = instrumentor_path.rsplit(".", 1)
            import importlib

            module = importlib.import_module(module_path)
            cls = getattr(module, cls_name)
            cls().uninstrument()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Test: OTLPSpanExporter is configured when endpoint is set
# ---------------------------------------------------------------------------


class TestOTLPExporterConfiguration:
    """Verify OTLPSpanExporter is wired when OTEL_EXPORTER_OTLP_ENDPOINT is set."""

    def test_otlp_exporter_created_with_endpoint(self):
        """OTLPSpanExporter should be instantiated when endpoint is provided."""
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        import observability

        with (
            patch.object(observability, "settings") as mock_settings,
            patch.object(observability, "_instrument_fastapi"),
            patch.object(observability, "_instrument_httpx"),
            patch(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
            ) as mock_exporter_cls,
        ):
            mock_settings.otel_enabled = True
            mock_settings.otel_endpoint = "https://otlp-gateway.example.net/otlp"
            mock_settings.is_production = True

            mock_exporter_cls.return_value = MagicMock()

            from fastapi import FastAPI

            app = FastAPI()
            result = observability.init_telemetry(app)

        assert result is True
        mock_exporter_cls.assert_called_once_with(endpoint="https://otlp-gateway.example.net/otlp")

        # Verify a real TracerProvider was installed
        provider = trace.get_tracer_provider()
        assert isinstance(provider, TracerProvider)

    def test_batch_span_processor_used_with_otlp(self):
        """BatchSpanProcessor (not Simple) should wrap the OTLP exporter."""
        import observability

        mock_exporter_instance = MagicMock()

        with (
            patch.object(observability, "settings") as mock_settings,
            patch.object(observability, "_instrument_fastapi"),
            patch.object(observability, "_instrument_httpx"),
            patch(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter",
                return_value=mock_exporter_instance,
            ),
            patch("opentelemetry.sdk.trace.export.BatchSpanProcessor") as mock_batch,
        ):
            mock_settings.otel_enabled = True
            mock_settings.otel_endpoint = "https://otlp-gateway.example.net/otlp"
            mock_settings.is_production = True

            from fastapi import FastAPI

            app = FastAPI()
            observability.init_telemetry(app)

        mock_batch.assert_called_once_with(mock_exporter_instance)

    def test_service_name_set_to_rateshift_backend(self):
        """The TracerProvider resource should identify as 'rateshift-backend'."""
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        import observability

        with (
            patch.object(observability, "settings") as mock_settings,
            patch.object(observability, "_instrument_fastapi"),
            patch.object(observability, "_instrument_httpx"),
            patch(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter",
                return_value=MagicMock(),
            ),
        ):
            mock_settings.otel_enabled = True
            mock_settings.otel_endpoint = "https://otlp-gateway.example.net/otlp"
            mock_settings.is_production = True

            from fastapi import FastAPI

            app = FastAPI()
            observability.init_telemetry(app)

        provider = trace.get_tracer_provider()
        assert isinstance(provider, TracerProvider)

        resource_attrs = dict(provider.resource.attributes)
        assert resource_attrs.get("service.name") == "rateshift-backend"


# ---------------------------------------------------------------------------
# Test: OTLP headers env var is respected by SDK
# ---------------------------------------------------------------------------


class TestOTLPHeadersEnvVar:
    """Verify that OTEL_EXPORTER_OTLP_HEADERS is respected by the OTel SDK."""

    def test_otlp_exporter_respects_headers_env(self):
        """OTLPSpanExporter reads OTEL_EXPORTER_OTLP_HEADERS from env automatically.

        The Python OTel SDK's OTLPSpanExporter constructor reads the
        OTEL_EXPORTER_OTLP_HEADERS env var when no `headers` kwarg is passed.
        This test verifies that our observability.py does NOT override headers,
        allowing the SDK's native env var reading to work.
        """
        # Inspect the source to confirm we only pass `endpoint`, not `headers`
        import inspect

        import observability

        source = inspect.getsource(observability._configure_tracer_provider)

        # Verify OTLPSpanExporter is called with endpoint= only
        assert "OTLPSpanExporter(endpoint=" in source
        # Verify we do NOT pass headers= (SDK reads from env automatically)
        assert "headers=" not in source.split("OTLPSpanExporter")[1].split(")")[0]


# ---------------------------------------------------------------------------
# Test: Span export payload structure
# ---------------------------------------------------------------------------


class TestSpanExportPayload:
    """Verify that spans have the expected structure when exported."""

    def test_exported_span_has_required_fields(self):
        """Spans created via get_tracer() should have name, trace_id, span_id."""
        from opentelemetry import trace
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            SimpleSpanProcessor,
            SpanExporter,
            SpanExportResult,
        )

        class _InMemoryExporter(SpanExporter):
            def __init__(self):
                self.spans = []

            def export(self, spans):
                self.spans.extend(spans)
                return SpanExportResult.SUCCESS

            def shutdown(self):
                pass

        exporter = _InMemoryExporter()
        resource = Resource.create({SERVICE_NAME: "rateshift-backend"})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Create a span using the same pattern services use
        tracer = trace.get_tracer("test.otlp_export")
        with tracer.start_as_current_span("test.operation") as span:
            span.set_attribute("test.attr", "value")

        assert len(exporter.spans) == 1
        exported = exporter.spans[0]

        # Required fields for OTLP export
        assert exported.name == "test.operation"
        assert exported.context.trace_id != 0
        assert exported.context.span_id != 0
        assert exported.resource.attributes.get("service.name") == "rateshift-backend"
        assert exported.attributes.get("test.attr") == "value"

    def test_nested_spans_share_trace_id(self):
        """Child spans must share the parent's trace_id for distributed tracing."""
        from opentelemetry import trace
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            SimpleSpanProcessor,
            SpanExporter,
            SpanExportResult,
        )

        class _InMemoryExporter(SpanExporter):
            def __init__(self):
                self.spans = []

            def export(self, spans):
                self.spans.extend(spans)
                return SpanExportResult.SUCCESS

            def shutdown(self):
                pass

        exporter = _InMemoryExporter()
        provider = TracerProvider(resource=Resource.create({SERVICE_NAME: "rateshift-backend"}))
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        tracer = trace.get_tracer("test.nested")
        with tracer.start_as_current_span("parent.operation"):
            with tracer.start_as_current_span("child.operation"):
                pass

        assert len(exporter.spans) == 2
        parent = next(s for s in exporter.spans if s.name == "parent.operation")
        child = next(s for s in exporter.spans if s.name == "child.operation")

        # Both spans share the same trace_id
        assert parent.context.trace_id == child.context.trace_id
        # Child has parent's span_id as its parent
        assert child.parent.span_id == parent.context.span_id

    def test_error_span_records_exception(self):
        """Spans recording errors should include exception details for Tempo."""
        from opentelemetry import trace
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            SimpleSpanProcessor,
            SpanExporter,
            SpanExportResult,
        )
        from opentelemetry.trace import StatusCode

        class _InMemoryExporter(SpanExporter):
            def __init__(self):
                self.spans = []

            def export(self, spans):
                self.spans.extend(spans)
                return SpanExportResult.SUCCESS

            def shutdown(self):
                pass

        exporter = _InMemoryExporter()
        provider = TracerProvider(resource=Resource.create({SERVICE_NAME: "rateshift-backend"}))
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        tracer = trace.get_tracer("test.errors")
        try:
            with tracer.start_as_current_span("failing.operation") as span:
                span.set_status(StatusCode.ERROR, "test error")
                span.record_exception(ValueError("something went wrong"))
                raise ValueError("something went wrong")
        except ValueError:
            pass

        assert len(exporter.spans) == 1
        exported = exporter.spans[0]
        assert exported.status.status_code == StatusCode.ERROR
        # Exception events should be recorded
        exception_events = [e for e in exported.events if e.name == "exception"]
        assert len(exception_events) >= 1
