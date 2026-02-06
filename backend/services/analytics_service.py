"""
Analytics Service

Business logic for price analytics and aggregation.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, Any, List
from statistics import stdev

from repositories.price_repository import PriceRepository
from models.price import PriceRegion


class AnalyticsService:
    """
    Service for price analytics and trend analysis.

    Provides aggregation, statistical analysis, and
    trend detection for electricity prices.
    """

    def __init__(self, price_repo: PriceRepository):
        """
        Initialize the analytics service.

        Args:
            price_repo: Price repository instance
        """
        self._repo = price_repo

    async def calculate_average_price(
        self,
        region: PriceRegion,
        days: int = 7
    ) -> Decimal:
        """
        Calculate average price for a region over a period.

        Args:
            region: Price region
            days: Number of days to analyze

        Returns:
            Average price per kWh
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        prices = await self._repo.get_historical_prices(
            region=region,
            start_date=start,
            end_date=end
        )

        if not prices:
            return Decimal("0")

        total = sum(p.price_per_kwh for p in prices)
        return (total / len(prices)).quantize(Decimal("0.0001"))

    async def calculate_volatility(
        self,
        region: PriceRegion,
        days: int = 7
    ) -> Decimal:
        """
        Calculate price volatility (standard deviation) for a region.

        Args:
            region: Price region
            days: Number of days to analyze

        Returns:
            Price volatility as standard deviation
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        prices = await self._repo.get_historical_prices(
            region=region,
            start_date=start,
            end_date=end
        )

        if len(prices) < 2:
            return Decimal("0")

        # Calculate standard deviation
        price_values = [float(p.price_per_kwh) for p in prices]
        try:
            volatility = stdev(price_values)
            return Decimal(str(volatility)).quantize(Decimal("0.0001"))
        except Exception:
            return Decimal("0")

    async def get_price_trend(
        self,
        region: PriceRegion,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Analyze price trend over a period.

        Args:
            region: Price region
            days: Number of days to analyze

        Returns:
            Trend analysis with direction and change percentage
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        prices = await self._repo.get_historical_prices(
            region=region,
            start_date=start,
            end_date=end
        )

        if len(prices) < 2:
            return {
                'direction': 'stable',
                'change_percent': Decimal("0"),
                'start_price': Decimal("0"),
                'end_price': Decimal("0"),
                'data_points': 0
            }

        # Sort by timestamp
        prices = sorted(prices, key=lambda p: p.timestamp)

        # Calculate first and last third averages for more stable comparison
        third = len(prices) // 3
        if third < 1:
            third = 1

        first_third_avg = sum(p.price_per_kwh for p in prices[:third]) / third
        last_third_avg = sum(p.price_per_kwh for p in prices[-third:]) / third

        # Calculate change
        if first_third_avg > 0:
            change_percent = ((last_third_avg - first_third_avg) / first_third_avg) * Decimal("100")
        else:
            change_percent = Decimal("0")

        # Determine direction
        if change_percent > Decimal("5"):
            direction = "increasing"
        elif change_percent < Decimal("-5"):
            direction = "decreasing"
        else:
            direction = "stable"

        return {
            'direction': direction,
            'change_percent': change_percent.quantize(Decimal("0.01")),
            'start_price': first_third_avg.quantize(Decimal("0.0001")),
            'end_price': last_third_avg.quantize(Decimal("0.0001")),
            'data_points': len(prices)
        }

    async def get_peak_hours_analysis(
        self,
        region: PriceRegion,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Analyze peak and off-peak hours based on pricing.

        Args:
            region: Price region
            days: Number of days to analyze

        Returns:
            Analysis with peak and off-peak hour identification
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        prices = await self._repo.get_historical_prices(
            region=region,
            start_date=start,
            end_date=end
        )

        if not prices:
            return {
                'peak_hours': [],
                'off_peak_hours': [],
                'average_by_hour': {}
            }

        # Group prices by hour
        hourly_prices: Dict[int, List[Decimal]] = {h: [] for h in range(24)}

        for price in prices:
            hour = price.timestamp.hour
            hourly_prices[hour].append(price.price_per_kwh)

        # Calculate average for each hour
        hourly_avg = {}
        for hour, hour_prices in hourly_prices.items():
            if hour_prices:
                hourly_avg[hour] = (sum(hour_prices) / len(hour_prices)).quantize(Decimal("0.0001"))
            else:
                hourly_avg[hour] = Decimal("0")

        # Calculate overall average
        all_prices = [p.price_per_kwh for p in prices]
        overall_avg = sum(all_prices) / len(all_prices)

        # Identify peak and off-peak hours
        peak_hours = []
        off_peak_hours = []

        for hour, avg in hourly_avg.items():
            if avg > overall_avg * Decimal("1.1"):  # 10% above average
                peak_hours.append(hour)
            elif avg < overall_avg * Decimal("0.9"):  # 10% below average
                off_peak_hours.append(hour)

        return {
            'peak_hours': sorted(peak_hours),
            'off_peak_hours': sorted(off_peak_hours),
            'average_by_hour': hourly_avg,
            'overall_average': overall_avg.quantize(Decimal("0.0001")),
            'peak_premium_percent': (
                (max(hourly_avg.values()) / overall_avg - 1) * 100
            ).quantize(Decimal("0.1")) if overall_avg > 0 else Decimal("0")
        }

    async def get_supplier_comparison_analytics(
        self,
        region: PriceRegion,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get detailed supplier comparison analytics.

        Args:
            region: Price region
            days: Number of days to analyze

        Returns:
            Comparison analytics by supplier
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        prices = await self._repo.get_historical_prices(
            region=region,
            start_date=start,
            end_date=end
        )

        if not prices:
            return {'suppliers': []}

        # Group by supplier
        supplier_prices: Dict[str, List[Decimal]] = {}

        for price in prices:
            if price.supplier not in supplier_prices:
                supplier_prices[price.supplier] = []
            supplier_prices[price.supplier].append(price.price_per_kwh)

        # Calculate statistics for each supplier
        supplier_stats = []

        for supplier, sp_prices in supplier_prices.items():
            avg = sum(sp_prices) / len(sp_prices)
            min_price = min(sp_prices)
            max_price = max(sp_prices)

            try:
                volatility = Decimal(str(stdev([float(p) for p in sp_prices])))
            except Exception:
                volatility = Decimal("0")

            supplier_stats.append({
                'supplier': supplier,
                'average_price': avg.quantize(Decimal("0.0001")),
                'min_price': min_price.quantize(Decimal("0.0001")),
                'max_price': max_price.quantize(Decimal("0.0001")),
                'volatility': volatility.quantize(Decimal("0.0001")),
                'data_points': len(sp_prices)
            })

        # Sort by average price
        supplier_stats.sort(key=lambda s: s['average_price'])

        return {
            'region': region.value,
            'period_days': days,
            'suppliers': supplier_stats,
            'cheapest_supplier': supplier_stats[0]['supplier'] if supplier_stats else None,
            'most_stable': min(supplier_stats, key=lambda s: s['volatility'])['supplier'] if supplier_stats else None
        }
