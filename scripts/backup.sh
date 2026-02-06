#!/bin/bash
# =============================================================================
# Database Backup Script for Electricity Optimizer
# =============================================================================
# Usage: ./scripts/backup.sh [--full]
# Creates backups of TimescaleDB and Redis data
# =============================================================================

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backups}"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=${RETENTION_DAYS:-7}
FULL_BACKUP=${1:-""}

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
# Create Backup Directory
# =============================================================================

create_backup_dir() {
    if [ ! -d "$BACKUP_DIR" ]; then
        mkdir -p "$BACKUP_DIR"
        log_info "Created backup directory: $BACKUP_DIR"
    fi
}

# =============================================================================
# PostgreSQL/TimescaleDB Backup
# =============================================================================

backup_postgres() {
    log_info "Starting TimescaleDB backup..."

    local backup_file="$BACKUP_DIR/timescaledb_${DATE}.sql.gz"

    # Get password from environment or .env
    source "$(dirname "$0")/../.env" 2>/dev/null || true

    docker exec timescaledb pg_dump \
        -U postgres \
        -d electricity \
        --no-owner \
        --no-privileges \
        | gzip > "$backup_file"

    if [ -f "$backup_file" ]; then
        local size=$(du -h "$backup_file" | cut -f1)
        log_info "TimescaleDB backup completed: $backup_file ($size)"
    else
        log_error "TimescaleDB backup failed"
        return 1
    fi
}

# =============================================================================
# Redis Backup
# =============================================================================

backup_redis() {
    log_info "Starting Redis backup..."

    local backup_file="$BACKUP_DIR/redis_${DATE}.rdb"

    source "$(dirname "$0")/../.env" 2>/dev/null || true

    # Trigger BGSAVE
    docker exec redis redis-cli -a "$REDIS_PASSWORD" BGSAVE

    # Wait for save to complete
    sleep 5

    # Copy the dump file
    docker cp redis:/data/dump.rdb "$backup_file"

    if [ -f "$backup_file" ]; then
        local size=$(du -h "$backup_file" | cut -f1)
        log_info "Redis backup completed: $backup_file ($size)"
    else
        log_warn "Redis backup may have failed - dump.rdb not found"
    fi
}

# =============================================================================
# Airflow Metadata Backup
# =============================================================================

backup_airflow() {
    log_info "Starting Airflow database backup..."

    local backup_file="$BACKUP_DIR/airflow_${DATE}.sql.gz"

    docker exec postgres-airflow pg_dump \
        -U airflow \
        -d airflow \
        --no-owner \
        --no-privileges \
        | gzip > "$backup_file"

    if [ -f "$backup_file" ]; then
        local size=$(du -h "$backup_file" | cut -f1)
        log_info "Airflow backup completed: $backup_file ($size)"
    else
        log_error "Airflow backup failed"
        return 1
    fi
}

# =============================================================================
# Cleanup Old Backups
# =============================================================================

cleanup_old_backups() {
    log_info "Cleaning up backups older than $RETENTION_DAYS days..."

    local count=$(find "$BACKUP_DIR" -type f -mtime +$RETENTION_DAYS | wc -l)

    find "$BACKUP_DIR" -type f -mtime +$RETENTION_DAYS -delete

    log_info "Removed $count old backup files"
}

# =============================================================================
# Verify Backups
# =============================================================================

verify_backups() {
    log_info "Verifying backups..."

    local errors=0

    # Check TimescaleDB backup
    latest_pg=$(ls -t "$BACKUP_DIR"/timescaledb_*.sql.gz 2>/dev/null | head -1)
    if [ -n "$latest_pg" ] && [ -s "$latest_pg" ]; then
        log_info "TimescaleDB backup verified: $latest_pg"
    else
        log_error "TimescaleDB backup verification failed"
        errors=$((errors + 1))
    fi

    # Check Redis backup
    latest_redis=$(ls -t "$BACKUP_DIR"/redis_*.rdb 2>/dev/null | head -1)
    if [ -n "$latest_redis" ] && [ -s "$latest_redis" ]; then
        log_info "Redis backup verified: $latest_redis"
    else
        log_warn "Redis backup verification failed"
    fi

    return $errors
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "==========================================="
    echo "Electricity Optimizer - Backup"
    echo "Date: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "==========================================="
    echo ""

    create_backup_dir

    # Always backup TimescaleDB
    backup_postgres

    # Backup Redis
    backup_redis

    # Full backup includes Airflow
    if [ "$FULL_BACKUP" = "--full" ]; then
        backup_airflow
    fi

    # Cleanup old backups
    cleanup_old_backups

    # Verify backups
    if verify_backups; then
        echo ""
        echo "==========================================="
        echo -e "${GREEN}Backup completed successfully!${NC}"
        echo "==========================================="
    else
        echo ""
        echo "==========================================="
        echo -e "${RED}Backup completed with errors${NC}"
        echo "==========================================="
        exit 1
    fi

    # List backup files
    echo ""
    echo "Backup files:"
    ls -lh "$BACKUP_DIR"/*.{sql.gz,rdb} 2>/dev/null | tail -10
}

# Run main
main
