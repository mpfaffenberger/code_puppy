"""Real task/context regressions: no mocked sleeps or lifecycle coroutines."""

import asyncio

import anyio
import pytest

from code_puppy.mcp_.async_lifecycle import AsyncServerLifecycleManager


class Toolset:
    def __init__(self, *, blocked=False, failure=None, init_timeout=None):
        self.init_timeout = init_timeout
        self.failure = failure
        self.entering = asyncio.Event()
        self.release = asyncio.Event()
        self.cleaned = asyncio.Event()
        self.exiting = asyncio.Event()
        self.exit_release = asyncio.Event()
        self.exit_release.set()
        if not blocked:
            self.release.set()
        self.is_running = False
        self.enters = 0
        self.exits = 0

    async def __aenter__(self):
        self.enters += 1
        self.owner = asyncio.current_task()
        self.entering.set()
        try:
            await self.release.wait()
            if self.failure:
                raise self.failure
        except BaseException:
            # Like an actual transport, enter cleans its partial resources.
            await asyncio.sleep(0)
            self.cleaned.set()
            raise
        self.scope = anyio.CancelScope()
        self.scope.__enter__()
        self.is_running = True
        return self

    async def __aexit__(self, *args):
        assert asyncio.current_task() is self.owner
        self.exiting.set()
        await self.exit_release.wait()
        self.scope.__exit__(*args)
        self.exits += 1
        self.is_running = False
        self.cleaned.set()


@pytest.fixture
async def manager():
    manager = AsyncServerLifecycleManager()
    yield manager
    await asyncio.wait_for(manager.stop_all(), 1)
    assert not manager._servers


async def begin(manager, server, server_id="test"):
    start = asyncio.create_task(manager.start_server(server_id, server))
    await asyncio.wait_for(server.entering.wait(), 1)
    return start


async def test_stop_during_blocked_enter(manager):
    server = Toolset(blocked=True)
    start = await begin(manager, server)
    lifecycle = manager._servers["test"].task
    assert not manager.is_running("test")
    assert not manager.list_servers()["test"]["is_running"]
    assert await asyncio.wait_for(manager.stop_server("test"), 1)
    assert await asyncio.wait_for(start, 1) is False
    assert lifecycle.done()
    assert server.cleaned.is_set()
    assert server.exits == 0
    assert not manager._servers


async def test_failure_is_reported_without_waiting_for_deadline(manager):
    server = Toolset(failure=ValueError("bad handshake"), init_timeout=300)
    assert await asyncio.wait_for(manager.start_server("test", server), 1) is False
    assert server.cleaned.is_set()
    assert not manager._servers
    replacement = Toolset()
    assert await manager.start_server("test", replacement)


async def test_timeout_joins_partial_enter_cleanup(manager, caplog):
    server = Toolset(blocked=True, init_timeout=0.02)
    start = await begin(manager, server)
    lifecycle = manager._servers["test"].task
    assert await asyncio.wait_for(start, 1) is False
    assert lifecycle.done()
    assert server.cleaned.is_set()
    assert not manager._servers
    assert "Timed out" in caplog.text


@pytest.mark.parametrize("timeout", [None, 330])
async def test_wrapped_toolset_timeout_is_used(manager, monkeypatch, timeout):
    server = Toolset(init_timeout=timeout)

    class Wrapper:
        wrapped = server

        async def __aenter__(self):
            return await self.wrapped.__aenter__()

        async def __aexit__(self, *args):
            return await self.wrapped.__aexit__(*args)

    deadlines = []
    real_timeout = asyncio.timeout

    def capture_timeout(delay):
        deadlines.append(delay)
        return real_timeout(delay)

    monkeypatch.setattr(asyncio, "timeout", capture_timeout)
    assert await manager.start_server("test", Wrapper())
    assert deadlines == [timeout]


async def test_stop_running_does_not_hold_lock_or_double_cancel(manager):
    server = Toolset()
    assert await manager.start_server("test", server)
    server.exit_release.clear()
    stop = asyncio.create_task(manager.stop_server("test"))
    await asyncio.wait_for(server.exiting.wait(), 1)
    assert not manager.is_running("test")
    # Registry operations must remain available while __aexit__ is blocked.
    assert await asyncio.wait_for(manager.start_server("other", Toolset()), 1)
    assert await manager.start_server("test", Toolset()) is False
    second_stop = asyncio.create_task(manager.stop_server("test"))
    await asyncio.sleep(0)
    server.exit_release.set()
    assert await asyncio.wait_for(asyncio.gather(stop, second_stop), 1) == [True, True]
    assert server.exits == 1
    assert "test" not in manager._servers


async def test_duplicate_starts_share_pending_and_running_lifecycle(manager):
    server = Toolset(blocked=True)
    start = await begin(manager, server)
    ignored = Toolset()
    duplicate = asyncio.create_task(manager.start_server("test", ignored))
    await asyncio.sleep(0)
    assert not duplicate.done()
    server.release.set()
    assert await asyncio.wait_for(asyncio.gather(start, duplicate), 1) == [True, True]
    assert await manager.start_server("test", ignored)
    assert server.enters == 1
    assert ignored.enters == 0


@pytest.mark.parametrize("cancel_owner", [True, False])
async def test_cancel_start_waiter(manager, cancel_owner):
    server = Toolset(blocked=True)
    owner = await begin(manager, server)
    duplicate = asyncio.create_task(manager.start_server("test", server))
    await asyncio.sleep(0)
    cancelled = owner if cancel_owner else duplicate
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(cancelled, 1)
    if cancel_owner:
        assert await asyncio.wait_for(duplicate, 1) is False
        assert server.cleaned.is_set()
        assert not manager._servers
    else:
        assert not owner.done()
        server.release.set()
        assert await asyncio.wait_for(owner, 1)


async def test_stop_before_lifecycle_task_runs(manager):
    server = Toolset(blocked=True)
    start = asyncio.create_task(manager.start_server("test", server))
    # start publishes its child, but this task resumes before that child runs.
    await asyncio.sleep(0)
    async with asyncio.timeout(1):
        assert await manager.stop_server("test")
    assert await asyncio.wait_for(start, 1) is False
    assert server.enters == 0
    assert not manager._servers


async def test_stop_all_includes_pending(manager):
    pending = Toolset(blocked=True)
    start = await begin(manager, pending)
    assert await manager.start_server("running", Toolset())
    await asyncio.wait_for(manager.stop_all(), 1)
    assert await start is False
    assert not manager._servers
    assert await manager.stop_server("missing") is False


async def test_cancel_stop_caller_preserves_cleanup(manager):
    server = Toolset()
    assert await manager.start_server("test", server)
    server.exit_release.clear()
    stop = asyncio.create_task(manager.stop_server("test"))
    await asyncio.wait_for(server.exiting.wait(), 1)
    stop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stop
    assert "test" in manager._servers
    server.exit_release.set()
    assert await asyncio.wait_for(manager.stop_server("test"), 1)
    assert server.exits == 1
    assert not manager._servers


async def test_duplicate_start_shares_failure(manager):
    server = Toolset(blocked=True, failure=RuntimeError("OAuth denied"))
    owner = await begin(manager, server)
    duplicate = asyncio.create_task(manager.start_server("test", Toolset()))
    await asyncio.sleep(0)
    server.release.set()
    assert await asyncio.wait_for(asyncio.gather(owner, duplicate), 1) == [False, False]
    assert server.enters == 1
    assert not manager._servers
