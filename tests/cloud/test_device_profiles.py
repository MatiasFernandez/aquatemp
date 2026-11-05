"""Device profile resolution: which mapping and catalog a product gets, and what they say.

Pins today's resolution, fallbacks included, so moving it into the library cannot
change it unnoticed. Only the resolve fixture knows where profiles are resolved.
"""

from functools import partial
import json
from pathlib import Path

import pytest

from custom_components.aqua_temp.cloud.device_profiles import DeviceProfiles

RESOLVED_PROFILES = Path(__file__).parent / "resolved_profiles.json"

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
        "semantic_codes": profile.semantic_codes,
    }


def catalog_keys(product_id: str) -> list[str]:
    """The keys of the product's catalog in the resolved-profile reference."""
    reference = json.loads(RESOLVED_PROFILES.read_text(encoding="utf-8"))
    [catalog] = [
        group["catalog"]
        for group in reference["catalogs"]
        if product_id in group["products"]
    ]

    return [item["key"] for item in catalog]


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


@pytest.mark.parametrize(
    ("product_id", "product_class", "mapping_chain", "catalog_chain", "mapping"),
    [
        ("default", None, ("default",), ("default",), DEFAULT_MAPPING),
        (HITEMP, None, (HITEMP,), (HITEMP,), HITEMP_MAPPING),
        (
            AQUA_TEMP,
            "pool_heat_pump",
            (AQUA_TEMP,),
            ("default", AQUA_TEMP),
            AQUA_TEMP_MAPPING,
        ),
        (UNKNOWN, None, ("default",), ("default",), DEFAULT_MAPPING),
        (PEISA, "pool_heat_pump", ("default",), ("default",), DEFAULT_MAPPING),
    ],
    ids=["default", "hitemp", "aqua_temp", "unknown", "peisa"],
)
def test_product_resolves_to_its_profile(
    resolve, product_id, product_class, mapping_chain, catalog_chain, mapping
):
    # No class file ships, so the class adds nothing to either chain
    profile = resolve(product_id)

    assert profile == {
        "class": product_class,
        "mapping_chain": mapping_chain,
        "catalog_chain": catalog_chain,
        **mapping,
        # Possible bug: "Mode" leads even where the catalog lists it, and
        # even for Hitemp, whose mode role is mode_real
        "poll_codes": ["Mode", *catalog_keys(product_id)],
        "semantic_codes": SEMANTIC_CODES[catalog_chain[-1]],
    }
