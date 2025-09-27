"""Walmart-specific plugins and configurations.

This module automatically applies necessary patches and configurations
for running Code Puppy within the Walmart environment.
"""

import os
import ssl

from .monkey_patches import apply_github_redirect_patches


def setup_ssl_environment():
    """Set up SSL environment variables for corporate firewall compatibility."""
    # Set environment variables to help with SSL issues behind corporate firewalls
    # This helps libraries that don't use our patched HTTP functions
    os.environ["PYTHONHTTPSVERIFY"] = "0"  # Disable SSL verification in Python
    os.environ["SSL_VERIFY"] = "false"  # Some libraries check this
    os.environ["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"  # For Node.js tools

    # Set default SSL context to unverified for Python
    try:
        ssl._create_default_https_context = ssl._create_unverified_context
    except AttributeError:
        # Fallback for older Python versions
        pass


# Automatically apply patches and environment setup when the plugin is imported
setup_ssl_environment()
apply_github_redirect_patches()

__all__ = [
    "apply_github_redirect_patches",
    "setup_ssl_environment",
]
