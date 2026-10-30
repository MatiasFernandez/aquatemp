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

LOGIN = "app/user/login"

FLOW_MANAGER = "custom_components.aqua_temp.managers.flow_manager"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


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
