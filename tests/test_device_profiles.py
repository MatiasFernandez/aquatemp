"""Device profile resolution: which mapping and catalog a product gets, and what they say.

Pins today's resolution, fallbacks included, so moving it into the library cannot
change it unnoticed. Only the resolve fixture knows where profiles are resolved.
"""

from functools import partial
import json
from pathlib import Path

import pytest

PROFILES = Path(__file__).parents[1] / "custom_components/aqua_temp/parameters"

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
def resolve(config_manager):
    """Everything the profile resolved for a product's device decides, by product id."""
    return partial(resolve_with_config_manager, config_manager)


def resolve_with_config_manager(config_manager, product_id: str) -> dict:
    device_code = f"device-{product_id}"

    config_manager.set_device(device_code, product_id)

    binding = config_manager._devices[device_code]
    hvac_modes = config_manager.get_hvac_modes(device_code)
    fan_modes = config_manager.get_fan_modes(device_code)

    return {
        "mapping_id": binding["mapping"],
        "catalog_id": binding["entity_description"],
        "pc_keys": {
            role: config_manager.get_pc_key(device_code, role) for role in ROLES
        },
        "hvac_modes": hvac_modes,
        "hvac_modes_reverse": {
            value: config_manager.get_hvac_reverse_mapping(device_code, value)
            for value in hvac_modes.values()
        },
        "fan_modes": fan_modes,
        "fan_modes_reverse": {
            value: config_manager.get_fan_reverse_mapping(device_code, value)
            for value in fan_modes.values()
        },
        "mode_codes": {
            mode: [
                config_manager.get_hvac_mode_pc_key(device_code, mode, key)
                for key in MODE_CODES
            ]
            for mode in hvac_modes
        },
        "poll_codes": config_manager.get_supported_protocol_codes(device_code),
        "platforms": {
            str(description.platform)
            for description in config_manager.get_entity_descriptions(device_code)
            if description.platform is not None
        },
    }


def catalog_keys(catalog_id: str) -> list[str]:
    catalog = PROFILES / f"entity_description.{catalog_id}.json"

    return [item["key"] for item in json.loads(catalog.read_text())]


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

PLATFORMS = {"binary_sensor", "climate", "select", "sensor"}


@pytest.mark.parametrize(
    ("product_id", "mapping_id", "catalog_id", "mapping"),
    [
        ("default", "default", "default", DEFAULT_MAPPING),
        (HITEMP, HITEMP, HITEMP, HITEMP_MAPPING),
        (AQUA_TEMP, AQUA_TEMP, AQUA_TEMP, AQUA_TEMP_MAPPING),
        (UNKNOWN, "default", "default", DEFAULT_MAPPING),
        (PEISA, "default", "default", DEFAULT_MAPPING),
    ],
    ids=["default", "hitemp", "aqua_temp", "unknown", "peisa"],
)
def test_product_resolves_to_its_profile(
    resolve, product_id, mapping_id, catalog_id, mapping
):
    profile = resolve(product_id)

    assert profile == {
        "mapping_id": mapping_id,
        "catalog_id": catalog_id,
        **mapping,
        # Possible bug: "Mode" leads even where the catalog lists it, and
        # even for Hitemp, whose mode role is mode_real
        "poll_codes": ["Mode", *catalog_keys(catalog_id)],
        "platforms": PLATFORMS,
    }
