#!/bin/bash
# =============================================================================
# Deployment Script for Electricity Optimizer
# =============================================================================
# Usage: ./scripts/deploy.sh [environment]
# Environments: development, staging, production
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ENVIRONMENT=${1:-"development"}
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# =============================================================================
# Pre-deployment Checks
# =============================================================================

pre_deploy_checks() {
    log_step "Running pre-deployment checks..."

    # Check Docker is running
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running"
        exit 1
    fi

    # Check .env file exists
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        log_error ".env file not found. Copy .env.example and configure."
        exit 1
    fi

    # Check required variables
    source "$PROJECT_DIR/.env"

    required_vars=("SUPABASE_URL" "SUPABASE_ANON_KEY" "JWT_SECRET" "POSTGRES_PASSWORD" "REDIS_PASSWORD")

    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            log_error "Required environment variable $var is not set"
            exit 1
        fi
    done

    log_info "Pre-deployment checks passed"
}

# =============================================================================
# Build Images
# =============================================================================

build_images() {
    log_step "Building Docker images..."

    cd "$PROJECT_DIR"

    if [ "$ENVIRONMENT" = "production" ]; then
        docker compose -f docker-compose.prod.yml build --no-cache
    else
        docker compose build
    fi

    log_info "Docker images built successfully"
}

# =============================================================================
# Run Tests
# =============================================================================

run_tests() {
    log_step "Running tests..."

    cd "$PROJECT_DIR"

    # Run backend tests
    log_info "Running backend tests..."
    docker compose run --rm backend pytest --cov=. --cov-report=term-missing -q || {
        log_error "Backend tests failed"
        exit 1
    }

    # Run ML tests
    log_info "Running ML tests..."
    cd ml && python -m pytest -q && cd ..

    log_info "All tests passed"
}

# =============================================================================
# Deploy
# =============================================================================

deploy() {
    log_step "Deploying to $ENVIRONMENT..."

    cd "$PROJECT_DIR"

    if [ "$ENVIRONMENT" = "production" ]; then
        COMPOSE_FILE="docker-compose.prod.yml"
    else
        COMPOSE_FILE="docker-compose.yml"
    fi

    # Pull latest images (for production)
    if [ "$ENVIRONMENT" = "production" ]; then
        log_info "Pulling latest images..."
        docker compose -f "$COMPOSE_FILE" pull
    fi

    # Start services
    log_info "Starting services..."
    docker compose -f "$COMPOSE_FILE" up -d

    # Wait for services to be healthy
    log_info "Waiting for services to be healthy..."
    sleep 30

    # Run health checks
    if bash "$PROJECT_DIR/scripts/health-check.sh"; then
        log_info "Deployment successful!"
    else
        log_error "Some services are not healthy"
        log_info "Check logs with: docker compose logs"
        exit 1
    fi
}

# =============================================================================
# Rollback
# =============================================================================

rollback() {
    log_warn "Rolling back deployment..."

    cd "$PROJECT_DIR"

    docker compose down

    # TODO: Implement rollback to previous version
    log_warn "Rollback not fully implemented"
}

# =============================================================================
# Post-deployment
# =============================================================================

post_deploy() {
    log_step "Running post-deployment tasks..."

    # Run database migrations (if any)
    # docker compose exec backend alembic upgrade head

    # Clear caches
    # docker compose exec redis redis-cli -a "$REDIS_PASSWORD" FLUSHALL

    log_info "Post-deployment tasks completed"
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "==========================================="
    echo "Electricity Optimizer - Deployment"
    echo "Environment: $ENVIRONMENT"
    echo "==========================================="
    echo ""

    pre_deploy_checks

    # Build images
    build_images

    # Run tests (skip in development for speed)
    if [ "$ENVIRONMENT" != "development" ]; then
        run_tests
    fi

    # Deploy
    deploy

    # Post-deployment tasks
    post_deploy

    echo ""
    echo "==========================================="
    echo -e "${GREEN}Deployment completed successfully!${NC}"
    echo "==========================================="
    echo ""
    echo "Service URLs:"
    echo "  - Frontend:   http://localhost:3000"
    echo "  - Backend:    http://localhost:8000"
    echo "  - API Docs:   http://localhost:8000/docs"
    echo "  - Airflow:    http://localhost:8080"
    echo "  - Grafana:    http://localhost:3001"
    echo "  - Prometheus: http://localhost:9090"
    echo ""
}

# Handle errors
trap 'log_error "Deployment failed!"; rollback' ERR

# Run main
main
