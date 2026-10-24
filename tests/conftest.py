"""Offline harness: the real config manager and API client against a mocked cloud.

Fixtures under fixtures/<api type>/ are catalogued, with their source, in
fixtures/README.md.
"""

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


def load_fixture(api_type: str, name: str) -> dict:
    """Parse fixtures/<api_type>/<name>.json; name may include a subfolder."""
    file_path = FIXTURES / api_type / f"{name}.json"

    return json.loads(file_path.read_text())


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
async def api(config_manager, cloud):
    """API client logged in and with its devices loaded, as after HA setup."""
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
        api = AquaTempAPI(None, config_manager)

        await api.initialize(throw_error=True)

        yield api

        api.set_token()
        await api.terminate()


@pytest.fixture
def cloud(api_type, config_manager):
    """Mocked cloud answering everything but getDataByCode; tests register that.

    Unmatched requests raise, so nothing reaches the real cloud.
    """

    def url(endpoint: str) -> str:
        return endpoint_url(config_manager, endpoint)

    responses = {
        Endpoints.Login: "synthetic/login",
        Endpoints.UserInfo: "synthetic/user_info",
        Endpoints.ListRegisteredDevices: "synthetic/device_list",
        Endpoints.ListSharedTobeDevices: "synthetic/device_list_empty",
        Endpoints.ListSharedAppectDevices: "synthetic/device_list_empty",
        Endpoints.DeviceStatus: "synthetic/device_status",
    }

    with aioresponses() as mocked:
        for endpoint, fixture in responses.items():
            mocked.post(
                url(endpoint), payload=load_fixture(api_type, fixture), repeat=True
            )

        yield mocked
