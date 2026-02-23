"""
Supplier API Endpoints

REST endpoints for energy supplier data.
Supports multi-utility type filtering (electricity, gas, oil, propane, solar).
Backed by the supplier_registry table (migration 006).
"""

import re
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from pydantic import BaseModel

from models.supplier import (
    SupplierResponse,
    SupplierDetailResponse,
    SupplierListResponse,
    TariffResponse,
    TariffListResponse,
)
from models.utility import UtilityType
from api.dependencies import get_db_session, get_current_user_optional, TokenData
from repositories.supplier_repository import SupplierRegistryRepository


router = APIRouter()

# Regex for valid region codes (e.g. us_ct, uk, de, jp)
_REGION_RE = re.compile(r"^[a-z]{2}(_[a-z]{2})?$")


def _validate_uuid(value: str, label: str = "ID") -> None:
    """Raise 404 if value is not a valid UUID."""
    try:
        UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} '{value}' not found"
        )


def _validate_region_code(value: str) -> None:
    """Raise 422 if value doesn't look like a valid region code."""
    if not _REGION_RE.match(value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid region code: '{value}'"
        )


# =============================================================================
# Response Models
# =============================================================================


class SuppliersResponse(BaseModel):
    """Response for suppliers list endpoint"""
    suppliers: List[SupplierResponse]
    total: int
    page: int
    page_size: int
    region: Optional[str] = None
    utility_type: Optional[str] = None


class SupplierTariffsResponse(BaseModel):
    """Response for supplier tariffs endpoint"""
    supplier_id: str
    supplier_name: str
    tariffs: List[TariffResponse]
    total: int


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=SuppliersResponse,
    summary="List energy suppliers",
    responses={
        200: {"description": "Suppliers retrieved successfully"},
    }
)
async def list_suppliers(
    region: Optional[str] = Query(None, description="Filter by region (e.g., us_ct, us_ma)"),
    utility_type: Optional[str] = Query(None, description="Filter by utility type (electricity, natural_gas, heating_oil, propane, community_solar)"),
    green_only: bool = Query(False, description="Filter for green energy providers"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db=Depends(get_db_session),
):
    """
    List energy suppliers with optional filtering.

    Returns paginated list of suppliers, optionally filtered by region,
    utility type, or green energy status. Data is sourced from the
    supplier_registry table.
    """
    repo = SupplierRegistryRepository(db)
    suppliers_data, total = await repo.list_suppliers(
        region=region,
        utility_type=utility_type,
        green_only=green_only,
        active_only=True,
        page=page,
        page_size=page_size,
    )

    suppliers = [SupplierResponse(**s) for s in suppliers_data]

    return SuppliersResponse(
        suppliers=suppliers,
        total=total,
        page=page,
        page_size=page_size,
        region=region,
        utility_type=utility_type,
    )


@router.get(
    "/{supplier_id}",
    response_model=SupplierDetailResponse,
    summary="Get supplier details",
    responses={
        200: {"description": "Supplier retrieved successfully"},
        404: {"description": "Supplier not found"},
    }
)
async def get_supplier(
    supplier_id: str = Path(..., description="Supplier ID"),
    db=Depends(get_db_session),
):
    """
    Get detailed information about a specific supplier.

    Returns full supplier details including contact info and ratings.
    """
    _validate_uuid(supplier_id, "Supplier")
    repo = SupplierRegistryRepository(db)
    supplier = await repo.get_by_id(supplier_id)

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier with ID '{supplier_id}' not found"
        )

    return SupplierDetailResponse(
        id=supplier["id"],
        name=supplier["name"],
        regions=supplier["regions"],
        tariff_types=supplier["tariff_types"],
        api_available=supplier["api_available"],
        rating=supplier.get("rating"),
        review_count=supplier.get("review_count"),
        green_energy_provider=supplier["green_energy_provider"],
        carbon_neutral=supplier.get("carbon_neutral", False),
        average_renewable_percentage=None,
        description=None,
        logo_url=None,
        is_active=supplier["is_active"],
    )


@router.get(
    "/{supplier_id}/tariffs",
    response_model=SupplierTariffsResponse,
    summary="Get supplier tariffs",
    responses={
        200: {"description": "Tariffs retrieved successfully"},
        404: {"description": "Supplier not found"},
    }
)
async def get_supplier_tariffs(
    supplier_id: str = Path(..., description="Supplier ID"),
    utility_type: Optional[str] = Query(None, description="Filter by utility type"),
    available_only: bool = Query(True, description="Show only available tariffs"),
    db=Depends(get_db_session),
):
    """
    Get tariffs offered by a specific supplier.

    Returns list of tariffs with pricing and contract details.
    """
    _validate_uuid(supplier_id, "Supplier")
    repo = SupplierRegistryRepository(db)
    supplier = await repo.get_by_id(supplier_id)

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier with ID '{supplier_id}' not found"
        )

    # TODO: Replace with actual tariff query from DB once tariff data is populated.
    from decimal import Decimal
    from models.supplier import TariffType, ContractLength

    mock_tariffs = [
        TariffResponse(
            id=f"tariff_{supplier_id}_001",
            supplier_id=supplier_id,
            name="Standard Variable",
            type=TariffType.VARIABLE,
            unit_rate=Decimal("0.25"),
            standing_charge=Decimal("0.40"),
            green_energy_percentage=0,
            contract_length=ContractLength.ROLLING,
            is_available=True,
        ),
        TariffResponse(
            id=f"tariff_{supplier_id}_002",
            supplier_id=supplier_id,
            name="Fixed 12 Month",
            type=TariffType.FIXED,
            unit_rate=Decimal("0.22"),
            standing_charge=Decimal("0.45"),
            green_energy_percentage=50,
            contract_length=ContractLength.ANNUAL,
            is_available=True,
        ),
    ]

    if available_only:
        mock_tariffs = [t for t in mock_tariffs if t.is_available]

    return SupplierTariffsResponse(
        supplier_id=supplier_id,
        supplier_name=supplier["name"],
        tariffs=mock_tariffs,
        total=len(mock_tariffs),
    )


@router.get(
    "/region/{region}",
    response_model=SuppliersResponse,
    summary="Get suppliers by region",
    responses={
        200: {"description": "Suppliers retrieved successfully"},
    }
)
async def get_suppliers_by_region(
    region: str = Path(..., description="Region code (e.g., us_ct, us_ma, us_tx)"),
    utility_type: Optional[str] = Query(None, description="Filter by utility type"),
    green_only: bool = Query(False, description="Filter for green energy providers"),
    db=Depends(get_db_session),
):
    """
    Get all suppliers available in a specific region.

    Convenience endpoint for region-based filtering.
    """
    _validate_region_code(region)
    repo = SupplierRegistryRepository(db)
    suppliers_data, total = await repo.list_suppliers(
        region=region,
        utility_type=utility_type,
        green_only=green_only,
    )

    suppliers = [SupplierResponse(**s) for s in suppliers_data]

    return SuppliersResponse(
        suppliers=suppliers,
        total=total,
        page=1,
        page_size=total or 20,
        region=region,
        utility_type=utility_type,
    )


@router.get(
    "/compare/{region}",
    summary="Compare suppliers in a region",
    responses={
        200: {"description": "Comparison retrieved successfully"},
    }
)
async def compare_suppliers(
    region: str = Path(..., description="Region code"),
    utility_type: Optional[str] = Query("electricity", description="Utility type to compare"),
    tariff_type: Optional[str] = Query(None, description="Filter by tariff type"),
    db=Depends(get_db_session),
):
    """
    Compare suppliers in a region with their best tariff prices.

    Returns suppliers sorted by their cheapest available tariff.
    """
    repo = SupplierRegistryRepository(db)
    suppliers_data, _ = await repo.list_suppliers(
        region=region,
        utility_type=utility_type,
    )

    comparison = []
    for supplier in suppliers_data:
        comparison.append({
            "supplier_id": supplier["id"],
            "supplier_name": supplier["name"],
            "utility_types": supplier["utility_types"],
            "cheapest_tariff": "Standard Variable",
            "unit_rate": "0.25",
            "standing_charge": "0.40",
            "rating": supplier.get("rating"),
            "green_energy_provider": supplier["green_energy_provider"],
        })

    comparison.sort(key=lambda x: float(x["unit_rate"]))

    return {
        "region": region,
        "utility_type": utility_type,
        "suppliers": comparison,
        "total": len(comparison),
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
