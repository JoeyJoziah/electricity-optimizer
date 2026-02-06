#!/bin/bash
# =============================================================================
# Health Check Script for All Services
# =============================================================================
# This script verifies all services are running and healthy
# Usage: ./scripts/health-check.sh [--verbose]
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

VERBOSE=${1:-""}

print_status() {
    local service=$1
    local status=$2
    local message=$3

    if [ "$status" = "OK" ]; then
        echo -e "${GREEN}[OK]${NC}     $service - $message"
    elif [ "$status" = "WARN" ]; then
        echo -e "${YELLOW}[WARN]${NC}   $service - $message"
    else
        echo -e "${RED}[FAIL]${NC}   $service - $message"
    fi
}

check_service() {
    local name=$1
    local url=$2
    local expected_code=${3:-200}

    response=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null) || response="000"

    if [ "$response" = "$expected_code" ]; then
        print_status "$name" "OK" "HTTP $response"
        return 0
    else
        print_status "$name" "FAIL" "Expected HTTP $expected_code, got $response"
        return 1
    fi
}

check_redis() {
    local password=${REDIS_PASSWORD:-""}

    if [ -n "$password" ]; then
        result=$(redis-cli -h localhost -p 6380 -a "$password" ping 2>/dev/null) || result=""
    else
        result=$(redis-cli -h localhost -p 6380 ping 2>/dev/null) || result=""
    fi

    if [ "$result" = "PONG" ]; then
        print_status "Redis" "OK" "PONG received"
        return 0
    else
        print_status "Redis" "FAIL" "No response"
        return 1
    fi
}

check_postgres() {
    result=$(pg_isready -h localhost -p 5433 -U postgres 2>/dev/null) || result=""

    if echo "$result" | grep -q "accepting connections"; then
        print_status "TimescaleDB" "OK" "Accepting connections"
        return 0
    else
        print_status "TimescaleDB" "FAIL" "Not ready"
        return 1
    fi
}

# =============================================================================
# Main Health Check
# =============================================================================

echo "==========================================="
echo "Electricity Optimizer - Health Check"
echo "==========================================="
echo ""

FAILED=0

# Backend API
echo "API Services:"
check_service "Backend API" "http://localhost:8000/health" 200 || FAILED=$((FAILED + 1))
check_service "Backend Docs" "http://localhost:8000/docs" 200 || FAILED=$((FAILED + 1))

echo ""
echo "Frontend:"
check_service "Frontend" "http://localhost:3000" 200 || FAILED=$((FAILED + 1))

echo ""
echo "Airflow:"
check_service "Airflow Web" "http://localhost:8080/health" 200 || FAILED=$((FAILED + 1))

echo ""
echo "Data Services:"
check_redis || FAILED=$((FAILED + 1))
check_postgres || FAILED=$((FAILED + 1))

echo ""
echo "Monitoring:"
check_service "Prometheus" "http://localhost:9090/-/healthy" 200 || FAILED=$((FAILED + 1))
check_service "Grafana" "http://localhost:3001/api/health" 200 || FAILED=$((FAILED + 1))

echo ""
echo "Exporters:"
check_service "Node Exporter" "http://localhost:9100/metrics" 200 || FAILED=$((FAILED + 1))
check_service "Redis Exporter" "http://localhost:9121/metrics" 200 || FAILED=$((FAILED + 1))
check_service "Postgres Exporter" "http://localhost:9187/metrics" 200 || FAILED=$((FAILED + 1))

echo ""
echo "==========================================="
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All services are healthy!${NC}"
    exit 0
else
    echo -e "${RED}$FAILED service(s) failed health check${NC}"
    exit 1
fi
