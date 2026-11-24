"""Config flow on a real Home Assistant: the form, the entry it creates, and the
credential check's session, which is released."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.aqua_temp.common.consts import CONF_API_TYPE, DOMAIN
from custom_components.aqua_temp.managers.password_manager import PasswordManager
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from tests.cloud.mock_cloud import cloud_with
from tests.harness import MockConfigEntry

from .conftest import add_entry

LOGIN = "app/user/login"

FLOW_MANAGER = "custom_components.aqua_temp.managers.flow_manager"


@pytest.fixture
def flow_sessions():
    """Spy on the sessions the flow creates through HA's factory.

    Yields (calls, sessions): the keyword arguments of each call, and the
    sessions returned, which are real and share HA's connector.
    """
    calls = []
    sessions = []

    def create(*args, **kwargs):
        calls.append(kwargs)
        session = async_create_clientsession(*args, **kwargs)
        session.detach = MagicMock(wraps=session.detach)
        sessions.append(session)

        return session

    with patch(f"{FLOW_MANAGER}.async_create_clientsession", create):
        yield calls, sessions


async def submit(hass, api_type: str) -> dict:
    """Open the user step and submit the credentials; returns the flow result."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "test-password",
            CONF_API_TYPE: api_type,
        },
    )


def assert_released(calls: list[dict], sessions: list) -> None:
    # Not tied to HA shutdown, and detached rather than closed, which would act
    # on the shared connector
    assert len(calls) == 1
    assert calls[0].get("auto_cleanup", True) is False
    sessions[0].detach.assert_called_once_with()
    assert sessions[0].closed


def defaults(result) -> dict:
    """Each field's default, None for a field without one."""
    return {
        str(key): key.default() if callable(key.default) else None
        for key in result["data_schema"].schema
    }


async def test_valid_credentials_release_the_session(
    hass, api_type, cloud, flow_sessions
):
    result = await submit(hass, api_type)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert_released(*flow_sessions)


@cloud_with({LOGIN: "synthetic/login_rejected"})
async def test_rejected_credentials_release_the_session(
    hass, api_type, cloud, flow_sessions
):
    result = await submit(hass, api_type)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_credentials"}
    assert_released(*flow_sessions)


async def test_form_starts_with_the_default_title(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert {str(key): key.default() for key in result["data_schema"].schema} == {
        "title": "Aqua Temp",
        "username": None,
        "password": None,
        "api_type": None,
    }


async def test_valid_credentials_create_an_entry_with_the_password_encrypted(
    hass, api_type, cloud
):
    result = await submit(hass, api_type)
    await hass.async_block_till_done()

    data = dict(result["data"])
    await PasswordManager.decrypt(hass, data)

    assert result["title"] == "Aqua Temp"
    assert result["data"][CONF_PASSWORD] != "test-password"
    assert data == {
        CONF_USERNAME: "test@example.com",
        CONF_PASSWORD: "test-password",
        CONF_API_TYPE: api_type,
    }


async def reauth(hass, entry, password: str | None = None) -> dict:
    """Open the reauth step, then submit password if given; returns the result."""
    result = await entry.start_reauth_flow(hass)

    if password is None:
        return result

    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: password}
    )


async def test_reauth_asks_only_for_the_password(hass, api_type, cloud):
    entry = await add_entry(hass, api_type)

    result = await reauth(hass, entry)

    assert (result["step_id"], [str(key) for key in result["data_schema"].schema]) == (
        "reauth_confirm",
        [CONF_PASSWORD],
    )


async def test_reauth_stores_the_new_password_encrypted(hass, api_type, cloud):
    entry = await add_entry(hass, api_type)

    result = await reauth(hass, entry, "new-password")
    await hass.async_block_till_done()

    data = dict(entry.data)
    await PasswordManager.decrypt(hass, data)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] != "new-password"
    assert data == {
        CONF_USERNAME: "test@example.com",
        CONF_PASSWORD: "new-password",
        CONF_API_TYPE: api_type,
    }


@cloud_with({LOGIN: "synthetic/login_rejected"})
async def test_reauth_with_a_rejected_password_asks_again(hass, api_type, cloud):
    entry = await add_entry(hass, api_type)
    stored_password = entry.data[CONF_PASSWORD]

    result = await reauth(hass, entry, "wrong-password")

    assert (result["type"], result["errors"]) == (
        FlowResultType.FORM,
        {"base": "invalid_credentials"},
    )
    assert entry.data[CONF_PASSWORD] == stored_password


# The account's id in the user info the mocked cloud serves
ACCOUNT_ID = "test-user"


async def test_new_entry_is_identified_by_the_cloud_account(hass, api_type, cloud):
    result = await submit(hass, api_type)
    await hass.async_block_till_done()

    assert result["result"].unique_id == ACCOUNT_ID


async def test_account_already_set_up_is_not_added_again(hass, api_type, cloud):
    MockConfigEntry(domain=DOMAIN, unique_id=ACCOUNT_ID).add_to_hass(hass)

    result = await submit(hass, api_type)

    assert (result["type"], result["reason"]) == (
        FlowResultType.ABORT,
        "already_configured",
    )


async def reconfigure(hass, entry, user_input: dict | None = None) -> dict:
    """Open the reconfigure step, then submit user_input if given."""
    result = await entry.start_reconfigure_flow(hass)

    if user_input is None:
        return result

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    await hass.async_block_till_done()

    return result


def new_credentials(api_type: str) -> dict:
    return {
        CONF_USERNAME: "new@example.com",
        CONF_PASSWORD: "new-password",
        CONF_API_TYPE: api_type,
    }


async def test_reconfigure_shows_the_credentials_without_the_password(
    hass, api_type, cloud
):
    entry = await add_entry(hass, api_type)

    result = await reconfigure(hass, entry)

    assert (result["step_id"], defaults(result)) == (
        "reconfigure",
        {
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: None,
            CONF_API_TYPE: api_type,
        },
    )


async def test_reconfigure_stores_the_new_credentials_encrypted(hass, api_type, cloud):
    entry = await add_entry(hass, api_type)

    result = await reconfigure(hass, entry, new_credentials(api_type))

    data = dict(entry.data)
    await PasswordManager.decrypt(hass, data)

    assert (result["type"], result["reason"]) == (
        FlowResultType.ABORT,
        "reconfigure_successful",
    )
    assert entry.data[CONF_PASSWORD] != "new-password"
    assert (data, entry.unique_id) == (new_credentials(api_type), ACCOUNT_ID)


@cloud_with({LOGIN: "synthetic/login_rejected"})
async def test_reconfigure_with_rejected_credentials_keeps_the_entry(
    hass, api_type, cloud
):
    entry = await add_entry(hass, api_type)
    before = dict(entry.data)

    result = await reconfigure(hass, entry, new_credentials(api_type))

    assert (result["type"], result["errors"]) == (
        FlowResultType.FORM,
        {"base": "invalid_credentials"},
    )
    assert dict(entry.data) == before


async def test_reconfigure_to_an_account_another_entry_uses_is_refused(
    hass, api_type, cloud
):
    MockConfigEntry(domain=DOMAIN, unique_id=ACCOUNT_ID).add_to_hass(hass)
    entry = await add_entry(hass, api_type)
    before = dict(entry.data)

    result = await reconfigure(hass, entry, new_credentials(api_type))

    assert (result["type"], result["reason"]) == (
        FlowResultType.ABORT,
        "already_configured",
    )
    assert dict(entry.data) == before
