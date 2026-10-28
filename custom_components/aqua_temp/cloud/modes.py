"""Operating and fan modes, independent of Home Assistant's HVACMode."""

from enum import StrEnum


class Mode(StrEnum):
    """Operating modes, keyed as in the mapping profiles."""

    OFF = "off"
    COOL = "cool"
    HEAT = "heat"
    AUTO = "auto"


class FanMode(StrEnum):
    """Fan modes, keyed as in the mapping profiles."""

    AUTO = "auto"
    LOW = "low"
    OFF = "off"
    HIGH = "high"
