"""
Tests for RecommendationService (backend/services/recommendation_service.py).

Focuses on the pure computation helpers (_compute_switching, _compute_usage,
_get_appliance_consumption, _adjust_confidence_from_patterns) since these
carry the business logic and can be exercised without async DB calls.
Also covers the async entry-points (get_switching_recommendation,
get_usage_recommendation, get_daily_recommendations).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.recommendation_service import RecommendationService, SwitchingRecommendation

# =============================================================================
# Helpers
# =============================================================================


def _make_price(supplier: str, price: str, green_pct: int = 0) -> MagicMock:
    p = MagicMock()
    p.supplier = supplier
    p.price_per_kwh = Decimal(price)
    p.green_energy_percentage = green_pct
    return p


def _make_user(region: str = "us_ct", supplier: str = "SupplierA", preferences=None) -> MagicMock:
    u = MagicMock()
    u.region = region
    u.current_supplier = supplier
    u.preferences = preferences or {}
    return u


def _make_services(user=None, prices=None, windows=None):
    """Return (svc, price_service_mock, user_repo_mock)."""
    price_svc = AsyncMock()
    price_svc.get_price_comparison = AsyncMock(return_value=prices or [])
    price_svc.get_optimal_usage_windows = AsyncMock(return_value=windows or [])
    price_svc.get_current_prices = AsyncMock(return_value=prices or [])

    user_repo = AsyncMock()
    user_repo.get_by_id = AsyncMock(return_value=user)

    svc = RecommendationService(price_svc, user_repo)
    return svc, price_svc, user_repo


def _window(avg_price: str = "0.10") -> dict:
    return {
        "start": datetime(2026, 5, 12, 2, 0, tzinfo=UTC),
        "end": datetime(2026, 5, 12, 4, 0, tzinfo=UTC),
        "avg_price": Decimal(avg_price),
    }


# =============================================================================
# _get_appliance_consumption
# =============================================================================


class TestGetApplianceConsumption:
    def test_known_appliance_electric_vehicle(self):
        svc, _, _ = _make_services()
        result = svc._get_appliance_consumption("electric_vehicle", 2)
        assert result == Decimal("14.0")  # 7.0 kW × 2h

    def test_known_appliance_dryer(self):
        svc, _, _ = _make_services()
        result = svc._get_appliance_consumption("dryer", 1)
        assert result == Decimal("3.0")

    def test_unknown_appliance_falls_back_to_default(self):
        svc, _, _ = _make_services()
        result = svc._get_appliance_consumption("toaster_oven", 3)
        assert result == Decimal("3.0")  # default 1.0 kW × 3h

    def test_case_insensitive_lookup(self):
        svc, _, _ = _make_services()
        result = svc._get_appliance_consumption("DISHWASHER", 2)
        assert result == Decimal("3.6")  # 1.8 kW × 2h


# =============================================================================
# _compute_switching (pure computation)
# =============================================================================


class TestComputeSwitching:
    def test_returns_none_when_no_prices(self):
        svc, _, _ = _make_services()
        user = _make_user()
        result = svc._compute_switching("u1", user, [])
        assert result is None

    def test_recommends_cheapest_supplier(self):
        svc, _, _ = _make_services()
        user = _make_user(supplier="SupplierA")
        prices = [
            _make_price("CheapSupplier", "0.10"),
            _make_price("SupplierA", "0.15"),
        ]
        result = svc._compute_switching("u1", user, prices)
        assert result is not None
        assert result.recommended_supplier == "CheapSupplier"
        assert result.current_price == Decimal("0.15")
        assert result.recommended_price == Decimal("0.10")

    def test_potential_savings_computed_correctly(self):
        svc, _, _ = _make_services()
        user = _make_user(supplier="ExpensiveSupplier")
        prices = [
            _make_price("CheapSupplier", "0.08"),
            _make_price("ExpensiveSupplier", "0.20"),
        ]
        result = svc._compute_switching("u1", user, prices)
        assert result.potential_savings == Decimal("0.12")

    def test_falls_back_to_last_price_when_supplier_not_found(self):
        """When the user's current_supplier is not in prices, use the last price."""
        svc, _, _ = _make_services()
        user = _make_user(supplier="Unknown")
        prices = [
            _make_price("Best", "0.08"),
            _make_price("Worst", "0.25"),
        ]
        result = svc._compute_switching("u1", user, prices)
        assert result.current_price == Decimal("0.25")

    def test_high_savings_yields_high_confidence(self):
        svc, _, _ = _make_services()
        user = _make_user(supplier="SupplierA")
        prices = [
            _make_price("Cheap", "0.05"),
            _make_price("SupplierA", "0.20"),
        ]
        result = svc._compute_switching("u1", user, prices)
        assert result.confidence >= 0.85

    def test_low_savings_yields_lower_confidence(self):
        svc, _, _ = _make_services()
        user = _make_user(supplier="SupplierA")
        prices = [
            _make_price("SlightlyCheap", "0.149"),
            _make_price("SupplierA", "0.150"),
        ]
        result = svc._compute_switching("u1", user, prices)
        assert result.confidence < 0.85

    def test_green_only_preference_filters_to_green_suppliers(self):
        svc, _, _ = _make_services()
        user = _make_user(supplier="DirtySupplier", preferences={"green_energy_only": True})
        prices = [
            _make_price("CheapDirty", "0.05", green_pct=0),
            _make_price("GreenExpensive", "0.12", green_pct=80),
            _make_price("DirtySupplier", "0.15", green_pct=10),
        ]
        result = svc._compute_switching("u1", user, prices)
        assert result.recommended_supplier == "GreenExpensive"

    def test_green_only_falls_back_to_cheapest_when_no_green_available(self):
        svc, _, _ = _make_services()
        user = _make_user(supplier="DirtySupplier", preferences={"green_energy_only": True})
        prices = [
            _make_price("CheapDirty", "0.05", green_pct=10),
            _make_price("DirtySupplier", "0.15", green_pct=10),
        ]
        result = svc._compute_switching("u1", user, prices)
        # No green suppliers → falls back to cheapest overall
        assert result.recommended_supplier == "CheapDirty"

    def test_significant_savings_reason_added(self):
        svc, _, _ = _make_services()
        user = _make_user(supplier="SupplierA")
        prices = [
            _make_price("Cheap", "0.05"),
            _make_price("SupplierA", "0.20"),
        ]
        result = svc._compute_switching("u1", user, prices)
        assert any("Significant price difference" in r for r in result.reasons)

    def test_result_is_switching_recommendation_dataclass(self):
        svc, _, _ = _make_services()
        user = _make_user(supplier="SupplierA")
        prices = [_make_price("SupplierA", "0.12")]
        result = svc._compute_switching("u1", user, prices)
        assert isinstance(result, SwitchingRecommendation)


# =============================================================================
# _compute_usage (pure computation)
# =============================================================================


class TestComputeUsage:
    def test_returns_none_when_no_windows(self):
        svc, _, _ = _make_services()
        result = svc._compute_usage("u1", "dryer", 2, [], [], Decimal("0.15"))
        assert result is None

    def test_computes_estimated_cost_from_window_price(self):
        svc, _, _ = _make_services()
        result = svc._compute_usage("u1", "dryer", 1, [_window("0.10")], [], Decimal("0.20"))
        # dryer = 3.0 kW, 1h = 3.0 kWh × 0.10 = $0.30
        assert result["estimated_cost"] == Decimal("0.30")

    def test_cost_vs_peak_computed_correctly(self):
        svc, _, _ = _make_services()
        result = svc._compute_usage("u1", "dryer", 1, [_window("0.10")], [], Decimal("0.20"))
        # cost_at_peak = 3.0 × 0.20 = 0.60; estimated = 0.30; diff = 0.30
        assert result["cost_vs_peak"] == Decimal("0.30")

    def test_off_peak_reason_added_when_price_below_70_pct_peak(self):
        svc, _, _ = _make_services()
        # 0.05 < 0.20 * 0.7 = 0.14 → off-peak reason
        result = svc._compute_usage("u1", "dryer", 1, [_window("0.05")], [], Decimal("0.20"))
        assert any("off-peak" in r.lower() for r in result["reasons"])

    def test_off_peak_reason_not_added_when_price_above_70_pct_peak(self):
        svc, _, _ = _make_services()
        # 0.15 > 0.20 * 0.7 = 0.14 → no off-peak reason
        result = svc._compute_usage("u1", "dryer", 1, [_window("0.15")], [], Decimal("0.20"))
        assert not any("off-peak" in r.lower() for r in result["reasons"])

    def test_result_contains_expected_keys(self):
        svc, _, _ = _make_services()
        result = svc._compute_usage("u1", "dishwasher", 2, [_window("0.08")], [], Decimal("0.15"))
        for key in (
            "user_id",
            "appliance",
            "optimal_start_time",
            "optimal_end_time",
            "estimated_cost",
            "cost_vs_peak",
            "reasons",
            "generated_at",
        ):
            assert key in result, f"Missing key: {key}"


# =============================================================================
# _adjust_confidence_from_patterns
# =============================================================================


class TestAdjustConfidenceFromPatterns:
    def test_returns_unchanged_when_no_vector_store(self):
        svc, _, _ = _make_services()
        prices = [_make_price("A", "0.10")]
        result = svc._adjust_confidence_from_patterns(prices, 0.75)
        assert result == 0.75

    def test_returns_unchanged_when_no_prices(self):
        vector_store = MagicMock()
        price_svc = AsyncMock()
        user_repo = AsyncMock()
        svc = RecommendationService(price_svc, user_repo, vector_store)
        result = svc._adjust_confidence_from_patterns([], 0.75)
        assert result == 0.75

    def test_skips_when_index_is_sparse(self):
        vector_store = MagicMock()
        vector_store.get_stats.return_value = {"total_vectors": 5}
        price_svc = AsyncMock()
        user_repo = AsyncMock()
        svc = RecommendationService(price_svc, user_repo, vector_store)
        prices = [_make_price("A", "0.10")]
        result = svc._adjust_confidence_from_patterns(prices, 0.80)
        # Sparse index → skip, return original confidence unchanged
        assert result == 0.80

    def test_increases_confidence_on_high_similarity_high_confidence_match(self):
        vector_store = MagicMock()
        vector_store.get_stats.return_value = {"total_vectors": 20}
        vector_store.search.return_value = [{"similarity": 0.95, "confidence": 0.9}]

        price_svc = AsyncMock()
        user_repo = AsyncMock()
        svc = RecommendationService(price_svc, user_repo, vector_store)
        prices = [_make_price("A", "0.10")] * 5

        with patch("services.vector_store.price_curve_to_vector", return_value=[0.1]):
            result = svc._adjust_confidence_from_patterns(prices, 0.80)

        assert result > 0.80

    def test_decreases_confidence_on_high_similarity_low_confidence_match(self):
        vector_store = MagicMock()
        vector_store.get_stats.return_value = {"total_vectors": 20}
        vector_store.search.return_value = [{"similarity": 0.95, "confidence": 0.3}]

        price_svc = AsyncMock()
        user_repo = AsyncMock()
        svc = RecommendationService(price_svc, user_repo, vector_store)
        prices = [_make_price("A", "0.10")] * 5

        with patch("services.vector_store.price_curve_to_vector", return_value=[0.1]):
            result = svc._adjust_confidence_from_patterns(prices, 0.80)

        assert result < 0.80

    def test_returns_unchanged_on_exception(self):
        vector_store = MagicMock()
        vector_store.get_stats.side_effect = RuntimeError("index error")
        price_svc = AsyncMock()
        user_repo = AsyncMock()
        svc = RecommendationService(price_svc, user_repo, vector_store)
        prices = [_make_price("A", "0.10")]
        result = svc._adjust_confidence_from_patterns(prices, 0.70)
        assert result == 0.70


# =============================================================================
# Async entry-points
# =============================================================================


class TestGetSwitchingRecommendation:
    @pytest.mark.asyncio
    async def test_returns_none_when_user_not_found(self):
        svc, _, _ = _make_services(user=None)
        result = await svc.get_switching_recommendation("unknown-user")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_recommendation_for_known_user(self):
        user = _make_user(supplier="SupplierA")
        prices = [
            _make_price("Cheap", "0.08"),
            _make_price("SupplierA", "0.15"),
        ]
        svc, _, _ = _make_services(user=user, prices=prices)
        result = await svc.get_switching_recommendation("u1")
        assert isinstance(result, SwitchingRecommendation)
        assert result.recommended_supplier == "Cheap"


class TestGetDailyRecommendations:
    @pytest.mark.asyncio
    async def test_returns_null_recommendation_when_user_not_found(self):
        svc, _, _ = _make_services(user=None)
        result = await svc.get_daily_recommendations("no-such-user")
        assert result["switching_recommendation"] is None
        assert result["usage_recommendations"] == []

    @pytest.mark.asyncio
    async def test_returns_dict_with_expected_keys(self):
        user = _make_user(supplier="SupplierA")
        prices = [_make_price("Cheap", "0.08"), _make_price("SupplierA", "0.15")]
        windows = [_window("0.08")]
        svc, _, _ = _make_services(user=user, prices=prices, windows=windows)
        result = await svc.get_daily_recommendations("u1")
        for key in ("user_id", "generated_at", "switching_recommendation", "usage_recommendations"):
            assert key in result

    @pytest.mark.asyncio
    async def test_usage_recommendations_populated_when_windows_available(self):
        user = _make_user(supplier="SupplierA")
        prices = [_make_price("Cheap", "0.08"), _make_price("SupplierA", "0.15")]
        windows = [_window("0.08")]
        svc, _, _ = _make_services(user=user, prices=prices, windows=windows)
        result = await svc.get_daily_recommendations("u1")
        assert len(result["usage_recommendations"]) > 0

    @pytest.mark.asyncio
    async def test_only_three_db_calls_made(self):
        user = _make_user(supplier="SupplierA")
        prices = [_make_price("Cheap", "0.08"), _make_price("SupplierA", "0.15")]
        svc, price_svc, user_repo = _make_services(user=user, prices=prices)
        await svc.get_daily_recommendations("u1")
        # user_repo: 1 call; price_svc: get_price_comparison + get_optimal_usage_windows = 2
        assert user_repo.get_by_id.await_count == 1
        assert price_svc.get_price_comparison.await_count == 1
        assert price_svc.get_optimal_usage_windows.await_count == 1
