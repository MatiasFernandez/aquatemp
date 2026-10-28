"""Wire values, mapping-profile keys and the product allow-list of the cloud API."""

from enum import StrEnum

from .modes import FanMode, Mode

HTTP_HEADER_X_TOKEN = "x-token"

PRODUCT_IDS = [
    "1245226668902080512",  # Hitemp
    "1132174963097280512",  # Aqua Temp
    "1656269521923575808",  # Aqua Temp
    "1663080854333558784",  # Aqua Temp
    "1596427678569979904",  # Aqua Temp
    "1674238226096406528",  # Aqua Temp
    "1650063968998252544",  # Aqua Temp
    "1668781858447085568",  # Aqua Temp
    "1186904563333062656",  # Aqua Temp
    "1158905952238313472",  # Aqua Temp
    "1442284873216843776",  # Aqua Temp
    "1732565142225256450",  # Aqua Temp
    "1548963836789501952",  # Aqua Temp
    "1669159229372477440",  # Aqua Temp
    "1650758828508766208",  # Aqua Temp
    "1664085465655808000",  # Aqua Temp
    "1845987289788989441",  # Aqua Temp
]

POWER_MODE_OFF = "0"
POWER_MODE_ON = "1"

HEADERS = {"Content-Type": "application/json; charset=utf-8"}

API_MAX_ATTEMPTS = 3

CONFIG_SET_MODE = "mode"
CONFIG_SET_POWER = "power"
CONFIG_SET_TEMPERATURE = "temperature"
CONFIG_SET_FAN = "fan"
CONFIG_SET_CURRENT_TEMPERATURE = "current_temperature"
CONFIG_INLET_WATER_TEMPERATURE = "inlet_water_temperature"
CONFIG_OUTLET_WATER_TEMPERATURE = "outlet_water_temperature"

PRODUCT_ID_DEFAULT = "default"

CONFIG_HVAC_MODES = "hvac_modes"
CONFIG_HVAC_OFF = str(Mode.OFF)
CONFIG_HVAC_HEAT = str(Mode.HEAT)
CONFIG_HVAC_COOL = str(Mode.COOL)
CONFIG_HVAC_AUTO = str(Mode.AUTO)
CONFIG_HVAC_SET = "set"
CONFIG_HVAC_TARGET = "target"
CONFIG_HVAC_MINIMUM = "minimum"
CONFIG_HVAC_MAXIMUM = "maximum"

CONFIG_FAN_MODES = "fan_modes"
CONFIG_FAN_AUTO = str(FanMode.AUTO)
CONFIG_FAN_LOW = str(FanMode.LOW)

DEVICE_CONTROL_VALUE = "value"
DEVICE_CONTROL_PARAM = "param"


class ProductParameter(StrEnum):
    MAPPING = "mapping"
    ENTITY_DESCRIPTION = "entity_description"
