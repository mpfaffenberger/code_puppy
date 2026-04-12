from io import StringIO
from unittest.mock import MagicMock

from rich.console import Console
from rich.table import Table

from code_puppy.messaging.bus import MessageBus
from code_puppy.messaging.legacy_bridge import LegacyQueueToBusBridge
from code_puppy.messaging.message_queue import MessageQueue, MessageType, UIMessage
from code_puppy.messaging.messages import LegacyQueueMessage
from code_puppy.messaging.rich_renderer import RichConsoleRenderer


def _console():
    return Console(file=StringIO(), force_terminal=False, width=100)


def test_legacy_bridge_replays_buffered_messages_into_bus():
    queue = MessageQueue()
    bus = MagicMock(spec=MessageBus)
    bridge = LegacyQueueToBusBridge(queue, bus)

    queue.emit_simple(MessageType.INFO, "hello")
    queue.emit_simple(MessageType.DIVIDER, "---")

    bridge.start()

    emitted = [call.args[0] for call in bus.emit.call_args_list]
    assert len(emitted) == 2
    assert all(isinstance(message, LegacyQueueMessage) for message in emitted)
    assert emitted[0].legacy_type == "info"
    assert emitted[0].content == "hello"
    assert emitted[1].legacy_type == "divider"


def test_legacy_bridge_skips_human_input_messages():
    queue = MessageQueue()
    bus = MagicMock(spec=MessageBus)
    bridge = LegacyQueueToBusBridge(queue, bus)

    queue.emit(
        UIMessage(
            type=MessageType.HUMAN_INPUT_REQUEST,
            content="Enter value",
            metadata={"prompt_id": "p1"},
        )
    )

    bridge.start()

    bus.emit.assert_not_called()


def test_rich_renderer_renders_wrapped_legacy_renderables():
    console = _console()
    renderer = RichConsoleRenderer(MessageBus(), console=console)

    table = Table()
    table.add_column("Col")
    table.add_row("value")

    renderer._render_sync(
        LegacyQueueMessage(
            legacy_type="info",
            content=table,
            legacy_metadata={},
        )
    )

    output = console.file.getvalue()
    assert "Col" in output
    assert "value" in output
