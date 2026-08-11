"""Regression tests for UTF-8 subprocess pipes on Windows."""

import os
import sys
from unittest.mock import MagicMock, patch

from code_puppy.plugins.customizable_commands import register_callbacks as commands


def test_exec_runner_uses_utf8_stdio_contract():
    """The parent and child explicitly agree on UTF-8 pipe encoding."""
    result = MagicMock(stdout="ok", stderr="", returncode=0)

    with patch.object(commands.subprocess, "run", return_value=result) as run:
        commands._run_exec_directive("echo ok", "pinger")

    kwargs = run.call_args.kwargs
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
    assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
    assert kwargs["env"]["FORCE_COLOR"] == "1"
    assert "PYTHONUTF8" not in kwargs["env"] or kwargs["env"][
        "PYTHONUTF8"
    ] == os.environ.get("PYTHONUTF8")


def test_child_python_emoji_survives_pipe(tmp_path):
    """A real child printing an emoji must not hit the Windows cp1252 trap."""
    script = tmp_path / "emoji.py"
    script.write_text("print('\\U0001F300 flux')\n", encoding="utf-8")
    directive = (
        f"{commands._shell_quote(sys.executable)} {commands._shell_quote(str(script))}"
    )
    lines: list[str] = []

    with (
        patch.object(
            commands,
            "emit_shell_line",
            side_effect=lambda line, **_: lines.append(line),
        ),
        patch.object(commands, "emit_warning") as warning,
    ):
        commands._run_exec_directive(directive, "emoji-test")

    assert any("\U0001f300 flux" in line for line in lines)
    warning.assert_not_called()
