"""
Tests for services.weather_service.WeatherService (OpenWeather v2.5).

All HTTP is mocked at ``httpx.AsyncClient`` — no network calls are made.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.weather_service import OWM_BASE_URL, STATE_COORDS, WeatherService

API_KEY = "test-owm-key"

CURRENT_PAYLOAD = {
    "main": {"temp": 71.5, "humidity": 40},
    "clouds": {"all": 20},
    "wind": {"speed": 6.2},
    "weather": [{"description": "few clouds"}],
    "name": "ignored extra field",
}

FORECAST_PAYLOAD = {
    "list": [
        {
            "dt": 1_800_000_000,
            "main": {"temp": 60.0, "humidity": 55},
            "clouds": {"all": 75},
            "wind": {"speed": 9.0},
        },
        {
            "dt": 1_800_010_800,
            "main": {"temp": 58.5, "humidity": 60},
            "clouds": {"all": 90},
            "wind": {"speed": 11.5},
        },
    ]
}


def _service(api_key: str | None = API_KEY) -> WeatherService:
    return WeatherService(settings=SimpleNamespace(openweathermap_api_key=api_key))


def _response(payload: dict, *, raise_exc: Exception | None = None) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock(side_effect=raise_exc)
    return resp


def _patch_client(response: MagicMock):
    """Patch httpx.AsyncClient in the service; returns (patcher, client mock)."""
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    patcher = patch("services.weather_service.httpx.AsyncClient", return_value=cm)
    return patcher, client


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", f"{OWM_BASE_URL}/weather")
    return httpx.HTTPStatusError(
        f"{status_code}", request=request, response=httpx.Response(status_code, request=request)
    )


class TestStateCoords:
    def test_covers_fifty_states_and_dc(self):
        assert len(STATE_COORDS) == 51
        assert "DC" in STATE_COORDS

    def test_coordinates_are_plausible_us_lat_lon(self):
        for state, (lat, lon) in STATE_COORDS.items():
            assert 18 < lat < 72, state
            assert -180 < lon < -66, state


class TestInit:
    def test_uses_injected_settings(self):
        assert _service("abc")._api_key == "abc"

    def test_falls_back_to_get_settings(self):
        fake = SimpleNamespace(openweathermap_api_key="from-settings")
        with patch("services.weather_service.get_settings", return_value=fake):
            assert WeatherService()._api_key == "from-settings"


class TestGetCurrentWeather:
    @pytest.mark.asyncio
    async def test_returns_none_without_api_key_and_makes_no_call(self):
        patcher, client = _patch_client(_response(CURRENT_PAYLOAD))
        with patcher as client_cls:
            result = await _service(None).get_current_weather(41.764, -72.682)

        assert result is None
        client_cls.assert_not_called()
        client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_maps_response_to_normalised_dict(self):
        patcher, _ = _patch_client(_response(CURRENT_PAYLOAD))
        with patcher:
            result = await _service().get_current_weather(41.764, -72.682)

        assert result == {
            "temp_f": 71.5,
            "humidity": 40,
            "clouds_pct": 20,
            "wind_mph": 6.2,
            "description": "few clouds",
        }

    @pytest.mark.asyncio
    async def test_calls_weather_endpoint_with_imperial_units_and_timeout(self):
        patcher, client = _patch_client(_response(CURRENT_PAYLOAD))
        with patcher as client_cls:
            await _service().get_current_weather(41.764, -72.682)

        client_cls.assert_called_once_with(timeout=10.0)
        client.get.assert_awaited_once_with(
            f"{OWM_BASE_URL}/weather",
            params={"lat": 41.764, "lon": -72.682, "appid": API_KEY, "units": "imperial"},
        )

    @pytest.mark.asyncio
    async def test_http_error_propagates(self):
        patcher, _ = _patch_client(_response({}, raise_exc=_http_error(401)))
        with patcher, pytest.raises(httpx.HTTPStatusError):
            await _service().get_current_weather(41.764, -72.682)

    @pytest.mark.asyncio
    async def test_malformed_payload_raises_rather_than_inventing_values(self):
        patcher, _ = _patch_client(_response({"main": {"temp": 70.0}}))
        with patcher, pytest.raises(KeyError):
            await _service().get_current_weather(41.764, -72.682)


class TestGetForecast5Day:
    @pytest.mark.asyncio
    async def test_returns_none_without_api_key(self):
        patcher, client = _patch_client(_response(FORECAST_PAYLOAD))
        with patcher:
            assert await _service("").get_forecast_5day(30.275, -97.740) is None
        client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_maps_each_entry_in_order(self):
        patcher, client = _patch_client(_response(FORECAST_PAYLOAD))
        with patcher:
            result = await _service().get_forecast_5day(30.275, -97.740)

        assert result == [
            {
                "dt": 1_800_000_000,
                "temp_f": 60.0,
                "humidity": 55,
                "clouds_pct": 75,
                "wind_mph": 9.0,
            },
            {
                "dt": 1_800_010_800,
                "temp_f": 58.5,
                "humidity": 60,
                "clouds_pct": 90,
                "wind_mph": 11.5,
            },
        ]
        client.get.assert_awaited_once_with(
            f"{OWM_BASE_URL}/forecast",
            params={"lat": 30.275, "lon": -97.740, "appid": API_KEY, "units": "imperial"},
        )

    @pytest.mark.asyncio
    async def test_empty_forecast_list_returns_empty_list(self):
        patcher, _ = _patch_client(_response({"list": []}))
        with patcher:
            assert await _service().get_forecast_5day(30.275, -97.740) == []

    @pytest.mark.asyncio
    async def test_http_error_propagates(self):
        patcher, _ = _patch_client(_response({}, raise_exc=_http_error(429)))
        with patcher, pytest.raises(httpx.HTTPStatusError):
            await _service().get_forecast_5day(30.275, -97.740)


class TestFetchWeatherForRegions:
    @pytest.mark.asyncio
    async def test_fetches_each_known_region_by_its_coordinates(self):
        svc = _service()
        svc.get_current_weather = AsyncMock(
            side_effect=lambda lat, lon: {"temp_f": lat, "wind_mph": lon}
        )

        result = await svc.fetch_weather_for_regions(["CT", "TX"])

        assert result == {
            "CT": {"temp_f": STATE_COORDS["CT"][0], "wind_mph": STATE_COORDS["CT"][1]},
            "TX": {"temp_f": STATE_COORDS["TX"][0], "wind_mph": STATE_COORDS["TX"][1]},
        }
        assert svc.get_current_weather.await_count == 2

    @pytest.mark.asyncio
    async def test_unknown_region_is_skipped_without_a_call(self):
        svc = _service()
        svc.get_current_weather = AsyncMock(return_value={"temp_f": 50.0})

        result = await svc.fetch_weather_for_regions(["ZZ", "us_ct", "NY"])

        assert result == {"NY": {"temp_f": 50.0}}
        svc.get_current_weather.assert_awaited_once_with(*STATE_COORDS["NY"])

    @pytest.mark.asyncio
    async def test_one_failing_region_does_not_fail_the_batch(self):
        svc = _service()

        async def _weather(lat, lon):
            if (lat, lon) == STATE_COORDS["TX"]:
                raise httpx.ConnectTimeout("timed out")
            return {"temp_f": 65.0}

        svc.get_current_weather = AsyncMock(side_effect=_weather)

        with patch("services.weather_service.logger") as mock_logger:
            result = await svc.fetch_weather_for_regions(["CT", "TX", "NY"])

        assert result == {"CT": {"temp_f": 65.0}, "NY": {"temp_f": 65.0}}
        mock_logger.warning.assert_called_once()
        args, kwargs = mock_logger.warning.call_args
        assert args[0] == "weather_fetch_failed"
        assert kwargs["region"] == "TX"

    @pytest.mark.asyncio
    async def test_regions_without_data_are_omitted(self):
        # No API key -> get_current_weather returns None for every region.
        result = await _service(None).fetch_weather_for_regions(["CT", "TX"])
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_region_list(self):
        assert await _service().fetch_weather_for_regions([]) == {}

    @pytest.mark.asyncio
    async def test_at_most_ten_calls_run_concurrently(self):
        import asyncio

        svc = _service()
        running = 0
        peak = 0

        async def _weather(lat, lon):
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            running -= 1
            return {"temp_f": 1.0}

        svc.get_current_weather = AsyncMock(side_effect=_weather)

        result = await svc.fetch_weather_for_regions(list(STATE_COORDS))

        assert len(result) == 51
        assert peak == 10
