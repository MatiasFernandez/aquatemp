from datetime import timedelta
import json
import logging

from homeassistant.config_entries import STORAGE_VERSION, ConfigEntry
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_TEMPERATURE_UNIT,
    CONF_USERNAME,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import translation
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.json import JSONEncoder
from homeassistant.helpers.storage import Store

from ..cloud.api_profile import ApiProfile
from ..cloud.client import Credentials
from ..cloud.consts import API_REQUEST_TIMEOUT, PRODUCT_ID_DEFAULT, PRODUCT_IDS
from ..cloud.device_profiles import DeviceProfile, DeviceProfiles
from ..common.consts import (
    CONF_LOG_SESSION_TOKEN,
    CONF_REQUEST_TIMEOUT,
    CONF_UPDATE_INTERVAL,
    CONFIGURATION_FILE,
    DEFAULT_ENTRY_ID,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from ..common.entity_descriptions import (
    AquaTempEntityDescription,
    build_entity_descriptions,
)
from ..models.config_data import ConfigData

_LOGGER = logging.getLogger(__name__)


class AquaTempConfigManager:
    _api_profile: ApiProfile | None
    _device_profiles: DeviceProfiles | None
    _translations: dict | None
    _entry: ConfigEntry | None
    _entry_id: str
    _entry_title: str
    _config_data: ConfigData
    _store: Store

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry | None):
        self._hass = hass

        self._data = None
        self.platforms = []

        self._entity_descriptions = {}

        self._api_profile = None
        self._device_profiles = None
        self._translations = None

        self._entry = entry
        self._entry_id = DEFAULT_ENTRY_ID if entry is None else entry.entry_id
        self._entry_title = DEFAULT_NAME if entry is None else entry.title

        self._config_data = ConfigData()

        self._is_initialized = False

        self._store = Store(
            hass, STORAGE_VERSION, CONFIGURATION_FILE, encoder=JSONEncoder
        )

    @property
    def is_initialized(self) -> bool:
        is_initialized = self._is_initialized

        return is_initialized

    @property
    def entry_id(self) -> str:
        entry_id = self._entry_id

        return entry_id

    @property
    def entry_title(self) -> str:
        entry_title = self._entry_title

        return entry_title

    @property
    def entry(self) -> ConfigEntry:
        entry = self._entry

        return entry

    @property
    def config_data(self) -> ConfigData:
        config_data = self._config_data

        return config_data

    @property
    def api_profile(self) -> ApiProfile:
        return self._api_profile

    @property
    def device_profiles(self) -> DeviceProfiles:
        return self._device_profiles

    @property
    def credentials(self) -> Credentials:
        credentials = Credentials(
            username=self._config_data.username, password=self._config_data.password
        )

        return credentials

    @property
    def log_session_token(self) -> bool:
        if self._entry is None:
            return False

        log_session_token = self._entry.options.get(CONF_LOG_SESSION_TOKEN, False)

        return log_session_token

    @property
    def request_timeout(self) -> int:
        """Seconds each request to the cloud may take."""
        if self._entry is None:
            return API_REQUEST_TIMEOUT

        request_timeout = self._entry.options.get(
            CONF_REQUEST_TIMEOUT, API_REQUEST_TIMEOUT
        )

        return request_timeout

    @property
    def update_interval(self) -> timedelta:
        if self._entry is None:
            return timedelta(seconds=DEFAULT_UPDATE_INTERVAL)

        seconds = self._entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

        return timedelta(seconds=seconds)

    async def initialize(self, entry_config: dict):
        await self._load()

        self._config_data.update(entry_config)

        self._api_profile = await ApiProfile.load(self._config_data.api_type)

        self._translations = await translation.async_get_translations(
            self._hass, self._hass.config.language, "entity", {DOMAIN}
        )

        self._is_initialized = True

    async def remove(self, entry_id: str):
        store_data = await self._store.async_load()

        entries = [DEFAULT_ENTRY_ID, entry_id]

        if store_data is not None:
            should_save = False
            data = {key: store_data[key] for key in store_data}

            for rm_entry_id in entries:
                if rm_entry_id in store_data:
                    data.pop(rm_entry_id)

                    should_save = True

            if should_save:
                await self._store.async_save(data)

    def get_entity_name(
        self, entity_description: AquaTempEntityDescription, device_info: DeviceInfo
    ) -> str:
        entity_key = entity_description.key
        platform = entity_description.platform

        device_name = device_info.get("name")

        translation_key = f"component.{DOMAIN}.entity.{platform}.{entity_key}.name"

        translated_name = self._translations.get(
            translation_key, entity_description.name
        )

        _LOGGER.debug(
            f"Translations requested, Key: {translation_key}, "
            f"Entity: {entity_description.name}, Value: {translated_name}"
        )

        entity_name = (
            device_name
            if translated_name is None or translated_name == ""
            else f"{device_name} {translated_name}"
        )

        return entity_name

    async def update_temperature_unit(self, device_code: str, value: str):
        _LOGGER.debug(f"Set temperature unit for device '{device_code}' to {value}")

        self._data[CONF_TEMPERATURE_UNIT][device_code] = value

        await self._save()

    def get_temperature_unit(self, device_code: str):
        temperature_units = self._data.get(CONF_TEMPERATURE_UNIT, {})
        temperature_unit = temperature_units.get(device_code, UnitOfTemperature.CELSIUS)

        return temperature_unit

    def get_debug_data(self) -> dict:
        data = self._config_data.to_dict()

        for key in self._data:
            data[key] = self._data[key]

        return data

    async def _load(self):
        self._data = None

        await self._load_config_from_file()

        if self._data is None:
            self._data = {}

        default_configuration = self._get_defaults()

        for key in default_configuration:
            value = default_configuration[key]

            if key not in self._data:
                self._data[key] = value

        await self._save()

        self._device_profiles = await DeviceProfiles.load()

        for product_id in [PRODUCT_ID_DEFAULT, *PRODUCT_IDS]:
            self._load_entity_descriptions(product_id)

        log_messages = [
            f"Entity Descriptions: {len(self._entity_descriptions)}",
            f"platforms: {len(self.platforms)}",
        ]

        log_message = f"Initialized, {', '.join(log_messages)}"

        _LOGGER.debug(log_message)

    async def _load_config_from_file(self):
        store_data = await self._store.async_load()

        if store_data is not None:
            self._data = store_data.get(self._entry_id)

    @staticmethod
    def _get_defaults() -> dict:
        data = {CONF_TEMPERATURE_UNIT: {}}

        return data

    async def _save(self):
        should_save = False
        store_data = await self._store.async_load()

        if store_data is None:
            store_data = {}

        entry_data = store_data.get(self._entry_id, {})

        _LOGGER.debug(
            f"Storing config data: {json.dumps(self._data)}, "
            f"Exiting: {json.dumps(entry_data)}"
        )

        for key in self._data:
            stored_value = entry_data.get(key)

            if key in [CONF_PASSWORD, CONF_USERNAME]:
                entry_data.pop(key)

                if stored_value is not None:
                    should_save = True

            else:
                current_value = self._data.get(key)

                if stored_value != current_value:
                    should_save = True

                    entry_data[key] = self._data[key]

        if DEFAULT_ENTRY_ID in store_data:
            store_data.pop(DEFAULT_ENTRY_ID)
            should_save = True

        if should_save:
            store_data[self._entry_id] = entry_data

            await self._store.async_save(store_data)

    def _load_entity_descriptions(self, product_id: str):
        device_profile = self._device_profiles.for_product(product_id)
        catalog_id = device_profile.catalog_id

        # Products without a catalog of their own use the default's
        # descriptions, see get_entity_descriptions
        if catalog_id != product_id:
            return

        entities = build_entity_descriptions(device_profile)

        self._update_platforms(entities)

        self._entity_descriptions[catalog_id] = entities

    def _update_platforms(self, entity_descriptions):
        for entity_description in entity_descriptions:
            if (
                entity_description.platform not in self.platforms
                and entity_description.platform is not None
            ):
                self.platforms.append(entity_description.platform)

    def get_entity_descriptions(self, device_profile: DeviceProfile):
        result = self._entity_descriptions.get(device_profile.catalog_id)

        if result is None:
            result = self._entity_descriptions.get(PRODUCT_ID_DEFAULT)

        return result
