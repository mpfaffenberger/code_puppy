"""Exercise the real OAuth callback server, including lazy protocol imports."""

import asyncio
import socket

import anyio
import httpx
import pytest
from fastmcp.client.auth.oauth import (
    OAuthCallbackResult,
    create_oauth_callback_server,
)


def test_callback_protocol_dependencies_load():
    server = create_oauth_callback_server(port=0)
    # Uvicorn imports the configured protocol only at startup, not construction.
    server.config.load()
    assert server.config.loaded


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params,status,expected_error",
    [
        ({"code": "test-code", "state": "test-state"}, 200, False),
        ({"error": "access_denied", "state": "test-state"}, 400, True),
        ({"code": "test-code"}, 400, True),
    ],
)
async def test_callback_server_round_trip(params, status, expected_error):
    result = OAuthCallbackResult()
    ready = anyio.Event()
    server = create_oauth_callback_server(
        port=0, result_container=result, result_ready=ready
    )
    # Reserve an ephemeral loopback port without a find-port/rebind race.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.setblocking(False)
        port = listener.getsockname()[1]
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    if task.done():
                        await task
                        pytest.fail("Callback server exited before starting")
                    await asyncio.sleep(0.01)
                async with httpx.AsyncClient(trust_env=False) as client:
                    response = await client.get(
                        f"http://127.0.0.1:{port}/callback", params=params
                    )
                await ready.wait()
            assert response.status_code == status
            assert bool(result.error) == expected_error
            if not expected_error:
                assert (result.code, result.state) == ("test-code", "test-state")
        finally:
            server.should_exit = True
            try:
                await asyncio.wait_for(task, timeout=5)
            finally:
                if not task.done():
                    task.cancel()
