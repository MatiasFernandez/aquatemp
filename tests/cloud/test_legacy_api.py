"""The legacy Aqua Temp API type: its own host and .json suffix, snake_case
field names, and a keep-alive instruction before each read."""

import logging

import pytest
from yarl import URL

from custom_components.aqua_temp.cloud.api_types import APIType
from custom_components.aqua_temp.cloud.client import DeviceMeta
from custom_components.aqua_temp.cloud.consts import PRODUCT_IDS

from .mock_cloud import DEVICE_CODE, cloud_with

# Literal on purpose: the expected values must not come from the config under test
LOGIN = "app/user/login"
REGISTERED = "app/device/deviceList"
SHARED_TOBE = "app/device/getMyTobeAppectDeviceShareDataList"
SHARED_APPECT = "app/device/getMyAppectDeviceShareDataList"
DATA = "app/device/getDataByCode"
STATUS = "app/device/getDeviceStatus"
KEEP_ALIVE = "device/sendDevicePassthroughInstruction"
LOGIN_URL = URL(f"https://cloud.linked-go.com/cloudservice/api/{LOGIN}.json")

# MD5 of test-password
PASSWORD_HASH = "dfb450efddbb5387197c84460623675b"

RESPONSES = {
    DATA: "synthetic/get_data_by_code",
    STATUS: "synthetic/device_status",
    KEEP_ALIVE: "synthetic/passthrough_success",
}


@pytest.fixture
def api_type() -> str:
    return str(APIType.AquaTempOld)


@pytest.fixture
def cloud_responses() -> dict:
    return RESPONSES


async def test_login_posts_to_the_legacy_host(client, cloud, wire):
    await client.initialize(throw_error=True)

    assert ("POST", LOGIN_URL) in cloud.requests
    assert wire[0] == (
        LOGIN,
        {"user_name": "test@example.com", "password": PASSWORD_HASH},
    )


async def test_device_lists_use_snake_case_fields(client, wire):
    await client.initialize(throw_error=True)

    assert [request for request in wire if request[0] != LOGIN][1:] == [
        (REGISTERED, {"product_ids": PRODUCT_IDS, "page_index": 1, "page_size": 999}),
        (SHARED_TOBE, {"product_ids": PRODUCT_IDS, "to_user": "test-user"}),
        (
            SHARED_APPECT,
            {
                "product_ids": PRODUCT_IDS,
                "to_user": "test-user",
                "page_index": 1,
                "page_size": 999,
            },
        ),
    ]
    assert client.get_device_meta(DEVICE_CODE) == DeviceMeta(
        nickname="Heat pump",
        device_id=None,
        model=None,
        product_id="1132174963097280512",
    )


async def test_each_read_follows_a_keep_alive(api, wire):
    wire.clear()

    await api.update()

    assert [endpoint for endpoint, _ in wire] == [KEEP_ALIVE, DATA, STATUS]
    assert wire[0][1] == {
        "device_code": DEVICE_CODE,
        "query_instruction": "630300040001CD89",
    }
    assert wire[1][1]["device_code"] == DEVICE_CODE


@cloud_with(RESPONSES | {KEEP_ALIVE: "synthetic/error_generic"})
async def test_failed_keep_alive_is_logged_and_the_read_goes_on(api, wire, caplog):
    wire.clear()

    with caplog.at_level(logging.ERROR):
        await api.update()

    assert [endpoint for endpoint, _ in wire] == [KEEP_ALIVE, DATA, STATUS]
    assert "Failed to send passthrough instruction, Error: Failed" in caplog.text
    assert api.get_device_data(DEVICE_CODE)["T02"] == "13.0"


async def test_reported_values_become_device_state(api):
    await api.update()

    assert {
        "power": api.get_device_power(DEVICE_CODE),
        "hvac_mode": api.get_device_hvac_mode(DEVICE_CODE),
        "current": api.get_device_current_temperature(DEVICE_CODE),
        "target": api.get_device_target_temperature(DEVICE_CODE),
    } == {"power": True, "hvac_mode": "heat", "current": 13.0, "target": 28.0}
