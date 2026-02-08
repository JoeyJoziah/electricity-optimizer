#!/bin/bash
# Production startup script for free tier deployment
# Optimized for Render.com (512MB RAM, single worker)

set -e  # Exit on error

echo "🚀 Starting Electricity Optimizer API..."
echo "Environment: ${ENVIRONMENT:-production}"
echo "Port: ${PORT:-8000}"

# Validate required environment variables
if [ "$ENVIRONMENT" = "production" ]; then
    if [ -z "$DATABASE_URL" ] && [ -z "$TIMESCALEDB_URL" ]; then
        echo "❌ ERROR: DATABASE_URL or TIMESCALEDB_URL required in production"
        exit 1
    fi
fi

# Use uvicorn directly for free tier (lighter than gunicorn)
# For production with more resources, use: gunicorn -c gunicorn_config.py main:app
echo "Starting with uvicorn (optimized for free tier)..."

exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1 \
    --log-level info \
    --no-access-log \
    --timeout-keep-alive 5 \
    --limit-concurrency 50 \
    --limit-max-requests 1000 \
    --backlog 100
