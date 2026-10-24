from copy import copy
import json
import logging

import aiofiles

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import STORAGE_VERSION, ConfigEntry
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_TEMPERATURE_UNIT,
    CONF_USERNAME,
    EntityCategory,
    Platform,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import translation
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.json import JSONEncoder
from homeassistant.helpers.storage import Store

from ..cloud.api_profile import PROFILES_PATH, ApiProfile
from ..cloud.api_types import APIParam
from ..cloud.consts import PRODUCT_ID_DEFAULT, PRODUCT_IDS, ProductParameter
from ..cloud.device_profiles import DeviceProfile, DeviceProfiles
from ..common.consts import (
    CONF_LOG_SESSION_TOKEN,
    CONFIGURATION_FILE,
    DEFAULT_ENTRY_ID,
    DEFAULT_NAME,
    DOMAIN,
)
from ..common.entity_descriptions import (
    DEFAULT_ENTITY_DESCRIPTIONS,
    AquaTempBinarySensorEntityDescription,
    AquaTempEntityDescription,
    AquaTempSensorEntityDescription,
    get_derived_entity_descriptions,
)
from ..models.config_data import ConfigData

_LOGGER = logging.getLogger(__name__)


class AquaTempConfigManager:
    _api_profile: ApiProfile | None
    _device_profiles: DeviceProfiles | None
    _devices: dict[str, DeviceProfile]
    _translations: dict | None
    _entry: ConfigEntry | None
    _entry_id: str
    _entry_title: str
    _config_data: ConfigData
    _store: Store | None

    def __init__(self, hass: HomeAssistant | None, entry: ConfigEntry | None):
        self._hass = hass

        self._data = None
        self.platforms = []

        self._entity_descriptions = {}

        self._devices = {}
        self._api_profile = None
        self._device_profiles = None
        self._translations = None

        self._entry = entry
        self._entry_id = DEFAULT_ENTRY_ID if entry is None else entry.entry_id
        self._entry_title = DEFAULT_NAME if entry is None else entry.title

        self._config_data = ConfigData()

        self._is_initialized = False

        self._store = None

        if hass is not None:
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
    def log_session_token(self) -> bool:
        if self._entry is None:
            return False

        log_session_token = self._entry.options.get(CONF_LOG_SESSION_TOKEN, False)

        return log_session_token

    async def initialize(self, entry_config: dict):
        await self._load()

        self._config_data.update(entry_config)

        self._api_profile = await ApiProfile.load(self._config_data.api_type)

        if self._hass is None:
            self._translations = {}
        else:
            self._translations = await translation.async_get_translations(
                self._hass, self._hass.config.language, "entity", {DOMAIN}
            )

        self._is_initialized = True

    async def remove(self, entry_id: str):
        if self._store is None:
            return

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

    def set_device(self, device_code: str, product_id: str):
        device_profile = self._device_profiles.for_product(product_id)

        self._devices[device_code] = device_profile

        _LOGGER.info(
            f"Device {device_code} mapped to "
            f"Product ID {product_id}, "
            f"Mapping Key: {device_profile.mapping_id}, "
            f"Entity Description Key: {device_profile.catalog_id}"
        )

    def get_temperature_unit(self, device_code: str):
        temperature_units = self._data.get(CONF_TEMPERATURE_UNIT, {})
        temperature_unit = temperature_units.get(device_code, UnitOfTemperature.CELSIUS)

        return temperature_unit

    def get_supported_protocol_codes(self, device_code) -> list[str]:
        result = self._get_device_profile(device_code).poll_codes

        return result

    def get_pc_key(self, device_code: str, key: str):
        protocol_code_key = self._get_device_profile(device_code).get_pc_key(key)

        return protocol_code_key

    def get_hvac_mode_pc_key(self, device_code: str, hvac_mode: str, key: str):
        device_profile = self._get_device_profile(device_code)
        protocol_code_key = device_profile.get_hvac_mode_pc_key(hvac_mode, key)

        return protocol_code_key

    def get_hvac_modes(self, device_code: str) -> dict[str, str | None]:
        result = self._get_device_profile(device_code).hvac_modes

        return result

    def get_fan_modes(self, device_code: str) -> dict[str, str]:
        result = self._get_device_profile(device_code).fan_modes

        return result

    def get_fan_reverse_mapping(self, device_code, fan_mode) -> str:
        fan_modes = self._get_device_profile(device_code).fan_modes_reverse
        result = fan_modes.get(fan_mode)

        return result

    def get_hvac_reverse_mapping(self, device_code, hvac_mode) -> str:
        hvac_modes = self._get_device_profile(device_code).hvac_modes_reverse
        result = hvac_modes.get(hvac_mode)

        return result

    def get_api_param(self, param: APIParam):
        result = self._api_profile.get(param)

        return result

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

        # Profiles first: entity descriptions read their mappings for derived
        # entities
        self._device_profiles = await DeviceProfiles.load()

        await self._load_entity_descriptions(PRODUCT_ID_DEFAULT)

        for product_id in PRODUCT_IDS:
            await self._load_entity_descriptions(product_id)

        log_messages = [
            f"Entity Descriptions: {len(self._entity_descriptions)}",
            f"platforms: {len(self.platforms)}",
        ]

        log_message = f"Initialized, {', '.join(log_messages)}"

        _LOGGER.debug(log_message)

    async def _load_config_from_file(self):
        if self._store is not None:
            store_data = await self._store.async_load()

            if store_data is not None:
                self._data = store_data.get(self._entry_id)

    @staticmethod
    def _get_defaults() -> dict:
        data = {CONF_TEMPERATURE_UNIT: {}}

        return data

    async def _save(self):
        if self._store is None:
            return

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

    async def _load_entity_descriptions(self, product_id: str):
        entities = copy(DEFAULT_ENTITY_DESCRIPTIONS)
        file_path = (
            PROFILES_PATH / f"{ProductParameter.ENTITY_DESCRIPTION}.{product_id}.json"
        )

        if not file_path.exists():
            return

        file = await aiofiles.open(file_path)
        json_str = await file.read()
        await file.close()

        json_data = json.loads(json_str)

        for data_item in json_data:
            platform = data_item.get("platform")
            key = data_item.get("key")
            translation_key = f"{product_id}_{key}".replace("/", "").lower()

            if platform == Platform.SENSOR:
                state_class = data_item.get("state_class")

                sensor_entity = AquaTempSensorEntityDescription(
                    key=key,
                    name=data_item.get("name"),
                    device_class=data_item.get("device_class"),
                    native_unit_of_measurement=data_item.get("unit_of_measurement"),
                    entity_category=self._get_entity_category(data_item),
                    state_class=(
                        None if state_class is None else SensorStateClass(state_class)
                    ),
                    translation_key=translation_key,
                )

                entities.append(sensor_entity)

            elif platform == Platform.BINARY_SENSOR:
                binary_sensor_entity = AquaTempBinarySensorEntityDescription(
                    key=key,
                    name=data_item.get("name"),
                    device_class=data_item.get("device_class"),
                    on_value=data_item.get("on_value"),
                    entity_category=self._get_entity_category(data_item),
                    translation_key=translation_key,
                )

                entities.append(binary_sensor_entity)

            else:
                entity = AquaTempEntityDescription(key=key, name=data_item.get("name"))

                entities.append(entity)

        # Same fallback as set_device: a product without its own mapping uses
        # the default one
        pc_mapping = self._device_profiles.for_product(product_id).mapping

        entities.extend(get_derived_entity_descriptions(pc_mapping))

        self._update_platforms(entities)

        self._entity_descriptions[product_id] = entities

    def _update_platforms(self, entity_descriptions):
        for entity_description in entity_descriptions:
            if (
                entity_description.platform not in self.platforms
                and entity_description.platform is not None
            ):
                self.platforms.append(entity_description.platform)

    def _get_device_profile(self, device_code: str) -> DeviceProfile:
        device_profile = self._devices.get(device_code)

        if device_profile is None:
            device_profile = self._device_profiles.for_product(PRODUCT_ID_DEFAULT)

        return device_profile

    def get_entity_descriptions(self, device_code):
        catalog_id = self._get_device_profile(device_code).catalog_id

        result = self._entity_descriptions.get(catalog_id)

        if result is None:
            result = self._entity_descriptions.get(PRODUCT_ID_DEFAULT)

        return result

    @staticmethod
    def _get_entity_category(data_item: dict) -> EntityCategory | None:
        """Resolve entity_category for a JSON-defined entity.

        An absent key keeps the historical DIAGNOSTIC behaviour, so every product
        profile that does not opt in is unaffected. An explicit null promotes the
        entity to the device's primary section.
        """
        if "entity_category" not in data_item:
            return EntityCategory.DIAGNOSTIC

        value = data_item["entity_category"]

        return None if value is None else EntityCategory(value)
