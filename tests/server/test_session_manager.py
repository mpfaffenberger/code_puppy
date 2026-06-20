from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from code_puppy.messaging.bus import MessageBus
from code_puppy.messaging.messages import MessageLevel, TextMessage
from code_puppy.server.session_manager import SessionManager, SessionState


@dataclass
class FakeResult:
    output: str
    messages: list[str]

    def all_messages(self):
        return self.messages


class FakeAgent:
    def __init__(self, name: str, bus: MessageBus, delay: float = 0) -> None:
        self.name = name
        self.bus = bus
        self.delay = delay
        self.history: list[str] = []

    async def run_with_mcp(self, prompt: str):
        self.bus.emit(TextMessage(level=MessageLevel.INFO, text=f"start:{prompt}"))
        await asyncio.sleep(self.delay)
        self.history.extend([prompt, f"answer:{prompt}"])
        return FakeResult(f"answer:{prompt}", list(self.history))

    def get_message_history(self):
        return self.history

    def set_message_history(self, history):
        self.history = list(history)

    def estimate_tokens_for_message(self, _message):
        return 1


@pytest.fixture
def manager(tmp_path):
    bus = MessageBus()
    value = SessionManager(
        state_dir=tmp_path,
        bus=bus,
        agent_factory=lambda name: FakeAgent(name, bus),
    )
    yield value
    value.close()


async def test_independent_sessions_isolate_events(manager):
    one = await manager.create_session("mist")
    two = await manager.create_session("mist")

    await asyncio.gather(
        await manager.submit(one.id, "one"),
        await manager.submit(two.id, "two"),
    )

    assert one.state is SessionState.IDLE
    assert two.state is SessionState.IDLE
    assert all(event.session_id == one.id for event in one.events)
    assert all(event.session_id == two.id for event in two.events)
    assert any(event.data.get("text") == "start:one" for event in one.events)
    assert not any(event.data.get("text") == "start:two" for event in one.events)


async def test_replay_after_event_id(manager):
    record = await manager.create_session()
    await (await manager.submit(record.id, "hello"))
    expected = [event for event in record.events if event.sequence > 2]

    stream = manager.events(record.id, after=2)
    actual = [await anext(stream) for _ in expected]
    await stream.aclose()

    assert [event.sequence for event in actual] == [
        event.sequence for event in expected
    ]


async def test_slow_subscriber_gets_lag_marker(tmp_path):
    bus = MessageBus()
    manager = SessionManager(
        state_dir=tmp_path,
        bus=bus,
        subscriber_limit=1,
        agent_factory=lambda name: FakeAgent(name, bus),
    )
    record = await manager.create_session()
    stream = manager.events(record.id, after=record.sequence)
    pending = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    manager._append_event(record, "one", {})
    manager._append_event(record, "two", {})

    event = await pending
    assert event.type == "stream.lagged"
    await stream.aclose()
    manager.close()


async def test_registry_and_history_restore(tmp_path):
    bus = MessageBus()

    def factory(name):
        return FakeAgent(name, bus)

    first = SessionManager(state_dir=tmp_path, bus=bus, agent_factory=factory)
    record = await first.create_session()
    await (await first.submit(record.id, "remember"))
    first.close()

    second = SessionManager(state_dir=tmp_path, bus=bus, agent_factory=factory)
    restored = second.get_session(record.id)
    await (await second.submit(restored.id, "again"))

    assert restored.agent.get_message_history() == [
        "remember",
        "answer:remember",
        "again",
        "answer:again",
    ]
    assert (tmp_path / "server_autosaves" / f"server-{record.id}.jsonl").exists()
    second.close()


async def test_fork_reuses_tree_history(manager):
    source = await manager.create_session()
    await (await manager.submit(source.id, "first"))

    forked = await manager.fork(source.id)

    assert forked.agent.get_message_history() == ["first", "answer:first"]
    assert any(event.type == "session.forked" for event in forked.events)


async def test_interrupt_cancels_owned_task(tmp_path, monkeypatch):
    bus = MessageBus()
    manager = SessionManager(
        state_dir=tmp_path,
        bus=bus,
        agent_factory=lambda name: FakeAgent(name, bus, delay=10),
    )
    monkeypatch.setattr(
        "code_puppy.tools.command_runner.kill_all_running_shell_processes", lambda: 0
    )
    record = await manager.create_session()
    await manager.submit(record.id, "slow")
    await asyncio.sleep(0)

    assert await manager.interrupt(record.id) is True
    assert record.state is SessionState.INTERRUPTED
    manager.close()
