"""Frontend emitter plugin for Code Puppy.

This plugin provides event emission capabilities for frontend integration,
allowing WebSocket handlers to subscribe to real-time events from the
agent system including tool calls, streaming events, and agent invocations.

Usage:
    from code_puppy.plugins.frontend_emitter.emitter import (
        emit_event,
        subscribe,
        unsubscribe,
        get_recent_events,
    )

    # Subscribe to events
    queue = subscribe()

    # Process events in your WebSocket handler
    while True:
        event = await queue.get()
        await websocket.send_json(event)

    # Clean up
    unsubscribe(queue)
"""
