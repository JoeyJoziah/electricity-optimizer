"""
Locust Load Testing Suite for Electricity Optimizer API

Simulates realistic user behavior patterns for load testing.
Target: 1000+ concurrent users with 99%+ success rate.
"""

from locust import HttpUser, task, between, TaskSet, tag, events
from locust.runners import MasterRunner
import random
import json
import time
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UnauthenticatedBehavior(TaskSet):
    """Tasks that don't require authentication."""

    @task(10)
    @tag('health')
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
    @tag('public')
    def get_public_prices(self):
        """Get public price overview (no auth required)."""
        regions = ['UK', 'EU', 'US']
        region = random.choice(regions)
        self.client.get(f"/api/v1/prices/overview?region={region}")


class AuthenticatedUserBehavior(TaskSet):
    """Tasks that require authentication."""

    def on_start(self):
        """Login when user starts."""
        self.token = None
        self.user_id = None
        self._login()

    def _login(self):
        """Authenticate and get JWT token."""
        user_id = random.randint(1, 10000)
        email = f"loadtest_{user_id}@example.com"

        response = self.client.post(
            '/api/v1/auth/signin',
            json={
                'email': email,
                'password': 'LoadTest123!'
            },
            name='/api/v1/auth/signin'
        )

        if response.status_code == 200:
            data = response.json()
            self.token = data.get('access_token')
            self.user_id = data.get('user', {}).get('id')
            self.headers = {'Authorization': f'Bearer {self.token}'}
        else:
            # Use mock token for testing without real auth
            self.token = f"mock_token_{user_id}"
            self.user_id = f"user_{user_id}"
            self.headers = {'Authorization': f'Bearer {self.token}'}

    @task(10)
    @tag('prices', 'critical')
    def get_current_prices(self):
        """Most common action - check current prices."""
        regions = ['UK', 'EU', 'US']
        region = random.choice(regions)

        with self.client.get(
            f'/api/v1/prices/current?region={region}',
            headers=self.headers,
            name='/api/v1/prices/current'
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if 'prices' in data or 'price' in data:
                    response.success()
            elif response.status_code == 401:
                # Re-authenticate if token expired
                self._login()

    @task(6)
    @tag('prices', 'critical')
    def get_forecast(self):
        """Get 24-hour forecast."""
        regions = ['UK', 'EU', 'US']
        region = random.choice(regions)
        hours = random.choice([12, 24, 48])

        with self.client.get(
            f'/api/v1/prices/forecast?region={region}&hours={hours}',
            headers=self.headers,
            name='/api/v1/prices/forecast'
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if 'forecast' in data:
                    response.success()

    @task(4)
    @tag('prices')
    def get_price_history(self):
        """Get historical price data."""
        regions = ['UK', 'EU', 'US']
        region = random.choice(regions)
        days = random.choice([1, 7, 30])

        self.client.get(
            f'/api/v1/prices/history?region={region}&days={days}',
            headers=self.headers,
            name='/api/v1/prices/history'
        )

    @task(4)
    @tag('suppliers')
    def get_suppliers(self):
        """Check supplier recommendations."""
        self.client.get(
            '/api/v1/suppliers?region=UK&active=true',
            headers=self.headers,
            name='/api/v1/suppliers'
        )

    @task(2)
    @tag('suppliers')
    def get_supplier_details(self):
        """Get specific supplier details."""
        supplier_ids = ['supplier_1', 'supplier_2', 'supplier_3']
        supplier_id = random.choice(supplier_ids)

        self.client.get(
            f'/api/v1/suppliers/{supplier_id}',
            headers=self.headers,
            name='/api/v1/suppliers/{id}'
        )

    @task(2)
    @tag('optimization', 'ml')
    def optimize_schedule(self):
        """Run load optimization (ML inference) - resource intensive."""
        appliances = [
            {
                'id': 'dishwasher',
                'power_kw': 1.5,
                'duration_hours': 2,
                'earliest_start': 18,
                'latest_end': 30,
                'flexible': True,
            }
        ]

        # Randomly add more appliances
        if random.random() > 0.5:
            appliances.append({
                'id': 'washing_machine',
                'power_kw': 2.0,
                'duration_hours': 2,
                'earliest_start': 20,
                'latest_end': 32,
                'flexible': True,
            })

        if random.random() > 0.7:
            appliances.append({
                'id': 'ev_charger',
                'power_kw': 7.0,
                'duration_hours': 4,
                'earliest_start': 23,
                'latest_end': 31,
                'flexible': True,
                'priority': 'high',
            })

        with self.client.post(
            '/api/v1/optimization/schedule',
            json={'appliances': appliances},
            headers=self.headers,
            name='/api/v1/optimization/schedule'
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if 'schedules' in data:
                    response.success()

    @task(1)
    @tag('user')
    def get_user_preferences(self):
        """Get user preferences."""
        self.client.get(
            '/api/v1/user/preferences',
            headers=self.headers,
            name='/api/v1/user/preferences'
        )

    @task(1)
    @tag('analytics')
    def get_savings_analytics(self):
        """Get savings analytics dashboard data."""
        self.client.get(
            '/api/v1/analytics/savings?period=monthly',
            headers=self.headers,
            name='/api/v1/analytics/savings'
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
        logger.debug(f"User started")


class PowerUser(HttpUser):
    """Power user who checks prices frequently."""

    wait_time = between(0.5, 2)  # More frequent requests

    @task(5)
    def check_current_prices(self):
        """Check current prices frequently."""
        regions = ['UK', 'EU', 'US']
        region = random.choice(regions)
        self.client.get(f'/api/v1/prices/current?region={region}')

    @task(3)
    def check_forecast(self):
        """Check forecast frequently."""
        self.client.get('/api/v1/prices/forecast?region=UK&hours=24')

    @task(2)
    def run_optimization(self):
        """Run optimization more frequently."""
        self.client.post(
            '/api/v1/optimization/schedule',
            json={
                'appliances': [
                    {'id': 'ev_charger', 'power_kw': 7.0, 'duration_hours': 4}
                ]
            }
        )


class APIConsumer(HttpUser):
    """API consumer (mobile app, integrations) with high request rate."""

    wait_time = between(0.1, 1)  # Fast request rate

    @task(10)
    def get_prices(self):
        """Fetch prices via API."""
        self.client.get('/api/v1/prices/current?region=UK')

    @task(5)
    def get_forecast(self):
        """Fetch forecast via API."""
        self.client.get('/api/v1/prices/forecast?region=UK&hours=24')


# Event handlers for custom metrics
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, **kwargs):
    """Track custom metrics for each request."""
    if response_time > 1000:  # Slow request (>1s)
        logger.warning(f"Slow request: {name} took {response_time}ms")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Log test start."""
    logger.info("Load test starting...")
    logger.info(f"Target host: {environment.host}")


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
        logger.info(f"Failure rate: {total_failures/total_requests*100:.2f}%")
        logger.info(f"Average response time: {avg_response:.2f}ms")
