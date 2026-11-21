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
from .common.consts import (
    CONF_API_TYPE,
    CONF_LOG_SESSION_TOKEN,
    CONF_REQUEST_TIMEOUT,
    CONF_TITLE,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    INVALID_TOKEN_SECTION,
)
from .managers.aqua_temp_config_manager import AquaTempConfigManager
from .managers.flow_manager import IntegrationFlowManager, async_check_login
from .managers.password_manager import PasswordManager
from .models.config_data import ConfigData

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
        return DomainOptionsFlowHandler()

    async def async_step_user(self, user_input=None):
        """Handle a flow start."""
        flow_manager = IntegrationFlowManager(self.hass, self)

        return await flow_manager.async_step(user_input)

    async def _async_check(self, entry: ConfigEntry, data: dict) -> str | None:
        """Log in with data's plain credentials, under entry's request timeout;
        return the account's id."""
        config_manager = AquaTempConfigManager(self.hass, None)
        await config_manager.initialize(data)

        return await async_check_login(
            self.hass,
            config_manager,
            entry.options.get(CONF_REQUEST_TIMEOUT, API_REQUEST_TIMEOUT),
        )

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

                user_id = await self._async_check(entry, data)

            except LoginError:
                errors = {"base": "invalid_credentials"}

            except InvalidToken:
                errors = {"base": "corrupted_encryption_key"}

            else:
                await PasswordManager.encrypt(self.hass, data, entry.entry_id)

                # The update listener reloads the entry with the new password
                self.hass.config_entries.async_update_entry(
                    entry, data=data, unique_id=entry.unique_id or user_id
                )

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

    async def async_step_reconfigure(self, user_input=None):
        """Replace the entry's credentials, checking them first.

        Moving to another account is allowed, as the README suggests for
        keeping the app logged in (a second account the heat pump is shared
        with), but not to one another entry already uses.
        """
        entry = self._get_reconfigure_entry()
        errors = None

        if user_input is not None:
            data = dict(user_input)

            try:
                user_id = await self._async_check(entry, data)

            except LoginError:
                errors = {"base": "invalid_credentials"}

            else:
                if user_id is not None and user_id != entry.unique_id:
                    await self.async_set_unique_id(user_id)
                    self._abort_if_unique_id_configured()

                await PasswordManager.encrypt(self.hass, data, entry.entry_id)

                # The update listener reloads the entry with the new credentials
                self.hass.config_entries.async_update_entry(
                    entry, data=data, unique_id=user_id or entry.unique_id
                )

                return self.async_abort(reason="reconfigure_successful")

        values = user_input or entry.data

        return self.async_show_form(
            step_id="reconfigure",
            # Home Assistant 2026.11 types this as probatio.Schema. A voluptuous
            # schema works at runtime, and 2025.11 doesn't ship probatio.
            data_schema=ConfigData.credentials_schema(  # ty: ignore[invalid-argument-type]
                values.get(CONF_USERNAME), values.get(CONF_API_TYPE)
            ),
            errors=errors,
        )


class DomainOptionsFlowHandler(config_entries.OptionsFlow):
    """The entry's title and settings; the credentials are reconfigured."""

    async def async_step_init(self, user_input=None):
        entry = self.config_entry

        if user_input is not None:
            options = dict(user_input)
            title = options.pop(CONF_TITLE)

            # Options are written here too, in the same update as the title, so
            # the update listener reloads the entry once. The flow's own write
            # of the same options afterwards is then a no-op
            self.hass.config_entries.async_update_entry(
                entry, title=title, options=options
            )

            return self.async_create_entry(data=options)

        values = {CONF_TITLE: entry.title} | {
            key: entry.options[key]
            for key in (
                CONF_UPDATE_INTERVAL,
                CONF_REQUEST_TIMEOUT,
                CONF_LOG_SESSION_TOKEN,
            )
            if key in entry.options
        }

        return self.async_show_form(
            step_id="init",
            # Home Assistant 2026.11 types this as probatio.Schema. A voluptuous
            # schema works at runtime, and 2025.11 doesn't ship probatio.
            data_schema=ConfigData.options_schema(  # ty: ignore[invalid-argument-type]
                values
            ),
        )
