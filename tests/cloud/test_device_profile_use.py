"""Each device read and written with its own profile's codes.

Two devices on one account: the recorded unit, whose product falls back to the
default profile, and a shared Hitemp, with a profile of its own. The cloud
serves both the same data, so which values each device reports depends only
on the codes its profile picks.
"""

import json
from pathlib import Path

import pytest

from custom_components.aqua_temp.cloud.client import DeviceMeta

from .mock_cloud import DATA, DATA_IDLE, DEVICE_CODE, cloud_with, data_with

# Literal on purpose: the expected values must not come from the config under test
CONTROL = "app/device/control"
SHARED_APPECT = "app/device/getMyAppectDeviceShareDataList"

HITEMP_DEVICE_CODE = "000000000002"
HITEMP = "1245226668902080512"

HITEMP_CATALOG = (
    Path(__file__).parents[2]
    / f"custom_components/aqua_temp/cloud/profiles/entity_description.{HITEMP}.json"
)


def with_hitemp_codes(data: dict) -> dict:
    """data plus the Hitemp mode, power and fan codes: powered on, heat, high.

    The cloud only returns these when asked, and the Hitemp catalog doesn't
    ask for them; see test_hitemp_mode_is_never_polled.
    """
    data["objectResult"].extend(
        {"code": code, "value": value}
        for code, value in [("mode_real", "0"), ("MO6", "1"), ("M17", "2")]
    )

    return data


RESPONSES = {
    SHARED_APPECT: "synthetic/device_list_shared",
    DATA: with_hitemp_codes(data_with(T10="21.5")),
    CONTROL: "synthetic/control_success",
}


@pytest.fixture
def cloud_responses() -> dict:
    return RESPONSES


@pytest.fixture
async def heat_pumps(api, wire):
    """Client after one poll of both devices, with the transcript cleared."""
    await api.update()

    wire.clear()

    return api


def state(api, device_code: str) -> dict:
    return {
        "power": api.get_device_power(device_code),
        "hvac_mode": api.get_device_hvac_mode(device_code),
        "fan_mode": api.get_device_fan_mode(device_code),
        "current": api.get_device_current_temperature(device_code),
        "target": api.get_device_target_temperature(device_code),
        "minimum": api.get_device_minimum_temperature(device_code),
        "maximum": api.get_device_maximum_temperature(device_code),
    }


async def test_each_device_reads_its_profile_codes(heat_pumps):
    assert {
        device_code: state(heat_pumps, device_code)
        for device_code in (DEVICE_CODE, HITEMP_DEVICE_CODE)
    } == {
        # Power 0, Mode 1, Manual-mute 0, T02 13.0, heat's R02, R10, R11
        DEVICE_CODE: {
            "power": False,
            "hvac_mode": "heat",
            "fan_mode": "auto",
            "current": 13.0,
            "target": 28.0,
            "minimum": 15.0,
            "maximum": 35.0,
        },
        # MO6 1, mode_real 0, M17 2, T10 21.5, heat's R01, T02, T03
        HITEMP_DEVICE_CODE: {
            "power": True,
            "hvac_mode": "heat",
            "fan_mode": "high",
            "current": 21.5,
            "target": 27.0,
            "minimum": 13.0,
            "maximum": 14.5,
        },
    }


async def test_each_device_polls_its_catalog_codes(api, wire):
    await api.update()

    hitemp_codes = [item["key"] for item in json.loads(HITEMP_CATALOG.read_text())]
    [hitemp_request] = [
        body
        for endpoint, body in wire
        if endpoint == DATA and body["deviceCode"] == HITEMP_DEVICE_CODE
    ]

    assert hitemp_request["protocalCodes"] == ["Mode", *hitemp_codes]


@cloud_with(RESPONSES | {DATA: DATA_IDLE})
async def test_hitemp_mode_is_never_polled(api, wire):
    await api.update()

    [hitemp_request] = [
        body
        for endpoint, body in wire
        if endpoint == DATA and body["deviceCode"] == HITEMP_DEVICE_CODE
    ]
    # Possible bug: mode_real, MO6 and M17 are not in the Hitemp catalog, so
    # they are never requested. A missing mode matches off's null wire value
    assert not {"mode_real", "MO6", "M17"} & set(hitemp_request["protocalCodes"])
    assert state(api, HITEMP_DEVICE_CODE) == {
        "power": False,
        "hvac_mode": "off",
        "fan_mode": None,
        "current": 0.0,
        "target": None,
        "minimum": None,
        "maximum": None,
    }


async def test_device_meta_comes_from_its_device_list_entry(heat_pumps):
    assert heat_pumps.get_device_meta(HITEMP_DEVICE_CODE) == DeviceMeta(
        nickname="Shared heat pump", device_id=None, model=None, product_id=HITEMP
    )


async def test_set_temperature_writes_the_device_codes(heat_pumps, wire):
    await heat_pumps.set_temperature(HITEMP_DEVICE_CODE, 26.5)

    # Possible bug: heat's target and the temperature role are both R01, so it
    # is written twice in one request
    assert wire == [
        (
            CONTROL,
            {
                "param": [
                    {
                        "deviceCode": HITEMP_DEVICE_CODE,
                        "protocolCode": "R01",
                        "value": 26.5,
                    },
                    {
                        "deviceCode": HITEMP_DEVICE_CODE,
                        "protocolCode": "R01",
                        "value": 26.5,
                    },
                ]
            },
        )
    ]


async def test_set_hvac_mode_writes_the_device_codes(heat_pumps, wire):
    await heat_pumps.set_hvac_mode(HITEMP_DEVICE_CODE, "heat")

    assert wire == [
        (
            CONTROL,
            {
                "param": [
                    {
                        "deviceCode": HITEMP_DEVICE_CODE,
                        "protocolCode": "R01",
                        "value": 27.0,
                    },
                    {
                        "deviceCode": HITEMP_DEVICE_CODE,
                        "protocolCode": "mode_real",
                        "value": "0",
                    },
                ]
            },
        )
    ]


async def test_hvac_off_powers_off_with_the_device_code(heat_pumps, wire):
    await heat_pumps.set_hvac_mode(HITEMP_DEVICE_CODE, "off")

    # Possible bug: the profile's code is "MO6", sent lowercased
    assert wire == [
        (
            CONTROL,
            {
                "param": [
                    {
                        "deviceCode": HITEMP_DEVICE_CODE,
                        "protocolCode": "mo6",
                        "value": "0",
                    }
                ]
            },
        )
    ]
