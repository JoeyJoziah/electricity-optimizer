"""
Export API — Historical rate data export.

Business tier gated. Provides CSV/JSON export of rate history
per utility type with date range filtering.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from api.dependencies import get_db_session, require_tier
from services.rate_export_service import RateExportService, EXPORT_CONFIGS

router = APIRouter(prefix="/export")


@router.get(
    "/rates",
    tags=["Export"],
    summary="Export historical rate data",
)
async def export_rates(
    utility_type: str = Query(..., description="Utility type to export"),
    format: str = Query("json", regex="^(json|csv)$", description="Export format"),
    state: Optional[str] = Query(None, description="State code filter"),
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    _user=Depends(require_tier("business")),
    db=Depends(get_db_session),
):
    """
    Export historical rate data for a utility type.

    Requires Business subscription.

    - Supports JSON and CSV formats
    - Date range filter (defaults to last 90 days)
    - Max export window: 365 days
    - Max 10,000 rows per export
    """
    service = RateExportService(db)
    result = await service.export_rates(
        utility_type=utility_type,
        format=format,
        state=state,
        start_date=start_date,
        end_date=end_date,
    )

    if "error" in result:
        return result

    # For CSV, return as downloadable file
    if format == "csv":
        filename = f"rateshift_{utility_type}_rates.csv"
        return Response(
            content=result["data"],
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return result


@router.get(
    "/types",
    tags=["Export"],
    summary="List exportable utility types",
)
async def list_export_types(
    _user=Depends(require_tier("business")),
):
    """List all utility types that support data export."""
    return {
        "supported_types": list(EXPORT_CONFIGS.keys()),
        "formats": ["json", "csv"],
        "max_days": 365,
        "max_rows": 10000,
    }
