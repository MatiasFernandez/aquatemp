from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .consts import DOMAIN


@callback
def async_get_ha_device(
    hass: HomeAssistant, config_entry_id: str, device_id: str
) -> dr.DeviceEntry | None:
    """The registry's device for a cloud device id, under a config entry."""
    device_registry = dr.async_get(hass)
    identifier = (DOMAIN, device_id)

    # async_get_device is deprecated since HA 2026.8.0, which added this
    # lookup; drop the fallback once hacs.json's minimum reaches 2026.8.0
    if hasattr(device_registry, "async_get_device_by_identifier"):
        return device_registry.async_get_device_by_identifier(
            identifier, config_entry_id
        )

    # Unscoped, so it can find another config entry's device
    device = device_registry.async_get_device(identifiers={identifier})
    if device is None or config_entry_id not in device.config_entries:
        return None

    return device
