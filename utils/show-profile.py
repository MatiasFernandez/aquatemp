import argparse
import asyncio
import json

from custom_components.aqua_temp.cloud.consts import PRODUCT_IDS
from custom_components.aqua_temp.cloud.device_profiles import DeviceProfiles
from utils.common.entity_references import (
    RESOLVED_ENTITY_NAMES,
    resolved_entity_names,
)
from utils.common.profile_references import (
    RESOLVED_PROFILES,
    resolved_profiles,
    write_reference,
)


def describe(device_profiles: DeviceProfiles, product_id: str) -> dict:
    """The files a product's profile comes from, and what it resolves to."""
    profile = device_profiles.for_product(product_id)

    return {
        "product_id": product_id,
        "mapping_id": profile.mapping_id,
        "catalog_id": profile.catalog_id,
        "mapping": profile.mapping,
        "catalog": profile.parameters,
    }


async def main():
    parser = argparse.ArgumentParser(
        description="Print the profile a product resolves to."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("product_id", nargs="?", help="the product id to resolve")
    target.add_argument("--all", action="store_true", help="every known product")
    target.add_argument(
        "--write-references",
        action="store_true",
        help="rewrite the reference files the tests compare against",
    )
    args = parser.parse_args()

    device_profiles = await DeviceProfiles.load()

    if args.write_references:
        write_reference(RESOLVED_PROFILES, resolved_profiles(device_profiles))
        write_reference(RESOLVED_ENTITY_NAMES, resolved_entity_names(device_profiles))

        print(f"Wrote {RESOLVED_PROFILES} and {RESOLVED_ENTITY_NAMES}")

        return

    product_ids = PRODUCT_IDS if args.all else [args.product_id]
    profiles = [describe(device_profiles, product_id) for product_id in product_ids]

    print(json.dumps(profiles if args.all else profiles[0], indent=2))


asyncio.run(main())
