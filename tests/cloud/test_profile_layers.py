"""Profile layering: product, class, then default, each file complete or a delta.

Synthetic profiles in a temporary directory stand in for the shipped ones, which
ship no class file.
"""

import json

import pytest

from custom_components.aqua_temp.cloud.device_profiles import DeviceProfiles
from custom_components.aqua_temp.cloud.exceptions import InvalidProfileError

# Known products: two in the class, one outside every class
MEMBER = "1132174963097280512"
OTHER_MEMBER = "1656269521923575808"
OUTSIDER = "1245226668902080512"

CLASSES = {"pool_heat_pump": [MEMBER, OTHER_MEMBER]}

DEFAULT_MAPPING = {
    "mode": "Mode",
    "power": "Power",
    "temperature": "Set_Temp",
    "fan": "Manual-mute",
    "current_temperature": "T02",
    "hvac_modes": {
        "off": {"set": None, "target": None},
        "heat": {"set": "1", "target": "R02"},
    },
    "fan_modes": {"auto": "0"},
}

A = {"key": "A", "platform": "sensor"}
B = {"key": "B", "platform": "sensor"}
C = {"key": "C", "platform": None}
D = {"key": "D", "platform": "sensor"}
E = {"key": "E", "platform": None}

DEFAULT_FILES = {
    "classes.json": CLASSES,
    "mapping.default.json": DEFAULT_MAPPING,
    "entity_description.default.json": [A, B, C],
}


def write_profiles(tmp_path, files: dict):
    """The default files with files added or replaced; a None value leaves
    that file out."""
    for name, content in (DEFAULT_FILES | files).items():
        if content is not None:
            (tmp_path / name).write_text(json.dumps(content))


async def load(tmp_path, files: dict) -> DeviceProfiles:
    write_profiles(tmp_path, files)

    return await DeviceProfiles.load(tmp_path)


def catalog(profiles: DeviceProfiles, product_id: str) -> tuple:
    profile = profiles.for_product(product_id)

    return profile.catalog_chain, profile.parameters


async def test_class_members_inherit_the_class_file(tmp_path):
    profiles = await load(
        tmp_path,
        {
            "entity_description.pool_heat_pump.json": {
                "inherits": "default",
                "entries": [D],
            }
        },
    )

    assert [catalog(profiles, MEMBER), catalog(profiles, OTHER_MEMBER)] == [
        (("default", "pool_heat_pump"), [A, B, C, D]),
        (("default", "pool_heat_pump"), [A, B, C, D]),
    ]


async def test_product_delta_applies_on_its_class(tmp_path):
    profiles = await load(
        tmp_path,
        {
            "entity_description.pool_heat_pump.json": {
                "inherits": "default",
                "entries": [D],
            },
            f"entity_description.{MEMBER}.json": {
                "inherits": "pool_heat_pump",
                "remove": ["B"],
            },
        },
    )

    assert catalog(profiles, MEMBER) == (
        ("default", "pool_heat_pump", MEMBER),
        [A, C, D],
    )


async def test_complete_product_file_replaces_its_class_and_default(tmp_path):
    profiles = await load(
        tmp_path,
        {
            "entity_description.pool_heat_pump.json": {
                "inherits": "default",
                "entries": [D],
            },
            f"entity_description.{MEMBER}.json": [E],
        },
    )

    assert catalog(profiles, MEMBER) == ((MEMBER,), [E])


async def test_product_outside_every_class_applies_on_default(tmp_path):
    profiles = await load(
        tmp_path,
        {
            "entity_description.pool_heat_pump.json": {
                "inherits": "default",
                "entries": [D],
            },
            f"entity_description.{OUTSIDER}.json": {
                "inherits": "default",
                "entries": [E],
            },
        },
    )

    assert catalog(profiles, OUTSIDER) == (("default", OUTSIDER), [A, B, C, E])


async def test_overriding_entry_keeps_the_inherited_position(tmp_path):
    new_b = {"key": "B", "platform": None}

    profiles = await load(
        tmp_path,
        {
            f"entity_description.{MEMBER}.json": {
                "inherits": "default",
                "entries": [new_b],
            }
        },
    )

    assert catalog(profiles, MEMBER) == (("default", MEMBER), [A, new_b, C])


async def test_added_entries_follow_the_inherited_ones_in_file_order(tmp_path):
    profiles = await load(
        tmp_path,
        {
            f"entity_description.{MEMBER}.json": {
                "inherits": "default",
                "entries": [E, D],
            }
        },
    )

    assert catalog(profiles, MEMBER) == (("default", MEMBER), [A, B, C, E, D])


async def test_each_entry_records_the_level_defining_it(tmp_path):
    profiles = await load(
        tmp_path,
        {
            "entity_description.pool_heat_pump.json": {
                "inherits": "default",
                "entries": [D],
            },
            f"entity_description.{MEMBER}.json": {
                "inherits": "pool_heat_pump",
                "entries": [{**B, "name": "B"}],
            },
        },
    )

    assert profiles.for_product(MEMBER).parameter_layers == {
        "A": "default",
        "B": MEMBER,
        "C": "default",
        "D": "pool_heat_pump",
    }


async def test_mapping_delta_merges_key_by_key(tmp_path):
    profiles = await load(
        tmp_path,
        {
            "mapping.pool_heat_pump.json": {
                "inherits": "default",
                "hvac_modes": {"heat": {"target": "R04"}},
            },
            f"mapping.{MEMBER}.json": {"inherits": "pool_heat_pump", "mode": "Mode2"},
        },
    )
    profile = profiles.for_product(MEMBER)

    assert (profile.mapping_chain, profile.mapping) == (
        ("default", "pool_heat_pump", MEMBER),
        {
            "mode": "Mode2",
            "power": "Power",
            "temperature": "Set_Temp",
            "fan": "Manual-mute",
            "current_temperature": "T02",
            "hvac_modes": {
                "off": {"set": None, "target": None},
                "heat": {"set": "1", "target": "R04"},
            },
            "fan_modes": {"auto": "0"},
        },
    )


async def test_null_in_a_mapping_delta_leaves_an_optional_role_without_a_code(
    tmp_path,
):
    profiles = await load(
        tmp_path,
        {
            f"mapping.{MEMBER}.json": {
                "inherits": "default",
                "current_temperature": None,
            }
        },
    )
    profile = profiles.for_product(MEMBER)

    assert (profile.mapping, profile.get_pc_key("current_temperature")) == (
        {
            "mode": "Mode",
            "power": "Power",
            "temperature": "Set_Temp",
            "fan": "Manual-mute",
            "hvac_modes": {
                "off": {"set": None, "target": None},
                "heat": {"set": "1", "target": "R02"},
            },
            "fan_modes": {"auto": "0"},
        },
        None,
    )


@pytest.mark.parametrize(
    "inherited",
    [{}, {"extra": "x"}],
    ids=["under_a_new_key", "replacing_a_value_that_is_not_an_object"],
)
async def test_null_in_a_mapping_delta_is_removed_at_any_depth(tmp_path, inherited):
    mapping = DEFAULT_MAPPING | inherited
    delta = {"extra": {"kept": "K1", "dropped": None, "nested": {"gone": None}}}

    profiles = await load(
        tmp_path,
        {
            "mapping.default.json": mapping,
            f"mapping.{MEMBER}.json": {"inherits": "default"} | delta,
        },
    )
    profile = profiles.for_product(MEMBER)

    assert profile.mapping["extra"] == {"kept": "K1", "nested": {}}


async def test_null_in_a_mapping_delta_drops_a_mode(tmp_path):
    profiles = await load(
        tmp_path,
        {
            f"mapping.{MEMBER}.json": {
                "inherits": "default",
                "hvac_modes": {"heat": None},
                "fan_modes": {"auto": None, "low": "1"},
            }
        },
    )
    profile = profiles.for_product(MEMBER)

    assert (profile.hvac_modes, profile.fan_modes) == (
        {"off": None},
        {"low": "1"},
    )


async def test_complete_mapping_replaces_the_one_below(tmp_path):
    mapping = DEFAULT_MAPPING | {"power": "MO6"}

    profiles = await load(tmp_path, {"mapping.pool_heat_pump.json": mapping})
    profile = profiles.for_product(MEMBER)

    assert (profile.mapping_chain, profile.mapping) == (("pool_heat_pump",), mapping)


async def test_product_reports_its_class(tmp_path):
    profiles = await load(tmp_path, {})

    assert [
        profiles.for_product(product_id).product_class
        for product_id in (MEMBER, OUTSIDER, "default", None)
    ] == ["pool_heat_pump", None, None, None]


@pytest.mark.parametrize(
    ("files", "error"),
    [
        (
            {
                f"entity_description.{MEMBER}.json": {
                    "inherits": "default",
                    "remove": ["Z"],
                }
            },
            "removes Z, which the level below doesn't have",
        ),
        (
            {f"entity_description.{MEMBER}.json": [A, A]},
            "A more than once",
        ),
        (
            {
                f"entity_description.{MEMBER}.json": {
                    "inherits": "default",
                    "remove": ["A"],
                    "entries": [A],
                }
            },
            "A more than once",
        ),
        (
            {
                f"entity_description.{MEMBER}.json": {
                    "inherits": "default",
                    "entries": [D],
                    "add": [E],
                }
            },
            "unknown fields add",
        ),
        (
            {"entity_description.default.json": {"entries": [A]}},
            "must be complete, not a delta",
        ),
        (
            {"mapping.default.json": DEFAULT_MAPPING | {"inherits": "default"}},
            "must be complete, not a delta",
        ),
        (
            {f"entity_description.{MEMBER}.json": {"remove": ["B"]}},
            f'entity_description.{MEMBER}.json applies on default, so "inherits" '
            'must be "default"',
        ),
        (
            {f"mapping.{MEMBER}.json": {"inherits": "pool_heat_pump", "power": "P"}},
            f'mapping.{MEMBER}.json applies on default, so "inherits" must be '
            '"default"',
        ),
        (
            {
                "entity_description.pool_heat_pump.json": {
                    "inherits": "default",
                    "entries": [D],
                },
                f"entity_description.{MEMBER}.json": {
                    "inherits": "default",
                    "remove": ["B"],
                },
            },
            f"entity_description.{MEMBER}.json applies on pool_heat_pump, so "
            '"inherits" must be "pool_heat_pump"',
        ),
        ({"entity_description.default.json": None}, "is missing"),
        ({"mapping.default.json": None}, "is missing"),
        ({"classes.json": None}, "classes.json is missing"),
        ({f"mapping.{MEMBER}.json": ["Power"]}, "must be an object"),
        (
            {f"entity_description.{MEMBER}.json": "T01"},
            "must be an array or an object",
        ),
        (
            {"classes.json": {"pool_heat_pump": ["1000000000000000000"]}},
            "1000000000000000000 in pool_heat_pump is not a known product",
        ),
        (
            {"classes.json": CLASSES | {"other": [MEMBER]}},
            f"{MEMBER} is in both pool_heat_pump and other",
        ),
        (
            {"classes.json": {"default": [MEMBER]}},
            "class default is named like a level",
        ),
        ({"classes.json": []}, "classes.json must be an object"),
        (
            {"classes.json": {"pool_heat_pump": MEMBER}},
            "pool_heat_pump must be an array of product ids",
        ),
        (
            {f"entity_description.{MEMBER}.json": ["T01"]},
            "every entry must be an object with a key",
        ),
        (
            {
                f"entity_description.{MEMBER}.json": {
                    "inherits": "default",
                    "entries": [{"name": "T01"}],
                }
            },
            "every entry must be an object with a key",
        ),
        (
            {
                f"entity_description.{MEMBER}.json": {
                    "inherits": "default",
                    "remove": "A",
                }
            },
            '"remove" must be an array of keys',
        ),
        (
            {
                f"entity_description.{MEMBER}.json": {
                    "inherits": "default",
                    "entries": D,
                }
            },
            '"entries" must be an array',
        ),
        (
            {f"mapping.{MEMBER}.json": {"inherits": "default", "hvac_modes": None}},
            f'mapping.{MEMBER}.json: "hvac_modes" must list at least one mode',
        ),
        (
            {
                f"mapping.{MEMBER}.json": {
                    "inherits": "default",
                    "hvac_modes": {"off": None, "heat": None},
                }
            },
            f'mapping.{MEMBER}.json: "hvac_modes" must list at least one mode',
        ),
        (
            {
                f"mapping.{MEMBER}.json": DEFAULT_MAPPING
                | {"hvac_modes": {"heat": None}}
            },
            "each an object",
        ),
        (
            {f"mapping.{MEMBER}.json": {"inherits": "default", "fan_modes": None}},
            f'mapping.{MEMBER}.json: "fan_modes" must list at least one fan mode',
        ),
        (
            {
                f"mapping.{MEMBER}.json": {
                    "inherits": "default",
                    "fan_modes": {"auto": None},
                }
            },
            f'mapping.{MEMBER}.json: "fan_modes" must list at least one fan mode',
        ),
        (
            {"mapping.default.json": DEFAULT_MAPPING | {"fan_modes": {}}},
            'mapping.default.json: "fan_modes" must list at least one fan mode',
        ),
    ],
    ids=[
        "remove_missing_key",
        "key_twice_in_complete_file",
        "key_twice_in_delta",
        "unknown_delta_field",
        "catalog_delta_at_default",
        "mapping_delta_at_default",
        "delta_without_inherits",
        "delta_inheriting_a_level_without_a_file",
        "delta_skipping_the_class_file",
        "default_catalog_missing",
        "default_mapping_missing",
        "class_table_missing",
        "mapping_not_an_object",
        "catalog_neither_array_nor_object",
        "unknown_product_in_class",
        "product_in_two_classes",
        "class_named_like_a_level",
        "class_table_not_an_object",
        "class_not_an_array",
        "catalog_entry_not_an_object",
        "catalog_entry_without_key",
        "remove_not_an_array",
        "entries_not_an_array",
        "hvac_modes_removed",
        "hvac_modes_emptied",
        "hvac_mode_not_an_object",
        "fan_modes_removed",
        "fan_modes_emptied",
        "fan_modes_empty_in_complete_file",
    ],
)
async def test_invalid_profiles_fail_on_load(tmp_path, files, error):
    write_profiles(tmp_path, files)

    with pytest.raises(InvalidProfileError, match=error):
        await DeviceProfiles.load(tmp_path)


@pytest.mark.parametrize(
    "mapping, error",
    [
        (
            DEFAULT_MAPPING | {"hvac_modes": {"off": {}, "dry": {"set": "3"}}},
            '"hvac_modes" lists unknown modes: .*dry',
        ),
        (
            DEFAULT_MAPPING | {"fan_modes": {"turbo": "0"}},
            '"fan_modes" lists unknown fan modes: .*turbo',
        ),
        (
            {"inherits": "default", "hvac_modes": {"heat": {"set": None}}},
            r'"hvac_modes.heat.set" must be a string',
        ),
        (
            DEFAULT_MAPPING
            | {"hvac_modes": {"off": {"set": "9"}, "heat": {"set": "1"}}},
            r'"hvac_modes.off.set" must be null or absent',
        ),
        (
            {"inherits": "default", "hvac_modes": {"cool": {"set": "1"}}},
            "hvac_modes set values must differ between modes, repeated: .*1",
        ),
        (
            DEFAULT_MAPPING | {"fan_modes": {"auto": "0", "low": "0"}},
            "fan_modes values must differ between modes, repeated: .*0",
        ),
        (
            DEFAULT_MAPPING | {"fan_modes": {"auto": {}}},
            r'"fan_modes.auto" must be a string',
        ),
        (
            {"inherits": "default", "power": None},
            '"power" must be the protocol code of that role',
        ),
        (
            {"inherits": "default", "mode": None},
            '"mode" must be the protocol code of that role',
        ),
        (
            {"inherits": "default", "temperature": None},
            '"temperature" must be the protocol code of that role',
        ),
        (
            {"inherits": "default", "fan": None},
            '"fan" must be the protocol code of that role',
        ),
        (
            {key: value for key, value in DEFAULT_MAPPING.items() if key != "power"},
            '"power" must be the protocol code of that role',
        ),
    ],
    ids=[
        "unknown_hvac_mode",
        "unknown_fan_mode",
        "hvac_mode_without_a_wire_value",
        "off_with_a_wire_value",
        "hvac_modes_sharing_a_wire_value",
        "fan_modes_sharing_a_wire_value",
        "fan_mode_value_not_a_string",
        "power_role_removed",
        "mode_role_removed",
        "temperature_role_removed",
        "fan_role_removed",
        "power_role_missing_from_complete_file",
    ],
)
async def test_invalid_mapping_fails_on_load_naming_the_file(tmp_path, mapping, error):
    # The product's mapping would otherwise crash later, or silently drop a mode
    write_profiles(tmp_path, {f"mapping.{MEMBER}.json": mapping})

    with pytest.raises(InvalidProfileError, match=f"mapping.{MEMBER}.json: .*{error}"):
        await DeviceProfiles.load(tmp_path)


@pytest.mark.parametrize(
    "file_name",
    ["classes.json", f"mapping.{MEMBER}.json", f"entity_description.{MEMBER}.json"],
)
async def test_file_holding_null_fails_on_load(tmp_path, file_name):
    # Not read as a missing file, which would silently drop a class or a delta
    write_profiles(tmp_path, {})
    (tmp_path / file_name).write_text("null")

    with pytest.raises(InvalidProfileError, match=f"{file_name} is null"):
        await DeviceProfiles.load(tmp_path)
