"""Online state: getDeviceStatus reports it, and it lands in device data."""

import pytest

from .mock_cloud import DEVICE_CODE, cloud_with

# Literal on purpose: the expected values must not come from the config under test
STATUS = "app/device/getDeviceStatus"
FAULT = "app/device/getFaultDataByDeviceCode"
DATA = "app/device/getDataByCode"

RESPONSES = {DATA: "get_data_by_code.idle"}


@cloud_with(RESPONSES | {STATUS: "device_status.online"})
async def test_online_device_reports_online(api):
    await api.update()

    assert api.get_device_data(DEVICE_CODE)["device_status"] == "ONLINE"


@cloud_with(RESPONSES | {STATUS: "device_status.offline"})
async def test_offline_device_reports_offline(api):
    await api.update()

    assert api.get_device_data(DEVICE_CODE)["device_status"] == "OFFLINE"


@cloud_with(
    RESPONSES
    | {
        STATUS: "synthetic/device_status_fault",
        FAULT: "synthetic/device_fault",
    }
)
async def test_faulting_device_reports_its_status(api):
    await api.update()

    assert api.get_device_data(DEVICE_CODE)["device_status"] == "ONLINE"


@cloud_with(
    RESPONSES
    | {
        STATUS: {
            "error_code": "0",
            "error_msg": "Success",
            "objectResult": {"isFault": False},
        }
    }
)
async def test_missing_status_is_unknown(api):
    await api.update()

    assert api.get_device_data(DEVICE_CODE)["device_status"] is None


@cloud_with(RESPONSES | {STATUS: ["device_status.offline", "device_status.online"]})
async def test_status_follows_each_poll(api):
    await api.update()
    await api.update()

    assert api.get_device_data(DEVICE_CODE)["device_status"] == "ONLINE"


@pytest.mark.parametrize(
    ("cloud_responses", "is_offline"),
    [
        pytest.param(RESPONSES | {STATUS: "device_status.online"}, False, id="online"),
        pytest.param(RESPONSES | {STATUS: "device_status.offline"}, True, id="offline"),
        pytest.param(
            RESPONSES
            | {
                STATUS: {
                    "error_code": "0",
                    "error_msg": "Success",
                    "objectResult": {"isFault": False},
                }
            },
            False,
            id="missing",
        ),
    ],
)
async def test_device_is_offline_only_when_the_cloud_says_so(api, is_offline):
    await api.update()

    assert api.is_device_offline(DEVICE_CODE) is is_offline
