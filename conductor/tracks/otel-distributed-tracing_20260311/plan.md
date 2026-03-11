# Implementation Plan: OpenTelemetry Distributed Tracing

**Track ID:** otel-distributed-tracing_20260311
**Spec:** spec.md
**Created:** 2026-03-11
**Status:** [ ] Not Started
**Estimated Effort:** 8h

## Overview

Four-phase implementation that layers custom OTel spans onto the existing SDK foundation, connects to Grafana Cloud, and validates end-to-end. Each phase follows TDD (RED/GREEN/REFACTOR) and is independently verifiable. Stream-chain orchestration coordinates analysis -> test -> implement -> validate across phases.

---

## Phase 1: Tracing Helpers & ML Pipeline Spans (~2h)

Build a thin tracing helper module and instrument the ML inference pipeline — the highest-value tracing target.

### Tasks

- [x] Task 1.1: **RED** — Write `test_tracing_helpers.py` with tests for a `traced()` context manager/decorator that creates spans, records exceptions, and sets standard attributes
- [x] Task 1.2: **GREEN** — Implement `backend/lib/tracing.py` with `traced()` helper wrapping `get_tracer()` + span lifecycle (attributes, error recording, status codes)
- [x] Task 1.3: **REFACTOR** — Ensure `traced()` is zero-cost when OTEL_ENABLED=false (no-op tracer path, no import overhead)
- [x] Task 1.4: **RED** — Write `test_ml_tracing.py` with tests asserting spans are created for `LearningService.train()`, `ObservationService.observe()`, `ModelVersionService.predict()`
- [x] Task 1.5: **GREEN** — Add `traced()` calls to LearningService, ObservationService, ModelVersionService with attributes: `ml.model_name`, `ml.region`, `ml.inference_latency_ms`, `ml.observation_count`
- [x] Task 1.6: **REFACTOR** — Extract common ML span attributes into a `_ml_span_attrs()` helper if duplication emerges

### Verification

- [ ] `pytest tests/test_tracing_helpers.py tests/test_ml_tracing.py -v` — all green
- [ ] `pytest --tb=short` — full backend suite passes (2,077+ tests)
- [ ] Manual: `OTEL_ENABLED=true .venv/bin/python -c "from lib.tracing import traced; print('OK')"` — no import errors

---

## Phase 2: Core Service Spans (~2.5h)

Instrument the 7 highest-traffic / highest-value services with custom spans.

### Tasks

- [x] Task 2.1: **RED** — Write `test_service_tracing.py` with parametrized tests asserting span creation for each target service/method pair
- [x] Task 2.2: **GREEN** — Instrument `AgentService` — spans on `query_streaming()`, `query_async()` with attributes: `agent.provider`
- [x] Task 2.3: **GREEN** — Instrument `PriceService` — spans on `get_current_price()`, `get_price_forecast()` with attributes: `price.region`, `price.source`
- [x] Task 2.4: **GREEN** — Instrument `StripeService` — spans on `create_checkout_session()`, `handle_webhook_event()` with attributes: `stripe.plan`, `stripe.event_type`
- [x] Task 2.5: **GREEN** — Instrument `AlertService` — spans on `send_alerts()`, `create_alert()` with attributes: `alert.type`, `alert.region`, `alert.count`
- [x] Task 2.6: **GREEN** — Instrument `PortalScraperService` — spans on `scrape_portal()` with attributes: `scraper.utility`, `scraper.method`
- [x] Task 2.7: **GREEN** — Instrument `ConnectionSyncService` + `RateScraperService` — spans on sync_connection/scrape_supplier_rates with attributes: `sync.connection_id`, `scraper.method`
- [x] Task 2.8: **REFACTOR** — Review all spans for consistent naming convention (`{service}.{operation}`), attribute naming (OTel semantic conventions), and error recording patterns

### Verification

- [ ] `pytest tests/test_service_tracing.py -v` — all green
- [ ] `pytest --tb=short` — full backend suite passes
- [ ] Verify span naming follows `{service}.{operation}` convention via test assertions
- [ ] Verify zero-overhead path: `OTEL_ENABLED=false` tests pass with no performance regression

---

## Phase 3: Grafana Cloud Integration (~2h)

Provision Grafana Cloud, configure OTLP export, and deploy to production.

### Tasks

- [x] Task 3.1: Sign up for Grafana Cloud free tier (grafana.com), create a stack, note the OTLP endpoint URL and API token
- [x] Task 3.2: Store Grafana Cloud credentials in 1Password vault "RateShift" (items: `GRAFANA_OTLP_ENDPOINT`, `GRAFANA_OTLP_TOKEN`)
- [x] Task 3.3: Add Render env vars: `OTEL_ENABLED=true`, `OTEL_EXPORTER_OTLP_ENDPOINT=<grafana-otlp-url>`, `OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <base64-token>`
- [x] Task 3.4: Update `render.yaml` blueprint with the 3 new env vars (referencing Render env group or secrets)
- [x] Task 3.5: Update `.env.example` with OTel env var documentation
- [x] Task 3.6: **RED/GREEN** — Write integration test `test_otlp_export.py` that verifies `OTLPSpanExporter` is configured when endpoint is set (mock the HTTP transport, assert export payload structure)
- [ ] Task 3.7: Deploy to Render and verify traces appear in Grafana Cloud Tempo

### Verification

- [ ] Grafana Cloud Tempo shows traces from `rateshift-backend` service
- [ ] Traces contain spans from FastAPI auto-instrumentor + custom service spans
- [ ] `render.yaml` diff is minimal (3 env vars only)
- [ ] `.env.example` documents all OTel variables
- [ ] 1Password has Grafana credentials stored

---

## Phase 4: Dashboards & End-to-End Validation (~1.5h)

Create a production Grafana dashboard and run end-to-end trace validation.

### Tasks

- [x] Task 4.1: Create Grafana Cloud dashboard "RateShift Backend Traces" with panels:
  - Request latency P50/P95/P99 by endpoint
  - Error rate by service
  - Trace count over time
  - Top 10 slowest traces (drill-down to spans)
- [x] Task 4.2: Export dashboard JSON to `monitoring/grafana/dashboards/traces.json` for version control
- [ ] Task 4.3: End-to-end smoke test — trigger real API requests (health, prices, forecast) and verify complete trace in Grafana Cloud (root span -> child spans -> DB/HTTP sub-spans)
- [x] Task 4.4: Document OTel setup in `docs/OBSERVABILITY.md` — architecture, span naming, how to add new spans, Grafana Cloud access, dashboard links
- [ ] Task 4.5: Update `conductor/tracks/otel-distributed-tracing_20260311/metadata.json` — mark all phases complete

### Verification

- [ ] Grafana dashboard loads and shows live data
- [ ] At least one complete trace visible with 3+ span levels (request -> service -> DB/HTTP)
- [ ] `docs/OBSERVABILITY.md` exists and covers setup, conventions, and how-to-extend
- [ ] All acceptance criteria from spec.md checked off

---

## Final Verification

- [ ] All acceptance criteria met (9/9)
- [ ] Backend tests passing (2,077+ existing + new tracing tests)
- [ ] No performance regression with OTEL_ENABLED=false
- [ ] Production traces flowing to Grafana Cloud
- [ ] Documentation updated
- [ ] TASK-QUALITY-003 status updated to COMPLETE in MASTER_TODO_REGISTRY
- [ ] Board sync triggered (GitHub Projects)
- [ ] Memory persisted to Claude Flow

---

## Stream-Chain Execution Plan

```bash
# Phase 1-2 follow this pipeline per service group:
claude-flow stream-chain run \
  "Analyze service methods that need tracing (identify hot paths)" \
  "Write failing tests asserting span creation and attributes (RED)" \
  "Implement tracing with traced() helper (GREEN)" \
  "Refactor for consistency and zero-overhead (REFACTOR)" \
  --timeout 60

# Phase 3-4 follow this pipeline:
claude-flow stream-chain run \
  "Configure Grafana Cloud OTLP endpoint and credentials" \
  "Deploy env vars and verify trace export" \
  "Build dashboards and validate end-to-end" \
  "Document setup and mark track complete" \
  --timeout 90
```

## TDD Cycle Summary

| Phase | RED (Tests First) | GREEN (Minimal Code) | REFACTOR |
|-------|-------------------|---------------------|----------|
| 1 | `test_tracing_helpers.py`, `test_ml_tracing.py` | `lib/tracing.py`, ML service spans | Zero-cost guard, DRY attrs |
| 2 | `test_service_tracing.py` (parametrized) | 7 service instrumentations | Naming conventions, error patterns |
| 3 | `test_otlp_export.py` | Env var config, deploy | render.yaml cleanup |
| 4 | E2E smoke test | Dashboard creation | Documentation |

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
