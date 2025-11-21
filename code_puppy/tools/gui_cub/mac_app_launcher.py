"""macOS application launcher using reliable system commands.

Provides a robust alternative to Spotlight-based app launching that:
- Works regardless of window focus state
- Handles minimized apps correctly
- Doesn't require GUI automation timing tricks
- Uses native macOS 'open' command
"""

from __future__ import annotations

import subprocess

from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info
from code_puppy.tools.common import generate_group_id

from .platform import IS_MACOS
from .result_types import AppLaunchResult
from .tool_wrapper import desktop_tool


def mac_launch_app(
    context: RunContext,
    app_name: str,
    timeout: float = 5.0,
) -> AppLaunchResult:
    """Launch a macOS application using the 'open' command.

    This is more reliable than using Spotlight (Cmd+Space) because:
    1. No focus race conditions - works even with minimized apps
    2. No timing sensitivity - doesn't depend on GUI delays
    3. Native macOS command - uses system app launching
    4. Brings app to foreground automatically

    Args:
        app_name: Name of the app to launch (e.g., "Calculator", "Safari")
        timeout: Maximum seconds to wait for launch command

    Returns:
        AppLaunchResult with success status and app info

    Examples:
        - mac_launch_app(app_name="Calculator")
        - mac_launch_app(app_name="Safari", timeout=10.0)
        - mac_launch_app(app_name="Visual Studio Code")
    """
    if not IS_MACOS:
        return AppLaunchResult(
            success=False,
            error="mac_launch_app is only available on macOS",
        )

    try:
        # Use 'open -a' which launches by application name
        # -a flag: Opens the application with the specified name
        subprocess.run(
            ["open", "-a", app_name],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return AppLaunchResult(
            success=True,
            app_name=app_name,
            method="open_command",
        )

    except subprocess.CalledProcessError as e:
        # App not found or failed to launch
        error_msg = e.stderr.strip() if e.stderr else f"Failed to launch {app_name}"
        return AppLaunchResult(
            success=False,
            app_name=app_name,
            error=error_msg,
        )

    except subprocess.TimeoutExpired:
        return AppLaunchResult(
            success=False,
            app_name=app_name,
            error=f"Launch command timed out after {timeout}s",
        )

    except Exception as e:
        return AppLaunchResult(
            success=False,
            app_name=app_name,
            error=str(e),
        )


def register_mac_app_launcher_tools(agent):
    """Register macOS application launcher tool."""

    @agent.tool
    @desktop_tool("MAC LAUNCH APP", requires=None)
    def _wrapped_mac_launch_app(
        context: RunContext,
        app_name: str,
        timeout: float = 5.0,
    ) -> AppLaunchResult:
        """
        Launch a macOS application using the native 'open' command.

        This is the RECOMMENDED way to open apps on macOS instead of using
        Spotlight (Cmd+Space) because it:
        - Works reliably even with minimized windows
        - Doesn't require keyboard focus or timing delays
        - Brings app to foreground automatically
        - Uses native macOS system command

        Args:
            app_name: Name of the app to launch (e.g., "Calculator", "Safari")
            timeout: Maximum seconds to wait for launch (default: 5.0)

        Returns:
            AppLaunchResult with success status and app info

        Examples:
            - mac_launch_app(app_name="Calculator") - Opens Calculator
            - mac_launch_app(app_name="Safari") - Opens Safari browser
            - mac_launch_app(app_name="Visual Studio Code") - Opens VS Code
            - mac_launch_app(app_name="TextEdit") - Opens TextEdit

        Common App Names:
            - System: Calculator, TextEdit, Safari, Mail, Calendar, Notes
            - Dev: "Visual Studio Code", "IntelliJ IDEA", "PyCharm"
            - Browsers: Safari, Chrome, "Google Chrome", Firefox
            - Communication: Slack, "Microsoft Teams", Discord

        Note:
            App names are case-insensitive and should match the app's
            display name in /Applications (without .app extension).
        """
        group_id = generate_group_id("mac_launch_app", app_name)

        if not IS_MACOS:
            emit_error(
                "[red]✖ mac_launch_app is only available on macOS[/red]",
                message_group=group_id,
            )
            return AppLaunchResult(
                success=False,
                error="mac_launch_app is only available on macOS",
            )

        emit_info(
            f"[bold white on blue] MAC LAUNCH APP [/bold white on blue] 🚀 app_name='{app_name}'",
            message_group=group_id,
        )

        return mac_launch_app(context, app_name, timeout)
