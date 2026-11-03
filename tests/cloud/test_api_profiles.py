"""API profiles: where each API type reads device data, what it calls the codes,
and whether it reads through the semantic codes."""

import pytest

from custom_components.aqua_temp.cloud.api_profile import ApiProfile
from custom_components.aqua_temp.cloud.api_types import APIParam, APIType

# Literal on purpose: the expected values must not come from the config under test
DATA_REQUESTS = {
    APIType.AquaTemp: ("app/device/v5/getDataByCode", "codes"),
    APIType.HiTemp: ("app/device/getDataByCode", "protocalCodes"),
    APIType.AquaTempOld: ("app/device/getDataByCode", "protocal_codes"),
}

SEMANTIC_CODES = {
    APIType.AquaTemp: False,
    APIType.HiTemp: False,
    APIType.AquaTempOld: False,
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


def test_unknown_data_endpoint_fails_on_load():
    fields = {"data_endpoint": "app/device/v6/getDataByCode"}

    with pytest.raises(ValueError, match="v6/getDataByCode"):
        ApiProfile(APIType.AquaTemp, fields)


@pytest.mark.parametrize(
    ("profile_type", "expected"), SEMANTIC_CODES.items(), ids=list(SEMANTIC_CODES)
)
async def test_reads_through_semantic_codes(profile_type, expected):
    profile = await ApiProfile.load(profile_type)

    assert profile.get(APIParam.SemanticCodes) is expected
