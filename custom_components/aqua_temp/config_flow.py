"""Config flow to configure."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from cryptography.fernet import InvalidToken
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback

from .cloud.consts import API_REQUEST_TIMEOUT
from .cloud.exceptions import LoginError
from .common.consts import CONF_REQUEST_TIMEOUT, DOMAIN, INVALID_TOKEN_SECTION
from .managers.aqua_temp_config_manager import AquaTempConfigManager
from .managers.flow_manager import IntegrationFlowManager, async_check_login
from .managers.password_manager import PasswordManager

_LOGGER = logging.getLogger(__name__)


@config_entries.HANDLERS.register(DOMAIN)
class DomainFlowHandler(config_entries.ConfigFlow):
    """Handle a domain config flow."""

    VERSION = 1

    def __init__(self):
        super().__init__()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return DomainOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle a flow start."""
        flow_manager = IntegrationFlowManager(self.hass, self)

        return await flow_manager.async_step(user_input)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]):
        """Start a reauth flow when the cloud rejects the stored login."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Ask for the password again and check it before storing it."""
        entry = self._get_reauth_entry()
        errors = None

        if user_input is not None:
            data = dict(entry.data)

            try:
                await PasswordManager.decrypt(self.hass, data, entry.entry_id)
                data[CONF_PASSWORD] = user_input[CONF_PASSWORD]

                config_manager = AquaTempConfigManager(self.hass, None)
                await config_manager.initialize(data)

                await async_check_login(
                    self.hass,
                    config_manager,
                    entry.options.get(CONF_REQUEST_TIMEOUT, API_REQUEST_TIMEOUT),
                )

            except LoginError:
                errors = {"base": "invalid_credentials"}

            except InvalidToken:
                errors = {"base": "corrupted_encryption_key"}

            else:
                await PasswordManager.encrypt(self.hass, data, entry.entry_id)

                # The update listener reloads the entry with the new password
                self.hass.config_entries.async_update_entry(entry, data=data)

                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            # Home Assistant 2026.11 types this as probatio.Schema. A voluptuous
            # schema works at runtime, and 2025.11 doesn't ship probatio.
            data_schema=vol.Schema(  # ty: ignore[invalid-argument-type]
                {vol.Required(CONF_PASSWORD): str}
            ),
            errors=errors,
            description_placeholders={
                "username": entry.data.get(CONF_USERNAME, ""),
                "invalid_token_url": INVALID_TOKEN_SECTION,
            },
        )


class DomainOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle domain options."""

    _config_entry: ConfigEntry

    def __init__(self, config_entry: ConfigEntry):
        """Initialize domain options flow."""
        super().__init__()

        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the domain options."""
        flow_manager = IntegrationFlowManager(self.hass, self, self._config_entry)

        return await flow_manager.async_step(user_input)
