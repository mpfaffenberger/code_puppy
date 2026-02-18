import subprocess
import sys
import tempfile
import httpx

from rich.text import Text

from code_puppy.http_utils import create_client
from code_puppy.messaging import emit_system_message
from code_puppy.plugins.walmart_specific.urls import (
    get_latest_version_url,
    get_setup_url,
    get_setup_windows_url,
)
from code_puppy.version_checker import normalize_version, versions_are_equal


def fetch_latest_version(package_name=None):
    """
    Fetch the latest version from the code-puppy staging API.

    Args:
        package_name: Ignored for backwards compatibility. We always fetch from the staging API.

    Returns:
        str: Latest version string (e.g., "v0.0.78") or None if fetch fails
    """
    try:
        # Use properly configured httpx client with correct certificates and 10 second timeout
        with create_client(timeout=10) as client:
            response = client.get(get_latest_version_url())
            response.raise_for_status()  # Raise an error for bad responses
            data = response.json()

            # Check if the response has the expected structure
            if not data.get("success"):
                print(
                    f"API returned unsuccessful response: {data.get('message', 'Unknown error')}"
                )
                return None

            # Extract version from nested structure
            version = data.get("data", {}).get("version")
            if not version:
                print("Error: Version not found in API response")
                return None

            return normalize_version(version)

    except httpx.TimeoutException:
        print("Error fetching version: Request timed out")
        return None
    except httpx.HTTPStatusError as e:
        print(
            f"Error fetching version: HTTP {e.response.status_code} - {e.response.reason_phrase}"
        )
        return None
    except httpx.RequestError as e:
        print(f"Error fetching version: {e}")
        return None
    except (KeyError, ValueError) as e:
        print(f"Error parsing version response: {e}")
        return None


def _handle_update(current_version):
    """Handle the auto-update process if a new version is available."""
    latest_version = fetch_latest_version("code-puppy")
    version_msg = f"Current version: {current_version}"
    emit_system_message(version_msg)

    # Guard: if the version API is unreachable we cannot determine whether
    # an update exists, so bail out silently rather than prompting for an
    # update to an unknown version.
    if latest_version is None:
        return

    latest_msg = f"Latest version: {latest_version}"
    emit_system_message(latest_msg)

    if versions_are_equal(current_version, latest_version):
        return

    update_available_msg = f"A new version of code puppy is available: {latest_version}"
    emit_system_message(
        Text.from_markup(f"[bold yellow]{update_available_msg}[/bold yellow]")
    )
    emit_system_message(
        Text.from_markup("[bold green]Auto-updating now...[/bold green]")
    )

    try:
        if sys.platform == "win32":
            # Windows update path.
            emit_system_message(
                Text.from_markup("[bold yellow]Running Windows update...[/bold yellow]")
            )
            proceed = input(
                "This will stop *ALL* other running instances of Code Puppy on your computer. Proceed (y/n)? "
            )
            if proceed.lower()[0] != "y":
                emit_system_message(
                    Text.from_markup("[yellow]Update cancelled by user.[/yellow]")
                )
                return

            # Write the bootstrap bat to %TEMP% to avoid System32 permission issues.
            # FIX: use get_setup_windows_url() — no hardcoded domain.
            # FIX: use curl.exe -Lk --proxy-insecure for Walmart network compat.
            setup_url = get_setup_windows_url()
            temp_dir = tempfile.gettempdir()
            update_bat_path = f"{temp_dir}\\update.bat"
            bat_content = (
                f"curl.exe -Lk --proxy-insecure {setup_url} "
                f"-o %TEMP%\\setup.bat && %TEMP%\\setup.bat && del %TEMP%\\setup.bat"
            )
            with open(update_bat_path, "w") as f:
                f.write(bat_content)

            update_command = f"start cmd.exe /k {update_bat_path}"
            emit_system_message(
                Text.from_markup(f"[dim]Running: {update_command}[/dim]")
            )
            emit_system_message("This instance of Code Puppy will close.")
            # FIX: launch the updater in its own CMD window (independent process),
            # then exit immediately.  The old code slept 20 s then always printed
            # an error because start(1) always returns 0 — never an error code.
            subprocess.run(update_command, shell=True)
            sys.exit(0)

        else:
            # macOS and Linux update
            setup_url = get_setup_url()
            emit_system_message(Text.from_markup(f"[dim]{setup_url}[/dim]"))

            result = subprocess.run(
                ["curl", "-skSL", setup_url],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                bash_result = subprocess.run(
                    ["bash"], input=result.stdout, text=True, timeout=120
                )

                if bash_result.returncode == 0:
                    success_msg = "✅ Update completed successfully!"
                    restart_msg = "Restarting code-puppy..."
                    emit_system_message(
                        Text.from_markup(f"[bold green]{success_msg}[/bold green]")
                    )
                    emit_system_message(
                        Text.from_markup(f"[yellow]{restart_msg}[/yellow]")
                    )
                    sys.exit(0)
                else:
                    error_msg = f"❌ Update script failed with exit code: {bash_result.returncode}"
                    emit_system_message(
                        Text.from_markup(f"[bold red]{error_msg}[/bold red]")
                    )
                    emit_system_message(
                        Text.from_markup(
                            "[yellow]Try reinstalling from https://puppy.walmart.com[/yellow]"
                        )
                    )
            else:
                error_msg = f"❌ Failed to download update script: {result.stderr}"
                emit_system_message(
                    Text.from_markup(f"[bold red]{error_msg}[/bold red]")
                )
                emit_system_message(
                    Text.from_markup(
                        "[yellow]Try reinstalling from https://puppy.walmart.com[/yellow]"
                    )
                )

    except subprocess.TimeoutExpired:
        timeout_msg = "❌ Update timed out"
        emit_system_message(Text.from_markup(f"[bold red]{timeout_msg}[/bold red]"))
        if sys.platform == "win32":
            emit_system_message(
                Text.from_markup(
                    "[yellow]Try running code-puppy in PowerShell or reinstall from https://puppy.walmart.com[/yellow]"
                )
            )
        else:
            emit_system_message(
                Text.from_markup(
                    "[yellow]Try reinstalling from https://puppy.walmart.com[/yellow]"
                )
            )
    except Exception as e:
        error_msg = f"❌ An unexpected error occurred during update: {str(e)}"
        emit_system_message(Text.from_markup(f"[bold red]{error_msg}[/bold red]"))
        if sys.platform == "win32":
            emit_system_message(
                Text.from_markup(
                    "[yellow]Try running code-puppy in PowerShell or reinstall from https://puppy.walmart.com[/yellow]"
                )
            )
        else:
            emit_system_message(
                Text.from_markup(
                    "[yellow]Try reinstalling from https://puppy.walmart.com[/yellow]"
                )
            )

    continue_msg = "Continuing with current version..."
    emit_system_message(Text.from_markup(f"[yellow]{continue_msg}[/yellow]"))
