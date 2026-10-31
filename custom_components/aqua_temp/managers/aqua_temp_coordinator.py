from collections.abc import Awaitable
import logging

from homeassistant.components.climate import HVACMode
from homeassistant.core import Event
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ..cloud.client import AquaTempAPI, DeviceMeta
from ..cloud.device_profiles import DeviceProfile
from ..cloud.exceptions import (
    DeviceNotRespondingError,
    DeviceOfflineError,
    LoginError,
)
from ..common.consts import (
    DATA_ITEM_CONFIG,
    DATA_ITEM_DEVICES,
    DATA_ITEM_LOGIN_DETAILS,
    DOMAIN,
    SIGNAL_AQUA_TEMP_DEVICE_NEW,
)
from .aqua_temp_config_manager import AquaTempConfigManager

_LOGGER = logging.getLogger(__name__)


class AquaTempCoordinator(DataUpdateCoordinator):
    """My custom coordinator."""

    def __init__(
        self,
        hass,
        config_manager: AquaTempConfigManager,
    ):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=config_manager.entry_title,
            update_interval=config_manager.update_interval,
            update_method=self._async_update_data,
        )

        self._api = AquaTempAPI(
            async_create_clientsession(hass=hass),
            config_manager.credentials,
            config_manager.api_profile,
            config_manager.device_profiles,
            on_new_device=self._on_new_device,
            log_session_token=config_manager.log_session_token,
            log_label=config_manager.entry_title,
            request_timeout=config_manager.request_timeout,
        )
        self._config_manager = config_manager

    @property
    def api_status(self):
        return self._api.is_connected

    @property
    def config_manager(self):
        return self._config_manager

    @property
    def devices(self):
        return self._api.devices

    @property
    def login_details(self):
        return self._api.login_details

    async def on_home_assistant_start(self, _event_data: Event):
        await self.initialize()

    async def initialize(self):
        """Initialize the integration.

        LoginError (bad credentials) is allowed to propagate so async_setup_entry
        can mark the integration as failed and surface a re-auth prompt to the
        user. Any other exception (DNS timeout, transient network error, AquaTemp
        cloud blip) is caught and logged so platform setup still proceeds — the
        coordinator's next regular update will retry the login. Without
        this, a brief network hiccup at HA boot leaves the integration
        permanently broken until a manual reload.
        """
        _LOGGER.debug("Initializing coordinator")

        entry = self.config_manager.entry
        platforms = self.config_manager.platforms

        try:
            await self._api.initialize(throw_error=True)

        except LoginError:
            raise

        except Exception as ex:
            _LOGGER.warning(
                f"Initial API connect failed; coordinator will retry on next "
                f"update. Error: {ex}"
            )

        await self.hass.config_entries.async_forward_entry_setups(entry, platforms)

        _LOGGER.info(f"Start loading {DOMAIN} integration, Entry ID: {entry.entry_id}")

        await self.async_request_refresh()

    def _on_new_device(self, device_code: str):
        async_dispatcher_send(
            self.hass,
            SIGNAL_AQUA_TEMP_DEVICE_NEW,
            self._config_manager.entry_id,
            device_code,
        )

    def get_device(self, device_code: str) -> DeviceInfo:
        device_meta = self.get_device_meta(device_code)

        device_info = DeviceInfo(
            identifiers={(DOMAIN, device_meta.device_id)},
            name=device_meta.nickname,
            model=device_meta.model,
        )

        return device_info

    def get_device_meta(self, device_code: str) -> DeviceMeta:
        device_meta = self._api.get_device_meta(device_code)

        return device_meta

    def get_device_profile(self, device_code: str) -> DeviceProfile:
        device_profile = self._api.get_device_profile(device_code)

        return device_profile

    def get_unknown_codes(self, device_code: str) -> frozenset[str]:
        unknown_codes = self._api.get_unknown_codes(device_code)

        return unknown_codes

    def get_debug_data(self) -> dict:
        config_data = self._config_manager.get_debug_data()

        data = {
            DATA_ITEM_DEVICES: self.devices,
            DATA_ITEM_CONFIG: config_data,
            DATA_ITEM_LOGIN_DETAILS: self._api.login_details,
        }

        return data

    async def _async_update_data(self):
        """Fetch parameters from API endpoint.

        This is the place to pre-process the parameters to lookup tables
        so entities can quickly look up their parameters.
        """
        try:
            await self._api.update()

            config_data = self._config_manager.get_debug_data()

            return {
                DATA_ITEM_DEVICES: self.devices,
                DATA_ITEM_LOGIN_DETAILS: self._api.login_details,
                DATA_ITEM_CONFIG: config_data,
            }

        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    def get_temperature_unit(self, device_code: str):
        return self._config_manager.get_temperature_unit(device_code)

    async def set_hvac_mode(self, device_code: str, hvac_mode: HVACMode):
        await self._control(self._api.set_hvac_mode(device_code, hvac_mode))

    async def set_temperature(self, device_code: str, temperature: float):
        await self._control(self._api.set_temperature(device_code, temperature))

    async def set_fan_mode(self, device_code: str, fan_mode):
        await self._control(self._api.set_fan_mode(device_code, fan_mode))

    async def _control(self, control: Awaitable[None]):
        """Send a control, then poll so entities show what the device did,
        whether the control succeeded or not."""
        try:
            await control

        except DeviceOfflineError as ex:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="device_offline",
            ) from ex

        except DeviceNotRespondingError as ex:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="device_not_responding",
            ) from ex

        finally:
            await self.async_request_refresh()

    async def set_temperature_unit(self, device_code: str, option: str):
        await self._config_manager.update_temperature_unit(device_code, option)

        await self.async_request_refresh()

    def get_device_data(self, device_code: str) -> dict | None:
        device_data = self._api.get_device_data(device_code)

        return device_data

    def get_device_target_temperature(self, device_code: str) -> float | None:
        target_temperature = self._api.get_device_target_temperature(device_code)

        return target_temperature

    def get_device_current_temperature(self, device_code: str) -> float | None:
        current_temperature = self._api.get_device_current_temperature(device_code)

        return current_temperature

    def get_device_minimum_temperature(self, device_code: str) -> float | None:
        minimum_temperature = self._api.get_device_minimum_temperature(device_code)

        return minimum_temperature

    def get_device_maximum_temperature(self, device_code: str) -> float | None:
        maximum_temperature = self._api.get_device_maximum_temperature(device_code)

        return maximum_temperature

    def get_device_hvac_mode(self, device_code: str) -> HVACMode:
        hvac_mode = HVACMode(self._api.get_device_hvac_mode(device_code))

        return hvac_mode

    def get_device_fan_mode(self, device_code: str) -> str:
        fan_mode = self._api.get_device_fan_mode(device_code)

        return fan_mode

    def get_device_power(self, device_code: str) -> bool:
        power = self._api.get_device_power(device_code)

        return power

    def is_device_offline(self, device_code: str) -> bool:
        is_offline = self._api.is_device_offline(device_code)

        return is_offline

    def get_hvac_modes(self, device_code: str) -> list[HVACMode]:
        modes = self.get_device_profile(device_code).hvac_modes

        result = [HVACMode(mode) for mode in modes]

        return result

    def get_fan_modes(self, device_code: str) -> list[str]:
        modes = self.get_device_profile(device_code).fan_modes

        return modes
