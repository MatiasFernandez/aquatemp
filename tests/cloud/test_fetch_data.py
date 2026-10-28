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

from .mock_cloud import (
    DATA,
    DATA_IDLE,
    DEVICE_CODE,
    cloud_with,
    data_untyped,
    endpoint_url,
    load_fixture,
)

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


# Answered with an empty value and dataType in the idle recording
UNKNOWN_CODES = {
    "F10",
    "O01",
    "O02",
    "O03",
    "O04",
    "O05",
    "S01",
    "S02",
    "S03",
    "S04",
    "S05",
    "S06",
}


def data_endpoint(api_profile: ApiProfile) -> str:
    return api_profile.get(APIParam.DataEndpoint)


def register_data(cloud, api_type, api_profile, *fixtures):
    """Queue getDataByCode responses; each is served once, in the order given.

    A fixture is a name or a payload dict.
    """
    url = endpoint_url(api_profile, data_endpoint(api_profile))

    for fixture in fixtures:
        payload = (
            load_fixture(api_type, fixture) if isinstance(fixture, str) else fixture
        )

        cloud.post(url, payload=payload)


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

    assert api.get_device_data(DEVICE_CODE) == device | {"device_status": "ONLINE"}
    assert "Failed to fetch parameters, Error: Failed" in caplog.text


async def test_untyped_codes_are_unknown(api, cloud, api_type, api_profile):
    register_data(cloud, api_type, api_profile, DATA_IDLE)

    await api.update()

    assert api.get_unknown_codes(DEVICE_CODE) == UNKNOWN_CODES


async def test_nothing_is_unknown_before_the_first_read(api):
    assert api.get_unknown_codes(DEVICE_CODE) == frozenset()


async def test_unknown_codes_are_logged(api, cloud, api_type, api_profile, caplog):
    register_data(cloud, api_type, api_profile, DATA_IDLE)

    with caplog.at_level(logging.DEBUG):
        await api.update()

    assert (
        f"Device {DEVICE_CODE} doesn't know codes, skipping them: "
        f"{sorted(UNKNOWN_CODES)}"
    ) in caplog.text


async def test_all_codes_untyped_is_logged(api, cloud, api_type, api_profile, caplog):
    register_data(cloud, api_type, api_profile, data_untyped())

    with caplog.at_level(logging.DEBUG):
        await api.update()

    assert (
        f"Device {DEVICE_CODE} answered every code as unknown, skipping none"
    ) in caplog.text


async def test_all_codes_untyped_leaves_nothing_unknown(
    api, cloud, api_type, api_profile
):
    register_data(cloud, api_type, api_profile, data_untyped())

    await api.update()

    assert api.get_unknown_codes(DEVICE_CODE) == frozenset()


async def test_null_or_missing_data_type_is_not_unknown(
    api, cloud, api_type, api_profile
):
    data = load_fixture(api_type, DATA_IDLE)
    items = {item["code"]: item for item in data["objectResult"]}
    items["T02"]["dataType"] = None
    del items["T03"]["dataType"]

    register_data(cloud, api_type, api_profile, data)

    await api.update()

    assert api.get_unknown_codes(DEVICE_CODE) == UNKNOWN_CODES


async def test_untyped_item_without_code_is_ignored(api, cloud, api_type, api_profile):
    data = load_fixture(api_type, DATA_IDLE)
    data["objectResult"].append({"value": "", "dataType": ""})

    register_data(cloud, api_type, api_profile, data)

    await api.update()

    assert api.get_unknown_codes(DEVICE_CODE) == UNKNOWN_CODES


async def test_first_answered_read_decides_unknown_codes(
    api, cloud, api_type, api_profile
):
    register_data(
        cloud,
        api_type,
        api_profile,
        "synthetic/error_generic",
        DATA_IDLE,
    )

    await api.update()

    assert api.get_unknown_codes(DEVICE_CODE) == frozenset()

    await api.update()

    assert api.get_unknown_codes(DEVICE_CODE) == UNKNOWN_CODES


async def test_unknown_codes_are_kept_after_later_reads(
    api, cloud, api_type, api_profile
):
    register_data(
        cloud,
        api_type,
        api_profile,
        DATA_IDLE,
        data_untyped("T02"),
    )

    await api.update()
    await api.update()

    assert api.get_unknown_codes(DEVICE_CODE) == UNKNOWN_CODES


async def test_unknown_codes_survive_logging_in_again(
    api, cloud, api_type, api_profile
):
    """Logging in again rediscovers devices, replacing their data."""
    register_data(
        cloud,
        api_type,
        api_profile,
        DATA_IDLE,
        "synthetic/error_token_expired",
        data_untyped("T02"),
    )

    await api.update()
    await api.update()

    assert len(requests_to(cloud, api_profile, Endpoints.Login)) == 2
    assert api.get_unknown_codes(DEVICE_CODE) == UNKNOWN_CODES


async def test_unknown_codes_are_no_longer_requested(api, cloud, api_type, api_profile):
    register_data(
        cloud,
        api_type,
        api_profile,
        DATA_IDLE,
        DATA_IDLE,
    )

    await api.update()
    await api.update()

    first, second = cloud.requests.get(("POST", URL(DATA_URL)))

    assert first.kwargs["json"]["protocalCodes"] == default_profile_codes()
    assert second.kwargs["json"]["protocalCodes"] == [
        code for code in default_profile_codes() if code not in UNKNOWN_CODES
    ]
    assert second.kwargs["json"]["protocalCodes"].count("Mode") == 2


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
    # The empty first read didn't settle which codes the device doesn't know
    assert api.get_unknown_codes(DEVICE_CODE) == UNKNOWN_CODES


SHARED_APPECT = "app/device/getMyAppectDeviceShareDataList"
SHARED_DEVICE_CODE = "000000000002"


@cloud_with(
    {
        SHARED_APPECT: "synthetic/device_list_shared",
        DATA: "synthetic/data_empty",
    }
)
async def test_empty_read_warns_once_per_device(api, caplog):
    with caplog.at_level(logging.WARNING):
        await api.update()
        await api.update()

    warned_devices = [warning.split(":")[0] for warning in empty_read_warnings(caplog)]

    assert warned_devices == [f"Device {DEVICE_CODE}", f"Device {SHARED_DEVICE_CODE}"]
