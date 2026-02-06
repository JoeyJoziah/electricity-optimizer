#!/bin/bash
# =============================================================================
# Database Restore Script for Electricity Optimizer
# =============================================================================
# Usage: ./scripts/restore.sh [backup_file]
# Restores TimescaleDB and Redis data from backup
# =============================================================================

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_FILE=${1:-""}

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# =============================================================================
# Restore PostgreSQL/TimescaleDB
# =============================================================================

restore_postgres() {
    local backup_file=$1

    if [ -z "$backup_file" ]; then
        # Find latest backup
        backup_file=$(ls -t "$BACKUP_DIR"/timescaledb_*.sql.gz 2>/dev/null | head -1)
    fi

    if [ ! -f "$backup_file" ]; then
        log_error "Backup file not found: $backup_file"
        return 1
    fi

    log_info "Restoring TimescaleDB from: $backup_file"

    # Stop services that depend on the database
    docker compose stop backend celery-worker airflow-scheduler

    # Drop and recreate database
    docker exec timescaledb psql -U postgres -c "DROP DATABASE IF EXISTS electricity;"
    docker exec timescaledb psql -U postgres -c "CREATE DATABASE electricity;"

    # Restore backup
    gunzip -c "$backup_file" | docker exec -i timescaledb psql -U postgres -d electricity

    log_info "TimescaleDB restore completed"

    # Restart services
    docker compose start backend celery-worker airflow-scheduler
}

# =============================================================================
# Restore Redis
# =============================================================================

restore_redis() {
    local backup_file=$1

    if [ -z "$backup_file" ]; then
        # Find latest backup
        backup_file=$(ls -t "$BACKUP_DIR"/redis_*.rdb 2>/dev/null | head -1)
    fi

    if [ ! -f "$backup_file" ]; then
        log_warn "Redis backup file not found: $backup_file"
        return 0
    fi

    log_info "Restoring Redis from: $backup_file"

    # Stop Redis
    docker compose stop redis

    # Copy backup file
    docker cp "$backup_file" redis:/data/dump.rdb

    # Restart Redis
    docker compose start redis

    log_info "Redis restore completed"
}

# =============================================================================
# Restore Airflow
# =============================================================================

restore_airflow() {
    local backup_file=$1

    if [ -z "$backup_file" ]; then
        # Find latest backup
        backup_file=$(ls -t "$BACKUP_DIR"/airflow_*.sql.gz 2>/dev/null | head -1)
    fi

    if [ ! -f "$backup_file" ]; then
        log_warn "Airflow backup file not found"
        return 0
    fi

    log_info "Restoring Airflow from: $backup_file"

    # Stop Airflow services
    docker compose stop airflow-webserver airflow-scheduler

    # Drop and recreate database
    docker exec postgres-airflow psql -U airflow -c "DROP DATABASE IF EXISTS airflow;"
    docker exec postgres-airflow psql -U airflow -c "CREATE DATABASE airflow;"

    # Restore backup
    gunzip -c "$backup_file" | docker exec -i postgres-airflow psql -U airflow -d airflow

    log_info "Airflow restore completed"

    # Restart Airflow services
    docker compose start airflow-webserver airflow-scheduler
}

# =============================================================================
# List Available Backups
# =============================================================================

list_backups() {
    echo ""
    echo "Available backups:"
    echo ""

    echo "TimescaleDB:"
    ls -lh "$BACKUP_DIR"/timescaledb_*.sql.gz 2>/dev/null | tail -5 || echo "  No backups found"

    echo ""
    echo "Redis:"
    ls -lh "$BACKUP_DIR"/redis_*.rdb 2>/dev/null | tail -5 || echo "  No backups found"

    echo ""
    echo "Airflow:"
    ls -lh "$BACKUP_DIR"/airflow_*.sql.gz 2>/dev/null | tail -5 || echo "  No backups found"
    echo ""
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "==========================================="
    echo "Electricity Optimizer - Restore"
    echo "Date: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "==========================================="

    # List available backups
    list_backups

    # Confirm restore
    echo -e "${YELLOW}WARNING: This will overwrite existing data!${NC}"
    read -p "Are you sure you want to restore? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        log_info "Restore cancelled"
        exit 0
    fi

    # Restore databases
    restore_postgres "$BACKUP_FILE"
    restore_redis

    # Optionally restore Airflow
    read -p "Restore Airflow database? (yes/no): " restore_af
    if [ "$restore_af" = "yes" ]; then
        restore_airflow
    fi

    echo ""
    echo "==========================================="
    echo -e "${GREEN}Restore completed!${NC}"
    echo "==========================================="

    # Verify services are healthy
    log_info "Running health checks..."
    sleep 10
    bash "$(dirname "$0")/health-check.sh"
}

# Run main
main
