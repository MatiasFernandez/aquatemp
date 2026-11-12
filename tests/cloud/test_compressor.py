"""Whether the compressor runs, read through the mapping's compressor role and
its catalog entry's on and off values.

A small profile stands in for the shipped ones: Sys1CompState is a bit code
reading 1 while the compressor runs.
"""

import json

import pytest

from custom_components.aqua_temp.cloud.api_types import APIType
from custom_components.aqua_temp.cloud.device_profiles import DeviceProfiles

from .mock_cloud import DATA, DATA_HEATING, DEVICE_CODE, PROFILES, load_fixture

CATALOG = [
    {"key": "T02", "platform": "sensor"},
    {
        "key": "Sys1CompState",
        "platform": "binary_sensor",
        "request_field": "bitCodes",
        "on_value": "1",
        "off_value": "0",
    },
]


def mapping(**roles) -> dict:
    return json.loads((PROFILES / "mapping.default.json").read_text()) | roles


def answer(value) -> dict:
    """The recorded heating response, its compressor bit replaced; None
    leaves the bit out."""
    data = load_fixture(APIType.AquaTemp, DATA_HEATING)
    items = [item for item in data["objectResult"] if item["code"] != "Sys1CompState"]

    if value is not None:
        items.append({"code": "Sys1CompState", "value": value, "dataType": None})

    data["objectResult"] = items

    return data


@pytest.fixture
def device_profiles() -> DeviceProfiles:
    return DeviceProfiles(
        {"default": mapping(compressor="Sys1CompState")}, {"default": CATALOG}
    )


@pytest.mark.parametrize(
    ("cloud_responses", "expected"),
    [
        pytest.param({DATA: answer("1")}, True, id="on_value"),
        pytest.param({DATA: answer("0")}, False, id="off_value"),
        # Read as text, as the binary sensor of the same code reads it
        pytest.param({DATA: answer(1)}, True, id="number"),
        pytest.param({DATA: answer("")}, None, id="empty"),
        pytest.param({DATA: answer("2")}, None, id="other_value"),
        pytest.param({DATA: answer(["1"])}, None, id="not_a_scalar"),
        pytest.param({DATA: answer(None)}, None, id="missing"),
    ],
)
async def test_compressor_reads_its_catalog_values(api, expected):
    await api.update()

    assert api.get_device_compressor_running(DEVICE_CODE) is expected


@pytest.mark.parametrize(
    "device_profiles",
    [DeviceProfiles({"default": mapping()}, {"default": CATALOG})],
    ids=["no_role"],
)
@pytest.mark.parametrize("cloud_responses", [{DATA: answer("1")}])
async def test_compressor_without_a_role_is_unknown(api):
    await api.update()

    assert api.get_device_compressor_running(DEVICE_CODE) is None
