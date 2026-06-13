"""`/statusline` command — scaffold, enable, inspect the status line.

Mirrors Claude Code's ``/statusline``. Rather than calling the model, this
scaffolds a ready-to-edit starter script (Claude Code generates one via the
agent; we hand you a working template you can tweak immediately).

Subcommands:
    /statusline                 Show current status + quick help
    /statusline init            Write a starter ~/.code_puppy/statusline.sh,
                                point config at it, and enable
    /statusline on | off        Enable / disable rendering
    /statusline show            Run the command once and preview its output
    /statusline json            Print the JSON payload your script receives
"""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any, List, Optional, Tuple

from code_puppy.messaging import emit_info, emit_success, emit_warning

from . import config, payload, runner

_COMMAND_NAME = "statusline"

_STARTER_SCRIPT = """\
#!/usr/bin/env bash
# Code Puppy status line. Receives session JSON on stdin; prints one line.
# In the default "replace" mode this line REPLACES the default prompt content
# (so include a name/emoji if you want one). Edit freely.
# Requires `jq` for the parsing below (or parse however you like).
input=$(cat)

puppy=$(printf '%s' "$input" | jq -r '.puppy_name // "code-puppy"')
model=$(printf '%s' "$input" | jq -r '.model.display_name // "model"')
dir=$(printf '%s' "$input" | jq -r '.workspace.current_dir // .cwd // ""')
branch=$(printf '%s' "$input" | jq -r '.workspace.git_branch // empty')
ind=$(printf '%s' "$input" | jq -r '.context_window.indicator // ""')
pct=$(printf '%s' "$input" | jq -r '.context_window.used_percentage // 0')
tps=$(printf '%s' "$input" | jq -r '.tokens_per_second // 0')

line="\\033[1m🐶 $puppy\\033[0m"
[ -n "$ind" ] && line="$line $ind"
line="$line \\033[36m[$model]\\033[0m \\033[2m$(basename "$dir")\\033[0m"
[ -n "$branch" ] && line="$line \\033[35m($branch)\\033[0m"
line="$line \\033[33m${pct}%ctx\\033[0m"
# Show t/s only while generating.
awk "BEGIN{exit !($tps>0)}" && line="$line \\033[32m${tps} t/s\\033[0m"

printf '%b' "$line"
"""


def statusline_command_help() -> List[Tuple[str, str]]:
    return [
        (_COMMAND_NAME, "Customize the bottom status line (init/on/off/show/json)"),
    ]


def _default_script_path() -> Path:
    return Path.home() / ".code_puppy" / "statusline.sh"


def _status_text() -> str:
    enabled = "ON" if config.is_enabled() else "OFF"
    cmd = config.get_command() or "(none)"
    return (
        f"Status line: {enabled}   mode: {config.get_mode()}\n"
        f"  command: {cmd}\n"
        f"  refresh: {config.get_refresh_ms()}ms   timeout: {config.get_timeout_ms()}ms\n"
        "  Subcommands: init | on | off | mode <replace|above|newline> | show | json"
    )


def _do_init() -> None:
    path = _default_script_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_STARTER_SCRIPT, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    config.set_command(str(path))
    config.set_enabled(True)
    runner.reset_cache()
    emit_success(f"Wrote starter status line script: {path}")
    emit_info("Enabled. Edit that file to customize. Preview with /statusline show.")
    if not _has_jq():
        emit_warning(
            "Note: the starter script uses `jq` (not found on PATH). Install jq "
            "or rewrite the script to parse JSON another way."
        )


def _has_jq() -> bool:
    from shutil import which

    return which("jq") is not None


def handle_statusline_command(command: str, name: str) -> Optional[Any]:
    if name != _COMMAND_NAME:
        return None

    tokens = command.split()
    sub = tokens[1].strip().lower() if len(tokens) > 1 else "status"

    if sub in ("status", ""):
        emit_info(_status_text())
        return True
    if sub == "init":
        _do_init()
        return True
    if sub == "on":
        if not config.get_command():
            emit_warning(
                "No command set. Run /statusline init first, or set "
                "statusline_command via /set."
            )
            return True
        config.set_enabled(True)
        runner.reset_cache()
        emit_success("Status line enabled.")
        return True
    if sub == "off":
        config.set_enabled(False)
        emit_warning("Status line disabled.")
        return True
    if sub == "mode":
        mode = tokens[2].strip().lower() if len(tokens) > 2 else ""
        if mode not in ("replace", "above", "newline"):
            emit_warning("Usage: /statusline mode <replace|above|newline>")
            emit_info(
                "  replace = your line REPLACES the default prompt (no duplicate)\n"
                "  above   = your line sits on its own line above the default prompt\n"
                "  newline = like replace, but >>> drops to its own line below"
            )
            return True
        config.set_mode(mode)
        emit_success(f"Status line mode set to '{mode}'.")
        return True
    if sub == "show":
        if not config.get_command():
            emit_warning("No command set. Run /statusline init first.")
            return True
        out = runner.run_once_sync()
        emit_info("Status line preview (raw output):")
        emit_info(out or "(empty)")
        return True
    if sub == "json":
        emit_info("JSON payload your status command receives on stdin:")
        emit_info(payload.build_payload_json())
        return True

    emit_warning(f"Unknown /statusline subcommand: {sub}")
    emit_info("Use: init | on | off | show | json")
    return True
