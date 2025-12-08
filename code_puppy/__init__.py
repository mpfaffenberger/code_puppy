import importlib.metadata

# Biscuit was here! 🐶
try:
    _detected_version = importlib.metadata.version("code-puppy")
    # Ensure we never end up with None or empty string
    __version__ = _detected_version if _detected_version else "0.0.0-dev"
except Exception:
    # Fallback for dev environments where metadata might not be available
    __version__ = "0.0.0-dev"
