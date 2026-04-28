"""
Supplier Repository

Data access layer for supplier and tariff data.
Includes the SupplierRegistryRepository (backed by supplier_registry table)
and StateRegulationRepository (backed by state_regulations table).

Caching strategy
----------------
SupplierRegistryRepository accepts an optional Redis client.  When Redis is
unavailable (client is None) the repository falls through to the database
transparently.

TTL: 3600 s (1 hour) for all supplier queries — supplier data is semi-static.
Keys follow the pattern:  supplier_registry:<method>:<args...>

Cache invalidation is explicit via clear_registry_cache().

.. note::
    The legacy ``SupplierRepository`` class was removed in the Sprint 4
    audit remediation (S4-11). It used Pydantic models with SQLAlchemy ORM
    calls, which is fundamentally broken at runtime. All production code
    paths use :class:`SupplierRegistryRepository` (raw SQL, supplier_registry
    table). See ADR-006 for details.
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.base import MAX_PAGE_SIZE, RepositoryError

# 1-hour TTL for all supplier-registry caches.
_SUPPLIER_CACHE_TTL = 3600


class _RemovedSupplierRepository:
    """Stub so that any stale import of SupplierRepository raises a clear error."""

    def __init__(self, *_args: Any, **_kwargs: Any):
        raise ImportError(
            "SupplierRepository has been removed (S4-11 audit remediation). "
            "Use SupplierRegistryRepository instead."
        )


# Backwards-compatible name: importing SupplierRepository still works, but
# instantiating it raises ImportError with a migration guide.
SupplierRepository = _RemovedSupplierRepository


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

    async def _cache_get(self, key: str) -> Any | None:
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
        region: str | None = None,
        utility_type: str | None = None,
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
        page_size = max(1, min(MAX_PAGE_SIZE, page_size))

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

            data_sql += (
                " ORDER BY rating DESC NULLS LAST, name LIMIT :limit OFFSET :offset"
            )

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

    async def get_by_id(self, supplier_id: str) -> dict | None:
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

    async def get_by_state(self, state_code: str) -> dict | None:
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
        electricity: bool | None = None,
        gas: bool | None = None,
        oil: bool | None = None,
        community_solar: bool | None = None,
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
