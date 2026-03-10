"""Bridge legacy MessageQueue output into the structured MessageBus."""

from __future__ import annotations

import logging

from .bus import MessageBus
from .message_queue import MessageQueue, MessageType, UIMessage
from .messages import LegacyQueueMessage

logger = logging.getLogger(__name__)


class LegacyQueueToBusBridge:
    """Forward legacy queue messages into the structured bus."""

    def __init__(self, queue: MessageQueue, bus: MessageBus) -> None:
        self._queue = queue
        self._bus = bus
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True

        for message in self._queue.get_buffered_messages():
            self._forward_message(message)
        self._queue.clear_startup_buffer()
        self._queue.add_listener(self._forward_message)

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        self._queue.remove_listener(self._forward_message)

    def _forward_message(self, message: UIMessage) -> None:
        if message.type == MessageType.HUMAN_INPUT_REQUEST:
            logger.debug("Skipping legacy human-input queue message in bridge")
            return

        self._bus.emit(
            LegacyQueueMessage(
                legacy_type=message.type.value,
                content=message.content,
                legacy_metadata=dict(message.metadata or {}),
                legacy_timestamp=message.timestamp,
            )
        )
