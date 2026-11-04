"""Reads through semantic codes: a catalog entry's semantic code, the one the
official app requests, preferred over its legacy key, which still answers when
the device doesn't know the semantic one.

A small catalog stands in for the shipped ones: T02 and R02 have semantic
codes, T03 doesn't.
"""

import json
import logging
from pathlib import Path

import pytest

from custom_components.aqua_temp.cloud.api_profile import ApiProfile
from custom_components.aqua_temp.cloud.api_types import APIType
from custom_components.aqua_temp.cloud.device_profiles import DeviceProfiles

from .mock_cloud import DATA, DEVICE_CODE, cloud_with, load_fixture

PROFILES = Path(__file__).parents[2] / "custom_components/aqua_temp/cloud/profiles"

CATALOG = [
    {"key": "Mode", "name": "Mode", "platform": None},
    {"key": "T02", "semantic_code": "InletWaterTemp", "platform": "sensor"},
    {"key": "R02", "semantic_code": "SetHeatTargetTemp", "platform": "sensor"},
    {"key": "T03", "platform": "sensor"},
]

# "Mode" leads the polled codes and is in the catalog too
LEGACY_CODES = ["Mode", "Mode", "T02", "R02", "T03"]


def aqua_temp_profile(semantic_codes: bool) -> ApiProfile:
    fields = json.loads((PROFILES / "api.aqua_temp.json").read_text())
    fields["semantic_codes"] = semantic_codes

    return ApiProfile(APIType.AquaTemp, fields)


def answer(*, unknown=(), **values) -> dict:
    """Both vocabularies answering, every pair agreeing, with some codes'
    values replaced and some answered as codes the device doesn't know."""
    data = load_fixture(APIType.AquaTemp, "synthetic/data_semantic")
    items = {item["code"]: item for item in data["objectResult"]}

    for code, value in values.items():
        items[code]["value"] = value

    for code in unknown:
        items[code] |= {"value": "", "dataType": ""}

    return data


@pytest.fixture
def api_profile() -> ApiProfile:
    return aqua_temp_profile(semantic_codes=True)


@pytest.fixture
def device_profiles() -> DeviceProfiles:
    mapping = json.loads((PROFILES / "mapping.default.json").read_text())

    return DeviceProfiles({"default": mapping}, {"default": CATALOG})


def requested_codes(wire) -> list[list[str]]:
    return [body["codes"] for endpoint, body in wire if endpoint == DATA]


def values(api, *codes) -> dict:
    device_data = api.get_device_data(DEVICE_CODE)

    return {code: device_data[code] for code in codes}


def disagreement_warnings(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING
        and "the code for the same value" in record.getMessage()
    ]


@cloud_with({DATA: answer()})
async def test_semantic_codes_are_requested_after_the_catalog(api, wire):
    await api.update()

    assert requested_codes(wire) == [
        [*LEGACY_CODES, "InletWaterTemp", "SetHeatTargetTemp"]
    ]


@pytest.mark.parametrize("api_profile", [aqua_temp_profile(False)], ids=["off"])
@cloud_with({DATA: answer(T02="12.5", InletWaterTemp="13.0")})
async def test_profile_without_semantic_reads_requests_legacy_codes_only(api, wire):
    await api.update()

    assert requested_codes(wire) == [LEGACY_CODES]
    assert api.get_device_data(DEVICE_CODE)["T02"] == "12.5"


@cloud_with({DATA: answer(T02="12.5", InletWaterTemp="13.0")})
async def test_semantic_value_is_read_under_the_legacy_key(api):
    await api.update()

    assert values(api, "T02", "InletWaterTemp") == {
        "T02": "13.0",
        "InletWaterTemp": "13.0",
    }


@cloud_with({DATA: answer(T02="12.5", InletWaterTemp="")})
async def test_known_semantic_code_without_a_value_reads_none(api):
    await api.update()

    assert api.get_device_data(DEVICE_CODE)["T02"] is None


@cloud_with({DATA: answer(T02="12.5", unknown=["InletWaterTemp"])})
async def test_unknown_semantic_code_falls_back_to_the_legacy_one(api):
    await api.update()

    assert values(api, "T02", "InletWaterTemp") == {
        "T02": "12.5",
        "InletWaterTemp": None,
    }


@cloud_with({DATA: answer(unknown=["T02", "InletWaterTemp"])})
async def test_both_codes_unknown_read_none(api):
    await api.update()

    assert api.get_device_data(DEVICE_CODE)["T02"] is None


@cloud_with({DATA: answer(unknown=["T02", "InletWaterTemp"])})
async def test_pair_unknown_on_both_codes_is_no_longer_requested(api, wire):
    await api.update()
    await api.update()

    assert requested_codes(wire)[1] == [
        "Mode",
        "Mode",
        "R02",
        "T03",
        "SetHeatTargetTemp",
    ]


@cloud_with({DATA: answer(unknown=["InletWaterTemp", "R02"])})
async def test_pair_with_one_known_code_is_still_requested_in_full(api, wire):
    await api.update()
    await api.update()

    assert requested_codes(wire)[1] == [
        *LEGACY_CODES,
        "InletWaterTemp",
        "SetHeatTargetTemp",
    ]


@cloud_with({DATA: answer(unknown=["T02", "InletWaterTemp", "R02", "T03"])})
async def test_only_pairs_unknown_on_both_codes_are_unknown(api):
    await api.update()

    assert api.get_unknown_codes(DEVICE_CODE) == {"T02", "InletWaterTemp", "T03"}


@cloud_with(
    {
        DATA: [
            answer(T02="12.5", unknown=["InletWaterTemp"]),
            answer(T02="12.5", InletWaterTemp="13.0"),
        ]
    }
)
async def test_semantic_code_answering_later_is_read(api):
    await api.update()
    await api.update()

    assert api.get_device_data(DEVICE_CODE)["T02"] == "13.0"


@cloud_with({DATA: answer(T02="12.5", InletWaterTemp="13.0")})
async def test_disagreement_warns_once(api, caplog):
    with caplog.at_level(logging.WARNING):
        await api.update()
        await api.update()

    assert disagreement_warnings(caplog) == [
        f"Device {DEVICE_CODE}: T02 reads '12.5' but InletWaterTemp, the code for "
        "the same value, reads '13.0'; using InletWaterTemp. The two may not be "
        "the same value on this unit"
    ]


@cloud_with({DATA: answer(InletWaterTemp="13.0", SetHeatTargetTemp="29.0", T03="15.0")})
async def test_each_disagreeing_pair_warns(api, caplog):
    with caplog.at_level(logging.WARNING):
        await api.update()

    assert len(disagreement_warnings(caplog)) == 2


@cloud_with({DATA: answer()})
async def test_agreeing_codes_do_not_warn(api, caplog):
    with caplog.at_level(logging.WARNING):
        await api.update()

    assert disagreement_warnings(caplog) == []


@cloud_with({DATA: answer(T02="", InletWaterTemp=None)})
async def test_codes_both_without_a_value_do_not_warn(api, caplog):
    with caplog.at_level(logging.WARNING):
        await api.update()

    assert disagreement_warnings(caplog) == []
