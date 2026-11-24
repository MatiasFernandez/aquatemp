import logging

from cryptography.fernet import InvalidToken

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv

from .common.consts import DOMAIN, INVALID_TOKEN_SECTION
from .managers.aqua_temp_config_manager import AquaTempConfigManager
from .managers.aqua_temp_coordinator import AquaTempCoordinator
from .managers.password_manager import PasswordManager

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type AquaTempConfigEntry = ConfigEntry[AquaTempCoordinator]


async def async_setup(_hass, _config):
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AquaTempConfigEntry) -> bool:
    """Set up an Aqua Temp account: log in, read its devices, then the platforms.

    The first poll runs here, so a rejected login asks the user to log in again
    (ConfigEntryAuthFailed) and a cloud or network failure retries the setup
    later (ConfigEntryNotReady), both raised by the coordinator.
    """
    entry_config = dict(entry.data)

    try:
        await PasswordManager.decrypt(hass, entry_config, entry.entry_id)

    except InvalidToken as ex:
        raise ConfigEntryError(
            "Corrupted password or encryption key, "
            f"please follow the steps in {INVALID_TOKEN_SECTION}"
        ) from ex

    config_manager = AquaTempConfigManager(hass, entry)
    await config_manager.initialize(entry_config)

    if not config_manager.is_initialized:
        return False

    coordinator = AquaTempCoordinator(hass, config_manager, entry)

    await coordinator.async_config_entry_first_refresh()

    _async_identify_entry(hass, entry, coordinator.user_id)

    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    await hass.config_entries.async_forward_entry_setups(
        entry, config_manager.platforms
    )

    _LOGGER.info("Finished loading integration")

    return True


@callback
def _async_identify_entry(
    hass: HomeAssistant, entry: AquaTempConfigEntry, user_id: str | None
) -> None:
    """Give an entry created before entries were identified by cloud account
    its account's id, unless another entry already has it.

    Runs before the update listener is added, so it doesn't reload the entry.
    """
    if entry.unique_id is not None or user_id is None:
        return

    for other in hass.config_entries.async_entries(DOMAIN):
        if other.unique_id == user_id:
            _LOGGER.warning(
                f"Entry {entry.title} uses the same Aqua Temp account as "
                f"{other.title}; the cloud allows one login per account, so "
                "they log each other out. Remove one of them"
            )

            return

    hass.config_entries.async_update_entry(entry, unique_id=user_id)


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry so edited credentials and options take effect."""
    _LOGGER.info(f"Reloading {DOMAIN} integration, Entry ID: {entry.entry_id}")

    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AquaTempConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info(f"Unloading {DOMAIN} integration, Entry ID: {entry.entry_id}")

    coordinator = entry.runtime_data

    await coordinator.config_manager.remove(entry.entry_id)

    return await hass.config_entries.async_unload_platforms(
        entry, coordinator.config_manager.platforms
    )
