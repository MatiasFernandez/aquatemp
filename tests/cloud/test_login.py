"""Login: request shape, the token on later requests, rejection and re-login."""

from aiohttp import ClientSession
import pytest
from yarl import URL

from custom_components.aqua_temp.cloud.api_types import APIType
from custom_components.aqua_temp.cloud.client import AquaTempAPI, Credentials
from custom_components.aqua_temp.cloud.exceptions import LoginError

from .mock_cloud import DATA, DATA_IDLE, DEVICE_CODE, cloud_with, load_fixture

# Literal on purpose: the expected values must not come from the config under test
LOGIN = "app/user/login"
LOGIN_URL = URL(f"https://cloud.linked-go.com:449/crmservice/api/{LOGIN}")

# MD5 of test-password
PASSWORD_HASH = "dfb450efddbb5387197c84460623675b"


@pytest.fixture
def cloud_responses() -> dict:
    return {DATA: DATA_IDLE}


def login_with_token(token: str) -> dict:
    login = load_fixture(APIType.AquaTemp, "synthetic/login")
    login["objectResult"]["x-token"] = token

    return login


def tokens_sent(cloud) -> set[str | None]:
    return {
        call.kwargs["headers"].get("x-token")
        for calls in cloud.requests.values()
        for call in calls
    }


async def test_login_sends_username_and_password_hash(client, wire):
    await client.initialize(throw_error=True)

    assert wire[0] == (
        LOGIN,
        {"userName": "test@example.com", "password": PASSWORD_HASH},
    )
    assert client.login_details == {"x-token": "test-token"}


def test_credentials_repr_hides_the_password():
    credentials = Credentials(username="test@example.com", password="test-password")

    assert "test-password" not in repr(credentials)


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
async def test_rejected_login_with_null_result_raises(client, wire):
    """A null objectResult, as in the cloud's other error responses."""
    with pytest.raises(LoginError):
        await client.initialize(throw_error=True)

    assert not client.is_connected
    assert [endpoint for endpoint, _ in wire] == [LOGIN]


@cloud_with({DATA: [401, DATA_IDLE]})
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


@cloud_with(
    {
        DATA: DATA_IDLE,
        LOGIN: [login_with_token("token-a"), login_with_token("token-b")],
    }
)
async def test_each_client_sends_its_own_token(
    client, api_profile, device_profiles, cloud
):
    """Two clients, as two config entries have, do not log each other out."""
    async with ClientSession() as session:
        other = AquaTempAPI(
            session,
            Credentials(username="other@example.com", password="other-password"),
            api_profile,
            device_profiles,
        )

        await client.initialize(throw_error=True)
        await other.initialize(throw_error=True)

        cloud.requests.clear()
        await client.update()

        assert tokens_sent(cloud) == {"token-a"}

        cloud.requests.clear()
        await other.update()

        assert tokens_sent(cloud) == {"token-b"}
