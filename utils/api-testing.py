import asyncio
import json
import logging
import os
import sys

from aiohttp import ClientSession

from custom_components.aqua_temp.cloud.api_profile import ApiProfile
from custom_components.aqua_temp.cloud.api_types import APIType
from custom_components.aqua_temp.cloud.client import AquaTempAPI, Credentials
from custom_components.aqua_temp.cloud.device_profiles import DeviceProfiles

DEBUG = str(os.environ.get("DEBUG", False)).lower() == str(True).lower()
USERNAME = os.environ.get("USERNAME", False)
PASSWORD = os.environ.get("PASSWORD", False)

log_level = logging.DEBUG if DEBUG else logging.INFO

root = logging.getLogger()
root.setLevel(log_level)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(log_level)
formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
stream_handler.setFormatter(formatter)
root.addHandler(stream_handler)

_LOGGER = logging.getLogger(__name__)


class Test:
    @staticmethod
    async def _create_api(session: ClientSession) -> AquaTempAPI:
        api_profile = await ApiProfile.load(str(APIType.AquaTemp))
        device_profiles = await DeviceProfiles.load()

        return AquaTempAPI(
            session,
            Credentials(username=USERNAME, password=PASSWORD),
            api_profile,
            device_profiles,
        )

    async def parameters_list(self):
        async with ClientSession() as session:
            api = await self._create_api(session)

            await api.initialize()

    async def list_data(self):
        async with ClientSession() as session:
            api = await self._create_api(session)

            await api.initialize()

            await api.update()

            for device_code in api.devices:
                device_data = api.get_device_data(device_code)

                _LOGGER.info(f"{device_code}: {json.dumps(device_data, indent=4)}")

    async def api_test(self):
        async with ClientSession() as session:
            api = await self._create_api(session)

            await api.initialize()

            for i in range(1, 10):
                await api.update()

                _LOGGER.info(api.devices)

                await asyncio.sleep(30)


instance = Test()

# asyncio.run cancels the task on Ctrl+C, so the session still closes
try:
    asyncio.run(instance.list_data())

except KeyboardInterrupt:
    _LOGGER.info("Aborted")

except Exception as rex:
    _LOGGER.error(f"Error: {rex}")
