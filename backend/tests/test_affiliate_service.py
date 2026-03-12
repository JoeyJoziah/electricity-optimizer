"""Tests for AffiliateService."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from services.affiliate_service import AffiliateService, AFFILIATE_PARTNERS


def _mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


def _row(data: dict):
    m = MagicMock()
    m.__getitem__ = lambda self, key: data[key]
    m.get = lambda key, default=None: data.get(key, default)
    return m


class TestGenerateAffiliateUrl:
    def test_generates_url_with_utm_params(self):
        db = _mock_db()
        service = AffiliateService(db)
        url = service.generate_affiliate_url(
            supplier_name="Eversource",
            utility_type="electricity",
            region="CT",
            partner="choose_energy",
        )
        assert url is not None
        assert "chooseenergy.com" in url
        assert "utm_source=rateshift" in url
        assert "utm_campaign=electricity_ct" in url
        assert "utm_content=eversource" in url

    def test_returns_none_for_unknown_partner(self):
        db = _mock_db()
        service = AffiliateService(db)
        url = service.generate_affiliate_url(
            supplier_name="Eversource",
            utility_type="electricity",
            region="CT",
            partner="unknown_partner",
        )
        assert url is None

    def test_energysage_partner(self):
        db = _mock_db()
        service = AffiliateService(db)
        url = service.generate_affiliate_url(
            supplier_name="SunPower",
            utility_type="community_solar",
            region="CA",
            partner="energysage",
        )
        assert url is not None
        assert "energysage.com" in url


class TestRecordClick:
    @pytest.mark.asyncio
    async def test_records_click_and_returns_id(self):
        db = _mock_db()
        service = AffiliateService(db)
        click_id = await service.record_click(
            user_id="user-1",
            supplier_id="sup-1",
            supplier_name="Eversource",
            utility_type="electricity",
            region="CT",
            source_page="/rates/connecticut/electricity",
            affiliate_url="https://example.com/aff",
        )
        assert click_id is not None
        assert len(click_id) == 36  # UUID
        db.execute.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_records_click_without_user(self):
        db = _mock_db()
        service = AffiliateService(db)
        click_id = await service.record_click(
            user_id=None,
            supplier_id=None,
            supplier_name="CheapCo",
            utility_type="natural_gas",
            region="TX",
            source_page="/rates/texas/natural-gas",
            affiliate_url="",
        )
        assert click_id is not None
        db.execute.assert_called_once()


class TestMarkConverted:
    @pytest.mark.asyncio
    async def test_marks_as_converted(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.rowcount = 1
        db.execute.return_value = result_mock

        service = AffiliateService(db)
        converted = await service.mark_converted("click-1", commission_cents=500)

        assert converted is True
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_already_converted(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.rowcount = 0
        db.execute.return_value = result_mock

        service = AffiliateService(db)
        converted = await service.mark_converted("click-1", commission_cents=500)

        assert converted is False


class TestGetRevenueSummary:
    @pytest.mark.asyncio
    async def test_returns_summary_by_utility(self):
        db = _mock_db()
        rows = [
            _row({
                "utility_type": "electricity",
                "total_clicks": 100,
                "conversions": 10,
                "total_commission_cents": 5000,
            }),
            _row({
                "utility_type": "natural_gas",
                "total_clicks": 50,
                "conversions": 3,
                "total_commission_cents": 1500,
            }),
        ]
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = rows
        db.execute.return_value = result_mock

        service = AffiliateService(db)
        summary = await service.get_revenue_summary(days=30)

        assert summary["period_days"] == 30
        assert summary["total_clicks"] == 150
        assert summary["total_conversions"] == 13
        assert summary["total_revenue_cents"] == 6500
        assert len(summary["by_utility"]) == 2
        assert summary["by_utility"][0]["conversion_rate"] == 10.0

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_clicks(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.mappings.return_value.all.return_value = []
        db.execute.return_value = result_mock

        service = AffiliateService(db)
        summary = await service.get_revenue_summary(days=7)

        assert summary["total_clicks"] == 0
        assert summary["total_conversions"] == 0
        assert summary["total_revenue_cents"] == 0


class TestAffiliatePartners:
    def test_all_partners_have_required_fields(self):
        for name, config in AFFILIATE_PARTNERS.items():
            assert "base_url" in config, f"{name} missing base_url"
            assert "utm_source" in config, f"{name} missing utm_source"
            assert config["utm_source"] == "rateshift"
