"""Config entries for the integration tests on a real Home Assistant."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aqua_temp.common.consts import CONF_API_TYPE, DOMAIN
from custom_components.aqua_temp.managers.password_manager import PasswordManager
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant


async def add_entry(
    hass: HomeAssistant, api_type: str, options: dict | None = None
) -> MockConfigEntry:
    """A config entry, not set up, its password encrypted as the config flow
    stores it."""
    data = {
        CONF_USERNAME: "test@example.com",
        CONF_PASSWORD: "test-password",
        CONF_API_TYPE: api_type,
    }

    await PasswordManager.encrypt(hass, data)

    entry = MockConfigEntry(
        domain=DOMAIN, title="Aqua Temp", data=data, options=options or {}
    )
    entry.add_to_hass(hass)

    return entry


@pytest.fixture
async def config_entry(hass: HomeAssistant, api_type, cloud) -> MockConfigEntry:
    """A config entry added but not set up."""
    return await add_entry(hass, api_type)


@pytest.fixture
async def entry(hass: HomeAssistant, config_entry) -> MockConfigEntry:
    """The config entry set up and polled once."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    return config_entry
