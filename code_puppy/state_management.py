from typing import Any, List

from code_puppy.message_history_processor import message_history_processor

_message_history: List[Any] = []


def get_message_history() -> List[Any]:
    return _message_history


def set_message_history(history: List[Any]) -> None:
    global _message_history
    _message_history = history


def clear_message_history() -> None:
    global _message_history
    _message_history = []


def append_to_message_history(message: Any) -> None:
    _message_history.append(message)


def extend_message_history(history: List[Any]) -> None:
    _message_history.extend(history)


def hash_message(message):
    hashable_entities = []
    for part in message.parts:
        if hasattr(part, "timestamp"):
            hashable_entities.append(part.timestamp.isoformat())
        elif hasattr(part, "tool_call_id"):
            hashable_entities.append(part.tool_call_id)
        else:
            hashable_entities.append(part.content)
    return hash(",".join(hashable_entities))


def message_history_accumulator(messages: List[Any]):
    global _message_history

    message_history_hashes = set([hash_message(m) for m in _message_history])
    for msg in messages:
        if hash_message(msg) not in message_history_hashes:
            _message_history.append(msg)

    # Apply message history trimming using the main processor
    # This ensures we maintain global state while still managing context limits
    trimmed_messages = message_history_processor(_message_history)

    # Update our global state with the trimmed version
    # This preserves the state but keeps us within token limits
    _message_history = trimmed_messages

    return _message_history
