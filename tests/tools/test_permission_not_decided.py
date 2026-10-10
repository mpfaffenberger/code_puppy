"""A denial nobody chose must not be reported to the model as a rejection.

Approval backends return ``(False, feedback)`` both when a person selected
Reject and when no decision was made (a timeout, a cancelled or failed
request). ``PermissionNotDecided`` marks the second case so the file tools
stop telling the model "the user explicitly rejected these changes".
"""

from __future__ import annotations

from typing import Any

import pytest

from code_puppy.tools import file_permission_state as fps
from code_puppy.tools.file_modifications import _create_rejection_response


@pytest.fixture
def feedback():
    """Install a provider whose captured feedback the test controls."""
    saved = fps._provider
    state: dict[str, Any] = {"feedback": None}
    fps.register_file_permission_state_provider(
        set_diff_already_shown=lambda shown=True: None,
        was_diff_already_shown=lambda: False,
        clear_diff_shown_flag=lambda: None,
        get_last_user_feedback=lambda: state["feedback"],
        clear_user_feedback=lambda: state.update(feedback=None),
        owner=None,
    )
    yield state
    fps._provider = saved


def test_permission_not_decided_is_still_a_str():
    reason = fps.PermissionNotDecided("The permission request timed out.")

    assert isinstance(reason, str)
    assert reason == "The permission request timed out."


def test_undecided_denial_is_not_reported_as_a_user_rejection(feedback):
    feedback["feedback"] = fps.PermissionNotDecided("The request timed out.")

    result = _create_rejection_response("notes.txt")

    assert result["success"] is False
    assert result["changed"] is False
    assert result["user_rejection"] is False
    assert result["rejection_type"] == "no_user_decision"
    assert result["user_feedback"] is None
    assert "The request timed out." in result["message"]
    assert "USER REJECTED" not in result["message"]
    assert feedback["feedback"] is None  # consumed


def test_explicit_rejection_is_unchanged(feedback):
    feedback["feedback"] = "use the other file"

    result = _create_rejection_response("notes.txt")

    assert result["user_rejection"] is True
    assert result["rejection_type"] == "explicit_user_denial"
    assert result["user_feedback"] == "use the other file"
    assert "USER REJECTED" in result["message"]


def test_rejection_without_feedback_is_unchanged(feedback):
    result = _create_rejection_response("notes.txt")

    assert result["user_rejection"] is True
    assert result["rejection_type"] == "explicit_user_denial"
