# Section 1: Database Layer — Clarity Gate Baseline

**Date:** 2026-03-11
**Assessor:** Loki Mode (Autonomous RARV)
**Scope:** All 35 migration files, schema design, index strategy, query patterns, connection config

---

## Quantitative Baseline

| Metric | Value |
|--------|-------|
| Migration files | 35 (init_neon + 002-035) |
| Public tables | 33 |
| neon_auth tables | 9 |
| Total tables | 42 |
| Index migrations | 004, 010, 017, 020, 022, 023 (6 dedicated index migrations) |
| Backend tests | 2,045 collected |
| DSP entities | 353 |
| DSP orphans | 126 |
| DSP cycles | 0 |

## Clarity Gate Scorecard (Pre-Optimization)

| # | Dimension | Score | Notes |
|---|-----------|-------|-------|
| 1 | Correctness | ?/10 | Pending audit |
| 2 | Coverage | ?/10 | Pending audit |
| 3 | Security | ?/10 | Pending audit |
| 4 | Performance | ?/10 | Pending audit |
| 5 | Maintainability | ?/10 | Pending audit |
| 6 | Documentation | ?/10 | Pending audit |
| 7 | Error Handling | ?/10 | Pending audit |
| 8 | Consistency | ?/10 | Pending audit |
| 9 | Modernity | ?/10 | Pending audit |
| | **Aggregate** | **?/90** | |

**Minimum passing:** 8/10 per dimension, 72/90 aggregate

---

## Files in Scope

### Migration Files (35)
- `init_neon.sql` — Initial schema with neon_auth integration
- `002_gdpr_auth_tables.sql` — GDPR compliance tables
- `003_reconcile_schema.sql` — Schema reconciliation
- `004_performance_indexes.sql` — Performance indexing
- `005_observation_tables.sql` — ML observation tables
- `006_multi_utility_expansion.sql` — Multi-utility support
- `007_user_supplier_accounts.sql` — User-supplier relationships
- `008_connection_feature.sql` — Connection management
- `009_email_oauth_tokens.sql` — Email OAuth tokens
- `010_utility_type_index.sql` — Utility type indexing
- `011_utilityapi_sync_columns.sql` — UtilityAPI sync
- `012_user_savings.sql` — User savings tracking
- `013_user_profile_columns.sql` — User profile expansion
- `014_alert_tables.sql` — Alert system
- `015_notifications.sql` — Notification system
- `016_feature_flags.sql` — Feature flag system
- `017_additional_indexes.sql` — Additional performance indexes
- `018_nationwide_defaults.sql` — Nationwide default data
- `019_nationwide_suppliers.sql` — Nationwide supplier data
- `020_price_query_indexes.sql` — Price query optimization
- `021_fix_supplier_api_available.sql` — Supplier API fix
- `022_user_supplier_composite_index.sql` — Composite indexing
- `023_db_audit_indexes.sql` — Audit indexes
- `024_payment_retry_history.sql` — Payment retry tracking
- `025_data_cache_tables.sql` — Data caching
- `026_notifications_metadata.sql` — Notification metadata
- `027_model_config.sql` — ML model config
- `028_feedback_table.sql` — User feedback
- `029_notification_delivery_tracking.sql` — Delivery tracking
- `030_model_versioning_ab_tests.sql` — Model versioning & A/B
- `031_agent_tables.sql` — AI agent tables
- `032_notification_error_message.sql` — Notification errors
- `033_model_predictions_ab_assignments.sql` — ML predictions
- `034_portal_credentials.sql` — Portal credentials (encrypted)
- `035_backfill_neon_auth_users.sql` — User backfill script

### Database Configuration
- Connection pooling config
- asyncpg settings
- Neon-specific configuration

### Model Definitions
- `backend/models/` — All SQLAlchemy models

---

_Baseline established. Audit phase begins next._
