import httpx

from .http_utils import create_client


def normalize_version(version_str):
    """
    Normalize version string by removing 'v' prefix for comparison.

    Args:
        version_str: Version string like "v0.0.78" or "0.0.78"

    Returns:
        str: Normalized version string without 'v' prefix
    """
    if not version_str:
        return version_str
    return version_str.lstrip("v")


def versions_are_equal(current, latest):
    """
    Compare two version strings, ignoring 'v' prefix differences.

    Args:
        current: Current version string
        latest: Latest version string

    Returns:
        bool: True if versions are equivalent
    """
    return normalize_version(current) == normalize_version(latest)


def fetch_latest_version(package_name=None):
    """
    Fetch the latest version from the code-puppy staging API.

    Args:
        package_name: Ignored for backwards compatibility. We always fetch from the staging API.

    Returns:
        str: Latest version string (e.g., "v0.0.78") or None if fetch fails
    """
    try:
        # Use properly configured httpx client with correct certificates
        with create_client() as client:
            response = client.get("https://puppy.stg.walmart.com/api/releases/latest")
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
