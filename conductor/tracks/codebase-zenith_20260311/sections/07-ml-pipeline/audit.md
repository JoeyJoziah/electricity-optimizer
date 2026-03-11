# Section 7: ML Pipeline — Clarity Gate Audit

**Date:** 2026-03-12
**Auditor:** Claude Code (Direct)
**Score:** 78/90 (PASS)

---

## Aggregate Scores

| # | Dimension | Score |
|---|-----------|-------|
| 1 | Correctness | 8/10 |
| 2 | Coverage | 9/10 |
| 3 | Security | 9/10 |
| 4 | Performance | 8/10 |
| 5 | Maintainability | 9/10 |
| 6 | Documentation | 9/10 |
| 7 | Error Handling | 8/10 |
| 8 | Consistency | 9/10 |
| 9 | Modernity | 9/10 |
| | **TOTAL** | **78/90** |

---

## Files Analyzed (~5,000 lines across 15 source + 13 test files)

**Models**: `models/ensemble.py` (675 lines), `models/price_forecaster.py`
**Training**: `training/train_forecaster.py` (601 lines), `training/cnn_lstm_trainer.py`, `training/hyperparameter_tuning.py`
**Data**: `data/feature_engineering.py` (623 lines)
**Inference**: `inference/predictor.py`, `inference/ensemble_predictor.py` (414 lines)
**Evaluation**: `evaluation/backtesting.py` (703 lines), `evaluation/metrics.py`
**Optimization**: `optimization/load_shifter.py`, `optimization/scheduler.py`, `optimization/switching_decision.py`, `optimization/constraints.py`
**Tests**: 13 test files covering all modules

---

## Architecture Assessment

Mature ML pipeline with clean separation across 5 layers: data (feature engineering), models (CNN-LSTM + ensemble), training (orchestrated pipeline), inference (ensemble predictor with Redis/DB/file weight fallback), and evaluation (walk-forward backtesting). The ensemble combines CNN-LSTM (50%), XGBoost (25%), and LightGBM (25%) with configurable weights and nightly adaptive learning.

## HIGH Findings (3)

**H-01: ensemble_predictor.py synchronous psycopg2 in async context**
- File: `inference/ensemble_predictor.py:131-166`
- `_load_weights_from_db()` uses synchronous `psycopg2.connect()` during startup
- While intentional (documented as "no async event-loop required"), it blocks the event loop if called during request handling
- Fix: Document that this is init-time only; add guard to prevent accidental async-context calls

**H-02: feature_engineering.py NaN fill strategy masks data quality issues**
- File: `data/feature_engineering.py:436-439`
- `df.ffill().bfill()` after replacing inf with NaN means missing data at the beginning/end of series is silently filled
- Could produce misleading features if data gaps are significant
- Fix: Log warning when >5% of values are filled; consider raising for >20% gaps

**H-03: train_forecaster.py hardcoded country code "GB"**
- File: `training/train_forecaster.py:69`
- `country_code: str = "GB"` default in TrainingConfig
- RateShift operates in all 50 US states — GB holidays don't apply
- Fix: Default to "US" or require explicit country code; use Region enum

## MEDIUM Findings (3)

**M-01: ensemble.py pickle usage for model serialization**
- File: `models/ensemble.py` (various save/load methods)
- While XGBoost/LightGBM use their own formats, the ensemble config uses JSON (safe)
- However, the `BaseGBMForecaster` stores models in a plain list — no version tracking
- Fix: Add model version metadata to saved artifacts

**M-02: backtesting.py matplotlib import at module level**
- File: `evaluation/backtesting.py:27-31`
- `try: import matplotlib` pattern is correct, but matplotlib is a heavy import
- In production inference (no plotting), this still attempts the import
- Fix: Move matplotlib import inside `_generate_plots()` method only

**M-03: No input validation on EnsemblePredictor.predict() horizon parameter**
- File: `inference/ensemble_predictor.py:231`
- `horizon` parameter accepts any integer — no upper bound validation
- Requesting horizon=1000 could produce meaningless results
- Fix: Validate `horizon <= config.forecast_horizon` (default 24)

## Strengths

- **4-tier weight loading**: Redis (fast) -> PostgreSQL (durable) -> metadata.yaml -> defaults — excellent resilience
- **Comprehensive backtesting**: Walk-forward validation with expanding/rolling windows, hourly MAPE breakdown
- **Clean feature engineering**: 50+ features including cyclical encoding, holiday awareness, demand proxies
- **Confidence intervals**: Combined epistemic (model variance) + aleatoric (individual uncertainty) estimation
- **Graceful degradation**: Optional imports for xgboost/lightgbm/statsmodels/matplotlib with feature-level fallbacks
- **611 tests**: Comprehensive test coverage across all ML modules
- **Country code normalization**: `_COUNTRY_CODE_ALIASES` handles UK->GB mapping gracefully

**Verdict:** PASS (78/90). Well-architected ML pipeline with strong separation of concerns, comprehensive evaluation framework, and resilient weight loading chain. Main issues are sync DB access in async context, silent NaN filling, and incorrect default country code.
