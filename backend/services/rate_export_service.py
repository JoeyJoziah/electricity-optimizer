"""
Rate Export Service

Exports historical rate data per utility type in CSV or JSON format.
Business tier only.
"""

import csv
import io
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Maximum export window
MAX_EXPORT_DAYS = 365

# Supported utility types and their table/column mappings
EXPORT_CONFIGS = {
    "electricity": {
        "table": "electricity_prices",
        "columns": ["region", "supplier", "price_per_kwh", "currency", "timestamp"],
        "price_col": "price_per_kwh",
        "time_col": "timestamp",
        "state_col": "region",
        "state_prefix": "us_",
        "extra_where": "utility_type = 'ELECTRICITY'",
        "unit": "$/kWh",
    },
    "natural_gas": {
        "table": "electricity_prices",
        "columns": ["region", "supplier", "price_per_kwh", "currency", "timestamp"],
        "price_col": "price_per_kwh",
        "time_col": "timestamp",
        "state_col": "region",
        "state_prefix": "us_",
        "extra_where": "utility_type = 'NATURAL_GAS'",
        "unit": "$/therm",
    },
    "heating_oil": {
        "table": "heating_oil_prices",
        "columns": ["state", "price_per_gallon", "source", "period_date", "fetched_at"],
        "price_col": "price_per_gallon",
        "time_col": "fetched_at",
        "state_col": "state",
        "state_prefix": "",
        "extra_where": None,
        "unit": "$/gallon",
    },
    "propane": {
        "table": "propane_prices",
        "columns": ["state", "price_per_gallon", "source", "period_date", "fetched_at"],
        "price_col": "price_per_gallon",
        "time_col": "fetched_at",
        "state_col": "state",
        "state_prefix": "",
        "extra_where": None,
        "unit": "$/gallon",
    },
}


class RateExportService:
    """Historical rate data export service."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export_rates(
        self,
        utility_type: str,
        format: str = "json",
        state: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """
        Export historical rate data.

        Args:
            utility_type: One of EXPORT_CONFIGS keys
            format: "json" or "csv"
            state: Optional state code filter
            start_date: Start of date range (defaults to 90 days ago)
            end_date: End of date range (defaults to now)

        Returns:
            Dict with format, data (list or CSV string), count, metadata
        """
        if utility_type not in EXPORT_CONFIGS:
            return {
                "error": f"Unknown utility type: {utility_type}",
                "supported_types": list(EXPORT_CONFIGS.keys()),
            }

        config = EXPORT_CONFIGS[utility_type]
        now = datetime.now(UTC)

        if not end_date:
            end_date = now
        if not start_date:
            start_date = now - timedelta(days=90)

        # Enforce max window
        if (end_date - start_date).days > MAX_EXPORT_DAYS:
            start_date = end_date - timedelta(days=MAX_EXPORT_DAYS)

        rows = await self._fetch_data(config, state, start_date, end_date)

        if format == "csv":
            csv_content = self._to_csv(rows, config["columns"])
            return {
                "format": "csv",
                "content_type": "text/csv",
                "data": csv_content,
                "count": len(rows),
                "utility_type": utility_type,
                "unit": config["unit"],
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
            }
        else:
            json_rows = self._to_json(rows, config["columns"])
            return {
                "format": "json",
                "content_type": "application/json",
                "data": json_rows,
                "count": len(rows),
                "utility_type": utility_type,
                "unit": config["unit"],
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
            }

    async def _fetch_data(
        self,
        config: dict,
        state: str | None,
        start_date: datetime,
        end_date: datetime,
    ) -> list:
        """Fetch data from the appropriate table."""
        cols = ", ".join(config["columns"])
        conditions = [
            f"{config['time_col']} >= :start_date",
            f"{config['time_col']} <= :end_date",
        ]
        params: dict = {"start_date": start_date, "end_date": end_date}

        if config["extra_where"]:
            conditions.append(config["extra_where"])

        if state:
            state_value = (
                f"{config['state_prefix']}{state.lower()}"
                if config["state_prefix"]
                else state.upper()
            )
            conditions.append(f"{config['state_col']} = :state")
            params["state"] = state_value

        where = " AND ".join(conditions)

        result = await self.db.execute(
            text(f"""
                SELECT {cols}
                FROM {config["table"]}
                WHERE {where}
                ORDER BY {config["time_col"]} ASC
                LIMIT 10000
            """),
            params,
        )
        return result.mappings().all()

    @staticmethod
    def _to_csv(rows: list, columns: list[str]) -> str:
        """Convert rows to CSV string."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(columns)

        for row in rows:
            writer.writerow(
                [
                    row[col].isoformat() if hasattr(row[col], "isoformat") else str(row[col])
                    for col in columns
                ]
            )

        return output.getvalue()

    @staticmethod
    def _to_json(rows: list, columns: list[str]) -> list[dict]:
        """Convert rows to JSON-serializable list."""
        result = []
        for row in rows:
            item = {}
            for col in columns:
                val = row[col]
                if hasattr(val, "isoformat"):
                    item[col] = val.isoformat()
                elif hasattr(val, "__float__"):
                    item[col] = float(val)
                else:
                    item[col] = str(val) if val is not None else None
            result.append(item)
        return result
