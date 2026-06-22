from code_puppy.messaging.spinner.spinner_base import SpinnerBase
from code_puppy.plugins.spinner_activity.register_callbacks import _activity_label


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
