"""Wire values, mapping-profile keys and the product allow-list of the cloud API."""

from enum import StrEnum

from .modes import FanMode, Mode

HTTP_HEADER_X_TOKEN = "x-token"

# Every heat pump the Aqua Temp Android app lists as of version 2.1.5, plus Hitemp,
# which the app doesn't list
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
    "1845987289788989441",  # Aqua Temp
    "1245644363707658240",  # Aqua Temp
    "1411880504755519488",  # Aqua Temp
    "1580015159123103744",  # Aqua Temp
    "1723968101434449921",  # Aqua Temp
    "1747074936915042306",  # Aqua Temp
    "1747077846280486914",  # Aqua Temp
    "1752888899863797762",  # Aqua Temp
    "1777261505886740482",  # Aqua Temp
    "1811606097627443201",  # Aqua Temp
    "1821729460190392321",  # Aqua Temp
    "1833329364592959490",  # Aqua Temp
    "1855893688663838722",  # Aqua Temp
    "1905164506956177410",  # Aqua Temp
    "2034832864020103169",  # Aqua Temp
    "2039970527406370818",  # Aqua Temp
]

POWER_MODE_OFF = "0"
POWER_MODE_ON = "1"

HEADERS = {"Content-Type": "application/json; charset=utf-8"}

API_MAX_ATTEMPTS = 3

# Seconds a single request to the cloud may take in total. The official app's
# HTTP client also uses 30 s
API_REQUEST_TIMEOUT = 30

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
