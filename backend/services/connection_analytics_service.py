"""
Connection analytics service — rate comparison, history, and savings calculations.

Provides analytics endpoints for comparing user's extracted rates against market
prices, historical rate trends, and estimated savings calculations.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ConnectionAnalyticsService:
    """Analytics for connected utility accounts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_rate_comparison(
        self,
        user_id: str,
        connection_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compare user's extracted rates vs current market average.

        Returns the user's latest rate, market average for their region,
        delta, and percentage difference.
        """
        # Get user's latest extracted rate
        query = """
            SELECT cer.rate_per_kwh, cer.supplier_name, cer.extracted_at,
                   uc.id as connection_id, uc.connection_type
            FROM connection_extracted_rates cer
            JOIN user_connections uc ON cer.connection_id = uc.id
            WHERE uc.user_id = :uid
        """
        params: Dict[str, Any] = {"uid": user_id}
        if connection_id:
            query += " AND uc.id = :cid"
            params["cid"] = connection_id
        query += " ORDER BY cer.extracted_at DESC LIMIT 1"

        result = await self.db.execute(text(query), params)
        user_rate_row = result.mappings().first()

        if not user_rate_row:
            return {
                "has_data": False,
                "message": "No extracted rates found. Connect a utility account to see comparisons.",
            }

        user_rate = float(user_rate_row["rate_per_kwh"])
        supplier = user_rate_row["supplier_name"]

        # Get user's region
        region_result = await self.db.execute(
            text("SELECT region FROM public.users WHERE id = :uid"),
            {"uid": user_id},
        )
        region_row = region_result.fetchone()
        user_region = region_row[0] if region_row else "US_CT"

        # Get market average for region (last 30 days)
        market_result = await self.db.execute(
            text("""
                SELECT AVG(price_per_kwh) as avg_price,
                       MIN(price_per_kwh) as min_price,
                       MAX(price_per_kwh) as max_price,
                       COUNT(*) as sample_count
                FROM electricity_prices
                WHERE region = :region
                  AND timestamp >= NOW() - INTERVAL '30 days'
            """),
            {"region": user_region},
        )
        market_row = market_result.mappings().first()

        market_avg = float(market_row["avg_price"]) if market_row and market_row["avg_price"] else user_rate
        market_min = float(market_row["min_price"]) if market_row and market_row["min_price"] else user_rate
        market_max = float(market_row["max_price"]) if market_row and market_row["max_price"] else user_rate

        delta = user_rate - market_avg
        pct_diff = (delta / market_avg * 100) if market_avg else 0

        return {
            "has_data": True,
            "user_rate": round(user_rate, 4),
            "supplier": supplier,
            "market_average": round(market_avg, 4),
            "market_min": round(market_min, 4),
            "market_max": round(market_max, 4),
            "delta": round(delta, 4),
            "percentage_difference": round(pct_diff, 2),
            "region": user_region,
            "is_above_average": delta > 0,
            "sample_count": int(market_row["sample_count"]) if market_row else 0,
        }

    async def get_rate_history(
        self,
        user_id: str,
        connection_id: Optional[str] = None,
        days: int = 365,
    ) -> Dict[str, Any]:
        """
        Get historical rate data for chart rendering.

        Returns time-series of extracted rates per connection.
        """
        query = """
            SELECT cer.rate_per_kwh, cer.supplier_name, cer.extracted_at,
                   cer.billing_period_start, cer.billing_period_end,
                   uc.id as connection_id, uc.connection_type, uc.label
            FROM connection_extracted_rates cer
            JOIN user_connections uc ON cer.connection_id = uc.id
            WHERE uc.user_id = :uid
              AND cer.extracted_at >= NOW() - make_interval(days => :days)
        """
        params: Dict[str, Any] = {"uid": user_id, "days": days}
        if connection_id:
            query += " AND uc.id = :cid"
            params["cid"] = connection_id
        query += " ORDER BY cer.extracted_at ASC"

        result = await self.db.execute(text(query), params)
        rows = result.mappings().all()

        data_points = []
        for row in rows:
            data_points.append({
                "date": row["extracted_at"].isoformat() if row["extracted_at"] else None,
                "rate": float(row["rate_per_kwh"]) if row["rate_per_kwh"] else None,
                "supplier": row["supplier_name"],
                "connection_id": row["connection_id"],
                "connection_label": row["label"],
                "billing_start": row["billing_period_start"].isoformat() if row.get("billing_period_start") else None,
                "billing_end": row["billing_period_end"].isoformat() if row.get("billing_period_end") else None,
            })

        return {
            "data_points": data_points,
            "total": len(data_points),
            "days": days,
        }

    async def get_savings_estimate(
        self,
        user_id: str,
        monthly_kwh: float = 900,
    ) -> Dict[str, Any]:
        """
        Calculate estimated annual savings based on rate comparison.

        Uses user's extracted rate vs the best available market rate,
        multiplied by estimated annual consumption.
        """
        comparison = await self.get_rate_comparison(user_id)
        if not comparison.get("has_data"):
            return {
                "has_data": False,
                "message": "No rate data available for savings calculation.",
            }

        user_rate = comparison["user_rate"]
        market_min = comparison["market_min"]
        market_avg = comparison["market_average"]

        annual_kwh = monthly_kwh * 12

        # Savings vs best available rate
        savings_vs_best = (user_rate - market_min) * annual_kwh if user_rate > market_min else 0
        # Savings vs average rate
        savings_vs_avg = (user_rate - market_avg) * annual_kwh if user_rate > market_avg else 0

        return {
            "has_data": True,
            "user_rate": user_rate,
            "best_available_rate": market_min,
            "market_average_rate": market_avg,
            "monthly_kwh": monthly_kwh,
            "annual_kwh": annual_kwh,
            "estimated_annual_savings_vs_best": round(savings_vs_best, 2),
            "estimated_annual_savings_vs_average": round(savings_vs_avg, 2),
            "estimated_monthly_savings_vs_best": round(savings_vs_best / 12, 2),
            "current_annual_cost": round(user_rate * annual_kwh, 2),
            "best_annual_cost": round(market_min * annual_kwh, 2),
        }

    async def check_stale_connections(
        self,
        user_id: str,
        stale_threshold_days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Find connections that haven't synced in >30 days."""
        result = await self.db.execute(
            text("""
                SELECT id, connection_type, label, email_provider,
                       status, last_scan_at, updated_at, created_at
                FROM user_connections
                WHERE user_id = :uid
                  AND status = 'active'
                  AND (
                    last_scan_at IS NULL
                    OR last_scan_at < NOW() - make_interval(days => :threshold)
                  )
            """),
            {"uid": user_id, "threshold": stale_threshold_days},
        )
        rows = result.mappings().all()

        return [
            {
                "connection_id": row["id"],
                "connection_type": row["connection_type"],
                "label": row["label"],
                "email_provider": row["email_provider"],
                "last_scan_at": row["last_scan_at"].isoformat() if row["last_scan_at"] else None,
                "days_since_sync": (
                    (datetime.now(timezone.utc) - row["last_scan_at"]).days
                    if row["last_scan_at"]
                    else (datetime.now(timezone.utc) - row["created_at"]).days
                    if row["created_at"]
                    else None
                ),
            }
            for row in rows
        ]

    async def detect_rate_changes(
        self,
        user_id: str,
        threshold_pct: float = 5.0,
    ) -> List[Dict[str, Any]]:
        """Detect significant rate changes (>threshold%) between consecutive extractions."""
        result = await self.db.execute(
            text("""
                SELECT cer.rate_per_kwh, cer.supplier_name, cer.extracted_at,
                       uc.id as connection_id, uc.label,
                       LAG(cer.rate_per_kwh) OVER (
                           PARTITION BY cer.connection_id ORDER BY cer.extracted_at
                       ) as prev_rate
                FROM connection_extracted_rates cer
                JOIN user_connections uc ON cer.connection_id = uc.id
                WHERE uc.user_id = :uid
                ORDER BY cer.connection_id, cer.extracted_at DESC
            """),
            {"uid": user_id},
        )
        rows = result.mappings().all()

        alerts = []
        for row in rows:
            if row["prev_rate"] is None:
                continue
            current = float(row["rate_per_kwh"])
            previous = float(row["prev_rate"])
            if previous == 0:
                continue
            change_pct = abs((current - previous) / previous) * 100
            if change_pct >= threshold_pct:
                alerts.append({
                    "connection_id": row["connection_id"],
                    "connection_label": row["label"],
                    "supplier": row["supplier_name"],
                    "previous_rate": round(previous, 4),
                    "current_rate": round(current, 4),
                    "change_percentage": round(change_pct, 2),
                    "direction": "increase" if current > previous else "decrease",
                    "detected_at": row["extracted_at"].isoformat() if row["extracted_at"] else None,
                })

        return alerts
