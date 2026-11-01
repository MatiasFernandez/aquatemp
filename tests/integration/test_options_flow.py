"""Options flow on a real Home Assistant: editing an entry's credentials, title,
polling interval, request timeout and session token logging."""

import pytest
import voluptuous as vol

from custom_components.aqua_temp.managers.password_manager import PasswordManager
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from tests.cloud.mock_cloud import DATA, DATA_IDLE, cloud_with

# Literal on purpose: the expected values must not come from the config under test
LOGIN = "app/user/login"

RESPONSES = {DATA: DATA_IDLE}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


@pytest.fixture
def cloud_responses() -> dict:
    return RESPONSES


def defaults(result) -> dict:
    return {str(key): key.default() for key in result["data_schema"].schema}


def new_settings(api_type: str) -> dict:
    return {
        "title": "Pool",
        "username": "new@example.com",
        "password": "new-password",
        "api_type": api_type,
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
    # Possible bug: the password is decrypted and sent to the frontend as the
    # field's default
    assert defaults(result) == {
        "title": "Aqua Temp",
        "username": "test@example.com",
        "password": "test-password",
        "api_type": api_type,
        "update_interval": 300,
        "request_timeout": 10,
        "log_session_token": False,
    }


async def test_new_settings_update_the_entry(hass, api_type, entry):
    result = await submit(hass, entry, new_settings(api_type))

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.title == "Pool"
    assert entry.options == {
        "update_interval": 60,
        "request_timeout": 15,
        "log_session_token": True,
    }
    assert await decrypted(hass, entry) == {
        "username": "new@example.com",
        "password": "new-password",
        "api_type": api_type,
    }
    assert entry.data["password"] != "new-password"


async def test_new_settings_are_checked_then_used_after_a_reload(
    hass, api_type, entry, wire
):
    wire.clear()

    await submit(hass, entry, new_settings(api_type))

    logins = [body for endpoint, body in wire if endpoint == LOGIN]

    # One login checks the credentials, one is the reloaded entry's
    assert entry.state is ConfigEntryState.LOADED
    assert [login["userName"] for login in logins] == [
        "new@example.com",
        "new@example.com",
    ]


@cloud_with(RESPONSES | {LOGIN: ["synthetic/login", "synthetic/login_rejected"]})
async def test_rejected_credentials_keep_the_entry(hass, api_type, entry):
    before = (entry.title, dict(entry.data), dict(entry.options))

    result = await submit(hass, entry, new_settings(api_type))

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_credentials"}
    assert (entry.title, dict(entry.data), dict(entry.options)) == before


@cloud_with(RESPONSES | {LOGIN: ["synthetic/login", TimeoutError()]})
async def test_new_settings_are_checked_with_the_new_timeout(hass, api_type, entry):
    # Possible bug: the form doesn't catch a timeout, so Home Assistant shows
    # an unknown error instead of saying the cloud can't be reached
    with pytest.raises(TimeoutError, match=rf"Request to {LOGIN} timed out after 15 s"):
        await submit(hass, entry, new_settings(api_type))


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
            result["flow_id"], new_settings(api_type) | {field: value}
        )
