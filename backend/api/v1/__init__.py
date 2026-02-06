"""
API v1 Routers

Version 1 of the Electricity Optimizer API.
"""

from api.v1.prices import router as prices_router
from api.v1.suppliers import router as suppliers_router

__all__ = ["prices_router", "suppliers_router"]
