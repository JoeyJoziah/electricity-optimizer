"""
Analytics Service

Business logic for price analytics and aggregation.
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
from statistics import stdev

from repositories.price_repository import PriceRepository
from models.price import PriceRegion


class AnalyticsService:
    """
    Service for price analytics and trend analysis.

    Provides aggregation, statistical analysis, and
    trend detection for electricity prices.
    """

    def __init__(self, price_repo: PriceRepository, cache: Any = None):
        """
        Initialize the analytics service.

        Args:
            price_repo: Price repository instance
            cache: Optional Redis cache client
        """
        self._repo = price_repo
        self._cache = cache

    async def _get_cached(self, key: str) -> Optional[Dict]:
        """Get value from Redis cache."""
        if self._cache:
            try:
                cached = await self._cache.get(key)
                if cached:
                    return json.loads(cached)
            except Exception:
                pass
        return None

    async def _acquire_cache_lock(self, key: str, ttl_ms: int = 5000) -> bool:
        """Try to acquire a compute lock for a cache key (prevents stampede)."""
        if not self._cache:
            return True
        try:
            return bool(await self._cache.set(f"{key}:lock", "1", px=ttl_ms, nx=True))
        except Exception:
            return True

    async def _set_cached(self, key: str, value: Dict, ttl: int) -> None:
        """Set value in Redis cache with TTL."""
        if self._cache:
            try:
                await self._cache.set(
                    key,
                    json.dumps(value, default=str),
                    ex=ttl,
                )
                await self._cache.delete(f"{key}:lock")
            except Exception:
                pass

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
        cache_key = f"analytics:price_trend:{region.value}:{days}"
        cached = await self._get_cached(cache_key)
        if cached:
            for k in ('change_percent', 'start_price', 'end_price'):
                if k in cached:
                    cached[k] = Decimal(cached[k])
            return cached

        if not await self._acquire_cache_lock(cache_key):
            await asyncio.sleep(0.1)
            cached = await self._get_cached(cache_key)
            if cached:
                for k in ('change_percent', 'start_price', 'end_price'):
                    if k in cached:
                        cached[k] = Decimal(cached[k])
                return cached

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

        result = {
            'direction': direction,
            'change_percent': change_percent.quantize(Decimal("0.01")),
            'start_price': first_third_avg.quantize(Decimal("0.0001")),
            'end_price': last_third_avg.quantize(Decimal("0.0001")),
            'data_points': len(prices)
        }

        await self._set_cached(cache_key, result, ttl=900)  # 15 min
        return result

    async def get_peak_hours_analysis(
        self,
        region: PriceRegion,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Analyze peak and off-peak hours based on pricing.

        Uses SQL GROUP BY for aggregation (returns 24 rows max)
        instead of fetching all price records into memory.

        Args:
            region: Price region
            days: Number of days to analyze

        Returns:
            Analysis with peak and off-peak hour identification
        """
        cache_key = f"analytics:peak_hours:{region.value}:{days}"
        cached = await self._get_cached(cache_key)
        if cached:
            # Restore Decimal types from cached strings
            cached['average_by_hour'] = {int(k): Decimal(v) for k, v in cached['average_by_hour'].items()}
            cached['overall_average'] = Decimal(cached['overall_average'])
            cached['peak_premium_percent'] = Decimal(cached['peak_premium_percent'])
            return cached

        if not await self._acquire_cache_lock(cache_key):
            await asyncio.sleep(0.1)
            cached = await self._get_cached(cache_key)
            if cached:
                cached['average_by_hour'] = {int(k): Decimal(v) for k, v in cached['average_by_hour'].items()}
                cached['overall_average'] = Decimal(cached['overall_average'])
                cached['peak_premium_percent'] = Decimal(cached['peak_premium_percent'])
                return cached

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        hourly_rows = await self._repo.get_hourly_price_averages(
            region=region,
            start_date=start,
            end_date=end,
        )

        if not hourly_rows:
            return {
                'peak_hours': [],
                'off_peak_hours': [],
                'average_by_hour': {}
            }

        # Build hourly avg map (fill missing hours with 0)
        hourly_avg: Dict[int, Decimal] = {h: Decimal("0") for h in range(24)}
        total_weighted = Decimal("0")
        total_count = 0
        for row in hourly_rows:
            hourly_avg[row["hour"]] = row["avg_price"]
            total_weighted += row["avg_price"] * row["count"]
            total_count += row["count"]

        overall_avg = (total_weighted / total_count).quantize(Decimal("0.0001")) if total_count else Decimal("0")

        # Identify peak and off-peak hours
        peak_hours = []
        off_peak_hours = []

        for hour, avg in hourly_avg.items():
            if avg > overall_avg * Decimal("1.1"):
                peak_hours.append(hour)
            elif avg < overall_avg * Decimal("0.9"):
                off_peak_hours.append(hour)

        non_zero_avgs = [v for v in hourly_avg.values() if v > 0]
        max_avg = max(non_zero_avgs) if non_zero_avgs else Decimal("0")

        result = {
            'peak_hours': sorted(peak_hours),
            'off_peak_hours': sorted(off_peak_hours),
            'average_by_hour': hourly_avg,
            'overall_average': overall_avg,
            'peak_premium_percent': (
                (max_avg / overall_avg - 1) * 100
            ).quantize(Decimal("0.1")) if overall_avg > 0 else Decimal("0")
        }

        await self._set_cached(cache_key, result, ttl=900)  # 15 min
        return result

    async def get_supplier_comparison_analytics(
        self,
        region: PriceRegion,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get detailed supplier comparison analytics.

        Uses SQL GROUP BY for aggregation (one row per supplier)
        instead of fetching all price records into memory.

        Args:
            region: Price region
            days: Number of days to analyze

        Returns:
            Comparison analytics by supplier
        """
        cache_key = f"analytics:supplier_comparison:{region.value}:{days}"
        cached = await self._get_cached(cache_key)
        if cached:
            # Restore Decimal types from cached strings
            for s in cached.get('suppliers', []):
                for k in ('average_price', 'min_price', 'max_price', 'volatility'):
                    if k in s:
                        s[k] = Decimal(s[k])
            return cached

        if not await self._acquire_cache_lock(cache_key):
            await asyncio.sleep(0.1)
            cached = await self._get_cached(cache_key)
            if cached:
                for s in cached.get('suppliers', []):
                    for k in ('average_price', 'min_price', 'max_price', 'volatility'):
                        if k in s:
                            s[k] = Decimal(s[k])
                return cached

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        supplier_rows = await self._repo.get_supplier_price_stats(
            region=region,
            start_date=start,
            end_date=end,
        )

        if not supplier_rows:
            return {'suppliers': []}

        supplier_stats = [
            {
                'supplier': row['supplier'],
                'average_price': row['avg_price'],
                'min_price': row['min_price'],
                'max_price': row['max_price'],
                'volatility': row['volatility'],
                'data_points': row['count'],
            }
            for row in supplier_rows
        ]

        result = {
            'region': region.value,
            'period_days': days,
            'suppliers': supplier_stats,
            'cheapest_supplier': supplier_stats[0]['supplier'] if supplier_stats else None,
            'most_stable': min(supplier_stats, key=lambda s: s['volatility'])['supplier'] if supplier_stats else None
        }

        await self._set_cached(cache_key, result, ttl=3600)  # 1 hour
        return result
