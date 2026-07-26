"""/spinner -- pick a status-bar spinner style, interactively or by name.

UX:
  /spinner                  -> interactive picker with live animated preview
                               (-/+ adjusts speed, i writes a starter
                               spinners.json, Enter applies)
  /spinner <name> [seconds] -> apply by name, optionally at a custom speed
  /spinner init             -> write a starter spinners.json for custom spinners

Custom spinners live in ``spinners.json`` next to ``puppy.cfg``; user
entries override builtins on name collision. The choice persists in
``puppy.cfg``, custom speeds save into spinners.json itself, and both
take effect on the very next tick -- no restart. Edits to spinners.json
are picked up automatically (mtime watch), so there's no reload command
to remember.
"""

from __future__ import annotations

import asyncio
import concurrent.futures

from code_puppy.messaging import emit_error, emit_info, emit_warning

from . import spinners
from .picker import interactive_spinner_picker

_INTERACTIVE_TIMEOUT_SECONDS = 300  # 5 min -- generous; user is browsing


def help_entries():
    return [
        ("spinner", "Pick a status-bar spinner style (interactive: /spinner)"),
    ]


def _run_interactive_picker() -> tuple[str, float | None] | None:
    """Run the async TUI from a sync command handler (theme-plugin pattern)."""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(lambda: asyncio.run(interactive_spinner_picker()))
        return future.result(timeout=_INTERACTIVE_TIMEOUT_SECONDS)


def _apply(name: str, interval: float | None = None) -> None:
    # Case-insensitive: the command path lowercases args, but the pack
    # has camelCase names (dotsWide, bouncingBall, ...).
    catalogue = spinners.get_catalogue()
    name = next((n for n in catalogue if n.lower() == name.lower()), name)
    try:
        spinner = spinners.set_active(name, interval)
    except KeyError:
        known = ", ".join(sorted(spinners.get_catalogue()))
        emit_warning(
            f"Unknown spinner '{name}'. Try /spinner for the picker, "
            f"or pick one of: {known}."
        )
        return
    speed_note = " -- speed saved to spinners.json" if interval is not None else ""
    emit_info(
        f"Spinner set to '{spinner.name}' "
        f"({len(spinner.frames)} frames @ {spinner.interval:.2f}s{speed_note}). "
        f"Sample: {spinner.frames[0].strip()}"
    )


def _init() -> None:
    try:
        created = spinners.write_template()
    except OSError as exc:
        emit_error(f"Could not write {spinners.USER_SPINNERS_FILE}: {exc}")
        return
    if created:
        emit_info(
            f"Starter file written: {spinners.USER_SPINNERS_FILE}\n"
            "Edit it freely -- changes are picked up automatically."
        )
    else:
        emit_info(
            f"{spinners.USER_SPINNERS_FILE} already exists -- not touching it. "
            "Edit it directly; changes are picked up automatically."
        )


def handle_spinner(command: str, name: str):
    """``custom_command`` callback -- owns ``/spinner`` only."""
    if name != "spinner":
        return None

    parts = command.split()
    sub = parts[1].lower() if len(parts) > 1 else ""

    if sub == "":
        try:
            chosen = _run_interactive_picker()
        except Exception as exc:  # pragma: no cover -- defensive UX
            emit_error(f"Spinner picker failed: {exc}")
            return True
        if chosen is None:
            emit_info("Spinner unchanged.")
            return True
        name, interval = chosen
        _apply(name, interval)
    elif sub == "init":
        _init()
    else:
        interval = None
        if len(parts) > 2:
            try:
                interval = float(parts[2])
            except ValueError:
                emit_warning(
                    f"'{parts[2]}' is not a number of seconds. "
                    "Usage: /spinner <name> [seconds]"
                )
                return True
        _apply(sub, interval)
    return True
