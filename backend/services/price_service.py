"""
Price Service

Business logic for electricity price operations.
"""

from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from typing import Optional, List, Dict, Any

from models.price import Price, PriceRegion, PriceForecast
from repositories.price_repository import PriceRepository


class PriceService:
    """
    Service layer for price-related operations.

    Contains business logic for fetching, comparing, and
    analyzing electricity prices.
    """

    def __init__(self, price_repo: PriceRepository, cache: Any = None):
        """
        Initialize the price service.

        Args:
            price_repo: Price repository instance
            cache: Optional cache client
        """
        self._repo = price_repo
        self._cache = cache

    async def get_current_price(
        self,
        region: PriceRegion,
        supplier: str
    ) -> Optional[Price]:
        """
        Get the current price for a specific supplier in a region.

        Args:
            region: Price region
            supplier: Supplier name

        Returns:
            Current price if available
        """
        return await self._repo.get_latest_by_supplier(region, supplier)

    async def get_current_prices(
        self,
        region: PriceRegion,
        limit: int = 10
    ) -> List[Price]:
        """
        Get current prices for all suppliers in a region.

        Args:
            region: Price region
            limit: Maximum number of results

        Returns:
            List of current prices
        """
        return await self._repo.get_current_prices(region, limit)

    async def get_cheapest_supplier(
        self,
        region: PriceRegion
    ) -> Optional[Price]:
        """
        Find the cheapest supplier in a region.

        Args:
            region: Price region

        Returns:
            Price from cheapest supplier if available
        """
        prices = await self._repo.get_current_prices(region, limit=50)
        if not prices:
            return None

        # Find minimum price
        return min(prices, key=lambda p: p.price_per_kwh)

    async def get_price_comparison(
        self,
        region: PriceRegion
    ) -> List[Price]:
        """
        Get price comparison across suppliers, sorted by price.

        Args:
            region: Price region

        Returns:
            List of prices sorted by price_per_kwh ascending
        """
        prices = await self._repo.get_current_prices(region, limit=50)
        return sorted(prices, key=lambda p: p.price_per_kwh)

    async def calculate_daily_cost(
        self,
        region: PriceRegion,
        supplier: str,
        kwh_usage: Decimal,
        target_date: date
    ) -> Decimal:
        """
        Calculate daily cost based on actual prices.

        Args:
            region: Price region
            supplier: Supplier name
            kwh_usage: Daily kWh consumption
            target_date: Date to calculate for

        Returns:
            Calculated daily cost
        """
        # Get prices for the date
        start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        prices = await self._repo.get_historical_prices(
            region=region,
            start_date=start,
            end_date=end,
            supplier=supplier
        )

        if not prices:
            # Fall back to current price
            current = await self.get_current_price(region, supplier)
            if current:
                return kwh_usage * current.price_per_kwh
            return Decimal("0")

        # Calculate weighted average price
        total_price = sum(p.price_per_kwh for p in prices)
        avg_price = total_price / len(prices)

        return (kwh_usage * avg_price).quantize(Decimal("0.01"))

    async def get_price_forecast(
        self,
        region: PriceRegion,
        hours: int = 24,
        supplier: Optional[str] = None
    ) -> Optional[PriceForecast]:
        """
        Get price forecast for upcoming hours.

        This is a placeholder that would integrate with ML predictions.

        Args:
            region: Price region
            hours: Forecast horizon in hours
            supplier: Optional supplier filter

        Returns:
            Price forecast if available
        """
        # In a real implementation, this would call the ML service
        # For now, return a simple forecast based on historical patterns

        current_prices = await self._repo.get_current_prices(region, limit=1)
        if not current_prices:
            return None

        base_price = current_prices[0].price_per_kwh
        now = datetime.now(timezone.utc)

        # Generate simple forecast
        forecast_prices = []
        for i in range(hours):
            hour = (now + timedelta(hours=i)).hour

            # Simple peak/off-peak adjustment
            if 16 <= hour <= 20:
                # Peak hours: higher prices
                price = base_price * Decimal("1.3")
            elif 0 <= hour <= 6:
                # Night: lower prices
                price = base_price * Decimal("0.7")
            else:
                price = base_price

            forecast_prices.append(
                Price(
                    region=region,
                    supplier=supplier or current_prices[0].supplier,
                    price_per_kwh=price.quantize(Decimal("0.0001")),
                    timestamp=now + timedelta(hours=i),
                    currency=current_prices[0].currency,
                    is_peak=16 <= hour <= 20
                )
            )

        return PriceForecast(
            region=region,
            generated_at=now,
            horizon_hours=hours,
            prices=forecast_prices,
            confidence=0.7,  # Lower confidence for simple forecast
            model_version="simple_v1"
        )

    async def get_optimal_usage_windows(
        self,
        region: PriceRegion,
        duration_hours: int,
        within_hours: int = 24,
        supplier: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find optimal low-price windows for appliance usage.

        Args:
            region: Price region
            duration_hours: Required usage duration
            within_hours: Time window to search in
            supplier: Optional supplier filter

        Returns:
            List of optimal usage windows with start/end times and avg price
        """
        # Get historical prices for analysis
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=within_hours)

        prices = await self._repo.get_historical_prices(
            region=region,
            start_date=start,
            end_date=end,
            supplier=supplier
        )

        if len(prices) < duration_hours:
            return []

        # Sort by timestamp
        prices = sorted(prices, key=lambda p: p.timestamp)

        # Find windows with lowest average price
        windows = []
        for i in range(len(prices) - duration_hours + 1):
            window_prices = prices[i:i + duration_hours]
            avg_price = sum(p.price_per_kwh for p in window_prices) / duration_hours

            windows.append({
                'start': window_prices[0].timestamp,
                'end': window_prices[-1].timestamp + timedelta(hours=1),
                'avg_price': avg_price.quantize(Decimal("0.0001")),
                'prices': [p.price_per_kwh for p in window_prices]
            })

        # Sort by average price and return top 5
        windows.sort(key=lambda w: w['avg_price'])
        return windows[:5]

    async def get_price_statistics(
        self,
        region: PriceRegion,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get price statistics for a region.

        Args:
            region: Price region
            days: Number of days to analyze

        Returns:
            Dictionary with price statistics
        """
        return await self._repo.get_price_statistics(region, days)
