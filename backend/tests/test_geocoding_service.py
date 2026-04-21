"""Tests for the Geocoding Service (OWM + Nominatim)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from services.geocoding_service import (_STATE_NAME_TO_ABBR, _US_STATES,
                                        GeocodingService)


def _make_settings(owm_key="test-owm-key"):
    s = MagicMock()
    s.openweathermap_api_key = owm_key
    return s


def _owm_response(name="Los Angeles", lat=34.05, lon=-118.24, state="California", country="US"):
    """Build a mock OWM /geo/1.0/direct JSON response."""
    return [{"name": name, "lat": lat, "lon": lon, "state": state, "country": country}]


def _nominatim_response(
    lat="34.0522",
    lon="-118.2437",
    display_name="Los Angeles, CA, USA",
    country_code="us",
    iso_code="US-CA",
):
    """Build a mock Nominatim search JSON response."""
    return [
        {
            "lat": lat,
            "lon": lon,
            "display_name": display_name,
            "address": {
                "country_code": country_code,
                "ISO3166-2-lvl4": iso_code,
            },
        }
    ]


class TestGeocodeViaOWM:
    async def test_geocode_via_owm_success(self):
        """OWM returns valid result with lat/lng/state."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _owm_response()
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            svc = GeocodingService(settings=_make_settings())
            result = await svc.geocode("Los Angeles, CA")

        assert result is not None
        assert result["lat"] == 34.05
        assert result["lng"] == -118.24
        assert result["state"] == "CA"
        assert "Los Angeles" in result["formatted_address"]

    async def test_owm_empty_response_falls_back(self):
        """OWM returns empty list, Nominatim is tried."""
        mock_resp_owm = MagicMock()
        mock_resp_owm.json.return_value = []
        mock_resp_owm.raise_for_status = MagicMock()

        mock_resp_nom = MagicMock()
        mock_resp_nom.json.return_value = _nominatim_response()
        mock_resp_nom.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.side_effect = [mock_resp_owm, mock_resp_nom]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            svc = GeocodingService(settings=_make_settings())
            result = await svc.geocode("Los Angeles, CA")

        assert result is not None
        assert result["state"] == "CA"


class TestGeocodeNominatimFallback:
    async def test_geocode_falls_back_to_nominatim(self):
        """OWM raises an error, Nominatim succeeds."""
        mock_client_owm = AsyncMock()
        mock_client_owm.get.side_effect = httpx.HTTPStatusError(
            "503", request=MagicMock(), response=MagicMock()
        )
        mock_client_owm.__aenter__ = AsyncMock(return_value=mock_client_owm)
        mock_client_owm.__aexit__ = AsyncMock(return_value=False)

        mock_resp_nom = MagicMock()
        mock_resp_nom.json.return_value = _nominatim_response()
        mock_resp_nom.raise_for_status = MagicMock()

        mock_client_nom = AsyncMock()
        mock_client_nom.get.return_value = mock_resp_nom
        mock_client_nom.__aenter__ = AsyncMock(return_value=mock_client_nom)
        mock_client_nom.__aexit__ = AsyncMock(return_value=False)

        clients = iter([mock_client_owm, mock_client_nom])
        with patch(
            "services.geocoding_service.httpx.AsyncClient", side_effect=lambda **kw: next(clients)
        ):
            svc = GeocodingService(settings=_make_settings())
            result = await svc.geocode("Los Angeles, CA")

        assert result is not None
        assert result["lat"] == 34.0522
        assert result["lng"] == -118.2437
        assert result["state"] == "CA"

    async def test_no_owm_key_falls_back_to_nominatim(self):
        """When OWM key is None, skip OWM and use Nominatim directly."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _nominatim_response()
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            svc = GeocodingService(settings=_make_settings(owm_key=None))
            result = await svc.geocode("Los Angeles, CA")

        assert result is not None
        assert result["state"] == "CA"

    async def test_owm_timeout_falls_back(self):
        """OWM times out, Nominatim is used instead."""
        mock_client_owm = AsyncMock()
        mock_client_owm.get.side_effect = httpx.ReadTimeout("timeout")
        mock_client_owm.__aenter__ = AsyncMock(return_value=mock_client_owm)
        mock_client_owm.__aexit__ = AsyncMock(return_value=False)

        mock_resp_nom = MagicMock()
        mock_resp_nom.json.return_value = _nominatim_response()
        mock_resp_nom.raise_for_status = MagicMock()

        mock_client_nom = AsyncMock()
        mock_client_nom.get.return_value = mock_resp_nom
        mock_client_nom.__aenter__ = AsyncMock(return_value=mock_client_nom)
        mock_client_nom.__aexit__ = AsyncMock(return_value=False)

        clients = iter([mock_client_owm, mock_client_nom])
        with patch(
            "services.geocoding_service.httpx.AsyncClient", side_effect=lambda **kw: next(clients)
        ):
            svc = GeocodingService(settings=_make_settings())
            result = await svc.geocode("New York, NY")

        assert result is not None


class TestBothProvidersFail:
    async def test_geocode_both_fail_returns_none(self):
        """Both OWM and Nominatim fail — returns None."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("offline")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            svc = GeocodingService(settings=_make_settings())
            result = await svc.geocode("Nowhere, XX")

        assert result is None


class TestAddressToRegion:
    async def test_address_to_region_returns_state_abbr(self):
        """address_to_region returns 2-letter abbreviation for US address."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _owm_response(state="New York")
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            svc = GeocodingService(settings=_make_settings())
            region = await svc.address_to_region("Albany, NY")

        assert region == "NY"

    async def test_address_to_region_non_us_returns_none(self):
        """Non-US address (no matching state) returns None."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _owm_response(name="London", state="England", country="GB")
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            svc = GeocodingService(settings=_make_settings())
            region = await svc.address_to_region("London, UK")

        assert region is None


class TestNominatimUserAgent:
    async def test_nominatim_user_agent_header(self):
        """Nominatim requests include User-Agent: RateShift/1.0."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _nominatim_response()
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            svc = GeocodingService(settings=_make_settings(owm_key=None))
            await svc.geocode("Test Address")

        # Verify the Nominatim call included User-Agent header
        call_kwargs = mock_client.get.call_args
        assert call_kwargs.kwargs.get("headers", {}).get("User-Agent") == "RateShift/1.0"


class TestStateMapping:
    def test_all_50_states_plus_dc_mapped(self):
        """_STATE_NAME_TO_ABBR covers all 51 entries (50 states + DC)."""
        assert len(_STATE_NAME_TO_ABBR) == 51

    def test_all_abbrs_in_us_states_set(self):
        """Every abbreviation in the mapping is in the _US_STATES set."""
        for abbr in _STATE_NAME_TO_ABBR.values():
            assert abbr in _US_STATES

    def test_known_mappings(self):
        """Spot-check a few state name → abbreviation mappings."""
        assert _STATE_NAME_TO_ABBR["California"] == "CA"
        assert _STATE_NAME_TO_ABBR["New York"] == "NY"
        assert _STATE_NAME_TO_ABBR["District of Columbia"] == "DC"
        assert _STATE_NAME_TO_ABBR["West Virginia"] == "WV"
