#!/bin/bash
# =============================================================================
# Docker Entrypoint Script for Backend Service
# =============================================================================
# This script initializes the backend service:
# 1. Waits for required services (PostgreSQL, Redis)
# 2. Runs database migrations
# 3. Starts the application
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# =============================================================================
# Wait for Services
# =============================================================================

wait_for_postgres() {
    log_info "Waiting for TimescaleDB to be ready..."
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if pg_isready -h timescaledb -p 5432 -U postgres > /dev/null 2>&1; then
            log_info "TimescaleDB is ready!"
            return 0
        fi
        log_warn "Attempt $attempt/$max_attempts: TimescaleDB not ready yet..."
        sleep 2
        attempt=$((attempt + 1))
    done

    log_error "TimescaleDB failed to become ready after $max_attempts attempts"
    return 1
}

wait_for_redis() {
    log_info "Waiting for Redis to be ready..."
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if redis-cli -h redis -a "${REDIS_PASSWORD}" ping > /dev/null 2>&1; then
            log_info "Redis is ready!"
            return 0
        fi
        log_warn "Attempt $attempt/$max_attempts: Redis not ready yet..."
        sleep 2
        attempt=$((attempt + 1))
    done

    log_error "Redis failed to become ready after $max_attempts attempts"
    return 1
}

# =============================================================================
# Database Migrations
# =============================================================================

run_migrations() {
    log_info "Running database migrations..."

    # Check if alembic.ini exists
    if [ -f "alembic.ini" ]; then
        alembic upgrade head
        log_info "Migrations completed successfully!"
    else
        log_warn "No alembic.ini found, skipping migrations"
    fi
}

# =============================================================================
# Health Check
# =============================================================================

create_health_endpoint() {
    log_info "Verifying health endpoint..."
    # The FastAPI app should have a /health endpoint defined
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    log_info "Starting Electricity Optimizer Backend..."
    log_info "Environment: ${ENVIRONMENT:-development}"

    # Wait for dependencies
    wait_for_postgres
    wait_for_redis

    # Run migrations (only in production)
    if [ "${ENVIRONMENT}" = "production" ]; then
        run_migrations
    fi

    # Start the application
    log_info "Starting FastAPI application..."

    if [ "${ENVIRONMENT}" = "production" ]; then
        # Production: multiple workers, no reload
        exec uvicorn main:app \
            --host 0.0.0.0 \
            --port 8000 \
            --workers 4 \
            --no-access-log
    else
        # Development: single worker with reload
        exec uvicorn main:app \
            --host 0.0.0.0 \
            --port 8000 \
            --reload
    fi
}

# Handle signals gracefully
trap 'log_info "Shutting down..."; exit 0' SIGTERM SIGINT

# Run main function
main "$@"
