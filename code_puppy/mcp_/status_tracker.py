"""
Server Status Tracker for monitoring MCP server runtime status.

This module provides the ServerStatusTracker class that tracks the runtime
status of MCP servers including state, metrics, and events.
"""

import logging
import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .managed_server import ServerState

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Data class representing a server event."""

    timestamp: datetime
    event_type: str  # "started", "stopped", "error", "health_check", etc.
    details: Dict
    server_id: str


class ServerStatusTracker:
    """
    Tracks the runtime status of MCP servers including state, metrics, and events.

    This class provides in-memory storage for server states, metadata, and events
    with thread-safe operations using locks. Events are stored using collections.deque
    for automatic size limiting.

    Example usage:
        tracker = ServerStatusTracker()
        tracker.set_status("server1", ServerState.RUNNING)
        tracker.record_event("server1", "started", {"message": "Server started successfully"})
        events = tracker.get_events("server1", limit=10)
    """

    def __init__(self):
        """Initialize the status tracker with thread-safe data structures."""
        # Thread safety lock
        self._lock = threading.RLock()

        # Server states (server_id -> ServerState)
        self._server_states: Dict[str, ServerState] = {}

        # Server metadata (server_id -> key -> value)
        self._server_metadata: Dict[str, Dict[str, Any]] = defaultdict(dict)

        # Server events (server_id -> deque of events)
        # Using deque with maxlen for automatic size limiting
        self._server_events: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

        # Server timing information
        self._start_times: Dict[str, datetime] = {}
        self._stop_times: Dict[str, datetime] = {}

        logger.info("ServerStatusTracker initialized")

    def set_status(self, server_id: str, state: ServerState) -> None:
        """
        Set the current state of a server.

        Args:
            server_id: Unique identifier for the server
            state: New server state
        """
        with self._lock:
            old_state = self._server_states.get(server_id)
            self._server_states[server_id] = state

            # Record state change event
            self.record_event(
                server_id,
                "state_change",
                {
                    "old_state": old_state.value if old_state else None,
                    "new_state": state.value,
                    "message": f"State changed from {old_state.value if old_state else 'unknown'} to {state.value}",
                },
            )

            logger.debug(f"Server {server_id} state changed: {old_state} -> {state}")

    def get_status(self, server_id: str) -> ServerState:
        """
        Get the current state of a server.

        Args:
            server_id: Unique identifier for the server

        Returns:
            Current server state, defaults to STOPPED if not found
        """
        with self._lock:
            return self._server_states.get(server_id, ServerState.STOPPED)

    def set_metadata(self, server_id: str, key: str, value: Any) -> None:
        """
        Set metadata value for a server.

        Args:
            server_id: Unique identifier for the server
            key: Metadata key
            value: Metadata value (can be any type)
        """
        with self._lock:
            if server_id not in self._server_metadata:
                self._server_metadata[server_id] = {}

            old_value = self._server_metadata[server_id].get(key)
            self._server_metadata[server_id][key] = value

            # Record metadata change event
            self.record_event(
                server_id,
                "metadata_update",
                {
                    "key": key,
                    "old_value": old_value,
                    "new_value": value,
                    "message": f"Metadata '{key}' updated",
                },
            )

            logger.debug(f"Server {server_id} metadata updated: {key} = {value}")

    def get_metadata(self, server_id: str, key: str) -> Any:
        """
        Get metadata value for a server.

        Args:
            server_id: Unique identifier for the server
            key: Metadata key

        Returns:
            Metadata value or None if not found
        """
        with self._lock:
            return self._server_metadata.get(server_id, {}).get(key)

    def record_event(self, server_id: str, event_type: str, details: Dict) -> None:
        """
        Record an event for a server.

        Args:
            server_id: Unique identifier for the server
            event_type: Type of event (e.g., "started", "stopped", "error", "health_check")
            details: Dictionary containing event details
        """
        with self._lock:
            event = Event(
                timestamp=datetime.now(),
                event_type=event_type,
                details=details.copy()
                if details
                else {},  # Copy to prevent modification
                server_id=server_id,
            )

            # Add to deque (automatically handles size limiting)
            self._server_events[server_id].append(event)

            logger.debug(f"Event recorded for server {server_id}: {event_type}")

    def get_events(self, server_id: str, limit: int = 100) -> List[Event]:
        """
        Get recent events for a server.

        Args:
            server_id: Unique identifier for the server
            limit: Maximum number of events to return (default: 100)

        Returns:
            List of events ordered by timestamp (most recent first)
        """
        with self._lock:
            events = list(self._server_events.get(server_id, deque()))

            # Return most recent events first, limited by count
            events.reverse()  # Most recent first
            return events[:limit]

    def clear_events(self, server_id: str) -> None:
        """
        Clear all events for a server.

        Args:
            server_id: Unique identifier for the server
        """
        with self._lock:
            if server_id in self._server_events:
                self._server_events[server_id].clear()
                logger.info(f"Cleared all events for server: {server_id}")

    def get_uptime(self, server_id: str) -> Optional[timedelta]:
        """
        Calculate uptime for a server based on start/stop times.

        Args:
            server_id: Unique identifier for the server

        Returns:
            Server uptime as timedelta, or None if server never started
        """
        with self._lock:
            start_time = self._start_times.get(server_id)
            if start_time is None:
                return None

            # If server is currently running, calculate from start time to now
            current_state = self.get_status(server_id)
            if current_state == ServerState.RUNNING:
                return datetime.now() - start_time

            # If server is stopped, calculate from start to stop time
            stop_time = self._stop_times.get(server_id)
            if stop_time is not None and stop_time > start_time:
                return stop_time - start_time

            # If we have start time but no valid stop time, assume currently running
            return datetime.now() - start_time

    def record_start_time(self, server_id: str) -> None:
        """
        Record the start time for a server.

        Args:
            server_id: Unique identifier for the server
        """
        with self._lock:
            start_time = datetime.now()
            self._start_times[server_id] = start_time

            # Record start event
            self.record_event(
                server_id,
                "started",
                {"start_time": start_time.isoformat(), "message": "Server started"},
            )

            logger.info(f"Recorded start time for server: {server_id}")

    def record_stop_time(self, server_id: str) -> None:
        """
        Record the stop time for a server.

        Args:
            server_id: Unique identifier for the server
        """
        with self._lock:
            stop_time = datetime.now()
            self._stop_times[server_id] = stop_time

            # Calculate final uptime
            start_time = self._start_times.get(server_id)
            uptime = None
            if start_time:
                uptime = stop_time - start_time

            # Record stop event
            self.record_event(
                server_id,
                "stopped",
                {
                    "stop_time": stop_time.isoformat(),
                    "uptime_seconds": uptime.total_seconds() if uptime else None,
                    "message": "Server stopped",
                },
            )

            logger.info(f"Recorded stop time for server: {server_id}")

    def get_all_server_ids(self) -> List[str]:
        """
        Get all server IDs that have been tracked.

        Returns:
            List of all server IDs
        """
        with self._lock:
            # Combine all sources of server IDs
            all_ids = set()
            all_ids.update(self._server_states.keys())
            all_ids.update(self._server_metadata.keys())
            all_ids.update(self._server_events.keys())
            all_ids.update(self._start_times.keys())
            all_ids.update(self._stop_times.keys())

            return sorted(list(all_ids))

    def get_server_summary(self, server_id: str) -> Dict[str, Any]:
        """
        Get comprehensive summary of server status.

        Args:
            server_id: Unique identifier for the server

        Returns:
            Dictionary containing current state, metadata, recent events, and uptime
        """
        with self._lock:
            return {
                "server_id": server_id,
                "state": self.get_status(server_id).value,
                "metadata": self._server_metadata.get(server_id, {}).copy(),
                "recent_events_count": len(self._server_events.get(server_id, deque())),
                "uptime": self.get_uptime(server_id),
                "start_time": self._start_times.get(server_id),
                "stop_time": self._stop_times.get(server_id),
                "last_event_time": (
                    list(self._server_events.get(server_id, deque()))[-1].timestamp
                    if server_id in self._server_events
                    and len(self._server_events[server_id]) > 0
                    else None
                ),
            }

    def cleanup_old_data(self, days_to_keep: int = 7) -> None:
        """
        Clean up old data to prevent memory bloat.

        Args:
            days_to_keep: Number of days of data to keep (default: 7)
        """
        cutoff_time = datetime.now() - timedelta(days=days_to_keep)

        with self._lock:
            cleaned_servers = []

            for server_id in list(self._server_events.keys()):
                events = self._server_events[server_id]
                if events:
                    # Filter out old events
                    original_count = len(events)
                    # Convert to list, filter, then create new deque
                    filtered_events = [
                        event for event in events if event.timestamp >= cutoff_time
                    ]

                    # Replace the deque with filtered events
                    self._server_events[server_id] = deque(filtered_events, maxlen=1000)

                    if len(filtered_events) < original_count:
                        cleaned_servers.append(server_id)

            if cleaned_servers:
                logger.info(f"Cleaned old events for {len(cleaned_servers)} servers")
