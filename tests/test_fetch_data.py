"""getDataByCode: request shape and response parsing, through the full update cycle."""

import json
import logging
from pathlib import Path

from aiohttp import ClientResponseError
import pytest
from yarl import URL

from custom_components.aqua_temp.cloud.endpoints import Endpoints

from .conftest import DEVICE_CODE, endpoint_url, load_fixture

# Literal on purpose: the expected values must not come from the config under test
DATA_URL = "https://cloud.linked-go.com:449/crmservice/api/app/device/getDataByCode"

DEFAULT_PROFILE = (
    Path(__file__).parents[1]
    / "custom_components/aqua_temp/cloud/profiles/entity_description.default.json"
)


def default_profile_codes() -> list[str]:
    """Codes requested for the default profile: Mode, then the JSON's."""
    profile = [item["key"] for item in json.loads(DEFAULT_PROFILE.read_text())]

    return ["Mode", *profile]


def register_data(cloud, api_type, config_manager, *fixtures):
    """Queue getDataByCode responses; each is served once, in the order given."""
    url = endpoint_url(config_manager, Endpoints.DeviceData)

    for fixture in fixtures:
        cloud.post(url, payload=load_fixture(api_type, fixture))


def requests_to(cloud, config_manager, endpoint):
    url = URL(endpoint_url(config_manager, endpoint))

    return cloud.requests.get(("POST", url), [])


async def test_requests_device_protocol_codes(api, cloud, api_type, config_manager):
    # Reads are due to move to v5/getDataByCode with a `codes` field; this test
    # changes with them on purpose
    register_data(cloud, api_type, config_manager, "get_data_by_code.idle")

    await api.update()

    data_requests = cloud.requests.get(("POST", URL(DATA_URL)))

    assert data_requests is not None
    assert len(data_requests) == 1

    body = data_requests[0].kwargs["json"]

    assert set(body) == {"deviceCode", "protocalCodes"}
    assert body["deviceCode"] == DEVICE_CODE
    # Suspect (AT-041): "Mode" leads the polled codes and is in the profile
    # too, so it is requested twice
    assert body["protocalCodes"] == default_profile_codes()
    assert body["protocalCodes"].count("Mode") == 2


async def test_reported_values_become_device_data(api, cloud, api_type, config_manager):
    register_data(cloud, api_type, config_manager, "get_data_by_code.idle")

    await api.update()

    device_data = api.get_device_data(DEVICE_CODE)

    assert device_data["T02"] == "13.0"  # TEMP
    assert device_data["Mode"] == "1"  # ENUM


async def test_empty_value_becomes_none(api, cloud, api_type, config_manager):
    register_data(cloud, api_type, config_manager, "get_data_by_code.idle")

    await api.update()

    device_data = api.get_device_data(DEVICE_CODE)

    # Recorded as "": a code the unit does not know
    assert "F10" in device_data
    assert device_data["F10"] is None


async def test_expired_token_logs_in_again_and_retries(
    api, cloud, api_type, config_manager
):
    """A -100 response clears the token, logs in again and retries the read."""
    register_data(
        cloud,
        api_type,
        config_manager,
        "synthetic/error_token_expired",
        "get_data_by_code.idle",
    )

    await api.update()

    assert len(requests_to(cloud, config_manager, Endpoints.Login)) == 2
    assert len(requests_to(cloud, config_manager, Endpoints.DeviceData)) == 2
    assert api.get_device_data(DEVICE_CODE)["T02"] == "13.0"


async def test_read_failing_every_attempt_raises(api, cloud, config_manager):
    """Three attempts, each after a fresh login, then the last error is raised."""
    url = endpoint_url(config_manager, Endpoints.DeviceData)
    cloud.post(url, status=500, repeat=True)

    with pytest.raises(ClientResponseError):
        await api.update()

    # One login by the api fixture, then one before each retry
    assert len(requests_to(cloud, config_manager, Endpoints.Login)) == 3
    assert len(requests_to(cloud, config_manager, Endpoints.DeviceData)) == 3


async def test_error_response_keeps_device_list_data(
    api, cloud, api_type, config_manager, caplog
):
    register_data(cloud, api_type, config_manager, "synthetic/error_generic")

    with caplog.at_level(logging.ERROR):
        await api.update()

    device = load_fixture(api_type, "synthetic/device_list")["objectResult"][0]

    assert api.get_device_data(DEVICE_CODE) == device
    assert "Failed to fetch parameters, Error: Failed" in caplog.text
