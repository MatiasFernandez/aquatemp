"""Device discovery: device-list requests, the unfiltered fallback, several devices."""

from custom_components.aqua_temp.cloud.api_types import APIType
from custom_components.aqua_temp.cloud.consts import PRODUCT_IDS

from .conftest import DEVICE_CODE, cloud_with, load_fixture

# Literal on purpose: the expected values must not come from the config under test
REGISTERED = "app/device/deviceList"
SHARED_TOBE = "app/device/getMyTobeAppectDeviceShareDataList"
SHARED_APPECT = "app/device/getMyAppectDeviceShareDataList"
DEVICE_LISTS = [REGISTERED, SHARED_TOBE, SHARED_APPECT]

SHARED_DEVICE_CODE = "000000000002"


def listed_device(name: str) -> dict:
    """The single device entry of a device-list fixture."""
    return load_fixture(APIType.AquaTemp, name)["objectResult"][0]


def device_list_requests(wire) -> list[tuple[str, dict | None]]:
    return [request for request in wire if request[0] in DEVICE_LISTS]


async def test_device_list_requests(client, wire):
    await client.initialize(throw_error=True)

    assert device_list_requests(wire) == [
        (REGISTERED, {"productIds": PRODUCT_IDS, "pageIndex": 1, "pageSize": 999}),
        (SHARED_TOBE, {"productIds": PRODUCT_IDS, "toUser": "test-user"}),
        (
            SHARED_APPECT,
            {
                "productIds": PRODUCT_IDS,
                "toUser": "test-user",
                "pageIndex": 1,
                "pageSize": 999,
            },
        ),
    ]
    assert list(client.devices) == [DEVICE_CODE]


@cloud_with({REGISTERED: ["synthetic/device_list_empty", "synthetic/device_list"]})
async def test_no_device_found_retries_without_product_filter(client, wire):
    await client.initialize(throw_error=True)

    assert device_list_requests(wire)[3:] == [
        (REGISTERED, {"pageIndex": 1, "pageSize": 999}),
        (SHARED_TOBE, {"toUser": "test-user"}),
        (SHARED_APPECT, {"toUser": "test-user", "pageIndex": 1, "pageSize": 999}),
    ]
    assert client.devices == {DEVICE_CODE: listed_device("synthetic/device_list")}


@cloud_with(
    {
        REGISTERED: ["synthetic/device_list_empty", 500],
        SHARED_APPECT: ["synthetic/device_list_empty", "synthetic/device_list_shared"],
    }
)
async def test_unfiltered_retry_skips_a_failing_list(client, wire):
    await client.initialize(throw_error=True)

    assert [endpoint for endpoint, _ in device_list_requests(wire)[3:]] == DEVICE_LISTS
    assert client.devices == {
        SHARED_DEVICE_CODE: listed_device("synthetic/device_list_shared")
    }


@cloud_with(
    {
        SHARED_APPECT: "synthetic/device_list_shared",
        "app/device/getDataByCode": "get_data_by_code.idle",
    }
)
async def test_each_discovered_device_is_read(api, wire):
    await api.update()

    data_requests = [
        body["deviceCode"]
        for endpoint, body in wire
        if endpoint == "app/device/getDataByCode"
    ]

    assert list(api.devices) == [DEVICE_CODE, SHARED_DEVICE_CODE]
    assert data_requests == [DEVICE_CODE, SHARED_DEVICE_CODE]


@cloud_with(
    {
        SHARED_APPECT: "synthetic/device_list_shared",
        "app/device/getDataByCode": "get_data_by_code.idle",
    }
)
async def test_each_device_is_announced_once(api, announced):
    await api.update()
    await api.update()

    assert announced == [DEVICE_CODE, SHARED_DEVICE_CODE]
