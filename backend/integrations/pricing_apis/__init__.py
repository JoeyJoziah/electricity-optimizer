"""
Electricity Pricing API Integration Layer

This module provides unified access to multiple electricity pricing APIs:
- Flatpeak: UK/EU electricity prices
- NREL: US utility rates
- IEA: Global electricity statistics

Features:
- Async/await with httpx
- Automatic retry with exponential backoff
- Circuit breaker pattern for failures
- Redis caching with configurable TTL
- Request deduplication
- Structured logging
- Data normalization to common schema
"""

from .base import (
    BasePricingClient,
    PriceData,
    PriceForecast,
    PricingRegion,
    PriceUnit,
    APIError,
    RateLimitError,
    AuthenticationError,
    ServiceUnavailableError,
)
from .flatpeak import FlatpeakClient
from .nrel import NRELClient
from .iea import IEAClient
from .cache import PricingCache
from .rate_limiter import RateLimiter, TokenBucketLimiter
from .service import PricingService, create_pricing_service_from_settings

__all__ = [
    # Base classes and models
    "BasePricingClient",
    "PriceData",
    "PriceForecast",
    "PricingRegion",
    "PriceUnit",
    # Errors
    "APIError",
    "RateLimitError",
    "AuthenticationError",
    "ServiceUnavailableError",
    # Clients
    "FlatpeakClient",
    "NRELClient",
    "IEAClient",
    # Infrastructure
    "PricingCache",
    "RateLimiter",
    "TokenBucketLimiter",
    # Service
    "PricingService",
    "create_pricing_service_from_settings",
]
