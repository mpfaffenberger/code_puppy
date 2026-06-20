"""Public Mist package facade.

The implementation remains in ``code_puppy`` for one compatibility cycle so
existing plugins and integrations continue to import successfully.
"""

from code_puppy import __version__
from code_puppy.branding import (
    DISTRIBUTION_NAME,
    PRIMARY_CLI_NAME,
    PRODUCT_EMOJI,
    PRODUCT_NAME,
    PRODUCT_TAGLINE,
)

__all__ = [
    "DISTRIBUTION_NAME",
    "PRIMARY_CLI_NAME",
    "PRODUCT_EMOJI",
    "PRODUCT_NAME",
    "PRODUCT_TAGLINE",
    "__version__",
]
