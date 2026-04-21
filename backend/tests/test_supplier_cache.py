"""
Supplier Repository Cache Tests

Verifies that SupplierRegistryRepository:
- Returns cached results on a cache hit (DB is NOT queried).
- Falls through to the DB on a cache miss and populates the cache.
- Invalidates relevant cache keys after write operations.
- Degrades gracefully when Redis is unavailable (cache=None).
- clear_registry_cache() wipes the correct key namespace.

Note: The legacy SupplierRepository was removed in S4-11 audit remediation.
"""

import json
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_redis(*, hit_value=None) -> AsyncMock:
    """
    Build a minimal async Redis mock.

    Args:
        hit_value: JSON-serialized string returned by get().  None = cache miss.
    """
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=hit_value)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    # scan_iter must be an async generator
    redis.scan_iter = _async_iter_factory([])
    return redis


def _async_iter_factory(items):
    """Return a factory that produces a fresh async generator each call."""

    async def _gen(*args, **kwargs):
        for item in items:
            yield item

    return _gen


def _make_db_session() -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.delete = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    return session


def _mapping_result(rows: list) -> MagicMock:
    """Wrap rows so result.mappings().all() / .first() work."""
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    result.mappings.return_value.first.return_value = rows[0] if rows else None
    result.scalar.return_value = len(rows)
    return result


# ---------------------------------------------------------------------------
# SupplierRegistryRepository — list_suppliers
# ---------------------------------------------------------------------------


class TestSupplierRegistryCacheListSuppliers:
    async def test_cache_miss_queries_db_and_populates_cache(self):
        """On a cache miss list_suppliers hits the DB and writes to Redis."""
        from repositories.supplier_repository import SupplierRegistryRepository

        row = {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "Test Supplier",
            "utility_types": ["electricity"],
            "regions": ["us_ct"],
            "website": "https://example.com",
            "phone": None,
            "api_available": False,
            "rating": 4.5,
            "review_count": 10,
            "green_energy": True,
            "carbon_neutral": False,
            "is_active": True,
            "metadata": {},
        }

        db = _make_db_session()
        # count query returns 1, data query returns the row
        db.execute.side_effect = [_mapping_result([row]), _mapping_result([row])]

        redis = _make_redis(hit_value=None)  # cache miss

        repo = SupplierRegistryRepository(db, cache=redis)
        suppliers, total = await repo.list_suppliers(region="us_ct")

        assert total == 1
        assert suppliers[0]["name"] == "Test Supplier"
        # DB was queried (count + data = 2 calls)
        assert db.execute.call_count == 2
        # Cache was written
        redis.set.assert_called_once()
        written_payload = json.loads(redis.set.call_args[0][1])
        assert written_payload["total"] == 1

    async def test_cache_hit_skips_db(self):
        """On a cache hit list_suppliers returns cached data without DB access."""
        from repositories.supplier_repository import SupplierRegistryRepository

        cached_payload = json.dumps(
            {
                "suppliers": [
                    {
                        "id": "abc",
                        "name": "Cached Supplier",
                        "utility_types": ["electricity"],
                        "regions": ["us_ct"],
                        "website": None,
                        "phone": None,
                        "api_available": False,
                        "rating": None,
                        "review_count": 0,
                        "green_energy_provider": False,
                        "carbon_neutral": False,
                        "is_active": True,
                        "metadata": {},
                        "tariff_types": ["fixed", "variable"],
                    }
                ],
                "total": 1,
            }
        )

        db = _make_db_session()
        redis = _make_redis(hit_value=cached_payload)

        repo = SupplierRegistryRepository(db, cache=redis)
        suppliers, total = await repo.list_suppliers(region="us_ct")

        assert total == 1
        assert suppliers[0]["name"] == "Cached Supplier"
        # DB must NOT have been touched
        db.execute.assert_not_called()

    async def test_no_cache_client_falls_through_to_db(self):
        """With cache=None every call goes straight to the database."""
        from repositories.supplier_repository import SupplierRegistryRepository

        row = {
            "id": "00000000-0000-0000-0000-000000000002",
            "name": "Direct Supplier",
            "utility_types": ["natural_gas"],
            "regions": ["us_ma"],
            "website": None,
            "phone": None,
            "api_available": False,
            "rating": None,
            "review_count": 0,
            "green_energy": False,
            "carbon_neutral": False,
            "is_active": True,
            "metadata": {},
        }

        db = _make_db_session()
        db.execute.side_effect = [_mapping_result([row]), _mapping_result([row])]

        repo = SupplierRegistryRepository(db, cache=None)
        suppliers, total = await repo.list_suppliers()

        assert total == 1
        assert db.execute.call_count == 2

    async def test_different_filter_combinations_use_distinct_cache_keys(self):
        """
        Two calls with different parameters must produce distinct cache
        keys so they do not share cached results.
        """
        from repositories.supplier_repository import SupplierRegistryRepository

        # Always a cache miss so both calls hit the DB.
        row_a = {
            "id": "aaa",
            "name": "Supplier A",
            "utility_types": ["electricity"],
            "regions": ["us_ct"],
            "website": None,
            "phone": None,
            "api_available": False,
            "rating": None,
            "review_count": 0,
            "green_energy": False,
            "carbon_neutral": False,
            "is_active": True,
            "metadata": {},
        }
        row_b = {
            "id": "bbb",
            "name": "Supplier B",
            "utility_types": ["natural_gas"],
            "regions": ["us_ma"],
            "website": None,
            "phone": None,
            "api_available": False,
            "rating": None,
            "review_count": 0,
            "green_energy": True,
            "carbon_neutral": True,
            "is_active": True,
            "metadata": {},
        }

        db = _make_db_session()
        db.execute.side_effect = [
            _mapping_result([row_a]),
            _mapping_result([row_a]),
            _mapping_result([row_b]),
            _mapping_result([row_b]),
        ]
        redis = _make_redis(hit_value=None)

        repo = SupplierRegistryRepository(db, cache=redis)
        await repo.list_suppliers(region="us_ct")
        await repo.list_suppliers(region="us_ma", green_only=True)

        # Two separate set() calls with different keys
        assert redis.set.call_count == 2
        key_a = redis.set.call_args_list[0][0][0]
        key_b = redis.set.call_args_list[1][0][0]
        assert key_a != key_b
        assert "us_ct" in key_a
        assert "us_ma" in key_b


# ---------------------------------------------------------------------------
# SupplierRegistryRepository — get_by_id
# ---------------------------------------------------------------------------


class TestSupplierRegistryCacheGetById:
    async def test_cache_miss_queries_db_and_writes_cache(self):
        from repositories.supplier_repository import SupplierRegistryRepository

        row = MagicMock()
        row.__getitem__ = lambda self, k: {
            "id": "00000000-0000-0000-0000-000000000010",
            "name": "Eversource Energy",
            "utility_types": ["electricity"],
            "regions": ["us_ct"],
            "website": "https://eversource.com",
            "phone": None,
            "api_available": False,
            "rating": 4.2,
            "review_count": 55,
            "green_energy": False,
            "carbon_neutral": False,
            "is_active": True,
            "metadata": {},
        }[k]

        db = _make_db_session()
        result = MagicMock()
        result.mappings.return_value.first.return_value = row
        db.execute.return_value = result

        redis = _make_redis(hit_value=None)

        repo = SupplierRegistryRepository(db, cache=redis)
        supplier = await repo.get_by_id("00000000-0000-0000-0000-000000000010")

        assert supplier is not None
        assert supplier["name"] == "Eversource Energy"
        db.execute.assert_called_once()
        redis.set.assert_called_once()
        # Verify the key contains the supplier ID
        key = redis.set.call_args[0][0]
        assert "00000000-0000-0000-0000-000000000010" in key

    async def test_cache_hit_skips_db_get_by_id(self):
        from repositories.supplier_repository import SupplierRegistryRepository

        cached = json.dumps(
            {
                "id": "00000000-0000-0000-0000-000000000010",
                "name": "Eversource Energy",
                "utility_types": ["electricity"],
                "regions": ["us_ct"],
                "website": None,
                "phone": None,
                "api_available": False,
                "rating": 4.2,
                "review_count": 55,
                "green_energy_provider": False,
                "carbon_neutral": False,
                "is_active": True,
                "metadata": {},
                "tariff_types": ["fixed", "variable"],
            }
        )

        db = _make_db_session()
        redis = _make_redis(hit_value=cached)

        repo = SupplierRegistryRepository(db, cache=redis)
        supplier = await repo.get_by_id("00000000-0000-0000-0000-000000000010")

        assert supplier["name"] == "Eversource Energy"
        db.execute.assert_not_called()

    async def test_get_by_id_returns_none_for_missing_supplier(self):
        from repositories.supplier_repository import SupplierRegistryRepository

        db = _make_db_session()
        result = MagicMock()
        result.mappings.return_value.first.return_value = None
        db.execute.return_value = result

        redis = _make_redis(hit_value=None)

        repo = SupplierRegistryRepository(db, cache=redis)
        supplier = await repo.get_by_id("00000000-0000-0000-0000-000000000099")

        assert supplier is None
        # Nothing to cache for a missing supplier
        redis.set.assert_not_called()


# ---------------------------------------------------------------------------
# SupplierRegistryRepository — clear_registry_cache
# ---------------------------------------------------------------------------


class TestSupplierRegistryClearCache:
    async def test_clear_registry_cache_deletes_all_keys(self):
        """clear_registry_cache() scans and deletes every supplier_registry:* key."""
        from repositories.supplier_repository import SupplierRegistryRepository

        existing_keys = [
            "supplier_registry:list:region=us_ct:ut=:green=0:active=1:p=1:ps=20",
            "supplier_registry:id:00000000-0000-0000-0000-000000000010",
        ]

        db = _make_db_session()
        redis = _make_redis()
        redis.scan_iter = _async_iter_factory(existing_keys)

        repo = SupplierRegistryRepository(db, cache=redis)
        await repo.clear_registry_cache()

        assert redis.delete.call_count == len(existing_keys)
        deleted_keys = {c.args[0] for c in redis.delete.call_args_list}
        assert deleted_keys == set(existing_keys)

    async def test_clear_registry_cache_no_op_without_redis(self):
        """clear_registry_cache() is a no-op when no cache client is provided."""
        from repositories.supplier_repository import SupplierRegistryRepository

        db = _make_db_session()
        repo = SupplierRegistryRepository(db, cache=None)
        # Should not raise
        await repo.clear_registry_cache()

    async def test_clear_registry_cache_survives_redis_error(self):
        """If Redis raises during clear, the method should not propagate the error."""
        from repositories.supplier_repository import SupplierRegistryRepository

        db = _make_db_session()
        redis = _make_redis()

        async def _broken_scan(*args, **kwargs):
            raise ConnectionError("Redis gone")
            yield  # make it a generator

        redis.scan_iter = _broken_scan

        repo = SupplierRegistryRepository(db, cache=redis)
        # Must not raise
        await repo.clear_registry_cache()


# ---------------------------------------------------------------------------
# Redis error resilience
# ---------------------------------------------------------------------------


class TestCacheErrorResilience:
    async def test_list_suppliers_continues_if_cache_get_fails(self):
        """If Redis.get() throws, list_suppliers falls through to the DB."""
        from repositories.supplier_repository import SupplierRegistryRepository

        row = {
            "id": "00000000-0000-0000-0000-000000000020",
            "name": "Fallback Supplier",
            "utility_types": ["electricity"],
            "regions": ["us_tx"],
            "website": None,
            "phone": None,
            "api_available": False,
            "rating": None,
            "review_count": 0,
            "green_energy": False,
            "carbon_neutral": False,
            "is_active": True,
            "metadata": {},
        }

        db = _make_db_session()
        db.execute.side_effect = [_mapping_result([row]), _mapping_result([row])]

        redis = _make_redis()
        redis.get = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

        repo = SupplierRegistryRepository(db, cache=redis)
        suppliers, total = await repo.list_suppliers(region="us_tx")

        assert total == 1
        assert suppliers[0]["name"] == "Fallback Supplier"

    async def test_list_suppliers_continues_if_cache_set_fails(self):
        """If Redis.set() throws after a DB hit, the result is still returned."""
        from repositories.supplier_repository import SupplierRegistryRepository

        row = {
            "id": "00000000-0000-0000-0000-000000000021",
            "name": "Resilient Supplier",
            "utility_types": ["electricity"],
            "regions": ["us_oh"],
            "website": None,
            "phone": None,
            "api_available": False,
            "rating": None,
            "review_count": 0,
            "green_energy": False,
            "carbon_neutral": False,
            "is_active": True,
            "metadata": {},
        }

        db = _make_db_session()
        db.execute.side_effect = [_mapping_result([row]), _mapping_result([row])]

        redis = _make_redis(hit_value=None)
        redis.set = AsyncMock(side_effect=ConnectionError("Redis write failed"))

        repo = SupplierRegistryRepository(db, cache=redis)
        suppliers, total = await repo.list_suppliers(region="us_oh")

        assert total == 1
        assert suppliers[0]["name"] == "Resilient Supplier"

    async def test_get_by_id_continues_if_cache_get_fails(self):
        """If Redis.get() raises for get_by_id, the DB is queried instead."""
        from repositories.supplier_repository import SupplierRegistryRepository

        row = MagicMock()
        row.__getitem__ = lambda self, k: {
            "id": "00000000-0000-0000-0000-000000000030",
            "name": "DB Supplier",
            "utility_types": ["electricity"],
            "regions": ["us_il"],
            "website": None,
            "phone": None,
            "api_available": False,
            "rating": None,
            "review_count": 0,
            "green_energy": False,
            "carbon_neutral": False,
            "is_active": True,
            "metadata": {},
        }[k]

        db = _make_db_session()
        result = MagicMock()
        result.mappings.return_value.first.return_value = row
        db.execute.return_value = result

        redis = _make_redis()
        redis.get = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

        repo = SupplierRegistryRepository(db, cache=redis)
        supplier = await repo.get_by_id("00000000-0000-0000-0000-000000000030")

        assert supplier is not None
        db.execute.assert_called_once()


# ---------------------------------------------------------------------------
# TTL verification
# ---------------------------------------------------------------------------


class TestCacheTTL:
    async def test_list_suppliers_uses_3600s_ttl(self):
        """Cache entries for list_suppliers must be set with a 1-hour TTL."""
        from repositories.supplier_repository import (
            _SUPPLIER_CACHE_TTL, SupplierRegistryRepository)

        row = {
            "id": "00000000-0000-0000-0000-000000000040",
            "name": "TTL Supplier",
            "utility_types": ["electricity"],
            "regions": ["us_ny"],
            "website": None,
            "phone": None,
            "api_available": False,
            "rating": None,
            "review_count": 0,
            "green_energy": False,
            "carbon_neutral": False,
            "is_active": True,
            "metadata": {},
        }

        db = _make_db_session()
        db.execute.side_effect = [_mapping_result([row]), _mapping_result([row])]

        redis = _make_redis(hit_value=None)

        repo = SupplierRegistryRepository(db, cache=redis)
        await repo.list_suppliers(region="us_ny")

        # Verify ex= keyword arg equals the module-level constant
        call_kwargs = redis.set.call_args[1]
        assert call_kwargs.get("ex") == _SUPPLIER_CACHE_TTL
        assert _SUPPLIER_CACHE_TTL == 3600

    async def test_get_by_id_uses_3600s_ttl(self):
        """Cache entries for get_by_id must be set with a 1-hour TTL."""
        from repositories.supplier_repository import (
            _SUPPLIER_CACHE_TTL, SupplierRegistryRepository)

        row = MagicMock()
        row.__getitem__ = lambda self, k: {
            "id": "00000000-0000-0000-0000-000000000041",
            "name": "TTL Lookup",
            "utility_types": ["electricity"],
            "regions": ["us_pa"],
            "website": None,
            "phone": None,
            "api_available": False,
            "rating": None,
            "review_count": 0,
            "green_energy": False,
            "carbon_neutral": False,
            "is_active": True,
            "metadata": {},
        }[k]

        db = _make_db_session()
        result = MagicMock()
        result.mappings.return_value.first.return_value = row
        db.execute.return_value = result

        redis = _make_redis(hit_value=None)

        repo = SupplierRegistryRepository(db, cache=redis)
        await repo.get_by_id("00000000-0000-0000-0000-000000000041")

        call_kwargs = redis.set.call_args[1]
        assert call_kwargs.get("ex") == _SUPPLIER_CACHE_TTL
