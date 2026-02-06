"""
Recommendation Service

Business logic for generating user recommendations.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any
from dataclasses import dataclass

from services.price_service import PriceService
from repositories.user_repository import UserRepository
from models.price import PriceRegion


@dataclass
class SwitchingRecommendation:
    """Recommendation for switching suppliers"""
    user_id: str
    current_supplier: str
    recommended_supplier: str
    current_price: Decimal
    recommended_price: Decimal
    potential_savings: Decimal
    savings_percentage: Decimal
    confidence: float
    reasons: list
    generated_at: datetime


@dataclass
class UsageRecommendation:
    """Recommendation for usage timing"""
    user_id: str
    appliance: str
    optimal_start_time: datetime
    optimal_end_time: datetime
    estimated_cost: Decimal
    cost_vs_peak: Decimal
    reasons: list
    generated_at: datetime


class RecommendationService:
    """
    Service for generating personalized recommendations.

    Analyzes user data and market prices to provide
    actionable recommendations for cost savings.
    """

    def __init__(
        self,
        price_service: PriceService,
        user_repo: UserRepository
    ):
        """
        Initialize the recommendation service.

        Args:
            price_service: Price service instance
            user_repo: User repository instance
        """
        self._price_service = price_service
        self._user_repo = user_repo

    async def get_switching_recommendation(
        self,
        user_id: str
    ) -> Optional[SwitchingRecommendation]:
        """
        Generate supplier switching recommendation for a user.

        Args:
            user_id: User ID

        Returns:
            Switching recommendation if available
        """
        # Get user info
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            return None

        region = PriceRegion(user.region)
        current_supplier = user.current_supplier

        # Get price comparison
        prices = await self._price_service.get_price_comparison(region)
        if not prices:
            return None

        # Find current supplier price
        current_price = None
        for p in prices:
            if p.supplier == current_supplier:
                current_price = p.price_per_kwh
                break

        if current_price is None:
            # User not on any tracked supplier, use highest as baseline
            current_price = prices[-1].price_per_kwh

        # Get cheapest supplier
        cheapest = prices[0]

        # Check user preferences
        preferences = user.preferences or {}
        green_only = preferences.get("green_energy_only", False)

        if green_only:
            # Filter for green suppliers (this would need actual data)
            green_prices = [p for p in prices if getattr(p, "green_energy_percentage", 0) >= 50]
            if green_prices:
                cheapest = green_prices[0]

        # Calculate savings
        potential_savings = current_price - cheapest.price_per_kwh
        if current_price > 0:
            savings_percentage = (potential_savings / current_price) * Decimal("100")
        else:
            savings_percentage = Decimal("0")

        # Generate reasons
        reasons = []
        if potential_savings > Decimal("0.05"):
            reasons.append(f"Save up to {savings_percentage:.1f}% on electricity costs")
        if green_only:
            reasons.append("Recommended supplier meets your green energy preference")
        if cheapest.price_per_kwh < current_price * Decimal("0.8"):
            reasons.append("Significant price difference detected")

        return SwitchingRecommendation(
            user_id=user_id,
            current_supplier=current_supplier or "Unknown",
            recommended_supplier=cheapest.supplier,
            current_price=current_price,
            recommended_price=cheapest.price_per_kwh,
            potential_savings=potential_savings,
            savings_percentage=savings_percentage,
            confidence=0.85 if potential_savings > Decimal("0.02") else 0.6,
            reasons=reasons,
            generated_at=datetime.now(timezone.utc)
        )

    async def get_usage_recommendation(
        self,
        user_id: str,
        appliance: str,
        duration_hours: int
    ) -> Optional[Dict[str, Any]]:
        """
        Generate usage timing recommendation for an appliance.

        Args:
            user_id: User ID
            appliance: Appliance type
            duration_hours: Required usage duration

        Returns:
            Usage recommendation if available
        """
        # Get user info
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            return None

        region = PriceRegion(user.region)

        # Get optimal windows
        windows = await self._price_service.get_optimal_usage_windows(
            region=region,
            duration_hours=duration_hours,
            within_hours=24
        )

        if not windows:
            return None

        best_window = windows[0]

        # Estimate cost (simplified - would use appliance power ratings)
        appliance_kwh = self._get_appliance_consumption(appliance, duration_hours)
        estimated_cost = appliance_kwh * best_window['avg_price']

        # Get peak price for comparison
        prices = await self._price_service.get_current_prices(region)
        peak_price = max(p.price_per_kwh for p in prices) if prices else best_window['avg_price']
        cost_at_peak = appliance_kwh * peak_price

        reasons = []
        if best_window['avg_price'] < peak_price * Decimal("0.7"):
            reasons.append("Running during off-peak hours saves significantly")
        reasons.append(f"Optimal window has average price of {best_window['avg_price']:.4f}/kWh")

        return {
            'user_id': user_id,
            'appliance': appliance,
            'optimal_start_time': best_window['start'],
            'optimal_end_time': best_window['end'],
            'estimated_cost': estimated_cost.quantize(Decimal("0.01")),
            'cost_vs_peak': (cost_at_peak - estimated_cost).quantize(Decimal("0.01")),
            'reasons': reasons,
            'generated_at': datetime.now(timezone.utc)
        }

    def _get_appliance_consumption(self, appliance: str, hours: int) -> Decimal:
        """
        Get estimated kWh consumption for an appliance.

        Args:
            appliance: Appliance type
            hours: Usage duration

        Returns:
            Estimated kWh consumption
        """
        # Simplified appliance consumption rates (kW)
        consumption_rates = {
            "washing_machine": Decimal("0.5"),
            "dishwasher": Decimal("1.8"),
            "dryer": Decimal("3.0"),
            "electric_vehicle": Decimal("7.0"),
            "pool_pump": Decimal("1.5"),
            "air_conditioner": Decimal("3.5"),
            "heater": Decimal("2.0"),
            "default": Decimal("1.0")
        }

        rate = consumption_rates.get(appliance.lower(), consumption_rates["default"])
        return rate * Decimal(str(hours))

    async def get_daily_recommendations(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Generate all daily recommendations for a user.

        Args:
            user_id: User ID

        Returns:
            Dictionary with all recommendations
        """
        switching = await self.get_switching_recommendation(user_id)

        # Get usage recommendations for common appliances
        appliances = ["washing_machine", "dishwasher", "electric_vehicle"]
        usage_recommendations = []

        for appliance in appliances:
            rec = await self.get_usage_recommendation(
                user_id,
                appliance,
                duration_hours=2
            )
            if rec:
                usage_recommendations.append(rec)

        return {
            'user_id': user_id,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'switching_recommendation': switching.__dict__ if switching else None,
            'usage_recommendations': usage_recommendations
        }
