"""Setting up a config entry on a real Home Assistant: failures, timing, the
entry's options, and data stored by older versions."""

import logging

from cryptography.fernet import Fernet
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aqua_temp.common.consts import CONF_API_TYPE, DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, EVENT_HOMEASSISTANT_START
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import entity_registry as er
from tests.cloud.mock_cloud import cloud_with

from .conftest import add_entry

# Literal on purpose: the expected values must not come from the config under test
LOGIN = "app/user/login"
DATA = "app/device/getDataByCode"
CONFIG_STORE = "aqua_temp.config.json"
LEGACY_KEY_STORE = ".aqua_temp"

RESPONSES = {DATA: "get_data_by_code.idle"}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


@pytest.fixture
def cloud_responses() -> dict:
    return RESPONSES


async def set_up(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def entities(hass: HomeAssistant, entry: MockConfigEntry) -> list:
    return er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)


def stored(key: str, data: dict) -> dict:
    """A Home Assistant store file's contents, as hass_storage holds them."""
    return {"version": 1, "minor_version": 1, "key": key, "data": data}


def entry_with_password(hass: HomeAssistant, api_type: str, password: str):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Aqua Temp",
        data={
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: password,
            CONF_API_TYPE: api_type,
        },
    )
    entry.add_to_hass(hass)

    return entry


@cloud_with(RESPONSES | {LOGIN: "synthetic/login_rejected"})
async def test_rejected_login_fails_setup(hass, api_type, cloud):
    entry = await add_entry(hass, api_type)

    await set_up(hass, entry)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entities(hass, entry) == []


async def test_password_the_key_cannot_decrypt_fails_setup(hass, api_type, cloud, wire):
    entry = entry_with_password(hass, api_type, "not-encrypted")

    await set_up(hass, entry)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert wire == []


async def test_unknown_api_type_fails_setup(hass, cloud, wire):
    entry = await add_entry(hass, "unknown")

    await set_up(hass, entry)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert wire == []


@cloud_with(RESPONSES | {LOGIN: [500, "synthetic/login"]})
async def test_cloud_error_at_setup_retries_on_the_first_update(
    hass, api_type, cloud, wire
):
    entry = await add_entry(hass, api_type)

    await set_up(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert [endpoint for endpoint, _ in wire].count(LOGIN) == 2
    assert entities(hass, entry) != []


async def test_setup_before_start_waits_for_home_assistant(hass, api_type, cloud, wire):
    hass.set_state(CoreState.not_running)
    entry = await add_entry(hass, api_type)

    await set_up(hass, entry)
    requests_before_start = list(wire)

    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert requests_before_start == []
    assert wire[0][0] == LOGIN
    assert entities(hass, entry) != []


async def test_unload_leaves_the_entities_unavailable(hass, api_type, cloud):
    entry = await add_entry(hass, api_type)
    await set_up(hass, entry)

    assert await hass.config_entries.async_unload(entry.entry_id)

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert entry.entry_id not in hass.data[DOMAIN]
    assert {
        hass.states.get(entity.entity_id).state for entity in entities(hass, entry)
    } == {"unavailable"}


async def test_entry_option_logs_the_session_token(hass, api_type, cloud, caplog):
    entry = await add_entry(hass, api_type, options={"log_session_token": True})

    with caplog.at_level(logging.WARNING):
        await set_up(hass, entry)

    assert (
        "[session-token] Aqua Temp: CREDENTIAL, do not share. "
        "Valid until the next login. export AQUATEMP_X_TOKEN='test-token'"
    ) in [record.getMessage() for record in caplog.records]


async def test_session_token_is_not_logged_without_the_option(
    hass, api_type, cloud, caplog
):
    entry = await add_entry(hass, api_type)

    with caplog.at_level(logging.INFO):
        await set_up(hass, entry)

    assert "test-token" not in caplog.text


@pytest.mark.parametrize("legacy_api_type", ["1", "2"])
async def test_legacy_api_type_sets_up(hass, cloud, wire, legacy_api_type):
    """Older versions stored the API type as a number: 1 Aqua Temp, 2 Hitemp,
    both served from the URLs mocked here."""
    entry = await add_entry(hass, legacy_api_type)

    await set_up(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert wire[0][0] == LOGIN


async def test_key_from_the_legacy_key_store_is_moved(
    hass, hass_storage, api_type, cloud
):
    key = Fernet.generate_key().decode()
    hass_storage[LEGACY_KEY_STORE] = stored(LEGACY_KEY_STORE, {"key": key})
    password = Fernet(key.encode()).encrypt(b"test-password").decode()
    entry = entry_with_password(hass, api_type, password)

    await set_up(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert LEGACY_KEY_STORE not in hass_storage
    assert hass_storage[CONFIG_STORE]["data"]["key"] == key


async def test_key_stored_under_the_entry_is_copied(
    hass, hass_storage, api_type, cloud
):
    key = Fernet.generate_key().decode()
    password = Fernet(key.encode()).encrypt(b"test-password").decode()
    entry = entry_with_password(hass, api_type, password)
    hass_storage[CONFIG_STORE] = stored(
        CONFIG_STORE, {entry.entry_id: {"key": key, "temperature_unit": {}}}
    )

    await set_up(hass, entry)

    # Possible bug: the entry's copy is meant to be removed, but it is popped
    # from data the store then reloads, so it stays
    assert entry.state is ConfigEntryState.LOADED
    assert hass_storage[CONFIG_STORE]["data"] == {
        "key": key,
        entry.entry_id: {"key": key, "temperature_unit": {}},
    }


async def test_credentials_stored_by_older_versions_are_dropped(
    hass, hass_storage, api_type, cloud
):
    entry = await add_entry(hass, api_type)
    key = hass_storage[CONFIG_STORE]["data"]["key"]
    hass_storage[CONFIG_STORE] = stored(
        CONFIG_STORE,
        {
            "key": key,
            "config": {"temperature_unit": {}},
            entry.entry_id: {
                "username": "old@example.com",
                "password": "old-password",
                "temperature_unit": {"000000000001": "°F"},
            },
        },
    )

    await set_up(hass, entry)

    assert hass_storage[CONFIG_STORE]["data"] == {
        "key": key,
        entry.entry_id: {"temperature_unit": {"000000000001": "°F"}},
    }
