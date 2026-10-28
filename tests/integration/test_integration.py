"""The integration on a real Home Assistant, against the mocked cloud.

Covers the HA side of the cloud library boundary: the client's new-device
callback turning into entities, the device list into the device registry and
diagnostics, and modes crossing between HVACMode and the library's Mode.
Expected values are literal or read from the profile files, never from the
code under test.
"""

import json
from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aqua_temp.common.consts import CONF_API_TYPE, DOMAIN
from custom_components.aqua_temp.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)
from custom_components.aqua_temp.managers.password_manager import PasswordManager
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import slugify
from tests.cloud.mock_cloud import DEVICE_CODE, cloud_with, data_with, load_fixture

CONTROL = "app/device/control"
DATA = "app/device/getDataByCode"
DEVICE_LIST = "app/device/deviceList"

PROFILES = Path(__file__).parents[2] / "custom_components/aqua_temp/cloud/profiles"

DEVICE_ID = "device-id-1"
MODEL = "Model X"


def device_list() -> dict:
    """The synthetic device list, with the id and model the registry reads."""
    payload = load_fixture("aqua_temp", "synthetic/device_list")
    payload["objectResult"][0] |= {"deviceId": DEVICE_ID, "custModel": MODEL}

    return payload


RESPONSES = {
    DEVICE_LIST: device_list(),
    DATA: "get_data_by_code.idle",
    CONTROL: "synthetic/control_success",
}

# The recorded state, powered on: heat, Manual-mute 0
POWERED_ON = RESPONSES | {DATA: data_with(Power="1")}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


@pytest.fixture
def cloud_responses() -> dict:
    return RESPONSES


@pytest.fixture
async def entry(hass: HomeAssistant, api_type, cloud) -> MockConfigEntry:
    """A config entry set up and polled once, its password encrypted as the
    config flow stores it."""
    data = {
        CONF_USERNAME: "test@example.com",
        CONF_PASSWORD: "test-password",
        CONF_API_TYPE: api_type,
    }

    await PasswordManager.encrypt(hass, data)

    entry = MockConfigEntry(domain=DOMAIN, title="Aqua Temp", data=data)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    return entry


def climate_entity_id(hass: HomeAssistant) -> str:
    unique_id = slugify(f"{DOMAIN}_climate_Mode_{DEVICE_CODE}")

    return er.async_get(hass).async_get_entity_id("climate", DOMAIN, unique_id)


def expected_unique_ids(catalog_id: str) -> set[str]:
    """Built-in entities, the catalog's sensors and binary sensors, Water ΔT."""
    catalog = json.loads(
        (PROFILES / f"entity_description.{catalog_id}.json").read_text()
    )

    entities = [
        ("binary_sensor", "api_status"),
        ("select", "temperature_unit"),
        ("binary_sensor", "is_fault"),
        ("binary_sensor", "device_status"),
        ("climate", "Mode"),
        ("sensor", "water_delta_t"),
    ]
    entities.extend(
        (item["platform"], item["key"])
        for item in catalog
        if item.get("platform") in ("sensor", "binary_sensor")
    )

    return {
        slugify(f"{DOMAIN}_{platform}_{key}_{DEVICE_CODE}")
        for platform, key in entities
    }


async def test_device_is_registered_from_the_device_list(hass, entry):
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, DEVICE_ID)})

    assert device is not None
    assert device.name == "Heat pump"
    assert device.model == MODEL


async def test_device_gets_its_catalog_entities(hass, entry):
    registry = er.async_get(hass)
    unique_ids = {
        entity.unique_id
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    }

    # The device's product, 1132174963097280512, has no catalog of its own
    assert unique_ids == expected_unique_ids("default")


async def test_device_entities_are_added_once(hass, entry):
    registry = er.async_get(hass)
    before = len(er.async_entries_for_config_entry(registry, entry.entry_id))

    await hass.data[DOMAIN][entry.entry_id].async_refresh()
    await hass.async_block_till_done()

    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == before


async def test_climate_offers_the_profile_modes(hass, entry):
    state = hass.states.get(climate_entity_id(hass))

    assert state.attributes["hvac_modes"] == ["off", "cool", "heat", "auto"]
    assert state.attributes["fan_modes"] == ["auto", "low"]


async def test_climate_is_off_while_powered_off(hass, entry):
    # The recorded Mode is 1, heat, but Power is 0
    assert hass.states.get(climate_entity_id(hass)).state == "off"


@cloud_with(POWERED_ON)
async def test_climate_reports_the_device_mode(hass, entry):
    state = hass.states.get(climate_entity_id(hass))

    assert state.state == "heat"
    assert state.attributes["fan_mode"] == "auto"


@cloud_with(POWERED_ON)
async def test_setting_hvac_mode_writes_the_profile_value(hass, entry, wire):
    wire.clear()

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": climate_entity_id(hass), "hvac_mode": "cool"},
        blocking=True,
    )

    writes = [body for endpoint, body in wire if endpoint == CONTROL]

    assert [param["protocolCode"] for param in writes[0]["param"]] == [
        "Set_Temp",
        "Mode",
    ]
    assert writes[0]["param"][1]["value"] == "0"


@cloud_with(POWERED_ON)
async def test_setting_fan_mode_writes_manual_mute(hass, entry, wire):
    wire.clear()

    await hass.services.async_call(
        "climate",
        "set_fan_mode",
        {"entity_id": climate_entity_id(hass), "fan_mode": "low"},
        blocking=True,
    )

    writes = [body for endpoint, body in wire if endpoint == CONTROL]

    assert writes[0]["param"] == [
        {"deviceCode": DEVICE_CODE, "protocolCode": "Manual-mute", "value": "1"}
    ]


async def test_device_diagnostics_return_the_device(hass, entry):
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, DEVICE_ID)})

    diagnostics = await async_get_device_diagnostics(hass, entry, device)

    assert diagnostics["device"]["data"]
    assert diagnostics["device"]["entities"]
    assert diagnostics["device"]["name"] == "Heat pump"


async def test_entry_diagnostics_list_each_device(hass, entry):
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert [device["device"]["name"] for device in diagnostics["devices"]] == [
        "Heat pump"
    ]
