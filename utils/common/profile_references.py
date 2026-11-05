"""The reference pinning what every product's profile resolves to.

The tests rebuild it and compare it with the committed file, and
utils/show-profile.py --write-references writes it. A diff in it is a change
to what a product polls or how it is controlled, reviewed like any other.
"""

import json
from pathlib import Path

from custom_components.aqua_temp.cloud.consts import PRODUCT_ID_DEFAULT, PRODUCT_IDS
from custom_components.aqua_temp.cloud.device_profiles import DeviceProfiles

ROOT = Path(__file__).parents[2]

RESOLVED_PROFILES = ROOT / "tests/cloud/resolved_profiles.json"

# Made up: a product the integration doesn't know
UNKNOWN_PRODUCT_ID = "1000000000000000000"

# The default, every known product, a device that reports no product and an
# unknown product
REFERENCE_PRODUCT_IDS = [
    PRODUCT_ID_DEFAULT,
    *PRODUCT_IDS,
    None,
    UNKNOWN_PRODUCT_ID,
]


def group_by_product(field: str, values: list[tuple[str | None, object]]) -> list:
    """One group per distinct value, listing the products that resolve to it,
    in the order the products first appear."""
    groups = []

    for product_id, value in values:
        group = next((group for group in groups if group[field] == value), None)

        if group is None:
            groups.append({"products": [product_id], field: value})

        else:
            group["products"].append(product_id)

    return groups


def resolved_profiles(device_profiles: DeviceProfiles) -> dict:
    """Each distinct resolved mapping and catalog, with the products using it."""
    profiles = [
        (product_id, device_profiles.for_product(product_id))
        for product_id in REFERENCE_PRODUCT_IDS
    ]

    return {
        "mappings": group_by_product(
            "mapping",
            [(product_id, profile.mapping) for product_id, profile in profiles],
        ),
        "catalogs": group_by_product(
            "catalog",
            [(product_id, profile.parameters) for product_id, profile in profiles],
        ),
    }


def write_reference(path: Path, data: dict):
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
