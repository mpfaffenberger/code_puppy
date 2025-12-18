"""Queue-based telemetry system with background processing.

This module provides a thread-safe, queue-based telemetry system that processes
telemetry events in the background with rate limiting and graceful error handling.
"""

import atexit
import queue
import threading
import time
from typing import Any, Dict, Optional

import httpx

from rich.text import Text

from code_puppy.config import get_puppy_token
from code_puppy.messaging import emit_system_message
from code_puppy.plugins.walmart_specific.urls import Environment, get_telemetry_url


class TelemetryQueue:
    """Thread-safe telemetry queue with background processing.

    This class manages a queue of telemetry events and processes them in a
    background thread with rate limiting and error handling.
    """

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.stop()

    def __init__(self, max_queue_size: int = 1000, rate_limit_delay: float = 0.1):
        """Initialize the telemetry queue.

        Args:
            max_queue_size: Maximum number of telemetry events to queue
            rate_limit_delay: Minimum delay between telemetry requests (seconds)
        """
        self._queue: queue.Queue[Dict[str, Any]] = queue.Queue(maxsize=max_queue_size)
        self._worker_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._rate_limit_delay = rate_limit_delay
        self._last_request_time = 0.0
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the background worker thread."""
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return  # Already running

        self._shutdown_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop, name="TelemetryWorker", daemon=True
        )
        self._worker_thread.start()

    def stop(self, timeout: float = 1.0) -> None:
        """Stop the background worker thread.

        Args:
            timeout: Maximum time to wait for worker to shutdown
        """
        if self._worker_thread is None:
            return

        # Signal shutdown
        self._shutdown_event.set()

        # Try to wake up the worker thread by adding a dummy item
        try:
            self._queue.put_nowait({"_shutdown": True})
        except queue.Full:
            pass  # Queue full, that's ok

        # Wait for graceful shutdown with shorter timeout for faster exit
        self._worker_thread.join(timeout=timeout)

        if self._worker_thread.is_alive():
            emit_system_message(
                "[dim yellow]Telemetry worker thread did not shutdown gracefully[/dim yellow]"
            )
            # Force cleanup
            self._worker_thread = None

    def enqueue_telemetry(self, telemetry_data: Dict[str, Any]) -> bool:
        """Add telemetry data to the processing queue.

        Args:
            telemetry_data: Telemetry payload to send

        Returns:
            True if successfully queued, False if queue is full
        """
        try:
            self._queue.put_nowait(telemetry_data)
            return True
        except queue.Full:
            emit_system_message(
                "[dim yellow]Telemetry queue full, dropping event[/dim yellow]"
            )
            return False

    def _worker_loop(self) -> None:
        """Main worker loop that processes telemetry events."""
        while not self._shutdown_event.is_set():
            try:
                # Wait for telemetry data with timeout to check shutdown event
                telemetry_data = self._queue.get(
                    timeout=0.2
                )  # Even shorter timeout for faster shutdown

                # Check for shutdown signal or dummy shutdown item
                if self._shutdown_event.is_set() or telemetry_data.get("_shutdown"):
                    # Don't put shutdown signal back in queue
                    if not telemetry_data.get("_shutdown"):
                        try:
                            self._queue.put_nowait(telemetry_data)
                        except queue.Full:
                            pass  # Queue full, dropping is acceptable during shutdown
                    self._queue.task_done()
                    break

                # Apply rate limiting (but check for shutdown during sleep)
                if not self._apply_rate_limit_with_shutdown_check():
                    # Shutdown requested during rate limiting
                    try:
                        self._queue.put_nowait(telemetry_data)
                    except queue.Full:
                        pass
                    break

                # Send telemetry
                self._send_telemetry(telemetry_data)

                # Mark task as done
                self._queue.task_done()

            except queue.Empty:
                # Timeout - check shutdown event and continue
                continue
            except Exception as e:
                emit_system_message(
                    f"[dim red]Telemetry worker error: {str(e)[:100]}[/dim red]"
                )
                # Mark task as done even on error to prevent hanging
                try:
                    self._queue.task_done()
                except ValueError:
                    pass  # task_done() called more times than there were items

    def _apply_rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        with self._lock:
            current_time = time.time()
            time_since_last = current_time - self._last_request_time

            if time_since_last < self._rate_limit_delay:
                sleep_time = self._rate_limit_delay - time_since_last
                time.sleep(sleep_time)

            self._last_request_time = time.time()

    def _apply_rate_limit_with_shutdown_check(self) -> bool:
        """Apply rate limiting while checking for shutdown events.

        Returns:
            True if rate limiting completed normally, False if shutdown requested
        """
        with self._lock:
            current_time = time.time()
            time_since_last = current_time - self._last_request_time

            if time_since_last < self._rate_limit_delay:
                sleep_time = self._rate_limit_delay - time_since_last

                # Sleep in small increments to check for shutdown
                sleep_increment = 0.05  # 50ms increments
                while sleep_time > 0 and not self._shutdown_event.is_set():
                    actual_sleep = min(sleep_increment, sleep_time)
                    time.sleep(actual_sleep)
                    sleep_time -= actual_sleep

                # If shutdown was requested during sleep, return False
                if self._shutdown_event.is_set():
                    return False

            self._last_request_time = time.time()
            return True

    def _send_telemetry(self, telemetry_data: Dict[str, Any]) -> None:
        """Send telemetry data to the endpoint.

        Args:
            telemetry_data: Telemetry payload to send
        """
        # Check for shutdown before making network request
        if self._shutdown_event.is_set():
            return

        try:
            # Use even shorter timeout during shutdown for faster exit
            timeout_val = 2.0 if self._shutdown_event.is_set() else 5.0
            with httpx.Client(timeout=timeout_val, verify=False) as client:
                response = client.post(
                    get_telemetry_url(Environment.STAGE),
                    json=telemetry_data,
                    headers={
                        "Content-Type": "application/json",
                        "X-Api-Key": get_puppy_token(),
                    },
                )

                if response.status_code != 200:
                    emit_system_message(
                        Text.from_markup(
                            f"[dim yellow]Telemetry upload failed: {response.status_code}[/dim yellow]"
                        )
                    )

        except httpx.TimeoutException:
            emit_system_message(
                Text.from_markup("[dim yellow]Telemetry request timed out[/dim yellow]")
            )
        except httpx.RequestError as e:
            emit_system_message(
                Text.from_markup(
                    f"[dim yellow]Telemetry request error: {str(e)[:50]}[/dim yellow]"
                )
            )
        except Exception as e:
            emit_system_message(
                Text.from_markup(
                    f"[dim red]Unexpected telemetry error: {str(e)[:50]}[/dim red]"
                )
            )

    def get_queue_size(self) -> int:
        """Get the current number of items in the queue."""
        return self._queue.qsize()

    def is_running(self) -> bool:
        """Check if the worker thread is running."""
        return (
            self._worker_thread is not None
            and self._worker_thread.is_alive()
            and not self._shutdown_event.is_set()
        )

    def force_shutdown(self) -> None:
        """Force immediate shutdown of the telemetry queue.

        This method can be called from signal handlers or other shutdown scenarios
        to immediately stop telemetry processing.
        """
        self._shutdown_event.set()

        # Try to wake up the worker thread
        try:
            self._queue.put_nowait({"_shutdown": True})
        except queue.Full:
            pass


# Global telemetry queue instance
_telemetry_queue: Optional[TelemetryQueue] = None


def get_telemetry_queue() -> TelemetryQueue:
    """Get the global telemetry queue instance.

    Returns:
        The global TelemetryQueue instance
    """
    global _telemetry_queue

    if _telemetry_queue is None:
        _telemetry_queue = TelemetryQueue(
            max_queue_size=1000,
            rate_limit_delay=0.1,  # 100ms between requests
        )
        _telemetry_queue.start()

    return _telemetry_queue


def shutdown_telemetry_queue() -> None:
    """Shutdown the global telemetry queue."""
    global _telemetry_queue

    if _telemetry_queue is not None:
        # Force immediate shutdown for faster exit
        _telemetry_queue.force_shutdown()
        _telemetry_queue.stop(timeout=0.5)  # Shorter timeout
        _telemetry_queue = None


def force_shutdown_telemetry_queue() -> None:
    """Force immediate shutdown of the global telemetry queue.

    This is intended for use in signal handlers where we need
    to stop telemetry processing immediately.
    """
    global _telemetry_queue

    if _telemetry_queue is not None:
        _telemetry_queue.force_shutdown()


# Register cleanup function to ensure graceful shutdown
atexit.register(shutdown_telemetry_queue)
