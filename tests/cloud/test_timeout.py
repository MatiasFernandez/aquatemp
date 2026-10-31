"""Requests to the cloud carry a total timeout, and a request that exceeds it fails
with a message saying so.

The mocked cloud doesn't enforce timeouts, so the limit is checked where it
crosses the boundary, on the request, and a timeout is simulated by the cloud
mock raising it.
"""

from unittest.mock import patch

from aiohttp import ClientTimeout
import pytest

from .mock_cloud import cloud_with

DATA = "app/device/getDataByCode"


async def test_every_request_has_a_total_timeout(client):
    with patch.object(client._session, "post", wraps=client._session.post) as post:
        await client.initialize(throw_error=True)

    assert post.call_count > 1
    assert {call.kwargs["timeout"] for call in post.call_args_list} == {
        ClientTimeout(total=30)
    }


@cloud_with({DATA: TimeoutError()})
async def test_request_that_exceeds_the_timeout_fails_with_a_message(api):
    with pytest.raises(
        TimeoutError,
        match=rf"Request to {DATA} timed out after 30 s",
    ):
        await api.update()
