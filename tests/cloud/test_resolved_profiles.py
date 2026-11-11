"""Every product's resolved mapping and catalog, against the committed reference.

A difference changes what a product polls or how it is controlled. Review it,
then regenerate the reference (see CONTRIBUTING, Tests); never regenerate it
just to make this pass.
"""

import json

from utils.common.profile_references import RESOLVED_PROFILES, resolved_profiles


def test_every_product_resolves_to_the_reference_profile(device_profiles):
    reference = json.loads(RESOLVED_PROFILES.read_text(encoding="utf-8"))

    assert resolved_profiles(device_profiles) == reference
