"""Every product's entities and their English names, against the committed reference.

A difference renames or adds entities for users. Review it, then regenerate the
reference (see CONTRIBUTING, Tests); never regenerate it just to make this pass.
"""

import json

from utils.common.entity_references import (
    RESOLVED_ENTITY_NAMES,
    resolved_entity_names,
)


def test_every_product_sets_up_the_reference_entities(device_profiles):
    reference = json.loads(RESOLVED_ENTITY_NAMES.read_text(encoding="utf-8"))

    assert resolved_entity_names(device_profiles) == reference
