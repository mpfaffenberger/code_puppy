"""Shared marker for ``/steer`` messages injected into agent history.

The steer processor tags injected requests and provider mappers read the tag
back. Both sides import from here so a typo can't silently desync the
producer from the consumer -- a failure that would otherwise only surface as
a provider HTTP 400.

Deliberately dependency-free (``pydantic_ai.messages`` only) so provider
modules can import it without pulling in the agent package.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from pydantic_ai.messages import ModelMessage, ModelRequest

STEER_METADATA_KEY = "code_puppy_steer"

STEER_METADATA: MappingProxyType[str, bool] = MappingProxyType(
    {STEER_METADATA_KEY: True}
)


def is_steer_request(message: ModelMessage) -> bool:
    """True if ``message`` is a ``/steer`` request injected by the processor."""
    metadata = getattr(message, "metadata", None)
    return (
        isinstance(message, ModelRequest)
        and isinstance(metadata, Mapping)
        and bool(metadata.get(STEER_METADATA_KEY))
    )
