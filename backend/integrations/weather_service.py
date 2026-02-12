"""
OpenWeatherMap Integration for Weather-Aware Price Forecasting

Provides weather data that correlates with electricity demand:
- Temperature (heating/cooling demand driver)
- Humidity (AC load factor)
- Wind speed (renewable generation indicator)
- Cloud cover (solar generation indicator)

Free tier: 1,000 calls/day (plenty for 6-hour price refresh cycle)
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Connecticut coordinates (New Haven as representative)
CT_LAT = 41.3083
CT_LON = -72.9279

# Reference temperature for degree day calculations (65F / 18.3C)
DEGREE_DAY_BASE_F = 65.0


@dataclass
class WeatherData:
    """Normalized weather observation."""

    timestamp: datetime
    temperature_f: float
    humidity: float  # 0-100 percentage
    wind_speed_mph: float
    cloud_cover: float  # 0-100 percentage
    feels_like_f: float
    pressure_hpa: float

    @property
    def heating_degree_hours(self) -> float:
        """HDD contribution: how much heating is needed this hour."""
        return max(0.0, DEGREE_DAY_BASE_F - self.temperature_f)

    @property
    def cooling_degree_hours(self) -> float:
        """CDD contribution: how much cooling is needed this hour."""
        return max(0.0, self.temperature_f - DEGREE_DAY_BASE_F)

    def to_feature_vector(self) -> List[float]:
        """Convert to ML feature vector [temp, humidity, wind, clouds]."""
        return [
            self.temperature_f,
            self.humidity,
            self.wind_speed_mph,
            self.cloud_cover,
            self.heating_degree_hours,
            self.cooling_degree_hours,
        ]


@dataclass
class WeatherForecast:
    """Multi-hour weather forecast."""

    location: str
    generated_at: datetime
    hourly: List[WeatherData]


class WeatherService:
    """
    Async client for OpenWeatherMap API.

    Usage:
        service = WeatherService(api_key="your-key")
        current = await service.get_current(lat=41.31, lon=-72.93)
        forecast = await service.get_forecast_48h(lat=41.31, lon=-72.93)
    """

    BASE_URL = "https://api.openweathermap.org/data/2.5"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=httpx.Timeout(15.0),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    def _parse_weather(self, data: dict) -> WeatherData:
        """Parse OWM response into WeatherData."""
        main = data.get("main", {})
        wind = data.get("wind", {})
        clouds = data.get("clouds", {})

        # OWM returns Kelvin by default; request imperial for Fahrenheit
        return WeatherData(
            timestamp=datetime.fromtimestamp(data.get("dt", 0), tz=timezone.utc),
            temperature_f=main.get("temp", 0),
            humidity=main.get("humidity", 0),
            wind_speed_mph=wind.get("speed", 0),
            cloud_cover=clouds.get("all", 0),
            feels_like_f=main.get("feels_like", 0),
            pressure_hpa=main.get("pressure", 0),
        )

    async def get_current(
        self,
        lat: float = CT_LAT,
        lon: float = CT_LON,
    ) -> WeatherData:
        """
        Get current weather for a location.

        Args:
            lat: Latitude (default: Connecticut)
            lon: Longitude (default: Connecticut)

        Returns:
            Current weather data
        """
        client = await self._get_client()
        response = await client.get(
            "/weather",
            params={
                "lat": lat,
                "lon": lon,
                "appid": self._api_key,
                "units": "imperial",
            },
        )
        response.raise_for_status()
        return self._parse_weather(response.json())

    async def get_forecast_48h(
        self,
        lat: float = CT_LAT,
        lon: float = CT_LON,
    ) -> WeatherForecast:
        """
        Get 48-hour weather forecast (3-hour intervals from free tier).

        Args:
            lat: Latitude (default: Connecticut)
            lon: Longitude (default: Connecticut)

        Returns:
            WeatherForecast with hourly data points
        """
        client = await self._get_client()
        response = await client.get(
            "/forecast",
            params={
                "lat": lat,
                "lon": lon,
                "appid": self._api_key,
                "units": "imperial",
                "cnt": 16,  # 16 x 3h = 48 hours
            },
        )
        response.raise_for_status()

        data = response.json()
        hourly = [self._parse_weather(item) for item in data.get("list", [])]

        return WeatherForecast(
            location=data.get("city", {}).get("name", "Unknown"),
            generated_at=datetime.now(timezone.utc),
            hourly=hourly,
        )

    async def get_features_for_forecast(
        self,
        lat: float = CT_LAT,
        lon: float = CT_LON,
    ) -> Dict[str, List[float]]:
        """
        Get weather features formatted for the ML model.

        Returns dict with keys matching new model features:
        - temperature, humidity, wind_speed, cloud_cover
        - heating_degree_hours, cooling_degree_hours

        Each value is a list of floats (one per forecast hour).
        """
        forecast = await self.get_forecast_48h(lat, lon)

        features: Dict[str, List[float]] = {
            "temperature": [],
            "humidity": [],
            "wind_speed": [],
            "cloud_cover": [],
            "heating_degree_hours": [],
            "cooling_degree_hours": [],
        }

        for w in forecast.hourly:
            features["temperature"].append(w.temperature_f)
            features["humidity"].append(w.humidity)
            features["wind_speed"].append(w.wind_speed_mph)
            features["cloud_cover"].append(w.cloud_cover)
            features["heating_degree_hours"].append(w.heating_degree_hours)
            features["cooling_degree_hours"].append(w.cooling_degree_hours)

        return features
