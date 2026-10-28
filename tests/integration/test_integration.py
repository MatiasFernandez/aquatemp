"""The integration on a real Home Assistant, against the mocked cloud.

Covers the HA side of the cloud library boundary: the client's new-device
callback turning into entities, the device list into the device registry and
diagnostics, modes crossing between HVACMode and the library's Mode, the
climate's temperatures and writes, and the temperature unit select.
Expected values are literal or read from the profile files, never from the
code under test.
"""

from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.aqua_temp.cloud.exceptions import OperationFailedException
from custom_components.aqua_temp.common.consts import DOMAIN
from custom_components.aqua_temp.common.device_lookup import async_get_ha_device
from custom_components.aqua_temp.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)
from homeassistant.const import CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.update_coordinator import REQUEST_REFRESH_DEFAULT_COOLDOWN
from homeassistant.util import dt as dt_util, slugify
from tests.cloud.mock_cloud import (
    DATA,
    DATA_IDLE,
    DEVICE_CODE,
    cloud_with,
    data_untyped,
    data_with,
    load_fixture,
)

CONTROL = "app/device/control"
DEVICE_LIST = "app/device/deviceList"
STATUS = "app/device/getDeviceStatus"

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
    DATA: DATA_IDLE,
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


async def set_up(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    return entry


def entity_id(hass: HomeAssistant, platform: str, key: str) -> str | None:
    unique_id = slugify(f"{DOMAIN}_{platform}_{key}_{DEVICE_CODE}")

    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)


def climate_entity_id(hass: HomeAssistant) -> str:
    return entity_id(hass, "climate", "Mode")


def refresh_button_entity_id(hass: HomeAssistant) -> str:
    return entity_id(hass, "button", "refresh_data")


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
        ("button", "refresh_data"),
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


async def test_water_delta_t_is_created(hass, entry):
    assert sensor_unique_id("water_delta_t") in entry_unique_ids(hass, entry)


# T03 is the default mapping's outlet water temperature
@cloud_with(RESPONSES | {DATA: data_untyped("T03")})
async def test_water_delta_t_is_skipped_when_an_input_is_unknown(hass, entry):
    assert sensor_unique_id("water_delta_t") not in entry_unique_ids(hass, entry)


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


async def test_entity_ids_name_the_device_once(hass, entry):
    assert entity_id(hass, "sensor", "water_delta_t") == "sensor.heat_pump_water_dt"
    assert climate_entity_id(hass) == "climate.heat_pump"


async def test_entity_ids_use_the_device_name_given_in_home_assistant(
    hass, config_entry
):
    # The device renamed before its entities were registered
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={(DOMAIN, DEVICE_ID)}
    )
    dr.async_get(hass).async_update_device(device.id, name_by_user="Pool")

    await set_up(hass, config_entry)

    assert entity_id(hass, "sensor", "water_delta_t") == "sensor.pool_water_dt"
    assert climate_entity_id(hass) == "climate.pool"


async def test_entity_names_follow_the_device_name(hass, entry):
    device = async_get_ha_device(hass, entry.entry_id, DEVICE_ID)

    dr.async_get(hass).async_update_device(device.id, name_by_user="Pool")
    await hass.async_block_till_done()

    water_delta_t = hass.states.get(entity_id(hass, "sensor", "water_delta_t"))
    climate = hass.states.get(climate_entity_id(hass))

    assert water_delta_t.attributes["friendly_name"] == "Pool Water ΔT"
    assert climate.attributes["friendly_name"] == "Pool"


async def test_registered_entities_keep_their_entity_id(hass, config_entry):
    # As registered while the integration named entities itself, for a
    # device renamed in Home Assistant
    registered = er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        slugify(f"{DOMAIN}_sensor_water_delta_t_{DEVICE_CODE}"),
        suggested_object_id="pool_heat_pump_water_dt",
        config_entry=config_entry,
    )

    await set_up(hass, config_entry)

    assert entity_id(hass, "sensor", "water_delta_t") == registered.entity_id
    assert hass.states.get(registered.entity_id) is not None


async def test_device_entities_are_added_once(hass, entry):
    registry = er.async_get(hass)
    before = len(er.async_entries_for_config_entry(registry, entry.entry_id))

    await hass.data[DOMAIN][entry.entry_id].async_refresh()
    await hass.async_block_till_done()

    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == before


async def test_pressing_refresh_data_polls_the_cloud(hass, entry, wire, freezer):
    # Setup leaves a refresh waiting out the debounce; let it poll first
    freezer.tick(timedelta(seconds=REQUEST_REFRESH_DEFAULT_COOLDOWN))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    wire.clear()

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": refresh_button_entity_id(hass)},
        blocking=True,
    )
    # The refresh a press requests waits out the coordinator's debounce
    freezer.tick(timedelta(seconds=REQUEST_REFRESH_DEFAULT_COOLDOWN))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert [endpoint for endpoint, _ in wire] == [DATA, STATUS]


@cloud_with(RESPONSES | {DATA: [DATA_IDLE, 500, 500, 500]})
async def test_refresh_data_stays_available_after_a_failed_update(hass, entry, freezer):
    with patch("custom_components.aqua_temp.cloud.client.sleep"):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": refresh_button_entity_id(hass)},
            blocking=True,
        )
        freezer.tick(timedelta(seconds=REQUEST_REFRESH_DEFAULT_COOLDOWN))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    assert hass.states.get(climate_entity_id(hass)).state == "unavailable"
    assert hass.states.get(refresh_button_entity_id(hass)).state != "unavailable"


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


def temperatures(state) -> dict:
    return {
        attribute: state.attributes[attribute]
        for attribute in ("current_temperature", "temperature", "min_temp", "max_temp")
    }


def powered_on_in(mode: str) -> dict:
    return RESPONSES | {DATA: data_with(Power="1", Mode=mode)}


# Recorded: T02 13.0, R01 27.0, R02 28.0, R03 27.0, R08 8.0, R09 35.0, R10 15.0,
# R11 35.0. Each mode reads its own target, minimum and maximum codes
@pytest.mark.parametrize(
    ("cloud_responses", "expected"),
    [
        pytest.param(
            powered_on_in("0"),
            {
                "current_temperature": 13.0,
                "temperature": 27.0,
                "min_temp": 8.0,
                "max_temp": 35.0,
            },
            id="cool",
        ),
        pytest.param(
            powered_on_in("1"),
            {
                "current_temperature": 13.0,
                "temperature": 28.0,
                "min_temp": 15.0,
                "max_temp": 35.0,
            },
            id="heat",
        ),
        pytest.param(
            powered_on_in("2"),
            {
                "current_temperature": 13.0,
                "temperature": 27.0,
                "min_temp": 8.0,
                "max_temp": 35.0,
            },
            id="auto",
        ),
    ],
)
async def test_climate_reports_the_mode_temperatures(hass, entry, expected):
    state = hass.states.get(climate_entity_id(hass))

    assert temperatures(state) == expected


async def test_climate_reports_temperatures_while_powered_off(hass, entry):
    # The recorded Mode, heat, still picks the codes
    state = hass.states.get(climate_entity_id(hass))

    assert temperatures(state) == {
        "current_temperature": 13.0,
        "temperature": 28.0,
        "min_temp": 15.0,
        "max_temp": 35.0,
    }


@cloud_with(RESPONSES | {DATA: data_with(Power="1", T02="", R02="", R10="", R11="")})
async def test_climate_temperatures_the_device_does_not_know_are_empty(hass, entry):
    state = hass.states.get(climate_entity_id(hass))

    assert temperatures(state) == {
        "current_temperature": None,
        "temperature": None,
        "min_temp": None,
        "max_temp": None,
    }


@cloud_with(POWERED_ON)
async def test_setting_temperature_writes_the_mode_target(hass, entry, wire):
    wire.clear()

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": climate_entity_id(hass), "temperature": 26.5},
        blocking=True,
    )

    assert wire == [
        (
            CONTROL,
            {
                "param": [
                    {"deviceCode": DEVICE_CODE, "protocolCode": "R02", "value": 26.5},
                    {
                        "deviceCode": DEVICE_CODE,
                        "protocolCode": "Set_Temp",
                        "value": 26.5,
                    },
                ]
            },
        )
    ]


@cloud_with(POWERED_ON)
async def test_device_is_read_again_after_a_write(hass, entry, wire, freezer):
    wire.clear()

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": climate_entity_id(hass), "temperature": 26.5},
        blocking=True,
    )
    # The refresh a write requests waits out the coordinator's debounce
    freezer.tick(timedelta(seconds=REQUEST_REFRESH_DEFAULT_COOLDOWN))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert [endpoint for endpoint, _ in wire] == [CONTROL, DATA, STATUS]


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


def unit_entity_id(hass: HomeAssistant) -> str:
    unique_id = slugify(f"{DOMAIN}_select_temperature_unit_{DEVICE_CODE}")

    return er.async_get(hass).async_get_entity_id("select", DOMAIN, unique_id)


async def select_unit(hass: HomeAssistant, unit: str) -> None:
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": unit_entity_id(hass), "option": unit},
        blocking=True,
    )


async def test_temperature_unit_defaults_to_celsius(hass, entry):
    assert hass.states.get(unit_entity_id(hass)).state == "°C"


async def test_selected_temperature_unit_shows_after_the_next_refresh(
    hass, entry, freezer
):
    await select_unit(hass, "°F")
    shown_at_once = hass.states.get(unit_entity_id(hass)).state

    freezer.tick(timedelta(seconds=REQUEST_REFRESH_DEFAULT_COOLDOWN))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert shown_at_once == "°C"
    assert hass.states.get(unit_entity_id(hass)).state == "°F"


async def test_selecting_a_temperature_unit_writes_nothing_to_the_device(
    hass, entry, wire, freezer
):
    wire.clear()

    await select_unit(hass, "°F")
    freezer.tick(timedelta(seconds=REQUEST_REFRESH_DEFAULT_COOLDOWN))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert [endpoint for endpoint, _ in wire] == [DATA, STATUS]


async def test_reload_resets_the_temperature_unit(hass, entry, freezer):
    await select_unit(hass, "°F")
    freezer.tick(timedelta(seconds=REQUEST_REFRESH_DEFAULT_COOLDOWN))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    # Possible bug: unloading removes the entry's stored configuration, so the
    # unit picked is lost on every reload, including after an options change
    assert hass.states.get(unit_entity_id(hass)).state == "°C"


async def test_climate_keeps_its_temperature_unit_when_another_is_selected(
    hass, entry, freezer
):
    await select_unit(hass, "°F")
    freezer.tick(timedelta(seconds=REQUEST_REFRESH_DEFAULT_COOLDOWN))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    # Possible bug: the climate reads the unit once, when it is created, and a
    # reload resets the unit, so a unit other than Celsius never reaches it
    assert temperatures(hass.states.get(climate_entity_id(hass)))["temperature"] == 28.0


async def set_temperature(hass: HomeAssistant, temperature: float):
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": climate_entity_id(hass), "temperature": temperature},
        blocking=True,
    )


async def past_refresh_cooldowns(hass: HomeAssistant):
    """Move past the coordinator's 10 s refresh cooldown twice, so a refresh
    requested during one runs, and the cooldown it starts ends too.

    Setup requests a refresh while one is cooling down, so one is still
    waiting to run after setup."""
    for seconds in (11, 22):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
        await hass.async_block_till_done()


@cloud_with(POWERED_ON | {CONTROL: "control.device_timeout"})
async def test_control_the_device_did_not_acknowledge_fails_with_a_clear_error(
    hass, entry
):
    with pytest.raises(HomeAssistantError) as failure:
        await set_temperature(hass, 26.5)

    assert failure.value.translation_key == "device_not_responding"


@cloud_with(POWERED_ON | {CONTROL: "synthetic/error_generic"})
async def test_failed_control_polls_the_device_again(hass, entry, wire):
    await past_refresh_cooldowns(hass)
    wire.clear()

    with pytest.raises(OperationFailedException):
        await set_temperature(hass, 26.5)
    await hass.async_block_till_done()

    assert DATA in [endpoint for endpoint, _ in wire]


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


async def test_entry_diagnostics_list_each_device_unknown_codes(hass, entry):
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert [device["device"]["unknown_codes"] for device in diagnostics["devices"]] == [
        sorted(UNKNOWN_CODES)
    ]


async def test_device_diagnostics_list_its_unknown_codes(hass, entry):
    device = async_get_ha_device(hass, entry.entry_id, DEVICE_ID)

    diagnostics = await async_get_device_diagnostics(hass, entry, device)

    assert diagnostics["device"]["unknown_codes"] == sorted(UNKNOWN_CODES)


def status_entity_id(hass: HomeAssistant) -> str:
    unique_id = slugify(f"{DOMAIN}_binary_sensor_device_status_{DEVICE_CODE}")

    return er.async_get(hass).async_get_entity_id("binary_sensor", DOMAIN, unique_id)


@pytest.mark.parametrize(
    ("cloud_responses", "state"),
    [
        pytest.param(
            RESPONSES | {"app/device/getDeviceStatus": "device_status.online"},
            "on",
            id="online",
        ),
        pytest.param(
            RESPONSES | {"app/device/getDeviceStatus": "device_status.offline"},
            "off",
            id="offline",
        ),
        pytest.param(
            RESPONSES
            | {
                "app/device/getDeviceStatus": {
                    "error_code": "0",
                    "error_msg": "Success",
                    "objectResult": {"isFault": False},
                }
            },
            "unavailable",
            id="missing",
        ),
        pytest.param(
            RESPONSES
            | {
                "app/device/getDeviceStatus": {
                    "error_code": "0",
                    "error_msg": "Success",
                    "objectResult": {"isFault": False, "status": "UPDATING"},
                }
            },
            "unavailable",
            id="unknown",
        ),
    ],
)
async def test_status_sensor_follows_the_online_state(hass, entry, state):
    assert hass.states.get(status_entity_id(hass)).state == state


@cloud_with(
    RESPONSES
    | {
        "app/device/getDeviceStatus": [
            {
                "error_code": "0",
                "error_msg": "Success",
                "objectResult": {"isFault": False, "status": "UPDATING"},
            },
            "device_status.online",
        ]
    }
)
async def test_status_sensor_recovers_from_an_unknown_state(hass, entry):
    await hass.data[DOMAIN][entry.entry_id].async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(status_entity_id(hass)).state == "on"


STATUS = "app/device/getDeviceStatus"


def unique_id(platform: str, key: str) -> str:
    return slugify(f"{DOMAIN}_{platform}_{key}_{DEVICE_CODE}")


def available_states(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, str]:
    """The state of each of the entry's enabled entities that is available,
    by unique id."""
    registry = er.async_get(hass)
    states = {
        registry_entry.unique_id: hass.states.get(registry_entry.entity_id).state
        for registry_entry in er.async_entries_for_config_entry(
            registry, entry.entry_id
        )
        if registry_entry.disabled_by is None
    }

    return {key: state for key, state in states.items() if state != "unavailable"}


@cloud_with(RESPONSES | {STATUS: "device_status.offline"})
async def test_offline_device_shows_only_what_is_not_its_values(hass, entry):
    # Its values are the cloud's last cached ones
    assert available_states(hass, entry) == {
        unique_id("binary_sensor", "api_status"): "on",
        unique_id("binary_sensor", "device_status"): "off",
        unique_id("select", "temperature_unit"): "°C",
        unique_id("button", "refresh_data"): "unknown",
    }


@cloud_with(RESPONSES | {STATUS: ["device_status.offline", "device_status.online"]})
async def test_device_values_are_available_again_once_online(hass, entry, freezer):
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": refresh_button_entity_id(hass)},
        blocking=True,
    )
    freezer.tick(timedelta(seconds=REQUEST_REFRESH_DEFAULT_COOLDOWN))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(climate_entity_id(hass)).state == "off"


@cloud_with(RESPONSES | {STATUS: ["device_status.online", "device_status.offline"]})
async def test_control_to_a_device_that_went_offline_fails_with_a_clear_error(
    hass, entry
):
    """Turning it on reads the device again before setting the mode, and finds
    it offline."""
    with pytest.raises(HomeAssistantError) as failure:
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": climate_entity_id(hass), "hvac_mode": "heat"},
            blocking=True,
        )

    assert failure.value.translation_key == "device_offline"
