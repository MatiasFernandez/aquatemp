"""Platform for climate integration."""

from abc import ABC
import logging

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    FAN_AUTO,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .common.base_entity import BaseEntity, async_setup_base_entry
from .common.entity_descriptions import AquaTempClimateEntityDescription
from .managers.aqua_temp_coordinator import AquaTempCoordinator

_LOGGER = logging.getLogger(__name__)

# Home Assistant 2026.11 renamed the climate temperature shorthands with a
# native_ prefix; the old names log a warning there and stop working in 2027.11.
# Releases before it, down to hacs.json's minimum, only have the old names. Drop
# the old ones once that minimum reaches 2026.11
_NATIVE_NAMES = hasattr(ClimateEntity, "native_target_temperature")
_PREFIX = "_attr_native_" if _NATIVE_NAMES else "_attr_"
ATTR_TEMPERATURE_UNIT = f"{_PREFIX}temperature_unit"
ATTR_CURRENT_TEMPERATURE = f"{_PREFIX}current_temperature"
ATTR_TARGET_TEMPERATURE = f"{_PREFIX}target_temperature"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    await async_setup_base_entry(
        hass,
        entry,
        Platform.CLIMATE,
        AquaTempClimateEntity,
        async_add_entities,
    )


class AquaTempClimateEntity(BaseEntity, ClimateEntity, ABC):
    """Representation of a climate entity."""

    _attributes: dict

    def __init__(
        self,
        entity_description: AquaTempClimateEntityDescription,
        coordinator: AquaTempCoordinator,
        device_code: str,
    ):
        """Initialize the climate entity."""
        super().__init__(entity_description, coordinator, device_code)

        self._warned_range = False

        self._enable_turn_on_off_backwards_compatibility = False

        self._attr_supported_features = (
            ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
        )
        self._attr_fan_modes = list(coordinator.get_fan_modes(device_code))
        self._attr_hvac_modes = list(coordinator.get_hvac_modes(device_code))

        self._attr_hvac_mode = HVACMode.OFF
        self._attr_fan_mode = FAN_AUTO

        setattr(
            self,
            ATTR_TEMPERATURE_UNIT,
            coordinator.get_temperature_unit(device_code),
        )

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get("temperature")
        _LOGGER.debug(f"Set target temperature to: {temperature}")

        await self.local_coordinator.set_temperature(self.device_code, temperature)

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        _LOGGER.debug(f"Set HVAC Mode to: {hvac_mode}")

        await self.local_coordinator.set_hvac_mode(self.device_code, hvac_mode)

    async def async_set_fan_mode(self, fan_mode):
        """Set new target fan mode."""
        _LOGGER.debug(f"Set Fan Mode to: {fan_mode}")

        await self.local_coordinator.set_fan_mode(self.device_code, fan_mode)

    def _handle_coordinator_update(self) -> None:
        """Fetch new state parameters for the sensor."""
        coordinator = self.local_coordinator
        device_code = self.device_code

        is_power_on = coordinator.get_device_power(device_code)
        fan_mode = coordinator.get_device_fan_mode(device_code)
        current_temperature = coordinator.get_device_current_temperature(device_code)

        try:
            hvac_mode = coordinator.get_device_hvac_mode(device_code)

        except ValueError:
            # A mode the profile doesn't map, such as a Hitemp unit's Hybrid
            # (3) or Fast Heating (4): no HVAC mode, and no mode to pick the
            # target and limit codes by
            hvac_mode = None
            hvac_action = None
            target_temperature = None
            minimum_temperature = None
            maximum_temperature = None

        else:
            hvac_action = coordinator.get_device_hvac_action(device_code)
            target_temperature = coordinator.get_device_target_temperature(device_code)
            minimum_temperature = coordinator.get_device_minimum_temperature(
                device_code
            )
            maximum_temperature = coordinator.get_device_maximum_temperature(
                device_code
            )

        if not is_power_on:
            hvac_mode = HVACMode.OFF

        if (
            minimum_temperature is None
            or maximum_temperature is None
            or minimum_temperature > maximum_temperature
        ):
            # Home Assistant's default range instead: a None limit fails every
            # set_temperature call, and an inverted one leaves no valid value
            for attribute in ("_attr_min_temp", "_attr_max_temp"):
                if hasattr(self, attribute):
                    delattr(self, attribute)

            if not self._warned_range:
                self._warned_range = True

                _LOGGER.warning(
                    f"Device {device_code} reports no usable target temperature "
                    f"range (minimum {minimum_temperature}, maximum "
                    f"{maximum_temperature}), using Home Assistant's default range"
                )

        else:
            self._attr_min_temp = minimum_temperature
            self._attr_max_temp = maximum_temperature
            self._warned_range = False
        self._attr_hvac_mode = hvac_mode
        self._attr_hvac_action = hvac_action
        self._attr_fan_mode = fan_mode
        setattr(self, ATTR_TARGET_TEMPERATURE, target_temperature)
        setattr(self, ATTR_CURRENT_TEMPERATURE, current_temperature)

        _LOGGER.debug(f"_attr_hvac_mode: {self._attr_hvac_mode}")
        _LOGGER.debug(f"_attr_hvac_action: {self._attr_hvac_action}")
        _LOGGER.debug(f"target_temperature: {target_temperature}")
        _LOGGER.debug(f"_attr_fan_mode: {self._attr_fan_mode}")
        _LOGGER.debug(f"min_temp: {self.min_temp}")
        _LOGGER.debug(f"max_temp: {self.max_temp}")

        self.async_write_ha_state()
