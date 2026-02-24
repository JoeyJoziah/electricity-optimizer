"""
Repository Tests - Written FIRST following TDD principles

Tests for:
- PriceRepository with mocked database
- UserRepository with mocked database
- SupplierRepository with mocked database

RED phase: These tests should FAIL initially until repositories are implemented.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch


# =============================================================================
# PRICE REPOSITORY TESTS
# =============================================================================


class TestPriceRepository:
    """Tests for PriceRepository"""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session"""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client"""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        redis.delete = AsyncMock()
        redis.ping = AsyncMock(return_value=True)
        return redis

    @pytest.mark.asyncio
    async def test_get_current_prices_returns_list(self, mock_db_session, mock_redis):
        """Test fetching current prices returns a list"""
        from repositories.price_repository import PriceRepository
        from models.price import Price, PriceRegion

        # Setup mock to return price data as dict rows (raw SQL pattern)
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {
                "id": "price_1",
                "region": "us_ct",
                "supplier": "Eversource Energy",
                "price_per_kwh": Decimal("0.26"),
                "timestamp": datetime.now(timezone.utc),
                "currency": "USD",
                "is_peak": False,
                "source_api": None,
                "created_at": datetime.now(timezone.utc),
                "carbon_intensity": None,
                "utility_type": "electricity",
            }
        ]
        mock_db_session.execute.return_value = mock_result

        repo = PriceRepository(mock_db_session, mock_redis)
        prices = await repo.get_current_prices(region=PriceRegion.UK)

        assert isinstance(prices, list)
        assert len(prices) >= 0

    @pytest.mark.asyncio
    async def test_get_current_prices_filters_by_region(self, mock_db_session, mock_redis):
        """Test current prices are filtered by region"""
        from repositories.price_repository import PriceRepository
        from models.price import PriceRegion

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        repo = PriceRepository(mock_db_session, mock_redis)
        await repo.get_current_prices(region=PriceRegion.UK)

        # Verify execute was called (query was made)
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_price_by_id(self, mock_db_session, mock_redis):
        """Test fetching a single price by ID"""
        from repositories.price_repository import PriceRepository

        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = {
            "id": "price_123",
            "region": "us_ct",
            "supplier": "Test",
            "price_per_kwh": Decimal("0.25"),
            "timestamp": datetime.now(timezone.utc),
            "currency": "USD",
            "is_peak": None,
            "source_api": None,
            "created_at": datetime.now(timezone.utc),
            "carbon_intensity": None,
            "utility_type": "electricity",
        }
        mock_db_session.execute.return_value = mock_result

        repo = PriceRepository(mock_db_session, mock_redis)
        price = await repo.get_by_id("price_123")

        assert price is not None

    @pytest.mark.asyncio
    async def test_get_price_by_id_returns_none_for_missing(self, mock_db_session, mock_redis):
        """Test get_by_id returns None for non-existent price"""
        from repositories.price_repository import PriceRepository

        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        mock_db_session.execute.return_value = mock_result

        repo = PriceRepository(mock_db_session, mock_redis)
        price = await repo.get_by_id("nonexistent_id")

        assert price is None

    @pytest.mark.asyncio
    async def test_create_price(self, mock_db_session, mock_redis):
        """Test creating a new price record"""
        from repositories.price_repository import PriceRepository
        from models.price import Price, PriceRegion

        price_data = Price(
            region=PriceRegion.US_CT,
            supplier="Test Supplier",
            price_per_kwh=Decimal("0.30"),
            timestamp=datetime.now(timezone.utc),
            currency="USD"
        )

        repo = PriceRepository(mock_db_session, mock_redis)
        created = await repo.create(price_data)

        assert created is not None
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_historical_prices(self, mock_db_session, mock_redis):
        """Test fetching historical prices within a date range"""
        from repositories.price_repository import PriceRepository
        from models.price import PriceRegion

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        repo = PriceRepository(mock_db_session, mock_redis)

        start = datetime.now(timezone.utc) - timedelta(days=7)
        end = datetime.now(timezone.utc)

        prices = await repo.get_historical_prices(
            region=PriceRegion.UK,
            start_date=start,
            end_date=end
        )

        assert isinstance(prices, list)
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_latest_price_by_supplier(self, mock_db_session, mock_redis):
        """Test fetching latest price for a specific supplier"""
        from repositories.price_repository import PriceRepository
        from models.price import PriceRegion

        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = {
            "id": "price_latest",
            "region": "us_ct",
            "supplier": "Eversource Energy",
            "price_per_kwh": Decimal("0.26"),
            "timestamp": datetime.now(timezone.utc),
            "currency": "USD",
            "is_peak": True,
            "source_api": "nrel",
            "created_at": datetime.now(timezone.utc),
            "carbon_intensity": None,
            "utility_type": "electricity",
        }
        mock_db_session.execute.return_value = mock_result

        repo = PriceRepository(mock_db_session, mock_redis)
        price = await repo.get_latest_by_supplier(
            region=PriceRegion.UK,
            supplier="Eversource Energy"
        )

        assert price is not None

    @pytest.mark.asyncio
    async def test_bulk_create_prices(self, mock_db_session, mock_redis):
        """Test bulk creating multiple price records"""
        from repositories.price_repository import PriceRepository
        from models.price import Price, PriceRegion

        prices = [
            Price(
                region=PriceRegion.US_CT,
                supplier="Supplier A",
                price_per_kwh=Decimal("0.25"),
                timestamp=datetime.now(timezone.utc),
                currency="USD"
            ),
            Price(
                region=PriceRegion.US_CT,
                supplier="Supplier B",
                price_per_kwh=Decimal("0.27"),
                timestamp=datetime.now(timezone.utc),
                currency="USD"
            )
        ]

        repo = PriceRepository(mock_db_session, mock_redis)
        count = await repo.bulk_create(prices)

        assert count == 2
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_repository_handles_db_error(self, mock_db_session, mock_redis):
        """Test repository handles database errors gracefully"""
        from repositories.price_repository import PriceRepository
        from models.price import PriceRegion
        from repositories.base import RepositoryError

        mock_db_session.execute.side_effect = Exception("DB Connection Error")

        repo = PriceRepository(mock_db_session, mock_redis)

        with pytest.raises(RepositoryError):
            await repo.get_current_prices(region=PriceRegion.UK)

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self, mock_db_session, mock_redis):
        """Test that cache hit skips database query"""
        from repositories.price_repository import PriceRepository
        from models.price import PriceRegion
        import json

        # Setup cache to return data
        cached_data = json.dumps([{
            "id": "cached_price",
            "region": "us_ct",
            "supplier": "Cached Supplier",
            "price_per_kwh": "0.20",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "currency": "USD"
        }])
        mock_redis.get.return_value = cached_data

        repo = PriceRepository(mock_db_session, mock_redis)
        prices = await repo.get_current_prices(region=PriceRegion.UK)

        # Database should NOT be called
        mock_db_session.execute.assert_not_called()


# =============================================================================
# USER REPOSITORY TESTS
# =============================================================================


class TestUserRepository:
    """Tests for UserRepository"""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session"""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_get_user_by_id(self, mock_db_session):
        """Test fetching a user by ID"""
        from repositories.user_repository import UserRepository

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            id="user_123",
            email="test@example.com",
            name="Test User",
            region="us_ct"
        )
        mock_db_session.execute.return_value = mock_result

        repo = UserRepository(mock_db_session)
        user = await repo.get_by_id("user_123")

        assert user is not None

    @pytest.mark.asyncio
    async def test_get_user_by_email(self, mock_db_session):
        """Test fetching a user by email"""
        from repositories.user_repository import UserRepository

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            id="user_123",
            email="test@example.com",
            name="Test User",
            region="us_ct"
        )
        mock_db_session.execute.return_value = mock_result

        repo = UserRepository(mock_db_session)
        user = await repo.get_by_email("test@example.com")

        assert user is not None

    @pytest.mark.asyncio
    async def test_create_user(self, mock_db_session):
        """Test creating a new user"""
        from repositories.user_repository import UserRepository
        from models.user import User

        user_data = User(
            email="new@example.com",
            name="New User",
            region="us_ct"
        )

        repo = UserRepository(mock_db_session)
        created = await repo.create(user_data)

        assert created is not None
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_user_preferences(self, mock_db_session):
        """Test updating user preferences"""
        from repositories.user_repository import UserRepository
        from models.user import UserPreferences

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            id="user_123",
            preferences={}
        )
        mock_db_session.execute.return_value = mock_result

        prefs = UserPreferences(
            notification_enabled=True,
            auto_switch_enabled=True
        )

        repo = UserRepository(mock_db_session)
        updated = await repo.update_preferences("user_123", prefs)

        assert updated is not None
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_delete_user(self, mock_db_session):
        """Test deleting a user"""
        from repositories.user_repository import UserRepository

        repo = UserRepository(mock_db_session)
        result = await repo.delete("user_123")

        assert result is True
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_users_paginated(self, mock_db_session):
        """Test listing users with pagination"""
        from repositories.user_repository import UserRepository

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            MagicMock(id="user_1"),
            MagicMock(id="user_2")
        ]
        mock_db_session.execute.return_value = mock_result

        repo = UserRepository(mock_db_session)
        users = await repo.list(page=1, page_size=10)

        assert isinstance(users, list)
        assert len(users) == 2


# =============================================================================
# SUPPLIER REPOSITORY TESTS
# =============================================================================


class TestSupplierRepository:
    """Tests for SupplierRepository"""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session"""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_get_supplier_by_id(self, mock_db_session):
        """Test fetching a supplier by ID"""
        from repositories.supplier_repository import SupplierRepository

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(
            id="supplier_123",
            name="Eversource Energy",
            regions=["us_ct"]
        )
        mock_db_session.execute.return_value = mock_result

        repo = SupplierRepository(mock_db_session)
        supplier = await repo.get_by_id("supplier_123")

        assert supplier is not None

    @pytest.mark.asyncio
    async def test_list_suppliers_by_region(self, mock_db_session):
        """Test listing suppliers for a specific region"""
        from repositories.supplier_repository import SupplierRepository

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            MagicMock(id="s1", name="Supplier 1", regions=["us_ct"]),
            MagicMock(id="s2", name="Supplier 2", regions=["us_ct"])
        ]
        mock_db_session.execute.return_value = mock_result

        repo = SupplierRepository(mock_db_session)
        suppliers = await repo.list_by_region("us_ct")

        assert isinstance(suppliers, list)

    @pytest.mark.asyncio
    async def test_get_supplier_tariffs(self, mock_db_session):
        """Test fetching tariffs for a supplier"""
        from repositories.supplier_repository import SupplierRepository

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            MagicMock(id="t1", name="Standard Service"),
            MagicMock(id="t2", name="Time of Use")
        ]
        mock_db_session.execute.return_value = mock_result

        repo = SupplierRepository(mock_db_session)
        tariffs = await repo.get_tariffs("supplier_123")

        assert isinstance(tariffs, list)
