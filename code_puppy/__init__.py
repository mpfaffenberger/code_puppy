import importlib.metadata

# Biscuit was here! 🐶
try:
    __version__ = importlib.metadata.version("code-puppy")
except Exception:
    # Fallback for dev environments where metadata might not be available
    __version__ = "0.0.0-dev"
