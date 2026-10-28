"""Entity descriptions: the platforms and entities each product's catalog sets up."""

import pytest

from custom_components.aqua_temp.common.entity_descriptions import (
    build_entity_descriptions,
)

HITEMP = "1245226668902080512"
AQUA_TEMP = "1442284873216843776"

PLATFORMS = {"binary_sensor", "climate", "select", "sensor"}

PRODUCTS = pytest.mark.parametrize(
    "product_id", ["default", HITEMP, AQUA_TEMP], ids=["default", "hitemp", "aqua_temp"]
)


@PRODUCTS
def test_catalog_sets_up_platforms(device_profiles, product_id):
    profile = device_profiles.for_product(product_id)

    platforms = {
        str(description.platform)
        for description in build_entity_descriptions(profile)
        if description.platform is not None
    }

    assert platforms == PLATFORMS


@PRODUCTS
def test_catalog_parameters_become_descriptions(device_profiles, product_id):
    # The built-in and mapping-derived descriptions cover every platform on
    # their own, so the catalog's contribution is checked by key
    profile = device_profiles.for_product(product_id)

    catalog = {
        (item["platform"], item["key"])
        for item in profile.parameters
        if item.get("platform") is not None
    }
    descriptions = {
        (str(description.platform), description.key)
        for description in build_entity_descriptions(profile)
        if description.platform is not None
    }

    assert catalog
    assert catalog <= descriptions
