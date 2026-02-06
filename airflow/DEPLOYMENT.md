# Airflow Deployment Guide

This document describes how to deploy and operate the Electricity Optimizer Airflow DAGs.

## Architecture Overview

```
                                 +------------------+
                                 |    Airflow       |
                                 |   Webserver      |
                                 +--------+---------+
                                          |
+------------------+            +--------+---------+           +------------------+
|  Pricing APIs    |            |    Airflow       |           |   TimescaleDB    |
|  - Flatpeak      +<---------->+   Scheduler      +<--------->+   (Time-series)  |
|  - NREL          |            +--------+---------+           +------------------+
|  - IEA           |                     |
+------------------+            +--------+---------+           +------------------+
                                |    LocalExecutor |           |     Redis        |
                                +--------+---------+           |   (Cache)        |
                                         |                     +------------------+
                                +--------+---------+
                                |   ML Models      |
                                |   (PyTorch)      |
                                +------------------+
```

## Prerequisites

1. **Docker and Docker Compose** (v2.0+)
2. **External APIs**: Flatpeak, NREL, IEA API keys
3. **Databases**: TimescaleDB and Redis running
4. **ML Models**: Initial model trained and deployed

## Quick Start

### 1. Set Environment Variables

Create `.env` file in project root:

```bash
# Airflow Database
AIRFLOW_DB_URL=postgresql://airflow:airflow@postgres-airflow:5432/airflow

# Airflow Security
AIRFLOW_FERNET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
AIRFLOW_SECRET_KEY=$(openssl rand -base64 32)

# TimescaleDB
TIMESCALEDB_URL=postgresql://postgres:password@timescaledb:5432/electricity

# Redis
REDIS_URL=redis://:password@redis:6379/0

# API Keys
FLATPEAK_API_KEY=your_flatpeak_key
NREL_API_KEY=your_nrel_key
IEA_API_KEY=your_iea_key

# SMTP (for alerts)
SMTP_HOST=smtp.gmail.com
SMTP_USER=alerts@electricity-optimizer.io
SMTP_PASSWORD=your_smtp_password

# Slack Webhook (optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx
```

### 2. Initialize Airflow

```bash
# Start services
docker-compose up -d postgres-airflow

# Initialize database
docker-compose run --rm airflow-webserver airflow db init

# Create admin user
docker-compose run --rm airflow-webserver airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@electricity-optimizer.io \
    --password admin

# Start all services
docker-compose up -d
```

### 3. Configure Connections

Via Airflow UI (http://localhost:8080 > Admin > Connections) or CLI:

```bash
# TimescaleDB
airflow connections add 'timescaledb_default' \
    --conn-type 'postgres' \
    --conn-host 'timescaledb' \
    --conn-schema 'electricity' \
    --conn-login 'postgres' \
    --conn-password 'password' \
    --conn-port '5432'

# Redis
airflow connections add 'redis_default' \
    --conn-type 'redis' \
    --conn-host 'redis' \
    --conn-password 'password' \
    --conn-port '6379'

# Flatpeak API
airflow connections add 'flatpeak_default' \
    --conn-type 'http' \
    --conn-host 'api.flatpeak.com' \
    --conn-password 'your_api_key'

# NREL API
airflow connections add 'nrel_default' \
    --conn-type 'http' \
    --conn-host 'api.nrel.gov' \
    --conn-password 'your_api_key'

# IEA API
airflow connections add 'iea_default' \
    --conn-type 'http' \
    --conn-host 'api.iea.org' \
    --conn-password 'your_api_key'

# Slack Webhook
airflow connections add 'slack_data_quality' \
    --conn-type 'http' \
    --conn-host 'https://hooks.slack.com/services' \
    --conn-password 'your/webhook/url'
```

### 4. Create Resource Pools

```bash
# Rate limiting for pricing APIs
airflow pools set pricing_api_pool 5 "Rate-limited API requests"

# ML training concurrency
airflow pools set ml_training_pool 2 "ML model training jobs"

# Heavy database operations
airflow pools set db_heavy_pool 3 "Heavy database operations"
```

### 5. Set Variables

```bash
# Model accuracy tracking
airflow variables set current_model_mape 100.0
airflow variables set model_mape_threshold 10.0

# Ingestion settings
airflow variables set price_ingestion_min_records 10

# Feature flags
airflow variables set enable_slack_alerts true
```

### 6. Enable DAGs

Via UI or CLI:

```bash
airflow dags unpause electricity_price_ingestion
airflow dags unpause forecast_generation
airflow dags unpause model_retraining
airflow dags unpause data_quality
```

## DAG Overview

### electricity_price_ingestion

**Schedule**: Every 15 minutes (`*/15 * * * *`)

**Purpose**: Fetch electricity prices from external APIs

**Tasks**:
1. `check_api_health` - Verify API availability
2. `check_markets_open` - Skip if markets closed
3. `fetch_flatpeak` / `fetch_nrel` / `fetch_iea` - Parallel API fetches
4. `aggregate_prices` - Combine and deduplicate
5. `validate_data_quality` - Data validation
6. `store_prices` - Upsert to TimescaleDB
7. `update_cache` - Refresh Redis cache
8. `trigger_forecast_dag` - Optionally trigger forecasts

**SLA**: 5 minutes

### model_retraining

**Schedule**: Weekly, Sunday 2 AM UTC (`0 2 * * 0`)

**Purpose**: Retrain price forecasting model

**Tasks**:
1. `check_data_freshness` - Ensure recent data exists
2. `check_training_data_quality` - Validate training data
3. `extract_training_data` - Pull 2 years of data
4. `engineer_features` - Create ML features
5. `train_cnn_lstm` / `train_xgboost` / `train_lightgbm` - Parallel training
6. `evaluate_ensemble` - Calculate ensemble metrics
7. `deploy_model` - Deploy if accuracy improves

**Timeout**: 6 hours

### forecast_generation

**Schedule**: Hourly (`0 * * * *`)

**Purpose**: Generate 24-hour price forecasts

**Tasks**:
1. `check_model_ready` - Verify model available
2. `prepare_features` - Extract recent price features
3. `generate_forecasts` - Run ensemble inference
4. `store_forecasts` - Save to TimescaleDB
5. `update_forecast_cache` - Update Redis

**SLA**: 2 minutes

### data_quality

**Schedule**: Daily at 6 AM UTC (`0 6 * * *`)

**Purpose**: Comprehensive data quality checks

**Tasks**:
1. Completeness check - No gaps > 1 hour
2. Price range validation - Detect outliers
3. API health monitoring - Track response times
4. Model accuracy tracking - Monitor MAPE drift
5. Data freshness check - Ensure current data
6. Generate quality report
7. Alert on critical issues

## Monitoring

### Airflow UI

Access at http://localhost:8080

Key dashboards:
- **DAGs**: Overall DAG status and history
- **Task Duration**: Performance monitoring
- **Landing Times**: SLA compliance
- **Gantt**: Task execution visualization

### Prometheus Metrics

Metrics available at `http://localhost:9090/metrics`:

- `airflow_dag_processing_total`
- `airflow_task_duration_seconds`
- `airflow_scheduler_heartbeat`
- `data_quality_health_score`
- `data_quality_checks_passed`

### Grafana Dashboards

Import provided dashboards from `monitoring/grafana-dashboards/`:

1. **Airflow Overview**: DAG runs, task states
2. **Data Quality**: Quality scores over time
3. **ML Pipeline**: Model accuracy trends
4. **API Health**: External API metrics

### Alerting

Alerts are configured for:

- **SLA Miss**: Price ingestion > 5 min, Forecast > 2 min
- **DAG Failure**: Any DAG fails after retries
- **Data Quality**: Critical check failures
- **Model Accuracy**: MAPE > 15%

Configure in `monitoring/alerts.yml`.

## Operations

### Backfill

Re-run historical DAG runs:

```bash
# Backfill price ingestion for last 7 days
airflow dags backfill electricity_price_ingestion \
    --start-date 2024-01-01 \
    --end-date 2024-01-07

# Note: catchup=False prevents automatic backfill
```

### Clear Task States

Re-run specific tasks:

```bash
# Clear failed tasks for today
airflow tasks clear electricity_price_ingestion \
    --start-date 2024-01-07 \
    --end-date 2024-01-08 \
    --only-failed

# Clear specific task
airflow tasks clear electricity_price_ingestion \
    --task-regex "fetch_flatpeak" \
    --start-date 2024-01-07
```

### Pause/Unpause DAGs

```bash
# Pause for maintenance
airflow dags pause electricity_price_ingestion

# Resume
airflow dags unpause electricity_price_ingestion
```

### Trigger Manual Run

```bash
# Trigger with default config
airflow dags trigger electricity_price_ingestion

# Trigger with custom config
airflow dags trigger electricity_price_ingestion \
    --conf '{"manual_trigger": true}'
```

### View Logs

```bash
# Via CLI
airflow tasks logs electricity_price_ingestion fetch_flatpeak 2024-01-07

# Or access via UI: DAG > Task Instance > Log
```

## Troubleshooting

### Common Issues

#### 1. DAG Not Appearing in UI

**Symptoms**: New DAG not visible

**Solutions**:
```bash
# Check for import errors
airflow dags list-import-errors

# Trigger DAG rescan
airflow dags reserialize
```

#### 2. Tasks Stuck in Queued

**Symptoms**: Tasks remain in `queued` state

**Solutions**:
```bash
# Check scheduler is running
docker-compose logs airflow-scheduler | tail -50

# Check pool availability
airflow pools list

# Restart scheduler
docker-compose restart airflow-scheduler
```

#### 3. API Rate Limit Errors

**Symptoms**: 429 errors in task logs

**Solutions**:
1. Reduce pool size: `airflow pools set pricing_api_pool 3`
2. Add retry delay in default_args
3. Implement backoff in PricingAPIHook

#### 4. Database Connection Issues

**Symptoms**: `ConnectionRefusedError` or timeout

**Solutions**:
```bash
# Check TimescaleDB is running
docker-compose ps timescaledb

# Test connection
docker-compose exec timescaledb pg_isready

# Check connection pool settings in airflow.cfg
```

#### 5. Memory Issues During Training

**Symptoms**: OOM errors in model_retraining

**Solutions**:
1. Reduce training data window
2. Decrease batch size
3. Increase worker memory in docker-compose.yml

### Health Checks

```bash
# Airflow health
curl http://localhost:8080/health

# Scheduler health
airflow jobs check --job-type SchedulerJob

# Database health
airflow db check
```

## Scaling Considerations

### Current Setup (LocalExecutor)

Suitable for:
- 15-minute ingestion cycle
- 4 regions per API
- 6-hour weekly training

### When to Scale

Consider scaling when:
- Ingestion takes > 3 minutes consistently
- Training data exceeds 10GB
- Adding more regions/APIs

### Scaling Options

1. **CeleryExecutor**: Add worker containers
2. **KubernetesExecutor**: Run tasks as K8s pods
3. **Distributed Training**: Use Ray or Spark for ML

## Security Best Practices

1. **Rotate Fernet Key** regularly
2. **Use secrets backend** (AWS Secrets Manager, HashiCorp Vault)
3. **Enable RBAC** for multi-user access
4. **Network isolation** for sensitive connections
5. **Audit logging** for compliance

## Maintenance Schedule

| Task | Frequency | Description |
|------|-----------|-------------|
| Log rotation | Daily | Clean old logs |
| DB vacuum | Weekly | Optimize Airflow metadata |
| Pool review | Monthly | Adjust based on usage |
| Connection test | Monthly | Verify API connectivity |
| Model evaluation | Weekly | Review accuracy trends |

## Support

For issues:
1. Check this guide
2. Review Airflow logs
3. Consult data-quality DAG reports
4. Contact team at ml-team@electricity-optimizer.io
