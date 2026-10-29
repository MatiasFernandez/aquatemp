"""Client for the Aqua Temp cloud API."""

from asyncio import sleep
from collections.abc import Callable
from copy import copy
from dataclasses import dataclass, field
import hashlib
import json
import logging
import sys
import unicodedata

from aiohttp import ClientResponseError, ClientSession

from .api_profile import ApiProfile
from .api_types import DEVICE_LISTS, DEVICE_REQUEST_PARAMETERS, APIParam
from .consts import (
    API_MAX_ATTEMPTS,
    CONFIG_HVAC_MAXIMUM,
    CONFIG_HVAC_MINIMUM,
    CONFIG_HVAC_SET,
    CONFIG_HVAC_TARGET,
    CONFIG_SET_CURRENT_TEMPERATURE,
    CONFIG_SET_FAN,
    CONFIG_SET_MODE,
    CONFIG_SET_POWER,
    CONFIG_SET_TEMPERATURE,
    DEVICE_CONTROL_PARAM,
    DEVICE_CONTROL_VALUE,
    HEADERS,
    HTTP_HEADER_X_TOKEN,
    POWER_MODE_OFF,
    POWER_MODE_ON,
    PRODUCT_ID_DEFAULT,
)
from .device_profiles import DeviceProfile, DeviceProfiles
from .endpoints import Endpoints
from .exceptions import InvalidTokenError, LoginError, OperationFailedException
from .modes import FanMode, Mode

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Credentials:
    """The account's login; the password goes on the wire MD5-hashed."""

    username: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class DeviceMeta:
    """What the device lists say about a device, besides its data."""

    nickname: str | None
    device_id: str | None
    model: str | None
    product_id: str | None


class AquaTempAPI:
    """One account's session with the cloud: login, discovery, polling, writes.

    Call initialize once, then update on each poll; read device state with the
    get_device_* methods between polls. The cloud allows one login per account
    at a time, so another client logging in with it invalidates this token.
    """

    _devices: dict
    _device_profiles_by_code: dict[str, DeviceProfile]
    _unknown_codes: dict[str, frozenset[str]]
    _login_details: dict | None

    _session: ClientSession
    _credentials: Credentials
    _api_profile: ApiProfile
    _device_profiles: DeviceProfiles
    _token: str | None

    def __init__(
        self,
        session: ClientSession,
        credentials: Credentials,
        api_profile: ApiProfile,
        device_profiles: DeviceProfiles,
        on_new_device: Callable[[str], None] | None = None,
        log_session_token: bool = False,
        log_label: str = "Aqua Temp",
    ):
        """Initialize the client; the caller owns the session and closes it.

        on_new_device is called with a device's code after its first fetch.
        """

        self._devices = {}
        self._device_profiles_by_code = {}
        self._unknown_codes = {}
        self._login_details = None

        self._session = session
        self._token = None

        self._headers = dict(HEADERS)
        self._credentials = credentials
        self._api_profile = api_profile
        self._device_profiles = device_profiles
        self._on_new_device = on_new_device
        self._log_session_token = log_session_token
        self._log_label = log_label

        self._dispatched_devices = []
        self._device_list_request_data = {}

    @property
    def is_connected(self):
        result = self._token is not None

        return result

    @property
    def login_details(self):
        result = self._login_details

        return result

    @property
    def devices(self):
        result = self._devices

        return result

    async def initialize(self, throw_error: bool = False):
        """Log in and discover devices.

        With throw_error, failures raise (LoginError for bad credentials);
        without it they are logged and the next update tries again.
        """
        _LOGGER.debug(f"Initializing API, Throw Error: {throw_error}")

        try:
            await self._connect()

        except LoginError:
            if throw_error:
                raise
            _LOGGER.error("Failed to login, Please update credentials and try again")

        except Exception:
            if throw_error:
                raise
            _LOGGER.warning("Failed to initialize session", exc_info=True)

    async def _connect(self):
        if self._token is None:
            _LOGGER.debug("No token available, Login AquaTemp API and fetching devices")
            await self._login()

            await self._load_devices()

    async def update(self):
        """Fetch every device's data and faults, logging in again if needed.

        Devices are bound to their profile, and announced through
        on_new_device, on their first fetch. Raises the last error after
        API_MAX_ATTEMPTS failed attempts.
        """
        await self._internal_update()

    async def _internal_update(self):
        """Fetch new state with up to API_MAX_ATTEMPTS retries.

        Always clears the token between failed attempts so the next try goes
        through a full re-login, re-loads user info, and re-loads devices.
        Without that, a partial failure (e.g. network error after _login set
        the token but before _load_user_info populated _device_list_request_data)
        would leave _devices empty and self._token set; subsequent ticks would
        iterate an empty for-loop, raise no error, and silently report success
        forever — a "stuck token" state.

        AquaTemp's cloud only allows one active session per credential, so if
        another client (phone app, second HA) is also logging in with the same
        account we'll fight an unwinnable war. The README workaround is to use
        a second account and share the device to it.
        """
        last_error: Exception | None = None
        last_line: int | None = None

        for attempt in range(1, API_MAX_ATTEMPTS + 1):
            try:
                await self._connect()

                for device_code in self._devices:
                    await self._update_device(device_code)

                return

            except Exception as ex:
                _, _, tb = sys.exc_info()
                last_line = tb.tb_lineno if tb is not None else None
                last_error = ex
                self.set_token()

            if attempt < API_MAX_ATTEMPTS:
                await sleep(1)

        _LOGGER.error(
            f"Failed to update after {API_MAX_ATTEMPTS} attempts, "
            f"Error: {last_error}, Line: {last_line}"
        )
        raise last_error

    async def _update_device(self, device_code: str):
        _LOGGER.debug(f"Starting to update device: {device_code}")

        try:
            new_device = device_code not in self._dispatched_devices

            if new_device:
                device = self.get_device_data(device_code)
                product_id = self._get_device_product_id(device)

                self._set_device_profile(device_code, product_id)

            param_keep_alive = self._api_profile.get(APIParam.KeepAlive)

            if param_keep_alive:
                await self._send_passthrough_instruction(device_code)

            await self._fetch_data(device_code)

            await self._fetch_errors(device_code)

            if new_device:
                self._dispatched_devices.append(device_code)

                if self._on_new_device is not None:
                    self._on_new_device(device_code)

        except ClientResponseError as cre:
            if cre.status == 401:
                raise InvalidTokenError(f"Update device: {device_code}")

            else:
                raise cre

    def set_token(self, token: str | None = None):
        self._device_list_request_data = {}
        self._token = token

        if token is None:
            if HTTP_HEADER_X_TOKEN in self._headers:
                self._headers.pop(HTTP_HEADER_X_TOKEN)
        else:
            self._headers[HTTP_HEADER_X_TOKEN] = token

    async def set_hvac_mode(self, device_code: str, hvac_mode: Mode):
        """Switch the device to a mode, powering it on first if needed.

        Mode.OFF powers it off and keeps the mode it was in.
        """
        if hvac_mode == Mode.OFF:
            await self._set_power_mode(device_code, POWER_MODE_OFF)

        else:
            is_on = self.get_device_power(device_code)

            if not is_on:
                await self._set_power_mode(device_code, POWER_MODE_ON)

                await self._update_device(device_code)

            await self._set_hvac_mode(device_code, hvac_mode)

    async def set_temperature(self, device_code: str, temperature: float):
        """Set the target temperature of the device's current mode."""
        hvac_mode = self.get_device_hvac_mode(device_code)
        target_temperature_pc = self._get_target_temperature_protocol_code(
            device_code, hvac_mode
        )

        set_temp_pc_key = self._get_device_profile(device_code).get_pc_key(
            CONFIG_SET_TEMPERATURE
        )

        param_device_code = self._api_profile.get(APIParam.DeviceCode)
        param_protocol_code = self._api_profile.get(APIParam.ProtocolCode)

        request_data = {
            DEVICE_CONTROL_PARAM: [
                {
                    param_device_code: device_code,
                    param_protocol_code: target_temperature_pc,
                    DEVICE_CONTROL_VALUE: temperature,
                },
                {
                    param_device_code: device_code,
                    param_protocol_code: set_temp_pc_key,
                    DEVICE_CONTROL_VALUE: temperature,
                },
            ]
        }

        await self._perform_action(request_data, set_temp_pc_key)

    async def _set_power_mode(self, device_code: str, value):
        """Set new target power mode."""
        power_pc_key = self._get_device_profile(device_code).get_pc_key(
            CONFIG_SET_POWER
        )

        param_device_code = self._api_profile.get(APIParam.DeviceCode)
        param_protocol_code = self._api_profile.get(APIParam.ProtocolCode)

        request_data = {
            DEVICE_CONTROL_PARAM: [
                {
                    param_device_code: device_code,
                    param_protocol_code: power_pc_key.lower(),
                    DEVICE_CONTROL_VALUE: value,
                }
            ]
        }

        await self._perform_action(request_data, power_pc_key)

    async def _set_hvac_mode(self, device_code: str, hvac_mode: Mode):
        """Set new target hvac mode."""
        if hvac_mode == Mode.OFF:
            return

        mode_pc_key = self._get_device_profile(device_code).get_pc_key(CONFIG_SET_MODE)
        set_temp_pc_key = self._get_device_profile(device_code).get_pc_key(
            CONFIG_SET_TEMPERATURE
        )
        action_pc_key = self._get_device_profile(device_code).get_hvac_mode_pc_key(
            hvac_mode, CONFIG_HVAC_SET
        )

        target_temperature = self.get_device_target_temperature(device_code)

        _LOGGER.info(
            f"Set HVAC Mode: {hvac_mode}, PC Mode: {action_pc_key}, Target temperature: {target_temperature}"
        )

        control_params = []

        param_device_code = self._api_profile.get(APIParam.DeviceCode)
        param_protocol_code = self._api_profile.get(APIParam.ProtocolCode)

        set_target_temp = {
            param_device_code: device_code,
            param_protocol_code: set_temp_pc_key,
            DEVICE_CONTROL_VALUE: target_temperature,
        }

        control_params.append(set_target_temp)

        if mode_pc_key != set_temp_pc_key:
            set_mode = {
                param_device_code: device_code,
                param_protocol_code: mode_pc_key,
                DEVICE_CONTROL_VALUE: action_pc_key,
            }

            control_params.append(set_mode)

        request_data = {DEVICE_CONTROL_PARAM: control_params}

        await self._perform_action(request_data, mode_pc_key)

    async def set_fan_mode(self, device_code: str, fan_mode: FanMode):
        """Set the fan mode to its wire value in the device's profile."""
        device_profile = self._get_device_profile(device_code)
        fan_pc_key = device_profile.get_pc_key(CONFIG_SET_FAN)

        param_device_code = self._api_profile.get(APIParam.DeviceCode)
        param_protocol_code = self._api_profile.get(APIParam.ProtocolCode)

        value = device_profile.fan_modes.get(fan_mode)

        request_data = {
            DEVICE_CONTROL_PARAM: [
                {
                    param_device_code: device_code,
                    param_protocol_code: fan_pc_key,
                    DEVICE_CONTROL_VALUE: value,
                }
            ]
        }

        await self._perform_action(request_data, fan_pc_key)

    async def _perform_action(
        self, request_data: dict, operation: str, attempt: int = 1
    ):
        error = None

        try:
            param_error_msg = self._api_profile.get(APIParam.ErrorMessage)
            param_error_code = self._api_profile.get(APIParam.ErrorCode)

            operation_response = await self._post_request(
                Endpoints.DeviceControl, request_data
            )

            error_msg = operation_response.get(param_error_msg)

            if error_msg != "Success":
                error_code = operation_response.get(param_error_code)
                if error_code == "-100":
                    self.set_token()

                    error = InvalidTokenError(
                        f"Perform operation {operation}, "
                        f"Data: {json.dumps(request_data)}, "
                        f"Attempt: {attempt}"
                    )

                else:
                    error = OperationFailedException(
                        operation, request_data, f"{error_code}: {error_msg}"
                    )

        except Exception as ex:
            error = ex

        if error is not None:
            if attempt < API_MAX_ATTEMPTS:
                await sleep(1)

                await self._connect()

                await self._perform_action(request_data, operation, attempt + 1)

            else:
                raise error

    async def _fetch_data(self, device_code: str):
        unknown_codes = self.get_unknown_codes(device_code)
        codes = [
            code
            for code in self._get_device_profile(device_code).poll_codes
            if code not in unknown_codes
        ]

        param_device_code = self._api_profile.get(APIParam.DeviceCode)
        param_protocal_codes = self._api_profile.get(APIParam.ProtocalCodes)
        param_object_result = self._api_profile.get(APIParam.ObjectResult)
        param_error_msg = self._api_profile.get(APIParam.ErrorMessage)
        param_error_code = self._api_profile.get(APIParam.ErrorCode)

        data = {
            param_device_code: device_code,
            param_protocal_codes: codes,
        }

        data_response = await self._post_request(Endpoints.DeviceData, data)
        error_msg = data_response.get(param_error_msg)

        object_result_items = data_response.get(param_object_result, [])

        if error_msg == "Success":
            self._record_unknown_codes(device_code, object_result_items)

            for object_result_item in object_result_items:
                code = object_result_item.get("code")
                value = object_result_item.get("value")

                if value is not None and isinstance(value, str) and value == "":
                    value = None

                self._devices[device_code][code] = value

        else:
            error_code = data_response.get(param_error_code)
            if error_code == "-100":
                raise InvalidTokenError(f"Fetch data for device {device_code}")

            else:
                _LOGGER.error(f"Failed to fetch parameters, Error: {error_msg}")

    def _record_unknown_codes(self, device_code: str, object_result_items: list):
        """Note the codes the device doesn't know, once, from its first answer.

        The cloud echoes such a code with an empty value and an empty
        dataType; only the empty dataType tells it apart from a known code
        without a value. A missing or null dataType is not that signal.
        """
        if device_code in self._unknown_codes or not object_result_items:
            return

        coded_items = [
            item for item in object_result_items if item.get("code") is not None
        ]
        unknown_codes = frozenset(
            item["code"] for item in coded_items if item.get("dataType") == ""
        )

        # Every code unknown looks like a backend hiccup rather than codes
        # this device lacks
        if len(unknown_codes) == len({item["code"] for item in coded_items}):
            unknown_codes = frozenset()

        self._unknown_codes[device_code] = unknown_codes

    async def _send_passthrough_instruction(self, device_code: str):
        param_device_code = self._api_profile.get(APIParam.DeviceCode)

        data = {param_device_code: device_code, "query_instruction": "630300040001CD89"}

        data_response = await self._post_request(
            Endpoints.DevicePassthroughInstruction, data
        )
        error_msg = data_response.get("error_msg")

        if error_msg != "Success":
            _LOGGER.error(f"Failed to send passthrough instruction, Error: {error_msg}")

    async def _fetch_errors(self, device_code: str):
        param_device_code = self._api_profile.get(APIParam.DeviceCode)
        param_object_result = self._api_profile.get(APIParam.ObjectResult)
        param_is_fault = self._api_profile.get(APIParam.IsFault)

        data = {param_device_code: device_code}

        device_status_response = await self._post_request(Endpoints.DeviceStatus, data)
        object_result = device_status_response.get(param_object_result, {})

        is_fault = object_result.get(param_is_fault, str(False))
        fault_description = None

        if bool(is_fault):
            device_fault_response = await self._post_request(
                Endpoints.DeviceFault, data
            )
            object_results = device_fault_response.get(param_object_result, [])

            if len(object_results) > 0:
                object_result = object_results[0]
                fault_description = object_result.get("description")

        device_data = self._devices[device_code]

        if fault_description is None:
            if "fault" in device_data:
                device_data.pop("fault")
        else:
            device_data["fault"] = fault_description

    async def _login(self):
        param_username = self._api_profile.get(APIParam.Username)
        param_object_result = self._api_profile.get(APIParam.ObjectResult)

        credentials = self._credentials

        # MD5 is a weak hash for passwords, but the cloud API's login expects
        # exactly this; we can't choose another without breaking login
        password_hashed = hashlib.md5(credentials.password.encode("utf-8")).hexdigest()

        data = {param_username: credentials.username, "password": password_hashed}

        login_response = await self._post_request(Endpoints.Login, data)
        object_result = login_response.get(param_object_result) or {}

        self._login_details = object_result

        token = object_result.get(HTTP_HEADER_X_TOKEN)

        if token is None:
            _LOGGER.warning(
                "Login failed (no x-token in response). "
                "error_code=%s, error_msg=%s, error_msg_code=%s",
                login_response.get("error_code"),
                login_response.get("error_msg"),
                login_response.get("error_msg_code"),
            )
            # Shape-only diagnostics (no credential content), at DEBUG.
            # If chars != utf8_bytes the password has multibyte unicode; if
            # nfc_utf8_bytes differs again the input was non-NFC-normalized;
            # leading/trailing_ws and all_printable catch hidden whitespace
            # and zero-width chars from copy-paste.
            pw = credentials.password
            un = credentials.username
            _LOGGER.debug(
                "Login failure diagnostics (shape only): "
                "password chars=%d, utf8_bytes=%d, nfc_utf8_bytes=%d, "
                "leading_ws=%s, trailing_ws=%s, all_printable=%s, all_ascii=%s; "
                "username chars=%d, utf8_bytes=%d, has_plus=%s, has_uppercase=%s",
                len(pw),
                len(pw.encode("utf-8")),
                len(unicodedata.normalize("NFC", pw).encode("utf-8")),
                pw != pw.lstrip(),
                pw != pw.rstrip(),
                all(c.isprintable() for c in pw),
                pw.isascii(),
                len(un),
                len(un.encode("utf-8")),
                "+" in un,
                un != un.lower(),
            )
            self.set_token()
            raise LoginError()

        self.set_token(token)

        if self._log_session_token:
            # Opt-in, for running curl / utils scripts on HA's session instead of
            # logging in again (the API allows one login at a time).
            _LOGGER.warning(
                "[session-token] %s: CREDENTIAL, do not share. "
                "Valid until the next login. export AQUATEMP_X_TOKEN='%s'",
                self._log_label,
                token,
            )

        await self._load_user_info()

    async def _load_user_info(self):
        param_object_result = self._api_profile.get(APIParam.ObjectResult)
        param_user_id = self._api_profile.get(APIParam.UserId)

        user_info_response = await self._post_request(Endpoints.UserInfo)

        object_result = user_info_response.get(param_object_result, {})
        user_id = object_result.get(param_user_id)

        for device_list_url in DEVICE_LISTS:
            request_data = {}
            request_data_keys = DEVICE_LISTS[device_list_url]

            for request_data_key in request_data_keys:
                if request_data_key == APIParam.ToUser:
                    value = user_id

                else:
                    value = DEVICE_REQUEST_PARAMETERS.get(request_data_key)

                request_data_param = self._api_profile.get(request_data_key)

                request_data[request_data_param] = value

            self._device_list_request_data[device_list_url] = request_data

    async def _load_devices(self):
        param_object_result = self._api_profile.get(APIParam.ObjectResult)

        for device_list_url in DEVICE_LISTS:
            request_data = self._device_list_request_data[device_list_url]

            device_code_response = await self._post_request(
                device_list_url, request_data
            )

            devices = device_code_response.get(param_object_result, [])

            for device in devices:
                device_code = self._get_device_id(device)

                _LOGGER.debug(
                    f"Discover device: {device_code} by {device_list_url}, Data: {device}"
                )

                self._devices[device_code] = device

                _LOGGER.info(f"Discovering device {device_code}")

        if not self._devices:
            await self._load_devices_unfiltered(param_object_result)

    async def _load_devices_unfiltered(self, param_object_result):
        param_product_ids = self._api_profile.get(APIParam.ProductIds)

        _LOGGER.warning(
            "No devices matched the PRODUCT_IDS allow-list — retrying device discovery without productIds filter"
        )

        for device_list_url in DEVICE_LISTS:
            request_data = {
                k: v
                for k, v in self._device_list_request_data[device_list_url].items()
                if k != param_product_ids
            }

            try:
                device_code_response = await self._post_request(
                    device_list_url, request_data
                )
            except Exception as ex:
                _LOGGER.debug(f"Unfiltered discovery to {device_list_url} failed: {ex}")
                continue

            devices = device_code_response.get(param_object_result, [])

            for device in devices:
                device_code = self._get_device_id(device)
                product_id = self._get_device_product_id(device)

                _LOGGER.warning(
                    f"Unfiltered discovery: device {device_code} productId={product_id} (not in PRODUCT_IDS allow-list)"
                )
                _LOGGER.debug(
                    f"Discover device: {device_code} by {device_list_url}, Data: {device}"
                )

                self._devices[device_code] = device

    async def _post_request(
        self, endpoint: Endpoints, data: dict | list | None = None
    ) -> dict | None:
        param_url = self._api_profile.get(APIParam.URL)
        param_suffix = self._api_profile.get(APIParam.Suffix)

        url = f"{param_url}/{endpoint}{param_suffix}"

        if endpoint == Endpoints.DeviceControl:
            _LOGGER.info(f"Sending request to control device, Data: {data}")

        async with self._session.post(
            url, headers=self._headers, json=data, ssl=False
        ) as response:
            response.raise_for_status()

            result = await response.json()
            _LOGGER.debug(f"Request to {url}, Body: {data}, Result: {result}")

        return result

    def get_device_data(self, device_code: str) -> dict | None:
        device_data = copy(self._devices.get(device_code))

        return device_data

    def get_device_target_temperature(self, device_code: str) -> float | None:
        hvac_mode = self.get_device_hvac_mode(device_code)
        target_temperature_pc = self._get_target_temperature_protocol_code(
            device_code, hvac_mode
        )

        device_data = self.get_device_data(device_code)
        target_temperature = device_data.get(target_temperature_pc)

        if target_temperature == "":
            target_temperature = None

        if target_temperature is not None:
            target_temperature = float(str(target_temperature))

        return target_temperature

    def get_device_current_temperature(self, device_code: str) -> float | None:
        device_data = self.get_device_data(device_code)
        pc_key = self._get_device_profile(device_code).get_pc_key(
            CONFIG_SET_CURRENT_TEMPERATURE
        )
        current_temperature = device_data.get(pc_key)

        if current_temperature == "":
            current_temperature = None

        if current_temperature is not None:
            current_temperature = float(str(current_temperature))

        return current_temperature

    def get_device_minimum_temperature(self, device_code: str) -> float | None:
        device_data = self.get_device_data(device_code)

        hvac_mode = self.get_device_hvac_mode(device_code)
        key = self._get_device_profile(device_code).get_hvac_mode_pc_key(
            hvac_mode, CONFIG_HVAC_MINIMUM
        )

        temperature = device_data.get(key)

        if temperature == "":
            temperature = None

        if temperature is not None:
            temperature = float(str(temperature))

        return temperature

    def get_device_maximum_temperature(self, device_code: str) -> float | None:
        device_data = self.get_device_data(device_code)

        hvac_mode = self.get_device_hvac_mode(device_code)

        key = self._get_device_profile(device_code).get_hvac_mode_pc_key(
            hvac_mode, CONFIG_HVAC_MAXIMUM
        )

        temperature = device_data.get(key)

        if temperature == "":
            temperature = None

        if temperature is not None:
            temperature = float(str(temperature))

        return temperature

    def get_device_hvac_mode(self, device_code: str) -> Mode:
        """The mode the device reports; raises ValueError for an unmapped value."""
        device_data = self.get_device_data(device_code)
        device_profile = self._get_device_profile(device_code)
        pc_key = device_profile.get_pc_key(CONFIG_SET_MODE)
        device_mode = device_data.get(pc_key)

        hvac_mode = device_profile.hvac_modes_reverse.get(device_mode)
        result = Mode(hvac_mode)

        return result

    def get_device_fan_mode(self, device_code: str) -> FanMode | None:
        device_data = self.get_device_data(device_code)
        device_profile = self._get_device_profile(device_code)
        pc_key = device_profile.get_pc_key(CONFIG_SET_FAN)
        manual_mute = device_data.get(pc_key)

        fan_mode = device_profile.fan_modes_reverse.get(manual_mute)

        return fan_mode

    def get_device_power(self, device_code: str) -> bool:
        device_data = self.get_device_data(device_code)
        pc_key = self._get_device_profile(device_code).get_pc_key(CONFIG_SET_POWER)

        power = device_data.get(pc_key)
        is_on = power == POWER_MODE_ON

        return is_on

    def get_device_meta(self, device_code: str) -> DeviceMeta:
        """Name, ids and model from the device lists, read with this API type's
        field names."""
        device_data = self.get_device_data(device_code)

        device_meta = DeviceMeta(
            nickname=device_data.get(self._api_profile.get(APIParam.Nickname)),
            device_id=device_data.get(self._api_profile.get(APIParam.DeviceId)),
            model=device_data.get(self._api_profile.get(APIParam.CustomModel)),
            product_id=self._get_device_product_id(device_data),
        )

        return device_meta

    def get_device_profile(self, device_code: str) -> DeviceProfile:
        """The profile the device was bound to on its first fetch."""
        device_profile = self._get_device_profile(device_code)

        return device_profile

    def get_unknown_codes(self, device_code: str) -> frozenset[str]:
        """Codes the device doesn't know, decided on its first answered read.

        Empty until then, and when every code came back unknown.
        """
        unknown_codes = self._unknown_codes.get(device_code, frozenset())

        return unknown_codes

    def _set_device_profile(self, device_code: str, product_id: str):
        device_profile = self._device_profiles.for_product(product_id)

        self._device_profiles_by_code[device_code] = device_profile

        _LOGGER.info(
            f"Device {device_code} mapped to "
            f"Product ID {product_id}, "
            f"Mapping Key: {device_profile.mapping_id}, "
            f"Entity Description Key: {device_profile.catalog_id}"
        )

    def _get_device_profile(self, device_code: str) -> DeviceProfile:
        device_profile = self._device_profiles_by_code.get(device_code)

        if device_profile is None:
            device_profile = self._device_profiles.for_product(PRODUCT_ID_DEFAULT)

        return device_profile

    def _get_target_temperature_protocol_code(self, device_code: str, hvac_mode: Mode):
        target_temperature_pc = self._get_device_profile(
            device_code
        ).get_hvac_mode_pc_key(hvac_mode, CONFIG_HVAC_TARGET)

        _LOGGER.debug(f"Target temp PC {target_temperature_pc}, HA Mode: {hvac_mode}")

        return target_temperature_pc

    def _get_device_product_id(self, device_data: dict):
        param = self._api_profile.get(APIParam.ProductId)
        product_id = device_data.get(param)

        return product_id

    def _get_device_id(self, device_data: dict):
        param = self._api_profile.get(APIParam.DeviceCode)
        device_code = device_data.get(param)

        return device_code
