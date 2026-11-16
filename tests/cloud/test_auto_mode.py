"""Whether a unit running in auto mode heats or cools, by the official app's
rule: it heats when the auto target is above the inlet water temperature.

Recorded: R03, the auto target, is 27.0 and T02, the inlet water temperature,
12.5, both answered under their legacy codes.
"""

import json

import pytest

from custom_components.aqua_temp.cloud.device_profiles import DeviceProfiles
from custom_components.aqua_temp.cloud.modes import Mode

from .mock_cloud import DATA, DEVICE_CODE, PROFILES, data_with

CATALOG = [
    {"key": "T02", "semantic_code": "InletWaterTemp", "platform": "sensor"},
    {"key": "R03", "platform": "sensor"},
]


def mapping(**roles) -> dict:
    return json.loads((PROFILES / "mapping.default.json").read_text()) | roles


def modes_without_auto() -> dict:
    modes = mapping()["hvac_modes"]
    del modes["auto"]

    return modes


def inlet(value: str) -> dict:
    return {DATA: data_with(T02=value, InletWaterTemp=value)}


@pytest.mark.parametrize(
    ("cloud_responses", "expected"),
    [
        pytest.param({DATA: data_with()}, Mode.HEAT, id="target_above_inlet"),
        pytest.param(inlet("30.0"), Mode.COOL, id="target_below_inlet"),
        # The app's comparison is obfuscated; equal is read as cooling
        pytest.param(inlet("27.0"), Mode.COOL, id="equal"),
        pytest.param(inlet("26.9"), Mode.HEAT, id="just_below_target"),
    ],
)
async def test_auto_mode_heats_when_the_target_is_above_the_inlet(api, expected):
    await api.update()

    assert api.get_device_auto_mode_direction(DEVICE_CODE) is expected


@pytest.mark.parametrize(
    "cloud_responses",
    [
        pytest.param({DATA: data_with(R03="")}, id="no_target"),
        pytest.param(inlet(""), id="no_inlet"),
        pytest.param({DATA: data_with(R03="n/a")}, id="target_not_a_number"),
        pytest.param(inlet("nan"), id="inlet_not_finite"),
    ],
)
async def test_auto_mode_direction_is_unknown_without_a_reading(api):
    await api.update()

    assert api.get_device_auto_mode_direction(DEVICE_CODE) is None


@pytest.mark.parametrize(
    "device_profiles",
    [
        DeviceProfiles(
            {"default": mapping(inlet_water_temperature=None)}, {"default": CATALOG}
        ),
        DeviceProfiles(
            {"default": mapping(hvac_modes=modes_without_auto())},
            {"default": CATALOG},
        ),
    ],
    ids=["no_inlet_role", "no_auto_mode"],
)
@pytest.mark.parametrize("cloud_responses", [{DATA: data_with()}])
async def test_auto_mode_direction_is_unknown_without_the_codes(api):
    await api.update()

    assert api.get_device_auto_mode_direction(DEVICE_CODE) is None
