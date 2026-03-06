"""
Address-to-region resolution via Google Geocoding API.

Free tier: 10,000 geocodes/month. Card required but $0 budget alert recommended.
"""

from typing import Optional

import httpx
import structlog

from config.settings import get_settings

logger = structlog.get_logger(__name__)

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

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


class GeocodingService:
    def __init__(self, settings=None):
        self._settings = settings or get_settings()
        self._api_key = self._settings.google_maps_api_key

    async def address_to_region(self, address: str) -> Optional[str]:
        """Resolve a US address to a two-letter state abbreviation.

        Uses 1 geocoding credit. Free tier: 10,000/month.
        """
        if not self._api_key:
            return None
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                GEOCODE_URL,
                params={"address": address, "key": self._api_key},
            )
            resp.raise_for_status()
            data = resp.json()

        if data["status"] != "OK" or not data["results"]:
            return None

        # Extract state from address components
        for component in data["results"][0].get("address_components", []):
            if "administrative_area_level_1" in component.get("types", []):
                abbr = component.get("short_name", "")
                if abbr in _US_STATES:
                    return abbr
        return None

    async def geocode(self, address: str) -> Optional[dict]:
        """Full geocode returning lat/lng and state abbreviation."""
        if not self._api_key:
            return None
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                GEOCODE_URL,
                params={"address": address, "key": self._api_key},
            )
            resp.raise_for_status()
            data = resp.json()

        if data["status"] != "OK" or not data["results"]:
            return None

        result = data["results"][0]
        location = result["geometry"]["location"]
        state = None
        for component in result.get("address_components", []):
            if "administrative_area_level_1" in component.get("types", []):
                abbr = component.get("short_name", "")
                if abbr in _US_STATES:
                    state = abbr
                    break

        return {
            "lat": location["lat"],
            "lng": location["lng"],
            "state": state,
            "formatted_address": result.get("formatted_address"),
        }
