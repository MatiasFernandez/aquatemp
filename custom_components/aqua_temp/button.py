import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .common.base_entity import BaseEntity, async_setup_base_entry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    await async_setup_base_entry(
        hass,
        entry,
        Platform.BUTTON,
        AquaTempRefreshDataButtonEntity,
        async_add_entities,
    )


class AquaTempRefreshDataButtonEntity(BaseEntity, ButtonEntity):
    """Button that refreshes the cloud data on demand.

    async_setup_base_entry builds every button with this class, so a second
    button would need its action on the entity description instead.
    """

    @property
    def available(self) -> bool:
        """Keep the button pressable after a failed update.

        CoordinatorEntity ties availability to the last update's success, which
        would hide the one control that can trigger a retry when it is needed.
        """
        return True

    async def async_press(self) -> None:
        """Poll the cloud now; the coordinator refreshes every device at once."""
        _LOGGER.debug(f"Manual refresh requested for device {self.device_code}")

        await self.local_coordinator.async_request_refresh()
