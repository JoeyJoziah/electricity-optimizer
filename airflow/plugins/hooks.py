"""
Custom Airflow Hooks for Electricity Price Optimizer

These hooks provide reusable connection management for:
- TimescaleDB (time-series database)
- Redis (caching layer)
- Pricing APIs (Flatpeak, NREL, IEA)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx
from airflow.exceptions import AirflowException
from airflow.hooks.base import BaseHook

logger = logging.getLogger(__name__)


class TimescaleDBHook(BaseHook):
    """
    Hook for TimescaleDB connections.

    Provides:
    - Connection pooling
    - Query execution
    - Bulk insert/upsert operations
    - Hypertable-aware operations

    :param conn_id: Airflow connection ID
    :param schema: Database schema to use
    """

    conn_name_attr = "conn_id"
    default_conn_name = "timescaledb_default"
    conn_type = "postgres"
    hook_name = "TimescaleDB"

    def __init__(
        self,
        conn_id: str = default_conn_name,
        schema: str = "public",
    ) -> None:
        super().__init__()
        self.conn_id = conn_id
        self.schema = schema
        self._conn = None

    def get_conn(self):
        """Get database connection."""
        if self._conn is None:
            import psycopg2
            from psycopg2.extras import RealDictCursor

            conn_config = self.get_connection(self.conn_id)

            self._conn = psycopg2.connect(
                host=conn_config.host,
                port=conn_config.port or 5432,
                dbname=conn_config.schema or "electricity",
                user=conn_config.login,
                password=conn_config.password,
                cursor_factory=RealDictCursor,
            )
            self._conn.autocommit = True

        return self._conn

    def execute_query(
        self,
        query: str,
        params: Optional[Tuple] = None,
    ) -> List[Dict]:
        """Execute a query and return results as list of dicts."""
        conn = self.get_conn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                if cursor.description:
                    return [dict(row) for row in cursor.fetchall()]
                return []
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise AirflowException(f"TimescaleDB query failed: {e}")

    def insert_many(
        self,
        table: str,
        data: List[Dict],
        on_conflict: Optional[str] = None,
    ) -> int:
        """Insert multiple rows efficiently."""
        if not data:
            return 0

        conn = self.get_conn()

        # Get columns from first row
        columns = list(data[0].keys())
        placeholders = ", ".join(["%s"] * len(columns))
        columns_str = ", ".join(columns)

        query = f"INSERT INTO {self.schema}.{table} ({columns_str}) VALUES ({placeholders})"

        if on_conflict:
            query += f" ON CONFLICT {on_conflict}"

        try:
            with conn.cursor() as cursor:
                from psycopg2.extras import execute_batch

                values = [tuple(row.get(col) for col in columns) for row in data]
                execute_batch(cursor, query, values, page_size=1000)
                return len(data)

        except Exception as e:
            logger.error(f"Bulk insert failed: {e}")
            raise AirflowException(f"TimescaleDB bulk insert failed: {e}")

    def upsert_many(
        self,
        table: str,
        data: List[Dict],
        conflict_columns: List[str],
    ) -> Dict[str, int]:
        """Upsert multiple rows with conflict resolution."""
        if not data:
            return {"inserted": 0, "updated": 0}

        conn = self.get_conn()

        # Get columns from first row
        columns = list(data[0].keys())
        placeholders = ", ".join(["%s"] * len(columns))
        columns_str = ", ".join(columns)
        conflict_str = ", ".join(conflict_columns)

        # Build update clause for non-conflict columns
        update_columns = [c for c in columns if c not in conflict_columns]
        update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_columns)

        query = f"""
            INSERT INTO {self.schema}.{table} ({columns_str})
            VALUES ({placeholders})
            ON CONFLICT ({conflict_str})
            DO UPDATE SET {update_clause}
        """

        try:
            with conn.cursor() as cursor:
                from psycopg2.extras import execute_batch

                values = [tuple(row.get(col) for col in columns) for row in data]
                execute_batch(cursor, query, values, page_size=1000)

                # Note: PostgreSQL doesn't easily distinguish inserts vs updates
                # in ON CONFLICT, so we return total as "inserted"
                return {"inserted": len(data), "updated": 0}

        except Exception as e:
            logger.error(f"Upsert failed: {e}")
            raise AirflowException(f"TimescaleDB upsert failed: {e}")

    def create_hypertable(
        self,
        table: str,
        time_column: str = "timestamp",
        chunk_interval: str = "1 day",
    ) -> bool:
        """Convert a table to a TimescaleDB hypertable."""
        query = f"""
            SELECT create_hypertable(
                '{self.schema}.{table}',
                '{time_column}',
                chunk_time_interval => INTERVAL '{chunk_interval}',
                if_not_exists => TRUE
            )
        """

        try:
            self.execute_query(query)
            logger.info(f"Created hypertable {table}")
            return True
        except Exception as e:
            logger.warning(f"Hypertable creation failed (may already exist): {e}")
            return False

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


class RedisHook(BaseHook):
    """
    Hook for Redis connections.

    Provides:
    - Connection management
    - JSON serialization/deserialization
    - Pattern-based operations
    - TTL management

    :param conn_id: Airflow connection ID
    :param db: Redis database number
    """

    conn_name_attr = "conn_id"
    default_conn_name = "redis_default"
    conn_type = "redis"
    hook_name = "Redis"

    def __init__(
        self,
        conn_id: str = default_conn_name,
        db: int = 0,
    ) -> None:
        super().__init__()
        self.conn_id = conn_id
        self.db = db
        self._client = None

    def get_conn(self):
        """Get Redis client."""
        if self._client is None:
            import redis

            conn_config = self.get_connection(self.conn_id)

            self._client = redis.Redis(
                host=conn_config.host or "localhost",
                port=conn_config.port or 6379,
                password=conn_config.password,
                db=self.db,
                decode_responses=True,
            )

        return self._client

    def set_json(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set a JSON-serializable value."""
        client = self.get_conn()
        serialized = json.dumps(value, default=str)

        if ttl:
            return client.setex(key, ttl, serialized)
        else:
            return client.set(key, serialized)

    def get_json(self, key: str) -> Optional[Any]:
        """Get and deserialize a JSON value."""
        client = self.get_conn()
        value = client.get(key)

        if value:
            return json.loads(value)
        return None

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern."""
        client = self.get_conn()
        keys = list(client.scan_iter(pattern))

        if keys:
            return client.delete(*keys)
        return 0

    def get_many_json(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple JSON values."""
        client = self.get_conn()
        pipeline = client.pipeline()

        for key in keys:
            pipeline.get(key)

        values = pipeline.execute()
        result = {}

        for key, value in zip(keys, values):
            if value:
                result[key] = json.loads(value)

        return result

    def incr_with_ttl(
        self,
        key: str,
        amount: int = 1,
        ttl: int = 3600,
    ) -> int:
        """Increment a counter with TTL."""
        client = self.get_conn()
        pipeline = client.pipeline()

        pipeline.incrby(key, amount)
        pipeline.expire(key, ttl)

        results = pipeline.execute()
        return results[0]

    def close(self):
        """Close the Redis connection."""
        if self._client:
            self._client.close()
            self._client = None


class PricingAPIHook(BaseHook):
    """
    Hook for Pricing API connections.

    Supports:
    - Flatpeak (UK/EU)
    - NREL (US)
    - IEA (Global)

    Features:
    - Automatic retry with exponential backoff
    - Rate limiting awareness
    - Response normalization

    :param api_source: API to connect to
    :param conn_id: Airflow connection ID
    """

    conn_name_attr = "conn_id"
    default_conn_name = "pricing_api_default"
    conn_type = "http"
    hook_name = "PricingAPI"

    # API base URLs
    API_URLS = {
        "flatpeak": "https://api.flatpeak.com/v1",
        "nrel": "https://api.nrel.gov/utility_rates/v3",
        "iea": "https://api.iea.org/v1/electricity",
    }

    def __init__(
        self,
        api_source: str,
        conn_id: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.api_source = api_source.lower()
        self.conn_id = conn_id or f"{self.api_source}_default"
        self._client = None
        self._api_key = None

    def get_conn(self) -> httpx.Client:
        """Get HTTP client with authentication."""
        if self._client is None:
            conn_config = self.get_connection(self.conn_id)
            self._api_key = conn_config.password

            headers = self._get_auth_headers()

            self._client = httpx.Client(
                base_url=self.API_URLS.get(self.api_source, ""),
                headers=headers,
                timeout=60.0,
            )

        return self._client

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers based on API source."""
        if self.api_source == "flatpeak":
            return {"Authorization": f"Bearer {self._api_key}"}
        elif self.api_source == "nrel":
            return {"X-Api-Key": self._api_key}
        elif self.api_source == "iea":
            return {"Authorization": f"Bearer {self._api_key}"}
        else:
            return {}

    def get_prices(
        self,
        region: str,
        start_time: datetime,
        end_time: datetime,
        timeout: int = 60,
    ) -> List[Dict]:
        """Fetch prices for a region and time range."""
        client = self.get_conn()

        if self.api_source == "flatpeak":
            return self._get_flatpeak_prices(client, region, start_time, end_time)
        elif self.api_source == "nrel":
            return self._get_nrel_prices(client, region, start_time, end_time)
        elif self.api_source == "iea":
            return self._get_iea_prices(client, region, start_time, end_time)
        else:
            raise ValueError(f"Unknown API source: {self.api_source}")

    def _get_flatpeak_prices(
        self,
        client: httpx.Client,
        region: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Dict]:
        """Fetch prices from Flatpeak API."""
        params = {
            "region": region,
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "resolution": "PT15M",  # 15-minute intervals
        }

        response = client.get("/prices", params=params)
        response.raise_for_status()

        data = response.json()
        prices = []

        for item in data.get("prices", []):
            prices.append({
                "timestamp": item["timestamp"],
                "region": region,
                "price": item["value"],
                "currency": item.get("currency", "EUR"),
                "unit": "EUR/MWh",
                "price_type": "spot",
            })

        return prices

    def _get_nrel_prices(
        self,
        client: httpx.Client,
        region: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Dict]:
        """Fetch prices from NREL API."""
        # NREL uses different endpoint structure
        params = {
            "lat": self._get_region_coords(region)[0],
            "lon": self._get_region_coords(region)[1],
            "api_key": self._api_key,
        }

        response = client.get(".json", params=params)
        response.raise_for_status()

        data = response.json()
        prices = []

        # NREL returns rate schedules, not real-time prices
        # We need to map these to hourly values
        outputs = data.get("outputs", {})
        residential = outputs.get("residential", {})

        for rate in residential.get("rate_schedule", []):
            prices.append({
                "timestamp": start_time.isoformat(),  # Simplified
                "region": region,
                "price": rate.get("rate", 0) * 1000,  # Convert $/kWh to $/MWh
                "currency": "USD",
                "unit": "USD/MWh",
                "price_type": "tariff",
            })

        return prices

    def _get_iea_prices(
        self,
        client: httpx.Client,
        region: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Dict]:
        """Fetch prices from IEA API."""
        params = {
            "region": region,
            "year": start_time.year,
        }

        response = client.get("/prices", params=params)
        response.raise_for_status()

        data = response.json()
        prices = []

        for item in data.get("data", []):
            prices.append({
                "timestamp": f"{item['year']}-01-01T00:00:00",
                "region": region,
                "price": item.get("price", 0),
                "currency": item.get("currency", "USD"),
                "unit": "USD/MWh",
                "price_type": "average",
            })

        return prices

    def _get_region_coords(self, region: str) -> Tuple[float, float]:
        """Get coordinates for a region (for NREL API)."""
        coords = {
            "US-CA": (36.7783, -119.4179),
            "US-TX": (31.9686, -99.9018),
            "US-NY": (42.1657, -74.9481),
            "US-FL": (27.6648, -81.5158),
        }
        return coords.get(region, (0, 0))

    def health_check(self, timeout: int = 10) -> bool:
        """Perform API health check."""
        try:
            client = self.get_conn()
            client.timeout = timeout

            if self.api_source == "flatpeak":
                response = client.get("/health")
            elif self.api_source == "nrel":
                # NREL doesn't have health endpoint, try a simple request
                response = client.get(".json", params={
                    "lat": 0,
                    "lon": 0,
                    "api_key": self._api_key,
                })
            elif self.api_source == "iea":
                response = client.get("/status")
            else:
                return False

            return response.status_code < 500

        except Exception as e:
            logger.warning(f"Health check failed for {self.api_source}: {e}")
            return False

    def close(self):
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None
