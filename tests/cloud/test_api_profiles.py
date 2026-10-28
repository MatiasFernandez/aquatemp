"""API profiles: where each API type reads device data, and what it calls the codes."""

import pytest

from custom_components.aqua_temp.cloud.api_profile import ApiProfile
from custom_components.aqua_temp.cloud.api_types import APIParam, APIType

# Literal on purpose: the expected values must not come from the config under test
DATA_REQUESTS = {
    APIType.AquaTemp: ("app/device/getDataByCode", "protocalCodes"),
    APIType.HiTemp: ("app/device/getDataByCode", "protocalCodes"),
    APIType.AquaTempOld: ("app/device/getDataByCode", "protocal_codes"),
}


@pytest.mark.parametrize(
    ("profile_type", "expected"), DATA_REQUESTS.items(), ids=list(DATA_REQUESTS)
)
async def test_data_endpoint_and_code_field(profile_type, expected):
    profile = await ApiProfile.load(profile_type)

    assert (
        profile.get(APIParam.DataEndpoint),
        profile.get(APIParam.DataCodes),
    ) == expected
