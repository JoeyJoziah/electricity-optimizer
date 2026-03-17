"""
Scheduled database maintenance — runs retention cleanup functions.

Designed to run as a Render cron job. Connects to Neon PostgreSQL,
executes cleanup_old_prices() and cleanup_old_observations(), and logs results.

Usage:
    python scripts/db_maintenance.py
"""

import asyncio
import os
import ssl
import sys
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import asyncpg


def clean_database_url(raw_url: str) -> str:
    """Strip sslmode/channel_binding params that asyncpg handles via connect args."""
    parsed = urlparse(raw_url)
    params = parse_qs(parsed.query)
    params.pop("sslmode", None)
    params.pop("channel_binding", None)
    clean_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=clean_query))


async def run_maintenance():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    db_url = clean_database_url(db_url)
    is_neon = "neon.tech" in db_url or "neon" in db_url

    connect_kwargs = {}
    if is_neon:
        connect_kwargs["ssl"] = "require"
        connect_kwargs["statement_cache_size"] = 0

    print("Connecting to database...")
    conn = await asyncpg.connect(db_url, **connect_kwargs)

    try:
        # Run price retention (default 365 days)
        price_result = await conn.fetchval("SELECT cleanup_old_prices(365)")
        print(f"cleanup_old_prices(365): deleted {price_result} rows")

        # Run observation retention (default 90 days)
        obs_result = await conn.fetchval("SELECT cleanup_old_observations(90)")
        print(f"cleanup_old_observations(90): deleted {obs_result} rows")

        # Cache table retention (Wave 0 — prevent Neon storage overflow)
        weather_result = await conn.fetchval(
            "DELETE FROM weather_cache WHERE fetched_at < now() - interval '30 days'"
        )
        print(f"weather_cache retention (30d): deleted {weather_result} rows")

        scraped_result = await conn.fetchval(
            "DELETE FROM scraped_rates WHERE fetched_at < now() - interval '90 days'"
        )
        print(f"scraped_rates retention (90d): deleted {scraped_result} rows")

        market_result = await conn.fetchval(
            "DELETE FROM market_intelligence WHERE fetched_at < now() - interval '180 days'"
        )
        print(f"market_intelligence retention (180d): deleted {market_result} rows")

        print("Database maintenance completed successfully.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_maintenance())
