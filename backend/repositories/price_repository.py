"""
Price Repository

Data access layer for electricity price data.
Implements the repository pattern with caching support.
"""

import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Any

from sqlalchemy import select, and_, desc, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.base import BaseRepository, RepositoryError, NotFoundError
from models.price import Price, PriceRegion


class PriceRepository(BaseRepository[Price]):
    """
    Repository for managing electricity price data.

    Provides data access methods for prices with caching support
    and TimescaleDB optimizations.
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

    async def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if self._cache:
            try:
                cached = await self._cache.get(key)
                if cached:
                    return json.loads(cached)
            except Exception:
                pass
        return None

    async def _set_in_cache(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache"""
        if self._cache:
            try:
                await self._cache.set(
                    key,
                    json.dumps(value, default=str),
                    ex=ttl or self._cache_ttl
                )
            except Exception:
                pass

    async def get_by_id(self, id: str) -> Optional[Price]:
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
            from models.price import Price as PriceModel
            result = await self._db.execute(
                select(PriceModel).where(PriceModel.id == id)
            )
            price = result.scalar_one_or_none()

            if price:
                await self._set_in_cache(cache_key, price.model_dump())

            return price

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
            self._db.add(entity)
            await self._db.commit()
            await self._db.refresh(entity)
            return entity

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to create price: {str(e)}", e)

    async def update(self, id: str, entity: Price) -> Optional[Price]:
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

            # Update fields
            for field, value in entity.model_dump(exclude_unset=True).items():
                setattr(existing, field, value)

            await self._db.commit()
            await self._db.refresh(existing)

            # Invalidate cache
            cache_key = self._cache_key("id", id)
            if self._cache:
                await self._cache.delete(cache_key)

            return existing

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
            existing = await self.get_by_id(id)
            if not existing:
                return False

            await self._db.delete(existing)
            await self._db.commit()

            # Invalidate cache
            cache_key = self._cache_key("id", id)
            if self._cache:
                await self._cache.delete(cache_key)

            return True

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to delete price: {str(e)}", e)

    async def list(
        self,
        page: int = 1,
        page_size: int = 10,
        **filters: Any
    ) -> List[Price]:
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

            query = select(Price).offset(offset).limit(page_size)

            # Apply filters
            if "region" in filters:
                query = query.where(Price.region == filters["region"].value)
            if "supplier" in filters:
                query = query.where(Price.supplier == filters["supplier"])

            query = query.order_by(desc(Price.timestamp))

            result = await self._db.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            raise RepositoryError(f"Failed to list prices: {str(e)}", e)

    async def count(self, **filters: Any) -> int:
        """
        Count prices matching filters.

        Args:
            **filters: Filter criteria

        Returns:
            Count of matching prices
        """
        try:
            from sqlalchemy import func

            query = select(func.count()).select_from(Price)

            if "region" in filters:
                query = query.where(Price.region == filters["region"].value)
            if "supplier" in filters:
                query = query.where(Price.supplier == filters["supplier"])

            result = await self._db.execute(query)
            return result.scalar() or 0

        except Exception as e:
            raise RepositoryError(f"Failed to count prices: {str(e)}", e)

    # ==========================================================================
    # Price-specific methods
    # ==========================================================================

    async def get_current_prices(
        self,
        region: PriceRegion,
        limit: int = 10
    ) -> List[Price]:
        """
        Get current prices for a region.

        Args:
            region: Price region
            limit: Maximum number of results

        Returns:
            List of current prices
        """
        try:
            # Check cache first
            cache_key = self._cache_key("current", region.value)
            cached = await self._get_from_cache(cache_key)
            if cached:
                return [Price(**p) for p in cached]

            # Query database for latest prices
            query = (
                select(Price)
                .where(Price.region == region.value)
                .order_by(desc(Price.timestamp))
                .limit(limit)
            )

            result = await self._db.execute(query)
            prices = list(result.scalars().all())

            # Cache results
            if prices:
                await self._set_in_cache(
                    cache_key,
                    [p.model_dump() for p in prices],
                    ttl=60  # 1 minute TTL for current prices
                )

            return prices

        except Exception as e:
            raise RepositoryError(f"Failed to get current prices: {str(e)}", e)

    async def get_latest_by_supplier(
        self,
        region: PriceRegion,
        supplier: str
    ) -> Optional[Price]:
        """
        Get the latest price for a specific supplier.

        Args:
            region: Price region
            supplier: Supplier name

        Returns:
            Latest price if found
        """
        try:
            cache_key = self._cache_key("latest", region.value, supplier)
            cached = await self._get_from_cache(cache_key)
            if cached:
                return Price(**cached)

            query = (
                select(Price)
                .where(
                    and_(
                        Price.region == region.value,
                        Price.supplier == supplier
                    )
                )
                .order_by(desc(Price.timestamp))
                .limit(1)
            )

            result = await self._db.execute(query)
            price = result.scalar_one_or_none()

            if price:
                await self._set_in_cache(cache_key, price.model_dump())

            return price

        except Exception as e:
            raise RepositoryError(f"Failed to get latest price: {str(e)}", e)

    async def get_historical_prices(
        self,
        region: PriceRegion,
        start_date: datetime,
        end_date: datetime,
        supplier: Optional[str] = None
    ) -> List[Price]:
        """
        Get historical prices for a date range.

        Args:
            region: Price region
            start_date: Start of date range
            end_date: End of date range
            supplier: Optional supplier filter

        Returns:
            List of historical prices
        """
        try:
            conditions = [
                Price.region == region.value,
                Price.timestamp >= start_date,
                Price.timestamp <= end_date
            ]

            if supplier:
                conditions.append(Price.supplier == supplier)

            query = (
                select(Price)
                .where(and_(*conditions))
                .order_by(Price.timestamp)
            )

            result = await self._db.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            raise RepositoryError(f"Failed to get historical prices: {str(e)}", e)

    async def bulk_create(self, prices: List[Price]) -> int:
        """
        Bulk create multiple price records.

        Args:
            prices: List of prices to create

        Returns:
            Number of records created
        """
        try:
            self._db.add_all(prices)
            await self._db.commit()
            return len(prices)

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to bulk create prices: {str(e)}", e)

    async def get_price_statistics(
        self,
        region: PriceRegion,
        days: int = 7
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
            from sqlalchemy import func

            start_date = datetime.now(timezone.utc) - timedelta(days=days)

            query = (
                select(
                    func.min(Price.price_per_kwh).label("min_price"),
                    func.max(Price.price_per_kwh).label("max_price"),
                    func.avg(Price.price_per_kwh).label("avg_price"),
                    func.count(Price.id).label("count")
                )
                .where(
                    and_(
                        Price.region == region.value,
                        Price.timestamp >= start_date
                    )
                )
            )

            result = await self._db.execute(query)
            row = result.one()

            return {
                "min_price": Decimal(str(row.min_price)) if row.min_price else None,
                "max_price": Decimal(str(row.max_price)) if row.max_price else None,
                "avg_price": Decimal(str(row.avg_price)).quantize(Decimal("0.0001")) if row.avg_price else None,
                "count": row.count,
                "period_days": days
            }

        except Exception as e:
            raise RepositoryError(f"Failed to get price statistics: {str(e)}", e)

    async def get_hourly_price_averages(
        self,
        region: PriceRegion,
        start_date: datetime,
        end_date: datetime,
    ) -> List[dict]:
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
            hour_col = extract("hour", Price.timestamp).label("hour")
            query = (
                select(
                    hour_col,
                    func.avg(Price.price_per_kwh).label("avg_price"),
                    func.count(Price.id).label("count"),
                )
                .where(
                    and_(
                        Price.region == region.value,
                        Price.timestamp >= start_date,
                        Price.timestamp <= end_date,
                    )
                )
                .group_by(hour_col)
                .order_by(hour_col)
            )

            result = await self._db.execute(query)
            rows = result.all()

            return [
                {
                    "hour": int(row.hour),
                    "avg_price": Decimal(str(row.avg_price)).quantize(Decimal("0.0001")),
                    "count": row.count,
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
    ) -> List[dict]:
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
            query = (
                select(
                    Price.supplier,
                    func.avg(Price.price_per_kwh).label("avg_price"),
                    func.min(Price.price_per_kwh).label("min_price"),
                    func.max(Price.price_per_kwh).label("max_price"),
                    func.stddev(Price.price_per_kwh).label("stddev_price"),
                    func.count(Price.id).label("count"),
                )
                .where(
                    and_(
                        Price.region == region.value,
                        Price.timestamp >= start_date,
                        Price.timestamp <= end_date,
                    )
                )
                .group_by(Price.supplier)
                .order_by(func.avg(Price.price_per_kwh))
            )

            result = await self._db.execute(query)
            rows = result.all()

            return [
                {
                    "supplier": row.supplier,
                    "avg_price": Decimal(str(row.avg_price)).quantize(Decimal("0.0001")),
                    "min_price": Decimal(str(row.min_price)).quantize(Decimal("0.0001")),
                    "max_price": Decimal(str(row.max_price)).quantize(Decimal("0.0001")),
                    "volatility": Decimal(str(row.stddev_price)).quantize(Decimal("0.0001")) if row.stddev_price else Decimal("0"),
                    "count": row.count,
                }
                for row in rows
            ]

        except Exception as e:
            raise RepositoryError(f"Failed to get supplier stats: {str(e)}", e)
