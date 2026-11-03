"""Per-API-type field names, from profiles/api.<type>.json."""

import json
from pathlib import Path
from typing import Self

import aiofiles

from .api_types import APIParam
from .endpoints import Endpoints

PROFILES_PATH = Path(__file__).parent / "profiles"


class ApiProfile:
    """What one API type calls each field: the contents of api.<type>.json."""

    _api_type: str
    _fields: dict
    _data_endpoint: Endpoints

    def __init__(self, api_type: str, fields: dict):
        self._api_type = api_type
        self._fields = fields

        # Checked here so a path that isn't a known endpoint fails on load
        self._data_endpoint = Endpoints(fields[APIParam.DataEndpoint])

    @property
    def api_type(self) -> str:
        return self._api_type

    @property
    def data_endpoint(self) -> Endpoints:
        """Where this API type reads device data."""
        return self._data_endpoint

    @classmethod
    async def load(cls, api_type: str) -> Self:
        """Read profiles/api.<api_type>.json; api_type is an APIType value."""
        file_path = PROFILES_PATH / f"api.{api_type}.json"

        async with aiofiles.open(file_path) as file:
            json_str = await file.read()

        return cls(api_type, json.loads(json_str))

    def get(self, param: APIParam):
        """This API type's value for param: a field name, the URL, or a flag
        such as keep_alive. None if the profile does not define it."""
        result = self._fields.get(str(param))

        return result
