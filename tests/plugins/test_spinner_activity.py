import asyncio

import pytest

from code_puppy.messaging.spinner.spinner_base import SpinnerBase
from code_puppy.plugins.spinner_activity import register_callbacks as rc
from code_puppy.plugins.spinner_activity.register_callbacks import _activity_label


@pytest.fixture(autouse=True)
def _reset_spinner_state(monkeypatch):
    """Reset SpinnerBase + disable compact-steps so these tests exercise
    the legacy activity-label path (no ledger prefixing)."""
    monkeypatch.setattr(
        "code_puppy.plugins.spinner_activity.register_callbacks.get_compact_steps",
        lambda: False,
    )
    SpinnerBase.clear_activity()
    SpinnerBase.set_ledger_active(False)
    yield
    SpinnerBase.clear_activity()
    SpinnerBase.set_ledger_active(False)


def test_pre_tool_call_sets_activity_label():
    """Option B: ``_on_pre_tool_call`` just sets the activity label and
    pushes a ledger row. The old ``resume_all_spinners`` call is gone —
    one ``Live`` owns the turn and Rich coordinates above-prints, so
    there's nothing to resume."""
    asyncio.run(rc._on_pre_tool_call("read_file", {"file_path": "a.py"}))
    assert SpinnerBase.get_activity() == "Reading a.py"
    asyncio.run(rc._on_post_tool_call("read_file", {}, None, 1.0))
    assert SpinnerBase.get_activity() == ""


def test_labels_are_concise_and_tool_aware():
    assert _activity_label("agent_run_shell_command", {"command": "npm test"}) == (
        "Running: npm test"
    )
    assert _activity_label("read_file", {"file_path": "src/app.py"}) == (
        "Reading src/app.py"
    )
    assert _activity_label("grep", {"search_string": "TODO"}) == "Searching TODO"
    assert _activity_label("replace_in_file", {"path": "x.py"}) == "Editing x.py"
    assert _activity_label("invoke_agent", {"agent_name": "qa"}) == "Delegating to qa"
    assert _activity_label("mystery_tool", {}) == "Running mystery_tool"


def test_long_args_are_truncated():
    label = _activity_label("agent_run_shell_command", {"command": "x" * 200})
    assert label.endswith("…")
    assert len(label) < 80


def test_activity_roundtrip_on_spinner_base():
    SpinnerBase.clear_activity()
    assert SpinnerBase.get_activity() == ""
    SpinnerBase.set_activity("Running: pytest")
    assert SpinnerBase.get_activity() == "Running: pytest"
    SpinnerBase.clear_activity()
    assert SpinnerBase.get_activity() == ""
