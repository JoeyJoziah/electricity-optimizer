"""
Supplier Repository

Data access layer for supplier and tariff data.
Includes the SupplierRegistryRepository (backed by supplier_registry table)
and StateRegulationRepository (backed by state_regulations table).

Caching strategy
----------------
Both SupplierRepository and SupplierRegistryRepository accept an optional
Redis client.  When Redis is unavailable (client is None) the repositories
fall through to the database transparently.

TTL: 3600 s (1 hour) for all supplier queries — supplier data is semi-static.
Keys follow the pattern:  supplier:<method>:<args...>

Cache invalidation is explicit via clear_cache() / clear_registry_cache().
"""

import json
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.supplier import Supplier, Tariff
from repositories.base import BaseRepository, NotFoundError, RepositoryError

# 1-hour TTL for all supplier / supplier-registry caches.
_SUPPLIER_CACHE_TTL = 3600


class SupplierRepository(BaseRepository[Supplier]):
    """
    Repository for managing supplier data.

    Provides data access methods for suppliers and their tariffs.
    Wraps get_by_name() and list_by_region() with a Redis TTL cache
    (1 hour).  All other write paths call clear_cache() to keep the
    cache consistent.
    """

    def __init__(self, db_session: AsyncSession, cache: Any = None):
        """
        Initialize the supplier repository.

        Args:
            db_session: SQLAlchemy async session
            cache: Redis cache client (optional).  Must expose async
                   get(key), set(key, value, ex=ttl) and delete(*keys).
        """
        self._db = db_session
        self._cache = cache

    # ------------------------------------------------------------------
    # Internal cache helpers
    # ------------------------------------------------------------------

    async def _cache_get(self, key: str) -> Optional[Any]:
        """Return deserialized value from Redis, or None on miss/error."""
        if not self._cache:
            return None
        try:
            raw = await self._cache.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    async def _cache_set(self, key: str, value: Any) -> None:
        """Serialize and store value in Redis with the supplier TTL."""
        if not self._cache:
            return
        try:
            await self._cache.set(key, json.dumps(value, default=str), ex=_SUPPLIER_CACHE_TTL)
        except Exception:
            pass

    async def _cache_delete(self, *keys: str) -> None:
        """Delete one or more keys from Redis (best-effort)."""
        if not self._cache or not keys:
            return
        try:
            await self._cache.delete(*keys)
        except Exception:
            pass

    async def clear_cache(self) -> None:
        """
        Remove all known supplier cache keys.

        Call this after any write operation (create / update / delete)
        so subsequent reads reflect the latest database state.
        """
        if not self._cache:
            return
        try:
            # Scan for all keys matching the supplier namespace.
            # Uses SCAN so it is non-blocking on large key spaces.
            async for key in self._cache.scan_iter(match="supplier:*"):
                await self._cache.delete(key)
        except Exception:
            pass

    async def get_by_id(self, id: str) -> Optional[Supplier]:
        """
        Get a supplier by ID.

        Args:
            id: Supplier ID

        Returns:
            Supplier if found, None otherwise
        """
        try:
            result = await self._db.execute(select(Supplier).where(Supplier.id == id))
            return result.scalar_one_or_none()

        except Exception as e:
            raise RepositoryError(f"Failed to get supplier by ID: {str(e)}", e)

    async def get_by_name(self, name: str) -> Optional[Supplier]:
        """
        Get a supplier by name.

        Results are cached in Redis for 1 hour (key: supplier:name:<name>).

        Args:
            name: Supplier name

        Returns:
            Supplier if found, None otherwise
        """
        cache_key = f"supplier:name:{name}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            # Reconstruct the ORM object from the cached dict.
            # Use a lightweight MagicMock-free approach: build a Supplier
            # from the stored dict and skip any DB round-trip.
            try:
                return Supplier(**cached)
            except Exception:
                # If reconstruction fails (schema drift, etc.) fall through.
                pass

        try:
            result = await self._db.execute(select(Supplier).where(Supplier.name == name))
            supplier = result.scalar_one_or_none()

            if supplier is not None:
                await self._cache_set(cache_key, supplier.__dict__.copy())

            return supplier

        except Exception as e:
            raise RepositoryError(f"Failed to get supplier by name: {str(e)}", e)

    async def create(self, entity: Supplier) -> Supplier:
        """
        Create a new supplier.

        Clears the supplier cache after a successful write so region-list
        queries reflect the new record immediately.

        Args:
            entity: Supplier data to create

        Returns:
            Created supplier
        """
        try:
            entity.created_at = datetime.now(timezone.utc)
            entity.updated_at = datetime.now(timezone.utc)

            self._db.add(entity)
            await self._db.commit()
            await self._db.refresh(entity)
            await self.clear_cache()
            return entity

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to create supplier: {str(e)}", e)

    async def update(self, id: str, entity: Supplier) -> Optional[Supplier]:
        """
        Update an existing supplier.

        Clears the supplier cache after a successful write.

        Args:
            id: Supplier ID
            entity: Updated supplier data

        Returns:
            Updated supplier if found, None otherwise
        """
        try:
            existing = await self.get_by_id(id)
            if not existing:
                return None

            for field, value in entity.model_dump(exclude_unset=True).items():
                if field not in ["id", "created_at"]:
                    setattr(existing, field, value)

            existing.updated_at = datetime.now(timezone.utc)

            await self._db.commit()
            await self._db.refresh(existing)
            await self.clear_cache()
            return existing

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to update supplier: {str(e)}", e)

    async def delete(self, id: str) -> bool:
        """
        Delete a supplier.

        Clears the supplier cache after a successful deletion.

        Args:
            id: Supplier ID

        Returns:
            True if deleted, False if not found
        """
        try:
            existing = await self.get_by_id(id)
            if not existing:
                return False

            await self._db.delete(existing)
            await self._db.commit()
            await self.clear_cache()
            return True

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to delete supplier: {str(e)}", e)

    async def list(self, page: int = 1, page_size: int = 10, **filters: Any) -> List[Supplier]:
        """
        List suppliers with pagination.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            **filters: Filter criteria

        Returns:
            List of suppliers
        """
        try:
            offset = (page - 1) * page_size

            query = select(Supplier).offset(offset).limit(page_size)

            if "is_active" in filters:
                query = query.where(Supplier.is_active == filters["is_active"])

            query = query.order_by(Supplier.name)

            result = await self._db.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            raise RepositoryError(f"Failed to list suppliers: {str(e)}", e)

    async def count(self, **filters: Any) -> int:
        """
        Count suppliers matching filters.

        Args:
            **filters: Filter criteria

        Returns:
            Count of matching suppliers
        """
        try:
            from sqlalchemy import func

            query = select(func.count()).select_from(Supplier)

            if "is_active" in filters:
                query = query.where(Supplier.is_active == filters["is_active"])

            result = await self._db.execute(query)
            return result.scalar() or 0

        except Exception as e:
            raise RepositoryError(f"Failed to count suppliers: {str(e)}", e)

    # ==========================================================================
    # Supplier-specific methods
    # ==========================================================================

    async def list_by_region(self, region: str, active_only: bool = True) -> List[Supplier]:
        """
        Get all suppliers available in a region.

        Results are cached in Redis for 1 hour.
        Key: supplier:region:<region>:active_only:<0|1>

        Args:
            region: Region code
            active_only: Whether to include only active suppliers

        Returns:
            List of suppliers in the region
        """
        cache_key = f"supplier:region:{region.lower()}:active_only:{int(active_only)}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            try:
                return [Supplier(**row) for row in cached]
            except Exception:
                pass

        try:
            # PostgreSQL array contains
            from sqlalchemy import any_

            conditions = [region.lower() == any_(Supplier.regions)]

            if active_only:
                conditions.append(Supplier.is_active == True)

            query = select(Supplier).where(and_(*conditions)).order_by(Supplier.name)
            result = await self._db.execute(query)
            suppliers = list(result.scalars().all())

            await self._cache_set(cache_key, [s.__dict__.copy() for s in suppliers])

            return suppliers

        except Exception as e:
            raise RepositoryError(f"Failed to list suppliers by region: {str(e)}", e)

    async def get_tariffs(self, supplier_id: str, available_only: bool = True) -> List[Tariff]:
        """
        Get all tariffs for a supplier.

        Args:
            supplier_id: Supplier ID
            available_only: Whether to include only available tariffs

        Returns:
            List of tariffs
        """
        try:
            conditions = [Tariff.supplier_id == supplier_id]

            if available_only:
                conditions.append(Tariff.is_available == True)

            query = select(Tariff).where(and_(*conditions)).order_by(Tariff.name)
            result = await self._db.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            raise RepositoryError(f"Failed to get tariffs: {str(e)}", e)

    async def create_tariff(self, tariff: Tariff) -> Tariff:
        """
        Create a new tariff.

        Args:
            tariff: Tariff data to create

        Returns:
            Created tariff
        """
        try:
            tariff.created_at = datetime.now(timezone.utc)
            tariff.updated_at = datetime.now(timezone.utc)

            self._db.add(tariff)
            await self._db.commit()
            await self._db.refresh(tariff)
            return tariff

        except Exception as e:
            await self._db.rollback()
            raise RepositoryError(f"Failed to create tariff: {str(e)}", e)

    async def get_green_suppliers(
        self, region: str, min_renewable_percentage: int = 50
    ) -> List[Supplier]:
        """
        Get suppliers with high renewable energy percentage.

        Args:
            region: Region code
            min_renewable_percentage: Minimum renewable percentage

        Returns:
            List of green suppliers
        """
        try:
            from sqlalchemy import any_

            conditions = [
                region.lower() == any_(Supplier.regions),
                Supplier.is_active == True,
                Supplier.green_energy_provider == True,
            ]

            if min_renewable_percentage > 0:
                conditions.append(Supplier.average_renewable_percentage >= min_renewable_percentage)

            query = (
                select(Supplier)
                .where(and_(*conditions))
                .order_by(Supplier.average_renewable_percentage.desc())
            )
            result = await self._db.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            raise RepositoryError(f"Failed to get green suppliers: {str(e)}", e)


# ==========================================================================
# Supplier Registry (migration 006 — replaces mock data in API layer)
# ==========================================================================


class SupplierRegistryRepository:
    """
    Repository for the supplier_registry table.

    This is the new source of truth for supplier data, replacing
    the hardcoded MOCK_SUPPLIERS list in api/v1/suppliers.py.
    Uses raw SQL since the table has no ORM model yet.

    Caching
    -------
    list_suppliers() and get_by_id() are cached in Redis for 1 hour
    (key prefix: ``supplier_registry:``).  Pass a Redis client as the
    second constructor argument; omit it (or pass None) to disable
    caching and always hit the database.

    Call clear_registry_cache() after any mutation to the
    supplier_registry table.
    """

    def __init__(self, db_session: AsyncSession, cache: Any = None):
        """
        Args:
            db_session: SQLAlchemy async session.
            cache: Optional async Redis client (aioredis.Redis or
                   any object with async get/set/delete/scan_iter).
        """
        self._db = db_session
        self._cache = cache

    # ------------------------------------------------------------------
    # Internal cache helpers
    # ------------------------------------------------------------------

    async def _cache_get(self, key: str) -> Optional[Any]:
        if not self._cache:
            return None
        try:
            raw = await self._cache.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    async def _cache_set(self, key: str, value: Any) -> None:
        if not self._cache:
            return
        try:
            await self._cache.set(
                key,
                json.dumps(value, default=str),
                ex=_SUPPLIER_CACHE_TTL,
            )
        except Exception:
            pass

    async def clear_registry_cache(self) -> None:
        """
        Remove all supplier_registry cache entries.

        Call this after writing to the supplier_registry table so
        subsequent reads pick up the latest data.
        """
        if not self._cache:
            return
        try:
            async for key in self._cache.scan_iter(match="supplier_registry:*"):
                await self._cache.delete(key)
        except Exception:
            pass

    async def list_suppliers(
        self,
        region: Optional[str] = None,
        utility_type: Optional[str] = None,
        green_only: bool = False,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """
        List suppliers with optional filtering.

        Results are cached in Redis for 1 hour.  The cache key encodes
        all filter and pagination parameters so different query shapes
        get independent cache entries.

        Returns:
            Tuple of (list of supplier dicts, total count)
        """
        # Build a deterministic, safe cache key from query parameters.
        cache_key = (
            f"supplier_registry:list"
            f":region={region or ''}"
            f":ut={utility_type or ''}"
            f":green={int(green_only)}"
            f":active={int(active_only)}"
            f":p={page}"
            f":ps={page_size}"
        )
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached["suppliers"], cached["total"]

        try:
            # Build WHERE clause from fixed literal fragments only (no f-string
            # interpolation of variables) to prevent SQL injection (CWE-89).
            count_sql = "SELECT COUNT(*) FROM supplier_registry WHERE 1=1"
            data_sql = (
                "SELECT id, name, utility_types, regions, website, phone,"
                " api_available, rating, review_count, green_energy,"
                " carbon_neutral, is_active, metadata"
                " FROM supplier_registry WHERE 1=1"
            )
            params: dict[str, Any] = {}

            if active_only:
                count_sql += " AND is_active = TRUE"
                data_sql += " AND is_active = TRUE"
            if region:
                count_sql += " AND :region = ANY(regions)"
                data_sql += " AND :region = ANY(regions)"
                params["region"] = region.lower()
            if utility_type:
                count_sql += " AND :utility_type::utility_type = ANY(utility_types)"
                data_sql += " AND :utility_type::utility_type = ANY(utility_types)"
                params["utility_type"] = utility_type
            if green_only:
                count_sql += " AND green_energy = TRUE"
                data_sql += " AND green_energy = TRUE"

            data_sql += " ORDER BY rating DESC NULLS LAST, name LIMIT :limit OFFSET :offset"

            count_result = await self._db.execute(text(count_sql), params)
            total = count_result.scalar() or 0

            offset = (page - 1) * page_size
            data_params = {**params, "limit": page_size, "offset": offset}

            result = await self._db.execute(text(data_sql), data_params)
            rows = result.mappings().all()

            suppliers = [
                {
                    "id": str(row["id"]),
                    "name": row["name"],
                    "utility_types": list(row["utility_types"]),
                    "regions": list(row["regions"]),
                    "website": row["website"],
                    "phone": row["phone"],
                    "api_available": row["api_available"],
                    "rating": float(row["rating"]) if row["rating"] else None,
                    "review_count": row["review_count"] or 0,
                    "green_energy_provider": row["green_energy"],
                    "carbon_neutral": row["carbon_neutral"],
                    "is_active": row["is_active"],
                    "metadata": row["metadata"] or {},
                    "tariff_types": ["fixed", "variable"],
                }
                for row in rows
            ]

            await self._cache_set(cache_key, {"suppliers": suppliers, "total": total})

            return suppliers, total

        except Exception as e:
            raise RepositoryError(f"Failed to list suppliers: {str(e)}", e)

    async def get_by_id(self, supplier_id: str) -> Optional[dict]:
        """
        Get a single supplier by its UUID.

        Result is cached in Redis for 1 hour
        (key: supplier_registry:id:<supplier_id>).
        """
        cache_key = f"supplier_registry:id:{supplier_id}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            result = await self._db.execute(
                text("""
                    SELECT id, name, utility_types, regions, website, phone,
                           api_available, rating, review_count, green_energy,
                           carbon_neutral, is_active, metadata
                    FROM supplier_registry WHERE id = :id
                """),
                {"id": supplier_id},
            )
            row = result.mappings().first()
            if not row:
                return None

            supplier = {
                "id": str(row["id"]),
                "name": row["name"],
                "utility_types": list(row["utility_types"]),
                "regions": list(row["regions"]),
                "website": row["website"],
                "phone": row["phone"],
                "api_available": row["api_available"],
                "rating": float(row["rating"]) if row["rating"] else None,
                "review_count": row["review_count"] or 0,
                "green_energy_provider": row["green_energy"],
                "carbon_neutral": row["carbon_neutral"],
                "is_active": row["is_active"],
                "metadata": row["metadata"] or {},
                "tariff_types": ["fixed", "variable"],
            }

            await self._cache_set(cache_key, supplier)

            return supplier

        except Exception as e:
            raise RepositoryError(f"Failed to get supplier: {str(e)}", e)


# ==========================================================================
# State Regulations
# ==========================================================================


class StateRegulationRepository:
    """
    Repository for state_regulations table (migration 006).
    """

    def __init__(self, db_session: AsyncSession):
        self._db = db_session

    async def get_by_state(self, state_code: str) -> Optional[dict]:
        """Get regulation info for a US state."""
        try:
            result = await self._db.execute(
                text("SELECT * FROM state_regulations WHERE state_code = :code"),
                {"code": state_code.upper()},
            )
            row = result.mappings().first()
            return dict(row) if row else None
        except Exception as e:
            raise RepositoryError(f"Failed to get state regulation: {str(e)}", e)

    async def list_deregulated(
        self,
        electricity: Optional[bool] = None,
        gas: Optional[bool] = None,
        oil: Optional[bool] = None,
        community_solar: Optional[bool] = None,
    ) -> list[dict]:
        """List states matching deregulation criteria."""
        try:
            # Build WHERE from fixed literal fragments only (no f-string
            # interpolation) to prevent SQL injection (CWE-89).
            sql = "SELECT * FROM state_regulations WHERE 1=1"
            params: dict[str, Any] = {}

            if electricity is not None:
                sql += " AND electricity_deregulated = :elec"
                params["elec"] = electricity
            if gas is not None:
                sql += " AND gas_deregulated = :gas"
                params["gas"] = gas
            if oil is not None:
                sql += " AND oil_competitive = :oil"
                params["oil"] = oil
            if community_solar is not None:
                sql += " AND community_solar_enabled = :solar"
                params["solar"] = community_solar

            sql += " ORDER BY state_code"

            result = await self._db.execute(text(sql), params)
            return [dict(row) for row in result.mappings().all()]

        except Exception as e:
            raise RepositoryError(f"Failed to list regulations: {str(e)}", e)
