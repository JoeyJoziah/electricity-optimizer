"""
External API Integrations

This module provides integration clients for external services:

Pricing APIs:
- Flatpeak: UK/EU electricity prices
- NREL: US utility rates
- IEA: Global electricity statistics

All clients support:
- Async/await with httpx
- Automatic retry with exponential backoff
- Circuit breaker pattern
- Redis caching
- Rate limiting
- Structured logging
"""

from .pricing_apis import \
    PriceForecast  # backward-compat alias for ForecastData
from .pricing_apis import (  # Errors; Base classes and models; Clients; Infrastructure
    APIError, AuthenticationError, BasePricingClient, FlatpeakClient,
    ForecastData, IEAClient, NRELClient, PriceData, PriceUnit, PricingCache,
    PricingRegion, RateLimiter, RateLimitError, ServiceUnavailableError,
    TokenBucketLimiter)

__all__ = [
    # Base classes and models
    "BasePricingClient",
    "PriceData",
    "ForecastData",
    "PriceForecast",  # backward-compat alias
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
]
