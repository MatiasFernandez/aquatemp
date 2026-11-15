"""Reads through the bit codes array: catalog entries marked to be requested
there, which answer only through it, read alongside the codes array.

A small catalog stands in for the shipped ones: T02 is a code, Sys1CompState
and WaterFlowSwitch are bit codes.
"""

import json
import logging

import pytest

from custom_components.aqua_temp.cloud.api_types import APIType
from custom_components.aqua_temp.cloud.device_profiles import DeviceProfiles

from .mock_cloud import (
    DATA,
    DATA_HEATING,
    DEVICE_CODE,
    LEGACY_DATA,
    PROFILES,
    cloud_with,
    legacy_aqua_temp_profile,
    load_fixture,
)

CATALOG = [
    {"key": "T02", "platform": "sensor"},
    {"key": "Sys1CompState", "platform": "binary_sensor", "request_field": "bitCodes"},
    {
        "key": "WaterFlowSwitch",
        "platform": "binary_sensor",
        "request_field": "bitCodes",
    },
]

BIT_CODES = {"Sys1CompState", "WaterFlowSwitch"}


def answer(*, unknown=()) -> dict:
    """The recorded heating response to the small catalog, codes and bit codes,
    with some answered as codes the device doesn't know."""
    data = load_fixture(APIType.AquaTemp, DATA_HEATING)
    data["objectResult"] = [
        item
        for item in data["objectResult"]
        if item["code"] in {"Mode", "T02", *BIT_CODES}
    ]
    items = {item["code"]: item for item in data["objectResult"]}

    for code in unknown:
        items[code] |= {"value": "", "dataType": ""}

    return data


@pytest.fixture
def device_profiles() -> DeviceProfiles:
    mapping = json.loads((PROFILES / "mapping.default.json").read_text())

    return DeviceProfiles({"default": mapping}, {"default": CATALOG})


def data_requests(wire, endpoint=DATA) -> list[dict]:
    return [body for request_endpoint, body in wire if request_endpoint == endpoint]


@cloud_with({DATA: answer()})
async def test_bit_codes_are_requested_in_their_own_array(api, wire):
    await api.update()

    assert data_requests(wire) == [
        {
            "deviceCode": DEVICE_CODE,
            "codes": ["Mode", "T02"],
            "bitCodes": ["Sys1CompState", "WaterFlowSwitch"],
        }
    ]


@cloud_with({DATA: answer()})
async def test_bit_codes_are_read_with_the_codes(api):
    await api.update()

    device_data = api.get_device_data(DEVICE_CODE)

    # Recorded heating: compressor running, water flowing
    assert {code: device_data[code] for code in ("T02", *sorted(BIT_CODES))} == {
        "T02": "16.0",
        "Sys1CompState": "1",
        "WaterFlowSwitch": "0",
    }


@cloud_with({DATA: answer()})
async def test_bit_codes_answering_without_a_type_are_known(api):
    # The cloud answers a known bit code with dataType null, not a type name
    await api.update()

    assert api.get_unknown_codes(DEVICE_CODE) == frozenset()


@cloud_with({DATA: answer(unknown=["WaterFlowSwitch"])})
async def test_unknown_bit_codes_are_no_longer_requested(api, wire):
    await api.update()
    await api.update()

    assert data_requests(wire)[1]["bitCodes"] == ["Sys1CompState"]


@cloud_with({DATA: answer(unknown=sorted(BIT_CODES))})
async def test_bit_codes_array_is_left_out_once_every_bit_code_is_unknown(api, wire):
    await api.update()
    await api.update()

    assert data_requests(wire)[1] == {
        "deviceCode": DEVICE_CODE,
        "codes": ["Mode", "T02"],
    }


@cloud_with({DATA: answer(unknown=["Mode", "T02"])})
async def test_bit_codes_answering_do_not_hide_every_code_unknown(api):
    # Every code unknown looks like a backend hiccup, whatever the bit codes do
    await api.update()

    assert api.get_unknown_codes(DEVICE_CODE) == frozenset()


@cloud_with({DATA: answer(unknown=["Mode", "T02"])})
async def test_every_code_unknown_keeps_requesting_the_bit_codes(api, wire):
    await api.update()
    await api.update()

    assert data_requests(wire)[1]["bitCodes"] == ["Sys1CompState", "WaterFlowSwitch"]


@cloud_with({DATA: answer(unknown=["WaterFlowSwitch"])})
async def test_unknown_bit_codes_are_recorded_while_codes_answer(api):
    await api.update()

    assert api.get_unknown_codes(DEVICE_CODE) == {"WaterFlowSwitch"}


@cloud_with({DATA: answer(unknown=["WaterFlowSwitch"])})
async def test_unknown_bit_codes_are_unread(api):
    await api.update()

    assert api.get_unread_codes(DEVICE_CODE) == {"WaterFlowSwitch"}


@pytest.mark.parametrize("api_profile", [legacy_aqua_temp_profile()], ids=["legacy"])
@cloud_with({LEGACY_DATA: answer()})
async def test_api_type_without_a_bit_codes_array_requests_none(api, wire):
    await api.update()

    assert data_requests(wire, LEGACY_DATA) == [
        {"deviceCode": DEVICE_CODE, "protocalCodes": ["Mode", "T02"]}
    ]


@pytest.mark.parametrize("api_profile", [legacy_aqua_temp_profile()], ids=["legacy"])
async def test_api_type_without_a_bit_codes_array_leaves_them_unread(api):
    assert api.get_unread_codes(DEVICE_CODE) == BIT_CODES


@pytest.mark.parametrize("api_profile", [legacy_aqua_temp_profile()], ids=["legacy"])
@cloud_with({LEGACY_DATA: answer()})
async def test_api_type_without_a_bit_codes_array_logs_the_unread_bit_codes_once(
    api, caplog
):
    with caplog.at_level(logging.DEBUG):
        await api.update()
        await api.update()

    messages = [
        record.getMessage()
        for record in caplog.records
        if "no field to request bit codes" in record.getMessage()
    ]

    assert messages == [
        f"Device {DEVICE_CODE}: this API type has no field to request bit codes, "
        "so they are not read: ['Sys1CompState', 'WaterFlowSwitch']"
    ]
