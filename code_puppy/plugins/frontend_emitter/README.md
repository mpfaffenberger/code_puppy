# Frontend Emitter Plugin

A builtin plugin for Code Puppy that emits structured events for frontend integration via WebSocket handlers.

## Overview

This plugin provides a pub/sub event system that allows WebSocket handlers (or any async consumer) to subscribe to real-time events from the agent system. Events include:

- **Tool call lifecycle** - when tools start and complete execution
- **Stream events** - real-time streaming tokens and events from agents
- **Agent invocations** - when agents are invoked

## Architecture

```
┌─────────────────────┐     ┌─────────────────────┐
│    Agent System     │────▶│  Callback System    │
│   (tools, agents)   │     │  (pre/post hooks)   │
└─────────────────────┘     └──────────┬──────────┘
                                       │
                                       ▼
                            ┌─────────────────────┐
                            │  Frontend Emitter   │
                            │    (this plugin)    │
                            └──────────┬──────────┘
                                       │
                     ┌─────────────────┼─────────────────┐
                     ▼                 ▼                 ▼
              ┌───────────┐     ┌───────────┐     ┌───────────┐
              │ WebSocket │     │ WebSocket │     │ WebSocket │
              │ Handler 1 │     │ Handler 2 │     │ Handler N │
              └───────────┘     └───────────┘     └───────────┘
```

## Usage

### Subscribing to Events

```python
from code_puppy.plugins.frontend_emitter.emitter import (
    subscribe,
    unsubscribe,
    get_recent_events,
)

# In your WebSocket handler
async def websocket_handler(websocket):
    # Subscribe to the event stream
    queue = subscribe()
    
    try:
        # Optionally send recent events for "catch up"
        for event in get_recent_events():
            await websocket.send_json(event)
        
        # Stream events to the client
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    finally:
        # Always clean up!
        unsubscribe(queue)
```

### Manually Emitting Events

```python
from code_puppy.plugins.frontend_emitter.emitter import emit_event

# Emit a custom event
emit_event("custom_event", {
    "message": "Something happened!",
    "details": {"foo": "bar"},
})
```

## Event Types

### `tool_call_start`

Emitted when a tool begins execution.

```json
{
    "id": "uuid-here",
    "type": "tool_call_start",
    "timestamp": "2025-05-15T12:00:00.000000+00:00",
    "data": {
        "tool_name": "read_file",
        "tool_args": {"file_path": "example.py"},
        "start_time": 1715774400.123
    }
}
```

### `tool_call_complete`

Emitted when a tool finishes execution.

```json
{
    "id": "uuid-here",
    "type": "tool_call_complete",
    "timestamp": "2025-05-15T12:00:00.500000+00:00",
    "data": {
        "tool_name": "read_file",
        "tool_args": {"file_path": "example.py"},
        "duration_ms": 45.2,
        "success": true,
        "result_summary": "<dict with 3 keys>"
    }
}
```

### `stream_event`

Emitted for streaming events from agents.

```json
{
    "id": "uuid-here",
    "type": "stream_event",
    "timestamp": "2025-05-15T12:00:00.100000+00:00",
    "data": {
        "event_type": "token",
        "event_data": "Hello, ",
        "agent_session_id": "my-session-abc123"
    }
}
```

### `agent_invoked`

Emitted when an agent is invoked.

```json
{
    "id": "uuid-here",
    "type": "agent_invoked",
    "timestamp": "2025-05-15T12:00:00.000000+00:00",
    "data": {
        "agent_name": "code_reviewer",
        "session_id": "review-session-123",
        "prompt_preview": "Review this code for..."
    }
}
```

## Thread Safety

The emitter is designed for async operation:

- `subscribe()` and `unsubscribe()` are thread-safe
- `emit_event()` uses `put_nowait()` which is safe from any context
- Each subscriber gets their own queue to prevent blocking
- Slow subscribers will have events dropped (queue maxsize=100) rather than blocking the system

## Configuration

No configuration required - this plugin auto-registers its callbacks on import.

## Files

- `__init__.py` - Module docstring and exports
- `emitter.py` - Core event emission and subscription logic
- `register_callbacks.py` - Callback registration for system events
- `README.md` - This documentation

## Testing

```python
import asyncio
from code_puppy.plugins.frontend_emitter.emitter import (
    emit_event,
    subscribe,
    unsubscribe,
    get_recent_events,
    clear_recent_events,
)

async def test_emission():
    clear_recent_events()  # Start fresh
    queue = subscribe()
    
    emit_event("test_event", {"foo": "bar"})
    
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event["type"] == "test_event"
    assert event["data"]["foo"] == "bar"
    
    unsubscribe(queue)
    print("✅ Test passed!")

asyncio.run(test_emission())
```
