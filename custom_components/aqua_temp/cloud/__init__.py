"""Client for the Aqua Temp / HiTemp cloud API, with no Home Assistant dependency."""

from .api_types import API_TYPE_LEGACY, API_TYPES, APIParam, APIType
from .consts import PRODUCT_IDS
from .endpoints import Endpoints
from .exceptions import InvalidTokenError, LoginError, OperationFailedException
from .modes import FanMode, Mode

__all__ = [
    "API_TYPES",
    "API_TYPE_LEGACY",
    "PRODUCT_IDS",
    "APIParam",
    "APIType",
    "Endpoints",
    "FanMode",
    "InvalidTokenError",
    "LoginError",
    "Mode",
    "OperationFailedException",
]
