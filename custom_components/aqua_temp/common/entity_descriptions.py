from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.components.climate import ClimateEntityDescription, HVACMode
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, Platform, UnitOfTemperature
from homeassistant.helpers.entity import EntityDescription

from ..cloud.consts import (
    CONFIG_INLET_WATER_TEMPERATURE,
    CONFIG_OUTLET_WATER_TEMPERATURE,
    POWER_MODE_ON,
)
from .consts import API_STATUS


@dataclass(frozen=True, kw_only=True)
class AquaTempEntityDescription(EntityDescription):
    platform: Platform | None = None


@dataclass(frozen=True, kw_only=True)
class AquaTempClimateEntityDescription(
    ClimateEntityDescription, AquaTempEntityDescription
):
    platform: Platform | None = Platform.CLIMATE
    fan_modes: list[str] | None = None
    hvac_modes: list[HVACMode] | list[str] = None


@dataclass(frozen=True, kw_only=True)
class AquaTempBinarySensorEntityDescription(
    BinarySensorEntityDescription, AquaTempEntityDescription
):
    platform: Platform | None = Platform.BINARY_SENSOR
    on_value: str | bool | None = None
    attributes: list[str] | None = None


@dataclass(frozen=True, kw_only=True)
class AquaTempSensorEntityDescription(
    SensorEntityDescription, AquaTempEntityDescription
):
    platform: Platform | None = Platform.SENSOR
    value_fn: Callable[[dict], float | None] | None = None


@dataclass(frozen=True, kw_only=True)
class AquaTempSelectEntityDescription(
    SelectEntityDescription, AquaTempEntityDescription
):
    platform: Platform | None = Platform.SELECT


DEFAULT_ENTITY_DESCRIPTIONS: list[AquaTempEntityDescription] = [
    AquaTempBinarySensorEntityDescription(
        key=API_STATUS,
        name="API Status",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        on_value=True,
        translation_key=API_STATUS,
    ),
    AquaTempSelectEntityDescription(
        key="temperature_unit",
        name="Temperature Unit",
        options=[UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT],
        entity_category=EntityCategory.CONFIG,
        translation_key="temperature_unit",
    ),
    AquaTempBinarySensorEntityDescription(
        key="is_fault",
        name="Fault",
        on_value=POWER_MODE_ON,
        device_class=BinarySensorDeviceClass.PROBLEM,
        attributes=["fault"],
        translation_key="is_fault",
    ),
    AquaTempBinarySensorEntityDescription(
        key="device_status",
        name="Status",
        on_value="ONLINE",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        translation_key="device_status",
    ),
    AquaTempClimateEntityDescription(key="Mode", name=None, translation_key="mode"),
]


def water_delta_t(device_data: dict, inlet_code: str, outlet_code: str) -> float | None:
    """Outlet minus inlet water temperature, signed."""
    try:
        return float(device_data[outlet_code]) - float(device_data[inlet_code])

    except (KeyError, TypeError, ValueError):
        return None


def get_derived_entity_descriptions(
    pc_mapping: dict,
) -> list[AquaTempEntityDescription]:
    """Entities computed from other codes, for the roles the mapping defines."""
    entity_descriptions = []

    inlet_code = pc_mapping.get(CONFIG_INLET_WATER_TEMPERATURE)
    outlet_code = pc_mapping.get(CONFIG_OUTLET_WATER_TEMPERATURE)

    if inlet_code is not None and outlet_code is not None:
        entity_descriptions.append(
            AquaTempSensorEntityDescription(
                key="water_delta_t",
                name="Water ΔT",
                device_class=SensorDeviceClass.TEMPERATURE_DELTA,
                state_class=SensorStateClass.MEASUREMENT,
                suggested_display_precision=1,
                value_fn=partial(
                    water_delta_t, inlet_code=inlet_code, outlet_code=outlet_code
                ),
                translation_key="water_delta_t",
            )
        )

    return entity_descriptions
