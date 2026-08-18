"""Variable substitution in hook command templates."""

import json
import shlex

from code_puppy.hook_engine.executor import _substitute_variables
from code_puppy.hook_engine.models import EventData


def test_hook_substitution_quotes_file_value():
    event = EventData(
        event_type="PreToolUse",
        tool_name="Edit",
        tool_args={"file_path": "a b; touch x"},
    )

    result = _substitute_variables("process ${file}", event, {})

    assert result == f"process {shlex.quote('a b; touch x')}"


def test_hook_substitution_quotes_tool_input():
    event = EventData(
        event_type="PreToolUse",
        tool_name="Bash",
        tool_args={"command": "$(touch y)"},
    )

    result = _substitute_variables("log ${CLAUDE_TOOL_INPUT}", event, {})

    expected = shlex.quote(json.dumps({"command": "$(touch y)"}))
    assert result == f"log {expected}"


def test_hook_substitution_leaves_plain_value_unchanged():
    event = EventData(
        event_type="PreToolUse",
        tool_name="Edit",
        tool_args={"file_path": "src/main.py"},
    )

    result = _substitute_variables("cat ${file}", event, {})

    assert result == "cat src/main.py"
