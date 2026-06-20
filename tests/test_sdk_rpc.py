from __future__ import annotations

import asyncio
import json
from io import StringIO

from code_puppy.messaging.bus import MessageBus
from code_puppy.rpc import RPCServer
from code_puppy.sdk import InProcessAgentClient
from code_puppy.server.session_manager import SessionManager
from tests.server.test_session_manager import FakeAgent


def make_manager(tmp_path):
    bus = MessageBus()
    return SessionManager(
        state_dir=tmp_path,
        bus=bus,
        agent_factory=lambda name: FakeAgent(name, bus),
    )


async def test_embedded_sdk_submit_stream(tmp_path):
    manager = make_manager(tmp_path)
    client = InProcessAgentClient(manager)
    session = await client.session()

    events = [event async for event in session.submit("sdk")]

    assert events[-1].type == "session.idle"
    assert any(event.type == "AgentResponseMessage" for event in events)
    assert await client.get_session(session.id)
    await client.close()


async def test_rpc_dispatch_uses_same_session_manager(tmp_path):
    manager = make_manager(tmp_path)
    rpc = RPCServer(manager)
    created = await rpc.dispatch({"id": 1, "method": "session.create", "params": {}})
    session_id = created["result"]["id"]
    submitted = await rpc.dispatch(
        {
            "id": 2,
            "method": "session.submit",
            "params": {"session_id": session_id, "prompt": "rpc"},
        }
    )
    await manager.get_session(session_id).task
    events = await rpc.dispatch(
        {
            "id": 3,
            "method": "session.events",
            "params": {"session_id": session_id},
        }
    )

    assert submitted["result"] == {"accepted": True}
    assert any(event["type"] == "AgentResponseMessage" for event in events["result"])
    manager.close()


async def test_rpc_subscription_pushes_event_notifications(tmp_path):
    manager = make_manager(tmp_path)
    rpc = RPCServer(manager)
    record = await manager.create_session()
    output = StringIO()
    subscription_id = rpc.subscribe(record.id, output, after=record.sequence)
    await asyncio.sleep(0)

    manager._append_event(record, "test.event", {"ok": True})
    await asyncio.sleep(0)
    rpc.unsubscribe(subscription_id)
    await asyncio.sleep(0)

    notification = json.loads(output.getvalue().strip())
    assert notification["method"] == "session.event"
    assert notification["params"]["event"]["type"] == "test.event"
    manager.close()
