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
        tmp_path, {"entity_description.pool_heat_pump.json": {"entries": [D]}}
    )

    assert [catalog(profiles, MEMBER), catalog(profiles, OTHER_MEMBER)] == [
        (("default", "pool_heat_pump"), [A, B, C, D]),
        (("default", "pool_heat_pump"), [A, B, C, D]),
    ]


async def test_product_delta_applies_on_its_class(tmp_path):
    profiles = await load(
        tmp_path,
        {
            "entity_description.pool_heat_pump.json": {"entries": [D]},
            f"entity_description.{MEMBER}.json": {"remove": ["B"]},
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
            "entity_description.pool_heat_pump.json": {"entries": [D]},
            f"entity_description.{MEMBER}.json": [E],
        },
    )

    assert catalog(profiles, MEMBER) == ((MEMBER,), [E])


async def test_product_outside_every_class_applies_on_default(tmp_path):
    profiles = await load(
        tmp_path,
        {
            "entity_description.pool_heat_pump.json": {"entries": [D]},
            f"entity_description.{OUTSIDER}.json": {"entries": [E]},
        },
    )

    assert catalog(profiles, OUTSIDER) == (("default", OUTSIDER), [A, B, C, E])


async def test_overriding_entry_keeps_the_inherited_position(tmp_path):
    new_b = {"key": "B", "platform": None}

    profiles = await load(
        tmp_path, {f"entity_description.{MEMBER}.json": {"entries": [new_b]}}
    )

    assert catalog(profiles, MEMBER) == (("default", MEMBER), [A, new_b, C])


async def test_added_entries_follow_the_inherited_ones_in_file_order(tmp_path):
    profiles = await load(
        tmp_path, {f"entity_description.{MEMBER}.json": {"entries": [E, D]}}
    )

    assert catalog(profiles, MEMBER) == (("default", MEMBER), [A, B, C, E, D])


async def test_each_entry_records_the_level_defining_it(tmp_path):
    profiles = await load(
        tmp_path,
        {
            "entity_description.pool_heat_pump.json": {"entries": [D]},
            f"entity_description.{MEMBER}.json": {"entries": [{**B, "name": "B"}]},
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
                "delta": True,
                "hvac_modes": {"heat": {"target": "R04"}},
            },
            # null: this product has no code for the role
            f"mapping.{MEMBER}.json": {"delta": True, "power": None},
        },
    )
    profile = profiles.for_product(MEMBER)

    assert (profile.mapping_chain, profile.mapping) == (
        ("default", "pool_heat_pump", MEMBER),
        {
            "mode": "Mode",
            "power": None,
            "hvac_modes": {
                "off": {"set": None, "target": None},
                "heat": {"set": "1", "target": "R04"},
            },
            "fan_modes": {"auto": "0"},
        },
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
            {f"entity_description.{MEMBER}.json": {"remove": ["Z"]}},
            "removes Z, which the level below doesn't have",
        ),
        (
            {f"entity_description.{MEMBER}.json": [A, A]},
            "A more than once",
        ),
        (
            {f"entity_description.{MEMBER}.json": {"remove": ["A"], "entries": [A]}},
            "A more than once",
        ),
        (
            {f"entity_description.{MEMBER}.json": {"entries": [D], "add": [E]}},
            "unknown fields add",
        ),
        (
            {"entity_description.default.json": {"entries": [A]}},
            "must be complete, not a delta",
        ),
        (
            {"mapping.default.json": DEFAULT_MAPPING | {"delta": True}},
            "must be complete, not a delta",
        ),
        (
            {f"mapping.{MEMBER}.json": {"delta": False, "power": "P"}},
            '"delta" must be true',
        ),
        ({"entity_description.default.json": None}, "is missing"),
        ({"mapping.default.json": None}, "is missing"),
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
    ],
    ids=[
        "remove_missing_key",
        "key_twice_in_complete_file",
        "key_twice_in_delta",
        "unknown_delta_field",
        "catalog_delta_at_default",
        "mapping_delta_at_default",
        "mapping_delta_not_true",
        "default_catalog_missing",
        "default_mapping_missing",
        "mapping_not_an_object",
        "catalog_neither_array_nor_object",
        "unknown_product_in_class",
        "product_in_two_classes",
        "class_named_like_a_level",
    ],
)
async def test_invalid_profiles_fail_on_load(tmp_path, files, error):
    write_profiles(tmp_path, files)

    with pytest.raises(InvalidProfileError, match=error):
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
