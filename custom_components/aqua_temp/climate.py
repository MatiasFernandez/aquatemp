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

        self._temperature_unit = coordinator.get_temperature_unit(device_code)
        self._current_temperature: float | None = None
        self._target_temperature: float | None = None

    @property
    def native_temperature_unit(self) -> str:  # ty: ignore[invalid-property-type-override]
        """Return the unit the device reports temperatures in."""
        return self._temperature_unit

    @property
    def native_current_temperature(self) -> float | None:  # ty: ignore[invalid-property-type-override]
        """Return the current temperature, in the device's unit."""
        return self._current_temperature

    @property
    def native_target_temperature(self) -> float | None:  # ty: ignore[invalid-property-type-override]
        """Return the target temperature, in the device's unit."""
        return self._target_temperature

    # Home Assistant before 2026.11 has no native_ names and reads these. From
    # 2026.11 it reads the native_ ones and deprecates these, but doesn't report
    # them while the class also provides the native_ ones. Remove once hacs.json's
    # minimum reaches 2026.11, together with the ty ignores on these aliases and on
    # the native_ properties above.
    temperature_unit = native_temperature_unit  # ty: ignore[override-of-final-variable]
    current_temperature = native_current_temperature  # ty: ignore[override-of-final-variable]
    target_temperature = native_target_temperature  # ty: ignore[override-of-final-variable]

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

        hvac_mode = coordinator.get_device_hvac_mode(device_code)
        hvac_action = coordinator.get_device_hvac_action(device_code)
        is_power_on = coordinator.get_device_power(device_code)
        fan_mode = coordinator.get_device_fan_mode(device_code)
        current_temperature = coordinator.get_device_current_temperature(device_code)
        target_temperature = coordinator.get_device_target_temperature(device_code)
        minimum_temperature = coordinator.get_device_minimum_temperature(device_code)
        maximum_temperature = coordinator.get_device_maximum_temperature(device_code)

        if not is_power_on:
            hvac_mode = HVACMode.OFF

        self._attr_min_temp = minimum_temperature
        self._attr_max_temp = maximum_temperature
        self._attr_hvac_mode = hvac_mode
        self._attr_hvac_action = hvac_action
        self._attr_fan_mode = fan_mode
        self._target_temperature = target_temperature
        self._current_temperature = current_temperature

        _LOGGER.debug(f"_attr_hvac_mode: {self._attr_hvac_mode}")
        _LOGGER.debug(f"_attr_hvac_action: {self._attr_hvac_action}")
        _LOGGER.debug(f"target_temperature: {self._target_temperature}")
        _LOGGER.debug(f"_attr_fan_mode: {self._attr_fan_mode}")
        _LOGGER.debug(f"_attr_min_temp: {self._attr_min_temp}")
        _LOGGER.debug(f"_attr_max_temp: {self._attr_max_temp}")

        self.async_write_ha_state()
