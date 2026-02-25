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
    local host=${REDIS_HOST:-"localhost"}
    local port=${REDIS_PORT:-"6379"}
    local password=${REDIS_PASSWORD:-""}

    if [ -n "$password" ]; then
        result=$(redis-cli -h "$host" -p "$port" -a "$password" ping 2>/dev/null) || result=""
    else
        result=$(redis-cli -h "$host" -p "$port" ping 2>/dev/null) || result=""
    fi

    if [ "$result" = "PONG" ]; then
        print_status "Redis" "OK" "PONG received ($host:$port)"
        return 0
    else
        print_status "Redis" "FAIL" "No response ($host:$port)"
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

echo ""
echo "Frontend:"
check_service "Frontend" "http://localhost:3000" 200 || FAILED=$((FAILED + 1))

echo ""
echo "Data Services:"
check_redis || FAILED=$((FAILED + 1))

echo ""
echo "==========================================="
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All services are healthy!${NC}"
    exit 0
else
    echo -e "${RED}$FAILED service(s) failed health check${NC}"
    exit 1
fi
