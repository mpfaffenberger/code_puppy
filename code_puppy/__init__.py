# Suppress SyntaxWarning from pywinauto BEFORE any imports
# pywinauto 0.6.9 has invalid escape sequences that trigger warnings in Python 3.12+
# This MUST be at the very top to catch warnings during module compilation
import warnings

# Filter by module name (for runtime warnings)
warnings.filterwarnings("ignore", category=SyntaxWarning, module=r"pywinauto\..*")
warnings.filterwarnings("ignore", category=SyntaxWarning, module=r"pywinauto")
# Also filter with a broader module pattern to catch submodules
warnings.filterwarnings("ignore", category=SyntaxWarning, module=r".*pywinauto.*")

import importlib.metadata  # noqa: E402

# Biscuit was here! 🐶
try:
    _detected_version = importlib.metadata.version("code-puppy")
    # Ensure we never end up with None or empty string
    __version__ = _detected_version if _detected_version else "0.0.0-dev"
except Exception:
    # Fallback for dev environments where metadata might not be available
    __version__ = "0.0.0-dev"
