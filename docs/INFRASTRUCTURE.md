# Infrastructure Documentation - Electricity Optimizer

This document describes the infrastructure architecture, service dependencies, and operational procedures.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Service Catalog](#service-catalog)
3. [Network Architecture](#network-architecture)
4. [Resource Limits](#resource-limits)
5. [Monitoring Setup](#monitoring-setup)
6. [Scaling Guidelines](#scaling-guidelines)
7. [Cost Optimization](#cost-optimization)

---

## Architecture Overview

```
                              +------------------+
                              |    Internet      |
                              +--------+---------+
                                       |
                              +--------+---------+
                              |    Load Balancer |
                              |    (Nginx/Traefik)|
                              +--------+---------+
                                       |
                    +------------------+------------------+
                    |                                     |
           +--------+--------+                   +--------+--------+
           |    Frontend     |                   |    Backend API   |
           |   (Next.js 14)  |                   |   (FastAPI)      |
           |   Port: 3000    |                   |   Port: 8000     |
           +--------+--------+                   +--------+--------+
                    |                                     |
                    |              +----------------------+
                    |              |                      |
           +--------+--------+    +--------+--------+    +--------+--------+
           |    Supabase     |    |   TimescaleDB   |    |     Redis       |
           |   (Managed)     |    |   Port: 5432    |    |   Port: 6379    |
           +--------+--------+    +--------+--------+    +--------+--------+
                                           |
                              +------------+------------+
                              |                         |
                     +--------+--------+       +--------+--------+
                     | Airflow Web     |       | Airflow         |
                     | Port: 8080      |       | Scheduler       |
                     +-----------------+       +-----------------+
                              |
                     +--------+--------+
                     | Celery Workers  |
                     +-----------------+

           +------------------Monitoring------------------+
           |                                              |
           |  +-------------+  +-------------+            |
           |  | Prometheus  |  |   Grafana   |            |
           |  | Port: 9090  |  | Port: 3001  |            |
           |  +-------------+  +-------------+            |
           |                                              |
           +----------------------------------------------+
```

---

## Service Catalog

### Core Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| backend | custom | 8000 | FastAPI REST API |
| frontend | custom | 3000 | Next.js web application |
| redis | redis:7-alpine | 6379 | Caching and message queue |
| timescaledb | timescale/timescaledb:pg15 | 5432 | Time-series database |

### Airflow Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| airflow-webserver | custom (airflow) | 8080 | Airflow UI |
| airflow-scheduler | custom (airflow) | - | DAG scheduling |
| postgres-airflow | postgres:15-alpine | 5432 | Airflow metadata |

### Background Workers

| Service | Image | Purpose |
|---------|-------|---------|
| celery-worker | custom (backend) | Async task processing |

### Monitoring Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| prometheus | prom/prometheus | 9090 | Metrics collection |
| grafana | grafana/grafana | 3001 | Dashboards and alerting |
| node-exporter | prom/node-exporter | 9100 | System metrics |
| redis-exporter | oliver006/redis_exporter | 9121 | Redis metrics |
| postgres-exporter | prometheuscommunity/postgres-exporter | 9187 | PostgreSQL metrics |

---

## Network Architecture

### Docker Networks

```yaml
networks:
  electricity-optimizer:
    driver: bridge
    name: electricity-optimizer-network
```

All services communicate over the internal Docker bridge network. Only the following ports are exposed to the host:

| Port | Service | Access |
|------|---------|--------|
| 3000 | Frontend | Public |
| 8000 | Backend API | Public |
| 8080 | Airflow | Internal/VPN |
| 3001 | Grafana | Internal/VPN |
| 9090 | Prometheus | Internal only |

### Service Discovery

Services discover each other using Docker DNS:
- `http://backend:8000` - Backend API
- `postgresql://timescaledb:5432` - TimescaleDB
- `redis://redis:6379` - Redis

---

## Resource Limits

### Production Resource Allocation

| Service | CPU Limit | Memory Limit | CPU Reserved | Memory Reserved |
|---------|-----------|--------------|--------------|-----------------|
| backend | 1.0 | 512MB | 0.25 | 256MB |
| frontend | 0.5 | 256MB | 0.1 | 128MB |
| redis | 0.25 | 128MB | 0.1 | 64MB |
| timescaledb | 1.0 | 1GB | 0.25 | 512MB |
| airflow-webserver | 0.5 | 512MB | 0.1 | 256MB |
| airflow-scheduler | 0.5 | 512MB | 0.1 | 256MB |
| celery-worker | 0.5 | 256MB | 0.1 | 128MB |
| prometheus | 0.25 | 256MB | 0.1 | 128MB |
| grafana | 0.25 | 256MB | 0.1 | 128MB |

### Total Production Requirements

- **Minimum**: 2 CPU cores, 4GB RAM
- **Recommended**: 4 CPU cores, 8GB RAM
- **Storage**: 50GB SSD (for databases and logs)

---

## Monitoring Setup

### Metrics Collection

Prometheus scrapes metrics from all services:

```yaml
scrape_configs:
  - job_name: 'backend-api'
    targets: ['backend:8000']
    metrics_path: '/metrics'

  - job_name: 'redis'
    targets: ['redis-exporter:9121']

  - job_name: 'timescaledb'
    targets: ['postgres-exporter:9187']
```

### Key Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| `http_requests_total` | Total HTTP requests | - |
| `http_request_duration_seconds` | Request latency | p95 < 500ms |
| `forecast_mape` | ML model accuracy | < 10% |
| `price_data_last_update_timestamp` | Data freshness | < 15min |
| `redis_keyspace_hits_total` | Cache hits | > 80% hit rate |
| `pg_stat_database_numbackends` | DB connections | < 80% max |

### Alert Rules

Alerts are configured in `monitoring/alerts.yml`:

| Alert | Condition | Severity |
|-------|-----------|----------|
| HighAPILatency | p95 > 1s for 5m | Warning |
| HighErrorRate | > 5% for 5m | Critical |
| PriceDataStaleness | > 30min old | Warning |
| ModelForecastAccuracyDegraded | MAPE > 15% for 1h | Warning |
| HighDatabaseConnections | > 80% for 5m | Warning |
| ServiceDown | up == 0 for 2m | Critical |

### Grafana Dashboards

Pre-configured dashboards:

1. **Overview** - High-level service health
2. **API Performance** - Request rates, latency, errors
3. **Database** - TimescaleDB performance
4. **ML Models** - Forecast accuracy and inference times
5. **System Resources** - CPU, memory, disk

---

## Scaling Guidelines

### Horizontal Scaling

#### Backend API
```bash
# Scale to 3 replicas
docker compose up -d --scale backend=3
```

#### Celery Workers
```bash
# Scale workers for heavy workloads
docker compose up -d --scale celery-worker=4
```

### Vertical Scaling

Update resource limits in `docker-compose.prod.yml`:

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 1G
```

### When to Scale

| Condition | Action |
|-----------|--------|
| API latency > 500ms sustained | Scale backend horizontally |
| CPU > 80% sustained | Scale vertically or horizontally |
| Queue backlog growing | Scale Celery workers |
| DB connections > 80% | Increase connection pool |

---

## Cost Optimization

### Budget Target: $50/month

#### Current Allocation

| Component | Estimated Cost | Notes |
|-----------|----------------|-------|
| Supabase | $0 (free tier) | Up to 500MB storage |
| Self-hosted (VPS) | $20-40 | 4GB RAM, 2 vCPU |
| Domain + SSL | $0-10 | Let's Encrypt for SSL |
| **Total** | **$20-50** | Under budget |

### Cost-Saving Strategies

1. **Use Free Tiers**
   - Supabase free tier for auth and database
   - GitHub Actions free tier for CI/CD
   - Let's Encrypt for SSL certificates

2. **Self-Host Where Possible**
   - Run Prometheus/Grafana locally
   - Use Redis as cache (no managed service)
   - TimescaleDB on same VPS

3. **Resource Optimization**
   - Aggressive caching (5-min TTL)
   - Batch API calls
   - Compress data before storage

4. **Monitoring Costs**
   - Use `model-usage` skill to track costs
   - Set up alerts for cost anomalies
   - Review usage monthly

### Scaling Cost Impact

| Scale Action | Monthly Cost Impact |
|--------------|---------------------|
| Add 1 backend replica | +$10-15 |
| Double database size | +$5-10 |
| Add monitoring retention | +$0 (self-hosted) |

---

## Disaster Recovery

### Recovery Time Objectives

| Component | RTO | RPO |
|-----------|-----|-----|
| Frontend | 5 min | 0 |
| Backend API | 15 min | 0 |
| TimescaleDB | 30 min | 1 hour |
| Redis | 15 min | 24 hours |

### Backup Strategy

```bash
# Daily backup (cron)
0 2 * * * /app/scripts/backup.sh

# Weekly full backup
0 3 * * 0 /app/scripts/backup.sh --full
```

### Recovery Procedures

1. **Service Failure**: Docker auto-restarts (unless-stopped policy)
2. **Data Corruption**: Restore from backup
3. **Complete Failure**: Redeploy from Git + restore backups

---

## Security

### Network Security

- Internal services not exposed to public
- All public traffic through reverse proxy
- TLS 1.3 for all external connections

### Secrets Management

- Environment variables for non-sensitive config
- 1Password for production secrets
- Never commit secrets to Git

### Access Control

- Airflow/Grafana behind VPN or IP whitelist
- JWT authentication for API
- Role-based access control

---

**Last Updated**: 2026-02-06
