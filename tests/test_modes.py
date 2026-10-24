"""The library's mode enums stay in step with Home Assistant's values."""

import pytest

from custom_components.aqua_temp.cloud.modes import FanMode, Mode
from homeassistant.components.climate import const as climate


@pytest.mark.parametrize("mode", list(Mode), ids=str)
def test_mode_is_an_hvac_mode(mode):
    assert climate.HVACMode(mode) == mode


@pytest.mark.parametrize("fan_mode", list(FanMode), ids=str)
def test_fan_mode_is_a_climate_fan_mode(fan_mode):
    fan_constants = {
        value for name, value in vars(climate).items() if name.startswith("FAN_")
    }

    assert fan_mode in fan_constants
