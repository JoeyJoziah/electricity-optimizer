# Deployment Guide - Electricity Optimizer

This guide covers how to deploy the Electricity Optimizer platform in different environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development](#local-development)
3. [Staging Deployment](#staging-deployment)
4. [Production Deployment](#production-deployment)
5. [Rollback Procedures](#rollback-procedures)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Tools

- **Docker**: 20.10+ with Docker Compose 2.0+
- **Git**: For version control
- **Make**: For running common commands (optional but recommended)

### Required Accounts

- **Supabase**: For managed PostgreSQL and authentication
- **GitHub**: For CI/CD and container registry

### API Keys

Obtain API keys from the following providers:
- Flatpeak API (UK/EU electricity prices)
- NREL API (US utility rates)
- IEA API (Global statistics)

```
# Email Service (SendGrid primary, SMTP fallback)
SENDGRID_API_KEY=          # SendGrid API key for welcome emails
SMTP_HOST=                 # SMTP server hostname (fallback)
SMTP_PORT=587              # SMTP port (fallback)
SMTP_USERNAME=             # SMTP username (fallback)
SMTP_PASSWORD=             # SMTP password (fallback)
EMAIL_FROM_ADDRESS=noreply@electricity-optimizer.app

# ML Model Path
MODEL_PATH=                # Path to trained model directory (optional)
```

---

## Local Development

### Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/your-org/electricity-optimizer.git
cd electricity-optimizer

# 2. Copy environment file and configure
cp .env.example .env
# Edit .env with your credentials

# 3. Start all services
make setup

# Or manually:
docker compose up -d
```

### Verify Services

```bash
# Run health checks
make health

# Or manually:
./scripts/health-check.sh
```

### Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | - |
| Backend API | http://localhost:8000 | - |
| API Docs | http://localhost:8000/docs | - |
| Airflow | http://localhost:8080 | admin/admin |
| Grafana | http://localhost:3001 | admin/GRAFANA_PASSWORD |
| Prometheus | http://localhost:9090 | - |

> **Note:** The backend includes a live email service at `backend/services/email_service.py` that handles welcome and notification emails via SendGrid (with SMTP fallback). Ensure the email environment variables above are configured before using email features.

### Development Workflow

```bash
# View logs
make logs

# Run tests
make test

# Format code
make format

# Restart services
make restart
```

---

## Staging Deployment

Staging deployment is triggered automatically when code is merged to the `develop` branch.

### Manual Staging Deployment

```bash
# Deploy to staging
make deploy-staging

# Or trigger via GitHub Actions
gh workflow run deploy-staging.yml
```

### Staging Environment

- URL: https://staging.electricity-optimizer.com
- Container Registry: ghcr.io/your-org/electricity-optimizer

### Verification

1. Check GitHub Actions workflow status
2. Verify health endpoints
3. Run smoke tests
4. Check Grafana dashboards

---

## Production Deployment

Production deployment is triggered when a release is published on GitHub.

### Deployment Steps

1. **Create a Release**
   ```bash
   # Create and push a tag
   git tag -a v1.0.0 -m "Release v1.0.0"
   git push origin v1.0.0

   # Create release on GitHub
   gh release create v1.0.0 --title "v1.0.0" --notes "Release notes here"
   ```

2. **Monitor Deployment**
   - Watch GitHub Actions workflow
   - Monitor Grafana dashboards
   - Check error tracking (Sentry)

3. **Verify Deployment**
   ```bash
   # Check production health
   curl https://electricity-optimizer.com/api/v1/health
   ```

### Production Checklist

Before deploying to production:

- [ ] All tests passing in CI
- [ ] Security scan passed
- [ ] Database migrations tested
- [ ] Backup created
- [ ] Rollback plan documented
- [ ] Team notified

### Blue-Green Deployment

The CI/CD pipeline supports blue-green deployment:

1. New version deployed to "green" environment
2. Health checks run on green
3. Traffic switched from blue to green
4. Blue kept for rollback

---

## Rollback Procedures

### Automatic Rollback

If smoke tests fail, the CI/CD pipeline automatically rolls back to the previous version.

### Manual Rollback

```bash
# SSH to production server
ssh user@production-server

# Rollback to previous version
cd /app/electricity-optimizer

# Option 1: Use previous image tag
docker compose -f docker-compose.prod.yml pull
export VERSION=v0.9.0  # Previous version
docker compose -f docker-compose.prod.yml up -d

# Option 2: Restore from backup
./scripts/restore.sh
```

### Database Rollback

```bash
# Restore database from backup
./scripts/restore.sh /backups/timescaledb_YYYYMMDD.sql.gz
```

---

## Troubleshooting

### Common Issues

#### Services Not Starting

```bash
# Check logs
docker compose logs backend
docker compose logs frontend

# Check health status
docker compose ps

# Restart specific service
docker compose restart backend
```

#### Database Connection Issues

```bash
# Test database connection
docker compose exec timescaledb pg_isready -U postgres

# Check connection from backend
docker compose exec backend python -c "from config.database import engine; print('OK')"
```

#### Redis Connection Issues

```bash
# Test Redis connection
docker compose exec redis redis-cli -a $REDIS_PASSWORD ping

# Check Redis memory
docker compose exec redis redis-cli -a $REDIS_PASSWORD INFO memory
```

#### Airflow DAGs Not Running

```bash
# Check scheduler logs
docker compose logs airflow-scheduler

# Trigger DAG manually
docker compose exec airflow-webserver airflow dags trigger electricity_price_ingestion
```

### Performance Issues

```bash
# Check resource usage
docker stats

# Check Prometheus metrics
curl http://localhost:9090/api/v1/query?query=up

# View Grafana dashboards
open http://localhost:3001
```

### Getting Help

1. Check the logs: `make logs`
2. Review Grafana dashboards
3. Check GitHub Issues
4. Contact the development team

---

## Security Considerations

### Secrets Management

- Never commit secrets to version control
- Use 1Password for production secrets
- Rotate keys every 90 days

### Network Security

- All services communicate over internal Docker network
- Only frontend and backend ports exposed
- TLS/SSL required for production

### Access Control

- Use environment-specific credentials
- Limit production access to authorized personnel
- Enable audit logging

---

## Backup Schedule

| Backup Type | Frequency | Retention |
|-------------|-----------|-----------|
| TimescaleDB | Daily | 7 days |
| Redis | Daily | 7 days |
| Full (all databases) | Weekly | 30 days |

Run manual backup:
```bash
make backup
make backup-full  # Include Airflow
```

---

## Monitoring

### Key Metrics

| Metric | Warning | Critical |
|--------|---------|----------|
| API Latency (p95) | > 500ms | > 1s |
| Error Rate | > 1% | > 5% |
| DB Connections | > 80% | > 95% |
| Memory Usage | > 80% | > 95% |
| Price Data Age | > 15min | > 30min |
| Model MAPE | > 10% | > 15% |

### Alerts

Alerts are configured in `monitoring/alerts.yml` and sent to:
- Slack (if configured)
- Email (if configured)
- Grafana notification channels

---

**Last Updated**: 2026-02-06
