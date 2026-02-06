-- TimescaleDB Initialization Script for Electricity Optimizer
-- Creates hypertables, indexes, and retention policies

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================================
-- ELECTRICITY PRICES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS electricity_prices (
    time TIMESTAMPTZ NOT NULL,
    region VARCHAR(50) NOT NULL,
    supplier VARCHAR(100) NOT NULL,
    price DECIMAL(10, 4) NOT NULL,  -- Price in local currency per kWh
    currency VARCHAR(3) NOT NULL,    -- GBP, USD, EUR
    price_type VARCHAR(20) NOT NULL, -- spot, day_ahead, fixed
    data_source VARCHAR(50) NOT NULL, -- flatpeak, nrel, iea
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable (partitioned by time)
SELECT create_hypertable('electricity_prices', 'time', if_not_exists => TRUE);

-- Create indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_electricity_prices_region_time
    ON electricity_prices (region, time DESC);

CREATE INDEX IF NOT EXISTS idx_electricity_prices_supplier_time
    ON electricity_prices (supplier, time DESC);

CREATE INDEX IF NOT EXISTS idx_electricity_prices_region_supplier
    ON electricity_prices (region, supplier, time DESC);

-- Add compression policy (compress data older than 7 days)
ALTER TABLE electricity_prices SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'region, supplier',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('electricity_prices', INTERVAL '7 days', if_not_exists => TRUE);

-- Add retention policy (keep data for 2 years)
SELECT add_retention_policy('electricity_prices', INTERVAL '730 days', if_not_exists => TRUE);

-- ============================================================================
-- USER CONSUMPTION DATA TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_consumption (
    time TIMESTAMPTZ NOT NULL,
    user_id UUID NOT NULL,
    consumption_kwh DECIMAL(10, 4) NOT NULL,
    cost DECIMAL(10, 2),
    supplier VARCHAR(100),
    meter_id VARCHAR(100),
    data_source VARCHAR(50), -- smart_meter, manual, estimated
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable
SELECT create_hypertable('user_consumption', 'time', if_not_exists => TRUE);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_user_consumption_user_time
    ON user_consumption (user_id, time DESC);

-- Compression
ALTER TABLE user_consumption SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'user_id',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('user_consumption', INTERVAL '30 days', if_not_exists => TRUE);

-- Retention (keep user data for 2 years per GDPR)
SELECT add_retention_policy('user_consumption', INTERVAL '730 days', if_not_exists => TRUE);

-- ============================================================================
-- PRICE FORECASTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS price_forecasts (
    forecast_time TIMESTAMPTZ NOT NULL,    -- When forecast was made
    target_time TIMESTAMPTZ NOT NULL,      -- Time being forecasted
    region VARCHAR(50) NOT NULL,
    supplier VARCHAR(100),
    predicted_price DECIMAL(10, 4) NOT NULL,
    confidence_lower DECIMAL(10, 4),       -- Lower bound of confidence interval
    confidence_upper DECIMAL(10, 4),       -- Upper bound
    model_version VARCHAR(50) NOT NULL,
    model_type VARCHAR(50) NOT NULL,       -- cnn_lstm, xgboost, ensemble
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable (partition by forecast_time)
SELECT create_hypertable('price_forecasts', 'forecast_time', if_not_exists => TRUE);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_price_forecasts_target
    ON price_forecasts (target_time, region);

CREATE INDEX IF NOT EXISTS idx_price_forecasts_model
    ON price_forecasts (model_version, forecast_time DESC);

-- Compression
ALTER TABLE price_forecasts SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'region, model_version',
    timescaledb.compress_orderby = 'forecast_time DESC'
);

SELECT add_compression_policy('price_forecasts', INTERVAL '30 days', if_not_exists => TRUE);

-- Retention (keep forecasts for 90 days for accuracy tracking)
SELECT add_retention_policy('price_forecasts', INTERVAL '90 days', if_not_exists => TRUE);

-- ============================================================================
-- FORECAST ACCURACY TRACKING
-- ============================================================================
CREATE TABLE IF NOT EXISTS forecast_accuracy (
    evaluation_date DATE NOT NULL,
    region VARCHAR(50) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    model_type VARCHAR(50) NOT NULL,
    mape DECIMAL(10, 4),              -- Mean Absolute Percentage Error
    mae DECIMAL(10, 4),               -- Mean Absolute Error
    rmse DECIMAL(10, 4),              -- Root Mean Squared Error
    forecast_horizon_hours INT NOT NULL,
    sample_count INT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable
SELECT create_hypertable('forecast_accuracy', 'evaluation_date', if_not_exists => TRUE);

-- Index
CREATE INDEX IF NOT EXISTS idx_forecast_accuracy_model
    ON forecast_accuracy (model_version, evaluation_date DESC);

-- ============================================================================
-- SUPPLIER SWITCHING HISTORY
-- ============================================================================
CREATE TABLE IF NOT EXISTS supplier_switches (
    switch_time TIMESTAMPTZ NOT NULL,
    user_id UUID NOT NULL,
    from_supplier VARCHAR(100),
    to_supplier VARCHAR(100) NOT NULL,
    estimated_annual_savings DECIMAL(10, 2),
    switching_cost DECIMAL(10, 2),
    status VARCHAR(20) NOT NULL,      -- initiated, pending, completed, failed
    completion_time TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable
SELECT create_hypertable('supplier_switches', 'switch_time', if_not_exists => TRUE);

-- Index
CREATE INDEX IF NOT EXISTS idx_supplier_switches_user
    ON supplier_switches (user_id, switch_time DESC);

-- ============================================================================
-- CONTINUOUS AGGREGATES FOR FAST QUERIES
-- ============================================================================

-- Hourly average prices by region
CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_avg_prices
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS hour,
    region,
    supplier,
    AVG(price) AS avg_price,
    MIN(price) AS min_price,
    MAX(price) AS max_price,
    COUNT(*) AS sample_count
FROM electricity_prices
GROUP BY hour, region, supplier;

-- Refresh policy (update every 15 minutes)
SELECT add_continuous_aggregate_policy('hourly_avg_prices',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes',
    if_not_exists => TRUE
);

-- Daily consumption per user
CREATE MATERIALIZED VIEW IF NOT EXISTS daily_user_consumption
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS day,
    user_id,
    SUM(consumption_kwh) AS total_consumption_kwh,
    SUM(cost) AS total_cost,
    AVG(consumption_kwh) AS avg_hourly_consumption
FROM user_consumption
GROUP BY day, user_id;

-- Refresh policy
SELECT add_continuous_aggregate_policy('daily_user_consumption',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- ============================================================================
-- UTILITY FUNCTIONS
-- ============================================================================

-- Function to get latest price for a region
CREATE OR REPLACE FUNCTION get_latest_price(p_region VARCHAR, p_supplier VARCHAR DEFAULT NULL)
RETURNS TABLE (
    time TIMESTAMPTZ,
    price DECIMAL,
    supplier VARCHAR
) AS $$
BEGIN
    IF p_supplier IS NULL THEN
        RETURN QUERY
        SELECT ep.time, ep.price, ep.supplier
        FROM electricity_prices ep
        WHERE ep.region = p_region
        ORDER BY ep.time DESC
        LIMIT 1;
    ELSE
        RETURN QUERY
        SELECT ep.time, ep.price, ep.supplier
        FROM electricity_prices ep
        WHERE ep.region = p_region AND ep.supplier = p_supplier
        ORDER BY ep.time DESC
        LIMIT 1;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Function to get forecast accuracy for a model
CREATE OR REPLACE FUNCTION get_model_accuracy(p_model_version VARCHAR, p_days INT DEFAULT 30)
RETURNS TABLE (
    avg_mape DECIMAL,
    avg_mae DECIMAL,
    avg_rmse DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        AVG(mape) AS avg_mape,
        AVG(mae) AS avg_mae,
        AVG(rmse) AS avg_rmse
    FROM forecast_accuracy
    WHERE model_version = p_model_version
    AND evaluation_date >= CURRENT_DATE - p_days * INTERVAL '1 day';
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- INITIAL DATA VALIDATION
-- ============================================================================

-- Create check constraints
ALTER TABLE electricity_prices
    ADD CONSTRAINT check_price_positive CHECK (price >= 0);

ALTER TABLE user_consumption
    ADD CONSTRAINT check_consumption_positive CHECK (consumption_kwh >= 0);

ALTER TABLE price_forecasts
    ADD CONSTRAINT check_forecast_price_positive CHECK (predicted_price >= 0);

-- ============================================================================
-- COMMENTS FOR DOCUMENTATION
-- ============================================================================

COMMENT ON TABLE electricity_prices IS 'Time-series data for electricity spot prices from multiple sources';
COMMENT ON TABLE user_consumption IS 'User electricity consumption data from smart meters';
COMMENT ON TABLE price_forecasts IS 'ML model predictions for future electricity prices';
COMMENT ON TABLE forecast_accuracy IS 'Historical accuracy metrics for ML models';
COMMENT ON TABLE supplier_switches IS 'History of user supplier switching events';

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'TimescaleDB initialization completed successfully!';
    RAISE NOTICE 'Created tables: electricity_prices, user_consumption, price_forecasts, forecast_accuracy, supplier_switches';
    RAISE NOTICE 'Created continuous aggregates: hourly_avg_prices, daily_user_consumption';
    RAISE NOTICE 'Set up compression and retention policies';
END $$;
