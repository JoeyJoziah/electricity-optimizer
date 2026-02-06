#!/bin/bash

# Load Testing Runner Script
# Runs Locust load tests with predefined configurations

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Default values
HOST="${HOST:-http://localhost:8000}"
USERS="${USERS:-1000}"
SPAWN_RATE="${SPAWN_RATE:-50}"
RUN_TIME="${RUN_TIME:-5m}"
REPORT_DIR="${PROJECT_ROOT}/tests/load/reports"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Electricity Optimizer Load Test ===${NC}"
echo ""
echo "Configuration:"
echo "  Host: $HOST"
echo "  Users: $USERS"
echo "  Spawn Rate: $SPAWN_RATE users/second"
echo "  Duration: $RUN_TIME"
echo ""

# Create report directory
mkdir -p "$REPORT_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="${REPORT_DIR}/load_test_${TIMESTAMP}"

# Check if locust is installed
if ! command -v locust &> /dev/null; then
    echo -e "${RED}Error: locust is not installed${NC}"
    echo "Install with: pip install locust"
    exit 1
fi

# Check if backend is running
echo "Checking if backend is accessible..."
if ! curl -s "$HOST/health" > /dev/null 2>&1; then
    echo -e "${YELLOW}Warning: Backend may not be running at $HOST${NC}"
    echo "Start the backend with: docker-compose up -d backend"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Run different test scenarios
run_test() {
    local scenario="$1"
    local users="$2"
    local spawn="$3"
    local duration="$4"
    local report_name="${REPORT_FILE}_${scenario}"

    echo ""
    echo -e "${GREEN}Running scenario: $scenario${NC}"
    echo "  Users: $users, Spawn Rate: $spawn, Duration: $duration"

    locust -f "$SCRIPT_DIR/locustfile.py" \
        --headless \
        --users "$users" \
        --spawn-rate "$spawn" \
        --run-time "$duration" \
        --host "$HOST" \
        --html "${report_name}.html" \
        --csv "${report_name}" \
        2>&1 | tee "${report_name}.log"

    echo -e "${GREEN}Scenario $scenario complete. Report: ${report_name}.html${NC}"
}

# Parse command line arguments
case "${1:-full}" in
    quick)
        # Quick smoke test
        echo "Running quick smoke test..."
        run_test "quick" 50 10 "1m"
        ;;

    standard)
        # Standard load test
        echo "Running standard load test..."
        run_test "standard" 500 25 "3m"
        ;;

    full)
        # Full load test - 1000+ users
        echo "Running full load test..."
        run_test "full" "$USERS" "$SPAWN_RATE" "$RUN_TIME"
        ;;

    stress)
        # Stress test - find breaking point
        echo "Running stress test..."
        run_test "stress" 2000 100 "10m"
        ;;

    spike)
        # Spike test - sudden traffic increase
        echo "Running spike test..."
        # Start with low users
        run_test "spike_baseline" 100 50 "1m"
        # Spike to high users
        run_test "spike_peak" 1500 500 "2m"
        # Return to normal
        run_test "spike_recovery" 100 50 "1m"
        ;;

    endurance)
        # Endurance test - long running
        echo "Running endurance test (30 minutes)..."
        run_test "endurance" 500 25 "30m"
        ;;

    *)
        echo "Usage: $0 {quick|standard|full|stress|spike|endurance}"
        echo ""
        echo "Scenarios:"
        echo "  quick     - 50 users, 1 minute (smoke test)"
        echo "  standard  - 500 users, 3 minutes"
        echo "  full      - 1000 users, 5 minutes (default)"
        echo "  stress    - 2000 users, 10 minutes"
        echo "  spike     - Simulate traffic spike"
        echo "  endurance - 500 users, 30 minutes"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}=== Load Test Complete ===${NC}"
echo ""
echo "Reports saved to: $REPORT_DIR"
echo ""

# Print summary from last run
if [ -f "${REPORT_FILE}_stats.csv" ]; then
    echo "Summary Statistics:"
    echo "==================="
    tail -1 "${REPORT_FILE}_stats.csv" | while IFS=, read -r name requests failures median avg min max; do
        echo "  Total Requests: $requests"
        echo "  Failures: $failures"
        echo "  Median Response: ${median}ms"
        echo "  Average Response: ${avg}ms"
    done
fi
