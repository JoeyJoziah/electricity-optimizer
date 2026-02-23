"""
Region Models

Single source of truth for all supported pricing regions.
Replaces the duplicate PricingRegion (base.py) and PriceRegion (price.py) enums.
"""

from enum import Enum


class Region(str, Enum):
    """
    Supported pricing regions.

    US states use 'us_XX' format. International regions use ISO codes.
    This enum is the single source of truth -- both the pricing API layer
    and the Pydantic models reference it.
    """

    # US States (all 50 + DC)
    US_AL = "us_al"  # Alabama
    US_AK = "us_ak"  # Alaska
    US_AZ = "us_az"  # Arizona
    US_AR = "us_ar"  # Arkansas
    US_CA = "us_ca"  # California
    US_CO = "us_co"  # Colorado
    US_CT = "us_ct"  # Connecticut
    US_DE = "us_de"  # Delaware
    US_DC = "us_dc"  # District of Columbia
    US_FL = "us_fl"  # Florida
    US_GA = "us_ga"  # Georgia
    US_HI = "us_hi"  # Hawaii
    US_ID = "us_id"  # Idaho
    US_IL = "us_il"  # Illinois
    US_IN = "us_in"  # Indiana
    US_IA = "us_ia"  # Iowa
    US_KS = "us_ks"  # Kansas
    US_KY = "us_ky"  # Kentucky
    US_LA = "us_la"  # Louisiana
    US_ME = "us_me"  # Maine
    US_MD = "us_md"  # Maryland
    US_MA = "us_ma"  # Massachusetts
    US_MI = "us_mi"  # Michigan
    US_MN = "us_mn"  # Minnesota
    US_MS = "us_ms"  # Mississippi
    US_MO = "us_mo"  # Missouri
    US_MT = "us_mt"  # Montana
    US_NE = "us_ne"  # Nebraska
    US_NV = "us_nv"  # Nevada
    US_NH = "us_nh"  # New Hampshire
    US_NJ = "us_nj"  # New Jersey
    US_NM = "us_nm"  # New Mexico
    US_NY = "us_ny"  # New York
    US_NC = "us_nc"  # North Carolina
    US_ND = "us_nd"  # North Dakota
    US_OH = "us_oh"  # Ohio
    US_OK = "us_ok"  # Oklahoma
    US_OR = "us_or"  # Oregon
    US_PA = "us_pa"  # Pennsylvania
    US_RI = "us_ri"  # Rhode Island
    US_SC = "us_sc"  # South Carolina
    US_SD = "us_sd"  # South Dakota
    US_TN = "us_tn"  # Tennessee
    US_TX = "us_tx"  # Texas
    US_UT = "us_ut"  # Utah
    US_VT = "us_vt"  # Vermont
    US_VA = "us_va"  # Virginia
    US_WA = "us_wa"  # Washington
    US_WV = "us_wv"  # West Virginia
    US_WI = "us_wi"  # Wisconsin
    US_WY = "us_wy"  # Wyoming

    # International
    UK = "uk"
    UK_SCOTLAND = "uk_scotland"
    UK_WALES = "uk_wales"
    IRELAND = "ie"
    GERMANY = "de"
    FRANCE = "fr"
    SPAIN = "es"
    ITALY = "it"
    NETHERLANDS = "nl"
    BELGIUM = "be"
    AUSTRIA = "at"
    JAPAN = "jp"
    AUSTRALIA = "au"
    CANADA = "ca"
    CHINA = "cn"
    INDIA = "in"
    BRAZIL = "br"

    @property
    def is_us(self) -> bool:
        """Check if this is a US region"""
        return self.value.startswith("us_")

    @property
    def state_code(self) -> str | None:
        """Extract 2-letter state code for US regions, or None"""
        if self.is_us:
            return self.value[3:].upper()
        return None

    @classmethod
    def from_state_code(cls, code: str) -> "Region":
        """Create a Region from a 2-letter US state code"""
        return cls(f"us_{code.lower()}")

    @classmethod
    def us_regions(cls) -> list["Region"]:
        """Get all US regions"""
        return [r for r in cls if r.is_us]


# Backward-compatible aliases
PriceRegion = Region
PricingRegion = Region


# States with deregulated electricity
DEREGULATED_ELECTRICITY_STATES: set[str] = {
    "CT", "TX", "OH", "PA", "IL", "NY", "NJ", "MA", "MD", "RI",
    "NH", "ME", "DE", "MI", "VA", "DC", "OR", "MT",
}

# States with deregulated natural gas
DEREGULATED_GAS_STATES: set[str] = {
    "CT", "OH", "PA", "IL", "NY", "NJ", "MA", "MD", "RI", "DE",
    "MI", "DC", "GA", "IN", "KY", "FL",
}

# States with significant heating oil markets
HEATING_OIL_STATES: set[str] = {
    "CT", "MA", "NY", "NJ", "PA", "ME", "NH", "VT", "RI",
}

# States with community solar programs
COMMUNITY_SOLAR_STATES: set[str] = {
    "CT", "NY", "MA", "IL", "MN", "FL", "NJ", "MD", "ME",
    "CO", "CA", "OR", "HI", "SC", "NM", "AZ", "VA", "DE",
    "VT", "RI", "WI", "NV", "UT", "WA", "DC", "NC", "OH", "PA",
}
