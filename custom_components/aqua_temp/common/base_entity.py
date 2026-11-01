import logging
import sys

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from ..managers.aqua_temp_coordinator import AquaTempCoordinator
from .consts import ADD_COMPONENT_SIGNALS, DOMAIN
from .entity_descriptions import AquaTempEntityDescription

_LOGGER = logging.getLogger(__name__)


async def async_setup_base_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    platform: Platform,
    entity_type: type,
    async_add_entities,
):
    @callback
    def _async_handle_device(entry_id: str, device_code: str):
        if entry.entry_id != entry_id:
            return

        try:
            coordinator = hass.data[DOMAIN][entry.entry_id]

            config_manager = coordinator.config_manager
            device_profile = coordinator.get_device_profile(device_code)

            entity_descriptions = config_manager.get_entity_descriptions(device_profile)
            unknown_codes = coordinator.get_unknown_codes(device_code)

            entities = [
                entity_type(entity_description, coordinator, device_code)
                for entity_description in entity_descriptions
                if entity_description.platform == platform
                and unknown_codes.isdisjoint(entity_description.source_codes)
            ]

            _LOGGER.debug(f"Setting up {platform} entities: {entities}")

            async_add_entities(entities, True)

        except Exception as ex:
            exc_type, exc_obj, tb = sys.exc_info()
            line_number = tb.tb_lineno

            _LOGGER.error(
                f"Failed to initialize {platform}, Error: {ex}, Line: {line_number}"
            )

    for add_component_signal in ADD_COMPONENT_SIGNALS:
        entry.async_on_unload(
            async_dispatcher_connect(hass, add_component_signal, _async_handle_device)
        )


class BaseEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    _device_code: str
    _entity_description: AquaTempEntityDescription

    def __init__(
        self,
        entity_description: AquaTempEntityDescription,
        coordinator: AquaTempCoordinator,
        device_code: str,
    ):
        super().__init__(coordinator)

        self._entity_description = entity_description
        self.entity_description = entity_description

        device_info = coordinator.get_device(device_code)

        unique_id_parts = [
            DOMAIN,
            entity_description.platform,
            entity_description.key,
            device_code,
        ]

        unique_id = slugify("_".join(unique_id_parts))

        self._attr_device_info = device_info
        self._attr_unique_id = unique_id

        self._data = {}
        self._device_code = device_code

    @property
    def available(self) -> bool:
        """Unavailable while the device is offline, unless the entity doesn't
        show its values: the cloud keeps answering with the last ones it got,
        as if they were current."""
        is_offline = self.local_coordinator.is_device_offline(self._device_code)

        return super().available and (
            self._entity_description.available_offline or not is_offline
        )

    @property
    def device_code(self):
        return self._device_code

    @property
    def local_coordinator(self) -> AquaTempCoordinator:
        return self.coordinator

    @property
    def data(self) -> dict | None:
        return self._data
