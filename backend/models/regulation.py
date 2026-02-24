"""
State Regulation Models

Pydantic models for the state_regulations table — deregulation status,
PUC information, and compliance data for all 50 states + DC.
"""

from typing import Optional
from pydantic import BaseModel, Field


class StateRegulation(BaseModel):
    """State-level energy regulation data."""
    state_code: str = Field(..., description="Two-letter state code (e.g. CT, TX)")
    state_name: str = Field(..., description="Full state name")
    electricity_deregulated: bool = Field(default=False)
    gas_deregulated: bool = Field(default=False)
    oil_competitive: bool = Field(default=False)
    community_solar_enabled: bool = Field(default=False)
    licensing_required: bool = Field(default=False)
    bond_required: bool = Field(default=False)
    bond_amount: Optional[float] = None
    puc_name: Optional[str] = Field(None, description="Public Utility Commission name")
    puc_website: Optional[str] = None
    comparison_tool_url: Optional[str] = None
    notes: Optional[str] = None


class StateRegulationResponse(StateRegulation):
    """API response for a single state's regulation data."""
    pass


class StateRegulationListResponse(BaseModel):
    """API response for list of state regulations."""
    states: list[StateRegulationResponse]
    total: int
