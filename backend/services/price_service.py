"""
Price Service

Business logic for electricity price operations.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from typing import Optional, List, Dict, Any

from models.price import Price, PriceRegion, PriceForecast
from repositories.price_repository import PriceRepository

logger = logging.getLogger(__name__)

# Module-level cache for the ensemble predictor (loaded once)
_ensemble_predictor = None
_ensemble_load_attempted = False


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

        Tries the ML EnsemblePredictor first (if MODEL_PATH is set and models
        exist). Falls back to a simple peak/off-peak heuristic.

        Args:
            region: Price region
            hours: Forecast horizon in hours
            supplier: Optional supplier filter

        Returns:
            Price forecast if available
        """
        current_prices = await self._repo.get_current_prices(region, limit=1)
        if not current_prices:
            return None

        now = datetime.now(timezone.utc)
        base_price = current_prices[0].price_per_kwh
        default_supplier = supplier or current_prices[0].supplier
        currency = current_prices[0].currency

        # Try ML ensemble predictor
        ml_result = await self._try_ml_forecast(region, hours)
        if ml_result is not None:
            return self._ml_result_to_forecast(
                ml_result, region, hours, now, default_supplier, currency
            )

        # Fallback: simple peak/off-peak heuristic
        return self._simple_forecast(
            region, hours, now, base_price, default_supplier, currency
        )

    async def _try_ml_forecast(
        self, region: PriceRegion, hours: int
    ) -> Optional[Dict[str, Any]]:
        """Attempt to generate a forecast using the ML EnsemblePredictor."""
        global _ensemble_predictor, _ensemble_load_attempted

        if _ensemble_load_attempted and _ensemble_predictor is None:
            return None

        try:
            if not _ensemble_load_attempted:
                _ensemble_load_attempted = True
                _ensemble_predictor = await asyncio.to_thread(
                    self._load_ensemble_predictor
                )
                if _ensemble_predictor is None:
                    return None

            # Build feature DataFrame from recent prices
            features_df = await self._build_features(region, hours)
            if features_df is None:
                return None

            # Run prediction in thread (sync ML code)
            result = await asyncio.to_thread(
                _ensemble_predictor.predict,
                features_df,
                horizon=hours,
                confidence_level=0.9,
            )
            logger.info("ml_forecast_generated", region=str(region), hours=hours)
            return result

        except Exception as e:
            logger.warning("ml_forecast_failed", error=str(e))
            return None

    @staticmethod
    def _load_ensemble_predictor():
        """Load the EnsemblePredictor from MODEL_PATH (sync, runs in thread)."""
        import os

        model_path = os.environ.get("MODEL_PATH")
        if not model_path or not os.path.isdir(model_path):
            return None

        try:
            import sys
            # Add project root so ml package is importable
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            from ml.inference.ensemble_predictor import EnsemblePredictor
            predictor = EnsemblePredictor(model_path)
            logger.info("ensemble_predictor_loaded", version=predictor.version)
            return predictor
        except Exception as e:
            logger.warning("ensemble_predictor_load_failed", error=str(e))
            return None

    async def _build_features(self, region: PriceRegion, hours: int):
        """Build a feature DataFrame from recent price history for ML input."""
        try:
            import pandas as pd

            end = datetime.now(timezone.utc)
            start = end - timedelta(hours=168)  # 7 days of history
            prices = await self._repo.get_historical_prices(
                region=region, start_date=start, end_date=end
            )

            if len(prices) < 24:  # Need at least a day of data
                return None

            rows = []
            for p in prices:
                rows.append({
                    "timestamp": p.timestamp,
                    "price": float(p.price_per_kwh),
                    "hour": p.timestamp.hour,
                    "day_of_week": p.timestamp.weekday(),
                    "is_peak": 1 if (16 <= p.timestamp.hour <= 20) else 0,
                })

            return pd.DataFrame(rows)

        except ImportError:
            return None
        except Exception:
            return None

    def _ml_result_to_forecast(
        self,
        ml_result: Dict[str, Any],
        region: PriceRegion,
        hours: int,
        now: datetime,
        supplier: str,
        currency: str,
    ) -> PriceForecast:
        """Convert ML prediction arrays into a PriceForecast model."""
        forecast_prices = []
        point = ml_result["point"]
        lower = ml_result.get("lower", point)
        upper = ml_result.get("upper", point)

        for i in range(min(hours, len(point))):
            price_val = max(float(point[i]), 0)
            hour = (now + timedelta(hours=i)).hour
            forecast_prices.append(
                Price(
                    region=region,
                    supplier=supplier,
                    price_per_kwh=Decimal(str(round(price_val, 4))),
                    timestamp=now + timedelta(hours=i),
                    currency=currency,
                    is_peak=16 <= hour <= 20,
                )
            )

        # Confidence from interval width — narrower = higher confidence
        avg_width = float((upper - lower).mean()) if hasattr(upper, 'mean') else 0
        confidence = max(0.3, min(0.95, 1.0 - avg_width * 0.1))

        return PriceForecast(
            region=region,
            generated_at=now,
            horizon_hours=hours,
            prices=forecast_prices,
            confidence=confidence,
            model_version=getattr(_ensemble_predictor, "version", "ensemble"),
        )

    @staticmethod
    def _simple_forecast(
        region: PriceRegion,
        hours: int,
        now: datetime,
        base_price: Decimal,
        supplier: str,
        currency: str,
    ) -> PriceForecast:
        """Generate a simple peak/off-peak heuristic forecast."""
        forecast_prices = []
        for i in range(hours):
            hour = (now + timedelta(hours=i)).hour

            if 16 <= hour <= 20:
                price = base_price * Decimal("1.3")
            elif 0 <= hour <= 6:
                price = base_price * Decimal("0.7")
            else:
                price = base_price

            forecast_prices.append(
                Price(
                    region=region,
                    supplier=supplier,
                    price_per_kwh=price.quantize(Decimal("0.0001")),
                    timestamp=now + timedelta(hours=i),
                    currency=currency,
                    is_peak=16 <= hour <= 20,
                )
            )

        return PriceForecast(
            region=region,
            generated_at=now,
            horizon_hours=hours,
            prices=forecast_prices,
            confidence=0.7,
            model_version="simple_v1",
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
