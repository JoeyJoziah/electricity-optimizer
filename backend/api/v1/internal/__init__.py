"""
Internal API package.

Re-exports a single ``router`` that combines all sub-domain routers under a
shared ``verify_api_key`` dependency, preserving the import contract used by
app_factory:

    from api.v1.internal import router
"""

from fastapi import APIRouter, Depends

from api.dependencies import verify_api_key

from .alerts import router as alerts_router
from .billing import router as billing_router
from .data_pipeline import router as data_pipeline_router
from .email_scan import router as email_scan_router
from .ml import router as ml_router
from .operations import router as operations_router
from .portal_scan import router as portal_scan_router
from .sync import router as sync_router

router = APIRouter(dependencies=[Depends(verify_api_key)])
router.include_router(ml_router)
router.include_router(data_pipeline_router)
router.include_router(alerts_router)
router.include_router(billing_router)
router.include_router(operations_router)
router.include_router(sync_router)
router.include_router(email_scan_router)
router.include_router(portal_scan_router)

__all__ = ["router"]
