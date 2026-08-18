"""Variable substitution in hook command templates."""

import json
import os
import shlex
import subprocess

import pytest

from code_puppy.hook_engine.executor import _substitute_variables
from code_puppy.hook_engine.models import EventData


def _event(tool_args):
    event = EventData(
        event_type="PreToolUse",
        tool_name="Edit",
        tool_args=tool_args,
    )
    event.context = {"result": "; touch /tmp/x; :"}
    return event


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


def test_hook_substitution_short_form():
    event = EventData(
        event_type="PreToolUse",
        tool_name="Edit",
        tool_args={"file_path": "my file.py"},
    )

    assert _substitute_variables("cat $file", event, {}) == "cat 'my file.py'"
    # A longer variable name must not be partially consumed.
    assert _substitute_variables("cat $filedir", event, {}) == "cat $filedir"


def test_hook_substitution_unknown_placeholder_passthrough():
    event = EventData(
        event_type="PreToolUse",
        tool_name="Edit",
        tool_args={"file_path": "x"},
    )

    result = _substitute_variables("run $HOME/${file}", event, {})

    assert result == "run $HOME/x"


@pytest.mark.parametrize(
    "template,tool_args",
    [
        # Unquoted template: metacharacters must stay literal text.
        ("echo ${file}", {"file_path": "a; touch /tmp/x"}),
        ("echo ${file}", {"file_path": "$(touch /tmp/x)"}),
        # A placeholder inside the author's single quotes: the value cannot
        # close the quote and run trailing commands in the hook's shell.
        ("echo '${file}'", {"file_path": "a'; touch /tmp/x; 'b"}),
        ("echo '${file}'", {"file_path": "a b; touch /tmp/x"}),
        # A value naming another placeholder: substituted values are never
        # re-scanned, so ${result} inside the value cannot resolve.
        ("echo ${file}", {"file_path": "x${result}y"}),
        # Double-quoted template: value metacharacters stay literal.
        ('echo "${file}"', {"file_path": 'a"; touch /tmp/x; echo "b'}),
        ('echo "${file}"', {"file_path": "a`touch /tmp/x`$HOME"}),
        # A $(...) inside double quotes opens a fresh command context; the
        # value must not be able to run trailing commands there.
        (
            'echo "linted $(basename ${file})"',
            {"file_path": "a.py; touch /tmp/x; echo y"},
        ),
        # Backtick command substitution is the same hole.
        (
            'echo "linted `basename ${file}`"',
            {"file_path": "a.py; touch /tmp/x; echo y"},
        ),
        # Nested $( $( ) ) resolves against the innermost context.
        ("echo $(a $(b ${file}) c)", {"file_path": "a; touch /tmp/x"}),
    ],
)
def test_hook_substitution_is_not_injectable(template, tool_args):
    if os.path.exists("/tmp/x"):
        os.remove("/tmp/x")

    substituted = _substitute_variables(template, _event(tool_args), {})

    # The substituted command, run through /bin/sh, must not create the
    # marker file: every splice is inert text in the hook's own shell.
    subprocess.run(
        substituted,
        shell=True,
        capture_output=True,
        env={"PATH": os.environ["PATH"], "HOME": "/tmp"},
    )
    assert not os.path.exists("/tmp/x"), substituted


def test_hook_substitution_windows_uses_cmd_quoting(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    event = EventData(
        event_type="PreToolUse",
        tool_name="Edit",
        tool_args={"file_path": 'a"b & calc'},
    )

    result = _substitute_variables("process ${file}", event, {})

    assert result == 'process "a""b & calc"'


def test_hook_substitution_command_sub_quotes_value():
    injected = "a.py; touch /tmp/x; echo y"
    result = _substitute_variables(
        'echo "linted $(basename ${file})"', _event({"file_path": injected}), {}
    )

    # Inside $(...) the value is re-quoted as an inert single-quoted arg, so
    # the injected `; touch ...` cannot start a new command.
    assert shlex.quote(injected) in result
    assert result == "echo \"linted $(basename 'a.py; touch /tmp/x; echo y')\""


def test_hook_substitution_backtick_quotes_value():
    injected = "a.py; touch /tmp/x; echo y"
    result = _substitute_variables(
        'echo "linted `basename ${file}`"', _event({"file_path": injected}), {}
    )

    assert result == "echo \"linted `basename 'a.py; touch /tmp/x; echo y'`\""


def test_hook_substitution_nested_command_sub_quotes_value():
    injected = "a; touch /tmp/x"
    result = _substitute_variables(
        "echo $(a $(b ${file}) c)", _event({"file_path": injected}), {}
    )

    assert result == "echo $(a $(b 'a; touch /tmp/x') c)"


def test_hook_substitution_plain_double_quote_splices_bare():
    event = EventData(
        event_type="PreToolUse",
        tool_name="Edit",
        tool_args={"file_path": "src/main.py"},
    )

    result = _substitute_variables('echo "linted ${file}"', event, {})

    # A plain double-quoted placeholder still splices the bare value with only
    # double-quote escaping: no stray single quotes are introduced.
    assert result == 'echo "linted src/main.py"'


def test_hook_substitution_windows_quoted_template_single_command(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    event = EventData(
        event_type="PreToolUse",
        tool_name="Edit",
        tool_args={"file_path": "a & calc"},
    )

    result = _substitute_variables('process "${file}"', event, {})

    # The placeholder already sits in the author's quotes, so the value is
    # spliced without new outer quotes: & stays inside one quoted argument
    # (one argv, one command) instead of gaining quote parity and re-arming.
    assert result == 'process "a & calc"'
    assert '""' not in result
