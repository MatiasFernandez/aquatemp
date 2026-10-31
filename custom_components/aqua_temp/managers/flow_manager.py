"""Config flow to configure."""

from __future__ import annotations

from copy import copy
import logging
from typing import Any

from cryptography.fernet import InvalidToken

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowHandler
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from ..cloud.client import AquaTempAPI
from ..cloud.consts import API_REQUEST_TIMEOUT
from ..cloud.exceptions import LoginError
from ..common.consts import (
    CONF_API_TYPE,
    CONF_LOG_SESSION_TOKEN,
    CONF_REQUEST_TIMEOUT,
    CONF_TITLE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL,
    INVALID_TOKEN_SECTION,
)
from ..models.config_data import DATA_KEYS, ConfigData
from .aqua_temp_config_manager import AquaTempConfigManager
from .password_manager import PasswordManager

_LOGGER = logging.getLogger(__name__)


class IntegrationFlowManager:
    _hass: HomeAssistant
    _entry: ConfigEntry | None

    _flow_handler: FlowHandler
    _flow_id: str

    _config_manager: AquaTempConfigManager

    def __init__(
        self,
        hass: HomeAssistant,
        flow_handler: FlowHandler,
        entry: ConfigEntry | None = None,
    ):
        self._hass = hass
        self._flow_handler = flow_handler
        self._entry = entry
        self._flow_id = "user" if entry is None else "init"
        self._config_manager = AquaTempConfigManager(self._hass, None)

    async def async_step(self, user_input: dict | None = None):
        """Manage the domain options."""
        _LOGGER.info(f"Config flow started, Step: {self._flow_id}")

        form_errors = None

        if user_input is None:
            if self._entry is None:
                user_input = {}

            else:
                user_input = {key: self._entry.data[key] for key in self._entry.data}
                user_input[CONF_TITLE] = self._entry.title
                user_input[CONF_LOG_SESSION_TOKEN] = self._entry.options.get(
                    CONF_LOG_SESSION_TOKEN, False
                )
                user_input[CONF_UPDATE_INTERVAL] = self._entry.options.get(
                    CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                )
                user_input[CONF_REQUEST_TIMEOUT] = self._entry.options.get(
                    CONF_REQUEST_TIMEOUT, API_REQUEST_TIMEOUT
                )

                await PasswordManager.decrypt(
                    self._hass, user_input, self._entry.entry_id
                )

        else:
            _LOGGER.info(
                "Config flow submitted, "
                f"API Type: {user_input.get(CONF_API_TYPE)}, "
                f"Update Interval: {user_input.get(CONF_UPDATE_INTERVAL)}, "
                f"Request Timeout: {user_input.get(CONF_REQUEST_TIMEOUT)}, "
                f"Log Session Token: {user_input.get(CONF_LOG_SESSION_TOKEN, False)}"
            )

            try:
                await self._config_manager.initialize(user_input)

                # A flow runs outside config entry setup, so HA would only
                # detach an auto-cleaned session at shutdown, keeping one per
                # submission until then. Detach it here instead; close() would
                # act on HA's shared connector.
                session = async_create_clientsession(self._hass, auto_cleanup=False)

                try:
                    api = AquaTempAPI(
                        session,
                        self._config_manager.credentials,
                        self._config_manager.api_profile,
                        self._config_manager.device_profiles,
                    )

                    await api.initialize(True)

                finally:
                    session.detach()

                _LOGGER.debug("User inputs are valid")

                if self._entry is None:
                    data = copy(user_input)

                else:
                    data = await self.remap_entry_data(user_input)

                await PasswordManager.encrypt(self._hass, data)

                title = data.get(CONF_TITLE, DEFAULT_NAME)

                if CONF_TITLE in data:
                    data.pop(CONF_TITLE)

                return self._flow_handler.async_create_entry(title=title, data=data)

            except LoginError:
                error_key = "invalid_credentials"

            except InvalidToken:
                error_key = "corrupted_encryption_key"

            if error_key is not None:
                form_errors = {"base": error_key}

                _LOGGER.warning(f"Failed to create integration, Error Key: {error_key}")

        schema = ConfigData.default_schema(user_input, self._entry is not None)

        return self._flow_handler.async_show_form(
            step_id=self._flow_id,
            data_schema=schema,
            errors=form_errors,
            description_placeholders={"invalid_token_url": INVALID_TOKEN_SECTION},
        )

    async def remap_entry_data(self, options: dict[str, Any]) -> dict[str, Any]:
        config_options = {}
        config_data = {}

        entry = self._entry
        entry_data = entry.data

        title = DEFAULT_NAME

        for key in options:
            if key in DATA_KEYS:
                config_data[key] = options.get(key, entry_data.get(key))

            elif key == CONF_TITLE:
                title = options.get(key, DEFAULT_NAME)

            else:
                config_options[key] = options.get(key)

        await PasswordManager.encrypt(self._hass, config_data)

        # Options are written here too, in the same update as data and title, so
        # the update listener reloads the entry once. The options flow's own write
        # of the same options afterwards is then a no-op.
        self._hass.config_entries.async_update_entry(
            entry, data=config_data, title=title, options=config_options
        )

        return config_options
