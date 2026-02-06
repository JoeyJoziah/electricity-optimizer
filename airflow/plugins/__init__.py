# Electricity Optimizer Airflow Plugins
"""
Custom operators, sensors, and hooks for the Electricity Optimizer.
"""

from airflow.plugins_manager import AirflowPlugin
from plugins.custom_operators import (
    PricingAPIOperator,
    TimescaleDBOperator,
    ModelTrainingOperator,
    ForecastGenerationOperator,
    DataQualityOperator,
    RedisCacheOperator,
)
from plugins.sensors import (
    PriceDataFreshnessSensor,
    ModelReadySensor,
    APIHealthSensor,
    MarketOpenSensor,
)
from plugins.hooks import (
    TimescaleDBHook,
    RedisHook,
    PricingAPIHook,
)


class ElectricityOptimizerPlugin(AirflowPlugin):
    """Airflow plugin for Electricity Optimizer custom components."""

    name = "electricity_optimizer"
    operators = [
        PricingAPIOperator,
        TimescaleDBOperator,
        ModelTrainingOperator,
        ForecastGenerationOperator,
        DataQualityOperator,
        RedisCacheOperator,
    ]
    sensors = [
        PriceDataFreshnessSensor,
        ModelReadySensor,
        APIHealthSensor,
        MarketOpenSensor,
    ]
    hooks = [
        TimescaleDBHook,
        RedisHook,
        PricingAPIHook,
    ]
