"""Diagnostics download, with hass, the registries and the coordinator stubbed."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from custom_components.aqua_temp import diagnostics
from custom_components.aqua_temp.common.consts import (
    DATA_ITEM_CONFIG,
    DATA_ITEM_DEVICES,
    DATA_ITEM_LOGIN_DETAILS,
    DOMAIN,
)

DEVICE_ID = "device-id-1"
OTHER_DEVICE_ID = "device-id-2"


@pytest.fixture
def hass():
    """Hass with one coordinator holding two devices, and no entity states."""
    coordinator = MagicMock()
    coordinator.get_device_meta.side_effect = lambda code: SimpleNamespace(
        device_id={"000000000001": DEVICE_ID, "000000000002": OTHER_DEVICE_ID}[code]
    )
    coordinator.get_debug_data.return_value = {
        DATA_ITEM_DEVICES: {
            "000000000001": {"device_id": DEVICE_ID, "device_code": "000000000001"},
            "000000000002": {
                "device_id": OTHER_DEVICE_ID,
                "device_code": "000000000002",
            },
        },
        DATA_ITEM_CONFIG: {"api_type": "aqua_temp"},
        DATA_ITEM_LOGIN_DETAILS: {},
    }

    hass = MagicMock()
    hass.data = {DOMAIN: {"entry-1": coordinator}}

    return hass


@pytest.fixture(autouse=True)
def registries():
    """Device registry that knows both devices, entity registry with no entities."""
    ha_devices = {
        device_id: SimpleNamespace(
            id=f"ha-{device_id}",
            name="Heat pump",
            name_by_user=None,
            disabled=False,
            disabled_by=None,
        )
        for device_id in (DEVICE_ID, OTHER_DEVICE_ID)
    }

    def get_device(identifiers):
        for device_id, ha_device in ha_devices.items():
            if identifiers == {(DOMAIN, device_id)}:
                return ha_device
        return None

    device_registry = MagicMock()
    device_registry.async_get_device.side_effect = get_device

    with (
        patch.object(diagnostics.dr, "async_get", return_value=device_registry),
        patch.object(diagnostics.er, "async_get"),
        patch.object(diagnostics.er, "async_entries_for_device", return_value=[]),
    ):
        yield


@pytest.fixture
def entry():
    return SimpleNamespace(
        entry_id="entry-1", disabled_by=None, pref_disable_polling=False
    )


@pytest.mark.parametrize(("index", "device_id"), [(0, DEVICE_ID), (1, OTHER_DEVICE_ID)])
async def test_device_diagnostics_match_its_entry_in_the_config_entry_ones(
    hass, entry, index, device_id
):
    device = SimpleNamespace(identifiers={(DOMAIN, device_id)})

    device_data = await diagnostics.async_get_device_diagnostics(hass, entry, device)
    entry_data = await diagnostics.async_get_config_entry_diagnostics(hass, entry)

    all_devices = entry_data.pop("devices")

    assert device_data == entry_data | all_devices[index]
    assert device_data["device"]["data"]["device_id"] == device_id
