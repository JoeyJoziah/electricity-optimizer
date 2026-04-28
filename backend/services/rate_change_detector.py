"""
Rate Change Detection Service

Compares current vs previous prices across all utility types and regions.
Generates rate_change_alerts when significant changes are detected.
Optionally finds cheaper alternatives for "better deal" recommendations.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Minimum % change to trigger an alert, per utility type
DEFAULT_THRESHOLDS: dict[str, float] = {
    "electricity": 5.0,
    "natural_gas": 5.0,
    "heating_oil": 3.0,
    "propane": 5.0,
    "community_solar": 5.0,
}

# How far back to look for the "previous" price, per utility type
LOOKBACK_DAYS: dict[str, int] = {
    "electricity": 7,
    "natural_gas": 14,
    "heating_oil": 14,
    "propane": 30,
    "community_solar": 30,
}


class RateChangeDetector:
    """Detects significant rate changes across utility types."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def detect_changes(
        self,
        utility_type: str,
        threshold_pct: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Detect rate changes for a given utility type across all regions.

        Compares the most recent price against the previous price for each
        region/supplier combination. Returns changes exceeding the threshold.

        Args:
            utility_type: One of electricity, natural_gas, heating_oil, etc.
            threshold_pct: Minimum % change to report. Uses DEFAULT_THRESHOLDS if None.

        Returns:
            List of detected change dicts with keys:
                utility_type, region, supplier, previous_price, current_price,
                change_pct, change_direction
        """
        threshold = threshold_pct or DEFAULT_THRESHOLDS.get(utility_type, 5.0)
        lookback = LOOKBACK_DAYS.get(utility_type, 14)
        cutoff = datetime.now(UTC) - timedelta(days=lookback)

        if utility_type == "heating_oil":
            return await self._detect_heating_oil_changes(threshold, cutoff)
        elif utility_type == "propane":
            return await self._detect_propane_changes(threshold, cutoff)
        elif utility_type == "natural_gas":
            return await self._detect_gas_changes(threshold, cutoff)
        else:
            return await self._detect_electricity_changes(threshold, cutoff)

    async def _detect_electricity_changes(
        self, threshold: float, cutoff: datetime
    ) -> list[dict[str, Any]]:
        """Detect electricity price changes from electricity_prices table."""
        result = await self._db.execute(
            text("""
                WITH ranked AS (
                    SELECT
                        region,
                        supplier,
                        price_per_kwh,
                        created_at,
                        ROW_NUMBER() OVER (
                            PARTITION BY region, supplier
                            ORDER BY created_at DESC
                        ) AS rn
                    FROM electricity_prices
                    WHERE created_at >= :cutoff
                )
                SELECT
                    curr.region,
                    curr.supplier,
                    curr.price_per_kwh AS current_price,
                    prev.price_per_kwh AS previous_price
                FROM ranked curr
                JOIN ranked prev
                    ON curr.region = prev.region
                    AND curr.supplier = prev.supplier
                    AND curr.rn = 1
                    AND prev.rn = 2
                WHERE prev.price_per_kwh > 0
            """),
            {"cutoff": cutoff},
        )
        return self._process_changes(result.mappings().all(), "electricity", threshold)

    async def _detect_gas_changes(
        self, threshold: float, cutoff: datetime
    ) -> list[dict[str, Any]]:
        """Detect natural gas price changes from utility_rates table."""
        result = await self._db.execute(
            text("""
                WITH ranked AS (
                    SELECT
                        state AS region,
                        supplier_name AS supplier,
                        rate_per_unit AS current_price,
                        effective_date,
                        ROW_NUMBER() OVER (
                            PARTITION BY state, supplier_name
                            ORDER BY effective_date DESC
                        ) AS rn
                    FROM utility_rates
                    WHERE utility_type = 'natural_gas'
                      AND effective_date >= :cutoff
                )
                SELECT
                    curr.region,
                    curr.supplier,
                    curr.current_price,
                    prev.current_price AS previous_price
                FROM ranked curr
                JOIN ranked prev
                    ON curr.region = prev.region
                    AND curr.supplier = prev.supplier
                    AND curr.rn = 1
                    AND prev.rn = 2
                WHERE prev.current_price > 0
            """),
            {"cutoff": cutoff},
        )
        return self._process_changes(result.mappings().all(), "natural_gas", threshold)

    async def _detect_heating_oil_changes(
        self, threshold: float, cutoff: datetime
    ) -> list[dict[str, Any]]:
        """Detect heating oil price changes from heating_oil_prices table."""
        result = await self._db.execute(
            text("""
                WITH ranked AS (
                    SELECT
                        state AS region,
                        source AS supplier,
                        price_per_gallon AS current_price,
                        period_date,
                        ROW_NUMBER() OVER (
                            PARTITION BY state
                            ORDER BY period_date DESC
                        ) AS rn
                    FROM heating_oil_prices
                    WHERE period_date >= :cutoff
                )
                SELECT
                    curr.region,
                    curr.supplier,
                    curr.current_price,
                    prev.current_price AS previous_price
                FROM ranked curr
                JOIN ranked prev
                    ON curr.region = prev.region
                    AND curr.rn = 1
                    AND prev.rn = 2
                WHERE prev.current_price > 0
            """),
            {"cutoff": cutoff},
        )
        return self._process_changes(result.mappings().all(), "heating_oil", threshold)

    async def _detect_propane_changes(
        self, threshold: float, cutoff: datetime
    ) -> list[dict[str, Any]]:
        """Detect propane price changes from propane_prices table."""
        result = await self._db.execute(
            text("""
                WITH ranked AS (
                    SELECT
                        state AS region,
                        source AS supplier,
                        price_per_gallon AS current_price,
                        period_date,
                        ROW_NUMBER() OVER (
                            PARTITION BY state
                            ORDER BY period_date DESC
                        ) AS rn
                    FROM propane_prices
                    WHERE period_date >= :cutoff
                )
                SELECT
                    curr.region,
                    curr.supplier,
                    curr.current_price,
                    prev.current_price AS previous_price
                FROM ranked curr
                JOIN ranked prev
                    ON curr.region = prev.region
                    AND curr.rn = 1
                    AND prev.rn = 2
                WHERE prev.current_price > 0
            """),
            {"cutoff": cutoff},
        )
        return self._process_changes(result.mappings().all(), "propane", threshold)

    def _process_changes(
        self,
        rows: list,
        utility_type: str,
        threshold: float,
    ) -> list[dict[str, Any]]:
        """Filter rows by threshold and return change dicts."""
        changes = []
        for row in rows:
            prev = Decimal(str(row["previous_price"]))
            curr = Decimal(str(row["current_price"]))
            if prev == 0:
                continue
            change_pct = float(((curr - prev) / prev) * 100)
            if abs(change_pct) >= threshold:
                changes.append(
                    {
                        "utility_type": utility_type,
                        "region": row["region"],
                        "supplier": row.get("supplier") or "Unknown",
                        "previous_price": float(prev),
                        "current_price": float(curr),
                        "change_pct": round(change_pct, 2),
                        "change_direction": (
                            "increase" if change_pct > 0 else "decrease"
                        ),
                    }
                )
        return changes

    async def find_cheaper_alternative(
        self,
        utility_type: str,
        region: str,
        current_price: float,
    ) -> dict[str, Any] | None:
        """
        Find a cheaper supplier alternative in the same region.

        Returns the cheapest active supplier with a lower price, or None.
        """
        if utility_type == "electricity":
            result = await self._db.execute(
                text("""
                    SELECT DISTINCT ON (supplier)
                        supplier,
                        price_per_kwh AS price
                    FROM electricity_prices
                    WHERE region = :region
                      AND price_per_kwh < :current_price
                      AND created_at >= NOW() - INTERVAL '7 days'
                    ORDER BY supplier, price_per_kwh ASC
                    LIMIT 1
                """),
                {"region": region, "current_price": current_price},
            )
        elif utility_type == "natural_gas":
            result = await self._db.execute(
                text("""
                    SELECT DISTINCT ON (supplier_name)
                        supplier_name AS supplier,
                        rate_per_unit AS price
                    FROM utility_rates
                    WHERE state = :region
                      AND utility_type = 'natural_gas'
                      AND rate_per_unit < :current_price
                      AND effective_date >= NOW() - INTERVAL '14 days'
                    ORDER BY supplier_name, rate_per_unit ASC
                    LIMIT 1
                """),
                {"region": region, "current_price": current_price},
            )
        else:
            return None

        row = result.mappings().first()
        if not row:
            return None

        savings = current_price - float(row["price"])
        return {
            "supplier": row["supplier"],
            "price": float(row["price"]),
            "savings": round(savings, 6),
        }

    async def store_changes(
        self,
        changes: list[dict[str, Any]],
    ) -> int:
        """Persist detected rate changes to rate_change_alerts table (500-row chunks)."""
        if not changes:
            return 0

        insert_sql = text("""
            INSERT INTO rate_change_alerts
                (id, utility_type, region, supplier,
                 previous_price, current_price, change_pct,
                 change_direction, detected_at,
                 recommendation_supplier, recommendation_price,
                 recommendation_savings)
            VALUES
                (:id, :utility_type, :region, :supplier,
                 :previous_price, :current_price, :change_pct,
                 :change_direction, :detected_at,
                 :rec_supplier, :rec_price, :rec_savings)
        """)

        stored = 0
        chunk_size = 500
        now = datetime.now(UTC)
        for chunk_start in range(0, len(changes), chunk_size):
            chunk = changes[chunk_start : chunk_start + chunk_size]
            try:
                for change in chunk:
                    await self._db.execute(
                        insert_sql,
                        {
                            "id": str(uuid4()),
                            "utility_type": change["utility_type"],
                            "region": change["region"],
                            "supplier": change["supplier"],
                            "previous_price": change["previous_price"],
                            "current_price": change["current_price"],
                            "change_pct": change["change_pct"],
                            "change_direction": change["change_direction"],
                            "detected_at": now,
                            "rec_supplier": change.get("recommendation_supplier"),
                            "rec_price": change.get("recommendation_price"),
                            "rec_savings": change.get("recommendation_savings"),
                        },
                    )
                await self._db.commit()
                stored += len(chunk)
            except Exception:
                await self._db.rollback()
                raise
        return stored

    async def get_recent_changes(
        self,
        utility_type: str | None = None,
        region: str | None = None,
        days: int = 7,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve recent rate change alerts, optionally filtered."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        conditions = ["detected_at >= :cutoff"]
        params: dict[str, Any] = {"cutoff": cutoff, "limit": limit}

        if utility_type:
            conditions.append("utility_type = :utility_type")
            params["utility_type"] = utility_type
        if region:
            conditions.append("region = :region")
            params["region"] = region

        where = " AND ".join(conditions)
        result = await self._db.execute(
            text(f"""
                SELECT id, utility_type, region, supplier,
                       previous_price, current_price, change_pct,
                       change_direction, detected_at,
                       recommendation_supplier, recommendation_price,
                       recommendation_savings
                FROM rate_change_alerts
                WHERE {where}
                ORDER BY detected_at DESC
                LIMIT :limit
            """),
            params,
        )
        rows = result.mappings().all()
        return [
            {
                "id": str(row["id"]),
                "utility_type": row["utility_type"],
                "region": row["region"],
                "supplier": row["supplier"],
                "previous_price": float(row["previous_price"]),
                "current_price": float(row["current_price"]),
                "change_pct": float(row["change_pct"]),
                "change_direction": row["change_direction"],
                "detected_at": row["detected_at"].isoformat(),
                "recommendation_supplier": row["recommendation_supplier"],
                "recommendation_price": (
                    float(row["recommendation_price"])
                    if row["recommendation_price"] is not None
                    else None
                ),
                "recommendation_savings": (
                    float(row["recommendation_savings"])
                    if row["recommendation_savings"] is not None
                    else None
                ),
            }
            for row in rows
        ]


class AlertPreferenceService:
    """Manages per-utility alert preferences for users."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_preferences(self, user_id: str) -> list[dict[str, Any]]:
        """Get all alert preferences for a user."""
        result = await self._db.execute(
            text("""
                SELECT id, user_id, utility_type, enabled, channels, cadence,
                       created_at, updated_at
                FROM alert_preferences
                WHERE user_id = :user_id
                ORDER BY utility_type
            """),
            {"user_id": user_id},
        )
        return [self._row_to_dict(row) for row in result.mappings().all()]

    async def upsert_preference(
        self,
        user_id: str,
        utility_type: str,
        enabled: bool | None = None,
        channels: list[str] | None = None,
        cadence: str | None = None,
    ) -> dict[str, Any]:
        """Create or update alert preference for a utility type."""
        params: dict[str, Any] = {
            "id": str(uuid4()),
            "user_id": user_id,
            "utility_type": utility_type,
            "enabled": enabled if enabled is not None else True,
            "channels": channels or ["email"],
            "cadence": cadence or "daily",
        }
        try:
            result = await self._db.execute(
                text("""
                    INSERT INTO alert_preferences
                        (id, user_id, utility_type, enabled, channels, cadence)
                    VALUES
                        (:id, :user_id, :utility_type, :enabled, :channels, :cadence)
                    ON CONFLICT (user_id, utility_type)
                    DO UPDATE SET
                        enabled = EXCLUDED.enabled,
                        channels = EXCLUDED.channels,
                        cadence = EXCLUDED.cadence,
                        updated_at = NOW()
                    RETURNING id, user_id, utility_type, enabled, channels, cadence,
                              created_at, updated_at
                """),
                params,
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        row = result.mappings().first()
        return self._row_to_dict(row)

    async def is_enabled(self, user_id: str, utility_type: str) -> bool:
        """Check if alerts are enabled for a specific utility type."""
        result = await self._db.execute(
            text("""
                SELECT enabled
                FROM alert_preferences
                WHERE user_id = :user_id AND utility_type = :utility_type
            """),
            {"user_id": user_id, "utility_type": utility_type},
        )
        row = result.first()
        # Default to enabled if no preference exists
        return row[0] if row else True

    @staticmethod
    def _row_to_dict(row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "utility_type": row["utility_type"],
            "enabled": row["enabled"],
            "channels": list(row["channels"]) if row["channels"] else ["email"],
            "cadence": row["cadence"],
            "created_at": (
                row["created_at"].isoformat() if row.get("created_at") else None
            ),
            "updated_at": (
                row["updated_at"].isoformat() if row.get("updated_at") else None
            ),
        }
