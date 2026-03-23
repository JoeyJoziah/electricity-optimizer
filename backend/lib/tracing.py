"""
Tracing Helpers — thin wrapper around OpenTelemetry spans.

Provides ``traced()``, a dual-mode context manager (sync + async) that:
- Creates a span with a given operation name
- Sets arbitrary span attributes
- Records exceptions and sets ERROR status on failure
- Re-raises the original exception (never swallows)
- Is zero-cost when OTEL_ENABLED=false (no-op tracer path)

Usage
-----
    from lib.tracing import traced

    # Async
    async with traced("ml.predict", attributes={"ml.region": "NY"}) as span:
        result = await model.predict(...)
        span.set_attribute("ml.latency_ms", elapsed)

    # Sync
    with traced("stripe.create_checkout") as span:
        session = stripe.create(...)

Span naming convention: ``{service}.{operation}``
"""

from __future__ import annotations

from typing import Any

from observability import get_tracer


class traced:
    """Dual-mode context manager that creates and manages an OTel span.

    Works as both ``async with traced(...)`` and ``with traced(...)``.
    """

    def __init__(
        self,
        operation: str,
        *,
        attributes: dict[str, Any] | None = None,
        tracer_name: str | None = None,
    ) -> None:
        self._operation = operation
        self._attributes = attributes or {}
        self._tracer_name = tracer_name or "rateshift.tracing"

    # --- Async context manager ---

    async def __aenter__(self):
        tracer = get_tracer(self._tracer_name)
        self._span = tracer.start_span(self._operation)
        self._token = _set_span_in_context(self._span)
        for key, value in self._attributes.items():
            self._span.set_attribute(key, value)
        return self._span

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        from opentelemetry.trace import StatusCode

        try:
            if exc_val is not None:
                self._span.set_status(StatusCode.ERROR, str(exc_val))
                self._span.record_exception(exc_val)
            else:
                self._span.set_status(StatusCode.OK)
        finally:
            self._span.end()
            _detach_context(self._token)
        return False  # re-raise exceptions

    # --- Sync context manager ---

    def __enter__(self):
        tracer = get_tracer(self._tracer_name)
        self._span = tracer.start_span(self._operation)
        self._token = _set_span_in_context(self._span)
        for key, value in self._attributes.items():
            self._span.set_attribute(key, value)
        return self._span

    def __exit__(self, exc_type, exc_val, exc_tb):
        from opentelemetry.trace import StatusCode

        try:
            if exc_val is not None:
                self._span.set_status(StatusCode.ERROR, str(exc_val))
                self._span.record_exception(exc_val)
            else:
                self._span.set_status(StatusCode.OK)
        finally:
            self._span.end()
            _detach_context(self._token)
        return False  # re-raise exceptions


def _set_span_in_context(span):
    """Attach the span to the current OTel context and return the token."""
    from opentelemetry import context, trace

    ctx = trace.set_span_in_context(span)
    return context.attach(ctx)


def _detach_context(token):
    """Detach the span from the OTel context."""
    from opentelemetry import context

    context.detach(token)
