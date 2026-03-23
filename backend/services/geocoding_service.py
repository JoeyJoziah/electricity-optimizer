"""
Address-to-region resolution via OpenWeatherMap Geocoding + Nominatim fallback.

Primary: OpenWeatherMap /geo/1.0/direct (uses existing API key, 1 call per request).
Fallback: Nominatim / OpenStreetMap (free, no key required, 1 req/s policy).
"""

import httpx
import structlog

from config.settings import get_settings

logger = structlog.get_logger(__name__)

OWM_GEOCODE_URL = "https://api.openweathermap.org/geo/1.0/direct"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Two-letter state abbreviations
_US_STATES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "DC",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
}

# OWM returns full state names — map to 2-letter abbreviations
_STATE_NAME_TO_ABBR: dict[str, str] = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "District of Columbia": "DC",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}


class GeocodingService:
    def __init__(self, settings=None):
        self._settings = settings or get_settings()
        self._owm_key = self._settings.openweathermap_api_key

    async def geocode(self, address: str) -> dict | None:
        """Full geocode returning lat/lng and state abbreviation.

        Tries OpenWeatherMap first, falls back to Nominatim on failure.
        """
        result = await self._geocode_owm(address)
        if result:
            return result

        result = await self._geocode_nominatim(address)
        if result:
            return result

        return None

    async def address_to_region(self, address: str) -> str | None:
        """Resolve a US address to a two-letter state abbreviation."""
        result = await self.geocode(address)
        if result and result.get("state") in _US_STATES:
            return result["state"]
        return None

    async def _geocode_owm(self, address: str) -> dict | None:
        """Geocode via OpenWeatherMap /geo/1.0/direct."""
        if not self._owm_key:
            logger.debug("geocode_owm_skip", reason="no API key")
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    OWM_GEOCODE_URL,
                    params={"q": address, "limit": 1, "appid": self._owm_key},
                )
                resp.raise_for_status()
                data = resp.json()

            if not data:
                return None

            item = data[0]
            state_name = item.get("state", "")
            state_abbr = _STATE_NAME_TO_ABBR.get(state_name)
            country = item.get("country", "")

            return {
                "lat": item["lat"],
                "lng": item["lon"],
                "state": state_abbr,
                "formatted_address": f"{item.get('name', '')}, {state_name}, {country}".strip(", "),
            }
        except Exception as e:
            logger.warning("geocode_owm_failed", error=str(e))
            return None

    async def _geocode_nominatim(self, address: str) -> dict | None:
        """Geocode via Nominatim (OpenStreetMap) — free, no API key."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    NOMINATIM_URL,
                    params={
                        "q": address,
                        "format": "json",
                        "addressdetails": 1,
                        "limit": 1,
                    },
                    headers={"User-Agent": "RateShift/1.0"},
                )
                resp.raise_for_status()
                data = resp.json()

            if not data:
                return None

            item = data[0]
            addr = item.get("address", {})
            country_code = addr.get("country_code", "")

            # Extract state abbreviation from ISO3166-2 (e.g. "US-CA" -> "CA")
            state_abbr = None
            iso_code = addr.get("ISO3166-2-lvl4", "")
            if iso_code and "-" in iso_code:
                candidate = iso_code.split("-", 1)[1]
                if candidate in _US_STATES:
                    state_abbr = candidate

            return {
                "lat": float(item["lat"]),
                "lng": float(item["lon"]),
                "state": state_abbr if country_code == "us" else None,
                "formatted_address": item.get("display_name", ""),
            }
        except Exception as e:
            logger.warning("geocode_nominatim_failed", error=str(e))
            return None
