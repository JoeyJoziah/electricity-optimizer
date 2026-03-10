"""
OpenTelemetry Observability Integration
========================================

Provides opt-in distributed tracing for the FastAPI backend.

Activation
----------
Set ``OTEL_ENABLED=true`` in the environment to activate instrumentation.

Exporter selection
------------------
1. If ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set, spans are exported over
   OTLP/HTTP (e.g. to Jaeger, Grafana Tempo, or any OpenTelemetry Collector).
2. If ``OTEL_ENABLED=true`` but no endpoint is configured:
   - Development/test environments: ``ConsoleSpanExporter`` (stdout).
   - Production: ``NoOpSpanExporter`` (silently discard — avoids log spam
     while still allowing instrumentation code paths to be exercised).
3. If ``OTEL_ENABLED=false`` (default): nothing is initialised, zero overhead.

Usage
-----
    from observability import init_telemetry
    init_telemetry(app)           # call once during app construction
    get_tracer()                  # obtain a tracer anywhere in the codebase

Custom span attributes
----------------------
``OTelMiddleware`` injects ``user_id`` and ``request_id`` as span attributes
on every request that passes through the FastAPI middleware stack.  These
attributes supplement what ``opentelemetry-instrumentation-fastapi`` records
automatically (HTTP method, route, status code, etc.).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import structlog

from config.settings import settings

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level tracer reference
# A no-op tracer is used before init_telemetry() is called, which means
# instrumented code is safe to import/call even when OTEL is disabled.
# ---------------------------------------------------------------------------

_SERVICE_NAME = "rateshift-backend"


def get_tracer(name: str = __name__):
    """Return an OTel tracer.  Returns a no-op tracer when OTEL is disabled."""
    from opentelemetry import trace

    return trace.get_tracer(name)


# ---------------------------------------------------------------------------
# Public initialisation function
# ---------------------------------------------------------------------------


def init_telemetry(app: "FastAPI") -> bool:
    """Initialise OpenTelemetry instrumentation on *app*.

    Parameters
    ----------
    app:
        The FastAPI application instance to instrument.

    Returns
    -------
    bool
        ``True`` when instrumentation was activated, ``False`` when it was
        skipped (``OTEL_ENABLED`` is false or initialisation failed).

    The function is idempotent: calling it more than once is safe — the
    TracerProvider is only set once; subsequent calls are no-ops.
    """
    if not settings.otel_enabled:
        logger.debug("otel_disabled", reason="OTEL_ENABLED is not true")
        return False

    try:
        return _configure_tracer_provider(
            endpoint=settings.otel_endpoint,
            is_production=settings.is_production,
        )
    except Exception as exc:
        # Instrumentation must never crash the application.
        logger.warning("otel_init_failed", error=str(exc))
        return False


def _configure_tracer_provider(
    endpoint: Optional[str],
    is_production: bool,
) -> bool:
    """Wire up the TracerProvider, exporter and all auto-instrumentors.

    This is intentionally separated from ``init_telemetry`` so that tests can
    call it directly with controlled arguments without touching ``settings``.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

    # ------------------------------------------------------------------
    # Guard: only initialise once per process.
    # The SDK sets the global provider to a real TracerProvider on first
    # call; subsequent calls would stack processors, so we bail out if
    # the provider is already a TracerProvider (not the default no-op).
    # ------------------------------------------------------------------
    current_provider = trace.get_tracer_provider()
    if isinstance(current_provider, TracerProvider):
        logger.debug("otel_already_initialized")
        return True

    # ------------------------------------------------------------------
    # Resource — identifies this service in the backend of an OTel
    # collector (Jaeger, Tempo, …).
    # ------------------------------------------------------------------
    resource = Resource.create({SERVICE_NAME: _SERVICE_NAME})

    provider = TracerProvider(resource=resource)

    # ------------------------------------------------------------------
    # Exporter selection
    # ------------------------------------------------------------------
    if endpoint:
        # OTLP/HTTP exporter — sends to a real collector.
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        exporter = OTLPSpanExporter(endpoint=endpoint)
        # BatchSpanProcessor for production-grade throughput.
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("otel_otlp_exporter_configured", endpoint=endpoint)
    elif not is_production:
        # No endpoint in a non-production environment: print to stdout so
        # developers can see spans without running a collector.
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        exporter = ConsoleSpanExporter()
        # SimpleSpanProcessor for immediate, synchronous export (suitable
        # for low-volume dev/test usage).
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        logger.info("otel_console_exporter_configured")
    else:
        # Production without an endpoint: use a minimal no-op exporter so
        # that instrumentation code paths work without emitting anything.
        # ``NoOpSpanExporter`` was removed from the SDK in 1.x — we define
        # a minimal inline implementation that satisfies the SpanExporter
        # interface and silently discards every span.
        from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

        class _SilentSpanExporter(SpanExporter):
            """Silently discard spans — used in production without a collector."""

            def export(self, spans):  # type: ignore[override]
                return SpanExportResult.SUCCESS

            def shutdown(self) -> None:
                pass

        exporter = _SilentSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("otel_silent_exporter_configured")

    # Register as the global provider — all ``get_tracer()`` calls resolve here.
    trace.set_tracer_provider(provider)

    # ------------------------------------------------------------------
    # Auto-instrumentors
    # ------------------------------------------------------------------
    _instrument_fastapi(app=None)  # FastAPI instrumentor is wired next via app
    _instrument_httpx()
    logger.info("otel_instrumentation_complete", service=_SERVICE_NAME)

    return True


def _instrument_fastapi(app: Optional["FastAPI"]) -> None:
    """Instrument the FastAPI application.

    The FastAPI instrumentor patches the ASGI call stack automatically once
    ``instrument_app()`` is called.  If *app* is None we still call
    ``instrument()`` so that the instrumentor is ready to wrap any app
    created after this point.
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        if app is not None:
            FastAPIInstrumentor.instrument_app(
                app,
                server_request_hook=_server_request_hook,
                client_request_hook=_client_request_hook,
            )
        else:
            FastAPIInstrumentor().instrument(
                server_request_hook=_server_request_hook,
                client_request_hook=_client_request_hook,
            )
        logger.debug("otel_fastapi_instrumented")
    except Exception as exc:
        logger.warning("otel_fastapi_instrument_failed", error=str(exc))


def instrument_fastapi_app(app: "FastAPI") -> None:
    """Instrument a specific FastAPI *app* instance.

    Call this from ``create_app()`` after ``init_telemetry()`` has already
    been invoked once.  It is safe to call even when OTEL is disabled — the
    function checks the global provider before doing any work.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        return  # OTEL not active

    _instrument_fastapi(app)


def instrument_sqlalchemy_engine(engine: "AsyncEngine") -> None:
    """Instrument an existing SQLAlchemy *engine* for tracing.

    Call this after the engine is created (e.g. in ``DatabaseManager``).
    Safe to call when OTEL is disabled — it checks the global provider.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        return  # OTEL not active

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        # The SQLAlchemy instrumentation supports both sync and async engines.
        SQLAlchemyInstrumentor().instrument(engine=engine)
        logger.debug("otel_sqlalchemy_instrumented")
    except Exception as exc:
        logger.warning("otel_sqlalchemy_instrument_failed", error=str(exc))


def _instrument_httpx() -> None:
    """Instrument the httpx client library for outbound HTTP tracing."""
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        logger.debug("otel_httpx_instrumented")
    except Exception as exc:
        logger.warning("otel_httpx_instrument_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Request hooks — add user_id and request_id to every server-side span
# ---------------------------------------------------------------------------


def _server_request_hook(span, scope: dict) -> None:
    """Enrich the root server span with ``user_id`` and ``request_id``.

    Called by the FastAPI instrumentor at the start of every request.
    ``scope`` is the ASGI connection scope dict which carries headers and
    any state populated by earlier middleware (e.g. TracingMiddleware).
    """
    if span is None or not span.is_recording():
        return

    # Extract request_id from the ASGI state set by TracingMiddleware.
    # ``scope["state"]`` is a Starlette State object; it may not be present
    # on all scopes (e.g. WebSocket) so we guard with getattr.
    state = scope.get("state")
    if state is not None:
        request_id = getattr(state, "trace_id", None)
        if request_id:
            span.set_attribute("http.request_id", request_id)

    # Extract user information from the ASGI state if available.
    # ``request.state.user_id`` is set by auth middleware / dependencies
    # when the request carries a valid session token.
    if state is not None:
        user_id = getattr(state, "user_id", None)
        if user_id:
            span.set_attribute("app.user_id", str(user_id))


def _client_request_hook(span, scope: dict) -> None:
    """Hook for client-side spans (not used currently; reserved for future enrichment)."""
    pass
