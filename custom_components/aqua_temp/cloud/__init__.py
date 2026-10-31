"""Client for the Aqua Temp / HiTemp cloud API, with no Home Assistant dependency."""

from .api_profile import ApiProfile
from .api_types import API_TYPE_LEGACY, API_TYPES, APIParam, APIType
from .client import AquaTempAPI, Credentials, DeviceMeta
from .consts import PRODUCT_IDS
from .device_profiles import DeviceProfile, DeviceProfiles
from .endpoints import Endpoints
from .exceptions import (
    DeviceNotRespondingError,
    DeviceOfflineError,
    InvalidTokenError,
    LoginError,
    OperationFailedException,
)
from .modes import FanMode, Mode

__all__ = [
    "API_TYPES",
    "API_TYPE_LEGACY",
    "PRODUCT_IDS",
    "APIParam",
    "APIType",
    "ApiProfile",
    "AquaTempAPI",
    "Credentials",
    "DeviceMeta",
    "DeviceNotRespondingError",
    "DeviceOfflineError",
    "DeviceProfile",
    "DeviceProfiles",
    "Endpoints",
    "FanMode",
    "InvalidTokenError",
    "LoginError",
    "Mode",
    "OperationFailedException",
]
