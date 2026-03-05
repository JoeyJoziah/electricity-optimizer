"""
Weather data for ML feature enrichment via OpenWeather v2.5 (free, no card).

Free tier: 1,000 calls/day. Commercial use OK.
"""

import asyncio

import httpx
import structlog
from typing import Optional

from config.settings import get_settings

logger = structlog.get_logger(__name__)

OWM_BASE_URL = "https://api.openweathermap.org/data/2.5"

# US state capital coordinates for weather lookups
STATE_COORDS: dict[str, tuple[float, float]] = {
    "AL": (32.377, -86.300),
    "AK": (58.302, -134.420),
    "AZ": (33.449, -112.074),
    "AR": (34.747, -92.290),
    "CA": (38.576, -121.494),
    "CO": (39.739, -104.985),
    "CT": (41.764, -72.682),
    "DE": (39.157, -75.520),
    "DC": (38.907, -77.037),
    "FL": (30.438, -84.281),
    "GA": (33.749, -84.388),
    "HI": (21.307, -157.858),
    "ID": (43.615, -116.202),
    "IL": (39.798, -89.654),
    "IN": (39.768, -86.162),
    "IA": (41.591, -93.604),
    "KS": (39.048, -95.678),
    "KY": (38.187, -84.875),
    "LA": (30.451, -91.187),
    "ME": (44.307, -69.782),
    "MD": (38.979, -76.491),
    "MA": (42.358, -71.064),
    "MI": (42.733, -84.555),
    "MN": (44.955, -93.102),
    "MS": (32.303, -90.182),
    "MO": (38.579, -92.173),
    "MT": (46.586, -112.018),
    "NE": (40.808, -96.700),
    "NV": (39.164, -119.766),
    "NH": (43.207, -71.538),
    "NJ": (40.221, -74.756),
    "NM": (35.682, -105.940),
    "NY": (42.653, -73.757),
    "NC": (35.780, -78.639),
    "ND": (46.813, -100.779),
    "OH": (39.962, -82.999),
    "OK": (35.482, -97.535),
    "OR": (44.938, -123.030),
    "PA": (40.264, -76.884),
    "RI": (41.824, -71.413),
    "SC": (34.000, -81.035),
    "SD": (44.368, -100.350),
    "TN": (36.166, -86.784),
    "TX": (30.275, -97.740),
    "UT": (40.758, -111.876),
    "VT": (44.260, -72.576),
    "VA": (37.541, -77.434),
    "WA": (47.038, -122.893),
    "WV": (38.336, -81.612),
    "WI": (43.075, -89.384),
    "WY": (41.140, -104.820),
}


class WeatherService:
    def __init__(self, settings=None):
        self._settings = settings or get_settings()
        self._api_key = self._settings.openweathermap_api_key

    async def get_current_weather(
        self, lat: float, lon: float
    ) -> Optional[dict]:
        """Fetch current weather. 1 API call."""
        if not self._api_key:
            return None
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{OWM_BASE_URL}/weather",
                params={
                    "lat": lat,
                    "lon": lon,
                    "appid": self._api_key,
                    "units": "imperial",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "temp_f": data["main"]["temp"],
                "humidity": data["main"]["humidity"],
                "clouds_pct": data["clouds"]["all"],
                "wind_mph": data["wind"]["speed"],
                "description": data["weather"][0]["description"],
            }

    async def get_forecast_5day(
        self, lat: float, lon: float
    ) -> Optional[list]:
        """Fetch 5-day/3-hour forecast. 1 API call."""
        if not self._api_key:
            return None
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{OWM_BASE_URL}/forecast",
                params={
                    "lat": lat,
                    "lon": lon,
                    "appid": self._api_key,
                    "units": "imperial",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "dt": entry["dt"],
                    "temp_f": entry["main"]["temp"],
                    "humidity": entry["main"]["humidity"],
                    "clouds_pct": entry["clouds"]["all"],
                    "wind_mph": entry["wind"]["speed"],
                }
                for entry in data["list"]
            ]

    async def fetch_weather_for_regions(
        self, regions: list[str]
    ) -> dict[str, dict]:
        """Fetch current weather for multiple US state regions.

        Budget: 1 call per region. 51 regions = 51 calls/day (5.1% of daily limit).
        """
        results: dict[str, dict] = {}
        for region in regions:
            coords = STATE_COORDS.get(region)
            if not coords:
                continue
            try:
                weather = await self.get_current_weather(*coords)
                if weather:
                    results[region] = weather
            except Exception as e:
                logger.warning(
                    "weather_fetch_failed", region=region, error=str(e)
                )
            await asyncio.sleep(0.1)  # Gentle throttle
        return results
