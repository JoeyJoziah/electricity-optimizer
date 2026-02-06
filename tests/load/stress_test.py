"""
Database and API Stress Testing Suite

Performs targeted stress tests on:
- Database concurrent query handling
- API endpoint response under load
- Redis cache performance
- ML inference throughput
"""

import asyncio
import aiohttp
import time
import statistics
from dataclasses import dataclass
from typing import List, Dict, Any
import json


@dataclass
class StressTestResult:
    """Results from a stress test run."""

    total_requests: int
    successful_requests: int
    failed_requests: int
    latencies: List[float]
    errors: List[str]
    duration_seconds: float

    @property
    def success_rate(self) -> float:
        return self.successful_requests / self.total_requests * 100 if self.total_requests > 0 else 0

    @property
    def avg_latency(self) -> float:
        return statistics.mean(self.latencies) if self.latencies else 0

    @property
    def p50_latency(self) -> float:
        return statistics.median(self.latencies) if self.latencies else 0

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[idx]

    @property
    def p99_latency(self) -> float:
        if not self.latencies:
            return 0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[idx]

    @property
    def requests_per_second(self) -> float:
        return self.total_requests / self.duration_seconds if self.duration_seconds > 0 else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': f"{self.success_rate:.2f}%",
            'avg_latency_ms': f"{self.avg_latency * 1000:.2f}",
            'p50_latency_ms': f"{self.p50_latency * 1000:.2f}",
            'p95_latency_ms': f"{self.p95_latency * 1000:.2f}",
            'p99_latency_ms': f"{self.p99_latency * 1000:.2f}",
            'requests_per_second': f"{self.requests_per_second:.2f}",
            'duration_seconds': f"{self.duration_seconds:.2f}",
            'error_count': len(self.errors),
        }


async def make_request(
    session: aiohttp.ClientSession,
    url: str,
    method: str = 'GET',
    data: Dict = None,
    headers: Dict = None,
) -> tuple:
    """Make an async HTTP request and return (status, latency)."""
    start = time.time()
    try:
        if method == 'GET':
            async with session.get(url, headers=headers) as response:
                await response.text()
                latency = time.time() - start
                return response.status, latency, None
        else:
            async with session.post(url, json=data, headers=headers) as response:
                await response.text()
                latency = time.time() - start
                return response.status, latency, None
    except Exception as e:
        latency = time.time() - start
        return None, latency, str(e)


async def stress_test_endpoint(
    url: str,
    concurrent_requests: int = 1000,
    method: str = 'GET',
    data: Dict = None,
    headers: Dict = None,
    timeout: int = 30,
) -> StressTestResult:
    """
    Stress test a single endpoint with concurrent requests.

    Args:
        url: Target URL
        concurrent_requests: Number of simultaneous requests
        method: HTTP method (GET or POST)
        data: Request body for POST
        headers: Request headers
        timeout: Request timeout in seconds

    Returns:
        StressTestResult with performance metrics
    """
    connector = aiohttp.TCPConnector(limit=concurrent_requests)
    timeout_obj = aiohttp.ClientTimeout(total=timeout)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout_obj) as session:
        start_time = time.time()

        tasks = [
            make_request(session, url, method, data, headers)
            for _ in range(concurrent_requests)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        duration = time.time() - start_time

    latencies = []
    errors = []
    successful = 0
    failed = 0

    for result in results:
        if isinstance(result, Exception):
            failed += 1
            errors.append(str(result))
        else:
            status, latency, error = result
            latencies.append(latency)
            if status and 200 <= status < 300:
                successful += 1
            else:
                failed += 1
                if error:
                    errors.append(error)
                elif status:
                    errors.append(f"HTTP {status}")

    return StressTestResult(
        total_requests=concurrent_requests,
        successful_requests=successful,
        failed_requests=failed,
        latencies=latencies,
        errors=errors[:10],  # Keep only first 10 errors
        duration_seconds=duration,
    )


async def stress_test_database(
    base_url: str = 'http://localhost:8000',
    concurrent_requests: int = 1000,
) -> Dict[str, StressTestResult]:
    """
    Stress test database-heavy endpoints.

    Tests:
    - Current prices (read from cache/db)
    - Price history (database query)
    - Forecast (ML + cache)
    """
    results = {}

    print(f"\n{'='*60}")
    print(f"Database Stress Test - {concurrent_requests} concurrent requests")
    print(f"{'='*60}\n")

    # Test 1: Current prices (should hit cache)
    print("Testing: Current prices endpoint...")
    results['current_prices'] = await stress_test_endpoint(
        f'{base_url}/api/v1/prices/current?region=UK',
        concurrent_requests=concurrent_requests,
    )
    print(f"  Success rate: {results['current_prices'].success_rate:.2f}%")
    print(f"  p95 latency: {results['current_prices'].p95_latency * 1000:.2f}ms")

    # Test 2: Price history (database query)
    print("\nTesting: Price history endpoint...")
    results['price_history'] = await stress_test_endpoint(
        f'{base_url}/api/v1/prices/history?region=UK&days=7',
        concurrent_requests=concurrent_requests,
    )
    print(f"  Success rate: {results['price_history'].success_rate:.2f}%")
    print(f"  p95 latency: {results['price_history'].p95_latency * 1000:.2f}ms")

    # Test 3: Forecast (ML inference)
    print("\nTesting: Forecast endpoint...")
    results['forecast'] = await stress_test_endpoint(
        f'{base_url}/api/v1/prices/forecast?region=UK&hours=24',
        concurrent_requests=concurrent_requests,
    )
    print(f"  Success rate: {results['forecast'].success_rate:.2f}%")
    print(f"  p95 latency: {results['forecast'].p95_latency * 1000:.2f}ms")

    # Test 4: Suppliers (database read)
    print("\nTesting: Suppliers endpoint...")
    results['suppliers'] = await stress_test_endpoint(
        f'{base_url}/api/v1/suppliers?region=UK',
        concurrent_requests=concurrent_requests,
    )
    print(f"  Success rate: {results['suppliers'].success_rate:.2f}%")
    print(f"  p95 latency: {results['suppliers'].p95_latency * 1000:.2f}ms")

    return results


async def stress_test_ml_inference(
    base_url: str = 'http://localhost:8000',
    concurrent_requests: int = 100,
) -> StressTestResult:
    """
    Stress test ML inference endpoint.

    ML inference is more resource-intensive, so we use fewer concurrent requests.
    """
    print(f"\n{'='*60}")
    print(f"ML Inference Stress Test - {concurrent_requests} concurrent requests")
    print(f"{'='*60}\n")

    data = {
        'appliances': [
            {
                'id': 'dishwasher',
                'power_kw': 1.5,
                'duration_hours': 2,
                'earliest_start': 18,
                'latest_end': 30,
                'flexible': True,
            },
            {
                'id': 'washing_machine',
                'power_kw': 2.0,
                'duration_hours': 2,
                'earliest_start': 20,
                'latest_end': 32,
                'flexible': True,
            },
        ]
    }

    result = await stress_test_endpoint(
        f'{base_url}/api/v1/optimization/schedule',
        concurrent_requests=concurrent_requests,
        method='POST',
        data=data,
        timeout=60,  # ML inference may take longer
    )

    print(f"ML Optimization Results:")
    print(f"  Success rate: {result.success_rate:.2f}%")
    print(f"  Average latency: {result.avg_latency * 1000:.2f}ms")
    print(f"  p95 latency: {result.p95_latency * 1000:.2f}ms")
    print(f"  p99 latency: {result.p99_latency * 1000:.2f}ms")
    print(f"  Throughput: {result.requests_per_second:.2f} req/s")

    return result


async def run_full_stress_test(
    base_url: str = 'http://localhost:8000',
    db_concurrent: int = 1000,
    ml_concurrent: int = 100,
) -> Dict[str, Any]:
    """Run complete stress test suite."""
    print("\n" + "=" * 70)
    print("ELECTRICITY OPTIMIZER - FULL STRESS TEST")
    print("=" * 70)

    all_results = {}

    # Database stress tests
    db_results = await stress_test_database(base_url, db_concurrent)
    all_results['database'] = {k: v.to_dict() for k, v in db_results.items()}

    # ML inference stress test
    ml_result = await stress_test_ml_inference(base_url, ml_concurrent)
    all_results['ml_inference'] = ml_result.to_dict()

    # Print summary
    print("\n" + "=" * 70)
    print("STRESS TEST SUMMARY")
    print("=" * 70)

    # Check pass/fail criteria
    passed = True
    for name, result in db_results.items():
        status = "PASS" if result.success_rate >= 99 and result.p95_latency < 0.5 else "FAIL"
        if status == "FAIL":
            passed = False
        print(f"\n{name}:")
        print(f"  Status: {status}")
        print(f"  Success Rate: {result.success_rate:.2f}% (target: >99%)")
        print(f"  p95 Latency: {result.p95_latency * 1000:.2f}ms (target: <500ms)")

    ml_status = "PASS" if ml_result.success_rate >= 95 and ml_result.p95_latency < 2.0 else "FAIL"
    if ml_status == "FAIL":
        passed = False

    print(f"\nML Inference:")
    print(f"  Status: {ml_status}")
    print(f"  Success Rate: {ml_result.success_rate:.2f}% (target: >95%)")
    print(f"  p95 Latency: {ml_result.p95_latency * 1000:.2f}ms (target: <2000ms)")

    print("\n" + "=" * 70)
    print(f"OVERALL RESULT: {'PASS' if passed else 'FAIL'}")
    print("=" * 70)

    all_results['overall_passed'] = passed
    return all_results


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Run stress tests')
    parser.add_argument('--host', default='http://localhost:8000', help='Target host')
    parser.add_argument('--db-concurrent', type=int, default=1000, help='DB test concurrent requests')
    parser.add_argument('--ml-concurrent', type=int, default=100, help='ML test concurrent requests')
    parser.add_argument('--output', default=None, help='Output JSON file')

    args = parser.parse_args()

    results = asyncio.run(run_full_stress_test(
        base_url=args.host,
        db_concurrent=args.db_concurrent,
        ml_concurrent=args.ml_concurrent,
    ))

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {args.output}")
