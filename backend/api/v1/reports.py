"""
Reports API — Multi-utility optimization reports.

Business tier gated. Aggregates spend across utilities and
identifies savings opportunities.
"""

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_db_session, require_tier
from services.optimization_report_service import OptimizationReportService

router = APIRouter(prefix="/reports")


@router.get(
    "/optimization",
    tags=["Reports"],
    summary="Generate multi-utility spend optimization report",
)
async def get_optimization_report(
    state: str = Query(..., description="State code (e.g. CT, NY)"),
    _user=Depends(require_tier("business")),
    db=Depends(get_db_session),
):
    """
    Generate a comprehensive optimization report across all tracked utilities.

    Requires Business subscription.

    Identifies top savings opportunities ranked by dollar impact.
    """
    service = OptimizationReportService(db)
    return await service.generate_report(state=state)
