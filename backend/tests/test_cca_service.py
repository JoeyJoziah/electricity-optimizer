"""
Tests for CCA (Community Choice Aggregation) Service

Verifies detection by zip code and municipality, rate comparison,
opt-out info retrieval, program listing, and state checks.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from models.region import CCA_STATES
from services.cca_service import CCAService

CCA_ROW = {
    "id": uuid4(),
    "state": "CA",
    "municipality": "San Jose",
    "zip_codes": ["95101", "95102", "95103"],
    "program_name": "San Jose Clean Energy",
    "provider": "City of San Jose",
    "generation_mix": {"solar": 40, "wind": 30, "hydro": 20, "other": 10},
    "rate_vs_default_pct": -5.00,
    "opt_out_url": "https://sanjosecleanenergy.org/opt-out",
    "program_url": "https://sanjosecleanenergy.org",
    "status": "active",
}


def _mock_db_with_row(row):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = row
    mock_result.mappings.return_value.all.return_value = [row] if row else []
    mock_db.execute.return_value = mock_result
    return mock_db


def _mock_db_empty():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = None
    mock_result.mappings.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result
    return mock_db


class TestDetectCCA:
    """Test CCA detection by zip code and municipality."""

    async def test_detect_by_zip_code(self):
        mock_db = _mock_db_with_row(CCA_ROW)
        service = CCAService(mock_db)
        result = await service.detect_cca(zip_code="95101")

        assert result is not None
        assert result["program_name"] == "San Jose Clean Energy"
        assert result["state"] == "CA"

    async def test_detect_by_municipality(self):
        # First call (zip) returns None, second call (municipality) returns row
        mock_db = AsyncMock()
        mock_empty = MagicMock()
        mock_empty.mappings.return_value.first.return_value = None
        mock_found = MagicMock()
        mock_found.mappings.return_value.first.return_value = CCA_ROW
        mock_db.execute.side_effect = [mock_empty, mock_found]

        service = CCAService(mock_db)
        result = await service.detect_cca(
            zip_code="00000",
            state="CA",
            municipality="San Jose",
        )

        assert result is not None
        assert result["municipality"] == "San Jose"

    async def test_detect_not_found(self):
        mock_db = _mock_db_empty()
        service = CCAService(mock_db)
        result = await service.detect_cca(zip_code="99999")

        assert result is None

    async def test_detect_by_state_municipality_only(self):
        mock_db = _mock_db_with_row(CCA_ROW)
        service = CCAService(mock_db)
        result = await service.detect_cca(state="CA", municipality="San Jose")

        assert result is not None
        assert result["provider"] == "City of San Jose"


class TestCompareCCARate:
    """Test CCA rate comparison."""

    async def test_cheaper_cca(self):
        mock_db = _mock_db_with_row(CCA_ROW)
        service = CCAService(mock_db)
        result = await service.compare_cca_rate(
            cca_id=str(CCA_ROW["id"]),
            default_rate=0.20,
        )

        assert result["is_cheaper"] is True
        assert result["rate_difference_pct"] == -5.0
        assert result["cca_rate"] == 0.19  # 0.20 * 0.95
        assert result["savings_per_kwh"] == 0.01
        assert result["estimated_monthly_savings"] == 9.0  # 0.01 * 900

    async def test_not_found(self):
        mock_db = _mock_db_empty()
        service = CCAService(mock_db)
        result = await service.compare_cca_rate(
            cca_id=str(uuid4()),
            default_rate=0.20,
        )

        assert "error" in result

    async def test_more_expensive_cca(self):
        expensive_row = dict(CCA_ROW, rate_vs_default_pct=3.00)
        mock_db = _mock_db_with_row(expensive_row)
        service = CCAService(mock_db)
        result = await service.compare_cca_rate(
            cca_id=str(CCA_ROW["id"]),
            default_rate=0.20,
        )

        assert result["is_cheaper"] is False
        assert result["cca_rate"] == 0.206  # 0.20 * 1.03


class TestGetCCAInfo:
    """Test CCA info retrieval."""

    async def test_returns_full_info(self):
        mock_db = _mock_db_with_row(CCA_ROW)
        service = CCAService(mock_db)
        info = await service.get_cca_info(str(CCA_ROW["id"]))

        assert info is not None
        assert info["program_name"] == "San Jose Clean Energy"
        assert info["opt_out_url"] == "https://sanjosecleanenergy.org/opt-out"
        assert info["generation_mix"]["solar"] == 40
        assert "zip_codes" in info

    async def test_not_found(self):
        mock_db = _mock_db_empty()
        service = CCAService(mock_db)
        info = await service.get_cca_info(str(uuid4()))

        assert info is None


class TestListPrograms:
    """Test listing CCA programs."""

    async def test_list_all(self):
        mock_db = _mock_db_with_row(CCA_ROW)
        service = CCAService(mock_db)
        programs = await service.list_cca_programs()

        assert len(programs) == 1
        assert programs[0]["state"] == "CA"

    async def test_list_by_state(self):
        mock_db = _mock_db_with_row(CCA_ROW)
        service = CCAService(mock_db)
        programs = await service.list_cca_programs(state="CA")

        assert len(programs) == 1

    async def test_list_empty(self):
        mock_db = _mock_db_empty()
        service = CCAService(mock_db)
        programs = await service.list_cca_programs(state="ZZ")

        assert programs == []


class TestIsCCAState:
    """Test static CCA state check."""

    def test_ca_is_cca_state(self):
        assert CCAService.is_cca_state("CA") is True

    def test_ma_is_cca_state(self):
        assert CCAService.is_cca_state("MA") is True

    def test_al_not_cca_state(self):
        assert CCAService.is_cca_state("AL") is False

    def test_case_insensitive(self):
        assert CCAService.is_cca_state("ca") is True

    def test_all_ten_states(self):
        expected = {"CA", "MA", "NY", "NJ", "IL", "OH", "NH", "VA", "RI", "CO"}
        assert expected == CCA_STATES
