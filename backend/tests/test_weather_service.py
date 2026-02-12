"""Tests for the Weather Service integration."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from integrations.weather_service import (
    WeatherData,
    WeatherForecast,
    WeatherService,
    CT_LAT,
    CT_LON,
    DEGREE_DAY_BASE_F,
)


class TestWeatherData:
    def test_heating_degree_hours_cold(self):
        """Below base temp should produce heating degrees."""
        w = WeatherData(
            timestamp=datetime.now(timezone.utc),
            temperature_f=30.0,
            humidity=60.0,
            wind_speed_mph=10.0,
            cloud_cover=50.0,
            feels_like_f=25.0,
            pressure_hpa=1013.0,
        )
        assert w.heating_degree_hours == 35.0  # 65 - 30
        assert w.cooling_degree_hours == 0.0

    def test_cooling_degree_hours_hot(self):
        """Above base temp should produce cooling degrees."""
        w = WeatherData(
            timestamp=datetime.now(timezone.utc),
            temperature_f=85.0,
            humidity=70.0,
            wind_speed_mph=5.0,
            cloud_cover=20.0,
            feels_like_f=90.0,
            pressure_hpa=1015.0,
        )
        assert w.heating_degree_hours == 0.0
        assert w.cooling_degree_hours == 20.0  # 85 - 65

    def test_no_degree_hours_at_base(self):
        """At base temp, both should be zero."""
        w = WeatherData(
            timestamp=datetime.now(timezone.utc),
            temperature_f=DEGREE_DAY_BASE_F,
            humidity=50.0,
            wind_speed_mph=5.0,
            cloud_cover=50.0,
            feels_like_f=65.0,
            pressure_hpa=1013.0,
        )
        assert w.heating_degree_hours == 0.0
        assert w.cooling_degree_hours == 0.0

    def test_to_feature_vector(self):
        w = WeatherData(
            timestamp=datetime.now(timezone.utc),
            temperature_f=50.0,
            humidity=60.0,
            wind_speed_mph=10.0,
            cloud_cover=40.0,
            feels_like_f=45.0,
            pressure_hpa=1013.0,
        )
        features = w.to_feature_vector()
        assert len(features) == 6
        assert features[0] == 50.0  # temp
        assert features[1] == 60.0  # humidity
        assert features[2] == 10.0  # wind
        assert features[3] == 40.0  # clouds
        assert features[4] == 15.0  # HDD (65-50)
        assert features[5] == 0.0   # CDD


class TestWeatherService:
    def setup_method(self):
        self.service = WeatherService(api_key="test-key")

    def test_parse_weather(self):
        data = {
            "dt": 1707696000,
            "main": {
                "temp": 45.0,
                "humidity": 65,
                "feels_like": 40.0,
                "pressure": 1020,
            },
            "wind": {"speed": 12.0},
            "clouds": {"all": 75},
        }
        result = self.service._parse_weather(data)
        assert result.temperature_f == 45.0
        assert result.humidity == 65
        assert result.wind_speed_mph == 12.0
        assert result.cloud_cover == 75
        assert result.feels_like_f == 40.0

    def test_default_coordinates(self):
        """Verify Connecticut coordinates are set."""
        assert CT_LAT == pytest.approx(41.3083, abs=0.01)
        assert CT_LON == pytest.approx(-72.9279, abs=0.01)
