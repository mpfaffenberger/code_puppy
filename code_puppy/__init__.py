# Apply Walmart-specific patches BEFORE any other imports
# This ensures GitHub URL redirects are in place before http_utils or any other module
# imports requests, httpx, urllib3, etc.
try:
    from code_puppy.plugins.walmart_specific import apply_github_redirect_patches

    apply_github_redirect_patches()
except Exception:
    pass  # Silently fail if walmart_specific plugin not available

import importlib.metadata

# Biscuit was here! 🐶
try:
    __version__ = importlib.metadata.version("code-puppy")
except Exception:
    # Fallback for dev environments where metadata might not be available
    __version__ = "0.0.0-dev"
