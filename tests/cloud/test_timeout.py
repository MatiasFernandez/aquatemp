"""Requests to the cloud carry a total timeout, and a request that exceeds it fails
with a message saying so.

The mocked cloud doesn't enforce timeouts, so the limit is checked where it
crosses the boundary, on the request, and a timeout is simulated by the cloud
mock raising it.
"""

from unittest.mock import patch

from aiohttp import ClientSession, ClientTimeout
import pytest

from custom_components.aqua_temp.cloud.client import AquaTempAPI, Credentials

from .mock_cloud import cloud_with

DATA = "app/device/getDataByCode"


@pytest.fixture
async def client_with_a_timeout(api_profile, device_profiles, cloud):
    async with ClientSession() as session:
        yield AquaTempAPI(
            session,
            Credentials(username="test@example.com", password="test-password"),
            api_profile,
            device_profiles,
            request_timeout=15,
        )


def timeouts(post) -> set:
    return {call.kwargs["timeout"] for call in post.call_args_list}


async def test_every_request_has_a_total_timeout_of_10_s_by_default(client):
    with patch.object(client._session, "post", wraps=client._session.post) as post:
        await client.initialize(throw_error=True)

    assert post.call_count > 1
    assert timeouts(post) == {ClientTimeout(total=10)}


async def test_every_request_has_the_timeout_the_client_was_given(
    client_with_a_timeout,
):
    session = client_with_a_timeout._session

    with patch.object(session, "post", wraps=session.post) as post:
        await client_with_a_timeout.initialize(throw_error=True)

    assert post.call_count > 1
    assert timeouts(post) == {ClientTimeout(total=15)}


@cloud_with({DATA: TimeoutError()})
async def test_request_that_exceeds_the_timeout_fails_with_a_message(api):
    with pytest.raises(
        TimeoutError,
        match=rf"Request to {DATA} timed out after 10 s",
    ):
        await api.update()
