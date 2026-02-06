"""
Supplier API Endpoints

REST endpoints for electricity supplier data.
"""

from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from pydantic import BaseModel

from models.supplier import (
    SupplierResponse,
    SupplierDetailResponse,
    SupplierListResponse,
    TariffResponse,
    TariffListResponse,
)
from api.dependencies import get_db_session, get_current_user_optional, TokenData


router = APIRouter()


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


class SupplierTariffsResponse(BaseModel):
    """Response for supplier tariffs endpoint"""
    supplier_id: str
    supplier_name: str
    tariffs: List[TariffResponse]
    total: int


# =============================================================================
# Mock Data (Replace with actual repository calls)
# =============================================================================


MOCK_SUPPLIERS = [
    {
        "id": "supplier_001",
        "name": "Octopus Energy",
        "regions": ["uk"],
        "tariff_types": ["variable", "agile", "fixed"],
        "api_available": True,
        "rating": 4.5,
        "green_energy_provider": True,
        "is_active": True,
    },
    {
        "id": "supplier_002",
        "name": "British Gas",
        "regions": ["uk"],
        "tariff_types": ["fixed", "variable"],
        "api_available": True,
        "rating": 3.8,
        "green_energy_provider": False,
        "is_active": True,
    },
    {
        "id": "supplier_003",
        "name": "EDF Energy",
        "regions": ["uk", "france"],
        "tariff_types": ["fixed", "variable", "green"],
        "api_available": True,
        "rating": 4.0,
        "green_energy_provider": True,
        "is_active": True,
    },
]


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=SuppliersResponse,
    summary="List electricity suppliers",
    responses={
        200: {"description": "Suppliers retrieved successfully"},
    }
)
async def list_suppliers(
    region: Optional[str] = Query(None, description="Filter by region"),
    green_only: bool = Query(False, description="Filter for green energy providers"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db=Depends(get_db_session),
):
    """
    List electricity suppliers with optional filtering.

    Returns paginated list of suppliers, optionally filtered by region
    or green energy status.
    """
    # Filter suppliers
    filtered = MOCK_SUPPLIERS

    if region:
        filtered = [s for s in filtered if region.lower() in s["regions"]]

    if green_only:
        filtered = [s for s in filtered if s["green_energy_provider"]]

    # Pagination
    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = filtered[start:end]

    suppliers = [
        SupplierResponse(**s) for s in paginated
    ]

    return SuppliersResponse(
        suppliers=suppliers,
        total=total,
        page=page,
        page_size=page_size,
        region=region,
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
    # Find supplier
    supplier = next(
        (s for s in MOCK_SUPPLIERS if s["id"] == supplier_id),
        None
    )

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
        review_count=None,
        green_energy_provider=supplier["green_energy_provider"],
        carbon_neutral=False,
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
    available_only: bool = Query(True, description="Show only available tariffs"),
    db=Depends(get_db_session),
):
    """
    Get tariffs offered by a specific supplier.

    Returns list of tariffs with pricing and contract details.
    """
    # Find supplier
    supplier = next(
        (s for s in MOCK_SUPPLIERS if s["id"] == supplier_id),
        None
    )

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier with ID '{supplier_id}' not found"
        )

    # Mock tariffs (replace with actual data)
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
    region: str = Path(..., description="Region code (e.g., uk, germany)"),
    green_only: bool = Query(False, description="Filter for green energy providers"),
    db=Depends(get_db_session),
):
    """
    Get all suppliers available in a specific region.

    Convenience endpoint for region-based filtering.
    """
    filtered = [s for s in MOCK_SUPPLIERS if region.lower() in s["regions"]]

    if green_only:
        filtered = [s for s in filtered if s["green_energy_provider"]]

    suppliers = [SupplierResponse(**s) for s in filtered]

    return SuppliersResponse(
        suppliers=suppliers,
        total=len(suppliers),
        page=1,
        page_size=len(suppliers),
        region=region,
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
    tariff_type: Optional[str] = Query(None, description="Filter by tariff type"),
    db=Depends(get_db_session),
):
    """
    Compare suppliers in a region with their best tariff prices.

    Returns suppliers sorted by their cheapest available tariff.
    """
    filtered = [s for s in MOCK_SUPPLIERS if region.lower() in s["regions"]]

    # In production, would fetch actual tariffs and sort by price
    comparison = []
    for supplier in filtered:
        comparison.append({
            "supplier_id": supplier["id"],
            "supplier_name": supplier["name"],
            "cheapest_tariff": "Standard Variable",  # Mock
            "unit_rate": "0.25",  # Mock
            "standing_charge": "0.40",  # Mock
            "rating": supplier.get("rating"),
            "green_energy_provider": supplier["green_energy_provider"],
        })

    # Sort by unit rate (mock - all same)
    comparison.sort(key=lambda x: float(x["unit_rate"]))

    return {
        "region": region,
        "suppliers": comparison,
        "total": len(comparison),
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
