"""Full coverage tests for mcp_/status_tracker.py."""

from datetime import datetime, timedelta

from code_puppy.mcp_.managed_server import ServerState
from code_puppy.mcp_.status_tracker import ServerStatusTracker


class TestServerStatusTracker:
    def test_init(self):
        tracker = ServerStatusTracker()
        assert tracker.get_all_server_ids() == []

    def test_set_and_get_status(self):
        tracker = ServerStatusTracker()
        tracker.set_status("s1", ServerState.RUNNING)
        assert tracker.get_status("s1") == ServerState.RUNNING

    def test_get_status_default(self):
        tracker = ServerStatusTracker()
        assert tracker.get_status("unknown") == ServerState.STOPPED

    def test_set_status_records_state_change(self):
        tracker = ServerStatusTracker()
        tracker.set_status("s1", ServerState.STARTING)
        tracker.set_status("s1", ServerState.RUNNING)
        events = tracker.get_events("s1")
        types = [e.event_type for e in events]
        assert "state_change" in types

    def test_set_and_get_metadata(self):
        tracker = ServerStatusTracker()
        tracker.set_metadata("s1", "version", "1.0")
        assert tracker.get_metadata("s1", "version") == "1.0"
        assert tracker.get_metadata("s1", "nope") is None
        assert tracker.get_metadata("unknown", "key") is None

    def test_record_and_get_events(self):
        tracker = ServerStatusTracker()
        tracker.record_event("s1", "started", {"msg": "ok"})
        tracker.record_event("s1", "health", {})
        events = tracker.get_events("s1", limit=1)
        assert len(events) == 1

    def test_record_event_none_details(self):
        tracker = ServerStatusTracker()
        tracker.record_event("s1", "test", None)
        events = tracker.get_events("s1")
        assert len(events) == 1
        assert events[0].details == {}

    def test_clear_events(self):
        tracker = ServerStatusTracker()
        tracker.record_event("s1", "test", {})
        tracker.clear_events("s1")
        assert tracker.get_events("s1") == []

    def test_clear_events_nonexistent(self):
        tracker = ServerStatusTracker()
        tracker.clear_events("nonexistent")  # should not raise

    def test_record_start_and_stop_time(self):
        tracker = ServerStatusTracker()
        tracker.record_start_time("s1")
        tracker.set_status("s1", ServerState.RUNNING)
        uptime = tracker.get_uptime("s1")
        assert uptime is not None
        assert uptime >= timedelta(0)

    def test_get_uptime_never_started(self):
        tracker = ServerStatusTracker()
        assert tracker.get_uptime("s1") is None

    def test_get_uptime_stopped(self):
        tracker = ServerStatusTracker()
        tracker.record_start_time("s1")
        tracker.set_status("s1", ServerState.STOPPED)
        tracker.record_stop_time("s1")
        uptime = tracker.get_uptime("s1")
        assert uptime is not None

    def test_get_uptime_start_no_valid_stop(self):
        tracker = ServerStatusTracker()
        tracker.record_start_time("s1")
        tracker.set_status("s1", ServerState.STOPPED)
        # No stop time recorded, but not running
        uptime = tracker.get_uptime("s1")
        assert uptime is not None

    def test_get_all_server_ids(self):
        tracker = ServerStatusTracker()
        tracker.set_status("a", ServerState.RUNNING)
        tracker.set_metadata("b", "k", "v")
        tracker.record_event("c", "test", {})
        tracker.record_start_time("d")
        tracker.record_stop_time("e")
        ids = tracker.get_all_server_ids()
        assert "a" in ids
        assert "b" in ids
        assert "c" in ids
        assert "d" in ids
        assert "e" in ids

    def test_get_server_summary(self):
        tracker = ServerStatusTracker()
        tracker.set_status("s1", ServerState.RUNNING)
        tracker.set_metadata("s1", "key", "val")
        tracker.record_start_time("s1")
        summary = tracker.get_server_summary("s1")
        assert summary["server_id"] == "s1"
        assert summary["state"] == "running"
        assert summary["metadata"]["key"] == "val"
        assert summary["last_event_time"] is not None

    def test_get_server_summary_no_events(self):
        tracker = ServerStatusTracker()
        summary = tracker.get_server_summary("empty")
        assert summary["last_event_time"] is None

    def test_cleanup_old_data(self):
        tracker = ServerStatusTracker()
        # Add old event
        from collections import deque

        from code_puppy.mcp_.status_tracker import Event

        old_event = Event(
            timestamp=datetime.now() - timedelta(days=10),
            event_type="old",
            details={},
            server_id="s1",
        )
        tracker._server_events["s1"] = deque([old_event], maxlen=1000)
        tracker.record_event("s1", "new", {})
        tracker.cleanup_old_data(days_to_keep=1)
        events = tracker.get_events("s1")
        assert all(e.event_type != "old" for e in events)

    def test_cleanup_no_events(self):
        tracker = ServerStatusTracker()
        tracker.cleanup_old_data()  # Should not raise
