"""Tests for Community Solar Service and API endpoints."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.region import COMMUNITY_SOLAR_STATES
from services.community_solar_service import CommunitySolarService

# ---------------------------------------------------------------------------
# Unit tests: CommunitySolarService.calculate_savings (pure logic, no DB)
# ---------------------------------------------------------------------------


class TestCalculateSavings:
    """Test the static savings calculator."""

    def test_basic_savings_10_percent(self):
        result = CommunitySolarService.calculate_savings(
            monthly_bill=Decimal("150.00"),
            savings_percent=Decimal("10"),
        )
        assert result["monthly_savings"] == "15.00"
        assert result["annual_savings"] == "180.00"
        assert result["five_year_savings"] == "900.00"
        assert result["new_monthly_bill"] == "135.00"

    def test_savings_20_percent(self):
        result = CommunitySolarService.calculate_savings(
            monthly_bill=Decimal("200.00"),
            savings_percent=Decimal("20"),
        )
        assert result["monthly_savings"] == "40.00"
        assert result["annual_savings"] == "480.00"
        assert result["five_year_savings"] == "2400.00"
        assert result["new_monthly_bill"] == "160.00"

    def test_savings_rounding(self):
        # 33% of $100 = $33.33... -> rounds to $33.33
        result = CommunitySolarService.calculate_savings(
            monthly_bill=Decimal("100.00"),
            savings_percent=Decimal("33.33"),
        )
        assert result["monthly_savings"] == "33.33"
        assert result["annual_savings"] == "399.96"
        assert result["new_monthly_bill"] == "66.67"

    def test_small_bill(self):
        result = CommunitySolarService.calculate_savings(
            monthly_bill=Decimal("30.00"),
            savings_percent=Decimal("5"),
        )
        assert result["monthly_savings"] == "1.50"
        assert result["annual_savings"] == "18.00"

    def test_high_savings_percent(self):
        result = CommunitySolarService.calculate_savings(
            monthly_bill=Decimal("100.00"),
            savings_percent=Decimal("100"),
        )
        assert result["monthly_savings"] == "100.00"
        assert result["new_monthly_bill"] == "0.00"

    def test_preserves_input_values(self):
        result = CommunitySolarService.calculate_savings(
            monthly_bill=Decimal("150.00"),
            savings_percent=Decimal("10"),
        )
        assert result["current_monthly_bill"] == "150.00"
        assert result["savings_percent"] == "10"


# ---------------------------------------------------------------------------
# Unit tests: CommunitySolarService with mocked DB
# ---------------------------------------------------------------------------


class TestCommunitySolarServiceDB:
    """Test service methods that interact with the database."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        return CommunitySolarService(mock_db)

    async def test_get_programs_returns_list(self, service, mock_db):
        program_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_row = {
            "id": program_id,
            "state": "NY",
            "program_name": "Test Solar",
            "provider": "TestCo",
            "savings_percent": Decimal("10.00"),
            "capacity_kw": Decimal("5000.00"),
            "spots_available": 100,
            "enrollment_url": "https://example.com",
            "enrollment_status": "open",
            "description": "Test program",
            "min_bill_amount": Decimal("50.00"),
            "contract_months": 12,
            "updated_at": now,
        }

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [mock_row]
        mock_db.execute.return_value = mock_result

        programs = await service.get_programs(state="NY")

        assert len(programs) == 1
        assert programs[0]["program_name"] == "Test Solar"
        assert programs[0]["provider"] == "TestCo"
        assert programs[0]["savings_percent"] == "10.00"
        assert programs[0]["enrollment_status"] == "open"

    async def test_get_programs_empty_state(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        programs = await service.get_programs(state="WY")
        assert programs == []

    async def test_get_program_by_id_found(self, service, mock_db):
        program_id = uuid.uuid4()
        now = datetime.now(UTC)
        mock_row = {
            "id": program_id,
            "state": "MA",
            "program_name": "MA Solar",
            "provider": "Clearway",
            "savings_percent": Decimal("15.00"),
            "capacity_kw": Decimal("4000.00"),
            "spots_available": 120,
            "enrollment_url": "https://example.com",
            "enrollment_status": "open",
            "description": "MA community solar",
            "min_bill_amount": Decimal("60.00"),
            "contract_months": 24,
            "created_at": now,
            "updated_at": now,
        }

        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = mock_row
        mock_db.execute.return_value = mock_result

        program = await service.get_program_by_id(str(program_id))

        assert program is not None
        assert program["program_name"] == "MA Solar"
        assert program["savings_percent"] == "15.00"

    async def test_get_program_by_id_not_found(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        program = await service.get_program_by_id(str(uuid.uuid4()))
        assert program is None

    async def test_get_state_program_count(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"state": "NY", "program_count": 3},
            {"state": "MA", "program_count": 2},
        ]
        mock_db.execute.return_value = mock_result

        counts = await service.get_state_program_count()
        assert counts == {"NY": 3, "MA": 2}


# ---------------------------------------------------------------------------
# API validation tests (testing endpoint logic directly)
# ---------------------------------------------------------------------------


class TestCommunitySolarAPIValidation:
    """Test community solar API validation logic."""

    def test_community_solar_states_exist(self):
        """Verify COMMUNITY_SOLAR_STATES has expected states."""
        assert "NY" in COMMUNITY_SOLAR_STATES
        assert "MA" in COMMUNITY_SOLAR_STATES
        assert "MN" in COMMUNITY_SOLAR_STATES
        assert "CO" in COMMUNITY_SOLAR_STATES
        assert len(COMMUNITY_SOLAR_STATES) >= 10

    def test_invalid_state_not_in_community_solar(self):
        assert "ZZ" not in COMMUNITY_SOLAR_STATES
        assert "AK" not in COMMUNITY_SOLAR_STATES  # Alaska has no community solar

    def test_savings_calc_rejects_zero_bill_logically(self):
        """Savings on $0 bill is $0 — endpoint should reject but calc works."""
        result = CommunitySolarService.calculate_savings(
            monthly_bill=Decimal("0"),
            savings_percent=Decimal("10"),
        )
        assert result["monthly_savings"] == "0.00"

    def test_savings_calc_with_large_bill(self):
        result = CommunitySolarService.calculate_savings(
            monthly_bill=Decimal("500.00"),
            savings_percent=Decimal("15"),
        )
        assert result["monthly_savings"] == "75.00"
        assert result["annual_savings"] == "900.00"
        assert result["five_year_savings"] == "4500.00"

    def test_savings_calc_fractional_percent(self):
        result = CommunitySolarService.calculate_savings(
            monthly_bill=Decimal("100.00"),
            savings_percent=Decimal("7.5"),
        )
        assert result["monthly_savings"] == "7.50"
        assert result["annual_savings"] == "90.00"

    async def test_get_programs_passes_enrollment_filter(self):
        """Verify enrollment_status filter is applied in query."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        service = CommunitySolarService(mock_db)
        await service.get_programs(state="NY", enrollment_status="open")

        # Verify the query was called with enrollment_status param
        call_args = mock_db.execute.call_args
        params = call_args[0][1]  # second positional arg is params dict
        assert params["enrollment_status"] == "open"
