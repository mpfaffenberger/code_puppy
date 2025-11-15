"""BigQuery authentication module for Walmart.

This module handles authentication for BigQuery using gcloud CLI.
It runs `gcloud auth application-default login` to set up credentials
that can be used by the BigQuery Python client.

Also handles automatic installation of gcloud CLI and Python dependencies.
"""

import os
import platform
import subprocess
import sys
import warnings
from typing import List, Optional

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

try:
    from google.cloud import bigquery
except ImportError:
    bigquery = None  # type: ignore


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
                timeout=5,
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
                timeout=5,
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
                timeout=5,
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
        if "wal-mart.com" in os.environ.get("HOSTNAME", "").lower() or os.environ.get("WALMART_NETWORK"):
            proxy_cmd = "[System.Net.WebRequest]::DefaultWebProxy = New-Object System.Net.WebProxy('http://sysproxy.wal-mart.com:8080'); "
        
        return (
            "PowerShell Installer",
            [
                "powershell",
                "-Command",
                proxy_cmd +
                "$ErrorActionPreference='Stop'; "
                "$zipUrl = 'https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-windows-x86_64.zip'; "
                "$zipFile = Join-Path $env:TEMP 'google-cloud-sdk.zip'; "
                "$installPath = Join-Path $env:LOCALAPPDATA 'Google\\CloudSDK'; "
                "Write-Host 'Downloading Google Cloud SDK (~100MB, please wait)...'; "
                "$webClient = New-Object Net.WebClient; "
                "$webClient.DownloadFile($zipUrl, $zipFile); "
                "Write-Host 'Download complete. Extracting...'; "
                "Expand-Archive -Path $zipFile -DestinationPath $installPath -Force; "
                "Write-Host 'Extraction complete. Configuring PATH...'; "
                "$binPath = Join-Path $installPath 'google-cloud-sdk\\bin'; "
                "$currentPath = [Environment]::GetEnvironmentVariable('Path', 'User'); "
                "if ($currentPath -notlike \"*$binPath*\") { "
                "  [Environment]::SetEnvironmentVariable('Path', \"$currentPath;$binPath\", 'User'); "
                "  Write-Host 'PATH updated.'; "
                "}; "
                "Remove-Item $zipFile -Force -ErrorAction SilentlyContinue; "
                "Write-Host ''; "
                "Write-Host 'Installation complete! Restart your terminal to use gcloud commands.' -ForegroundColor Green",
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
    if "wal-mart.com" in os.environ.get("HOSTNAME", "").lower() or os.environ.get(
        "WALMART_NETWORK"
    ):
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
            if system == "Windows":
                emit_info("🔄 Please restart your PowerShell/terminal to use gcloud commands.")
            else:
                emit_info("🔄 You may need to restart your terminal or run: source ~/.zshrc (or ~/.bashrc)")
            return True
        else:
            error_msg = result.stderr or result.stdout if capture_output else "Check output above"
            emit_error(f"❌ Installation failed:\n{error_msg}")
            return False

    except subprocess.TimeoutExpired:
        emit_error(f"❌ Installation timed out after {timeout // 60} minutes.")
        return False
    except Exception as e:
        emit_error(f"❌ Installation failed: {str(e)}")
        return False


def _install_python_dependencies() -> bool:
    """Install BigQuery Python dependencies.

    Returns:
        True if installation succeeded, False otherwise
    """
    emit_info("📦 Installing BigQuery Python dependencies...")

    # Determine the correct pip command
    pip_cmd = [sys.executable, "-m", "pip", "install"]

    # Check if we're using uv
    try:
        subprocess.run(["uv", "--version"], capture_output=True, timeout=5, check=True)
        pip_cmd = ["uv", "pip", "install"]
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        pass

    # Install optional dependencies
    packages = [
        "google-cloud-bigquery>=3.0.0",
    ]

    # Set proxy and index URL for Walmart network
    env = os.environ.copy()
    extra_args = []
    if "wal-mart.com" in os.environ.get("HOSTNAME", "").lower() or os.environ.get(
        "WALMART_NETWORK"
    ):
        env["HTTP_PROXY"] = "http://sysproxy.wal-mart.com:8080"
        env["HTTPS_PROXY"] = "http://sysproxy.wal-mart.com:8080"
        extra_args.extend(
            [
                "--index-url",
                "https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple",
                "--trusted-host",
                "pypi.ci.artifacts.walmart.com",
            ]
        )
        emit_info("🌐 Using Walmart PyPI registry")

    try:
        cmd = pip_cmd + packages + extra_args
        emit_info(f"Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )

        if result.returncode == 0:
            emit_success("✅ Python dependencies installed successfully!")
            return True
        else:
            emit_warning(
                f"⚠️  Dependency installation completed with warnings:\n{result.stderr or result.stdout}"
            )
            return True  # Continue anyway

    except subprocess.TimeoutExpired:
        emit_error("❌ Dependency installation timed out.")
        return False
    except Exception as e:
        emit_error(f"❌ Dependency installation failed: {str(e)}")
        return False


def _verify_credentials() -> bool:
    """Verify that application default credentials are valid.

    Returns:
        True if credentials are valid, False otherwise
    """
    try:
        # Try to create a client to verify credentials
        if bigquery is None:
            return False

        # Suppress quota project warning (expected when using gcloud auth)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=".*Your application has authenticated using end user credentials.*",
                category=UserWarning,
            )
            client = bigquery.Client()
            # Try a simple operation to verify credentials work
            _ = client.project
        return True
    except Exception as e:
        emit_warning(f"⚠️  Credential verification failed: {str(e)}")
        return False


def handle_bigquery_auth_command(command: str, name: str) -> Optional[str]:
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

    # Step 1: Check and install Python dependencies
    try:
        import google.cloud.bigquery  # noqa: F401

        emit_success("✅ BigQuery Python dependencies already installed")
    except ImportError:
        emit_warning("⚠️  BigQuery Python dependencies not found")
        if not _install_python_dependencies():
            return "Failed to install Python dependencies. Please install manually with: pip install google-cloud-bigquery google-cloud-resource-manager"

    # Step 2: Check if gcloud is installed, if not, install it
    try:
        result = subprocess.run(
            ["gcloud", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
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

        # After installation, verify it worked
        try:
            subprocess.run(
                ["gcloud", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ):
            return (
                "gcloud CLI installation completed, but command not found. "
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
            cmd = ["gcloud", "auth", "application-default", "login"]
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
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

            if result.returncode == 0:
                emit_success(
                    "🎉 BigQuery authentication complete!\n"
                    "Application Default Credentials have been saved."
                )

                # Verify credentials actually work
                emit_info("🔍 Verifying credentials...")
                if _verify_credentials():
                    emit_success(
                        "✅ Credentials verified successfully!\n"
                        "You can now use BigQuery tools."
                    )

                    # Get the default project for helpful info
                    try:
                        from google.cloud import bigquery

                        client = bigquery.Client()
                        default_project = client.project
                        emit_info(
                            f"📊 Default project: {default_project}\n"
                            f"💡 Tip: You can work with other projects by specifying project_id in commands."
                        )
                    except Exception:
                        pass  # Ignore if we can't get project info

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


def get_bigquery_auth_help() -> List[str]:
    """Get help information for BigQuery authentication.

    Returns:
        List[str]: List of help strings describing the command
    """
    return [
        "/bigquery_auth - Authenticate with Google BigQuery using gcloud",
        "",
        "This command will:",
        "  1. Check and install BigQuery Python dependencies if needed",
        "  2. Check and install gcloud CLI if needed (auto-install)",
        "  3. Run 'gcloud auth application-default login'",
        "  4. Open a browser window for Google authentication",
        "  5. Automatically retry with manual flow if browser auth fails",
        "  6. Verify credentials after authentication",
        "  7. Save Application Default Credentials locally",
        "",
        "The saved credentials can be used for BigQuery API access.",
        "",
        "Auto-installation support:",
        "  - macOS/Linux: Detects package manager (brew, apt, yum)",
        "  - Windows: Direct installer download (silent installation)",
        "  - Installs gcloud CLI automatically",
        "  - Installs Python dependencies via pip/uv",
        "  - Works with Walmart corporate proxy",
        "",
        "Automatic retry on failure:",
        "  - Detects browser authentication failures",
        "  - Automatically retries with --no-browser flag",
        "  - Provides manual authorization code flow",
        "  - Handles scope consent errors gracefully",
        "",
        "Manual installation (if auto-install fails):",
        "  gcloud: https://cloud.google.com/sdk/docs/install",
        "  Python: pip install google-cloud-bigquery",
        "",
        "Example:",
        "  /bigquery_auth",
    ]
