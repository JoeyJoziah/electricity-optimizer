"""
Multi-Utility Forecast Service

Provides rate forecasting across utility types:
- Electricity: delegates to existing ML EnsemblePredictor (via PriceService)
- Gas/Oil/Propane: simple linear trend extrapolation (Decision D9: no ML until 6+ months data)
- Water: not forecasted (rates change via municipal schedule, not market)
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Valid utility types for forecasting
FORECASTABLE_UTILITIES = ("electricity", "natural_gas", "heating_oil", "propane")

# Trend extrapolation lookback window
TREND_LOOKBACK_DAYS = 90
FORECAST_HORIZON_DAYS = 30

# Allowlists for SQL identifiers to prevent injection
_ALLOWED_TABLES = frozenset({"electricity_prices", "heating_oil_prices", "propane_prices"})
_ALLOWED_COLS = frozenset({
    "price_per_kwh", "price_per_gallon", "fetched_at", "timestamp", "region", "state",
})


def _validate_sql_identifier(value: str, allowlist: frozenset, label: str) -> str:
    """Validate that a SQL identifier is in the allowlist."""
    if value not in allowlist:
        raise ValueError(f"Disallowed {label}: {value!r}")
    return value


class ForecastService:
    """Multi-utility rate forecasting service."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_forecast(
        self,
        utility_type: str,
        state: Optional[str] = None,
        horizon_days: int = FORECAST_HORIZON_DAYS,
    ) -> dict:
        """
        Generate a rate forecast for the given utility type.

        Args:
            utility_type: One of FORECASTABLE_UTILITIES
            state: State code (required for gas/oil/propane, optional for electricity)
            horizon_days: Number of days to forecast (max 90)

        Returns:
            Forecast dict with current_rate, forecasted_rate, trend, confidence, data_points
        """
        if utility_type not in FORECASTABLE_UTILITIES:
            return {
                "utility_type": utility_type,
                "error": f"Forecasting not available for {utility_type}",
                "supported_types": list(FORECASTABLE_UTILITIES),
            }

        horizon_days = min(horizon_days, 90)

        if utility_type == "electricity":
            return await self._forecast_electricity(state, horizon_days)
        elif utility_type == "natural_gas":
            return await self._forecast_from_table(
                utility_type="natural_gas",
                table="electricity_prices",
                price_col="price_per_kwh",
                unit="$/therm",
                where_clause="utility_type = 'NATURAL_GAS'",
                state=state,
                state_col="region",
                state_prefix="us_",
                horizon_days=horizon_days,
            )
        elif utility_type == "heating_oil":
            return await self._forecast_from_table(
                utility_type="heating_oil",
                table="heating_oil_prices",
                price_col="price_per_gallon",
                unit="$/gallon",
                where_clause=None,
                state=state,
                state_col="state",
                state_prefix="",
                horizon_days=horizon_days,
            )
        elif utility_type == "propane":
            return await self._forecast_from_table(
                utility_type="propane",
                table="propane_prices",
                price_col="price_per_gallon",
                unit="$/gallon",
                where_clause=None,
                state=state,
                state_col="state",
                state_prefix="",
                horizon_days=horizon_days,
            )

        return {"utility_type": utility_type, "error": "Unknown utility type"}

    async def _forecast_electricity(
        self, state: Optional[str], horizon_days: int
    ) -> dict:
        """Electricity forecast using historical price data and trend extrapolation.

        Note: The ML EnsemblePredictor is already available via PriceService.get_price_forecast
        for hourly forecasting. This method provides a simpler daily trend view.
        """
        region_filter = ""
        params: dict = {"lookback_days": TREND_LOOKBACK_DAYS}
        if state:
            region_filter = "AND region = :region"
            params["region"] = f"us_{state.lower()}"

        result = await self.db.execute(
            text(f"""
                SELECT price_per_kwh, timestamp
                FROM electricity_prices
                WHERE utility_type = 'ELECTRICITY'
                  AND timestamp >= NOW() - make_interval(days => :lookback_days)
                  {region_filter}
                ORDER BY timestamp ASC
            """),
            params,
        )
        rows = result.mappings().all()
        return self._extrapolate_trend(
            utility_type="electricity",
            rows=rows,
            price_col="price_per_kwh",
            time_col="timestamp",
            unit="$/kWh",
            state=state,
            horizon_days=horizon_days,
        )

    async def _forecast_from_table(
        self,
        utility_type: str,
        table: str,
        price_col: str,
        unit: str,
        where_clause: Optional[str],
        state: Optional[str],
        state_col: str,
        state_prefix: str,
        horizon_days: int,
    ) -> dict:
        """Generic trend extrapolation from a price history table."""
        # Validate all SQL identifiers against allowlists
        _validate_sql_identifier(table, _ALLOWED_TABLES, "table")
        _validate_sql_identifier(price_col, _ALLOWED_COLS, "column")
        _validate_sql_identifier(state_col, _ALLOWED_COLS, "column")

        conditions = []
        params: dict = {"lookback_days": TREND_LOOKBACK_DAYS}

        # Time filter — use fetched_at or period_date depending on table
        time_col = "fetched_at" if table in ("heating_oil_prices", "propane_prices") else "timestamp"
        _validate_sql_identifier(time_col, _ALLOWED_COLS, "column")
        conditions.append(
            f"{time_col} >= NOW() - make_interval(days => :lookback_days)"
        )

        if where_clause:
            conditions.append(where_clause)

        if state:
            state_value = f"{state_prefix}{state.lower()}" if state_prefix else state.upper()
            conditions.append(f"{state_col} = :state")
            params["state"] = state_value

        where = " AND ".join(conditions)

        result = await self.db.execute(
            text(f"""
                SELECT {price_col}, {time_col}
                FROM {table}
                WHERE {where}
                ORDER BY {time_col} ASC
            """),
            params,
        )
        rows = result.mappings().all()
        return self._extrapolate_trend(
            utility_type=utility_type,
            rows=rows,
            price_col=price_col,
            time_col=time_col,
            unit=unit,
            state=state,
            horizon_days=horizon_days,
        )

    @staticmethod
    def _extrapolate_trend(
        utility_type: str,
        rows: list,
        price_col: str,
        time_col: str,
        unit: str,
        state: Optional[str],
        horizon_days: int,
    ) -> dict:
        """Simple linear trend extrapolation from historical data points.

        Uses least-squares linear regression on (day_index, price) pairs.
        """
        if not rows or len(rows) < 2:
            return {
                "utility_type": utility_type,
                "state": state,
                "unit": unit,
                "data_points": len(rows) if rows else 0,
                "error": "Insufficient data for trend analysis (need 2+ data points)",
            }

        # Extract prices and compute day offsets
        prices = []
        timestamps = []
        for r in rows:
            price_val = r[price_col]
            time_val = r[time_col]
            if price_val is not None and time_val is not None:
                prices.append(float(price_val))
                timestamps.append(time_val)

        if len(prices) < 2:
            return {
                "utility_type": utility_type,
                "state": state,
                "unit": unit,
                "data_points": len(prices),
                "error": "Insufficient valid data points",
            }

        # Convert timestamps to day offsets from first point
        base_time = timestamps[0]
        days = [(t - base_time).total_seconds() / 86400 for t in timestamps]

        # Simple linear regression: y = mx + b
        n = len(days)
        sum_x = sum(days)
        sum_y = sum(prices)
        sum_xy = sum(x * y for x, y in zip(days, prices))
        sum_xx = sum(x * x for x in days)

        denominator = n * sum_xx - sum_x * sum_x
        if abs(denominator) < 1e-10:
            slope = 0.0
            intercept = sum_y / n
        else:
            slope = (n * sum_xy - sum_x * sum_y) / denominator
            intercept = (sum_y - slope * sum_x) / n

        # Current rate (latest data point)
        current_rate = prices[-1]
        current_day = days[-1]

        # Forecasted rate at horizon
        forecast_day = current_day + horizon_days
        forecasted_rate = intercept + slope * forecast_day

        # Don't allow negative forecasts
        forecasted_rate = max(forecasted_rate, 0.0)

        # Trend direction
        pct_change = ((forecasted_rate - current_rate) / current_rate * 100) if current_rate > 0 else 0
        if pct_change > 1:
            trend = "increasing"
        elif pct_change < -1:
            trend = "decreasing"
        else:
            trend = "stable"

        # Confidence based on data density and R-squared
        predicted = [intercept + slope * d for d in days]
        ss_res = sum((y - yp) ** 2 for y, yp in zip(prices, predicted))
        mean_y = sum_y / n
        ss_tot = sum((y - mean_y) ** 2 for y in prices)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        # Confidence: weight R² (fit quality) and data density
        data_density = min(n / 30, 1.0)  # 30 points = full density
        confidence = round(0.4 * max(r_squared, 0) + 0.6 * data_density, 2)

        return {
            "utility_type": utility_type,
            "state": state,
            "unit": unit,
            "current_rate": round(current_rate, 4),
            "forecasted_rate": round(forecasted_rate, 4),
            "horizon_days": horizon_days,
            "trend": trend,
            "percent_change": round(pct_change, 2),
            "confidence": confidence,
            "model": "trend_extrapolation_v1",
            "data_points": n,
            "r_squared": round(max(r_squared, 0), 4),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
