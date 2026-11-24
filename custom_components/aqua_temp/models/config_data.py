import voluptuous as vol
from voluptuous import Schema

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import selector

from ..cloud.api_types import API_TYPE_LEGACY, API_TYPES, APIType
from ..cloud.consts import API_REQUEST_TIMEOUT
from ..common.consts import (
    CONF_API_TYPE,
    CONF_LOG_SESSION_TOKEN,
    CONF_REQUEST_TIMEOUT,
    CONF_TITLE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL,
    MAX_REQUEST_TIMEOUT,
    MAX_UPDATE_INTERVAL,
    MIN_REQUEST_TIMEOUT,
    MIN_UPDATE_INTERVAL,
)


class ConfigData:
    _username: str | None
    _password: str | None
    _api_type: str | None

    def __init__(self):
        self._username = None
        self._password = None
        self._api_type = None

    @property
    def username(self) -> str:
        username = self._username

        return username

    @property
    def password(self) -> str:
        password = self._password

        return password

    @property
    def api_type(self) -> str:
        api_type = self._api_type

        return api_type

    def update(self, data: dict):
        self._password = data.get(CONF_PASSWORD)
        self._username = data.get(CONF_USERNAME)

        api_type = data.get(CONF_API_TYPE, str(APIType.AquaTemp))

        if api_type in API_TYPE_LEGACY:
            api_type = str(API_TYPE_LEGACY.get(api_type))

        self._api_type = api_type

    def to_dict(self):
        obj = {
            CONF_USERNAME: self.username,
            CONF_API_TYPE: self.api_type,
        }

        return obj

    def __repr__(self):
        to_string = f"{self.to_dict()}"

        return to_string

    @staticmethod
    def _api_type_selector() -> selector.SelectSelector:
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=API_TYPES, translation_key=CONF_API_TYPE
            )
        )

    @staticmethod
    def user_schema(user_input: dict | None) -> Schema:
        """A new entry's title and credentials."""
        if user_input is None:
            user_input = {}

        return vol.Schema(
            {
                vol.Required(
                    CONF_TITLE, default=user_input.get(CONF_TITLE, DEFAULT_NAME)
                ): str,
                vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME)): str,
                vol.Required(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD)): str,
                vol.Required(
                    CONF_API_TYPE, default=user_input.get(CONF_API_TYPE)
                ): ConfigData._api_type_selector(),
            }
        )

    @staticmethod
    def credentials_schema(username: str | None, api_type: str | None) -> Schema:
        """An entry's credentials to replace; the password starts empty, so
        the stored one never reaches the frontend."""
        return vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=username): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(
                    CONF_API_TYPE, default=api_type
                ): ConfigData._api_type_selector(),
            }
        )

    @staticmethod
    def options_schema(values: dict) -> Schema:
        """An entry's title and settings."""
        return vol.Schema(
            {
                vol.Required(
                    CONF_TITLE, default=values.get(CONF_TITLE, DEFAULT_NAME)
                ): str,
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=values.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL),
                ),
                vol.Optional(
                    CONF_REQUEST_TIMEOUT,
                    default=values.get(CONF_REQUEST_TIMEOUT, API_REQUEST_TIMEOUT),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_REQUEST_TIMEOUT, max=MAX_REQUEST_TIMEOUT),
                ),
                vol.Optional(
                    CONF_LOG_SESSION_TOKEN,
                    default=values.get(CONF_LOG_SESSION_TOKEN, False),
                ): bool,
            }
        )
