"""Make saved API keys reach model providers, as Code Puppy 0.0.x did.

0.0.x kept keys such as ``OPENAI_API_KEY`` in ``puppy.cfg`` and exported them
at startup. The migration moves them into the encrypted ``/keys`` store, where
the runtime treats names as labels and exports nothing. Providers read their
key from the environment, so without this step a migrated user would have to
set every key again.

Only names shaped like a key variable are exported, and a variable the user
already set always wins.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping

KEY_ACCOUNT = "api-keys"
CREDENTIAL_SUFFIXES = ("_API_KEY", "_TOKEN")
"""What a credential variable is called. A name that redirects requests or
moves Code Puppy's own folders is not one, which is what keeps an untrusted
``.env`` from setting it; see ``main._load_dotenv``."""


def is_credential_name(name: str) -> bool:
    """Whether ``name`` is a provider credential rather than a setting."""
    return name.endswith(CREDENTIAL_SUFFIXES)


def export_saved_keys(environ: MutableMapping[str, str] = os.environ) -> list[str]:
    """Export saved keys that the environment lacks; return the names exported.

    Does not touch the keyring unless a key bundle exists.
    """
    from pydantic_ai_pax.config.api_keys import load_keys
    from pydantic_ai_pax.config.credential_store import has_credentials

    if not has_credentials(account=KEY_ACCOUNT):
        return []
    exported: list[str] = []
    for name, secret in load_keys().items():
        if is_credential_name(name) and not environ.get(name):
            environ[name] = secret.get_secret_value()
            exported.append(name)
    return exported
