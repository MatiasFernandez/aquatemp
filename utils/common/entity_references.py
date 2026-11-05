"""The reference pinning the entities every product's profile sets up, by name.

Translation keys are left out on purpose: they may move between profile files
as long as the English name each entity ends up with stays the same.
"""

import json

from custom_components.aqua_temp.cloud.device_profiles import (
    DeviceProfile,
    DeviceProfiles,
)
from custom_components.aqua_temp.common.entity_descriptions import (
    AquaTempEntityDescription,
    build_entity_descriptions,
)
from utils.common.profile_references import (
    REFERENCE_PRODUCT_IDS,
    ROOT,
    group_by_product,
)

RESOLVED_ENTITY_NAMES = ROOT / "tests/integration/resolved_entity_names.json"

TRANSLATIONS = ROOT / "custom_components/aqua_temp/translations/en.json"


def resolved_entity_names(device_profiles: DeviceProfiles) -> dict:
    """Each distinct set of entities, with the products setting it up."""
    translations = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))["entity"]

    return {
        "entities": group_by_product(
            "entities",
            [
                (
                    product_id,
                    _entity_names(
                        device_profiles.for_product(product_id), translations
                    ),
                )
                for product_id in REFERENCE_PRODUCT_IDS
            ],
        )
    }


def _entity_names(profile: DeviceProfile, translations: dict) -> list[dict]:
    """Platform, key and English name of each entity, sorted: the order
    entities are created in isn't visible to users."""
    entities = [
        {
            "platform": str(description.platform),
            "key": description.key,
            "name": _english_name(description, translations),
        }
        for description in build_entity_descriptions(profile)
        if description.platform is not None
    ]

    return sorted(entities, key=lambda entity: (entity["platform"], entity["key"]))


def _english_name(
    description: AquaTempEntityDescription, translations: dict
) -> str | None:
    """The name Home Assistant shows: the translation's, else the description's."""
    translation = translations.get(str(description.platform), {}).get(
        description.translation_key, {}
    )

    return translation.get("name", description.name)
