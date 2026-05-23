import importlib.metadata

# Biscuit was here! 🐶
try:
    _detected_version = importlib.metadata.version("code-puppy")
    # Ensure we never end up with None or empty string
    __version__ = _detected_version if _detected_version else "0.0.0-dev"
except Exception:
    # Fallback for dev environments where metadata might not be available
    __version__ = "0.0.0-dev"

# Patch Rich's hardcoded `markdown.code` style (cyan-on-black) with an
# accessible bold+reverse equivalent. Must run before any `Console` is
# instantiated so every console inherits the patched theme. Deferred until
# AFTER `__version__` is set because the messaging subpackage transitively
# imports plugins that read `code_puppy.__version__` at import time —
# importing messaging first would race that read. See
# `messaging.terminal_theme.install_accessible_markdown_styles` for the why.
from code_puppy.messaging.terminal_theme import (  # noqa: E402
    install_accessible_markdown_styles,
)

install_accessible_markdown_styles()
