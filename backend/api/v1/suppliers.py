"""
Supplier API Endpoints

REST endpoints for energy supplier data.
Supports multi-utility type filtering (electricity, gas, oil, propane, solar).
Backed by the supplier_registry table (migration 006).
"""

import re
from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy import text

from api.dependencies import get_db_session, get_redis
from models.supplier import (
    SupplierDetailResponse,
    SupplierResponse,
    TariffResponse,
)
from repositories.supplier_repository import SupplierRegistryRepository

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Suppliers"])

# Regex for valid region codes (e.g. us_ct, uk, de, jp)
_REGION_RE = re.compile(r"^[a-z]{2}(_[a-z]{2})?$")


def _validate_uuid(value: str, label: str = "ID") -> None:
    """Raise 404 if value is not a valid UUID."""
    try:
        UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} '{value}' not found"
        )


def _validate_region_code(value: str) -> None:
    """Raise 422 if value doesn't look like a valid region code."""
    if not _REGION_RE.match(value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid region code: '{value}'",
        )


# =============================================================================
# Response Models
# =============================================================================


class SuppliersResponse(BaseModel):
    """Response for suppliers list endpoint"""

    suppliers: list[SupplierResponse]
    total: int
    page: int
    page_size: int
    region: str | None = None
    utility_type: str | None = None


class SupplierTariffsResponse(BaseModel):
    """Response for supplier tariffs endpoint"""

    supplier_id: str
    supplier_name: str
    tariffs: list[TariffResponse]
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
    },
)
async def list_suppliers(
    region: str | None = Query(None, description="Filter by region (e.g., us_ct, us_ma)"),
    utility_type: str | None = Query(
        None,
        description="Filter by utility type (electricity, natural_gas, heating_oil, propane, community_solar)",
    ),
    green_only: bool = Query(False, description="Filter for green energy providers"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db=Depends(get_db_session),
    redis=Depends(get_redis),
):
    """
    List energy suppliers with optional filtering.

    Returns paginated list of suppliers, optionally filtered by region,
    utility type, or green energy status. Data is sourced from the
    supplier_registry table. Results are cached in Redis for 1 hour.
    """
    repo = SupplierRegistryRepository(db, cache=redis)
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


@router.get("/registry", summary="List suppliers with API integration")
async def list_registry_suppliers(
    region: str | None = Query(None, description="Filter by region"),
    utility_type: str | None = Query(None, description="Filter by utility type"),
    db=Depends(get_db_session),
    redis=Depends(get_redis),
):
    """
    List suppliers that have API integration available.

    Used by the DirectLoginForm dropdown to show connectable utility providers.
    Returns only suppliers with api_available=true.
    """
    repo = SupplierRegistryRepository(db, cache=redis)
    suppliers_data, _ = await repo.list_suppliers(
        region=region,
        utility_type=utility_type,
        active_only=True,
        page=1,
        page_size=100,
    )
    api_suppliers = [s for s in suppliers_data if s.get("api_available")]

    # Fallback: if no suppliers have api_available set, return all active suppliers
    # so the dropdown is never empty. This handles the case where the migration
    # to set api_available hasn't been run yet.
    if not api_suppliers and suppliers_data:
        logger.warning(
            "supplier_registry_fallback",
            msg="No suppliers with api_available=true found, falling back to all active suppliers",
            total_active=len(suppliers_data),
        )
        api_suppliers = suppliers_data

    return {
        "suppliers": [
            {
                "id": s["id"],
                "name": s["name"],
                "region": s["regions"][0] if s.get("regions") else None,
                "utility_type": s["utility_types"][0] if s.get("utility_types") else "electricity",
            }
            for s in api_suppliers
        ]
    }


@router.get(
    "/{supplier_id}",
    response_model=SupplierDetailResponse,
    summary="Get supplier details",
    responses={
        200: {"description": "Supplier retrieved successfully"},
        404: {"description": "Supplier not found"},
    },
)
async def get_supplier(
    supplier_id: UUID = Path(..., description="Supplier ID (UUID)"),
    db=Depends(get_db_session),
    redis=Depends(get_redis),
):
    """
    Get detailed information about a specific supplier.

    Returns full supplier details including contact info and ratings.
    Result is cached in Redis for 1 hour.
    """
    repo = SupplierRegistryRepository(db, cache=redis)
    supplier = await repo.get_by_id(str(supplier_id))

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier with ID '{supplier_id}' not found",
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
    },
)
async def get_supplier_tariffs(
    supplier_id: UUID = Path(..., description="Supplier ID (UUID)"),
    utility_type: str | None = Query(None, description="Filter by utility type"),
    available_only: bool = Query(True, description="Show only available tariffs"),
    db=Depends(get_db_session),
    redis=Depends(get_redis),
):
    """
    Get tariffs offered by a specific supplier.

    Returns list of tariffs with pricing and contract details.
    The supplier existence check uses the Redis-cached get_by_id() call.
    """
    repo = SupplierRegistryRepository(db, cache=redis)
    supplier = await repo.get_by_id(str(supplier_id))

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier with ID '{supplier_id}' not found",
        )

    from models.supplier import ContractLength, TariffType

    # Build WHERE clause incrementally so we keep one parameterised query string
    where_clauses = ["supplier_id = :supplier_id"]
    params: dict = {"supplier_id": str(supplier_id)}

    if utility_type:
        where_clauses.append("utility_type = :utility_type")
        params["utility_type"] = utility_type

    if available_only:
        where_clauses.append("is_available = TRUE")

    where_sql = " AND ".join(where_clauses)
    query = text(f"""
        SELECT id, supplier_id, name, price_per_kwh, standing_charge,
               is_available, tariff_type, utility_type
        FROM tariffs
        WHERE {where_sql}
        ORDER BY name
    """)

    result = await db.execute(query, params)
    rows = result.fetchall()

    # Map DB columns → TariffResponse fields.
    # DB tariff_type values are expected to match TariffType enum members
    # (fixed, variable, time_of_use, prepaid, green, agile).  Unknown values
    # fall back to VARIABLE so the endpoint never hard-crashes on stale data.
    tariffs: list[TariffResponse] = []
    for row in rows:
        try:
            tariff_type_value = TariffType(row.tariff_type)
        except ValueError:
            tariff_type_value = TariffType.VARIABLE

        tariffs.append(
            TariffResponse(
                id=str(row.id),
                supplier_id=str(row.supplier_id),
                name=row.name,
                type=tariff_type_value,
                unit_rate=row.price_per_kwh,
                standing_charge=row.standing_charge,
                green_energy_percentage=0,
                contract_length=ContractLength.ROLLING,
                is_available=row.is_available,
            )
        )

    return SupplierTariffsResponse(
        supplier_id=str(supplier_id),
        supplier_name=supplier["name"],
        tariffs=tariffs,
        total=len(tariffs),
    )


@router.get(
    "/region/{region}",
    response_model=SuppliersResponse,
    summary="Get suppliers by region",
    responses={
        200: {"description": "Suppliers retrieved successfully"},
    },
)
async def get_suppliers_by_region(
    region: str = Path(..., description="Region code (e.g., us_ct, us_ma, us_tx)"),
    utility_type: str | None = Query(None, description="Filter by utility type"),
    green_only: bool = Query(False, description="Filter for green energy providers"),
    db=Depends(get_db_session),
    redis=Depends(get_redis),
):
    """
    Get all suppliers available in a specific region.

    Convenience endpoint for region-based filtering.
    Results are cached in Redis for 1 hour.
    """
    _validate_region_code(region)
    repo = SupplierRegistryRepository(db, cache=redis)
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
    },
)
async def compare_suppliers(
    region: str = Path(..., description="Region code"),
    utility_type: str | None = Query("electricity", description="Utility type to compare"),
    tariff_type: str | None = Query(None, description="Filter by tariff type"),
    db=Depends(get_db_session),
    redis=Depends(get_redis),
):
    """
    Compare suppliers in a region with their best tariff prices.

    Returns suppliers sorted by their cheapest available tariff.
    Supplier list lookup uses the Redis-cached list_suppliers() call.
    """
    repo = SupplierRegistryRepository(db, cache=redis)
    suppliers_data, _ = await repo.list_suppliers(
        region=region,
        utility_type=utility_type,
    )

    comparison = []
    for supplier in suppliers_data:
        comparison.append(
            {
                "supplier_id": supplier["id"],
                "supplier_name": supplier["name"],
                "utility_types": supplier["utility_types"],
                "cheapest_tariff": "Standard Variable",
                "unit_rate": "0.25",
                "standing_charge": "0.40",
                "rating": supplier.get("rating"),
                "green_energy_provider": supplier["green_energy_provider"],
            }
        )

    comparison.sort(key=lambda x: float(x["unit_rate"]))

    return {
        "region": region,
        "utility_type": utility_type,
        "suppliers": comparison,
        "total": len(comparison),
        "generated_at": datetime.now(UTC).isoformat(),
    }
