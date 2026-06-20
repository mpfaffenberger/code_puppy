import asyncio

from code_puppy.messaging.bus import MessageBus
from code_puppy.messaging.messages import MessageLevel, TextMessage


async def test_contextvar_session_scoping_and_listener_fanout():
    bus = MessageBus()
    seen = []
    listener_id = bus.add_listener(seen.append)

    async def emit(session_id):
        token = bus.push_session_context(session_id)
        await asyncio.sleep(0)
        bus.emit(TextMessage(level=MessageLevel.INFO, text=session_id))
        bus.reset_session_context(token)

    await asyncio.gather(emit("one"), emit("two"))
    bus.remove_listener(listener_id)

    assert {(item.text, item.session_id) for item in seen} == {
        ("one", "one"),
        ("two", "two"),
    }
