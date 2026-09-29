"""Application-side consumption of capability events.

The capabilities in ``code_puppy.capabilities`` are pure and emit typed
``CapabilityEvent`` families. This package owns the *only* seam where
those events meet Code Puppy specifics: the
:class:`~code_puppy.events.bridge.CapabilityEventBridge` capability
subscribes with ``@on_event`` listeners and translates events into
legacy ``code_puppy.callbacks`` phases, spinner updates, and messaging.

When a capability is upstreamed into pydantic-ai-harness, nothing on
this side changes except the import path of its event classes.
"""

from code_puppy.events.bridge import CapabilityEventBridge

__all__ = ["CapabilityEventBridge"]
