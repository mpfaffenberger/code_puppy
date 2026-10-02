"""MCP toolset delivery as a pydantic-ai capability.

Seventh in the capability series: promotes MCP server delivery from the
``Agent(toolsets=...)`` constructor kwarg to the first-class ``get_toolset()``
capability seam. Only *delivery* moves — server discovery
(``load_mcp_servers``), bound-server autostart, and collision filtering
(``filter_conflicting_mcp_tools``) are untouched and still run before this
capability is constructed.

Parity notes (verified against pydantic-ai 2.31.0 source):

* ``Agent.__aenter__`` enters ``_get_toolset()``, which includes
  capability-contributed toolsets — MCP server lifecycle is identical.
* ``Agent.override(toolsets=...)`` skips ``_cap_toolsets`` exactly as it
  skips constructor ``_user_toolsets`` — same replace semantics. This is
  what keeps the DBOS durable wrapper working: ``DBOSAgent`` reads the
  public ``agent.toolsets`` property (which includes capability toolsets),
  dbosifies them, and overrides them in per run.
* The ``toolsets=`` kwarg splits its input: ``AbstractToolset`` instances
  become ``_user_toolsets`` (in order), everything else is wrapped in
  ``DynamicToolset(toolset_func=...)`` and appended after. ``get_toolset()``
  returns a single toolset, so this capability replicates that split-then-
  wrap normalization itself before combining.
* Ordering divergence (inert): capability toolsets append *after*
  constructor/dynamic toolsets in ``_build_toolset_list``. MCP servers are
  the only toolsets code_puppy delivers, so the combined run toolset is
  identical; name conflicts raise either way.

Not spec-constructible (``get_serialization_name() -> None``): the servers
are live toolsets backed by subprocesses/HTTP clients owned by the MCP
manager — same precedent as the other live-object capabilities in the
series.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import AbstractToolset, CombinedToolset, DynamicToolset


@dataclass
class McpToolsets(AbstractCapability[Any]):
    """Deliver pre-filtered MCP server toolsets via ``get_toolset()``.

    ``servers`` is the exact list previously passed to
    ``Agent(toolsets=...)`` — post collision-filter on the main path,
    unfiltered on the sub-agent path (parity with what each call site did
    before).
    """

    servers: List[Any] = field(default_factory=list)

    # Built once so repeated ``get_toolset()`` calls (init-time snapshot,
    # any per-run re-extraction) hand pydantic-ai the same object identity —
    # matching the constructor, which stores its toolsets exactly once.
    _toolset: Optional[AbstractToolset[Any]] = field(
        init=False, repr=False, compare=False, default=None
    )

    def __post_init__(self) -> None:
        self._toolset = _combine(self.servers)

    @classmethod
    def get_serialization_name(cls) -> Optional[str]:
        return None  # Live MCP toolsets — not spec-constructible.

    def get_toolset(self) -> Optional[AbstractToolset[Any]]:
        return self._toolset


def _combine(servers: List[Any]) -> Optional[AbstractToolset[Any]]:
    """Normalize ``servers`` the way ``Agent(toolsets=...)`` did, as one toolset.

    The constructor keeps ``AbstractToolset`` instances (in order) and wraps
    anything else in ``DynamicToolset(toolset_func=...)`` appended after —
    ``filter_conflicting_mcp_tools`` deliberately passes non-toolset objects
    through, so we preserve that defensive tolerance here too.
    """
    static = [s for s in servers if isinstance(s, AbstractToolset)]
    dynamic = [
        DynamicToolset(toolset_func=s)
        for s in servers
        if not isinstance(s, AbstractToolset)
    ]
    toolsets: List[AbstractToolset[Any]] = [*static, *dynamic]
    if not toolsets:
        return None
    if len(toolsets) == 1:
        return toolsets[0]
    return CombinedToolset(toolsets)
