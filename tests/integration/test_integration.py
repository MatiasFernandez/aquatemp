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
from custom_components.aqua_temp.common.device_lookup import async_get_ha_device
from custom_components.aqua_temp.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)
from custom_components.aqua_temp.managers.password_manager import PasswordManager
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify
from tests.cloud.mock_cloud import (
    DEVICE_CODE,
    cloud_with,
    data_untyped,
    data_with,
    load_fixture,
)

CONTROL = "app/device/control"
DATA = "app/device/getDataByCode"
DEVICE_LIST = "app/device/deviceList"

PROFILES = Path(__file__).parents[2] / "custom_components/aqua_temp/cloud/profiles"

DEVICE_ID = "device-id-1"
OTHER_DEVICE_ID = "device-id-2"

# The listed device's id, under the AquaTemp API type's field name
DEVICE_ID_PARAM = "deviceId"
MODEL = "Model X"


def device_list() -> dict:
    """The synthetic device list, with the id and model the registry reads."""
    payload = load_fixture("aqua_temp", "synthetic/device_list")
    payload["objectResult"][0] |= {"deviceId": DEVICE_ID, "custModel": MODEL}

    return payload


def two_device_list() -> dict:
    """The device list with a second device, which has its own id."""
    payload = device_list()
    payload["objectResult"].append(
        payload["objectResult"][0]
        | {"deviceCode": "000000000002", "deviceId": OTHER_DEVICE_ID}
    )

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
async def config_entry(hass: HomeAssistant, api_type, cloud) -> MockConfigEntry:
    """A config entry added but not set up, its password encrypted as the
    config flow stores it."""
    data = {
        CONF_USERNAME: "test@example.com",
        CONF_PASSWORD: "test-password",
        CONF_API_TYPE: api_type,
    }

    await PasswordManager.encrypt(hass, data)

    entry = MockConfigEntry(domain=DOMAIN, title="Aqua Temp", data=data)
    entry.add_to_hass(hass)

    return entry


async def set_up(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    return entry


@pytest.fixture
async def entry(hass: HomeAssistant, config_entry) -> MockConfigEntry:
    """The config entry set up and polled once."""
    return await set_up(hass, config_entry)


def climate_entity_id(hass: HomeAssistant) -> str:
    unique_id = slugify(f"{DOMAIN}_climate_Mode_{DEVICE_CODE}")

    return er.async_get(hass).async_get_entity_id("climate", DOMAIN, unique_id)


# Answered with an empty value and dataType in the idle recording
UNKNOWN_CODES = {
    "F10",
    "O01",
    "O02",
    "O03",
    "O04",
    "O05",
    "S01",
    "S02",
    "S03",
    "S04",
    "S05",
    "S06",
}


def expected_unique_ids(catalog_id: str, skipped: set[str] = frozenset()) -> set[str]:
    """Built-in entities, the catalog's sensors and binary sensors but those
    for skipped codes, and Water ΔT."""
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
        and item["key"] not in skipped
    )

    return {
        slugify(f"{DOMAIN}_{platform}_{key}_{DEVICE_CODE}")
        for platform, key in entities
    }


async def test_device_is_registered_from_the_device_list(hass, entry):
    device = async_get_ha_device(hass, entry.entry_id, DEVICE_ID)

    assert device is not None
    assert device.name == "Heat pump"
    assert device.model == MODEL


async def test_device_lookup_ignores_other_entries_devices(hass, entry):
    other_entry = MockConfigEntry(domain=DOMAIN)
    other_entry.add_to_hass(hass)

    assert async_get_ha_device(hass, other_entry.entry_id, DEVICE_ID) is None


def entry_unique_ids(hass: HomeAssistant, entry: MockConfigEntry) -> set[str]:
    registry = er.async_get(hass)

    return {
        entity.unique_id
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    }


def sensor_unique_id(code: str) -> str:
    return slugify(f"{DOMAIN}_sensor_{code}_{DEVICE_CODE}")


async def test_device_gets_its_catalog_entities(hass, entry):
    # The device's product, 1132174963097280512, has no catalog of its own
    assert entry_unique_ids(hass, entry) == expected_unique_ids(
        "default", skipped=UNKNOWN_CODES
    )


async def test_codes_the_device_does_not_know_get_no_entity(hass, entry):
    unique_ids = entry_unique_ids(hass, entry)

    for code in ("F10", "O01", "S01"):
        assert sensor_unique_id(code) not in unique_ids

    assert sensor_unique_id("T02") in unique_ids
    assert climate_entity_id(hass) is not None


@cloud_with(RESPONSES | {DATA: data_untyped()})
async def test_every_code_unknown_skips_no_entity(hass, entry):
    assert entry_unique_ids(hass, entry) == expected_unique_ids("default")


async def test_entity_registered_for_an_unknown_code_is_kept(hass, config_entry):
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor", DOMAIN, sensor_unique_id("F10"), config_entry=config_entry
    )

    await set_up(hass, config_entry)

    entity_id = registry.async_get_entity_id("sensor", DOMAIN, sensor_unique_id("F10"))

    assert entity_id is not None
    # No entity provides it, so it has no state
    assert hass.states.get(entity_id) is None


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


@cloud_with(RESPONSES | {DEVICE_LIST: two_device_list()})
@pytest.mark.parametrize("device_id", [DEVICE_ID, OTHER_DEVICE_ID])
async def test_device_diagnostics_match_its_entry_in_the_config_entry_ones(
    hass, entry, device_id
):
    device = async_get_ha_device(hass, entry.entry_id, device_id)

    device_data = await async_get_device_diagnostics(hass, entry, device)
    entry_data = await async_get_config_entry_diagnostics(hass, entry)

    all_devices = entry_data.pop("devices")
    [this_device] = [
        listed
        for listed in all_devices
        if listed["device"]["data"][DEVICE_ID_PARAM] == device_id
    ]

    assert device_data == entry_data | this_device
    assert device_data["device"]["data"][DEVICE_ID_PARAM] == device_id


async def test_entry_diagnostics_list_each_device(hass, entry):
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert [device["device"]["name"] for device in diagnostics["devices"]] == [
        "Heat pump"
    ]


async def test_diagnostics_redact_the_account_email(hass, entry):
    device = async_get_ha_device(hass, entry.entry_id, DEVICE_ID)

    entry_data = await async_get_config_entry_diagnostics(hass, entry)
    device_data = await async_get_device_diagnostics(hass, entry, device)

    for data in (entry_data, device_data):
        assert data["configuration"][CONF_USERNAME] == "**REDACTED**"
        assert "test@example.com" not in json.dumps(data, default=str)
