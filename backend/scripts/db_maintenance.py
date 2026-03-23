"""
Scheduled database maintenance — runs retention cleanup functions.

Designed to run as a Render cron job. Connects to Neon PostgreSQL,
executes cleanup_old_prices() and cleanup_old_observations(), and logs results.

Usage:
    python scripts/db_maintenance.py
"""

import asyncio
import os
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


def _parse_delete_count(command_tag: str) -> int:
    """Extract row count from asyncpg execute() command tag (e.g. 'DELETE 42')."""
    parts = command_tag.split()
    if len(parts) >= 2 and parts[-1].isdigit():
        return int(parts[-1])
    return 0


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
        # P1-9: Use execute() instead of fetchval() for DELETE statements.
        # fetchval() returns None when zero rows are deleted; execute()
        # returns the command tag (e.g. "DELETE 42") which we parse.
        weather_tag = await conn.execute(
            "DELETE FROM weather_cache WHERE fetched_at < now() - interval '30 days'"
        )
        print(f"weather_cache retention (30d): deleted {_parse_delete_count(weather_tag)} rows")

        scraped_tag = await conn.execute(
            "DELETE FROM scraped_rates WHERE fetched_at < now() - interval '90 days'"
        )
        print(f"scraped_rates retention (90d): deleted {_parse_delete_count(scraped_tag)} rows")

        market_tag = await conn.execute(
            "DELETE FROM market_intelligence WHERE fetched_at < now() - interval '180 days'"
        )
        print(
            f"market_intelligence retention (180d): deleted {_parse_delete_count(market_tag)} rows"
        )

        # P1-8: rate_change_alerts retention — 90 days.
        # The idx_rate_change_alerts_recent index on (detected_at DESC)
        # supports efficient range scans for this deletion.
        rate_alerts_tag = await conn.execute(
            "DELETE FROM rate_change_alerts WHERE detected_at < now() - interval '90 days'"
        )
        print(
            f"rate_change_alerts retention (90d): deleted {_parse_delete_count(rate_alerts_tag)} rows"
        )

        print("Database maintenance completed successfully.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_maintenance())
