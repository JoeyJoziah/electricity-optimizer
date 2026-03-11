"""
Tests for backend/lib/tracing.py — the traced() helper.

RED phase — these tests define the contract for the traced() helper before
any implementation exists.  All tests should FAIL until Task 1.2 (GREEN).

The traced() helper must:
1. Create an OTel span with the given operation name
2. Set arbitrary span attributes
3. Record exceptions and set ERROR status on failure
4. Re-raise the original exception (never swallow)
5. Work as both a context manager (sync) and an async context manager
6. Be zero-cost when OTEL is disabled (no-op tracer path)
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


def _install_recording_provider():
    """Install a real TracerProvider so spans are recorded (not no-ops)."""
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
    resource = Resource.create({SERVICE_NAME: "test"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return exporter


# ---------------------------------------------------------------------------
# Tests: traced() as async context manager
# ---------------------------------------------------------------------------


class TestTracedAsyncContextManager:
    """traced() should work as an async context manager that creates spans."""

    @pytest.mark.asyncio
    async def test_creates_span_with_operation_name(self):
        """traced() creates a span named after the operation."""
        exporter = _install_recording_provider()

        from lib.tracing import traced

        async with traced("ml.predict"):
            pass

        assert len(exporter.spans) == 1
        assert exporter.spans[0].name == "ml.predict"

    @pytest.mark.asyncio
    async def test_sets_custom_attributes(self):
        """traced() accepts attributes dict and sets them on the span."""
        exporter = _install_recording_provider()

        from lib.tracing import traced

        async with traced("price.fetch", attributes={"price.region": "NY", "price.source": "eia"}):
            pass

        span = exporter.spans[0]
        assert span.attributes["price.region"] == "NY"
        assert span.attributes["price.source"] == "eia"

    @pytest.mark.asyncio
    async def test_records_exception_and_sets_error_status(self):
        """On exception, traced() records the exception and sets ERROR status."""
        exporter = _install_recording_provider()

        from lib.tracing import traced
        from opentelemetry.trace import StatusCode

        with pytest.raises(ValueError, match="boom"):
            async with traced("failing.op"):
                raise ValueError("boom")

        span = exporter.spans[0]
        assert span.status.status_code == StatusCode.ERROR
        assert "boom" in span.status.description
        # Exception event should be recorded
        events = span.events
        assert any(e.name == "exception" for e in events)

    @pytest.mark.asyncio
    async def test_reraises_original_exception(self):
        """traced() must re-raise the original exception, not wrap it."""
        _install_recording_provider()

        from lib.tracing import traced

        with pytest.raises(RuntimeError, match="original"):
            async with traced("reraise.test"):
                raise RuntimeError("original")

    @pytest.mark.asyncio
    async def test_span_has_ok_status_on_success(self):
        """On success, span status should be OK (or UNSET)."""
        exporter = _install_recording_provider()

        from lib.tracing import traced
        from opentelemetry.trace import StatusCode

        async with traced("success.op"):
            pass

        span = exporter.spans[0]
        assert span.status.status_code in (StatusCode.OK, StatusCode.UNSET)

    @pytest.mark.asyncio
    async def test_yields_span_object(self):
        """traced() yields the active span so callers can add attributes dynamically."""
        exporter = _install_recording_provider()

        from lib.tracing import traced

        async with traced("dynamic.attrs") as span:
            span.set_attribute("dynamic.key", "dynamic_value")

        assert exporter.spans[0].attributes["dynamic.key"] == "dynamic_value"


# ---------------------------------------------------------------------------
# Tests: traced() as sync context manager
# ---------------------------------------------------------------------------


class TestTracedSyncContextManager:
    """traced() should also work as a sync context manager."""

    def test_creates_span_sync(self):
        """traced() works in a 'with' block (non-async)."""
        exporter = _install_recording_provider()

        from lib.tracing import traced

        with traced("sync.op"):
            pass

        assert len(exporter.spans) == 1
        assert exporter.spans[0].name == "sync.op"

    def test_records_exception_sync(self):
        """Exception recording works in sync mode too."""
        exporter = _install_recording_provider()

        from lib.tracing import traced
        from opentelemetry.trace import StatusCode

        with pytest.raises(TypeError, match="bad type"):
            with traced("sync.fail"):
                raise TypeError("bad type")

        span = exporter.spans[0]
        assert span.status.status_code == StatusCode.ERROR


# ---------------------------------------------------------------------------
# Tests: zero-cost when OTEL disabled
# ---------------------------------------------------------------------------


class TestTracedZeroCost:
    """When OTEL is disabled (no-op tracer), traced() must not crash or add overhead."""

    @pytest.mark.asyncio
    async def test_noop_tracer_does_not_crash(self):
        """traced() works with the default no-op tracer (no TracerProvider set)."""
        # Do NOT install a recording provider — use the default no-op.
        from lib.tracing import traced

        async with traced("noop.test", attributes={"key": "value"}):
            pass
        # No assertion on spans — just verify no exception was raised.

    def test_noop_tracer_sync_does_not_crash(self):
        """Sync traced() also works with the no-op tracer."""
        from lib.tracing import traced

        with traced("noop.sync"):
            pass

    @pytest.mark.asyncio
    async def test_noop_tracer_exception_passthrough(self):
        """Exceptions pass through even with no-op tracer."""
        from lib.tracing import traced

        with pytest.raises(ValueError, match="pass through"):
            async with traced("noop.error"):
                raise ValueError("pass through")


# ---------------------------------------------------------------------------
# Tests: traced() with custom tracer name
# ---------------------------------------------------------------------------


class TestTracedCustomTracer:
    """traced() should accept an optional tracer_name parameter."""

    @pytest.mark.asyncio
    async def test_custom_tracer_name(self):
        """A custom tracer_name is passed to get_tracer()."""
        _install_recording_provider()

        from lib.tracing import traced

        async with traced("custom.op", tracer_name="my.service"):
            pass
        # Should not raise — tracer_name is accepted.

    @pytest.mark.asyncio
    async def test_default_tracer_name(self):
        """Without tracer_name, a sensible default is used."""
        _install_recording_provider()

        from lib.tracing import traced

        async with traced("default.tracer"):
            pass
        # Should not raise.
