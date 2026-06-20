import importlib.metadata

from code_puppy.branding import DISTRIBUTION_NAME, LEGACY_DISTRIBUTION_NAME

try:
    try:
        _detected_version = importlib.metadata.version(DISTRIBUTION_NAME)
    except importlib.metadata.PackageNotFoundError:
        _detected_version = importlib.metadata.version(LEGACY_DISTRIBUTION_NAME)
    # Ensure we never end up with None or empty string
    __version__ = _detected_version if _detected_version else "0.0.0-dev"
except Exception:
    # Fallback for dev environments where metadata might not be available
    __version__ = "0.0.0-dev"
