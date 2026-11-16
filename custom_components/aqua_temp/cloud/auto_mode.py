"""What a heat pump running in auto mode is doing."""

from math import isfinite

from .consts import CONFIG_HVAC_TARGET, CONFIG_INLET_WATER_TEMPERATURE
from .device_profiles import DeviceProfile
from .modes import Mode


def auto_mode_direction(
    device_profile: DeviceProfile, device_data: dict
) -> Mode | None:
    """Whether a unit running in auto mode heats or cools, as the official app
    works it out: it heats when the auto target temperature is above the inlet
    water temperature, and cools otherwise. Mode.HEAT or Mode.COOL.

    Equal temperatures read as cooling. The app's comparison is obfuscated, so
    that case is inferred.

    None when the profile has no auto mode, no code for the inlet water
    temperature, or either reading is missing or isn't a number.
    """
    if Mode.AUTO not in device_profile.hvac_modes:
        return None

    target_code = device_profile.get_hvac_mode_pc_key(Mode.AUTO, CONFIG_HVAC_TARGET)
    inlet_code = device_profile.get_pc_key(CONFIG_INLET_WATER_TEMPERATURE)

    if target_code is None or inlet_code is None:
        return None

    try:
        target = float(device_data[target_code])
        inlet = float(device_data[inlet_code])

    except (KeyError, TypeError, ValueError):
        return None

    if not (isfinite(target) and isfinite(inlet)):
        return None

    return Mode.HEAT if target > inlet else Mode.COOL
