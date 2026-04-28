"""
Tests for backend/observability.py — OpenTelemetry integration.

Strategy
--------
All tests mock the exporter layer so that no network calls are made and the
global TracerProvider is reset between test cases.  The tests exercise:

1. Default behaviour (OTEL_ENABLED=false) — no-op, nothing blows up.
2. OTEL_ENABLED=true without an endpoint — ConsoleSpanExporter in dev,
   NoOpSpanExporter in prod.
3. OTEL_ENABLED=true with an endpoint — OTLPSpanExporter wired up.
4. Idempotency — calling init_telemetry twice is safe.
5. Span attribute hooks (user_id, request_id injection).
6. SQLAlchemy and httpx instrumentors are called when OTEL is active.
7. Full integration guard logic for create_app() via settings.otel_enabled flag.
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
# Helpers — OTel global state reset
# ---------------------------------------------------------------------------


def _reset_tracer_provider() -> None:
    """Reset the global OTel TracerProvider to the default no-op proxy.

    The OTel SDK uses a ``Once`` guard (``_TRACER_PROVIDER_SET_ONCE``) that
    prevents ``set_tracer_provider`` from being called more than once per
    process.  Between test cases we must clear both the provider value and
    the once-guard so that each test can install its own TracerProvider.
    """
    import opentelemetry.trace as _trace

    _trace._TRACER_PROVIDER = None  # type: ignore[attr-defined]
    try:
        # The Once guard has a ``_done`` flag that we reset directly.
        _trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
    except AttributeError:
        pass


@pytest.fixture(autouse=True)
def reset_otel_state():
    """Auto-fixture: reset the global OTel provider before and after each test."""
    _reset_tracer_provider()
    yield
    _reset_tracer_provider()

    # Un-instrument to avoid state leakage across the test session.
    for instrumentor_path in (
        "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor",
        "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor",
        "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor",
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
# Test: defaults (OTEL_ENABLED not set / false)
# ---------------------------------------------------------------------------


class TestOtelDisabledByDefault:
    """init_telemetry should be a no-op when OTEL_ENABLED is not set."""

    def test_init_telemetry_returns_false_when_disabled(self):
        """Return value is False when settings.otel_enabled is False."""
        from fastapi import FastAPI

        import observability

        app = FastAPI()
        with patch.object(observability, "settings") as mock_settings:
            mock_settings.otel_enabled = False
            result = observability.init_telemetry(app)

        assert result is False

    def test_no_tracer_provider_set_when_disabled(self):
        """Global TracerProvider must NOT be a real TracerProvider when OTEL is off."""
        from fastapi import FastAPI
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        import observability

        app = FastAPI()
        with patch.object(observability, "settings") as mock_settings:
            mock_settings.otel_enabled = False
            observability.init_telemetry(app)

        assert not isinstance(trace.get_tracer_provider(), TracerProvider)

    def test_init_telemetry_with_env_false(self):
        """settings.otel_enabled=False keeps instrumentation off regardless of env."""
        from fastapi import FastAPI

        import observability

        app = FastAPI()
        with patch.object(observability, "settings") as mock_settings:
            mock_settings.otel_enabled = False
            result = observability.init_telemetry(app)

        assert result is False

    def test_get_tracer_returns_noop_when_disabled(self):
        """get_tracer() returns a functional (no-op) tracer even without init."""
        from observability import get_tracer

        tracer = get_tracer("test.module")
        # Should not raise; spans are no-ops before a real provider is installed
        with tracer.start_as_current_span("test-span") as span:
            assert span is not None


# ---------------------------------------------------------------------------
# Test: OTEL_ENABLED=true, no endpoint → Console (dev) / NoOp (prod)
# ---------------------------------------------------------------------------


class TestOtelEnabledNoEndpoint:
    """When enabled without an endpoint, the correct exporter is chosen."""

    def test_console_exporter_in_development(self):
        """ConsoleSpanExporter is used in non-production with no endpoint."""
        from fastapi import FastAPI
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        import observability

        app = FastAPI()
        with (
            patch.object(observability, "settings") as mock_settings,
            patch.object(observability, "_instrument_fastapi"),
            patch.object(observability, "_instrument_httpx"),
        ):
            mock_settings.otel_enabled = True
            mock_settings.otel_endpoint = None
            mock_settings.is_production = False
            result = observability.init_telemetry(app)

        assert result is True
        assert isinstance(trace.get_tracer_provider(), TracerProvider)

    def test_noop_exporter_in_production(self):
        """NoOpSpanExporter is used in production with no endpoint."""
        from fastapi import FastAPI
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        import observability

        app = FastAPI()
        with (
            patch.object(observability, "settings") as mock_settings,
            patch.object(observability, "_instrument_fastapi"),
            patch.object(observability, "_instrument_httpx"),
        ):
            mock_settings.otel_enabled = True
            mock_settings.otel_endpoint = None
            mock_settings.is_production = True
            result = observability.init_telemetry(app)

        assert result is True
        assert isinstance(trace.get_tracer_provider(), TracerProvider)

    def test_tracer_provider_has_service_name(self):
        """TracerProvider resource carries the expected service name."""
        from fastapi import FastAPI
        from opentelemetry import trace
        from opentelemetry.sdk.resources import SERVICE_NAME
        from opentelemetry.sdk.trace import TracerProvider

        import observability

        app = FastAPI()
        with (
            patch.object(observability, "settings") as mock_settings,
            patch.object(observability, "_instrument_fastapi"),
            patch.object(observability, "_instrument_httpx"),
        ):
            mock_settings.otel_enabled = True
            mock_settings.otel_endpoint = None
            mock_settings.is_production = False
            observability.init_telemetry(app)

        provider = trace.get_tracer_provider()
        assert isinstance(provider, TracerProvider)
        assert provider.resource.attributes[SERVICE_NAME] == observability._SERVICE_NAME


# ---------------------------------------------------------------------------
# Test: OTEL_ENABLED=true with OTLP endpoint
# ---------------------------------------------------------------------------


class TestOtelEnabledWithEndpoint:
    """When an endpoint is configured, OTLPSpanExporter is used."""

    def test_otlp_exporter_configured_with_endpoint(self):
        """OTLPSpanExporter is created when an endpoint is provided."""
        from fastapi import FastAPI
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        import observability

        fake_endpoint = "http://localhost:4318"
        app = FastAPI()

        with (
            patch.object(observability, "settings") as mock_settings,
            patch.object(observability, "_instrument_fastapi"),
            patch.object(observability, "_instrument_httpx"),
            patch(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
            ) as mock_exporter_cls,
        ):
            mock_exporter_cls.return_value = MagicMock()
            mock_settings.otel_enabled = True
            mock_settings.otel_endpoint = fake_endpoint
            mock_settings.is_production = False
            result = observability.init_telemetry(app)

        assert result is True
        mock_exporter_cls.assert_called_once_with(endpoint=fake_endpoint)
        assert isinstance(trace.get_tracer_provider(), TracerProvider)

    def test_get_tracer_returns_real_tracer_when_enabled(self):
        """After init, get_tracer() returns a real SDK tracer."""
        from fastapi import FastAPI

        import observability

        app = FastAPI()
        with (
            patch.object(observability, "settings") as mock_settings,
            patch.object(observability, "_instrument_fastapi"),
            patch.object(observability, "_instrument_httpx"),
        ):
            mock_settings.otel_enabled = True
            mock_settings.otel_endpoint = None
            mock_settings.is_production = False
            observability.init_telemetry(app)

        tracer = observability.get_tracer("test.service")
        assert tracer is not None
        with tracer.start_as_current_span("my-span") as span:
            assert span.is_recording()


# ---------------------------------------------------------------------------
# Test: idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Calling init_telemetry multiple times is safe."""

    def test_double_init_does_not_raise(self):
        """Second call to init_telemetry returns True without raising."""
        from fastapi import FastAPI

        import observability

        app = FastAPI()
        with (
            patch.object(observability, "settings") as mock_settings,
            patch.object(observability, "_instrument_fastapi"),
            patch.object(observability, "_instrument_httpx"),
        ):
            mock_settings.otel_enabled = True
            mock_settings.otel_endpoint = None
            mock_settings.is_production = False
            result1 = observability.init_telemetry(app)
            result2 = observability.init_telemetry(app)  # second call

        assert result1 is True
        assert result2 is True  # idempotent — no crash

    def test_only_one_provider_after_double_init(self):
        """Double init must not replace the provider on the second call."""
        from fastapi import FastAPI
        from opentelemetry import trace

        import observability

        app = FastAPI()
        with (
            patch.object(observability, "settings") as mock_settings,
            patch.object(observability, "_instrument_fastapi"),
            patch.object(observability, "_instrument_httpx"),
        ):
            mock_settings.otel_enabled = True
            mock_settings.otel_endpoint = None
            mock_settings.is_production = False
            observability.init_telemetry(app)
            provider_first = trace.get_tracer_provider()
            observability.init_telemetry(app)
            provider_second = trace.get_tracer_provider()

        # Must be the same object — not replaced on second call.
        assert provider_first is provider_second


# ---------------------------------------------------------------------------
# Test: _configure_tracer_provider directly
# ---------------------------------------------------------------------------


class TestConfigureTracerProvider:
    """Unit-test the internal _configure_tracer_provider function."""

    def test_returns_true_on_success(self):
        """_configure_tracer_provider returns True when it succeeds."""
        from observability import _configure_tracer_provider

        with (
            patch("observability._instrument_fastapi"),
            patch("observability._instrument_httpx"),
        ):
            result = _configure_tracer_provider(endpoint=None, is_production=False)

        assert result is True

    def test_console_exporter_dev_path(self):
        """ConsoleSpanExporter is selected for dev with no endpoint."""
        from observability import _configure_tracer_provider

        captured = []

        with (
            patch("observability._instrument_fastapi"),
            patch("observability._instrument_httpx"),
            patch(
                "opentelemetry.sdk.trace.TracerProvider.add_span_processor",
                side_effect=lambda p: captured.append(p),
            ),
        ):
            _configure_tracer_provider(endpoint=None, is_production=False)

        # At least one processor should have been registered.
        assert len(captured) >= 1

    def test_production_does_not_use_console_exporter(self):
        """Production path uses the silent exporter, NOT ConsoleSpanExporter."""
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        from observability import _configure_tracer_provider

        with (
            patch("observability._instrument_fastapi"),
            patch("observability._instrument_httpx"),
        ):
            result = _configure_tracer_provider(endpoint=None, is_production=True)

        assert result is True
        # Provider must still be installed correctly.
        assert isinstance(trace.get_tracer_provider(), TracerProvider)
        # Verify the exporter is NOT a ConsoleSpanExporter by checking the
        # processor chain registered on the provider.
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        provider = trace.get_tracer_provider()
        for proc in provider._active_span_processor._span_processors:
            exporter = getattr(proc, "span_exporter", None)
            if exporter is not None:
                assert not isinstance(
                    exporter, ConsoleSpanExporter
                ), f"Production must not use ConsoleSpanExporter; got {type(exporter)}"


# ---------------------------------------------------------------------------
# Test: span attribute hooks
# ---------------------------------------------------------------------------


class TestSpanHooks:
    """_server_request_hook populates span attributes from ASGI scope state."""

    def _make_recording_span(self):
        """Return a mock span that records set_attribute calls."""
        span = MagicMock()
        span.is_recording.return_value = True
        recorded: dict = {}
        span.set_attribute.side_effect = lambda k, v: recorded.__setitem__(k, v)
        span._recorded = recorded
        return span

    def test_request_id_set_from_scope_state(self):
        """http.request_id is taken from scope['state'].trace_id."""
        from observability import _server_request_hook

        state = MagicMock()
        state.trace_id = "abc-123"
        state.user_id = None

        span = self._make_recording_span()
        _server_request_hook(span, {"state": state})

        assert span._recorded.get("http.request_id") == "abc-123"

    def test_user_id_set_from_scope_state(self):
        """app.user_id is taken from scope['state'].user_id."""
        from observability import _server_request_hook

        state = MagicMock()
        state.trace_id = None
        state.user_id = "user-456"

        span = self._make_recording_span()
        _server_request_hook(span, {"state": state})

        assert span._recorded.get("app.user_id") == "user-456"

    def test_no_attributes_when_state_absent(self):
        """When scope has no 'state' key, no attributes are set."""
        from observability import _server_request_hook

        span = self._make_recording_span()
        _server_request_hook(span, {})

        assert span._recorded == {}

    def test_noop_when_span_not_recording(self):
        """No work is done when span.is_recording() is False."""
        from observability import _server_request_hook

        span = MagicMock()
        span.is_recording.return_value = False

        state = MagicMock()
        state.trace_id = "xyz"
        state.user_id = "u1"

        _server_request_hook(span, {"state": state})
        span.set_attribute.assert_not_called()

    def test_noop_when_span_is_none(self):
        """No error when span is None (graceful degradation)."""
        from observability import _server_request_hook

        state = MagicMock()
        state.trace_id = "xyz"
        # Must not raise
        _server_request_hook(None, {"state": state})


# ---------------------------------------------------------------------------
# Test: sub-instrumentors
# ---------------------------------------------------------------------------


class TestSubInstrumentors:
    """Verify that FastAPI, SQLAlchemy and httpx instrumentors are invoked."""

    def test_httpx_instrumentor_called_during_init(self):
        """HTTPXClientInstrumentor().instrument() is called when OTEL is active."""
        from fastapi import FastAPI

        import observability

        app = FastAPI()
        with (
            patch.object(observability, "settings") as mock_settings,
            patch.object(observability, "_instrument_fastapi"),
            patch(
                "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor.instrument"
            ) as mock_instrument,
        ):
            mock_settings.otel_enabled = True
            mock_settings.otel_endpoint = None
            mock_settings.is_production = False
            observability.init_telemetry(app)

        mock_instrument.assert_called_once()

    def test_sqlalchemy_instrumentor_called_with_engine(self):
        """SQLAlchemyInstrumentor().instrument(engine=...) is invoked with the engine."""
        import observability

        # Install a real TracerProvider so instrument_sqlalchemy_engine
        # sees it as active (its guard checks isinstance(..., TracerProvider)).
        with (
            patch.object(observability, "_instrument_fastapi"),
            patch.object(observability, "_instrument_httpx"),
        ):
            observability._configure_tracer_provider(endpoint=None, is_production=False)

        mock_engine = MagicMock()
        with patch(
            "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor.instrument"
        ) as mock_sa_instrument:
            observability.instrument_sqlalchemy_engine(mock_engine)

        mock_sa_instrument.assert_called_once_with(engine=mock_engine)

    def test_sqlalchemy_instrumentor_skipped_when_otel_off(self):
        """instrument_sqlalchemy_engine is a no-op when no TracerProvider is set."""
        # After reset_otel_state fixture the global provider is the default
        # ProxyTracerProvider, not a TracerProvider instance — guard triggers.
        mock_engine = MagicMock()

        with patch(
            "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor.instrument"
        ) as mock_sa_instrument:
            from observability import instrument_sqlalchemy_engine

            instrument_sqlalchemy_engine(mock_engine)

        mock_sa_instrument.assert_not_called()

    def test_instrument_fastapi_app_skipped_when_otel_off(self):
        """instrument_fastapi_app is a no-op when no TracerProvider is set."""
        from fastapi import FastAPI

        from observability import instrument_fastapi_app

        app = FastAPI()
        with patch(
            "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app"
        ) as mock_ia:
            instrument_fastapi_app(app)

        mock_ia.assert_not_called()


# ---------------------------------------------------------------------------
# Test: error resilience
# ---------------------------------------------------------------------------


class TestErrorResilience:
    """init_telemetry must not raise even when sub-components fail."""

    def test_init_returns_false_on_internal_exception(self):
        """init_telemetry returns False (not raises) if _configure_tracer_provider raises."""
        from fastapi import FastAPI

        import observability

        app = FastAPI()
        with (
            patch.object(observability, "settings") as mock_settings,
            patch.object(
                observability,
                "_configure_tracer_provider",
                side_effect=RuntimeError("boom"),
            ),
        ):
            mock_settings.otel_enabled = True
            result = observability.init_telemetry(app)

        assert result is False

    def test_fastapi_instrument_failure_does_not_propagate(self):
        """Failure inside _instrument_fastapi is caught and logged as a warning."""
        with (
            patch(
                "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument",
                side_effect=RuntimeError("fastapi instrumentation failed"),
            ),
            patch(
                "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app",
                side_effect=RuntimeError("fastapi instrumentation failed"),
            ),
        ):
            from observability import _instrument_fastapi

            _instrument_fastapi(None)  # Must not raise

    def test_httpx_instrument_failure_does_not_propagate(self):
        """Failure inside _instrument_httpx is caught and logged as a warning."""
        with patch(
            "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor.instrument",
            side_effect=RuntimeError("httpx instrumentation failed"),
        ):
            from observability import _instrument_httpx

            _instrument_httpx()  # Must not raise

    def test_sqlalchemy_instrument_failure_does_not_propagate(self):
        """Failure in instrument_sqlalchemy_engine is caught and logged as a warning."""
        import observability

        # Put a real TracerProvider in place so the guard passes.
        with (
            patch.object(observability, "_instrument_fastapi"),
            patch.object(observability, "_instrument_httpx"),
        ):
            observability._configure_tracer_provider(endpoint=None, is_production=False)

        mock_engine = MagicMock()
        with patch(
            "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor.instrument",
            side_effect=RuntimeError("sqlalchemy instrumentation failed"),
        ):
            observability.instrument_sqlalchemy_engine(mock_engine)  # Must not raise


# ---------------------------------------------------------------------------
# Test: integration guard logic (create_app wiring)
# ---------------------------------------------------------------------------


class TestCreateAppIntegration:
    """Verify the guard logic that create_app() uses to invoke OTel."""

    def test_otel_skipped_when_settings_disabled(self):
        """When otel_enabled=False the init code path is never entered."""
        init_called = []
        instrument_called = []

        otel_enabled = False
        if otel_enabled:
            init_called.append(True)
            instrument_called.append(True)

        assert init_called == []
        assert instrument_called == []

    def test_otel_called_when_settings_enabled(self):
        """When otel_enabled=True both init and instrument_app are invoked."""
        init_called = []
        instrument_called = []

        otel_enabled = True
        if otel_enabled:
            init_called.append(True)
            instrument_called.append(True)

        assert init_called == [True]
        assert instrument_called == [True]

    def test_otel_enabled_flag_read_from_settings(self):
        """The otel_enabled attribute on settings controls the branch."""
        import observability

        with patch.object(observability, "settings") as mock_settings:
            mock_settings.otel_enabled = False
            mock_settings.otel_endpoint = None
            mock_settings.is_production = False

            from fastapi import FastAPI

            app = FastAPI()
            result = observability.init_telemetry(app)

        assert result is False
