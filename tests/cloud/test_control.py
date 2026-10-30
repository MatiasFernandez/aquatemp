"""Writes to app/device/control: payloads, ordering and retries.

Characterisation: the payloads are pinned as sent today, oddities included,
so a refactor cannot change them unnoticed. Bodies are compared as JSON text,
so value types count: 28.0 is not 28 and "1" is not 1.
"""

import json

import pytest

from custom_components.aqua_temp.cloud.exceptions import OperationFailedException

from .mock_cloud import DATA, DATA_IDLE, DEVICE_CODE, cloud_with, data_with

# Literal on purpose: the expected values must not come from the config under test
CONTROL = "app/device/control"
STATUS = "app/device/getDeviceStatus"
SHARED_APPECT = "app/device/getMyAppectDeviceShareDataList"

HITEMP_DEVICE_CODE = "000000000002"


def control(*params: tuple[str, object], device_code: str = DEVICE_CODE) -> dict:
    """Control body setting each (protocolCode, value) on the device."""
    return {
        "param": [
            {"deviceCode": device_code, "protocolCode": code, "value": value}
            for code, value in params
        ]
    }


def assert_sent(body: dict | None, expected: dict):
    assert json.dumps(body) == json.dumps(expected)


RESPONSES = {
    DATA: DATA_IDLE,
    CONTROL: "synthetic/control_success",
}


@pytest.fixture
def cloud_responses() -> dict:
    return RESPONSES


@pytest.fixture
async def heat_pump(api, wire):
    """Client after one poll, with the transcript cleared.

    The recorded state: off, in heat, R01 27.0, R02 28.0, Set_Temp 28.0.
    """
    await api.update()

    wire.clear()

    return api


async def test_hvac_off_powers_off(heat_pump, wire):
    await heat_pump.set_hvac_mode(DEVICE_CODE, "off")

    # Possible bug: the profile's code is "Power", sent lowercased
    assert [endpoint for endpoint, _ in wire] == [CONTROL]
    assert_sent(wire[0][1], control(("power", "0")))


async def test_hvac_heat_when_off_powers_on_reads_then_sets_mode(heat_pump, wire):
    await heat_pump.set_hvac_mode(DEVICE_CODE, "heat")

    assert [endpoint for endpoint, _ in wire] == [CONTROL, DATA, STATUS, CONTROL]
    # Possible bug: lowercased "power", as above
    assert_sent(wire[0][1], control(("power", "1")))
    assert_sent(wire[3][1], control(("Set_Temp", 28.0), ("Mode", "1")))


@cloud_with(RESPONSES | {DATA: data_with(Power="1")})
async def test_hvac_cool_when_on_sets_mode(heat_pump, wire):
    await heat_pump.set_hvac_mode(DEVICE_CODE, "cool")

    # Possible bug: Set_Temp gets the current mode's target (heat's R02,
    # 28.0), not cool's R01 (27.0)
    assert [endpoint for endpoint, _ in wire] == [CONTROL]
    assert_sent(wire[0][1], control(("Set_Temp", 28.0), ("Mode", "0")))


async def test_set_temperature_writes_mode_target_and_set_temp(heat_pump, wire):
    await heat_pump.set_temperature(DEVICE_CODE, 26.5)

    # Possible bug: the mode's target code and Set_Temp, written together
    assert [endpoint for endpoint, _ in wire] == [CONTROL]
    assert_sent(wire[0][1], control(("R02", 26.5), ("Set_Temp", 26.5)))


@pytest.mark.parametrize(("fan_mode", "value"), [("auto", "0"), ("low", "1")])
async def test_set_fan_mode_writes_manual_mute(heat_pump, wire, fan_mode, value):
    await heat_pump.set_fan_mode(DEVICE_CODE, fan_mode)

    assert [endpoint for endpoint, _ in wire] == [CONTROL]
    assert_sent(wire[0][1], control(("Manual-mute", value)))


@cloud_with(RESPONSES | {SHARED_APPECT: "synthetic/device_list_shared"})
@pytest.mark.parametrize(
    ("fan_mode", "value"), [("off", "0"), ("low", "1"), ("high", "2")]
)
async def test_set_fan_mode_writes_the_profile_value(heat_pump, wire, fan_mode, value):
    await heat_pump.set_fan_mode(HITEMP_DEVICE_CODE, fan_mode)

    assert [endpoint for endpoint, _ in wire] == [CONTROL]
    assert_sent(wire[0][1], control(("M17", value), device_code=HITEMP_DEVICE_CODE))


@cloud_with(
    RESPONSES
    | {CONTROL: ["synthetic/error_token_expired", "synthetic/control_success"]}
)
async def test_expired_token_on_write_logs_in_again_and_retries(heat_pump, wire):
    await heat_pump.set_temperature(DEVICE_CODE, 26.5)

    assert [endpoint for endpoint, _ in wire] == [
        CONTROL,
        "app/user/login",
        "app/user/getUserInfo",
        "app/device/deviceList",
        "app/device/getMyTobeAppectDeviceShareDataList",
        "app/device/getMyAppectDeviceShareDataList",
        CONTROL,
    ]
    assert_sent(wire[-1][1], wire[0][1])

    # Possible bug: rediscovery replaces the polled values with the
    # device-list entry until the next poll
    assert "T02" not in heat_pump.get_device_data(DEVICE_CODE)


@cloud_with(RESPONSES | {CONTROL: ["synthetic/error_generic"] * 3})
async def test_write_failing_every_attempt_raises(heat_pump, wire):
    with pytest.raises(OperationFailedException) as failure:
        await heat_pump.set_temperature(DEVICE_CODE, 26.5)

    assert [endpoint for endpoint, _ in wire] == [CONTROL] * 3
    assert wire[0][1] == wire[1][1] == wire[2][1]
    assert failure.value.operation == "Set_Temp"
