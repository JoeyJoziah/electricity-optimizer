# ML Pipeline Architecture

> Last updated: 2026-03-25 | 676 tests across ml/ module + 8 ML-related backend services

## Overview

RateShift's ML pipeline predicts electricity prices 24 hours ahead, enabling users to shift energy loads to cheaper windows. The pipeline spans two layers: the standalone `ml/` module (models, training, evaluation) and backend services that integrate ML into the production API.

## End-to-End Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          DATA INGESTION                                │
│                                                                        │
│   EIA API ──┐                                                          │
│   NREL API ─┤── price_sync_service ──→ electricity_prices table        │
│   Diffbot ──┘   (CF Worker cron,       (Neon PostgreSQL)               │
│                  every 6h)                                             │
│                                                                        │
│   OWM API ──── weather_service ──→ weather_data table                  │
│                (GHA cron, 12h)                                         │
│                                                                        │
│   Tavily ───── market_intelligence ──→ market_research table           │
│   Diffbot      (GHA cron, daily)                                       │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       FEATURE ENGINEERING                              │
│                                                                        │
│   feature_engineering.py → 73 features per sample:                     │
│   ├── Temporal: hour, day_of_week, day_of_month, month                 │
│   ├── Cyclical: sin/cos encoding for hour, day, month                  │
│   ├── Domain: price volatility, moving averages (7d/30d)               │
│   ├── Seasonal: seasonal indices per region                            │
│   └── Normalization: per-region custom scaling                         │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         MODEL TRAINING                                 │
│                                                                        │
│   training/train_forecaster.py (weekly retrain, model-retrain.yml)     │
│   ├── Load 2 years historical data                                     │
│   ├── Feature engineering (73 features)                                │
│   ├── Train/val/test split (85/10/5)                                   │
│   ├── Hyperparameter tuning (Bayesian, 50-100 trials)                  │
│   └── Train 3 models:                                                  │
│       ├── CNN-LSTM (50% weight) ← complex temporal patterns            │
│       ├── XGBoost  (25% weight) ← feature interactions                 │
│       └── LightGBM (25% weight) ← gradient boosting signal            │
│                                                                        │
│   evaluation/backtesting.py                                            │
│   ├── Walk-forward validation                                          │
│   ├── 13 metrics: MAE, RMSE, MAPE, sMAPE, R², direction accuracy      │
│   └── Gate: MAPE < 10%, Direction > 70%, R² > 0.85                    │
│                                                                        │
│   utils/integrity.py                                                   │
│   └── HMAC-SHA256 model signing (ML_MODEL_SIGNING_KEY)                 │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      PRODUCTION INFERENCE                              │
│                                                                        │
│   EnsemblePredictor (ml/inference/ensemble_predictor.py)               │
│   ├── Loads weights: Redis → PostgreSQL model_config → defaults        │
│   ├── Weighted average of 3 model predictions                          │
│   ├── Confidence intervals via Z-scores (80-99%)                       │
│   └── Lazy weight loading (no startup blocking)                        │
│                                                                        │
│   forecast_service.py (backend bridge)                                 │
│   ├── Electricity: delegates to EnsemblePredictor                      │
│   ├── Gas/Oil/Propane: linear trend extrapolation (90-day window)      │
│   └── Water: not forecasted (municipal schedule, not market)           │
│                                                                        │
│   API: GET /api/v1/forecast (hourly, summary)                          │
│   Auth: require_tier("pro") for forecast endpoint                      │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      ADAPTIVE LEARNING LOOP                            │
│                                                                        │
│   observation_service.py (POST /internal/observe-forecasts, every 6h)  │
│   ├── Backfill actual prices into forecast_observations table          │
│   └── Compute per-forecast accuracy metrics                            │
│                                                                        │
│   learning_service.py (POST /internal/learn, daily pipeline)           │
│   ├── Compute rolling MAPE/RMSE per model                              │
│   ├── Detect systematic bias by hour-of-day                            │
│   ├── Adjust ensemble weights (bounded: 0.1 ≤ w ≤ 0.8)               │
│   ├── Persist weights to Redis + PostgreSQL model_config               │
│   ├── Store bias correction vectors in HNSW vector store               │
│   └── Prune low-quality patterns                                       │
│                                                                        │
│   rate_change_detector.py (POST /internal/detect-rate-changes, daily)  │
│   └── Identify statistically significant rate changes for alerts       │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        OPTIMIZATION                                    │
│                                                                        │
│   optimization/load_shifter.py                                         │
│   ├── MILP solver (PuLP) for optimal appliance scheduling              │
│   ├── Input: 24h forecast + appliance models + user constraints        │
│   └── Output: hour-by-hour schedule minimizing energy cost             │
│                                                                        │
│   optimization/switching_decision.py                                   │
│   ├── Buy/hold/sell signals for supplier switching                     │
│   └── Based on price trend + contract terms                            │
│                                                                        │
│   recommendation_service.py (backend bridge)                           │
│   ├── GET /recommendations/switching                                   │
│   ├── GET /recommendations/usage                                       │
│   └── GET /recommendations/daily                                       │
│                                                                        │
│   optimization_report_service.py (CTE query, 1 DB call)               │
│   └── GET /reports (combined optimization + savings report)            │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Reference

### ml/ Module (Standalone)

| Directory | Files | Purpose |
|-----------|-------|---------|
| `models/` | 2 | Ensemble model class, CNN-LSTM price forecaster |
| `inference/` | 2 | EnsemblePredictor (production), base Predictor class |
| `training/` | 3 | Train orchestrator, CNN-LSTM trainer, hyperparameter tuning |
| `evaluation/` | 2 | 13 metrics, walk-forward backtesting |
| `optimization/` | 7 | MILP load shifter, scheduler, appliance models, switching decision |
| `data/` | 1 | Feature engineering (73 features) |
| `utils/` | 1 | HMAC model integrity signing |
| `config/` | 1 | model_config.yaml (weights, hyperparams, horizons) |
| `tests/` | 20 | 676 tests |

### Backend ML Services (8 services)

| Service | File | Purpose |
|---------|------|---------|
| `forecast_service` | services/forecast_service.py | Multi-utility forecasting bridge |
| `learning_service` | services/learning_service.py | Nightly adaptive weight adjustment |
| `observation_service` | services/observation_service.py | Forecast accuracy tracking |
| `hnsw_vector_store` | services/hnsw_vector_store.py | HNSW-based similarity search for price patterns |
| `vector_store` | services/vector_store.py | Price curve to vector encoding |
| `model_version_service` | services/model_version_service.py | Model versioning and A/B testing |
| `data_quality_service` | services/data_quality_service.py | Data freshness, anomaly detection |
| `rate_change_detector` | services/rate_change_detector.py | Statistical rate change detection |

### Scheduled Jobs

| Job | Schedule | Endpoint | Purpose |
|-----|----------|----------|---------|
| price-sync | Every 6h (CF Worker) | `POST /prices/refresh` | Ingest price data |
| observe-forecasts | Every 6h+30min (CF Worker) | `POST /internal/observe-forecasts` | Accuracy tracking |
| nightly-learning | Daily 3am (GHA pipeline) | `POST /internal/learn` | Weight adjustment |
| detect-rate-changes | Daily 3am (GHA pipeline) | `POST /internal/detect-rate-changes` | Alert triggers |
| model-retrain | Manual (was weekly) | `workflow_dispatch` | Full model retrain |
| fetch-weather | Every 12h (GHA) | `POST /internal/fetch-weather` | Weather feature data |

## Key Design Decisions

1. **Ensemble over single model**: Three diverse model types reduce variance and improve robustness across market conditions
2. **Adaptive weights**: Nightly learning adjusts model weights based on recent accuracy, bounded to [0.1, 0.8] to prevent any model from dominating
3. **Dual persistence**: Weights stored in Redis (fast reads) and PostgreSQL (durability). Load order: Redis → PostgreSQL → defaults
4. **Lazy loading**: EnsemblePredictor defers weight loading to first use, avoiding startup blocking on cache/DB I/O
5. **Non-ML forecasting for utilities**: Gas, oil, propane use simple linear trend extrapolation until 6+ months of data accumulates (Decision D9)
6. **HMAC model signing**: Production models are signed with `ML_MODEL_SIGNING_KEY` to prevent tampering. Verified on load

## Testing

```bash
# All ML tests (676)
.venv/bin/python -m pytest ml/ -q

# Specific modules
.venv/bin/python -m pytest ml/tests/test_models.py
.venv/bin/python -m pytest ml/tests/test_optimization.py
.venv/bin/python -m pytest ml/tests/test_backtesting.py

# Backend ML service tests
.venv/bin/python -m pytest backend/tests/test_forecast_service.py
.venv/bin/python -m pytest backend/tests/test_learning_service.py
```

## Performance Targets

| Metric | Target | Measured By |
|--------|--------|-------------|
| MAPE | < 10% | observation_service |
| Direction Accuracy | > 70% | backtesting |
| R² Score | > 0.85 | backtesting |
| Inference Latency | < 100ms (p95) | OTel traces |
| Model Size | < 50MB | file system |

## Related Docs

- ML module README: `ml/README.md`
- Training pipeline details: `ml/TRAINING_EVALUATION_PIPELINE.md`
- Optimization engine: `ml/optimization/README.md`
- Observability: `docs/OBSERVABILITY.md`
- Cron job details: `docs/runbooks/CRON_JOBS.md`
