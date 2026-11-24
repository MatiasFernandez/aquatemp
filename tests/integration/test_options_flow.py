"""Options flow on a real Home Assistant: editing an entry's title, polling
interval, request timeout and session token logging. The credentials are
changed through the reconfigure step, in test_config_flow.py."""

import pytest
import voluptuous as vol

from custom_components.aqua_temp.managers.password_manager import PasswordManager
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from tests.cloud.mock_cloud import DATA, DATA_IDLE

# Literal on purpose: the expected values must not come from the config under test
LOGIN = "app/user/login"

RESPONSES = {DATA: DATA_IDLE}


@pytest.fixture
def cloud_responses() -> dict:
    return RESPONSES


def defaults(result) -> dict:
    return {str(key): key.default() for key in result["data_schema"].schema}


def new_settings() -> dict:
    return {
        "title": "Pool",
        "update_interval": 60,
        "request_timeout": 15,
        "log_session_token": True,
    }


async def submit(hass, entry, user_input: dict):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )
    await hass.async_block_till_done()

    return result


async def decrypted(hass, entry) -> dict:
    data = dict(entry.data)

    await PasswordManager.decrypt(hass, data, entry.entry_id)

    return data


async def test_form_shows_the_entry_settings(hass, api_type, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    # No credentials: the password is no longer sent to the frontend
    assert defaults(result) == {
        "title": "Aqua Temp",
        "update_interval": 300,
        "request_timeout": 10,
        "log_session_token": False,
    }


async def test_new_settings_update_the_entry(hass, api_type, entry):
    data_before = dict(entry.data)

    result = await submit(hass, entry, new_settings())

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.title == "Pool"
    assert entry.options == {
        "update_interval": 60,
        "request_timeout": 15,
        "log_session_token": True,
    }
    assert dict(entry.data) == data_before


async def test_new_settings_are_used_after_a_reload_without_a_login_check(
    hass, api_type, entry, wire
):
    wire.clear()

    await submit(hass, entry, new_settings())

    # Only the reloaded entry logs in: there are no credentials to check
    assert entry.state is ConfigEntryState.LOADED
    assert [endpoint for endpoint, _ in wire].count(LOGIN) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("update_interval", 29, id="polling-too-often"),
        pytest.param("update_interval", 3601, id="polling-too-rarely"),
        pytest.param("request_timeout", 4, id="timeout-too-short"),
        pytest.param("request_timeout", 61, id="timeout-too-long"),
    ],
)
async def test_out_of_range_settings_are_refused(hass, api_type, entry, field, value):
    result = await hass.config_entries.options.async_init(entry.entry_id)

    with pytest.raises(vol.Invalid, match=f"'{field}'"):
        await hass.config_entries.options.async_configure(
            result["flow_id"], new_settings() | {field: value}
        )
