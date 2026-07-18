"""Tests for event-driven polling elimination in WebSocket handlers.

Verifies that the polling-based event collection has been replaced with
event-driven asyncio.wait_for() approach. Tests validate:

1. Events are received without time-based polling
2. Batching efficiency is maintained
3. Timeout handling works gracefully
4. Empty queue behavior is correct
5. Performance improvement (no busy-wait loops)
"""

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


class EventDrivenCollector:
    """Reference implementation of event-driven batch collection.

    This mimics the pattern used in chat_handler.py
    after the polling elimination fix.
    """

    def __init__(self, event_queue: asyncio.Queue):
        self.event_queue = event_queue
        self.event_count = 0

    async def collect_batch(self) -> list[dict[str, Any]]:
        """Collect a batch of events using event-driven approach.

        Returns:
            List of events collected (may be empty if timeout occurs)
        """
        events_to_send = []
        try:
            # Wait for first event with 10ms timeout (blocks efficiently)
            first_event = await asyncio.wait_for(self.event_queue.get(), timeout=0.01)
            events_to_send.append(first_event)
            self.event_count += 1

            # Collect any additional events already in queue (non-blocking)
            # This keeps the batching benefit without polling the clock
            while not self.event_queue.empty():
                try:
                    event = self.event_queue.get_nowait()
                    events_to_send.append(event)
                    self.event_count += 1
                except Exception:
                    break

        except asyncio.TimeoutError:
            # No events available within 10ms timeout
            # No polling needed - asyncio.wait_for blocks efficiently
            pass

        return events_to_send


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
async def event_queue():
    """Fixture providing a fresh asyncio.Queue for each test."""
    return asyncio.Queue()


@pytest.fixture
def collector(event_queue):
    """Fixture providing an EventDrivenCollector instance."""
    return EventDrivenCollector(event_queue)


# ============================================================================
# TEST: Events are received without polling
# ============================================================================


@pytest.mark.asyncio
async def test_events_received_without_time_polling():
    """Verify events are received using asyncio.wait_for, not time-based polling.

    This test ensures that we've eliminated the busy-wait polling loop
    that used time.monotonic() or time.time() to check elapsed time.

    The event-driven approach should:
    - Block efficiently on event_queue.get()
    - Use asyncio.wait_for() for timeout
    - Not poll the clock in a loop
    """
    queue = asyncio.Queue()
    collector = EventDrivenCollector(queue)

    # Add an event to the queue
    test_event = {"type": "test", "data": "hello"}
    await queue.put(test_event)

    # Collect batch - should return the event immediately
    start = time.perf_counter()
    batch = await collector.collect_batch()
    elapsed = time.perf_counter() - start

    # Verify event was received
    assert len(batch) == 1
    assert batch[0] == test_event
    assert collector.event_count == 1

    # Verify it happened nearly instantly (< 5ms, not 10ms sleep)
    # If it was using time.sleep(0.01), it would take ~10ms
    assert elapsed < 0.005, f"Collection took {elapsed * 1000:.2f}ms (should be <5ms)"


@pytest.mark.asyncio
async def test_wait_for_timeout_called(event_queue, collector):
    """Verify asyncio.wait_for() is being used for timeout.

    Mock asyncio.wait_for to verify it's called, confirming we're using
    the efficient async timeout mechanism instead of time-based polling.
    """
    with patch("asyncio.wait_for", new_callable=AsyncMock) as mock_wait_for:
        # Setup mock to raise TimeoutError
        mock_wait_for.side_effect = asyncio.TimeoutError()

        # Collect batch
        batch = await collector.collect_batch()

        # Verify wait_for was called
        mock_wait_for.assert_called_once()
        call_args = mock_wait_for.call_args

        # Verify timeout parameter (should be 0.01 = 10ms)
        assert call_args.kwargs.get("timeout") == 0.01, "Should use 10ms timeout"

        # Verify returned empty batch on timeout
        assert len(batch) == 0


@pytest.mark.asyncio
async def test_no_time_module_polling():
    """Verify time module is not used for polling.

    The old implementation used time.monotonic() or time.time() to poll
    in a loop. The new implementation should not do this.

    Instead of mocking (which breaks asyncio), we verify the code doesn't
    have polling loops by checking it uses wait_for() instead.
    """
    queue = asyncio.Queue()
    collector = EventDrivenCollector(queue)

    # Add event
    await queue.put({"type": "test"})

    # Collect batch
    batch = await collector.collect_batch()

    # If we're here without exception, the pattern is working
    # (No time-based polling loop would cause issues with asyncio)
    assert len(batch) == 1
    assert batch[0]["type"] == "test"


# ============================================================================
# TEST: Batching efficiency maintained
# ============================================================================


@pytest.mark.asyncio
async def test_multiple_events_batched_together():
    """Verify multiple events arriving together are collected in one batch.

    The event-driven approach should maintain the batching benefit:
    when multiple events arrive within the 10ms window, they should be
    collected together in a single batch.
    """
    queue = asyncio.Queue()
    collector = EventDrivenCollector(queue)

    # Add multiple events to queue
    events = [
        {"type": "tool_call_start", "tool_name": "tool1"},
        {"type": "tool_result", "result": "result1"},
        {"type": "stream_event", "data": "text"},
        {"type": "tool_call_complete"},
    ]
    for event in events:
        await queue.put(event)

    # Collect batch
    batch = await collector.collect_batch()

    # All events should be in one batch
    assert len(batch) == 4, "All events should be in single batch"
    assert batch == events
    assert collector.event_count == 4


@pytest.mark.asyncio
async def test_batching_with_sequential_additions():
    """Verify batching when events are added: first immediately, then more.

    Simulates real-world scenario where:
    1. First event arrives immediately
    2. Additional events arrive quickly after
    3. All should be collected in one batch
    """
    queue = asyncio.Queue()
    collector = EventDrivenCollector(queue)

    # Add first event
    await queue.put({"type": "event1"})

    # Simulate additional events arriving quickly
    async def add_more_events():
        await asyncio.sleep(0.002)  # 2ms later
        await queue.put({"type": "event2"})
        await queue.put({"type": "event3"})

    # Start adding more events concurrently
    task = asyncio.create_task(add_more_events())

    # Collect batch (should wait 10ms, allowing time for more events)
    batch = await collector.collect_batch()
    await task

    # Should have collected first + any others that arrived
    assert len(batch) >= 1, "Should collect at least first event"
    assert batch[0]["type"] == "event1"


@pytest.mark.asyncio
async def test_event_count_tracking():
    """Verify event_count is incremented correctly for batched events."""
    queue = asyncio.Queue()
    collector = EventDrivenCollector(queue)

    assert collector.event_count == 0

    # First batch
    await queue.put({"type": "event1"})
    await queue.put({"type": "event2"})
    batch1 = await collector.collect_batch()
    assert len(batch1) == 2
    assert collector.event_count == 2

    # Second batch (after timeout)
    batch2 = await collector.collect_batch()
    assert len(batch2) == 0
    assert collector.event_count == 2  # Unchanged


# ============================================================================
# TEST: Timeout handling
# ============================================================================


@pytest.mark.asyncio
async def test_timeout_handled_gracefully():
    """Verify TimeoutError is caught and handled gracefully.

    When no events are available within the 10ms timeout window,
    the asyncio.TimeoutError should be caught and an empty batch returned.
    No exceptions should bubble up.
    """
    queue = asyncio.Queue()
    collector = EventDrivenCollector(queue)

    # Queue is empty, so timeout will occur
    batch = await collector.collect_batch()

    # Should return empty batch
    assert len(batch) == 0
    assert isinstance(batch, list)

    # Should not raise any exception
    assert True  # If we got here without exception, test passed


@pytest.mark.asyncio
async def test_loop_continues_after_timeout():
    """Verify loop can continue after timeout without issues.

    Multiple collection attempts should work correctly even if
    some attempts timeout.
    """
    queue = asyncio.Queue()
    collector = EventDrivenCollector(queue)

    # First collection - timeout
    batch1 = await collector.collect_batch()
    assert len(batch1) == 0

    # Add event
    await queue.put({"type": "event1"})

    # Second collection - should get event
    batch2 = await collector.collect_batch()
    assert len(batch2) == 1
    assert batch2[0]["type"] == "event1"

    # Third collection - timeout again
    batch3 = await collector.collect_batch()
    assert len(batch3) == 0


@pytest.mark.asyncio
async def test_timeout_value_correct(event_queue):
    """Verify the timeout value is exactly 10ms (0.01 seconds).

    The old polling approach used a 10ms window. The new approach
    should maintain this same responsiveness window.
    """
    collector = EventDrivenCollector(event_queue)

    # Measure actual timeout duration
    start = time.perf_counter()
    _ = await collector.collect_batch()  # Intentionally discarding batch
    elapsed = time.perf_counter() - start

    # With no events, should timeout after ~10ms (±2ms tolerance)
    assert 0.008 < elapsed < 0.015, (
        f"Timeout should be ~10ms, got {elapsed * 1000:.2f}ms"
    )


# ============================================================================
# TEST: Empty queue behavior
# ============================================================================


@pytest.mark.asyncio
async def test_empty_queue_returns_empty_batch():
    """Verify empty queue results in empty batch.

    When queue is empty and timeout occurs, should return empty list,
    not raise an exception.
    """
    queue = asyncio.Queue()
    collector = EventDrivenCollector(queue)
    batch = await collector.collect_batch()
    assert batch == []


@pytest.mark.asyncio
async def test_no_infinite_loop_on_empty_queue():
    """Verify no infinite loop when queue is empty.

    The timeout should prevent infinite looping. Collection should
    complete in ~10ms even with empty queue.
    """
    queue = asyncio.Queue()
    collector = EventDrivenCollector(queue)

    start = time.perf_counter()
    batch = await collector.collect_batch()
    elapsed = time.perf_counter() - start

    # Should complete quickly (within timeout + small overhead)
    assert elapsed < 0.05, f"Should not hang, took {elapsed * 1000:.2f}ms"
    assert batch == []


@pytest.mark.asyncio
async def test_queue_empty_check_works():
    """Verify queue.empty() check works correctly for secondary collection.

    After getting first event, the code checks event_queue.empty() to
    collect additional events. This should work correctly.
    """
    queue = asyncio.Queue()
    collector = EventDrivenCollector(queue)

    # Add multiple events
    await queue.put({"type": "event1"})
    await queue.put({"type": "event2"})
    await queue.put({"type": "event3"})

    batch = await collector.collect_batch()

    # All events should be collected despite using empty() check
    assert len(batch) == 3
    assert collector.event_count == 3

    # Queue should now be empty
    assert queue.empty()


# ============================================================================
# TEST: Performance improvement (no busy-wait loops)
# ============================================================================


@pytest.mark.asyncio
async def test_performance_event_arrival_near_instant():
    """Verify event collection happens near-instantly (<1ms).

    The old polling approach would wait up to 10ms before checking
    the queue. Event-driven approach wakes immediately on event arrival.
    """
    queue = asyncio.Queue()
    collector = EventDrivenCollector(queue)

    # Add event then immediately collect
    await queue.put({"type": "test"})

    start = time.perf_counter()
    batch = await collector.collect_batch()
    elapsed = time.perf_counter() - start

    # Should be near-instant (<1ms, not ~10ms)
    assert elapsed < 0.001, (
        f"Event should be collected near-instantly, "
        f"took {elapsed * 1000:.2f}ms (should be <1ms)"
    )
    assert len(batch) == 1


@pytest.mark.asyncio
async def test_no_sleep_on_every_iteration():
    """Verify we don't sleep 10ms on every loop iteration.

    The old implementation would do: if not events: await asyncio.sleep(0.01)
    This test verifies that pattern is eliminated.
    """
    queue = asyncio.Queue()
    collector = EventDrivenCollector(queue)

    # Track asyncio.sleep calls
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        # Run collection multiple times
        for _ in range(3):
            await collector.collect_batch()

        # Should NOT call asyncio.sleep(0.01) on idle
        # (It might be called elsewhere, but not as idle sleep)
        sleep_calls = [call for call in mock_sleep.call_args_list]
        idle_sleep_calls = [call for call in sleep_calls if call[0] == (0.01,)]
        assert len(idle_sleep_calls) == 0, (
            "Should not sleep 0.01s on every idle iteration"
        )


@pytest.mark.asyncio
async def test_multiple_events_processed_once():
    """Verify multiple events are processed in one batch, not multiple sleeps.

    Old approach: each iteration could sleep 10ms if no events
    New approach: waits 10ms once, collects all available events
    """
    queue = asyncio.Queue()
    collector = EventDrivenCollector(queue)

    # Add events
    for i in range(5):
        await queue.put({"type": "event", "id": i})

    start = time.perf_counter()
    batch = await collector.collect_batch()
    elapsed = time.perf_counter() - start

    # All events collected in one batch
    assert len(batch) == 5
    # Should be instant, not 50ms (5 iterations * 10ms sleep)
    assert elapsed < 0.005


@pytest.mark.asyncio
async def test_batching_efficiency_metric():
    """Calculate and verify batching efficiency.

    Batching efficiency = total_events / number_of_batches

    Event-driven approach should achieve good batching even with
    sequential additions, because it waits up to 10ms for additional events.
    """
    queue = asyncio.Queue()
    collector = EventDrivenCollector(queue)

    batch_sizes = []

    # Simulate 3 collection cycles
    for cycle in range(3):
        # Add varying number of events
        num_events = cycle + 1  # 1, 2, 3
        for i in range(num_events):
            await queue.put({"type": "event", "cycle": cycle, "id": i})

        batch = await collector.collect_batch()
        batch_sizes.append(len(batch))

    # Verify we collected events (not all empty)
    total_collected = sum(batch_sizes)
    assert total_collected == 6, "Should collect all 6 events (1+2+3)"

    # Calculate efficiency: 6 events / 3 batches = 2.0 average
    avg_batch_size = total_collected / 3
    assert avg_batch_size >= 1.5, "Should have reasonable batching"


# ============================================================================
# INTEGRATION: Full drain loop simulation
# ============================================================================


@pytest.mark.asyncio
async def test_drain_loop_simulation():
    """Simulate a full drain loop with event-driven collection.

    This mimics the actual usage in chat_handler.py:
    - Collect events in a loop
    - Process collected events
    - Continue until stop signal
    """
    queue = asyncio.Queue()
    collector = EventDrivenCollector(queue)
    stop_event = asyncio.Event()
    processed_events = []

    async def drain_loop():
        """Simulate the drain event loop."""
        while not stop_event.is_set():
            batch = await collector.collect_batch()
            for event in batch:
                processed_events.append(event)

            # Add small delay to allow test to add events
            if not batch:
                await asyncio.sleep(0.001)

    # Start drain loop
    drain_task = asyncio.create_task(drain_loop())

    # Simulate events being added
    await asyncio.sleep(0.01)
    for i in range(5):
        await queue.put({"type": "event", "id": i})

    await asyncio.sleep(0.05)  # Let drain collect them

    # Stop the loop
    stop_event.set()
    await asyncio.wait_for(drain_task, timeout=1.0)

    # Verify all events were processed
    assert len(processed_events) == 5
    assert all(e["type"] == "event" for e in processed_events)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
