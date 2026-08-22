"""OpenTelemetry/Logfire tracing as a first-class pydantic-ai capability.

Historically, opting into observability (``observability.configure_logfire``)
called ``logfire.instrument_pydantic_ai()``, which sets the *process-global*
``Agent.instrument_all(settings)`` default. Every agent run then received an
``Instrumentation`` capability injected by pydantic-ai's run layer.

This module promotes that implicit delivery to an explicit one for the agents
code_puppy itself constructs: :func:`build_instrumentation` snapshots the
effective global settings at build time and returns a stock
:class:`pydantic_ai.capabilities.Instrumentation` capability carrying the
*same* ``InstrumentationSettings`` object logfire installed. The run layer
skips its own injection when an explicit ``Instrumentation`` capability is
present ("explicit-capability-wins"), so spans are identical — same settings,
same tracer provider, same ``outermost`` ordering (``Instrumentation.
get_ordering()`` sorts it outermost regardless of list position).

**The global default is deliberately NOT removed.** Two reasons:

1. Out-of-tree agents. Plugins construct their own raw pydantic-ai agents
   (e.g. wiggum's judge, btw's side-query) and get spans purely from
   ``Agent.instrument_all``. Dropping the global would silently kill their
   telemetry.
2. ``ctx.tracer`` consistency. In the classic ``run``/``iter`` path,
   pydantic-ai resolves the run context's tracer from the *global/instance*
   settings before explicit capabilities are considered (realtime sessions
   additionally consult an explicit capability's settings — same object
   here either way). Keeping both in sync means capabilities and toolsets
   observing ``ctx.tracer`` see the real tracer, never a ``NoOpTracer``.

Observable divergence (documented + pinned by tests): the capability is a
build-time snapshot, while the global default is read per run. If something
called ``Agent.instrument_all(False)`` *after* an agent was built, that agent
would keep tracing until rebuilt (previously it would go quiet on the next
run). Nothing in code_puppy or its plugins flips the default after startup —
``configure_logfire`` runs once, before the first agent build. The inverse
direction degrades to exact old behaviour: an agent built *before* logfire
configuration carries no capability, so the run-layer fallback instruments it
from the global default just like before.

``Agent._instrument_default`` is private, but it is the only source of the
exact settings object logfire installed — re-deriving settings here would
duplicate logfire's shim and drift. pydantic-ai's own ``direct.py`` reads the
same attribute. A contract test pins the attribute name so a pydantic-ai bump
that renames it fails loudly; at runtime a missing attribute degrades to "no
explicit capability", which the run-layer fallback covers.
"""

from __future__ import annotations

from typing import List

from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.capabilities import Instrumentation


def _effective_default_settings():
    """Resolve the effective global instrumentation settings, or ``None``.

    Mirrors ``Agent._resolve_instrumentation_settings`` for the class-level
    default: ``False``/unset → ``None``; ``True`` → default-constructed
    ``InstrumentationSettings``; otherwise the installed settings object
    itself (what ``logfire.instrument_pydantic_ai()`` put there).
    """
    instrument = getattr(PydanticAgent, "_instrument_default", False)
    if not instrument:
        return None
    if instrument is True:
        from pydantic_ai.models.instrumented import InstrumentationSettings

        return InstrumentationSettings()
    return instrument


def build_instrumentation() -> List[Instrumentation]:
    """Return the explicit tracing capability for one agent construction.

    Returns a single-element list when the process has been instrumented
    (``configure_logfire`` opted in), else an empty list — splat it into the
    ``capabilities=[...]`` block. List position is inert: the capability
    declares ``position='outermost'`` ordering, exactly where the run layer
    would have injected it.
    """
    settings = _effective_default_settings()
    if settings is None:
        return []
    return [Instrumentation(settings=settings)]
