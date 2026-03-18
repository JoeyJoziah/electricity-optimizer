"""
Repository Tests - Written FIRST following TDD principles

Tests for:
- PriceRepository with mocked database
- UserRepository with mocked database
- SupplierRepository with mocked database

RED phase: These tests should FAIL initially until repositories are implemented.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
        from models.price import Price, PriceRegion
        from repositories.price_repository import PriceRepository

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
        from models.price import PriceRegion
        from repositories.price_repository import PriceRepository

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
        from models.price import Price, PriceRegion
        from repositories.price_repository import PriceRepository

        price_data = Price(
            region=PriceRegion.US_CT,
            supplier="Test Supplier",
            price_per_kwh=Decimal("0.30"),
            timestamp=datetime.now(timezone.utc),
            currency="USD",
        )

        repo = PriceRepository(mock_db_session, mock_redis)
        created = await repo.create(price_data)

        assert created is not None
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_historical_prices(self, mock_db_session, mock_redis):
        """Test fetching historical prices within a date range"""
        from models.price import PriceRegion
        from repositories.price_repository import PriceRepository

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        repo = PriceRepository(mock_db_session, mock_redis)

        start = datetime.now(timezone.utc) - timedelta(days=7)
        end = datetime.now(timezone.utc)

        prices = await repo.get_historical_prices(
            region=PriceRegion.UK, start_date=start, end_date=end
        )

        assert isinstance(prices, list)
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_latest_price_by_supplier(self, mock_db_session, mock_redis):
        """Test fetching latest price for a specific supplier"""
        from models.price import PriceRegion
        from repositories.price_repository import PriceRepository

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
            region=PriceRegion.UK, supplier="Eversource Energy"
        )

        assert price is not None

    @pytest.mark.asyncio
    async def test_bulk_create_prices(self, mock_db_session, mock_redis):
        """Test bulk creating multiple price records"""
        from models.price import Price, PriceRegion
        from repositories.price_repository import PriceRepository

        prices = [
            Price(
                region=PriceRegion.US_CT,
                supplier="Supplier A",
                price_per_kwh=Decimal("0.25"),
                timestamp=datetime.now(timezone.utc),
                currency="USD",
            ),
            Price(
                region=PriceRegion.US_CT,
                supplier="Supplier B",
                price_per_kwh=Decimal("0.27"),
                timestamp=datetime.now(timezone.utc),
                currency="USD",
            ),
        ]

        repo = PriceRepository(mock_db_session, mock_redis)
        count = await repo.bulk_create(prices)

        assert count == 2
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_repository_handles_db_error(self, mock_db_session, mock_redis):
        """Test repository handles database errors gracefully"""
        from models.price import PriceRegion
        from repositories.base import RepositoryError
        from repositories.price_repository import PriceRepository

        mock_db_session.execute.side_effect = Exception("DB Connection Error")

        repo = PriceRepository(mock_db_session, mock_redis)

        with pytest.raises(RepositoryError):
            await repo.get_current_prices(region=PriceRegion.UK)

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self, mock_db_session, mock_redis):
        """Test that cache hit skips database query"""
        import json

        from models.price import PriceRegion
        from repositories.price_repository import PriceRepository

        # Setup cache to return data
        cached_data = json.dumps(
            [
                {
                    "id": "cached_price",
                    "region": "us_ct",
                    "supplier": "Cached Supplier",
                    "price_per_kwh": "0.20",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "currency": "USD",
                }
            ]
        )
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

    def _make_user_row(self, **overrides):
        """Build a mock row mapping that mimics a raw SQL SELECT result."""
        from datetime import datetime, timezone

        defaults = {
            "id": "user_123",
            "email": "test@example.com",
            "name": "Test User",
            "region": "us_ct",
            "preferences": {},
            "current_supplier": None,
            "is_active": True,
            "is_verified": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "stripe_customer_id": None,
            "subscription_tier": "free",
            "email_verified": False,
            "current_tariff": None,
            "average_daily_kwh": None,
            "household_size": None,
            "current_supplier_id": None,
            "utility_types": None,
            "annual_usage_kwh": None,
            "onboarding_completed": False,
        }
        defaults.update(overrides)
        row = MagicMock()
        row.keys.return_value = list(defaults.keys())
        row.__getitem__ = lambda self, key: defaults[key]
        return row

    def _mock_result_with_row(self, row):
        """Wrap a row mock in a result mock with .mappings().first()."""
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = row
        return mock_result

    @pytest.mark.asyncio
    async def test_get_user_by_id(self, mock_db_session):
        """Test fetching a user by ID"""
        from repositories.user_repository import UserRepository

        row = self._make_user_row(id="user_123")
        mock_db_session.execute.return_value = self._mock_result_with_row(row)

        repo = UserRepository(mock_db_session)
        user = await repo.get_by_id("user_123")

        assert user is not None
        assert user.id == "user_123"
        assert user.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_user_by_email(self, mock_db_session):
        """Test fetching a user by email"""
        from repositories.user_repository import UserRepository

        row = self._make_user_row(email="test@example.com")
        mock_db_session.execute.return_value = self._mock_result_with_row(row)

        repo = UserRepository(mock_db_session)
        user = await repo.get_by_email("test@example.com")

        assert user is not None
        assert user.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_create_user(self, mock_db_session):
        """Test creating a new user"""
        from models.user import User
        from repositories.user_repository import UserRepository

        user_data = User(email="new@example.com", name="New User", region="us_ct")

        row = self._make_user_row(email="new@example.com", name="New User", region="us_ct")
        mock_db_session.execute.return_value = self._mock_result_with_row(row)

        repo = UserRepository(mock_db_session)
        created = await repo.create(user_data)

        assert created is not None
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_user_preferences(self, mock_db_session):
        """Test updating user preferences"""
        from models.user import UserPreferences
        from repositories.user_repository import UserRepository

        row = self._make_user_row(preferences={"notification_enabled": True})
        mock_db_session.execute.return_value = self._mock_result_with_row(row)

        prefs = UserPreferences(notification_enabled=True, auto_switch_enabled=True)

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

        row1 = self._make_user_row(id="user_1", email="u1@example.com", name="User 1")
        row2 = self._make_user_row(id="user_2", email="u2@example.com", name="User 2")

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [row1, row2]
        mock_db_session.execute.return_value = mock_result

        repo = UserRepository(mock_db_session)
        users = await repo.list(page=1, page_size=10)

        assert isinstance(users, list)
        assert len(users) == 2


# =============================================================================
# SUPPLIER REPOSITORY TESTS
# =============================================================================


class TestSupplierRepositoryRemoved:
    """Verify that the deprecated SupplierRepository has been removed (S4-11)."""

    def test_supplier_repository_import_raises(self):
        """Importing SupplierRepository gives a stub that raises ImportError."""
        from repositories.supplier_repository import SupplierRepository

        with pytest.raises(ImportError, match="removed"):
            SupplierRepository(None)

    def test_supplier_registry_repository_importable(self):
        """SupplierRegistryRepository should still be importable and usable."""
        from repositories.supplier_repository import SupplierRegistryRepository

        assert SupplierRegistryRepository is not None
