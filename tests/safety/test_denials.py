from unittest.mock import AsyncMock, patch

from code_puppy.safety.denials import (
    DenialTracker,
    clear_denial_scope,
    get_denial_tracker,
    record_allowed_action,
    record_denied_action,
    start_denial_scope,
)


def test_tracker_resets_consecutive_on_allowed_action():
    tracker = DenialTracker(session_id="s", consecutive_threshold=3, total_threshold=20)
    assert tracker.deny() is False
    assert tracker.deny() is False
    tracker.allow()
    assert tracker.consecutive == 0
    assert tracker.total == 2


def test_tracker_escalates_at_exact_thresholds():
    tracker = DenialTracker(session_id="s", consecutive_threshold=2, total_threshold=4)
    assert tracker.deny() is False
    assert tracker.deny() is True
    tracker.allow()
    assert tracker.deny() is False
    assert tracker.deny() is True
    assert tracker.deny() is False


async def test_record_denial_prompts_interactive_user_at_threshold():
    start_denial_scope("session")
    tracker = get_denial_tracker()
    tracker.consecutive_threshold = 1
    approval = AsyncMock(return_value=(True, None))
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("code_puppy.messaging.emit_warning"),
        patch("code_puppy.tools.common.get_user_approval_async", approval),
    ):
        assert await record_denied_action("blocked") is True
    approval.assert_awaited_once()
    clear_denial_scope()


async def test_noninteractive_escalation_does_not_prompt():
    start_denial_scope("session")
    tracker = get_denial_tracker()
    tracker.consecutive_threshold = 1
    with (
        patch("sys.stdin.isatty", return_value=False),
        patch("code_puppy.messaging.emit_warning"),
        patch("code_puppy.tools.common.get_user_approval_async") as approval,
    ):
        assert await record_denied_action("blocked") is True
    approval.assert_not_called()


def test_context_helpers_manage_current_tracker():
    tracker = start_denial_scope("abc")
    tracker.consecutive = 2
    record_allowed_action()
    assert get_denial_tracker().session_id == "abc"
    assert get_denial_tracker().consecutive == 0
    clear_denial_scope()
