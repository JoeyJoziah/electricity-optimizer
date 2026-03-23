"""Tests for the Weather Service integration."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from integrations.weather_service import (
    CT_LAT,
    CT_LON,
    DEGREE_DAY_BASE_F,
    CircuitState,
    WeatherCircuitBreaker,
    WeatherData,
    WeatherService,
)


class TestWeatherData:
    def test_heating_degree_hours_cold(self):
        """Below base temp should produce heating degrees."""
        w = WeatherData(
            timestamp=datetime.now(UTC),
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
            timestamp=datetime.now(UTC),
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
            timestamp=datetime.now(UTC),
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
            timestamp=datetime.now(UTC),
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
        assert features[5] == 0.0  # CDD


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
        assert pytest.approx(41.3083, abs=0.01) == CT_LAT
        assert pytest.approx(-72.9279, abs=0.01) == CT_LON


class TestWeatherCircuitBreaker:
    """Tests for the weather service circuit breaker."""

    async def test_starts_closed(self):
        cb = WeatherCircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert await cb.can_execute() is True

    async def test_opens_after_threshold_failures(self):
        cb = WeatherCircuitBreaker(failure_threshold=3)
        for _ in range(3):
            await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert await cb.can_execute() is False

    async def test_stays_closed_below_threshold(self):
        cb = WeatherCircuitBreaker(failure_threshold=5)
        for _ in range(4):
            await cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert await cb.can_execute() is True

    async def test_transitions_to_half_open_after_timeout(self):
        cb = WeatherCircuitBreaker(failure_threshold=2, timeout_seconds=60)
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Simulate timeout elapsed
        cb._last_failure_time = datetime.now(UTC) - timedelta(seconds=61)
        assert cb.state == CircuitState.HALF_OPEN
        assert await cb.can_execute() is True

    async def test_closes_after_success_threshold_in_half_open(self):
        cb = WeatherCircuitBreaker(failure_threshold=2, timeout_seconds=0, success_threshold=2)
        await cb.record_failure()
        await cb.record_failure()
        # timeout_seconds=0 so it immediately becomes HALF_OPEN
        cb._last_failure_time = datetime.now(UTC) - timedelta(seconds=1)
        assert cb.state == CircuitState.HALF_OPEN

        await cb.record_success()
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED

    async def test_reopens_on_failure_in_half_open(self):
        cb = WeatherCircuitBreaker(failure_threshold=2, timeout_seconds=0)
        await cb.record_failure()
        await cb.record_failure()
        cb._last_failure_time = datetime.now(UTC) - timedelta(seconds=1)
        assert cb.state == CircuitState.HALF_OPEN

        await cb.record_failure()
        assert cb._state == CircuitState.OPEN

    async def test_success_resets_failure_count_when_closed(self):
        cb = WeatherCircuitBreaker(failure_threshold=5)
        for _ in range(4):
            await cb.record_failure()
        await cb.record_success()
        assert cb._failure_count == 0


class TestWeatherServiceCircuitBreaker:
    """Tests for circuit breaker integration in WeatherService."""

    def setup_method(self):
        self.service = WeatherService(api_key="test-key")

    async def test_get_current_returns_none_when_circuit_open(self):
        """When circuit is open, get_current should return None."""
        # Force circuit open
        for _ in range(5):
            await self.service._circuit_breaker.record_failure()
        assert self.service._circuit_breaker.state == CircuitState.OPEN

        result = await self.service.get_current()
        assert result is None

    async def test_get_forecast_returns_none_when_circuit_open(self):
        """When circuit is open, get_forecast_48h should return None."""
        for _ in range(5):
            await self.service._circuit_breaker.record_failure()

        result = await self.service.get_forecast_48h()
        assert result is None

    async def test_get_features_returns_none_when_circuit_open(self):
        """When circuit is open, get_features_for_forecast should return None."""
        for _ in range(5):
            await self.service._circuit_breaker.record_failure()

        result = await self.service.get_features_for_forecast()
        assert result is None

    async def test_get_current_returns_none_on_http_error(self):
        """HTTP errors should return None and record failure."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=MagicMock(status_code=500)
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        self.service._client = mock_client

        result = await self.service.get_current()
        assert result is None
        assert self.service._circuit_breaker._failure_count == 1

    async def test_successful_call_records_success(self):
        """Successful API call should record success on circuit breaker."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "dt": 1707696000,
            "main": {"temp": 45.0, "humidity": 65, "feels_like": 40.0, "pressure": 1020},
            "wind": {"speed": 12.0},
            "clouds": {"all": 75},
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        self.service._client = mock_client

        result = await self.service.get_current()
        assert result is not None
        assert result.temperature_f == 45.0
        assert self.service._circuit_breaker._failure_count == 0
