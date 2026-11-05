"""Per-product device profiles: which protocol codes a device uses and polls."""

from dataclasses import dataclass
import json
from pathlib import Path
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
from .exceptions import InvalidProfileError
from .modes import FanMode, Mode

# The class table, in profiles/
CLASSES_FILE = "classes.json"

# Makes a mapping or catalog file a delta, naming the level it applies on
INHERITS = "inherits"

# A catalog delta's fields
CATALOG_DELTA_REMOVE = "remove"
CATALOG_DELTA_ENTRIES = "entries"
CATALOG_DELTA_FIELDS = {INHERITS, CATALOG_DELTA_REMOVE, CATALOG_DELTA_ENTRIES}

# Polled ahead of the catalog, which lists it too, so it goes on the wire
# twice
POLL_CODE_MODE = "Mode"


class DeviceProfile:
    """The mapping and parameter catalog a device is bound to.

    The mapping names the protocol code behind each role (mode, power, target
    temperature per mode, ...); the catalog lists the parameters to poll. Each
    is resolved from a chain of profile files, see DeviceProfiles.
    """

    _product_class: str | None
    _mapping_chain: tuple[str, ...]
    _mapping: dict
    _catalog_chain: tuple[str, ...]
    _parameters: list[dict]
    _parameter_layers: dict[str, str]

    def __init__(
        self,
        product_class: str | None,
        mapping_chain: tuple[str, ...],
        mapping: dict,
        catalog_chain: tuple[str, ...],
        parameters: list[dict],
        parameter_layers: dict[str, str],
    ):
        self._product_class = product_class
        self._mapping_chain = mapping_chain
        self._mapping = mapping
        self._catalog_chain = catalog_chain
        self._parameters = parameters
        self._parameter_layers = parameter_layers

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
    def product_class(self) -> str | None:
        """The class the product belongs to, None outside every class."""
        return self._product_class

    @property
    def mapping_chain(self) -> tuple[str, ...]:
        """The levels whose mapping files make up the mapping, lowest first."""
        return self._mapping_chain

    @property
    def catalog_chain(self) -> tuple[str, ...]:
        """The levels whose catalog files make up the catalog, lowest first."""
        return self._catalog_chain

    @property
    def mapping(self) -> dict:
        return self._mapping

    @property
    def parameters(self) -> list[dict]:
        """The catalog's entries, as in the profile files that define them."""
        return self._parameters

    @property
    def parameter_layers(self) -> dict[str, str]:
        """The level whose file defines each catalog entry, by key."""
        return self._parameter_layers

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
    def semantic_codes(self) -> dict[str, str]:
        """Each catalog key that has a semantic code, the code the official app
        requests for the same value, mapped to it; in catalog order."""
        semantic_codes = {
            parameter["key"]: parameter["semantic_code"]
            for parameter in self._parameters
            if parameter.get("semantic_code")
        }

        return semantic_codes

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
    """Every product's profile, resolved from the shipped profile files.

    A mapping and a catalog each resolve through up to three levels: the
    product, its class, then default. A level without a file of that kind is
    skipped. A file is either complete, replacing everything below it, or a
    delta holding only its differences from the level below. A delta names
    the level it applies on in "inherits": the nearest level below it with a
    file of its kind, so adding a file under a delta fails on load until the
    delta names it.

    - A catalog is complete as an array of entries. As an object it is a
      delta: "remove" lists keys of inherited entries to drop, and each of
      "entries" replaces the inherited entry with its key whole, in its place,
      or is appended after them, in file order.
    - A mapping is complete as an object without "inherits" and a delta with
      it, merged into the one below key by key, nested objects included;
      a null value means the product has no code for that role.

    The default level must ship both kinds of file, complete. Classes are
    listed in profiles/classes.json as {"<class>": ["<product id>", ...]}; the
    "pool_heat_pump" class holds the 30 product ids the official app handles as
    one group, requesting the same 45 codes and 10 bit codes for all of them,
    inferred to be heat pumps from those codes and pool ones from the app
    showing them with its swimming pool page and image. Every file is resolved
    on load, so a file breaking these rules raises InvalidProfileError there.
    """

    _classes: dict[str, list[str]]
    _profiles: dict[str, DeviceProfile]

    def __init__(
        self,
        mappings: dict[str, dict],
        catalogs: dict[str, list | dict],
        classes: dict[str, list[str]] | None = None,
    ):
        """Mappings and catalogs by level: default, a class name or a product id."""
        self._classes = classes or {}
        class_by_product = _class_by_product(self._classes)

        default_mapping = _resolve_mapping(mappings, PRODUCT_ID_DEFAULT, None)
        default_catalog = _resolve_catalog(catalogs, PRODUCT_ID_DEFAULT, None)

        class_levels = {
            product_class: (
                _resolve_mapping(mappings, product_class, default_mapping),
                _resolve_catalog(catalogs, product_class, default_catalog),
            )
            for product_class in self._classes
        }

        self._profiles = {
            PRODUCT_ID_DEFAULT: _profile(None, default_mapping, default_catalog)
        }

        for product_id in PRODUCT_IDS:
            product_class = class_by_product.get(product_id)
            mapping, catalog = class_levels.get(
                product_class, (default_mapping, default_catalog)
            )

            self._profiles[product_id] = _profile(
                product_class,
                _resolve_mapping(mappings, product_id, mapping),
                _resolve_catalog(catalogs, product_id, catalog),
            )

    @classmethod
    async def load(cls, profiles_path: Path = PROFILES_PATH) -> Self:
        """Read the class table and every level's files from profiles_path.

        Each level may ship a mapping, a catalog, both or neither.
        """
        classes = await _load_json(profiles_path / CLASSES_FILE) or {}
        mappings = {}
        catalogs = {}

        for level in [PRODUCT_ID_DEFAULT, *classes, *PRODUCT_IDS]:
            mapping = await _load_json(
                profiles_path / f"{ProductParameter.MAPPING}.{level}.json"
            )
            catalog = await _load_json(
                profiles_path / f"{ProductParameter.ENTITY_DESCRIPTION}.{level}.json"
            )

            if mapping is not None:
                mappings[level] = mapping

            if catalog is not None:
                catalogs[level] = catalog

        return cls(mappings, catalogs, classes)

    def for_product(self, product_id: str | None) -> DeviceProfile:
        """The product's profile; the default one for a product outside
        PRODUCT_IDS."""
        profile = self._profiles.get(product_id, self._profiles[PRODUCT_ID_DEFAULT])

        return profile


@dataclass(frozen=True)
class _ResolvedMapping:
    chain: tuple[str, ...]
    mapping: dict


@dataclass(frozen=True)
class _ResolvedCatalog:
    chain: tuple[str, ...]
    # The level that defined each entry, with the entry
    entries: list[tuple[str, dict]]


def _profile(
    product_class: str | None, mapping: _ResolvedMapping, catalog: _ResolvedCatalog
) -> DeviceProfile:
    profile = DeviceProfile(
        product_class,
        mapping.chain,
        mapping.mapping,
        catalog.chain,
        [entry for _, entry in catalog.entries],
        {entry["key"]: level for level, entry in catalog.entries},
    )

    return profile


def _class_by_product(classes: dict[str, list[str]]) -> dict[str, str]:
    """Each classified product's class; raises on an id that isn't in
    PRODUCT_IDS or is in two classes, and on a class named like a level."""
    class_by_product = {}

    for product_class, product_ids in classes.items():
        if product_class == PRODUCT_ID_DEFAULT or product_class in PRODUCT_IDS:
            raise InvalidProfileError(
                f"{CLASSES_FILE}: class {product_class} is named like a level"
            )

        for product_id in product_ids:
            if product_id not in PRODUCT_IDS:
                raise InvalidProfileError(
                    f"{CLASSES_FILE}: {product_id} in {product_class} is not a "
                    "known product"
                )

            if product_id in class_by_product:
                raise InvalidProfileError(
                    f"{CLASSES_FILE}: {product_id} is in both "
                    f"{class_by_product[product_id]} and {product_class}"
                )

            class_by_product[product_id] = product_class

    return class_by_product


def _resolve_mapping(
    mappings: dict[str, dict], level: str, below: _ResolvedMapping | None
) -> _ResolvedMapping:
    """The level's mapping file applied on the one resolved below it; below is
    None for the default level, which must be complete."""
    file_name = f"{ProductParameter.MAPPING}.{level}.json"
    mapping = mappings.get(level)

    if mapping is None:
        if below is None:
            raise InvalidProfileError(f"{file_name} is missing")

        return below

    if not isinstance(mapping, dict):
        raise InvalidProfileError(f"{file_name} must be an object")

    if INHERITS not in mapping:
        return _ResolvedMapping((level,), mapping)

    _check_inherits(file_name, mapping, below)

    changes = {key: value for key, value in mapping.items() if key != INHERITS}

    return _ResolvedMapping(
        (*below.chain, level), _merge_mapping(below.mapping, changes)
    )


def _merge_mapping(below: dict, changes: dict) -> dict:
    merged = dict(below)

    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_mapping(merged[key], value)

        else:
            merged[key] = value

    return merged


def _resolve_catalog(
    catalogs: dict[str, list | dict], level: str, below: _ResolvedCatalog | None
) -> _ResolvedCatalog:
    """The level's catalog file applied on the one resolved below it; below is
    None for the default level, which must be complete."""
    file_name = f"{ProductParameter.ENTITY_DESCRIPTION}.{level}.json"
    catalog = catalogs.get(level)

    if catalog is None:
        if below is None:
            raise InvalidProfileError(f"{file_name} is missing")

        return below

    if isinstance(catalog, list):
        _check_unique(file_name, [entry["key"] for entry in catalog])

        return _ResolvedCatalog((level,), [(level, entry) for entry in catalog])

    if not isinstance(catalog, dict):
        raise InvalidProfileError(f"{file_name} must be an array or an object")

    _check_inherits(file_name, catalog, below)

    unknown_fields = catalog.keys() - CATALOG_DELTA_FIELDS

    if unknown_fields:
        raise InvalidProfileError(
            f"{file_name}: unknown fields {', '.join(sorted(unknown_fields))}"
        )

    removed = catalog.get(CATALOG_DELTA_REMOVE, [])
    added = catalog.get(CATALOG_DELTA_ENTRIES, [])
    _check_unique(file_name, [*removed, *(entry["key"] for entry in added)])
    entries = {entry["key"]: entry for entry in added}

    below_keys = {entry["key"] for _, entry in below.entries}
    missing = [key for key in removed if key not in below_keys]

    if missing:
        raise InvalidProfileError(
            f"{file_name}: removes {', '.join(missing)}, which the level below "
            "doesn't have"
        )

    resolved = [
        (level, entries[entry["key"]]) if entry["key"] in entries else (layer, entry)
        for layer, entry in below.entries
        if entry["key"] not in removed
    ]
    resolved.extend(
        (level, entry) for key, entry in entries.items() if key not in below_keys
    )

    return _ResolvedCatalog((*below.chain, level), resolved)


def _check_inherits(
    file_name: str, delta: dict, below: _ResolvedMapping | _ResolvedCatalog | None
):
    """Raises unless the delta's "inherits" names the level it applies on: the
    nearest level below it with a file of its kind."""
    if below is None:
        raise InvalidProfileError(f"{file_name} must be complete, not a delta")

    base = below.chain[-1]

    if delta.get(INHERITS) != base:
        raise InvalidProfileError(
            f'{file_name} applies on {base}, so "{INHERITS}" must be "{base}"'
        )


def _check_unique(file_name: str, keys: list[str]):
    repeated = sorted({key for key in keys if keys.count(key) > 1})

    if repeated:
        raise InvalidProfileError(f"{file_name}: {', '.join(repeated)} more than once")


async def _load_json(file_path: Path):
    """The file's contents, None if there is no such file."""
    if not file_path.exists():
        return None

    async with aiofiles.open(file_path) as file:
        json_str = await file.read()

    return json.loads(json_str)
