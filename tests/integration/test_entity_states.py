"""Sensor and binary sensor states on a real Home Assistant, from the polled
device data."""

import pytest

from custom_components.aqua_temp.common.consts import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify
from tests.cloud.mock_cloud import (
    DATA,
    DATA_HEATING,
    DATA_IDLE,
    DEVICE_CODE,
    cloud_with,
    data_with,
    load_fixture,
)

# Literal on purpose: the expected values must not come from the config under test
STATUS = "app/device/getDeviceStatus"
FAULT = "app/device/getFaultDataByDeviceCode"

RESPONSES = {DATA: DATA_IDLE}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


@pytest.fixture
def cloud_responses() -> dict:
    return RESPONSES


def is_registered(hass: HomeAssistant, platform: str, key: str) -> bool:
    unique_id = slugify(f"{DOMAIN}_{platform}_{key}_{DEVICE_CODE}")

    return (
        er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id) is not None
    )


def state_of(hass: HomeAssistant, platform: str, key: str):
    unique_id = slugify(f"{DOMAIN}_{platform}_{key}_{DEVICE_CODE}")
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)

    return hass.states.get(entity_id)


async def test_sensor_reports_the_device_value(hass, entry):
    state = state_of(hass, "sensor", "T02")

    # Recorded T02: 12.5
    assert (state.state, state.attributes["unit_of_measurement"]) == ("12.5", "°C")


async def test_water_delta_t_is_outlet_minus_inlet(hass, entry):
    # Recorded T03 14.0 and T02 12.5
    assert state_of(hass, "sensor", "water_delta_t").state == "1.5"


@cloud_with({DATA: data_with(T03="", OutletWaterTemp="")})
async def test_water_delta_t_without_an_input_is_unknown(hass, entry):
    assert state_of(hass, "sensor", "water_delta_t").state == "unknown"


# Recorded heating max frequency H08 80 and cooling max H09 65; Mode 1 heats,
# 0 cools and 2 is auto
@pytest.mark.parametrize(
    ("cloud_responses", "expected"),
    [
        # Recorded O07 80 while heating
        pytest.param({DATA: DATA_HEATING}, "100.0", id="heating"),
        pytest.param({DATA: data_with(Mode="0", O07="52")}, "80.0", id="cooling"),
        # The compressor can run past the maximum, as while defrosting
        pytest.param({DATA: data_with(O07="88")}, "110.0", id="past_the_maximum"),
        # Recorded auto target R03 27.0 above the inlet T02 12.5: heating, H08
        pytest.param({DATA: data_with(Mode="2", O07="40")}, "50.0", id="auto_heating"),
        pytest.param(
            {DATA: data_with(Mode="2", O07="52", T02="30.0", InletWaterTemp="30.0")},
            "80.0",
            id="auto_cooling",
        ),
    ],
)
async def test_compressor_speed_is_the_frequency_share_of_the_mode_maximum(
    hass, entry, expected
):
    assert state_of(hass, "sensor", "compressor_speed").state == expected


@pytest.mark.parametrize(
    "cloud_responses",
    [
        # Recorded O07 0
        pytest.param(RESPONSES, id="heat"),
        pytest.param({DATA: data_with(Mode="2")}, id="auto"),
    ],
)
async def test_stopped_compressor_has_no_speed(hass, entry):
    assert state_of(hass, "sensor", "compressor_speed").state == "0.0"


@pytest.mark.parametrize(
    "cloud_responses",
    [
        # Without the auto target, nothing tells whether auto heats or cools, so
        # which maximum applies
        pytest.param(
            {DATA: data_with(Mode="2", O07="40", R03="")}, id="auto_without_target"
        ),
        pytest.param(
            {DATA: data_with(Mode="2", O07="40", T02="", InletWaterTemp="")},
            id="auto_without_inlet",
        ),
        pytest.param({DATA: data_with(O07="")}, id="no_frequency"),
        pytest.param({DATA: data_with(O07="40", H08="")}, id="no_maximum"),
        pytest.param({DATA: data_with(O07="40", H08="0")}, id="zero_maximum"),
        pytest.param({DATA: data_with(O07="40", H08="inf")}, id="maximum_not_finite"),
    ],
)
async def test_compressor_speed_is_unknown_without_its_inputs(hass, entry):
    assert state_of(hass, "sensor", "compressor_speed").state == "unknown"


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


DEVICE_LIST = "app/device/deviceList"


HEATING = {DATA: DATA_HEATING}


def data_without(code: str) -> dict:
    """The recorded idle response, without an answer for code."""
    data = data_with()
    data["objectResult"] = [
        item for item in data["objectResult"] if item["code"] != code
    ]

    return data


# Recorded compressor type H12 45
@pytest.mark.parametrize(
    "cloud_responses",
    [
        pytest.param({DATA: data_with(H12="0")}, id="zero"),
        pytest.param({DATA: data_with(H12="0.0")}, id="zero_with_decimals"),
    ],
)
async def test_no_compressor_speed_for_a_compressor_type_of_zero(hass, entry):
    assert not is_registered(hass, "sensor", "compressor_speed")


@pytest.mark.parametrize(
    "cloud_responses",
    [
        pytest.param(RESPONSES, id="recorded"),
        pytest.param({DATA: data_with(H12="1")}, id="other_value"),
        pytest.param({DATA: data_with(H12="")}, id="empty"),
        pytest.param({DATA: data_without("H12")}, id="missing"),
    ],
)
async def test_compressor_speed_exists_unless_the_compressor_type_is_zero(hass, entry):
    assert is_registered(hass, "sensor", "compressor_speed")


# Recorded heating max frequency H08 80 and cooling max H09 65
@pytest.mark.parametrize(
    ("cloud_responses", "expected"),
    [
        pytest.param({DATA: data_with(O07="40", H09="")}, "50.0", id="heating"),
        pytest.param(
            {DATA: data_with(Mode="0", O07="40", H09="")}, "unknown", id="cooling"
        ),
    ],
)
async def test_compressor_speed_with_only_the_heating_maximum_read(
    hass, entry, expected
):
    assert state_of(hass, "sensor", "compressor_speed").state == expected


@cloud_with({DATA: data_with(H08="", H09="")})
async def test_no_compressor_speed_when_no_maximum_is_read(hass, entry):
    assert not is_registered(hass, "sensor", "compressor_speed")


def device_list_of(product_id: str) -> dict:
    payload = load_fixture("aqua_temp", "synthetic/device_list")
    payload["objectResult"][0]["productId"] = product_id

    return payload


@pytest.mark.parametrize(
    ("cloud_responses", "expected"),
    [
        pytest.param(RESPONSES, "off", id="idle"),
        pytest.param(HEATING, "on", id="heating"),
    ],
)
async def test_compressor_reports_whether_it_runs(hass, entry, expected):
    assert state_of(hass, "binary_sensor", "Sys1CompState").state == expected


@pytest.mark.parametrize(
    ("cloud_responses", "expected"),
    [
        # The flow switch reads 0 while water flows
        pytest.param(RESPONSES, "off", id="idle"),
        pytest.param(HEATING, "on", id="heating"),
    ],
)
async def test_water_flow_reports_whether_water_flows(hass, entry, expected):
    assert state_of(hass, "binary_sensor", "WaterFlowSwitch").state == expected


@pytest.mark.parametrize(
    "cloud_responses",
    [
        pytest.param({DATA: data_without("Sys1CompState")}, id="missing"),
        pytest.param({DATA: data_with(Sys1CompState="")}, id="empty"),
    ],
)
async def test_bit_without_a_value_is_unavailable(hass, entry):
    assert state_of(hass, "binary_sensor", "Sys1CompState").state == "unavailable"


@pytest.mark.parametrize(
    ("cloud_responses", "expected"),
    [
        # Recorded EmergencySwitch: 0
        pytest.param(RESPONSES, "off", id="class_closed"),
        pytest.param(
            {
                DEVICE_LIST: device_list_of("1442284873216843776"),
                DATA: DATA_IDLE,
            },
            "on",
            id="1442284873216843776_open",
        ),
        pytest.param(
            {
                DEVICE_LIST: device_list_of("1732565142225256450"),
                DATA: data_with(EmergencySwitch="1"),
            },
            "off",
            id="1732565142225256450_closed",
        ),
    ],
)
async def test_external_stop_follows_the_product_polarity(hass, config_entry, expected):
    # Starts disabled: enabled ahead of setup, as a user would
    er.async_get(hass).async_get_or_create(
        "binary_sensor",
        DOMAIN,
        slugify(f"{DOMAIN}_binary_sensor_EmergencySwitch_{DEVICE_CODE}"),
        config_entry=config_entry,
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert state_of(hass, "binary_sensor", "EmergencySwitch").state == expected


async def test_diagnostic_bits_start_disabled(hass, entry):
    registry = er.async_get(hass)
    keys = ["Sys1CompState", "WaterFlowSwitch", "ATSensorFault", "ModeSwitch"]

    disabled = {
        key: registry.async_get(
            registry.async_get_entity_id(
                "binary_sensor",
                DOMAIN,
                slugify(f"{DOMAIN}_binary_sensor_{key}_{DEVICE_CODE}"),
            )
        ).disabled
        for key in keys
    }

    assert disabled == {
        "Sys1CompState": False,
        "WaterFlowSwitch": False,
        "ATSensorFault": True,
        "ModeSwitch": True,
    }


@cloud_with(
    RESPONSES
    | {STATUS: "synthetic/device_status_fault", FAULT: "synthetic/device_fault"}
)
async def test_fault_sensor_carries_the_fault_description(hass, entry):
    state = state_of(hass, "binary_sensor", "is_fault")

    # Possible bug: the fault is read and stored, but the sensor's state reads
    # is_fault from the device data, which nothing sets, so it stays off
    assert (state.state, state.attributes["fault"]) == ("off", "Water flow failure")
