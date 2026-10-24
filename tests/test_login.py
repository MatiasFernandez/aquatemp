"""Login: request shape, the token on later requests, rejection and re-login."""

import pytest
from yarl import URL

from custom_components.aqua_temp.cloud.exceptions import LoginError

from .conftest import DEVICE_CODE, cloud_with

# Literal on purpose: the expected values must not come from the config under test
LOGIN = "app/user/login"
DATA = "app/device/getDataByCode"
LOGIN_URL = URL(f"https://cloud.linked-go.com:449/crmservice/api/{LOGIN}")

# MD5 of test-password
PASSWORD_HASH = "dfb450efddbb5387197c84460623675b"


@pytest.fixture
def cloud_responses() -> dict:
    return {DATA: "get_data_by_code.idle"}


async def test_login_sends_username_and_password_hash(client, wire):
    await client.initialize(throw_error=True)

    assert wire[0] == (
        LOGIN,
        {"userName": "test@example.com", "password": PASSWORD_HASH},
    )
    assert client.login_details == {"x-token": "test-token"}


async def test_token_sent_on_every_request_after_login(api, cloud):
    await api.update()

    for (_, url), calls in cloud.requests.items():
        for call in calls:
            headers = call.kwargs["headers"]

            if url == LOGIN_URL:
                assert "x-token" not in headers

            else:
                assert headers["x-token"] == "test-token"

    assert len(cloud.requests) > 1


@cloud_with({LOGIN: "synthetic/login_rejected"})
async def test_rejected_login_raises_and_leaves_no_token(client, wire):
    with pytest.raises(LoginError):
        await client.initialize(throw_error=True)

    assert not client.is_connected
    assert [endpoint for endpoint, _ in wire] == [LOGIN]


@cloud_with({LOGIN: "synthetic/login_rejected_null"})
async def test_rejected_login_with_null_result_crashes(client):
    # Suspect (AT-040): `.get(key, {})` returns the null, so a rejection shaped
    # like the other error responses never becomes LoginError
    with pytest.raises(AttributeError):
        await client.initialize(throw_error=True)

    assert not client.is_connected


@cloud_with({DATA: [401, "get_data_by_code.idle"]})
async def test_unauthorized_read_logs_in_again_and_retries(api, wire):
    """HTTP 401 on a read is treated as an invalid token."""
    wire.clear()

    await api.update()

    assert [endpoint for endpoint, _ in wire] == [
        DATA,
        LOGIN,
        "app/user/getUserInfo",
        "app/device/deviceList",
        "app/device/getMyTobeAppectDeviceShareDataList",
        "app/device/getMyAppectDeviceShareDataList",
        DATA,
        "app/device/getDeviceStatus",
    ]
    assert api.get_device_data(DEVICE_CODE)["T02"] == "13.0"
