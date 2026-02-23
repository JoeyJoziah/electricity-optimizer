"""
Utility Type Models

Shared enums and models for multi-utility support across
electricity, natural gas, heating oil, propane, and community solar.
"""

from enum import Enum


class UtilityType(str, Enum):
    """Types of utilities supported by the platform"""
    ELECTRICITY = "electricity"
    NATURAL_GAS = "natural_gas"
    HEATING_OIL = "heating_oil"
    PROPANE = "propane"
    COMMUNITY_SOLAR = "community_solar"


class PriceUnit(str, Enum):
    """
    Canonical price unit enum — single source of truth.

    All modules must import PriceUnit from here. The lowercase values are
    used for storage and internal comparison; display labels are in UNIT_LABELS.
    """
    # Electricity
    KWH = "kwh"           # kilowatt-hour (electricity)
    MWH = "mwh"           # megawatt-hour (wholesale electricity)
    CENTS_KWH = "cents_kwh"  # cents per kWh (EIA format)

    # Currency-qualified electricity (international APIs)
    GBP_KWH = "gbp_kwh"  # GBP per kWh (UK)
    EUR_KWH = "eur_kwh"  # EUR per kWh (EU)
    USD_KWH = "usd_kwh"  # USD per kWh (US explicit)

    # Natural gas
    THERM = "therm"       # 100,000 BTU (residential gas)
    MCF = "mcf"           # 1,000 cubic feet (gas)
    MMBTU = "mmbtu"       # million BTU (wholesale gas)
    CCF = "ccf"           # 100 cubic feet (gas utility billing)

    # Heating oil & propane
    GALLON = "gallon"     # gallon (heating oil, propane)

    # Community solar
    CREDIT_KWH = "credit_kwh"  # solar credit per kWh


# Default units per utility type
UTILITY_DEFAULT_UNITS: dict[UtilityType, PriceUnit] = {
    UtilityType.ELECTRICITY: PriceUnit.KWH,
    UtilityType.NATURAL_GAS: PriceUnit.THERM,
    UtilityType.HEATING_OIL: PriceUnit.GALLON,
    UtilityType.PROPANE: PriceUnit.GALLON,
    UtilityType.COMMUNITY_SOLAR: PriceUnit.CREDIT_KWH,
}

# Display labels
UTILITY_LABELS: dict[UtilityType, str] = {
    UtilityType.ELECTRICITY: "Electricity",
    UtilityType.NATURAL_GAS: "Natural Gas",
    UtilityType.HEATING_OIL: "Heating Oil",
    UtilityType.PROPANE: "Propane",
    UtilityType.COMMUNITY_SOLAR: "Community Solar",
}

UNIT_LABELS: dict[PriceUnit, str] = {
    PriceUnit.KWH: "$/kWh",
    PriceUnit.MWH: "$/MWh",
    PriceUnit.CENTS_KWH: "cents/kWh",
    PriceUnit.GBP_KWH: "GBP/kWh",
    PriceUnit.EUR_KWH: "EUR/kWh",
    PriceUnit.USD_KWH: "USD/kWh",
    PriceUnit.THERM: "$/therm",
    PriceUnit.MCF: "$/Mcf",
    PriceUnit.MMBTU: "$/MMBtu",
    PriceUnit.CCF: "$/Ccf",
    PriceUnit.GALLON: "$/gallon",
    PriceUnit.CREDIT_KWH: "$/kWh credit",
}
