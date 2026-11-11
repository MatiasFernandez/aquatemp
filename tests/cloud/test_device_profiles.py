"""Device profile resolution: which mapping and catalog a product gets, and what they say.

Pins today's resolution, fallbacks included, so moving it into the library cannot
change it unnoticed. Only the resolve fixture knows where profiles are resolved.
"""

from functools import partial
import json
from pathlib import Path

import pytest

from custom_components.aqua_temp.cloud.device_profiles import DeviceProfiles

PROFILES = Path(__file__).parents[2] / "custom_components/aqua_temp/cloud/profiles"

ROLES = [
    "mode",
    "power",
    "temperature",
    "fan",
    "current_temperature",
    "inlet_water_temperature",
    "outlet_water_temperature",
]
MODE_CODES = ["target", "minimum", "maximum"]

HITEMP = "1245226668902080512"
AQUA_TEMP = "1442284873216843776"
# In PRODUCT_IDS, with no profile files of its own
PEISA = "1132174963097280512"
UNKNOWN = "1000000000000000000"


@pytest.fixture
def resolve(device_profiles):
    """Everything the profile resolved for a product's device decides, by product id."""
    return partial(resolve_with_profiles, device_profiles)


def resolve_with_profiles(device_profiles: DeviceProfiles, product_id: str) -> dict:
    profile = device_profiles.for_product(product_id)

    return {
        "class": profile.product_class,
        "mapping_chain": profile.mapping_chain,
        "catalog_chain": profile.catalog_chain,
        "pc_keys": {role: profile.get_pc_key(role) for role in ROLES},
        "hvac_modes": profile.hvac_modes,
        "hvac_modes_reverse": profile.hvac_modes_reverse,
        "fan_modes": profile.fan_modes,
        "fan_modes_reverse": profile.fan_modes_reverse,
        "mode_codes": {
            mode: [profile.get_hvac_mode_pc_key(mode, key) for key in MODE_CODES]
            for mode in profile.hvac_modes
        },
        "poll_codes": profile.poll_codes,
        "bit_codes": profile.bit_codes,
        "semantic_codes": profile.semantic_codes,
    }


def read_catalog(catalog_id: str) -> list | dict:
    catalog = PROFILES / f"entity_description.{catalog_id}.json"

    return json.loads(catalog.read_text(encoding="utf-8"))


def catalog_entries(catalog_id: str) -> list[dict]:
    """The entries of a catalog file, read from the file itself. A delta keeps
    the entries of the level it inherits but those it removes, replacing those
    it brings again in place, then adds the others it brings."""
    catalog = read_catalog(catalog_id)

    if isinstance(catalog, list):
        return catalog

    inherited = catalog_entries(catalog["inherits"])
    inherited_keys = {item["key"] for item in inherited}
    removed = set(catalog.get("remove", []))
    added = {item["key"]: item for item in catalog.get("entries", [])}

    return [
        added.get(item["key"], item) for item in inherited if item["key"] not in removed
    ] + [item for key, item in added.items() if key not in inherited_keys]


def polled_keys(catalog_id: str, bit_codes: bool) -> list[str]:
    """The catalog's keys requested in the bit codes array, or those that
    aren't."""
    return [
        item["key"]
        for item in catalog_entries(catalog_id)
        if (item.get("request_field") == "bitCodes") == bit_codes
    ]


DEFAULT_MAPPING = {
    "pc_keys": {
        "mode": "Mode",
        "power": "Power",
        "temperature": "Set_Temp",
        "fan": "Manual-mute",
        "current_temperature": "T02",
        "inlet_water_temperature": "T02",
        "outlet_water_temperature": "T03",
    },
    "hvac_modes": {"off": None, "cool": "0", "heat": "1", "auto": "2"},
    "hvac_modes_reverse": {None: "off", "0": "cool", "1": "heat", "2": "auto"},
    "fan_modes": {"auto": "0", "low": "1"},
    "fan_modes_reverse": {"0": "auto", "1": "low"},
    "mode_codes": {
        "off": [None, None, None],
        "cool": ["R01", "R08", "R09"],
        "heat": ["R02", "R10", "R11"],
        "auto": ["R03", "R08", "R11"],
    },
}

HITEMP_MAPPING = {
    "pc_keys": {
        "mode": "mode_real",
        "power": "MO6",
        "temperature": "R01",
        "fan": "M17",
        "current_temperature": "T10",
        "inlet_water_temperature": None,
        "outlet_water_temperature": None,
    },
    "hvac_modes": {"off": None, "heat": "0"},
    "hvac_modes_reverse": {None: "off", "0": "heat"},
    "fan_modes": {"off": "0", "low": "1", "high": "2"},
    "fan_modes_reverse": {"0": "off", "1": "low", "2": "high"},
    "mode_codes": {"off": [None, None, None], "heat": ["R01", "T02", "T03"]},
}

# The default mapping without the water roles, reading the current
# temperature from T2
AQUA_TEMP_MAPPING = DEFAULT_MAPPING | {
    "pc_keys": DEFAULT_MAPPING["pc_keys"]
    | {
        "current_temperature": "T2",
        "inlet_water_temperature": None,
        "outlet_water_temperature": None,
    }
}


# Each pairing proven on a unit by reading both codes in the same request
SEMANTIC_CODES = {
    "default": {
        "Set_Temp": "SetCurrentTemp",
        "R02": "SetHeatTargetTemp",
        "R08": "SetCoolMinTargetTemp",
        "R09": "SetCoolMaxTargetTemp",
        "R10": "SetHeatMinTargetTemp",
        "R11": "SetHeatMaxTargetTemp",
        "T02": "InletWaterTemp",
        "T03": "OutletWaterTemp",
    },
    HITEMP: {},
    AQUA_TEMP: {},
}
# The class adds bit codes only, which have no semantic code
SEMANTIC_CODES["pool_heat_pump"] = SEMANTIC_CODES["default"]


@pytest.mark.parametrize(
    ("product_id", "product_class", "mapping_chain", "catalog_chain", "mapping"),
    [
        ("default", None, ("default",), ("default",), DEFAULT_MAPPING),
        (HITEMP, None, (HITEMP,), (HITEMP,), HITEMP_MAPPING),
        (
            AQUA_TEMP,
            "pool_heat_pump",
            (AQUA_TEMP,),
            ("default", "pool_heat_pump", AQUA_TEMP),
            AQUA_TEMP_MAPPING,
        ),
        (UNKNOWN, None, ("default",), ("default",), DEFAULT_MAPPING),
        (
            PEISA,
            "pool_heat_pump",
            ("default",),
            ("default", "pool_heat_pump"),
            DEFAULT_MAPPING,
        ),
    ],
    ids=["default", "hitemp", "aqua_temp", "unknown", "peisa"],
)
def test_product_resolves_to_its_profile(
    resolve, product_id, product_class, mapping_chain, catalog_chain, mapping
):
    # The class ships a catalog but no mapping, so it is only in the catalog
    # chain
    profile = resolve(product_id)

    assert profile == {
        "class": product_class,
        "mapping_chain": mapping_chain,
        "catalog_chain": catalog_chain,
        **mapping,
        # Possible bug: "Mode" leads even where the catalog lists it, and
        # even for Hitemp, whose mode role is mode_real
        "poll_codes": ["Mode", *polled_keys(catalog_chain[-1], bit_codes=False)],
        "bit_codes": polled_keys(catalog_chain[-1], bit_codes=True),
        "semantic_codes": SEMANTIC_CODES[catalog_chain[-1]],
    }
