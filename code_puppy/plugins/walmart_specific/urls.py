from enum import Enum
from typing import Optional
from urllib.parse import urlencode


class Environment(Enum):
    DEV = "dev"
    STAGE = "stg"
    PROD = "prod"


class BaseURLs:
    DEV = "https://puppy.dev.walmart.com"
    STAGE = "https://puppy.stg.walmart.com"
    PROD = "https://puppy.walmart.com"


def get_base_url(environment: Environment = Environment.PROD) -> str:
    if environment == Environment.DEV:
        return BaseURLs.DEV
    elif environment == Environment.STAGE:
        return BaseURLs.STAGE
    elif environment == Environment.PROD:
        return BaseURLs.PROD
    else:
        raise ValueError(f"Unsupported environment: {environment}")


def get_models_url(environment: Environment = Environment.PROD) -> str:
    base_url = get_base_url(environment)
    return f"{base_url}/api/puppy-models/latest"


def get_authentication_url(
    port: Optional[int] = None,
    callback_url: Optional[str] = None,
    environment: Environment = Environment.PROD,
) -> str:
    """Build the authentication URL for code-puppy.

    Args:
        port: The local port for auth callback (legacy, localhost-only).
        callback_url: Full callback URL (for devcontainers/remote environments).
                     If provided, this takes precedence over port.
        environment: Target environment (dev/stage/prod).

    Returns:
        The authentication URL to open in the browser.

    Example callback_url for devcontainer:
        https://agent-sandbox.walmart.com/proxy/ws/app-123/proxy/8091/save_token
    """
    base_url = get_base_url(environment)
    url = f"{base_url}/authenticate_puppy"

    params = {}
    if callback_url is not None:
        # Use the full callback URL (for devcontainer/remote environments)
        params["callback_url"] = callback_url
    elif port is not None:
        # Legacy: just pass the port, auth site will POST to localhost:{port}
        params["port"] = str(port)

    if params:
        url = f"{url}?{urlencode(params)}"

    return url


def get_latest_version_url(environment: Environment = Environment.STAGE) -> str:
    base_url = get_base_url(environment)
    return f"{base_url}/api/releases/latest"


def get_setup_url(environment: Environment = Environment.STAGE) -> str:
    base_url = get_base_url(environment)
    return f"{base_url}/api/releases/setup"


def get_setup_windows_url(environment: Environment = Environment.STAGE) -> str:
    """Get the Windows-specific setup bat download URL.

    Defaults to STAGE to match the existing behaviour of all other release
    endpoints.  The environment default is intentionally NOT changed here —
    see the contrary review in docs/windows-update-review.md.
    """
    base_url = get_base_url(environment)
    return f"{base_url}/api/releases/setup_windows.bat"


def get_telemetry_url(environment: Environment = Environment.STAGE) -> str:
    """Get the telemetry endpoint URL for code generation events."""
    if environment == Environment.DEV:
        return "https://puppy-backend.dev.walmart.com/telemetry/code-generation"
    elif environment == Environment.STAGE:
        return "https://puppy-backend.stg.walmart.com/telemetry/code-generation"
    elif environment == Environment.PROD:
        return "https://puppy-backend.walmart.com/telemetry/code-generation"
    else:
        raise ValueError(f"Unsupported environment: {environment}")
    # For local development, fall back to localhost
    # return "http://localhost:8080/telemetry/code-generation"


def get_sharing_upload_url(
    environment: Environment = Environment.PROD,
    local: bool = False,
) -> str:
    """Get the sharing upload endpoint URL.

    Args:
        environment: Target environment (defaults to PROD).
        local: If True, use localhost:8080 instead of the remote server.
    """
    if local:
        return "http://localhost:8080/api/sharing/upload"
    base_url = get_base_url(environment)
    return f"{base_url}/api/sharing/upload"


def get_sharing_delete_url(
    business: str,
    name: str,
    environment: Environment = Environment.PROD,
    local: bool = False,
) -> str:
    """Get the sharing delete endpoint URL for a specific page."""
    if local:
        return f"http://localhost:8080/api/sharing/pages/{business}/{name}"
    base_url = get_base_url(environment)
    return f"{base_url}/api/sharing/pages/{business}/{name}"


def get_sharing_my_pages_url(
    environment: Environment = Environment.PROD,
    local: bool = False,
) -> str:
    """Get the sharing my-pages endpoint URL."""
    if local:
        return "http://localhost:8080/api/sharing/my-pages"
    base_url = get_base_url(environment)
    return f"{base_url}/api/sharing/my-pages"


def get_sharing_page_view_url(
    business: str,
    name: str,
    environment: Environment = Environment.PROD,
    local: bool = False,
) -> str:
    """Get the public view URL for a shared page."""
    if local:
        return f"http://localhost:8080/sharing/{business}/{name}"
    base_url = get_base_url(environment)
    return f"{base_url}/sharing/{business}/{name}"


def get_sharing_svps_url(
    environment: Environment = Environment.PROD,
    local: bool = False,
) -> str:
    """Get the sharing SVPs listing endpoint URL."""
    if local:
        return "http://localhost:8080/api/sharing/svps"
    base_url = get_base_url(environment)
    return f"{base_url}/api/sharing/svps"


def get_safety_validation_url(environment: Environment = Environment.STAGE) -> str:
    """Get the safety validation endpoint URL for shell command validation."""
    if environment == Environment.DEV:
        return "https://puppy-backend.dev.walmart.com/safety/validate-command"
    elif environment == Environment.STAGE:
        return "https://puppy-backend.stg.walmart.com/safety/validate-command"
    elif environment == Environment.PROD:
        return "https://puppy-backend.walmart.com/safety/validate-command"
    else:
        raise ValueError(f"Unsupported environment: {environment}")
