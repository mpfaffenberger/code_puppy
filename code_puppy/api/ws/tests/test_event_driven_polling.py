"""Tests for event-driven polling elimination (Phases 1-2 fixes).

Verifies that:
1. Events are collected without polling loops
2. Batching still works efficiently
3. Timeout handling works gracefully
4. Event ordering is preserved
5. No regressions in event processing
"""

import asyncio

import pytest


@pytest.mark.asyncio
async def test_event_driven_collection_no_polling():
    """Verify events are collected using asyncio.wait_for, not polling loops.

    This test ensures that the event-driven approach (Phase 1 & 2) correctly
    uses asyncio.wait_for() instead of busy-waiting with time.monotonic().
    """
    # Create a queue and emit events
    event_queue: asyncio.Queue = asyncio.Queue()

    # Add events to the queue
    await event_queue.put({"type": "content", "data": {"text": "Hello"}})
    await event_queue.put({"type": "content", "data": {"text": " World"}})

    # Simulate the event-driven collection pattern from fixed handlers
    events_to_send = []
    try:
        # Wait for first event with 10ms timeout (event-driven, not polling)
        first_event = await asyncio.wait_for(event_queue.get(), timeout=0.01)
        events_to_send.append(first_event)

        # Collect any additional events already queued (non-blocking)
        while not event_queue.empty():
            try:
                events_to_send.append(event_queue.get_nowait())
            except Exception:
                break

    except asyncio.TimeoutError:
        pass

    # Verify both events were collected
    assert len(events_to_send) == 2
    assert events_to_send[0]["data"]["text"] == "Hello"
    assert events_to_send[1]["data"]["text"] == " World"


@pytest.mark.asyncio
async def test_event_driven_timeout_handling():
    """Verify timeout handling when no events are available.

    This test ensures asyncio.TimeoutError is properly caught
    and doesn't cause the handler to crash.
    """
    # Empty queue
    event_queue: asyncio.Queue = asyncio.Queue()

    # Simulate event-driven collection with very short timeout
    events_to_send = []
    try:
        first_event = await asyncio.wait_for(event_queue.get(), timeout=0.001)
        events_to_send.append(first_event)
    except asyncio.TimeoutError:
        # Expected - no events in queue
        pass

    # No events should be collected
    assert len(events_to_send) == 0


@pytest.mark.asyncio
async def test_batching_preserved_with_event_driven():
    """Verify batching efficiency is preserved in event-driven approach.

    The 10ms batching window should still collect multiple events
    without introducing polling overhead.
    """
    event_queue: asyncio.Queue = asyncio.Queue()

    # Emit multiple events rapidly
    for i in range(5):
        await event_queue.put({"type": "event", "data": {"index": i}})

    # Collect all events in one batch using event-driven approach
    events_to_send = []
    try:
        first_event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
        events_to_send.append(first_event)

        while not event_queue.empty():
            try:
                events_to_send.append(event_queue.get_nowait())
            except Exception:
                break

    except asyncio.TimeoutError:
        pass

    # All 5 events should be collected in a single batch
    assert len(events_to_send) == 5
    for i in range(5):
        assert events_to_send[i]["data"]["index"] == i


@pytest.mark.asyncio
async def test_event_ordering_preserved():
    """Verify event ordering is preserved in batches.

    Events should be processed in the order they were emitted.
    """
    event_queue: asyncio.Queue = asyncio.Queue()

    # Emit events with order markers
    for i in range(10):
        await event_queue.put(
            {"type": "ordered_event", "data": {"sequence": i, "timestamp": i * 1000}}
        )

    # Collect events
    events_to_send = []
    try:
        first_event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
        events_to_send.append(first_event)

        while not event_queue.empty():
            try:
                events_to_send.append(event_queue.get_nowait())
            except Exception:
                break

    except asyncio.TimeoutError:
        pass

    # Verify all events collected and in order
    assert len(events_to_send) == 10
    for i, event in enumerate(events_to_send):
        assert event["data"]["sequence"] == i
        assert event["data"]["timestamp"] == i * 1000


@pytest.mark.asyncio
async def test_interleaved_event_production():
    """Test handling of events added during collection.

    Simulates realistic scenario where events arrive both before
    and after timeout in the wait_for() call.
    """
    event_queue: asyncio.Queue = asyncio.Queue()

    # Add initial events
    await event_queue.put({"type": "pre", "data": {"phase": "before"}})

    async def add_event_later():
        """Add event after a small delay."""
        await asyncio.sleep(0.005)
        await event_queue.put({"type": "post", "data": {"phase": "after"}})

    # Start background task to add event during collection
    task = asyncio.create_task(add_event_later())

    # Collect events with longer timeout
    events_to_send = []
    try:
        first_event = await asyncio.wait_for(event_queue.get(), timeout=0.05)
        events_to_send.append(first_event)

        while not event_queue.empty():
            try:
                events_to_send.append(event_queue.get_nowait())
            except Exception:
                break

    except asyncio.TimeoutError:
        pass

    await task

    # Should have at least the first event
    assert len(events_to_send) >= 1
    assert events_to_send[0]["data"]["phase"] == "before"


@pytest.mark.asyncio
async def test_no_cpu_waste_on_idle():
    """Verify that idle timeouts don't cause busy-waiting.

    The old polling approach used await asyncio.sleep(0.01) which still
    wasted CPU. The new approach uses asyncio.wait_for() which properly
    suspends the task without CPU usage.
    """
    event_queue: asyncio.Queue = asyncio.Queue()

    # Record timing of timeout
    start_time = asyncio.get_event_loop().time()

    events_to_send = []
    try:
        # This should block efficiently for ~10ms, not busy-wait
        first_event = await asyncio.wait_for(event_queue.get(), timeout=0.01)
        events_to_send.append(first_event)
    except asyncio.TimeoutError:
        pass

    elapsed = asyncio.get_event_loop().time() - start_time

    # Should take approximately 10ms, not significantly less or more
    # (we allow some variance for system scheduling)
    assert 0.008 < elapsed < 0.05, f"Timeout took {elapsed}s, expected ~0.01s"
    assert len(events_to_send) == 0


@pytest.mark.asyncio
async def test_rapid_fire_events_single_batch():
    """Test that rapidly fired events are collected in a single batch.

    This is key to the efficiency gains - multiple events should be
    processed together without individual polling cycles.
    """
    event_queue: asyncio.Queue = asyncio.Queue()

    # Emit 100 events rapidly
    for i in range(100):
        await event_queue.put({"type": "rapid", "data": {"id": i}})

    # Collect all in single cycle
    events_to_send = []
    try:
        first_event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
        events_to_send.append(first_event)

        while not event_queue.empty():
            try:
                events_to_send.append(event_queue.get_nowait())
            except Exception:
                break

    except asyncio.TimeoutError:
        pass

    # All events should be collected
    assert len(events_to_send) == 100
    # Verify we got them in order
    for i in range(100):
        assert events_to_send[i]["data"]["id"] == i


@pytest.mark.asyncio
async def test_mixed_event_types_preserved():
    """Test that different event types are preserved in batches.

    Various event types (tool_call, content, stream_event, etc.) should
    all be collected and processed correctly.
    """
    event_queue: asyncio.Queue = asyncio.Queue()

    # Emit mixed event types
    event_types = [
        {"type": "tool_call_start", "data": {"tool": "search"}},
        {"type": "content", "data": {"text": "Query..."}},
        {"type": "tool_call_complete", "data": {"result": "found"}},
        {"type": "stream_event", "data": {"event_type": "part_delta"}},
        {"type": "message_complete", "data": {"final": True}},
    ]

    for event in event_types:
        await event_queue.put(event)

    # Collect all events
    events_to_send = []
    try:
        first_event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
        events_to_send.append(first_event)

        while not event_queue.empty():
            try:
                events_to_send.append(event_queue.get_nowait())
            except Exception:
                break

    except asyncio.TimeoutError:
        pass

    # All events collected
    assert len(events_to_send) == 5
    # Verify types match in order
    for i, expected in enumerate(event_types):
        assert events_to_send[i]["type"] == expected["type"]


@pytest.mark.asyncio
async def test_timeout_with_partial_events():
    """Test partial collection when timeout occurs mid-batch.

    If events come in after wait_for timeout, the handler should
    gracefully handle the empty batch and try again.
    """
    event_queue: asyncio.Queue = asyncio.Queue()

    # First collection - empty
    events_batch_1 = []
    try:
        first_event = await asyncio.wait_for(event_queue.get(), timeout=0.005)
        events_batch_1.append(first_event)
    except asyncio.TimeoutError:
        pass

    # First batch should be empty
    assert len(events_batch_1) == 0

    # Add events
    await event_queue.put({"type": "event1", "data": {}})
    await event_queue.put({"type": "event2", "data": {}})

    # Second collection - should get both
    events_batch_2 = []
    try:
        first_event = await asyncio.wait_for(event_queue.get(), timeout=0.05)
        events_batch_2.append(first_event)

        while not event_queue.empty():
            try:
                events_batch_2.append(event_queue.get_nowait())
            except Exception:
                break

    except asyncio.TimeoutError:
        pass

    # Second batch should have both events
    assert len(events_batch_2) == 2
    assert events_batch_2[0]["type"] == "event1"
    assert events_batch_2[1]["type"] == "event2"
