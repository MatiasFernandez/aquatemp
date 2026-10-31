"""Sensor and binary sensor states on a real Home Assistant, from the polled
device data."""

import pytest

from custom_components.aqua_temp.common.consts import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify
from tests.cloud.mock_cloud import DEVICE_CODE, cloud_with, data_with

# Literal on purpose: the expected values must not come from the config under test
DATA = "app/device/getDataByCode"
STATUS = "app/device/getDeviceStatus"
FAULT = "app/device/getFaultDataByDeviceCode"

RESPONSES = {DATA: "get_data_by_code.idle"}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


@pytest.fixture
def cloud_responses() -> dict:
    return RESPONSES


def state_of(hass: HomeAssistant, platform: str, key: str):
    unique_id = slugify(f"{DOMAIN}_{platform}_{key}_{DEVICE_CODE}")
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)

    return hass.states.get(entity_id)


async def test_sensor_reports_the_device_value(hass, entry):
    state = state_of(hass, "sensor", "T02")

    # Recorded T02: 13.0
    assert (state.state, state.attributes["unit_of_measurement"]) == ("13.0", "°C")


async def test_water_delta_t_is_outlet_minus_inlet(hass, entry):
    # Recorded T03 14.5 and T02 13.0
    assert state_of(hass, "sensor", "water_delta_t").state == "1.5"


@cloud_with({DATA: data_with(T03="")})
async def test_water_delta_t_without_an_input_is_unknown(hass, entry):
    assert state_of(hass, "sensor", "water_delta_t").state == "unknown"


@pytest.mark.parametrize(
    ("cloud_responses", "expected"),
    [
        pytest.param(RESPONSES, "off", id="off"),
        pytest.param({DATA: data_with(Power="1")}, "on", id="on"),
    ],
)
async def test_power_reports_the_device_power(hass, entry, expected):
    assert state_of(hass, "binary_sensor", "Power").state == expected


async def test_api_status_is_on_while_logged_in(hass, entry):
    assert state_of(hass, "binary_sensor", "api_status").state == "on"


@cloud_with(
    RESPONSES
    | {STATUS: "synthetic/device_status_fault", FAULT: "synthetic/device_fault"}
)
async def test_fault_sensor_carries_the_fault_description(hass, entry):
    state = state_of(hass, "binary_sensor", "is_fault")

    # Possible bug: the fault is read and stored, but the sensor's state reads
    # is_fault from the device data, which nothing sets, so it stays off
    assert (state.state, state.attributes["fault"]) == ("off", "Water flow failure")
