"""Compatibility shim.

The real implementation lives at :mod:`code_puppy.subagent_context` — a
top-level, stdlib-only module. It was moved out of :mod:`code_puppy.tools`
because importing anything from ``code_puppy.tools`` forces Python to
execute ``code_puppy/tools/__init__.py``, which eagerly imports the full
tool registry (browser -> playwright, image_tools -> PIL, agent_tools ->
rapidfuzz, and dozens more). That import chain was the single largest
source of Code Puppy's cold-start cost.

``subagent_context`` has no reason to be coupled to the tool registry —
it's pure ``contextvars`` bookkeeping. Callers should prefer the new
canonical location:

    from code_puppy.subagent_context import is_subagent  # preferred

This shim is retained so existing external plugin authors (and tests
that patch this exact string path) keep working. Prefer the canonical
location for new code.

Note: only the public API (``__all__``) is re-exported. The private
``_subagent_*`` ContextVar objects are intentionally NOT re-exported —
reach into them via :mod:`code_puppy.subagent_context` directly if you
really need to poke at internals.
"""

from code_puppy.subagent_context import (  # noqa: F401
    get_subagent_chain,
    get_subagent_depth,
    get_subagent_model_name,
    get_subagent_name,
    is_subagent,
    subagent_context,
)

__all__ = [
    "subagent_context",
    "is_subagent",
    "get_subagent_name",
    "get_subagent_chain",
    "get_subagent_depth",
    "get_subagent_model_name",
]
