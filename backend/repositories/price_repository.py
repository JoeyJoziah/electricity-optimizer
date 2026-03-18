"""
Price Repository

Data access layer for electricity price data.
Implements the repository pattern with caching support.
Uses raw SQL (text()) since Price is a Pydantic model, not a SQLAlchemy ORM model.
"""

import asyncio
import builtins
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.price import Price, PriceRegion
from models.utility import UtilityType
from repositories.base import BaseRepository, RepositoryError

# Columns that exist in the electricity_prices table
_PRICE_COLUMNS = (
    "id, region, supplier, price_per_kwh, currency, timestamp, "
    "is_peak, source_api, created_at, carbon_intensity, utility_type"
)


def _row_to_price(row: dict) -> Price:
    """Convert a DB row mapping to a Price Pydantic model."""
    return Price(
        id=str(row["id"]),
        region=row["region"],
        supplier=row["supplier"],
        price_per_kwh=row["price_per_kwh"],
        currency=row["currency"],
        timestamp=row["timestamp"],
        is_peak=row.get("is_peak"),
        source_api=row.get("source_api"),
        created_at=row.get("created_at", datetime.now(UTC)),
        carbon_intensity=(
            float(row["carbon_intensity"]) if row.get("carbon_intensity") is not None else None
        ),
        utility_type=row.get("utility_type", "electricity"),
    )


class PriceRepository(BaseRepository[Price]):
    """
    Repository for managing electricity price data.

    Provides data access methods for prices with caching support.
    Uses raw SQL queries against the electricity_prices table.
    """

    def __init__(self, db_session: AsyncSession, cache: Any = None, cache_ttl: int = 60):
        """
        Initialize the price repository.

        Args:
            db_session: SQLAlchemy async session
            cache: Redis cache client (optional)
            cache_ttl: Cache TTL in seconds
        """
        self._db = db_session
        self._cache = cache
        self._cache_ttl = cache_ttl

    def _cache_key(self, *args: Any) -> str:
        """Generate cache key"""
        return f"price:{':'.join(str(a) for a in args)}"

    async def _get_from_cache(self, key: str) -> Any | None:
        """Get value from cache"""
        if self._cache:
            try:
                cached = await self._cache.get(key)
                if cached:
                    return json.loads(cached)
            except Exception:
                pass
        return None

    async def _acquire_cache_lock(self, key: str, ttl_ms: int = 5000) -> bool:
        """Try to acquire a compute lock for a cache key (prevents stampede).

        Returns True when the lock is successfully acquired (caller should
        proceed with the expensive computation).  Returns False when the lock
        is already held by another request OR when Redis is unavailable.

        Fail-closed on Redis error: returning False (lock appears held) prevents
        all concurrent waiters from stampeding the database when Redis is down.
        """
        if not self._cache:
            return True
        try:
            return bool(await self._cache.set(f"{key}:lock", "1", px=ttl_ms, nx=True))
        except Exception:
            # Fail-closed: treat Redis failure as "lock already held" so that
            # no caller proceeds to hammer the database during a Redis outage.
            return False

    async def _set_in_cache(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set value in cache and release compute lock."""
        if self._cache:
            try:
                await self._cache.set(
                    key, json.dumps(value, default=str), ex=ttl or self._cache_ttl
                )
                await self._cache.delete(f"{key}:lock")
            except Exception:
                pass

    async def get_by_id(self, id: str) -> Price | None:
        """
        Get a price record by ID.

        Args:
            id: Price record ID

        Returns:
            Price if found, None otherwise
        """
        try:
            # Check cache first
            cache_key = self._cache_key("id", id)
            cached = await self._get_from_cache(cache_key)
            if cached:
                return Price(**cached)

            # Query database
            result = await self._db.execute(
                text(f"SELECT {_PRICE_COLUMNS} FROM electricity_prices WHERE id = :id"),
                {"id": id},
            )
            row = result.mappings().first()

            if row:
                price = _row_to_price(row)
                await self._set_in_cache(cache_key, price.model_dump())
                return price

            return None

        except Exception as e:
            raise RepositoryError(f"Failed to get price by ID: {str(e)}", e)

    async def create(self, entity: Price) -> Price:
        """
        Create a new price record.

        Args:
            entity: Price data to create

        Returns:
            Created price record
        """
        try:
            await self._db.execute(
                text("""
                    INSERT INTO electricity_prices
                        (id, region, supplier, price_per_kwh, currency, timestamp,
                         is_peak, source_api, created_at, carbon_intensity, utility_type)
                    VALUES
                        (:id, :region, :supplier, :price_per_kwh, :currency, :timestamp,
                         :is_peak, :source_api, :created_at, :carbon_intensity, :utility_type)
                """),
                {
                    "id": entity.id,
                    "region": (
                        entity.region if isinstance(entity.region, str) else entity.region.value
                    ),
                    "supplier": entity.supplier,
                    "price_per_kwh": entity.price_per_kwh,
                    "currency": entity.currency,
                    "timestamp": entity.timestamp,
                    "is_peak": entity.is_peak,
                    "source_api": entity.source_api,
                    "created_at": entity.created_at,
                    "carbon_intensity": entity.carbon_intensity,
                    "utility_type": (
                        entity.utility_type
                        if isinstance(entity.utility_type, str)
                        else entity.utility_type.value
                    ),
                },
            )
            await self._db.commit()
            return entity

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to create price: {str(e)}", e)

    async def update(self, id: str, entity: Price) -> Price | None:
        """
        Update an existing price record.

        Args:
            id: Price record ID
            entity: Updated price data

        Returns:
            Updated price if found, None otherwise
        """
        try:
            existing = await self.get_by_id(id)
            if not existing:
                return None

            await self._db.execute(
                text("""
                    UPDATE electricity_prices SET
                        region = :region, supplier = :supplier,
                        price_per_kwh = :price_per_kwh, currency = :currency,
                        timestamp = :timestamp, is_peak = :is_peak,
                        source_api = :source_api, carbon_intensity = :carbon_intensity,
                        utility_type = :utility_type
                    WHERE id = :id
                """),
                {
                    "id": id,
                    "region": (
                        entity.region if isinstance(entity.region, str) else entity.region.value
                    ),
                    "supplier": entity.supplier,
                    "price_per_kwh": entity.price_per_kwh,
                    "currency": entity.currency,
                    "timestamp": entity.timestamp,
                    "is_peak": entity.is_peak,
                    "source_api": entity.source_api,
                    "carbon_intensity": entity.carbon_intensity,
                    "utility_type": (
                        entity.utility_type
                        if isinstance(entity.utility_type, str)
                        else entity.utility_type.value
                    ),
                },
            )
            await self._db.commit()

            # Invalidate cache
            cache_key = self._cache_key("id", id)
            if self._cache:
                await self._cache.delete(cache_key)

            return await self.get_by_id(id)

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to update price: {str(e)}", e)

    async def delete(self, id: str) -> bool:
        """
        Delete a price record.

        Args:
            id: Price record ID

        Returns:
            True if deleted, False if not found
        """
        try:
            result = await self._db.execute(
                text("DELETE FROM electricity_prices WHERE id = :id"),
                {"id": id},
            )
            await self._db.commit()

            deleted = result.rowcount > 0

            if deleted and self._cache:
                cache_key = self._cache_key("id", id)
                await self._cache.delete(cache_key)

            return deleted

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to delete price: {str(e)}", e)

    async def list(self, page: int = 1, page_size: int = 10, **filters: Any) -> list[Price]:
        """
        List prices with pagination.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            **filters: Filter criteria

        Returns:
            List of prices
        """
        try:
            offset = (page - 1) * page_size

            sql = f"SELECT {_PRICE_COLUMNS} FROM electricity_prices WHERE 1=1"
            params: dict[str, Any] = {}

            if "region" in filters:
                sql += " AND region = :region"
                params["region"] = (
                    filters["region"].value
                    if hasattr(filters["region"], "value")
                    else filters["region"]
                )
            if "supplier" in filters:
                sql += " AND supplier = :supplier"
                params["supplier"] = filters["supplier"]

            sql += " ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"
            params["limit"] = page_size
            params["offset"] = offset

            result = await self._db.execute(text(sql), params)
            rows = result.mappings().all()
            return [_row_to_price(row) for row in rows]

        except Exception as e:
            raise RepositoryError(f"Failed to list prices: {str(e)}", e)

    async def list_latest_by_regions(
        self,
        regions: builtins.list[str],
        limit_per_region: int = 20,
    ) -> builtins.list[Price]:
        """Fetch the latest prices for multiple regions in a single query.

        Uses a lateral join to get up to `limit_per_region` most-recent rows
        per region efficiently, replacing N sequential queries with one.
        """
        if not regions:
            return []
        try:
            # Build region value list for IN clause
            region_params = {
                f"r{i}": (r.value if hasattr(r, "value") else r) for i, r in enumerate(regions)
            }
            placeholders = ", ".join(f":{k}" for k in region_params)

            sql = f"""
                SELECT {_PRICE_COLUMNS}
                FROM (
                    SELECT *, ROW_NUMBER() OVER (PARTITION BY region ORDER BY timestamp DESC) AS rn
                    FROM electricity_prices
                    WHERE region IN ({placeholders})
                ) sub
                WHERE rn <= :lim
                ORDER BY region, timestamp DESC
            """
            params = {**region_params, "lim": limit_per_region}
            result = await self._db.execute(text(sql), params)
            rows = result.mappings().all()
            return [_row_to_price(row) for row in rows]
        except Exception as e:
            raise RepositoryError(f"Failed to list latest prices by regions: {str(e)}", e)

    async def count(self, **filters: Any) -> int:
        """
        Count prices matching filters.

        Args:
            **filters: Filter criteria

        Returns:
            Count of matching prices
        """
        try:
            sql = "SELECT COUNT(*) FROM electricity_prices WHERE 1=1"
            params: dict[str, Any] = {}

            if "region" in filters:
                sql += " AND region = :region"
                params["region"] = (
                    filters["region"].value
                    if hasattr(filters["region"], "value")
                    else filters["region"]
                )
            if "supplier" in filters:
                sql += " AND supplier = :supplier"
                params["supplier"] = filters["supplier"]

            result = await self._db.execute(text(sql), params)
            return result.scalar() or 0

        except Exception as e:
            raise RepositoryError(f"Failed to count prices: {str(e)}", e)

    # ==========================================================================
    # Price-specific methods
    # ==========================================================================

    async def get_current_prices(
        self,
        region: PriceRegion,
        limit: int = 10,
        utility_type: UtilityType = UtilityType.ELECTRICITY,
    ) -> builtins.list[Price]:
        """
        Get current prices for a region and utility type.

        Args:
            region: Price region
            limit: Maximum number of results
            utility_type: Type of utility (defaults to electricity)

        Returns:
            List of current prices
        """
        try:
            region_val = region.value if hasattr(region, "value") else region
            ut_val = utility_type.value if hasattr(utility_type, "value") else utility_type

            # Check cache first (include limit in key to prevent stale data)
            cache_key = self._cache_key("current", region_val, ut_val, limit)
            cached = await self._get_from_cache(cache_key)
            if cached:
                return [Price(**p) for p in cached]

            # Stampede prevention: acquire lock before DB query
            if not await self._acquire_cache_lock(cache_key):
                await asyncio.sleep(0.1)
                cached = await self._get_from_cache(cache_key)
                if cached:
                    return [Price(**p) for p in cached]

            # Query database for latest prices
            result = await self._db.execute(
                text(f"""
                    SELECT {_PRICE_COLUMNS}
                    FROM electricity_prices
                    WHERE region = :region AND utility_type = :utility_type
                    ORDER BY timestamp DESC
                    LIMIT :limit
                """),
                {"region": region_val, "utility_type": ut_val, "limit": limit},
            )
            rows = result.mappings().all()
            prices = [_row_to_price(row) for row in rows]

            # Cache results
            if prices:
                await self._set_in_cache(
                    cache_key,
                    [p.model_dump() for p in prices],
                    ttl=60,  # 1 minute TTL for current prices
                )

            return prices

        except Exception as e:
            raise RepositoryError(f"Failed to get current prices: {str(e)}", e)

    async def get_latest_by_supplier(self, region: PriceRegion, supplier: str) -> Price | None:
        """
        Get the latest price for a specific supplier.

        Args:
            region: Price region
            supplier: Supplier name

        Returns:
            Latest price if found
        """
        try:
            region_val = region.value if hasattr(region, "value") else region

            cache_key = self._cache_key("latest", region_val, supplier)
            cached = await self._get_from_cache(cache_key)
            if cached:
                return Price(**cached)

            result = await self._db.execute(
                text(f"""
                    SELECT {_PRICE_COLUMNS}
                    FROM electricity_prices
                    WHERE region = :region AND supplier = :supplier
                    ORDER BY timestamp DESC
                    LIMIT 1
                """),
                {"region": region_val, "supplier": supplier},
            )
            row = result.mappings().first()

            if row:
                price = _row_to_price(row)
                await self._set_in_cache(cache_key, price.model_dump())
                return price

            return None

        except Exception as e:
            raise RepositoryError(f"Failed to get latest price: {str(e)}", e)

    async def get_historical_prices(
        self,
        region: PriceRegion,
        start_date: datetime,
        end_date: datetime,
        supplier: str | None = None,
        utility_type: UtilityType = UtilityType.ELECTRICITY,
        limit: int = 5000,
    ) -> builtins.list[Price]:
        """
        Get historical prices for a date range.

        Args:
            region: Price region
            start_date: Start of date range
            end_date: End of date range
            supplier: Optional supplier filter
            utility_type: Type of utility (defaults to electricity)
            limit: Maximum number of rows to return (safety cap, default 5000)

        Returns:
            List of historical prices
        """
        try:
            region_val = region.value if hasattr(region, "value") else region
            ut_val = utility_type.value if hasattr(utility_type, "value") else utility_type

            sql = f"""
                SELECT {_PRICE_COLUMNS}
                FROM electricity_prices
                WHERE region = :region
                  AND utility_type = :utility_type
                  AND timestamp >= :start_date
                  AND timestamp <= :end_date
            """
            params: dict[str, Any] = {
                "region": region_val,
                "utility_type": ut_val,
                "start_date": start_date,
                "end_date": end_date,
            }

            if supplier:
                sql += " AND supplier = :supplier"
                params["supplier"] = supplier

            sql += " ORDER BY timestamp LIMIT :limit"
            params["limit"] = limit

            result = await self._db.execute(text(sql), params)
            rows = result.mappings().all()
            return [_row_to_price(row) for row in rows]

        except Exception as e:
            raise RepositoryError(f"Failed to get historical prices: {str(e)}", e)

    async def get_historical_prices_paginated(
        self,
        region: PriceRegion,
        start_date: datetime,
        end_date: datetime,
        page: int = 1,
        page_size: int = 24,
        supplier: str | None = None,
        utility_type: UtilityType = UtilityType.ELECTRICITY,
    ) -> tuple[builtins.list[Price], int]:
        """
        Get historical prices for a date range with offset pagination.

        Executes a COUNT query and a paginated SELECT in parallel to minimise
        round-trip latency.  Returns the page of Price objects together with
        the total matching row count so callers can compute total_pages.

        Args:
            region: Price region
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            page: 1-based page number (clamped to >= 1)
            page_size: Records per page (clamped to 1–100)
            supplier: Optional supplier filter
            utility_type: Type of utility (defaults to electricity)

        Returns:
            Tuple of (list of Price objects for the page, total matching count)
        """
        try:
            page = max(1, page)
            page_size = max(1, min(100, page_size))
            offset = (page - 1) * page_size

            region_val = region.value if hasattr(region, "value") else region
            ut_val = utility_type.value if hasattr(utility_type, "value") else utility_type

            base_params: dict[str, Any] = {
                "region": region_val,
                "utility_type": ut_val,
                "start_date": start_date,
                "end_date": end_date,
            }
            supplier_clause = ""
            if supplier:
                supplier_clause = " AND supplier = :supplier"
                base_params["supplier"] = supplier

            count_sql = text(f"""
                SELECT COUNT(*)
                FROM electricity_prices
                WHERE region = :region
                  AND utility_type = :utility_type
                  AND timestamp >= :start_date
                  AND timestamp <= :end_date
                {supplier_clause}
            """)

            rows_sql = text(f"""
                SELECT {_PRICE_COLUMNS}
                FROM electricity_prices
                WHERE region = :region
                  AND utility_type = :utility_type
                  AND timestamp >= :start_date
                  AND timestamp <= :end_date
                {supplier_clause}
                ORDER BY timestamp
                LIMIT :limit OFFSET :offset
            """)
            page_params = {**base_params, "limit": page_size, "offset": offset}

            # Sequential execution — asyncio.gather on a shared AsyncSession
            # can corrupt internal state (see SA docs on session concurrency)
            count_result = await self._db.execute(count_sql, base_params)
            rows_result = await self._db.execute(rows_sql, page_params)

            total = count_result.scalar() or 0
            rows = rows_result.mappings().all()
            prices = [_row_to_price(row) for row in rows]
            return prices, total

        except Exception as e:
            raise RepositoryError(f"Failed to get paginated historical prices: {str(e)}", e)

    async def bulk_create(self, prices: builtins.list[Price]) -> int:
        """
        Bulk create multiple price records using multi-row INSERT.

        Chunks at 500 rows to stay within parameter limits (11 params per row).

        Args:
            prices: List of prices to create

        Returns:
            Number of records created
        """
        if not prices:
            return 0

        CHUNK_SIZE = 500

        try:
            for chunk_start in range(0, len(prices), CHUNK_SIZE):
                chunk = prices[chunk_start : chunk_start + CHUNK_SIZE]
                placeholders = []
                params: dict = {}

                for i, entity in enumerate(chunk):
                    placeholders.append(
                        f"(:id{i}, :region{i}, :supplier{i}, :price_per_kwh{i}, "
                        f":currency{i}, :timestamp{i}, :is_peak{i}, :source_api{i}, "
                        f":created_at{i}, :carbon_intensity{i}, :utility_type{i})"
                    )
                    params[f"id{i}"] = entity.id
                    params[f"region{i}"] = (
                        entity.region if isinstance(entity.region, str) else entity.region.value
                    )
                    params[f"supplier{i}"] = entity.supplier
                    params[f"price_per_kwh{i}"] = entity.price_per_kwh
                    params[f"currency{i}"] = entity.currency
                    params[f"timestamp{i}"] = entity.timestamp
                    params[f"is_peak{i}"] = entity.is_peak
                    params[f"source_api{i}"] = entity.source_api
                    params[f"created_at{i}"] = entity.created_at
                    params[f"carbon_intensity{i}"] = entity.carbon_intensity
                    params[f"utility_type{i}"] = (
                        entity.utility_type
                        if isinstance(entity.utility_type, str)
                        else entity.utility_type.value
                    )

                await self._db.execute(
                    text(
                        "INSERT INTO electricity_prices "
                        "    (id, region, supplier, price_per_kwh, currency, timestamp, "
                        "     is_peak, source_api, created_at, carbon_intensity, utility_type) "
                        f"VALUES {', '.join(placeholders)}"
                    ),
                    params,
                )

            await self._db.commit()
            return len(prices)

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to bulk create prices: {str(e)}", e)

    async def get_price_statistics(
        self,
        region: PriceRegion,
        days: int = 7,
        utility_type: UtilityType = UtilityType.ELECTRICITY,
    ) -> dict:
        """
        Get price statistics for a region.

        Args:
            region: Price region
            days: Number of days to analyze

        Returns:
            Dictionary with min, max, avg prices
        """
        try:
            region_val = region.value if hasattr(region, "value") else region
            ut_val = utility_type.value if hasattr(utility_type, "value") else utility_type
            start_date = datetime.now(UTC) - timedelta(days=days)

            result = await self._db.execute(
                text("""
                    SELECT
                        MIN(price_per_kwh) AS min_price,
                        MAX(price_per_kwh) AS max_price,
                        AVG(price_per_kwh) AS avg_price,
                        COUNT(id) AS count
                    FROM electricity_prices
                    WHERE region = :region
                      AND utility_type = :utility_type
                      AND timestamp >= :start_date
                """),
                {"region": region_val, "utility_type": ut_val, "start_date": start_date},
            )
            row = result.mappings().first()

            return {
                "min_price": Decimal(str(row["min_price"])) if row["min_price"] else None,
                "max_price": Decimal(str(row["max_price"])) if row["max_price"] else None,
                "avg_price": (
                    Decimal(str(row["avg_price"])).quantize(Decimal("0.0001"))
                    if row["avg_price"]
                    else None
                ),
                "count": row["count"],
                "period_days": days,
                "utility_type": ut_val,
            }

        except Exception as e:
            raise RepositoryError(f"Failed to get price statistics: {str(e)}", e)

    async def get_price_statistics_with_stddev(
        self,
        region: PriceRegion,
        days: int = 7,
        utility_type: UtilityType = UtilityType.ELECTRICITY,
    ) -> dict:
        """
        Get price statistics including standard deviation using SQL aggregation.

        Computes AVG, MIN, MAX, STDDEV, and COUNT in a single query instead of
        fetching thousands of rows into Python.

        Args:
            region: Price region
            days: Number of days to analyze
            utility_type: Type of utility

        Returns:
            Dictionary with min, max, avg, stddev prices and count
        """
        try:
            region_val = region.value if hasattr(region, "value") else region
            ut_val = utility_type.value if hasattr(utility_type, "value") else utility_type
            start_date = datetime.now(UTC) - timedelta(days=days)

            result = await self._db.execute(
                text("""
                    SELECT
                        MIN(price_per_kwh) AS min_price,
                        MAX(price_per_kwh) AS max_price,
                        AVG(price_per_kwh) AS avg_price,
                        STDDEV_SAMP(price_per_kwh) AS stddev_price,
                        COUNT(id) AS count
                    FROM electricity_prices
                    WHERE region = :region
                      AND utility_type = :utility_type
                      AND timestamp >= :start_date
                """),
                {"region": region_val, "utility_type": ut_val, "start_date": start_date},
            )
            row = result.mappings().first()

            return {
                "min_price": Decimal(str(row["min_price"])) if row["min_price"] else None,
                "max_price": Decimal(str(row["max_price"])) if row["max_price"] else None,
                "avg_price": (
                    Decimal(str(row["avg_price"])).quantize(Decimal("0.0001"))
                    if row["avg_price"]
                    else None
                ),
                "stddev_price": (
                    Decimal(str(row["stddev_price"])).quantize(Decimal("0.0001"))
                    if row["stddev_price"]
                    else None
                ),
                "count": row["count"],
                "period_days": days,
                "utility_type": ut_val,
            }

        except Exception as e:
            raise RepositoryError(f"Failed to get price statistics with stddev: {str(e)}", e)

    async def get_price_trend_aggregates(
        self,
        region: PriceRegion,
        start_date: datetime,
        end_date: datetime,
        utility_type: UtilityType = UtilityType.ELECTRICITY,
    ) -> dict:
        """
        Compute first-third and last-third price averages in SQL.

        Uses ROW_NUMBER to match the Python logic:
          third = max(1, total_count // 3)
          first_third = rows[:third]
          last_third  = rows[-third:]

        Returns dict with first_third_avg, last_third_avg, total_count.
        """
        try:
            region_val = region.value if hasattr(region, "value") else region
            ut_val = utility_type.value if hasattr(utility_type, "value") else utility_type

            result = await self._db.execute(
                text("""
                    WITH numbered AS (
                        SELECT price_per_kwh,
                               ROW_NUMBER() OVER (ORDER BY timestamp ASC)  AS rn,
                               COUNT(*) OVER ()                             AS total
                        FROM electricity_prices
                        WHERE region = :region
                          AND utility_type = :utility_type
                          AND timestamp >= :start_date
                          AND timestamp <= :end_date
                    ),
                    bounds AS (
                        SELECT GREATEST(1, total / 3) AS third, total
                        FROM numbered
                        LIMIT 1
                    )
                    SELECT
                        (SELECT AVG(n.price_per_kwh) FROM numbered n, bounds b WHERE n.rn <= b.third)
                            AS first_third_avg,
                        (SELECT AVG(n.price_per_kwh) FROM numbered n, bounds b WHERE n.rn > b.total - b.third)
                            AS last_third_avg,
                        (SELECT total FROM bounds)
                            AS total_count
                """),
                {
                    "region": region_val,
                    "utility_type": ut_val,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )
            row = result.mappings().first()

            if not row or row["total_count"] is None or row["total_count"] < 2:
                return {"first_third_avg": None, "last_third_avg": None, "total_count": 0}

            return {
                "first_third_avg": (
                    Decimal(str(row["first_third_avg"])) if row["first_third_avg"] else None
                ),
                "last_third_avg": (
                    Decimal(str(row["last_third_avg"])) if row["last_third_avg"] else None
                ),
                "total_count": row["total_count"],
            }

        except Exception as e:
            raise RepositoryError(f"Failed to get price trend aggregates: {str(e)}", e)

    async def get_hourly_price_averages(
        self,
        region: PriceRegion,
        start_date: datetime,
        end_date: datetime,
    ) -> builtins.list[dict]:
        """
        Get average prices grouped by hour of day using SQL aggregation.

        Returns at most 24 rows instead of fetching all price records.

        Args:
            region: Price region
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of dicts with 'hour', 'avg_price', 'count' keys
        """
        try:
            region_val = region.value if hasattr(region, "value") else region

            result = await self._db.execute(
                text("""
                    SELECT
                        EXTRACT(HOUR FROM timestamp) AS hour,
                        AVG(price_per_kwh) AS avg_price,
                        COUNT(id) AS count
                    FROM electricity_prices
                    WHERE region = :region
                      AND timestamp >= :start_date
                      AND timestamp <= :end_date
                    GROUP BY EXTRACT(HOUR FROM timestamp)
                    ORDER BY EXTRACT(HOUR FROM timestamp)
                """),
                {"region": region_val, "start_date": start_date, "end_date": end_date},
            )
            rows = result.mappings().all()

            return [
                {
                    "hour": int(row["hour"]),
                    "avg_price": Decimal(str(row["avg_price"])).quantize(Decimal("0.0001")),
                    "count": row["count"],
                }
                for row in rows
            ]

        except Exception as e:
            raise RepositoryError(f"Failed to get hourly averages: {str(e)}", e)

    async def get_supplier_price_stats(
        self,
        region: PriceRegion,
        start_date: datetime,
        end_date: datetime,
    ) -> builtins.list[dict]:
        """
        Get price statistics grouped by supplier using SQL aggregation.

        Returns one row per supplier instead of fetching all price records.

        Args:
            region: Price region
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of dicts with supplier stats (avg, min, max, stddev, count)
        """
        try:
            region_val = region.value if hasattr(region, "value") else region

            result = await self._db.execute(
                text("""
                    SELECT
                        supplier,
                        AVG(price_per_kwh) AS avg_price,
                        MIN(price_per_kwh) AS min_price,
                        MAX(price_per_kwh) AS max_price,
                        STDDEV(price_per_kwh) AS stddev_price,
                        COUNT(id) AS count
                    FROM electricity_prices
                    WHERE region = :region
                      AND timestamp >= :start_date
                      AND timestamp <= :end_date
                    GROUP BY supplier
                    ORDER BY AVG(price_per_kwh)
                """),
                {"region": region_val, "start_date": start_date, "end_date": end_date},
            )
            rows = result.mappings().all()

            return [
                {
                    "supplier": row["supplier"],
                    "avg_price": Decimal(str(row["avg_price"])).quantize(Decimal("0.0001")),
                    "min_price": Decimal(str(row["min_price"])).quantize(Decimal("0.0001")),
                    "max_price": Decimal(str(row["max_price"])).quantize(Decimal("0.0001")),
                    "volatility": (
                        Decimal(str(row["stddev_price"])).quantize(Decimal("0.0001"))
                        if row["stddev_price"]
                        else Decimal("0")
                    ),
                    "count": row["count"],
                }
                for row in rows
            ]

        except Exception as e:
            raise RepositoryError(f"Failed to get supplier stats: {str(e)}", e)
