"""Offline harness: the real cloud library and API client against a mocked cloud.

Fixtures under fixtures/<api type>/ are catalogued, with their source, in
fixtures/README.md.
"""

from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from aiohttp import ClientSession
from aioresponses import aioresponses
import pytest

from custom_components.aqua_temp.cloud.api_profile import ApiProfile
from custom_components.aqua_temp.cloud.api_types import APIParam, APIType
from custom_components.aqua_temp.cloud.client import AquaTempAPI, Credentials
from custom_components.aqua_temp.cloud.device_profiles import DeviceProfiles
from custom_components.aqua_temp.cloud.endpoints import Endpoints

FIXTURES = Path(__file__).parent / "fixtures"

DEVICE_CODE = "000000000001"

# What the cloud answers unless a test says otherwise, every time it is asked.
# getDataByCode is left out: tests serve it themselves.
BASE_RESPONSES = {
    Endpoints.Login: "synthetic/login",
    Endpoints.UserInfo: "synthetic/user_info",
    Endpoints.ListRegisteredDevices: "synthetic/device_list",
    Endpoints.ListSharedTobeDevices: "synthetic/device_list_empty",
    Endpoints.ListSharedAppectDevices: "synthetic/device_list_empty",
    Endpoints.DeviceStatus: "synthetic/device_status",
}


def load_fixture(api_type: str, name: str) -> dict:
    """Parse fixtures/<api_type>/<name>.json; name may include a subfolder."""
    file_path = FIXTURES / api_type / f"{name}.json"

    return json.loads(file_path.read_text())


def data_with(**values) -> dict:
    """The recorded idle getDataByCode response, with some codes' values replaced."""
    data = load_fixture(APIType.AquaTemp, "get_data_by_code.idle")
    items = {item["code"]: item for item in data["objectResult"]}

    for code, value in values.items():
        assert code in items, f"{code} is not in the recording"

        items[code]["value"] = value

    return data


def data_untyped(*codes) -> dict:
    """The recorded idle getDataByCode response, with some codes answered the way
    the cloud answers a code the device doesn't know; all of them if none given."""
    data = load_fixture(APIType.AquaTemp, "get_data_by_code.idle")
    items = {item["code"]: item for item in data["objectResult"]}

    for code in codes or items:
        assert code in items, f"{code} is not in the recording"

        items[code] |= {"value": "", "dataType": ""}

    return data


def cloud_with(responses: dict):
    """Serve responses on top of BASE_RESPONSES for one test.

    Each value is what cloud_responses takes.
    """
    return pytest.mark.parametrize("cloud_responses", [responses])


def endpoint_url(api_profile: ApiProfile, endpoint: str) -> str:
    """URL the client posts to for endpoint, built from the profile under test."""
    param_url = api_profile.get(APIParam.URL)
    param_suffix = api_profile.get(APIParam.Suffix)

    return f"{param_url}/{endpoint}{param_suffix}"


@pytest.fixture(params=[APIType.AquaTemp], ids=str)
def api_type(request) -> str:
    """Each test runs once per API type in params; only AquaTemp has fixtures."""
    return str(request.param)


@pytest.fixture
async def api_profile(api_type) -> ApiProfile:
    return await ApiProfile.load(api_type)


@pytest.fixture
async def device_profiles() -> DeviceProfiles:
    return await DeviceProfiles.load()


@pytest.fixture
def announced() -> list[str]:
    """Codes of the devices the client announced as new, in order."""
    return []


@pytest.fixture
async def client(api_profile, device_profiles, announced, cloud):
    """API client against the mocked cloud, with fake credentials, not yet initialized."""
    # No point waiting between retries
    with patch("custom_components.aqua_temp.cloud.client.sleep", new=AsyncMock()):
        async with ClientSession() as session:
            client = AquaTempAPI(
                session,
                Credentials(username="test@example.com", password="test-password"),
                api_profile,
                device_profiles,
                on_new_device=announced.append,
            )

            yield client


@pytest.fixture
async def api(client):
    """API client logged in and with its devices loaded, as after HA setup."""
    await client.initialize(throw_error=True)

    return client


@pytest.fixture
def cloud_responses() -> dict:
    """Responses to serve on top of BASE_RESPONSES, by endpoint.

    A value is a fixture name, a payload dict or an HTTP error status, served
    every time; or a list of those, served once each, in order. Override in a
    module, or per test with cloud_with.
    """
    return {}


@pytest.fixture
def wire() -> list[tuple[str, dict | None]]:
    """Every request the cloud received, in order, as (endpoint, JSON body)."""
    return []


@pytest.fixture
def cloud(api_type, api_profile, cloud_responses, wire):
    """Mocked cloud serving BASE_RESPONSES merged with cloud_responses.

    Unmatched requests raise, so nothing reaches the real cloud.
    """

    def record(endpoint: str):
        def callback(url, **kwargs):
            wire.append((endpoint, deepcopy(kwargs.get("json"))))

        return callback

    def mock(endpoint: str, response, repeat: bool):
        url = endpoint_url(api_profile, endpoint)
        callback = record(endpoint)

        if isinstance(response, int):
            mocked.post(url, status=response, callback=callback, repeat=repeat)

        else:
            payload = (
                load_fixture(api_type, response)
                if isinstance(response, str)
                else response
            )

            mocked.post(url, payload=payload, callback=callback, repeat=repeat)

    responses = BASE_RESPONSES | cloud_responses

    with aioresponses() as mocked:
        for endpoint, response in responses.items():
            if isinstance(response, list):
                for item in response:
                    mock(endpoint, item, repeat=False)

            else:
                mock(endpoint, response, repeat=True)

        yield mocked
