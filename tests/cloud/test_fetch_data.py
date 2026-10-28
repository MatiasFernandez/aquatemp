"""getDataByCode: request shape and response parsing, through the full update cycle."""

import json
import logging
from pathlib import Path

from aiohttp import ClientResponseError
import pytest
from yarl import URL

from custom_components.aqua_temp.cloud.api_profile import ApiProfile
from custom_components.aqua_temp.cloud.api_types import APIParam
from custom_components.aqua_temp.cloud.endpoints import Endpoints

from .mock_cloud import DATA_IDLE, DEVICE_CODE, endpoint_url, load_fixture

# Literal on purpose: the expected values must not come from the config under test
DATA_URL = "https://cloud.linked-go.com:449/crmservice/api/app/device/getDataByCode"

DEFAULT_PROFILE = (
    Path(__file__).parents[2]
    / "custom_components/aqua_temp/cloud/profiles/entity_description.default.json"
)


def default_profile_codes() -> list[str]:
    """Codes requested for the default profile: Mode, then the JSON's."""
    profile = [item["key"] for item in json.loads(DEFAULT_PROFILE.read_text())]

    return ["Mode", *profile]


def data_endpoint(api_profile: ApiProfile) -> str:
    return api_profile.get(APIParam.DataEndpoint)


def register_data(cloud, api_type, api_profile, *fixtures):
    """Queue getDataByCode responses; each is served once, in the order given."""
    url = endpoint_url(api_profile, data_endpoint(api_profile))

    for fixture in fixtures:
        cloud.post(url, payload=load_fixture(api_type, fixture))


def requests_to(cloud, api_profile, endpoint):
    url = URL(endpoint_url(api_profile, endpoint))

    return cloud.requests.get(("POST", url), [])


async def test_requests_device_protocol_codes(api, cloud, api_type, api_profile):
    # Reads are due to move to v5/getDataByCode with a `codes` field; this test
    # changes with them on purpose
    register_data(cloud, api_type, api_profile, DATA_IDLE)

    await api.update()

    data_requests = cloud.requests.get(("POST", URL(DATA_URL)))

    assert data_requests is not None
    assert len(data_requests) == 1

    body = data_requests[0].kwargs["json"]

    assert set(body) == {"deviceCode", "protocalCodes"}
    assert body["deviceCode"] == DEVICE_CODE
    # Possible bug: "Mode" leads the polled codes and is in the profile
    # too, so it is requested twice
    assert body["protocalCodes"] == default_profile_codes()
    assert body["protocalCodes"].count("Mode") == 2


async def test_reported_values_become_device_data(api, cloud, api_type, api_profile):
    register_data(cloud, api_type, api_profile, DATA_IDLE)

    await api.update()

    device_data = api.get_device_data(DEVICE_CODE)

    assert device_data["T02"] == "13.0"  # TEMP
    assert device_data["Mode"] == "1"  # ENUM


async def test_empty_value_becomes_none(api, cloud, api_type, api_profile):
    register_data(cloud, api_type, api_profile, DATA_IDLE)

    await api.update()

    device_data = api.get_device_data(DEVICE_CODE)

    # Recorded as "": a code the unit does not know
    assert "F10" in device_data
    assert device_data["F10"] is None


async def test_expired_token_logs_in_again_and_retries(
    api, cloud, api_type, api_profile
):
    """A -100 response clears the token, logs in again and retries the read."""
    register_data(
        cloud,
        api_type,
        api_profile,
        "synthetic/error_token_expired",
        DATA_IDLE,
    )

    await api.update()

    assert len(requests_to(cloud, api_profile, Endpoints.Login)) == 2
    assert len(requests_to(cloud, api_profile, data_endpoint(api_profile))) == 2
    assert api.get_device_data(DEVICE_CODE)["T02"] == "13.0"


async def test_read_failing_every_attempt_raises(api, cloud, api_profile):
    """Three attempts, each after a fresh login, then the last error is raised."""
    url = endpoint_url(api_profile, data_endpoint(api_profile))
    cloud.post(url, status=500, repeat=True)

    with pytest.raises(ClientResponseError):
        await api.update()

    # One login by the api fixture, then one before each retry
    assert len(requests_to(cloud, api_profile, Endpoints.Login)) == 3
    assert len(requests_to(cloud, api_profile, data_endpoint(api_profile))) == 3


async def test_error_response_keeps_device_list_data(
    api, cloud, api_type, api_profile, caplog
):
    register_data(cloud, api_type, api_profile, "synthetic/error_generic")

    with caplog.at_level(logging.ERROR):
        await api.update()

    device = load_fixture(api_type, "synthetic/device_list")["objectResult"][0]

    assert api.get_device_data(DEVICE_CODE) == device
    assert "Failed to fetch parameters, Error: Failed" in caplog.text


def empty_read_warnings(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING and "no values" in record.getMessage()
    ]


async def test_empty_read_warns_once(api, cloud, api_type, api_profile, caplog):
    register_data(
        cloud,
        api_type,
        api_profile,
        DATA_IDLE,
        "synthetic/data_empty",
        "synthetic/data_empty",
    )

    await api.update()
    device_data = api.get_device_data(DEVICE_CODE)

    with caplog.at_level(logging.WARNING):
        await api.update()
        await api.update()

    assert empty_read_warnings(caplog) == [
        f"Device {DEVICE_CODE}: {data_endpoint(api_profile)} returned no values "
        f"for the requested codes; the {api_profile.get(APIParam.DataCodes)} "
        "field may be wrong, or the cloud changed"
    ]
    assert api.get_device_data(DEVICE_CODE) == device_data


async def test_empty_read_warns_again_after_values(
    api, cloud, api_type, api_profile, caplog
):
    register_data(
        cloud,
        api_type,
        api_profile,
        "synthetic/data_empty",
        DATA_IDLE,
        "synthetic/data_empty",
    )

    with caplog.at_level(logging.WARNING):
        await api.update()
        await api.update()
        await api.update()

    assert len(empty_read_warnings(caplog)) == 2
