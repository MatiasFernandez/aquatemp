"""Per-API-type field names, from profiles/api.<type>.json."""

import asyncio
import json
from pathlib import Path
from typing import Any, Self

from .api_types import APIParam

PROFILES_PATH = Path(__file__).parent / "profiles"


async def read_profile_json(file_path: Path) -> Any:
    """Read and parse a JSON profile file off the event loop.

    Raises FileNotFoundError if the file does not exist.
    """
    return await asyncio.to_thread(_read_json, file_path)


def _read_json(file_path: Path) -> Any:
    return json.loads(file_path.read_text(encoding="utf-8"))


class ApiProfile:
    """What one API type calls each field: the contents of api.<type>.json."""

    _api_type: str
    _fields: dict

    def __init__(self, api_type: str, fields: dict):
        self._api_type = api_type
        self._fields = fields

    @property
    def api_type(self) -> str:
        return self._api_type

    @classmethod
    async def load(cls, api_type: str) -> Self:
        """Read profiles/api.<api_type>.json; api_type is an APIType value."""
        file_path = PROFILES_PATH / f"api.{api_type}.json"

        return cls(api_type, await read_profile_json(file_path))

    def get(self, param: APIParam):
        """This API type's value for param: a field name, the URL, or a flag
        such as keep_alive. None if the profile does not define it."""
        result = self._fields.get(str(param))

        return result
