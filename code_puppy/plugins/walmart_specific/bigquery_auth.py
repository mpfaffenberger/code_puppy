"""BigQuery authentication module for Walmart.

This module handles authentication for BigQuery using gcloud CLI.
It runs `gcloud auth application-default login` to set up credentials
that can be used by the BigQuery Python client.

Also handles automatic installation of gcloud CLI and Python dependencies.
"""

import json
import os
import platform
import subprocess
import threading
import urllib.error
import urllib.request
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.walmart_specific.bigquery_client import (
    _get_windows_gcloud_paths,
)

try:
    from google.cloud import bigquery
except ImportError:
    bigquery = None  # type: ignore


def _input_with_timeout(prompt: str, timeout: int = 60) -> str | None:
    """Get user input with timeout.

    Args:
        prompt: The prompt to display
        timeout: Timeout in seconds

    Returns:
        User input string, empty string if user pressed Enter, or None if timeout
    """
    result = [None]

    def get_input():
        try:
            result[0] = input(prompt)
        except (EOFError, KeyboardInterrupt):
            result[0] = None

    thread = threading.Thread(target=get_input, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        # Timeout occurred
        print()  # Add newline for clean output
        return None

    return result[0]


def _is_walmart_network() -> bool:
    """Check if running on Walmart network.

    Returns:
        True if on Walmart network, False otherwise
    """
    return (
        "wal-mart.com" in os.environ.get("HOSTNAME", "").lower()
        or os.environ.get("WALMART_NETWORK") is not None
    )


def _get_adc_path() -> Path:
    """Get the path to Application Default Credentials file.

    Returns:
        Path to ADC credentials file
    """
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "gcloud" / "application_default_credentials.json"
    # Unix-like systems (macOS, Linux)
    home = os.path.expanduser("~")
    return Path(home) / ".config" / "gcloud" / "application_default_credentials.json"


def _get_package_manager() -> tuple[str, list[str]] | None:
    """Detect the system package manager and return install command.

    Returns:
        Tuple of (package_manager_name, install_command_parts) or None if not detected
    """
    system = platform.system()

    # Check for Homebrew (macOS/Linux)
    if system == "Darwin" or system == "Linux":
        try:
            subprocess.run(
                ["brew", "--version"],
                capture_output=True,
                timeout=10,
                check=True,
            )
            return ("Homebrew", ["brew", "install", "--cask", "google-cloud-sdk"])
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ):
            pass

    # Check for apt (Debian/Ubuntu)
    if system == "Linux":
        try:
            subprocess.run(
                ["apt", "--version"],
                capture_output=True,
                timeout=10,
                check=True,
            )
            return ("apt", ["sudo", "apt-get", "install", "-y", "google-cloud-sdk"])
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ):
            pass

        # Check for yum (RHEL/CentOS)
        try:
            subprocess.run(
                ["yum", "--version"],
                capture_output=True,
                timeout=10,
                check=True,
            )
            return ("yum", ["sudo", "yum", "install", "-y", "google-cloud-sdk"])
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ):
            pass

    # For Windows: Download, extract, and add to PATH (skip install.bat which hangs)
    if system == "Windows":
        proxy_cmd = ""
        if _is_walmart_network():
            proxy_cmd = "[System.Net.WebRequest]::DefaultWebProxy = New-Object System.Net.WebProxy('http://sysproxy.wal-mart.com:8080'); "

        return (
            "PowerShell Installer",
            [
                "powershell",
                "-Command",
                proxy_cmd + "$ErrorActionPreference='Stop'; "
                "Add-Type -Assembly System.IO.Compression.FileSystem; "
                "$zipUrl = 'https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-windows-x86_64.zip'; "
                "$zipFile = Join-Path $env:TEMP 'google-cloud-sdk.zip'; "
                "$installPath = Join-Path $env:LOCALAPPDATA 'Google\\CloudSDK'; "
                "Write-Host 'Downloading Google Cloud SDK (~100MB)...'; "
                "[Console]::Out.Flush(); "
                "$webClient = New-Object Net.WebClient; "
                "$webClient.DownloadFile($zipUrl, $zipFile); "
                "Write-Host 'Download complete. Extracting...'; "
                "[Console]::Out.Flush(); "
                "if (Test-Path $installPath) { Remove-Item $installPath -Recurse -Force }; "
                "$zip = [System.IO.Compression.ZipFile]::OpenRead($zipFile); "
                "$totalFiles = $zip.Entries.Count; "
                "$zip.Dispose(); "
                "Write-Progress -Activity 'Extracting Google Cloud SDK' -Status 'Processing files...' -PercentComplete 0; "
                "[System.IO.Compression.ZipFile]::ExtractToDirectory($zipFile, $installPath); "
                "Write-Progress -Activity 'Extracting Google Cloud SDK' -Status 'Complete' -PercentComplete 100 -Completed; "
                "Write-Host 'Extraction complete. Configuring PATH...'; "
                "$binPath = Join-Path $installPath 'google-cloud-sdk\\bin'; "
                "$currentPath = [Environment]::GetEnvironmentVariable('Path', 'User'); "
                'if ($currentPath -notlike "*$binPath*") { '
                "  [Environment]::SetEnvironmentVariable('Path', \"$currentPath;$binPath\", 'User'); "
                "}; "
                '$env:PATH = "$binPath;$env:PATH"; '
                "Remove-Item $zipFile -Force -ErrorAction SilentlyContinue; "
                "Write-Host ''; "
                "Write-Host 'Installation complete!' -ForegroundColor Green",
            ],
        )

    return None


def _install_gcloud_cli() -> bool:
    """Attempt to install gcloud CLI using system package manager.

    Returns:
        True if installation succeeded, False otherwise
    """
    emit_info("🔍 Detecting system package manager...")
    package_manager = _get_package_manager()

    if not package_manager:
        emit_error(
            "❌ Could not detect a supported package manager.\n"
            "Please install gcloud CLI manually from:\n"
            "https://cloud.google.com/sdk/docs/install"
        )
        return False

    manager_name, install_cmd = package_manager
    emit_info(f"📦 Found {manager_name}. Installing gcloud CLI...")
    emit_info(f"Running: {' '.join(install_cmd)}")

    # Set proxy for Walmart network if needed
    env = os.environ.copy()
    if _is_walmart_network():
        env["HTTP_PROXY"] = "http://sysproxy.wal-mart.com:8080"
        env["HTTPS_PROXY"] = "http://sysproxy.wal-mart.com:8080"
        emit_info("🌐 Detected Walmart network, using corporate proxy")

    # Windows needs longer timeout and should show progress
    system = platform.system()
    if system == "Windows" and manager_name == "PowerShell Installer":
        timeout = 600  # 10 minutes for large download on corporate network
        capture_output = False  # Show progress to user
        emit_info("⏳ This may take several minutes. Progress will be shown below...")
    else:
        timeout = 300
        capture_output = True

    try:
        result = subprocess.run(
            install_cmd,
            capture_output=capture_output,
            text=True if capture_output else False,
            timeout=timeout,
            env=env,
        )

        if result.returncode == 0:
            emit_success("✅ gcloud CLI installed successfully!")

            # For Windows, update current Python process PATH
            if system == "Windows" and manager_name == "PowerShell Installer":
                try:
                    gcloud_bin, _ = _get_windows_gcloud_paths()

                    if os.path.exists(gcloud_bin):
                        # Add to current Python process PATH
                        os.environ["PATH"] = f"{gcloud_bin};{os.environ['PATH']}"
                        emit_info(f"✅ Added gcloud to current session: {gcloud_bin}")

                        # Verify gcloud.cmd exists
                        gcloud_cmd = os.path.join(gcloud_bin, "gcloud.cmd")
                        if os.path.exists(gcloud_cmd):
                            emit_success("✅ gcloud is now available!")
                        else:
                            emit_warning(
                                "⚠️ gcloud.cmd not found, may need terminal restart"
                            )
                    else:
                        emit_warning(
                            f"⚠️ Installation directory not found: {gcloud_bin}"
                        )
                        emit_info("Please restart your terminal and try again")

                except Exception as e:
                    emit_warning(f"⚠️ Could not update PATH automatically: {str(e)}")
                    emit_info("Please restart your terminal to use gcloud")
            else:
                emit_info("🔄 Restart terminal or run: source ~/.zshrc (or ~/.bashrc)")

            return True
        else:
            error_msg = (
                result.stderr or result.stdout
                if capture_output
                else "Check output above"
            )
            emit_error(f"❌ Installation failed:\n{error_msg}")
            return False

    except subprocess.TimeoutExpired:
        emit_error(f"❌ Installation timed out after {timeout // 60} minutes.")
        return False
    except Exception as e:
        emit_error(f"❌ Installation failed: {str(e)}")
        return False


def _install_python_dependencies() -> bool:
    """Check BigQuery Python dependencies.

    Note: As of recent updates, google-cloud-bigquery and sqlparse are core
    dependencies and should always be available. This function is kept for
    backward compatibility but no longer performs installation.

    Returns:
        True (dependencies should always be available)
    """
    # Both google-cloud-bigquery and sqlparse are now core dependencies
    # No installation needed - they're installed with code-puppy
    emit_info("📦 BigQuery dependencies are core dependencies (already installed)")
    return True


def _ensure_gcloud_account_authenticated(gcloud_cmd: str = "gcloud") -> bool:
    """Ensure gcloud has an active account for CLI commands.

    gcloud auth application-default login sets up ADC but doesn't activate
    the gcloud CLI account. This function checks if there's an active account
    and prompts for gcloud auth login if needed.

    Args:
        gcloud_cmd: Path to gcloud command

    Returns:
        True if account is active or successfully authenticated, False otherwise
    """
    try:
        # Check if there's an active gcloud account
        result = subprocess.run(
            [
                gcloud_cmd,
                "auth",
                "list",
                "--filter=status:ACTIVE",
                "--format=value(account)",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0 and result.stdout.strip():
            # Active account exists
            active_account = result.stdout.strip()
            emit_info(f"✅ Active gcloud account: {active_account}")
            return True

        # No active account - need to run gcloud auth login
        emit_warning(
            "⚠️  No active gcloud account found.\n"
            "   Running 'gcloud auth login' to activate your account..."
        )
        emit_info("🌐 Opening browser for gcloud CLI authentication...")

        # Run gcloud auth login (this will use the same Google account)
        login_result = subprocess.run(
            [gcloud_cmd, "auth", "login"],
            timeout=300,
        )

        if login_result.returncode == 0:
            emit_success("✅ gcloud account activated successfully!")
            return True
        else:
            emit_error("❌ Failed to activate gcloud account")
            return False

    except subprocess.TimeoutExpired:
        emit_error("❌ Timeout while checking/activating gcloud account")
        return False
    except Exception as e:
        emit_warning(f"⚠️  Error checking gcloud account: {str(e)}")
        return False


def _get_access_token(gcloud_cmd: str = "gcloud") -> str | None:
    """Get access token from gcloud for API calls."""
    try:
        result = subprocess.run(
            [gcloud_cmd, "auth", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


def _check_bigquery_permission(project_id: str, token: str) -> bool:
    """Check if user has bigquery.jobs.create permission on a project."""
    try:
        url = (
            f"https://cloudresourcemanager.googleapis.com/v1/projects/"
            f"{project_id}:testIamPermissions"
        )
        data = json.dumps({"permissions": ["bigquery.jobs.create"]}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=30) as response:
            resp_data = json.loads(response.read().decode())
            return "bigquery.jobs.create" in resp_data.get("permissions", [])
    except Exception:
        return False


def _get_projects_with_bq_access(
    project_ids: list[str], gcloud_cmd: str = "gcloud"
) -> list[str]:
    """Get list of projects where user has bigquery.jobs.create permission."""
    if not project_ids:
        return []

    token = _get_access_token(gcloud_cmd)
    if not token:
        return []

    permitted = []

    def check(pid: str) -> str | None:
        if _check_bigquery_permission(pid, token):
            return pid
        return None

    with ThreadPoolExecutor(max_workers=40) as executor:
        futures = [executor.submit(check, p) for p in project_ids]
        for future in as_completed(futures):
            result = future.result()
            if result:
                permitted.append(result)

    permitted.sort()
    return permitted


def _get_default_project(gcloud_cmd: str = "gcloud") -> str | None:
    """Get default project from gcloud config or prompt user to select one.

    Args:
        gcloud_cmd: Path to gcloud command

    Returns:
        Default project ID or None
    """
    try:
        # First try to get the configured default project
        result = subprocess.run(
            [gcloud_cmd, "config", "get-value", "project"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        current_default = None
        if result.returncode == 0 and result.stdout.strip():
            project = result.stdout.strip()
            if project and project != "(unset)":
                current_default = project
                emit_success(f"✅ Found default project from gcloud config: {project}")

        # List all projects for user to review
        if current_default:
            emit_info(
                f"📊 Listing your available projects (current default: {current_default})..."
            )
            emit_info(
                "    You can select a different project or press Enter to keep the default."
            )
        else:
            emit_info("📊 No default project set. Listing your available projects...")
        emit_info("")

        # Get project IDs for BQ permission check (run in background)
        ids_result = subprocess.run(
            [gcloud_cmd, "projects", "list", "--format=value(projectId)"],
            capture_output=True,
            text=True,
            timeout=240,
        )
        all_project_ids = (
            [p.strip() for p in ids_result.stdout.strip().split("\n") if p.strip()]
            if ids_result.returncode == 0
            else []
        )

        # Show projects in table format
        list_result = subprocess.run(
            [gcloud_cmd, "projects", "list", "--format=table(projectId, name)"],
            capture_output=False,  # Show output directly to user
            timeout=240,  # 4 minutes - can be slow on corporate networks with many projects
        )

        if list_result.returncode != 0:
            emit_error("❌ Failed to list projects")
            return None

        emit_info("")

        # Check BigQuery permissions and show summary
        if all_project_ids:
            emit_info("🔍 Checking BigQuery access permissions...")
            bq_permitted = _get_projects_with_bq_access(all_project_ids, gcloud_cmd)
            if bq_permitted:
                emit_info("")
                emit_info(f"✅ Projects with BigQuery access ({len(bq_permitted)}):")
                emit_info("   " + "-" * 50)
                for proj in bq_permitted:
                    marker = " (current default)" if proj == current_default else ""
                    emit_info(f"   {proj}{marker}")
                emit_info("   " + "-" * 50)
            else:
                emit_warning("⚠️  No projects found with BigQuery access")
            emit_info("")
            emit_info(
                "💡 Tip: Preferably select projects with prefix 'wmt-*' or 'sams-*' "
                "for Walmart BigQuery access."
            )
            emit_info("")

        # If default exists, use timeout and allow Enter to keep default
        if current_default:
            emit_info(
                f"💡 Press Enter to keep '{current_default}' or enter a different Project ID:"
            )
            emit_info("    (120 second timeout - will use default if no response)")
            emit_info("")

            user_input = _input_with_timeout("Project ID: ", timeout=120)

            # Timeout occurred
            if user_input is None:
                emit_info(f"⏱️  No response - using current default: {current_default}")
                return current_default

            # User pressed Enter (empty input)
            project_id = user_input.strip()
            if not project_id:
                emit_success(f"✅ Keeping current default: {current_default}")
                return current_default

            # User entered a new project ID - proceed to set it
        else:
            # No default project exists - use original retry logic
            emit_info("💡 Please enter the Project ID from the list above:")
            emit_info("")

            # Get user input with retry (no default case)
            max_attempts = 3
            project_id = None

            for attempt in range(1, max_attempts + 1):
                try:
                    project_id = input("Project ID: ").strip()
                except (EOFError, KeyboardInterrupt):
                    emit_warning("\n⚠️  Project selection cancelled")
                    return None

                if project_id:
                    break
                else:
                    emit_error(
                        f"❌ No project ID provided (attempt {attempt}/{max_attempts})"
                    )
                    if attempt < max_attempts:
                        emit_info("Please try again:")
                    else:
                        emit_error("❌ Failed to get project ID after 3 attempts")
                        return None

        # Set it as the default
        emit_info(f"Setting {project_id} as default project...")
        set_result = subprocess.run(
            [gcloud_cmd, "config", "set", "project", project_id],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if set_result.returncode == 0:
            emit_success(f"✅ Set {project_id} as default project")
            return project_id
        else:
            emit_error(
                f"❌ Failed to set default project: {set_result.stderr or set_result.stdout}"
            )
            return None

    except subprocess.TimeoutExpired:
        emit_error("❌ Timeout while accessing gcloud projects")
        return None
    except Exception as e:
        emit_warning(f"⚠️  Could not determine default project: {str(e)}")
        return None


def _verify_credentials(project_id: str | None = None) -> bool:
    """Verify that application default credentials are valid.

    Args:
        project_id: Optional project ID to use for verification

    Returns:
        True if credentials are valid, False otherwise
    """
    try:
        from google.auth import default
        from google.auth.exceptions import DefaultCredentialsError

        # Try to load default credentials
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=".*Your application has authenticated using end user credentials.*",
                category=UserWarning,
            )
            credentials, detected_project = default()

        # Require a project - don't allow authentication without one
        final_project = project_id or detected_project

        if not final_project:
            emit_error("❌ No default project available. Cannot verify credentials.")
            return False

        # Verify we can create a client with this project
        if bigquery is not None:
            client = bigquery.Client(project=final_project, credentials=credentials)
            # Simple check - accessing project property
            _ = client.project
            emit_info(f"✅ Credentials verified with project: {final_project}")
        else:
            emit_info(f"✅ Credentials loaded (project: {final_project})")

        return True

    except DefaultCredentialsError as e:
        emit_warning(f"⚠️  Credential verification failed: {str(e)}")
        return False
    except Exception as e:
        emit_warning(f"⚠️  Unexpected error during verification: {str(e)}")
        return False


def handle_bigquery_auth_command(command: str, name: str) -> str | None:
    """Handle the /bigquery_auth command.

    This command:
    1. Checks for and installs Python dependencies if needed
    2. Checks for and installs gcloud CLI if needed
    3. Runs `gcloud auth application-default login`

    This opens a browser window for the user to authenticate with their
    Google account, and stores the credentials locally for use by the
    BigQuery client library.

    Args:
        command: The full command string (e.g., "/bigquery_auth")
        name: The command name without the slash (e.g., "bigquery_auth")

    Returns:
        Optional[str]: Success/error message, or None if not handled
    """
    if name != "bigquery_auth":
        return None

    emit_info("🔐 Starting BigQuery authentication flow...")

    # Step 1: Verify Python dependencies (should always be available as core dependencies)
    # Note: google-cloud-bigquery and sqlparse are now core dependencies
    try:
        import google.cloud.bigquery  # noqa: F401
        import sqlparse  # noqa: F401

        emit_success("✅ BigQuery Python dependencies available")
    except ImportError as e:
        emit_error(
            f"❌ BigQuery dependencies missing: {e}\n"
            "This should not happen - please reinstall code-puppy with: uv pip install --upgrade code-puppy"
        )
        return "BigQuery dependencies not found. Please reinstall code-puppy."

    # Step 2: Check if gcloud is installed, if not, install it
    system = platform.system()
    gcloud_cmd = "gcloud"

    # On Windows, check if gcloud exists in the standard location
    if system == "Windows":
        gcloud_bin_dir, gcloud_cmd_path = _get_windows_gcloud_paths()

        # If gcloud is installed, use full path and ensure it's in PATH
        if os.path.exists(gcloud_cmd_path):
            gcloud_cmd = gcloud_cmd_path

            # Update PATH for current Python process
            os.environ["PATH"] = f"{gcloud_bin_dir};{os.environ['PATH']}"

            # Also update user PATH in Windows registry so it persists and is immediately available
            # This ensures subprocess calls work even if os.environ doesn't propagate properly
            try:
                subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        f'$path = [Environment]::GetEnvironmentVariable("Path", "User"); '
                        f'if ($path -notlike "*{gcloud_bin_dir}*") {{ '
                        f'[Environment]::SetEnvironmentVariable("Path", "{gcloud_bin_dir};$path", "User"); '
                        f'$env:PATH = "{gcloud_bin_dir};$env:PATH" }}',
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=True,
                )
                emit_success(
                    "✅ Added gcloud to PATH (current session and user registry)"
                )
            except Exception as e:
                # Fallback - at least we have it in current process
                emit_warning(f"⚠️  Could not update user PATH registry: {e}")
                emit_info(f"✅ Added gcloud to current session PATH: {gcloud_bin_dir}")

    try:
        # Use longer timeout on Windows for potential first-time initialization
        check_timeout = 120 if system == "Windows" else 30
        result = subprocess.run(
            [gcloud_cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=check_timeout,
        )
        if result.returncode != 0:
            raise FileNotFoundError("gcloud command failed")
        emit_success("✅ gcloud CLI is already installed")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        emit_warning("⚠️  gcloud CLI is not installed")
        emit_info("🚀 Attempting to install gcloud CLI automatically...")

        if not _install_gcloud_cli():
            return (
                "Failed to install gcloud CLI automatically. "
                "Please install it manually from: https://cloud.google.com/sdk/docs/install"
            )

        # After installation, gcloud should be in PATH (updated in _install_gcloud_cli)
        # Verify gcloud.cmd exists and ensure PATH is set for this session
        if system == "Windows":
            gcloud_bin_dir, gcloud_path = _get_windows_gcloud_paths()

            if not os.path.exists(gcloud_path):
                return (
                    "gcloud CLI installation completed, but gcloud.cmd not found. "
                    "Please restart your terminal and try again."
                )

            # Update PATH for current Python process
            os.environ["PATH"] = f"{gcloud_bin_dir};{os.environ['PATH']}"

            # Also update user PATH in Windows registry for persistence
            try:
                subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        f'$path = [Environment]::GetEnvironmentVariable("Path", "User"); '
                        f'if ($path -notlike "*{gcloud_bin_dir}*") {{ '
                        f'[Environment]::SetEnvironmentVariable("Path", "{gcloud_bin_dir};$path", "User"); '
                        f'$env:PATH = "{gcloud_bin_dir};$env:PATH" }}',
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=True,
                )
                emit_success(
                    "✅ Added gcloud to PATH (current session and user registry)"
                )
            except Exception as e:
                emit_warning(f"⚠️  Could not update user PATH registry: {e}")
                emit_success(
                    f"✅ Added gcloud to current session PATH: {gcloud_bin_dir}"
                )

            emit_info(f"Using gcloud from PATH (installed at: {gcloud_path})")
            # For immediate verification after install, use full path
            gcloud_cmd = gcloud_path
        else:
            # Use 'gcloud' command to rely on PATH
            gcloud_cmd = "gcloud"

        # Verify installation worked
        # Use longer timeout on Windows for first-time initialization
        verification_timeout = 120 if system == "Windows" else 30
        emit_info(
            f"Verifying gcloud installation (timeout: {verification_timeout}s)..."
        )

        try:
            subprocess.run(
                [gcloud_cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=verification_timeout,
                check=True,
            )
            emit_success("✅ gcloud CLI verified successfully")
        except subprocess.TimeoutExpired:
            emit_warning(
                f"⚠️  gcloud verification timed out after {verification_timeout} seconds.\n"
                "This can happen on first run. The installation appears complete.\n"
                "If you encounter issues, please restart your terminal."
            )
            # Don't return error - installation succeeded, just verification timed out
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            return (
                f"gcloud CLI installation completed, but verification failed: {str(e)}. "
                "Please restart your terminal and try again."
            )

    # Step 3: Run gcloud auth application-default login
    # Try with browser first, fall back to --no-browser if it fails
    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        use_no_browser = attempt > 1  # Use --no-browser on retry

        if use_no_browser:
            emit_warning(
                "⚠️  Browser authentication failed. Trying manual authentication flow..."
            )
            emit_info(
                "🔑 You'll receive a URL and will need to:\n"
                "   1. Open the URL in your browser\n"
                "   2. Complete authentication\n"
                "   3. Copy the authorization code\n"
                "   4. Paste it back here"
            )
        else:
            emit_info(
                "🌐 Opening browser for Google authentication...\n"
                "The credentials will be stored locally by gcloud."
            )
            emit_info("⏳ Please complete authentication in the browser window...")

        try:
            cmd = [gcloud_cmd, "auth", "application-default", "login"]
            if use_no_browser:
                cmd.append("--no-browser")

            # For --no-browser mode, we need interactive input
            if use_no_browser:
                # Run interactively so user can paste the code
                import sys

                result = subprocess.run(
                    cmd,
                    stdin=sys.stdin,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                    timeout=300,
                )
            else:
                # Don't capture output - let user see what gcloud is doing
                result = subprocess.run(
                    cmd,
                    timeout=300,
                )

            if result.returncode == 0:
                emit_success(
                    "🎉 BigQuery authentication complete!\n"
                    "Application Default Credentials have been saved."
                )

                # Verify credentials file was actually created
                adc_path = _get_adc_path()
                if not adc_path.exists():
                    emit_error(
                        f"❌ Authentication succeeded but credentials file not found!\n"
                        f"   Expected: {adc_path}\n"
                        f"   \n"
                        f"   gcloud may have written credentials elsewhere or failed silently.\n"
                        f"   Check the output above for clues."
                    )
                    return "Authentication succeeded but credentials were not saved. See output above."

                # File exists, set env var
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(adc_path)
                emit_success(f"✅ Credentials saved to: {adc_path}")

                # Ensure gcloud account is active before listing projects
                emit_info("🔍 Checking gcloud account status...")
                if not _ensure_gcloud_account_authenticated(gcloud_cmd):
                    emit_warning(
                        "⚠️  Could not activate gcloud account.\n"
                        "   You may need to run 'gcloud auth login' manually."
                    )
                    return "Authentication completed but gcloud account activation failed. Please run: gcloud auth login"

                # Get and set default project automatically
                emit_info("🔍 Setting up default project...")
                default_project = _get_default_project(gcloud_cmd)

                if not default_project:
                    emit_error(
                        "❌ Could not determine a default GCP project.\n"
                        "Please set one manually: gcloud config set project YOUR_PROJECT_ID"
                    )
                    return "Authentication completed but no default project available. Please set one with: gcloud config set project YOUR_PROJECT_ID"

                # Verify credentials actually work
                emit_info("🔍 Verifying credentials...")
                if _verify_credentials(project_id=default_project):
                    emit_success(
                        "✅ Credentials verified successfully!\n"
                        "You can now use BigQuery tools."
                    )
                    emit_info(
                        f"💡 Default project '{default_project}' is now set.\n"
                        f"   You can work with other projects by specifying project_id in commands."
                    )
                    return "BigQuery authentication successful!"
                else:
                    emit_warning(
                        "⚠️  Authentication completed but credentials verification failed.\n"
                        "You may need to grant additional permissions."
                    )
                    return "Authentication completed with warnings. Try using BigQuery tools to verify."
            else:
                # Check if this is a browser/consent error
                error_output = (result.stderr if hasattr(result, "stderr") else "") + (
                    result.stdout if hasattr(result, "stdout") else ""
                )

                is_browser_error = any(
                    phrase in error_output.lower()
                    for phrase in [
                        "problem with web authentication",
                        "try running again with --no-browser",
                        "scope is required but not consented",
                        "browser",
                    ]
                )

                if is_browser_error and attempt < max_attempts:
                    emit_warning(
                        f"⚠️  Attempt {attempt}/{max_attempts} failed: Browser authentication issue detected"
                    )
                    continue  # Retry with --no-browser
                else:
                    error_msg = error_output or "Unknown error"
                    emit_error(f"❌ Authentication failed:\n{error_msg}")
                    if attempt >= max_attempts:
                        emit_info(
                            "💡 Troubleshooting tips:\n"
                            "   - Make sure you're allowing all required scopes/permissions\n"
                            "   - Check if your browser is blocking popups\n"
                            "   - Try running: gcloud auth application-default login --no-browser"
                        )
                    return f"Authentication failed after {max_attempts} attempts: {error_msg}"

        except subprocess.TimeoutExpired:
            emit_error(
                f"❌ Authentication attempt {attempt} timed out after 5 minutes."
            )
            if attempt >= max_attempts:
                return "Authentication timed out. Please try again."
            continue  # Retry
        except Exception as e:
            emit_error(f"❌ Authentication attempt {attempt} failed: {str(e)}")
            if attempt >= max_attempts:
                return f"Authentication failed: {str(e)}"
            continue  # Retry

    return "Authentication failed after all retry attempts."


def get_bigquery_auth_help() -> list[tuple[str, str]]:
    """Get help information for BigQuery authentication.

    Returns:
        List[Tuple[str, str]]: List of (command_name, description) tuples for autocomplete
    """
    return [
        ("bigquery_auth", "Authenticate with Google BigQuery using gcloud"),
    ]
