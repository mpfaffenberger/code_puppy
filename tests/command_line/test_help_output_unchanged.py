"""Pin /help output to the pre-catalog implementation.

``_legacy_get_commands_help`` is the committed HEAD body of
``command_handler.get_commands_help`` (including its inline callback parser),
kept verbatim so the rewrite on top of ``command_catalog`` can be compared
cell-for-cell.
"""

import pytest
from rich.text import Text

from code_puppy import callbacks
from code_puppy.command_line.command_handler import (
    _ensure_plugins_loaded,
    get_commands_help,
)


def _legacy_get_commands_help():
    """Generate aligned commands help using Rich Text for safe markup.

    Now dynamically generates help from the command registry!
    Only shows two sections: Built-in Commands and Custom Commands.
    """
    from rich.text import Text

    from code_puppy.command_line.command_registry import get_unique_commands

    # Ensure plugins are loaded so custom help can register
    _ensure_plugins_loaded()

    lines: list[Text] = []
    # No global header needed - user already knows they're viewing help

    # Collect all built-in commands (registered + legacy)
    builtin_cmds: list[tuple[str, str]] = []

    # Get registered commands (all categories are built-in)
    registered_commands = get_unique_commands()
    for cmd_info in sorted(registered_commands, key=lambda c: c.name):
        builtin_cmds.append((cmd_info.usage, cmd_info.description))

    # Get custom commands from plugins
    custom_entries: list[tuple[str, str]] = []
    try:
        from code_puppy import callbacks

        custom_help_results = callbacks.on_custom_command_help()
        for res in custom_help_results:
            if not res:
                continue
            # Format 1: Tuple with (command_name, description)
            if isinstance(res, tuple) and len(res) == 2:
                cmd_name = str(res[0])
                custom_entries.append((f"/{cmd_name}", str(res[1])))
            # Format 2: List of tuples or strings
            elif isinstance(res, list):
                # Check if it's a list of tuples (preferred format)
                if res and isinstance(res[0], tuple) and len(res[0]) == 2:
                    for item in res:
                        if isinstance(item, tuple) and len(item) == 2:
                            cmd_name = str(item[0])
                            custom_entries.append((f"/{cmd_name}", str(item[1])))
                # Format 3: List of strings (legacy format)
                # Extract command from first line like "/command_name - Description"
                elif res and isinstance(res[0], str) and res[0].startswith("/"):
                    first_line = res[0]
                    if " - " in first_line:
                        parts = first_line.split(" - ", 1)
                        cmd_name = parts[0].lstrip("/").strip()
                        description = parts[1].strip()
                        custom_entries.append((f"/{cmd_name}", description))
    except Exception:
        pass

    # Calculate global column width (longest command across ALL sections + padding)
    all_commands = builtin_cmds + custom_entries
    if all_commands:
        max_cmd_width = max(len(cmd) for cmd, _ in all_commands)
        column_width = max_cmd_width + 4  # Add 4 spaces padding
    else:
        column_width = 30

    # Maximum description width before truncation (to prevent line wrapping)
    max_desc_width = 80

    def truncate_desc(desc: str, max_width: int) -> str:
        """Truncate description if too long, add ellipsis."""
        if len(desc) <= max_width:
            return desc
        return desc[: max_width - 3] + "..."

    # Display Built-in Commands section (starts immediately, no blank line)
    lines.append(Text("Built-in Commands", style="bold magenta"))
    for cmd, desc in sorted(builtin_cmds, key=lambda x: x[0]):
        truncated_desc = truncate_desc(desc, max_desc_width)
        left = Text(cmd.ljust(column_width), style="cyan")
        right = Text(truncated_desc)
        line = Text()
        line.append_text(left)
        line.append_text(right)
        lines.append(line)

    # Display Custom Commands section (if any)
    if custom_entries:
        lines.append(Text(""))
        lines.append(Text("Custom Commands", style="bold magenta"))
        for cmd, desc in sorted(custom_entries, key=lambda x: x[0]):
            truncated_desc = truncate_desc(desc, max_desc_width)
            left = Text(cmd.ljust(column_width), style="cyan")
            right = Text(truncated_desc)
            line = Text()
            line.append_text(left)
            line.append_text(right)
            lines.append(line)

    # Display Shell Pass-through section
    lines.append(Text(""))
    lines.append(Text("Shell Pass-through", style="bold magenta"))
    shell_left = Text("!<command>".ljust(column_width), style="cyan")
    shell_right = Text("Run a shell command directly (e.g., !git status)")
    shell_line = Text()
    shell_line.append_text(shell_left)
    shell_line.append_text(shell_right)
    lines.append(shell_line)

    final_text = Text()
    for i, line in enumerate(lines):
        if i > 0:
            final_text.append("\n")
        final_text.append_text(line)

    # Add trailing newline for spacing before next prompt
    final_text.append("\n")

    return final_text


def _snapshot(text: Text) -> tuple[str, list[tuple[int, int, str]]]:
    return text.plain, [(s.start, s.end, str(s.style)) for s in text.spans]


@pytest.mark.parametrize(
    ("callback_results", "expects_truncation"),
    [
        pytest.param([], False, id="no-plugin-entries"),
        pytest.param(
            [
                ("bare", "Bare tuple description"),
                [("listed_one", "First"), ("listed_two", "Second")],
                ["/legacy - Legacy string description"],
            ],
            False,
            id="tuple-list-and-legacy-string",
        ),
        pytest.param([[("longy", "x" * 120)]], True, id="description-over-80"),
    ],
)
def test_help_output_matches_legacy(monkeypatch, callback_results, expects_truncation):
    monkeypatch.setattr(callbacks, "on_custom_command_help", lambda: callback_results)

    new_help = get_commands_help()
    legacy_help = _legacy_get_commands_help()

    assert _snapshot(new_help) == _snapshot(legacy_help)
    assert ("Custom Commands" in new_help.plain) == bool(callback_results)
    assert ("..." in new_help.plain) == expects_truncation
