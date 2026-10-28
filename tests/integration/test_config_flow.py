"""Config flow credential check: the session it validates with is released."""

from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientSession, TCPConnector
import pytest

from custom_components.aqua_temp.common.consts import CONF_API_TYPE
from custom_components.aqua_temp.managers.flow_manager import IntegrationFlowManager
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from tests.cloud.mock_cloud import cloud_with

LOGIN = "app/user/login"

FLOW_MANAGER = "custom_components.aqua_temp.managers.flow_manager"
CONFIG_MANAGER = "custom_components.aqua_temp.managers.aqua_temp_config_manager"


@pytest.fixture
async def shared_connector():
    """Stands in for Home Assistant's connector pool, which outlives any session."""
    connector = TCPConnector()

    yield connector

    await connector.close()


@pytest.fixture
def flow_session(shared_connector):
    """Patch HA's session factory where the flow uses it.

    Also stubs the storage and translations a hass would provide. Yields
    (factory, session).
    """
    session = ClientSession(connector=shared_connector, connector_owner=False)
    session.detach = MagicMock(wraps=session.detach)
    factory = MagicMock(return_value=session)
    empty_store = AsyncMock(async_load=AsyncMock(return_value=None))

    with (
        patch(f"{FLOW_MANAGER}.async_create_clientsession", factory, create=True),
        patch(f"{FLOW_MANAGER}.PasswordManager.encrypt", new=AsyncMock()),
        patch(f"{CONFIG_MANAGER}.Store", return_value=empty_store),
        patch(
            f"{CONFIG_MANAGER}.translation.async_get_translations",
            new=AsyncMock(return_value={}),
        ),
    ):
        yield factory, session


async def submit(api_type: str) -> MagicMock:
    """Submit the user step of the config flow; returns the flow handler."""
    flow_handler = MagicMock()
    flow_manager = IntegrationFlowManager(MagicMock(), flow_handler)

    await flow_manager.async_step(
        {
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "test-password",
            CONF_API_TYPE: api_type,
        }
    )

    return flow_handler


def assert_released(factory: MagicMock, session: ClientSession) -> None:
    # Not tied to HA shutdown, and detached rather than closed, which would act
    # on the shared connector
    factory.assert_called_once()
    assert factory.call_args.kwargs.get("auto_cleanup", True) is False
    session.detach.assert_called_once_with()
    assert session.closed


async def test_valid_credentials_release_the_session(api_type, cloud, flow_session):
    factory, session = flow_session

    flow_handler = await submit(api_type)

    flow_handler.async_create_entry.assert_called_once()
    assert_released(factory, session)


@cloud_with({LOGIN: "synthetic/login_rejected"})
async def test_rejected_credentials_release_the_session(api_type, cloud, flow_session):
    factory, session = flow_session

    flow_handler = await submit(api_type)

    assert flow_handler.async_show_form.call_args.kwargs["errors"] == {
        "base": "invalid_credentials"
    }
    assert_released(factory, session)
