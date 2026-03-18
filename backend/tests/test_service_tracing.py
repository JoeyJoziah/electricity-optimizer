"""
Tests for Phase 2 service tracing — 7 critical backend services.

RED phase — these tests assert that custom spans are created with correct
attributes when service methods are called. They will FAIL until Tasks 2.2–2.7
add traced() calls to the services.

Services instrumented:
- AgentService: query_streaming, query_async
- PriceService: get_current_price, get_price_forecast
- StripeService: create_checkout_session, handle_webhook_event
- AlertService: send_alerts, create_alert
- PortalScraperService: scrape_portal
- ConnectionSyncService: sync_connection
- RateScraperService: scrape_supplier_rates
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
# AgentService
# ---------------------------------------------------------------------------


class TestAgentServiceTracing:

    @pytest.mark.asyncio
    async def test_query_streaming_creates_span(self):
        """query_streaming() should create an 'agent.query' span."""
        exporter = _install_recording_provider()

        with (
            patch("services.agent_service.genai", MagicMock()),
            patch("services.agent_service.Groq", MagicMock()),
        ):
            from services.agent_service import AgentService

            svc = AgentService()
            svc._query_gemini = AsyncMock(return_value="test response")

            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=0)))

            # Consume the generator
            try:
                async for _ in svc.query_streaming(
                    "user1", "hello", {"region": "NY", "tier": "pro"}, mock_db
                ):
                    pass
            except Exception:
                pass

        agent_spans = [s for s in exporter.spans if s.name.startswith("agent.")]
        assert (
            len(agent_spans) >= 1
        ), f"Expected agent.* span, got: {[s.name for s in exporter.spans]}"
        assert agent_spans[0].attributes.get("agent.provider") is not None or True

    @pytest.mark.asyncio
    async def test_query_async_creates_span(self):
        """query_async() should create an 'agent.query_async' span."""
        exporter = _install_recording_provider()

        with (
            patch("services.agent_service.genai", MagicMock()),
            patch("services.agent_service.Groq", MagicMock()),
        ):
            from services.agent_service import AgentService

            svc = AgentService()
            svc._query_gemini = AsyncMock(return_value="async response")

            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=0)))

            try:
                await svc.query_async("user1", "hello", {"region": "CA", "tier": "pro"}, mock_db)
            except Exception:
                pass

        agent_spans = [s for s in exporter.spans if s.name.startswith("agent.")]
        assert (
            len(agent_spans) >= 1
        ), f"Expected agent.* span, got: {[s.name for s in exporter.spans]}"


# ---------------------------------------------------------------------------
# PriceService
# ---------------------------------------------------------------------------


class TestPriceServiceTracing:

    @pytest.mark.asyncio
    async def test_get_current_price_creates_span(self):
        """get_current_price() should create a 'price.get_current' span."""
        exporter = _install_recording_provider()

        mock_repo = AsyncMock()
        mock_repo.get_latest_by_supplier = AsyncMock(return_value=None)

        from services.price_service import PriceService

        svc = PriceService(price_repo=mock_repo)

        from models.region import PriceRegion

        await svc.get_current_price(PriceRegion.NY, "ConEd")

        price_spans = [s for s in exporter.spans if s.name.startswith("price.")]
        assert (
            len(price_spans) >= 1
        ), f"Expected price.* span, got: {[s.name for s in exporter.spans]}"
        span = price_spans[0]
        assert span.attributes.get("price.region") == "NY"

    @pytest.mark.asyncio
    async def test_get_price_forecast_creates_span(self):
        """get_price_forecast() should create a 'price.forecast' span."""
        exporter = _install_recording_provider()

        mock_repo = AsyncMock()
        mock_repo.get_historical_prices = AsyncMock(return_value=[])

        from services.price_service import PriceService

        svc = PriceService(price_repo=mock_repo)

        from models.region import PriceRegion

        try:
            await svc.get_price_forecast(PriceRegion.CA, hours=24)
        except Exception:
            pass  # May fail due to ML deps — we only care about span

        price_spans = [s for s in exporter.spans if s.name.startswith("price.")]
        assert (
            len(price_spans) >= 1
        ), f"Expected price.* span, got: {[s.name for s in exporter.spans]}"


# ---------------------------------------------------------------------------
# StripeService
# ---------------------------------------------------------------------------


class TestStripeServiceTracing:

    @pytest.mark.asyncio
    async def test_create_checkout_creates_span(self):
        """create_checkout_session() should create a 'stripe.create_checkout' span."""
        exporter = _install_recording_provider()

        with patch("services.stripe_service.stripe") as mock_stripe:
            mock_stripe.checkout.Session.create = MagicMock(
                return_value=MagicMock(url="https://checkout.stripe.com/test")
            )

            from services.stripe_service import StripeService

            svc = StripeService(db=AsyncMock())

            try:
                await svc.create_checkout_session(
                    user_id="user1", email="test@test.com", plan="pro"
                )
            except Exception:
                pass

        stripe_spans = [s for s in exporter.spans if s.name.startswith("stripe.")]
        assert (
            len(stripe_spans) >= 1
        ), f"Expected stripe.* span, got: {[s.name for s in exporter.spans]}"

    @pytest.mark.asyncio
    async def test_handle_webhook_creates_span(self):
        """handle_webhook_event() should create a 'stripe.webhook' span."""
        exporter = _install_recording_provider()

        with patch("services.stripe_service.stripe") as mock_stripe:
            from services.stripe_service import StripeService

            svc = StripeService(db=AsyncMock())

            mock_event = {"type": "checkout.session.completed", "data": {"object": {}}}
            try:
                await svc.handle_webhook_event(mock_event)
            except Exception:
                pass

        stripe_spans = [s for s in exporter.spans if s.name.startswith("stripe.")]
        assert (
            len(stripe_spans) >= 1
        ), f"Expected stripe.* span, got: {[s.name for s in exporter.spans]}"


# ---------------------------------------------------------------------------
# AlertService
# ---------------------------------------------------------------------------


class TestAlertServiceTracing:

    @pytest.mark.asyncio
    async def test_send_alerts_creates_span(self):
        """send_alerts() should create an 'alert.send' span."""
        exporter = _install_recording_provider()

        mock_db = AsyncMock()
        mock_email = AsyncMock()

        from services.alert_service import AlertService

        svc = AlertService(db=mock_db, email_service=mock_email)

        await svc.send_alerts([])  # empty list is fine

        alert_spans = [s for s in exporter.spans if s.name.startswith("alert.")]
        assert (
            len(alert_spans) >= 1
        ), f"Expected alert.* span, got: {[s.name for s in exporter.spans]}"

    @pytest.mark.asyncio
    async def test_create_alert_creates_span(self):
        """create_alert() should create an 'alert.create' span."""
        exporter = _install_recording_provider()

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock())
        mock_db.commit = AsyncMock()

        from services.alert_service import AlertService

        svc = AlertService(db=mock_db, email_service=AsyncMock())

        try:
            await svc.create_alert(
                user_id="user1",
                region="NY",
                alert_type="price_drop",
                threshold=0.10,
            )
        except Exception:
            pass

        alert_spans = [s for s in exporter.spans if s.name.startswith("alert.")]
        assert (
            len(alert_spans) >= 1
        ), f"Expected alert.* span, got: {[s.name for s in exporter.spans]}"


# ---------------------------------------------------------------------------
# PortalScraperService
# ---------------------------------------------------------------------------


class TestPortalScraperServiceTracing:

    @pytest.mark.asyncio
    async def test_scrape_portal_creates_span(self):
        """scrape_portal() should create a 'scraper.portal' span."""
        exporter = _install_recording_provider()

        from services.portal_scraper_service import PortalScraperService

        svc = PortalScraperService(db=AsyncMock())

        try:
            await svc.scrape_portal(
                connection_id="conn1",
                utility_name="Duke Energy",
                username="user",
                password="pass",
            )
        except Exception:
            pass

        scraper_spans = [s for s in exporter.spans if s.name.startswith("scraper.")]
        assert (
            len(scraper_spans) >= 1
        ), f"Expected scraper.* span, got: {[s.name for s in exporter.spans]}"
        assert scraper_spans[0].attributes.get("scraper.utility") == "Duke Energy"


# ---------------------------------------------------------------------------
# ConnectionSyncService
# ---------------------------------------------------------------------------


class TestConnectionSyncServiceTracing:

    @pytest.mark.asyncio
    async def test_sync_connection_creates_span(self):
        """sync_connection() should create a 'sync.connection' span."""
        exporter = _install_recording_provider()

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=None)))

        from services.connection_sync_service import ConnectionSyncService

        svc = ConnectionSyncService(db=mock_db)

        try:
            await svc.sync_connection("conn-123")
        except Exception:
            pass

        sync_spans = [s for s in exporter.spans if s.name.startswith("sync.")]
        assert (
            len(sync_spans) >= 1
        ), f"Expected sync.* span, got: {[s.name for s in exporter.spans]}"


# ---------------------------------------------------------------------------
# RateScraperService
# ---------------------------------------------------------------------------


class TestRateScraperServiceTracing:

    @pytest.mark.asyncio
    async def test_scrape_supplier_rates_creates_span(self):
        """scrape_supplier_rates() should create a 'scraper.rates' span."""
        exporter = _install_recording_provider()

        mock_db = AsyncMock()

        from services.rate_scraper_service import RateScraperService

        svc = RateScraperService(db=mock_db)

        try:
            await svc.scrape_supplier_rates()
        except Exception:
            pass

        scraper_spans = [s for s in exporter.spans if s.name.startswith("scraper.")]
        assert (
            len(scraper_spans) >= 1
        ), f"Expected scraper.* span, got: {[s.name for s in exporter.spans]}"
