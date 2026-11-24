"""The config flow's user step, and the login check every credential step uses."""

from __future__ import annotations

from copy import copy
import logging

from cryptography.fernet import InvalidToken

from homeassistant.config_entries import ConfigFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from ..cloud.client import AquaTempAPI
from ..cloud.consts import API_REQUEST_TIMEOUT
from ..cloud.exceptions import LoginError
from ..common.consts import (
    CONF_API_TYPE,
    CONF_TITLE,
    DEFAULT_NAME,
    INVALID_TOKEN_SECTION,
)
from ..models.config_data import ConfigData
from .aqua_temp_config_manager import AquaTempConfigManager
from .password_manager import PasswordManager

_LOGGER = logging.getLogger(__name__)


async def async_check_login(
    hass: HomeAssistant,
    config_manager: AquaTempConfigManager,
    request_timeout: int,
) -> str | None:
    """Log in with the initialized config manager's credentials and read the
    devices; return the account's id in the cloud, or raise LoginError when
    the cloud rejects them."""
    # A flow runs outside config entry setup, so HA would only detach an
    # auto-cleaned session at shutdown, keeping one per submission until then.
    # Detach it here instead; close() would act on HA's shared connector.
    session = async_create_clientsession(hass, auto_cleanup=False)

    try:
        api = AquaTempAPI(
            session,
            config_manager.credentials,
            config_manager.api_profile,
            config_manager.device_profiles,
            request_timeout=request_timeout,
        )

        await api.initialize(True)

        return api.user_id

    finally:
        session.detach()


class IntegrationFlowManager:
    """The user step: the credentials and title of a new entry."""

    _hass: HomeAssistant
    _flow_handler: ConfigFlow
    _config_manager: AquaTempConfigManager

    def __init__(self, hass: HomeAssistant, flow_handler: ConfigFlow):
        self._hass = hass
        self._flow_handler = flow_handler
        self._config_manager = AquaTempConfigManager(self._hass, None)

    async def async_step(self, user_input: dict | None = None):
        _LOGGER.info("Config flow started, Step: user")

        form_errors = None

        if user_input is None:
            user_input = {}

        else:
            _LOGGER.info(
                f"Config flow submitted, API Type: {user_input.get(CONF_API_TYPE)}"
            )

            try:
                await self._config_manager.initialize(user_input)

                user_id = await async_check_login(
                    self._hass, self._config_manager, API_REQUEST_TIMEOUT
                )

            except LoginError:
                form_errors = {"base": "invalid_credentials"}

            except InvalidToken:
                form_errors = {"base": "corrupted_encryption_key"}

            else:
                _LOGGER.debug("User inputs are valid")

                # One entry per cloud account: two would log each other out
                if user_id is not None:
                    await self._flow_handler.async_set_unique_id(user_id)
                    self._flow_handler._abort_if_unique_id_configured()

                data = copy(user_input)

                await PasswordManager.encrypt(self._hass, data)

                title = data.pop(CONF_TITLE, DEFAULT_NAME)

                return self._flow_handler.async_create_entry(title=title, data=data)

            _LOGGER.warning(f"Failed to create integration, Errors: {form_errors}")

        return self._flow_handler.async_show_form(
            step_id="user",
            # Home Assistant 2026.11 types this as probatio.Schema. A voluptuous
            # schema works at runtime, and 2025.11 doesn't ship probatio.
            data_schema=ConfigData.user_schema(  # ty: ignore[invalid-argument-type]
                user_input
            ),
            errors=form_errors,
            description_placeholders={"invalid_token_url": INVALID_TOKEN_SECTION},
        )
