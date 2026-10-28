"""Per-product device profiles: which protocol codes a device uses and polls."""

import json
from typing import Self

import aiofiles

from .api_profile import PROFILES_PATH
from .consts import (
    CONFIG_FAN_MODES,
    CONFIG_HVAC_MODES,
    CONFIG_HVAC_SET,
    PRODUCT_ID_DEFAULT,
    PRODUCT_IDS,
    ProductParameter,
)
from .modes import FanMode, Mode

# Polled ahead of the catalog, which lists it too, so it goes on the wire
# twice
POLL_CODE_MODE = "Mode"


class DeviceProfile:
    """The mapping and parameter catalog a device is bound to.

    The mapping names the protocol code behind each role (mode, power, target
    temperature per mode, ...); the catalog lists the parameters to poll.
    """

    _mapping_id: str
    _mapping: dict
    _catalog_id: str
    _parameters: list[dict]

    def __init__(
        self, mapping_id: str, mapping: dict, catalog_id: str, parameters: list[dict]
    ):
        self._mapping_id = mapping_id
        self._mapping = mapping
        self._catalog_id = catalog_id
        self._parameters = parameters

        hvac_modes = mapping.get(CONFIG_HVAC_MODES)
        fan_modes = mapping.get(CONFIG_FAN_MODES)

        self._hvac_modes = {
            Mode(mode): hvac_modes[mode].get(CONFIG_HVAC_SET) for mode in hvac_modes
        }
        self._hvac_modes_reverse = {
            value: mode for mode, value in self._hvac_modes.items()
        }

        self._fan_modes = {FanMode(mode): fan_modes[mode] for mode in fan_modes}
        self._fan_modes_reverse = {
            value: mode for mode, value in self._fan_modes.items()
        }

    @property
    def mapping_id(self) -> str:
        return self._mapping_id

    @property
    def catalog_id(self) -> str:
        return self._catalog_id

    @property
    def mapping(self) -> dict:
        return self._mapping

    @property
    def parameters(self) -> list[dict]:
        """The catalog's entries, as in the profile file."""
        return self._parameters

    @property
    def poll_codes(self) -> list[str]:
        """The codes to request on each fetch: "Mode", then every catalog key.

        "Mode" leads even where the catalog lists it, and even for Hitemp,
        whose mode role is mode_real.
        """
        codes = [POLL_CODE_MODE]
        codes.extend(parameter.get("key") for parameter in self._parameters)

        return codes

    @property
    def hvac_modes(self) -> dict[Mode, str | None]:
        """Each mode's value on the wire."""
        return self._hvac_modes

    @property
    def hvac_modes_reverse(self) -> dict[str | None, Mode]:
        """Each wire value's mode; None, the value of off, maps to Mode.OFF."""
        return self._hvac_modes_reverse

    @property
    def fan_modes(self) -> dict[FanMode, str]:
        """Each fan mode's value on the wire."""
        return self._fan_modes

    @property
    def fan_modes_reverse(self) -> dict[str, FanMode]:
        """Each wire value's fan mode."""
        return self._fan_modes_reverse

    def get_pc_key(self, key: str) -> str | None:
        """The protocol code behind a role (CONFIG_SET_*), None if unmapped."""
        protocol_code_key = self._mapping.get(key)

        return protocol_code_key

    def get_hvac_mode_pc_key(self, hvac_mode: str, key: str) -> str | None:
        """A mode's entry for key (CONFIG_HVAC_SET, _TARGET, _MINIMUM, _MAXIMUM).

        None if the mode maps no code for key, as off does for all of them.
        Raises AttributeError for a mode the mapping does not list.
        """
        hvac_modes = self._mapping.get(CONFIG_HVAC_MODES)
        hvac_mode_config = hvac_modes.get(hvac_mode)
        protocol_code_key = hvac_mode_config.get(key)

        return protocol_code_key


class DeviceProfiles:
    """Every shipped mapping and catalog, by product id."""

    _mappings: dict[str, dict]
    _catalogs: dict[str, list[dict]]

    def __init__(self, mappings: dict[str, dict], catalogs: dict[str, list[dict]]):
        self._mappings = mappings
        self._catalogs = catalogs

    @classmethod
    async def load(cls) -> Self:
        """Read the default's and each PRODUCT_IDS product's files from profiles/.

        A product may ship a mapping, a catalog, both or neither.
        """
        mappings = {}
        catalogs = {}

        for product_id in [PRODUCT_ID_DEFAULT, *PRODUCT_IDS]:
            mapping = await _load_product_file(ProductParameter.MAPPING, product_id)
            catalog = await _load_product_file(
                ProductParameter.ENTITY_DESCRIPTION, product_id
            )

            if mapping is not None:
                mappings[product_id] = mapping

            if catalog is not None:
                catalogs[product_id] = catalog

        return cls(mappings, catalogs)

    def for_product(self, product_id: str | None) -> DeviceProfile:
        """The product's profile; its mapping and catalog fall back to the
        default ones independently."""
        mapping_id = product_id if product_id in self._mappings else PRODUCT_ID_DEFAULT
        catalog_id = product_id if product_id in self._catalogs else PRODUCT_ID_DEFAULT

        profile = DeviceProfile(
            mapping_id,
            self._mappings[mapping_id],
            catalog_id,
            self._catalogs[catalog_id],
        )

        return profile


async def _load_product_file(parameter: ProductParameter, product_id: str):
    file_path = PROFILES_PATH / f"{parameter}.{product_id}.json"

    if not file_path.exists():
        return None

    async with aiofiles.open(file_path) as file:
        json_str = await file.read()

    return json.loads(json_str)
