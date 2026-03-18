"""
Locust Load Testing Suite for RateShift API

Simulates realistic user behavior patterns for load testing.
Target: 1000+ concurrent users with 99%+ success rate.

Region values must match the Region enum in backend/models/region.py:
- US states: 'us_ca', 'us_tx', 'us_ny', 'us_ct', etc.
- International: 'uk', 'de', 'fr', 'au', etc.

Auth: RateShift uses Better Auth — sign-in is handled by the Next.js
frontend at /api/auth/sign-in/email. The backend only validates sessions
via the neon_auth cookie. Load tests target the backend API directly, so
they use a pre-issued API token rather than going through the auth flow.

Skip guard: set the HOST environment variable to your target. The script
will exit immediately if the server is not reachable.
"""

from locust import HttpUser, task, between, TaskSet, tag, events
import random
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid Region values (subset of Region enum for load test distribution)
# Sourced from backend/models/region.py
# ---------------------------------------------------------------------------

US_REGIONS = [
    "us_ca",
    "us_tx",
    "us_ny",
    "us_ct",
    "us_fl",
    "us_il",
    "us_pa",
    "us_oh",
    "us_ga",
    "us_nc",
    "us_ma",
    "us_nj",
    "us_va",
    "us_wa",
    "us_co",
]

INTL_REGIONS = ["uk", "de", "fr", "au", "ca"]

ALL_REGIONS = US_REGIONS + INTL_REGIONS


class UnauthenticatedBehavior(TaskSet):
    """Tasks that don't require authentication."""

    @task(10)
    @tag("health")
    def health_check(self):
        """Check health endpoint - most common unauthenticated request."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    response.success()
                else:
                    response.failure(f"Unhealthy status: {data}")
            else:
                response.failure(f"Health check failed: {response.status_code}")

    @task(5)
    @tag("public")
    def get_public_prices(self):
        """Get public price overview (no auth required)."""
        region = random.choice(ALL_REGIONS)
        self.client.get(f"/api/v1/prices/overview?region={region}")


class AuthenticatedUserBehavior(TaskSet):
    """
    Tasks that require authentication.

    Note: Better Auth handles sign-in via the Next.js frontend
    (/api/auth/sign-in/email). The backend only validates sessions via the
    neon_auth cookie. For load testing the backend API directly, we use a
    pre-issued mock session cookie from the LOAD_TEST_SESSION_TOKEN
    environment variable (or fall back to a mock bearer token for
    development load tests against a local server).
    """

    def on_start(self):
        """Set up auth headers when user starts."""
        import os

        self.token = os.environ.get(
            "LOAD_TEST_SESSION_TOKEN", f"mock_token_{random.randint(1, 10000)}"
        )
        self.user_id = f"loadtest_user_{random.randint(1, 10000)}"
        # The backend accepts the neon_auth session cookie
        self.headers = {
            "Authorization": f"Bearer {self.token}",
        }

    @task(10)
    @tag("prices", "critical")
    def get_current_prices(self):
        """Most common action - check current prices."""
        region = random.choice(ALL_REGIONS)

        with self.client.get(
            f"/api/v1/prices/current?region={region}",
            headers=self.headers,
            name="/api/v1/prices/current",
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "prices" in data or "price" in data:
                    response.success()
            elif response.status_code == 401:
                # Session expired or not set up — log but do not re-auth
                logger.warning(
                    "Got 401 on prices/current — check LOAD_TEST_SESSION_TOKEN"
                )

    @task(6)
    @tag("prices", "critical")
    def get_forecast(self):
        """Get 24-hour forecast."""
        region = random.choice(US_REGIONS)  # Forecast is US-focused
        hours = random.choice([12, 24, 48])

        with self.client.get(
            f"/api/v1/prices/forecast?region={region}&hours={hours}",
            headers=self.headers,
            name="/api/v1/prices/forecast",
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "forecast" in data:
                    response.success()

    @task(4)
    @tag("prices")
    def get_price_history(self):
        """Get historical price data."""
        region = random.choice(ALL_REGIONS)
        days = random.choice([1, 7, 30])

        self.client.get(
            f"/api/v1/prices/history?region={region}&days={days}",
            headers=self.headers,
            name="/api/v1/prices/history",
        )

    @task(4)
    @tag("suppliers")
    def get_suppliers(self):
        """Check supplier recommendations."""
        region = random.choice(US_REGIONS)
        self.client.get(
            f"/api/v1/suppliers?region={region}&active=true",
            headers=self.headers,
            name="/api/v1/suppliers",
        )

    @task(2)
    @tag("suppliers")
    def get_supplier_details(self):
        """Get specific supplier details."""
        supplier_ids = ["supplier_1", "supplier_2", "supplier_3"]
        supplier_id = random.choice(supplier_ids)

        self.client.get(
            f"/api/v1/suppliers/{supplier_id}",
            headers=self.headers,
            name="/api/v1/suppliers/{id}",
        )

    @task(2)
    @tag("optimization", "ml")
    def optimize_schedule(self):
        """Run load optimization (ML inference) - resource intensive."""
        appliances = [
            {
                "id": "dishwasher",
                "power_kw": 1.5,
                "duration_hours": 2,
                "earliest_start": 18,
                "latest_end": 30,
                "flexible": True,
            }
        ]

        # Randomly add more appliances
        if random.random() > 0.5:
            appliances.append(
                {
                    "id": "washing_machine",
                    "power_kw": 2.0,
                    "duration_hours": 2,
                    "earliest_start": 20,
                    "latest_end": 32,
                    "flexible": True,
                }
            )

        if random.random() > 0.7:
            appliances.append(
                {
                    "id": "ev_charger",
                    "power_kw": 7.0,
                    "duration_hours": 4,
                    "earliest_start": 23,
                    "latest_end": 31,
                    "flexible": True,
                    "priority": "high",
                }
            )

        with self.client.post(
            "/api/v1/optimization/schedule",
            json={"appliances": appliances},
            headers=self.headers,
            name="/api/v1/optimization/schedule",
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "schedules" in data:
                    response.success()

    @task(1)
    @tag("user")
    def get_user_preferences(self):
        """Get user preferences."""
        self.client.get(
            "/api/v1/user/preferences",
            headers=self.headers,
            name="/api/v1/user/preferences",
        )

    @task(1)
    @tag("analytics")
    def get_savings_analytics(self):
        """Get savings analytics dashboard data."""
        self.client.get(
            "/api/v1/analytics/savings?period=monthly",
            headers=self.headers,
            name="/api/v1/analytics/savings",
        )


class MixedUserBehavior(TaskSet):
    """Mix of authenticated and unauthenticated behaviors."""

    tasks = {
        UnauthenticatedBehavior: 2,
        AuthenticatedUserBehavior: 8,
    }


class WebsiteUser(HttpUser):
    """Standard website user with typical browsing patterns."""

    tasks = [MixedUserBehavior]
    wait_time = between(1, 5)  # Wait 1-5 seconds between requests

    def on_start(self):
        """Log user start."""
        logger.debug("User started")


class PowerUser(HttpUser):
    """Power user who checks prices frequently."""

    wait_time = between(0.5, 2)  # More frequent requests

    @task(5)
    def check_current_prices(self):
        """Check current prices frequently."""
        region = random.choice(US_REGIONS)
        self.client.get(f"/api/v1/prices/current?region={region}")

    @task(3)
    def check_forecast(self):
        """Check forecast frequently."""
        self.client.get("/api/v1/prices/forecast?region=us_ct&hours=24")

    @task(2)
    def run_optimization(self):
        """Run optimization more frequently."""
        self.client.post(
            "/api/v1/optimization/schedule",
            json={
                "appliances": [
                    {"id": "ev_charger", "power_kw": 7.0, "duration_hours": 4}
                ]
            },
        )


class APIConsumer(HttpUser):
    """API consumer (mobile app, integrations) with high request rate."""

    wait_time = between(0.1, 1)  # Fast request rate

    @task(10)
    def get_prices(self):
        """Fetch prices via API."""
        region = random.choice(US_REGIONS)
        self.client.get(f"/api/v1/prices/current?region={region}")

    @task(5)
    def get_forecast(self):
        """Fetch forecast via API."""
        region = random.choice(US_REGIONS)
        self.client.get(f"/api/v1/prices/forecast?region={region}&hours=24")


# Event handlers for custom metrics
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, **kwargs):
    """Track custom metrics for each request."""
    if response_time > 1000:  # Slow request (>1s)
        logger.warning(f"Slow request: {name} took {response_time}ms")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Log test start and verify server is reachable."""
    import urllib.request
    import urllib.error

    host = environment.host
    health_url = f"{host}/health"
    logger.info("Load test starting...")
    logger.info(f"Target host: {host}")

    # Skip guard: fail fast if the server is not reachable
    try:
        req = urllib.request.urlopen(health_url, timeout=10)
        if req.status not in (200, 204):
            logger.error(
                f"Server health check returned {req.status} — is the backend running at {host}?"
            )
            environment.runner.quit()
    except urllib.error.URLError as exc:
        logger.error(
            f"Cannot reach {health_url}: {exc}. "
            f"Start the backend with: uvicorn main:app --host 0.0.0.0 --port 8000"
        )
        environment.runner.quit()
    except Exception as exc:
        logger.warning(f"Health check inconclusive ({exc}), continuing anyway")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Log test completion."""
    logger.info("Load test completed")

    # Log summary stats
    if environment.stats:
        total_requests = environment.stats.total.num_requests
        total_failures = environment.stats.total.num_failures
        avg_response = environment.stats.total.avg_response_time

        logger.info(f"Total requests: {total_requests}")
        logger.info(f"Total failures: {total_failures}")
        if total_requests > 0:
            logger.info(f"Failure rate: {total_failures / total_requests * 100:.2f}%")
        logger.info(f"Average response time: {avg_response:.2f}ms")
