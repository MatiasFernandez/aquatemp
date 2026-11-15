from collections.abc import Callable
from copy import copy
from dataclasses import dataclass
from functools import partial
from math import isfinite

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.components.button import ButtonEntityDescription
from homeassistant.components.climate import ClimateEntityDescription, HVACMode
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    Platform,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import EntityDescription

from ..cloud.auto_mode import auto_mode_direction
from ..cloud.consts import (
    CONFIG_COMPRESSOR_FREQUENCY,
    CONFIG_COMPRESSOR_TYPE,
    CONFIG_COOLING_MAX_FREQUENCY,
    CONFIG_HEATING_MAX_FREQUENCY,
    CONFIG_INLET_WATER_TEMPERATURE,
    CONFIG_OUTLET_WATER_TEMPERATURE,
    CONFIG_SET_MODE,
    POWER_MODE_ON,
)
from ..cloud.device_profiles import DeviceProfile
from ..cloud.modes import Mode
from .consts import API_STATUS


def include_always(device_data: dict) -> bool:
    return True


@dataclass(frozen=True, kw_only=True)
class AquaTempEntityDescription(EntityDescription):
    platform: Platform | None = None
    # Whether to create the entity for a device, from the device's data at setup
    include_if: Callable[[dict], bool] = include_always
    # Codes the entity reads; it is skipped on a device that doesn't know one
    source_codes: tuple[str, ...] = ()
    # Stays available while the device is offline, as it doesn't show the
    # device's values
    available_offline: bool = False


@dataclass(frozen=True, kw_only=True)
class AquaTempClimateEntityDescription(
    ClimateEntityDescription, AquaTempEntityDescription
):
    platform: Platform | None = Platform.CLIMATE
    fan_modes: list[str] | None = None
    hvac_modes: list[HVACMode] | list[str] | None = None


@dataclass(frozen=True, kw_only=True)
class AquaTempBinarySensorEntityDescription(
    BinarySensorEntityDescription, AquaTempEntityDescription
):
    platform: Platform | None = Platform.BINARY_SENSOR
    on_value: str | bool | None = None
    # When set, any state other than on_value or off_value is unavailable
    off_value: str | None = None
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


@dataclass(frozen=True, kw_only=True)
class AquaTempButtonEntityDescription(
    ButtonEntityDescription, AquaTempEntityDescription
):
    platform: Platform | None = Platform.BUTTON


DEFAULT_ENTITY_DESCRIPTIONS: list[AquaTempEntityDescription] = [
    AquaTempBinarySensorEntityDescription(
        key=API_STATUS,
        name="API Status",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        on_value=True,
        translation_key=API_STATUS,
        available_offline=True,
    ),
    AquaTempSelectEntityDescription(
        key="temperature_unit",
        name="Temperature Unit",
        options=[UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT],
        entity_category=EntityCategory.CONFIG,
        translation_key="temperature_unit",
        available_offline=True,
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
        off_value="OFFLINE",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        translation_key="device_status",
        available_offline=True,
    ),
    # Named after the device
    AquaTempClimateEntityDescription(key="Mode", name=None),
    AquaTempButtonEntityDescription(
        key="refresh_data",
        name="Refresh Data",
        icon="mdi:refresh",
        entity_category=EntityCategory.DIAGNOSTIC,
        translation_key="refresh_data",
    ),
]


def water_delta_t(device_data: dict, inlet_code: str, outlet_code: str) -> float | None:
    """Outlet minus inlet water temperature, signed."""
    try:
        return float(device_data[outlet_code]) - float(device_data[inlet_code])

    except (KeyError, TypeError, ValueError):
        return None


def compressor_speed(
    device_data: dict,
    device_profile: DeviceProfile,
    frequency_code: str,
    max_frequency_codes: dict[Mode, str],
) -> float | None:
    """The compressor's output frequency as a percentage of the highest one it
    is set to reach in the device's mode, by mode.

    0 while the compressor is stopped, whatever the mode. In auto mode the
    maximum is the heating or the cooling one, as auto_mode_direction tells.
    Unknown while it runs in a mode without a maximum, or when the direction
    can't be told. Not capped: the compressor can run past the maximum, as
    while defrosting.
    """
    try:
        frequency = float(device_data[frequency_code])

        if not isfinite(frequency):
            return None

        if frequency == 0:
            return 0.0

        mode_code = device_profile.get_pc_key(CONFIG_SET_MODE)
        mode = device_profile.hvac_modes_reverse.get(device_data.get(mode_code))

        if mode == Mode.AUTO:
            mode = auto_mode_direction(device_profile, device_data)

        max_frequency_code = max_frequency_codes.get(mode)

        if max_frequency_code is None:
            return None

        max_frequency = float(device_data[max_frequency_code])

    except (KeyError, TypeError, ValueError):
        return None

    if not (isfinite(frequency) and isfinite(max_frequency)):
        return None

    if max_frequency <= 0:
        return None

    speed = round(frequency / max_frequency * 100, 1)

    return speed


def compressor_type_is_not_zero(device_data: dict, type_code: str) -> bool:
    """False when the compressor type reads zero, as the official app does not
    show the speed then. A missing, empty or unreadable type doesn't count as
    zero. "0.0" does: it is read as a number."""
    try:
        return float(device_data[type_code]) != 0

    except (KeyError, TypeError, ValueError):
        return True


def has_readable_value(device_data: dict, code: str) -> bool:
    """Whether the device answered the code with a number."""
    try:
        float(device_data[code])

    except (KeyError, TypeError, ValueError):
        return False

    return True


def has_compressor_speed(
    device_data: dict, type_code: str | None, max_frequency_codes: tuple[str, ...]
) -> bool:
    """Whether the device can show a compressor speed: it reads at least one
    maximum frequency, and its compressor type isn't 0."""
    if type_code is not None and not compressor_type_is_not_zero(
        device_data, type_code
    ):
        return False

    return any(has_readable_value(device_data, code) for code in max_frequency_codes)


def get_derived_entity_descriptions(
    device_profile: DeviceProfile,
) -> list[AquaTempEntityDescription]:
    """Entities computed from other codes, for the roles the mapping defines."""
    entity_descriptions = []

    inlet_code = device_profile.get_pc_key(CONFIG_INLET_WATER_TEMPERATURE)
    outlet_code = device_profile.get_pc_key(CONFIG_OUTLET_WATER_TEMPERATURE)

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
                source_codes=(inlet_code, outlet_code),
            )
        )

    frequency_code = device_profile.get_pc_key(CONFIG_COMPRESSOR_FREQUENCY)
    max_frequency_roles = {
        Mode.HEAT: CONFIG_HEATING_MAX_FREQUENCY,
        Mode.COOL: CONFIG_COOLING_MAX_FREQUENCY,
    }
    max_frequency_codes = {
        mode: device_profile.get_pc_key(role)
        for mode, role in max_frequency_roles.items()
        if device_profile.get_pc_key(role) is not None
    }

    type_code = device_profile.get_pc_key(CONFIG_COMPRESSOR_TYPE)

    if frequency_code is not None and max_frequency_codes:
        entity_descriptions.append(
            AquaTempSensorEntityDescription(
                key="compressor_speed",
                name="Compressor speed",
                icon="mdi:gauge",
                native_unit_of_measurement=PERCENTAGE,
                state_class=SensorStateClass.MEASUREMENT,
                suggested_display_precision=0,
                value_fn=partial(
                    compressor_speed,
                    device_profile=device_profile,
                    frequency_code=frequency_code,
                    max_frequency_codes=max_frequency_codes,
                ),
                translation_key="compressor_speed",
                include_if=partial(
                    has_compressor_speed,
                    type_code=type_code,
                    max_frequency_codes=tuple(max_frequency_codes.values()),
                ),
                source_codes=(frequency_code,),
            )
        )

    return entity_descriptions


def build_entity_descriptions(
    device_profile: DeviceProfile,
) -> list[AquaTempEntityDescription]:
    """Built-in entities, then the catalog's, then those derived from the mapping.

    A catalog entity's translation key is <level>_<key>, lowercased and without
    "/", where level is the profile level whose file defines the entry.
    """
    parameter_layers = device_profile.parameter_layers
    entities = copy(DEFAULT_ENTITY_DESCRIPTIONS)

    for data_item in device_profile.parameters:
        platform = data_item.get("platform")
        key = data_item.get("key")
        # Prefixed with the profile file defining the entry, so an inherited
        # entry shares the translation of the level it comes from
        translation_key = f"{parameter_layers[key]}_{key}".replace("/", "").lower()

        if platform == Platform.SENSOR:
            state_class = data_item.get("state_class")

            sensor_entity = AquaTempSensorEntityDescription(
                key=key,
                name=data_item.get("name"),
                device_class=data_item.get("device_class"),
                native_unit_of_measurement=data_item.get("unit_of_measurement"),
                entity_category=_get_entity_category(data_item),
                state_class=(
                    None if state_class is None else SensorStateClass(state_class)
                ),
                entity_registry_enabled_default=data_item.get("enabled_default", True),
                translation_key=translation_key,
                source_codes=(key,),
            )

            entities.append(sensor_entity)

        elif platform == Platform.BINARY_SENSOR:
            binary_sensor_entity = AquaTempBinarySensorEntityDescription(
                key=key,
                name=data_item.get("name"),
                device_class=data_item.get("device_class"),
                on_value=data_item.get("on_value"),
                off_value=data_item.get("off_value"),
                entity_category=_get_entity_category(data_item),
                entity_registry_enabled_default=data_item.get("enabled_default", True),
                translation_key=translation_key,
                source_codes=(key,),
            )

            entities.append(binary_sensor_entity)

        else:
            entity = AquaTempEntityDescription(
                key=key, name=data_item.get("name"), source_codes=(key,)
            )

            entities.append(entity)

    entities.extend(get_derived_entity_descriptions(device_profile))

    return entities


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
