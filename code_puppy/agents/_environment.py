"""Model-facing facts about the local shell tool's execution environment."""

import os
import platform
import sys


def get_execution_environment_prompt() -> str:
    """Describe subprocess(shell=True), not the user's interactive terminal.

    The command runner does not override subprocess's executable: Windows
    uses COMSPEC (or SystemRoot's cmd.exe fallback), POSIX uses /bin/sh
    (or /system/bin/sh on Android).
    SHELL and the terminal hosting Code Puppy need not match that shell.
    """
    system = platform.system() or sys.platform
    if sys.platform == "win32":
        shell = os.environ.get("COMSPEC") or os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"
        )
        guidance = (
            "Use syntax compatible with this Windows command shell. "
            "For cmd.exe, use %NAME% for environment variables and Windows "
            "commands such as dir and where; do not use PowerShell cmdlets "
            "or POSIX shell syntax unless explicitly invoking that interpreter."
        )
    else:
        shell = "/system/bin/sh" if hasattr(sys, "getandroidapilevel") else "/bin/sh"
        guidance = (
            "Use POSIX sh-compatible syntax, not Bash-specific syntax unless "
            "explicitly invoking Bash. Do not assume GNU-only utilities or flags "
            "are available on every POSIX operating system."
        )
    return (
        "\n\nExecution environment (local shell tool):\n"
        f"- Operating system: {system}\n"
        f"- Command shell: {shell} (subprocess shell=True)\n"
        f"- {guidance}\n"
        "- The interactive terminal may use a different shell. These facts apply "
        "to local commands, not remote hosts, containers, or explicitly invoked shells."
    )
