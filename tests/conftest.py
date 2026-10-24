"""Offline harness: the real config manager and API client against a mocked cloud.

Fixtures under fixtures/<api type>/ are catalogued, with their source, in
fixtures/README.md.
"""

from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from aioresponses import aioresponses
import pytest

from custom_components.aqua_temp.common.api_types import APIParam, APIType
from custom_components.aqua_temp.common.consts import CONF_API_TYPE
from custom_components.aqua_temp.common.endpoints import Endpoints
from custom_components.aqua_temp.managers.aqua_temp_api import AquaTempAPI
from custom_components.aqua_temp.managers.aqua_temp_config_manager import (
    AquaTempConfigManager,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

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


def cloud_with(responses: dict):
    """Serve responses on top of BASE_RESPONSES for one test.

    Each value is what cloud_responses takes.
    """
    return pytest.mark.parametrize("cloud_responses", [responses])


def endpoint_url(config_manager: AquaTempConfigManager, endpoint: str) -> str:
    """URL the client posts to for endpoint, built from the config under test."""
    param_url = config_manager.get_api_param(APIParam.URL)
    param_suffix = config_manager.get_api_param(APIParam.Suffix)

    return f"{param_url}/{endpoint}{param_suffix}"


@pytest.fixture(params=[APIType.AquaTemp], ids=str)
def api_type(request) -> str:
    """Each test runs once per API type in params; only AquaTemp has fixtures."""
    return str(request.param)


@pytest.fixture
async def config_manager(api_type) -> AquaTempConfigManager:
    """Real config manager without hass or a config entry, with fake credentials."""
    config_manager = AquaTempConfigManager(None, None)

    await config_manager.initialize(
        {
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "test-password",
            CONF_API_TYPE: api_type,
        }
    )

    return config_manager


@pytest.fixture
async def client(config_manager, cloud):
    """API client against the mocked cloud, not yet initialized."""
    # No HA instance to dispatch new-device signals to, and no point waiting
    # between retries
    with (
        patch(
            "custom_components.aqua_temp.managers.aqua_temp_api.async_dispatcher_send"
        ),
        patch(
            "custom_components.aqua_temp.managers.aqua_temp_api.sleep",
            new=AsyncMock(),
        ),
    ):
        client = AquaTempAPI(None, config_manager)

        # The token lives in a module-level headers dict shared by every
        # client, so clear it both ways: a failed test must not leak it
        client.set_token()

        yield client

        client.set_token()
        await client.terminate()


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
def cloud(api_type, config_manager, cloud_responses, wire):
    """Mocked cloud serving BASE_RESPONSES merged with cloud_responses.

    Unmatched requests raise, so nothing reaches the real cloud.
    """

    def record(endpoint: str):
        def callback(url, **kwargs):
            wire.append((endpoint, deepcopy(kwargs.get("json"))))

        return callback

    def mock(endpoint: str, response, repeat: bool):
        url = endpoint_url(config_manager, endpoint)
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
