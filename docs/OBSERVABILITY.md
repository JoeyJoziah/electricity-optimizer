# Observability — OpenTelemetry Distributed Tracing

RateShift uses OpenTelemetry (OTel) for distributed tracing across the FastAPI backend. Traces are exported to Grafana Cloud Tempo via OTLP/HTTP.

## Architecture

```
FastAPI Request
  |
  v
OTelMiddleware (user_id, request_id)
  |
  v
FastAPI auto-instrumentor (HTTP method, route, status)
  |
  +---> Service spans (traced() helper)
  |       |
  |       +---> price.get_current, price.forecast
  |       +---> stripe.create_checkout, stripe.webhook
  |       +---> agent.query, agent.query_async
  |       +---> ml.compute_accuracy, ml.update_weights, ...
  |       +---> alert.send, alert.create
  |       +---> scraper.portal, scraper.rates
  |       +---> sync.connection
  |
  +---> SQLAlchemy auto-instrumentor (DB queries)
  +---> httpx auto-instrumentor (outbound HTTP)
  |
  v
BatchSpanProcessor --> OTLPSpanExporter --> Grafana Cloud Tempo
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OTEL_ENABLED` | Yes | Set `true` to activate instrumentation |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Yes (prod) | OTLP gateway URL from Grafana Cloud |
| `OTEL_EXPORTER_OTLP_HEADERS` | Yes (prod) | `Authorization=Basic <base64>` header |

### Exporter Selection (automatic)

1. `OTEL_EXPORTER_OTLP_ENDPOINT` set --> OTLP/HTTP export (production)
2. `OTEL_ENABLED=true`, no endpoint, non-prod --> ConsoleSpanExporter (stdout)
3. `OTEL_ENABLED=true`, no endpoint, prod --> Silent discard (no log spam)
4. `OTEL_ENABLED=false` (default) --> Zero overhead, nothing initialized

### Credentials

Stored in 1Password vault "RateShift" under "Grafana Cloud OTLP":
- OTLP endpoint URL
- Instance ID
- API token
- Pre-computed auth header

Render env vars reference these values directly (not in source control).

## Span Naming Convention

All custom spans follow `{service}.{operation}`:

| Service | Spans | Key Attributes |
|---------|-------|----------------|
| PriceService | `price.get_current`, `price.forecast` | `price.region`, `price.source` |
| StripeService | `stripe.create_checkout`, `stripe.webhook` | `stripe.plan`, `stripe.event_type` |
| AgentService | `agent.query`, `agent.query_async` | `agent.provider` |
| AlertService | `alert.send`, `alert.create` | `alert.type`, `alert.region`, `alert.count` |
| PortalScraperService | `scraper.portal` | `scraper.utility`, `scraper.method` |
| RateScraperService | `scraper.rates` | `scraper.method` |
| ConnectionSyncService | `sync.connection` | `sync.connection_id` |
| LearningService | `ml.compute_accuracy`, `ml.update_weights` | `ml.region`, `ml.days` |
| ObservationService | `ml.record_forecast`, `ml.observe_actuals` | `ml.region` |
| ModelVersionService | `ml.create_version`, `ml.promote_version` | `ml.model_name`, `ml.version_id` |

## How to Add New Spans

### 1. Import the helper

```python
from lib.tracing import traced
```

### 2. Wrap the method body

```python
async def my_method(self, region: str) -> dict:
    async with traced(
        "myservice.operation",
        attributes={
            "myservice.region": region,
        },
    ):
        # ... method body here ...
        return result
```

### 3. Key rules

- Span names: `{service}.{operation}` (lowercase, dot-separated)
- Attributes: `{service}.{attribute}` (OTel semantic convention prefix)
- Always wrap the full method body inside `async with traced(...):`
- The `traced()` helper records exceptions and sets error status automatically
- Zero-cost when `OTEL_ENABLED=false` (no-op tracer, no import overhead)
- Works as both sync (`with traced(...)`) and async (`async with traced(...)`)

### 4. Write a test

Add a parametrized test case to `tests/test_service_tracing.py`:

```python
@pytest.mark.asyncio
async def test_my_method_creates_span(self):
    exporter = _install_recording_provider()

    svc = MyService(...)
    await svc.my_method("NY")

    spans = [s for s in exporter.spans if s.name.startswith("myservice.")]
    assert len(spans) >= 1
    assert spans[0].attributes.get("myservice.region") == "NY"
```

## Grafana Cloud Access

- **Dashboard**: "RateShift Backend Traces" (uid: `rateshift-traces-v1`)
- **Datasource**: Tempo (auto-provisioned by Grafana Cloud)
- **Dashboard JSON**: `monitoring/grafana/dashboards/traces.json` (version-controlled)

### Dashboard Panels

| Row | Panel | Description |
|-----|-------|-------------|
| Overview | Total Traces | Trace count in time range |
| Overview | Error Rate | % traces with error status |
| Overview | Avg Latency | Median request duration |
| Overview | P99 Latency | Tail latency |
| Latency | P50/P95/P99 | Latency percentiles over time (green/yellow/red) |
| Latency | Trace Count | OK vs Error volume (stacked bars) |
| Services | Latency by Span | P95 per service operation |
| Services | Errors by Span | Error rate per service operation |
| Explorer | Slowest Traces | Top 10 by duration (click to drill down) |
| Explorer | Error Traces | Recent errors with exception details |

### Importing the Dashboard

1. Go to Grafana Cloud > Dashboards > Import
2. Upload `monitoring/grafana/dashboards/traces.json`
3. Select the Tempo datasource when prompted

## Files

| File | Purpose |
|------|---------|
| `backend/observability.py` | OTel SDK init, exporter selection, auto-instrumentors |
| `backend/lib/tracing.py` | `traced()` context manager helper |
| `backend/config/settings.py` | `otel_enabled`, `otel_endpoint` settings |
| `monitoring/grafana/dashboards/traces.json` | Dashboard JSON (version-controlled) |
| `render.yaml` | Render env vars (OTEL_ENABLED, endpoint, headers) |
| `backend/.env.example` | Local dev env var documentation |
| `backend/tests/test_tracing_helpers.py` | Unit tests for traced() helper (13 tests) |
| `backend/tests/test_ml_tracing.py` | ML service tracing tests (6 tests) |
| `backend/tests/test_service_tracing.py` | Phase 2 service tracing tests (11 tests) |
| `backend/tests/test_otlp_export.py` | OTLP export integration tests (7 tests) |
| `backend/tests/test_observability.py` | Core observability tests (27 tests) |
