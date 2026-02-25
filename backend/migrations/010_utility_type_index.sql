-- Migration 010: Index for multi-utility price queries
--
-- Supports get_historical_prices() and get_current_prices() in price_repository.py
-- which filter by (region, utility_type, timestamp).
--
-- NOTE: Run against app endpoint (ep-withered-morning), NOT Neon MCP endpoint.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prices_region_utilitytype_timestamp
    ON electricity_prices (region, utility_type, timestamp DESC);
