"""Base agent class — a thin conductor delegating to focused helpers.

The real logic lives in sibling modules:
    * ``_history``     — token estimation, hashing, orphan pruning
    * ``_compaction``  — summarization/truncation + history processor factory
    * ``_builder``     — pydantic-ai agent construction + MCP wiring
    * ``_runtime``     — ``run_with_mcp`` orchestration, cancellation, retries
    * ``_key_listeners`` — Ctrl+X / cancel-agent keyboard listener threads

Keep this file under 300 lines. If it's growing, the new logic probably
belongs in one of the helpers above (or a new one).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Set

import pydantic_ai.models

from code_puppy.agents._builder import (
    build_pydantic_agent,
    build_tool_probe_for_agent,
    reload_mcp_servers,
)
from code_puppy.agents._history import (
    estimate_context_overhead,
    estimate_tokens_for_message,
    hash_message,
)
from code_puppy.agents._runtime import run_with_mcp, should_retry_streaming
from code_puppy.config import (
    get_agent_pinned_model,
    get_global_model_name,
)
from code_puppy.model_factory import ModelFactory

# Backward-compat alias: existing tests import this name directly.
should_retry_streaming_exception = should_retry_streaming

__all__ = ["BaseAgent", "should_retry_streaming_exception"]


def _iter_function_toolsets(node: Any):
    """Yield every ``FunctionToolset`` reachable from a toolset ``node``.

    Capability-delivered toolsets (``NativeTools`` via ``get_toolset()``)
    surface on the agent's public ``toolsets`` property wrapped in
    ``CombinedToolset``/``CapabilityOwnedToolset`` chains; combined nodes
    expose ``.toolsets`` and wrapper nodes expose ``.wrapped``. Recurse
    through both.
    """
    from pydantic_ai.toolsets import FunctionToolset

    if isinstance(node, FunctionToolset):
        yield node
    for child in getattr(node, "toolsets", None) or []:
        yield from _iter_function_toolsets(child)
    wrapped = getattr(node, "wrapped", None)
    if wrapped is not None:
        yield from _iter_function_toolsets(wrapped)


def _extract_pydantic_agent_tools(pyd_agent: Any) -> Optional[Dict[str, Any]]:
    """Return the registered tool dict for a pydantic-ai agent, or None.

    Walks the agent's public ``toolsets`` property, which covers both the
    internal function toolset (legacy ``@agent.tool`` registration) and the
    ``NativeTools`` capability toolset (``get_toolset()`` delivery). Falls
    back to the direct ``agent._function_toolset`` read, then the legacy
    ``agent._tools`` attribute, so older pydantic-ai versions (and mocked
    agents in tests) still work. Returns ``None`` when nothing is populated.

    Deliberately broad: any ``FunctionToolset``-shaped constructor toolset
    is included too, which could in principle double-count with the
    separate ``mcp_servers=`` estimator input -- acceptable slack for a
    best-effort context-overhead estimate (real MCP servers are not
    ``FunctionToolset``s).
    """
    if pyd_agent is None:
        return None
    tools: Dict[str, Any] = {}
    try:
        for node in getattr(pyd_agent, "toolsets", None) or []:
            for fts in _iter_function_toolsets(node):
                tools.update(getattr(fts, "tools", None) or {})
    except Exception:
        # Best-effort estimator input -- fall through to the direct reads.
        tools = {}
    if tools:
        return tools
    fts = getattr(pyd_agent, "_function_toolset", None)
    if fts is not None:
        direct = getattr(fts, "tools", None)
        if direct:
            return direct
    legacy = getattr(pyd_agent, "_tools", None)
    return legacy or None


class BaseAgent(ABC):
    """Abstract base for all Code Puppy agents."""

    def __init__(self) -> None:
        self.id: str = str(uuid.uuid4())
        self._message_history: List[Any] = []
        self._compacted_message_hashes: Set[str] = set()
        self._code_generation_agent: Any = None
        self._last_model_name: Optional[str] = None
        self._runtime_model_name_override: Optional[str] = None
        self._runtime_system_prompt_additions: List[str] = []
        # Model chosen by a ``model_select`` hook for the current run. Slots
        # below an explicit runtime override but above pinned/JSON/global, and
        # is reset at the start of every run (see resolve_run_model_selection),
        # so it never leaks across turns.
        self._auto_model_override: Optional[str] = None
        self._puppy_rules: Optional[str] = None
        self._mcp_servers: List[Any] = []
        self.cur_model: Optional[pydantic_ai.models.Model] = None
        self.pydantic_agent: Any = None
        # Cached probe agent for tool-overhead counting before the real build;
        # keyed by ``_last_model_name`` so model swaps invalidate it.
        self._tool_probe_agent: Any = None
        self._probe_model_name: Optional[str] = None

    # ---- Abstract interface ------------------------------------------------
    @property
    @abstractmethod
    def name(self) -> str:
        """Stable machine identifier (e.g. ``python-programmer``)."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in UIs."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line summary of what this agent does."""

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the agent's system prompt (identity is appended separately)."""

    @abstractmethod
    def get_available_tools(self) -> List[str]:
        """Return the list of tool names this agent should register."""

    # ---- Optional overrides ------------------------------------------------
    def get_tools_config(self) -> Optional[Dict[str, Any]]:
        return None

    def get_user_prompt(self) -> Optional[str]:
        return None

    def get_runtime_model_name_override(self) -> Optional[str]:
        """Return a temporary per-run model override, if one is active."""
        return self._runtime_model_name_override

    def set_runtime_model_name_override(self, model_name: Optional[str]) -> None:
        """Set a temporary per-run model override.

        This is intentionally not persisted. It lets orchestration code run an
        agent on a specific model for one invocation without mutating global,
        pinned, or JSON agent model configuration.
        """
        self._runtime_model_name_override = model_name

    def get_auto_model_override(self) -> Optional[str]:
        """Return the model chosen by a ``model_select`` hook for this run."""
        return self._auto_model_override

    def set_auto_model_override(self, model_name: Optional[str]) -> None:
        """Set the ``model_select``-chosen model for this run (not persisted)."""
        self._auto_model_override = model_name

    @contextmanager
    def temporary_model_name_override(
        self, model_name: Optional[str]
    ) -> Iterator[None]:
        """Temporarily apply a per-run model override within a scoped block."""
        previous_model_name = self.get_runtime_model_name_override()
        try:
            self.set_runtime_model_name_override(model_name)
            yield
        finally:
            self.set_runtime_model_name_override(previous_model_name)

    @contextmanager
    def temporary_system_prompt_addition(self, prompt: str) -> Iterator[None]:
        """Append a system instruction for the duration of one scoped run."""
        self._runtime_system_prompt_additions.append(prompt)
        try:
            yield
        finally:
            popped = self._runtime_system_prompt_additions.pop()
            if popped != prompt:
                raise RuntimeError(
                    "Runtime system prompt additions exited out of order"
                )

    def get_model_name(self) -> Optional[str]:
        override = self.get_runtime_model_name_override()
        if override:
            return override
        auto = self.get_auto_model_override()
        if auto:
            return auto
        pinned = get_agent_pinned_model(self.name)
        return pinned if pinned else get_global_model_name()

    # ---- Identity ---------------------------------------------------------
    def get_identity(self) -> str:
        return f"{self.name}-{self.id[:6]}"

    def get_identity_prompt(self) -> str:
        return (
            f"\n\nYour ID is `{self.get_identity()}`. "
            "Use this for any tasks which require identifying yourself "
            "such as claiming task ownership or coordination with other agents."
        )

    def get_full_system_prompt(self) -> str:
        """Assemble the runtime system prompt.

        Layered as: authored prompt (``get_system_prompt``) + per-turn
        ``load_prompt`` plugin fragments + this instance's identity.

        The ``load_prompt`` fragments (live timestamp/CWD, file-permission
        rules, kennel memory, ...) and the identity ID are *runtime* concerns.
        They live here — not in ``get_system_prompt`` — so they're recomputed
        fresh every run and never get persisted into static agent definitions
        (e.g. when an agent is cloned to JSON). See ``clone_agent``.
        """
        from code_puppy import callbacks

        prompt = self.get_system_prompt()
        prompt_additions = callbacks.on_load_prompt()
        if prompt_additions:
            prompt += "\n" + "\n".join(prompt_additions)
        if self._runtime_system_prompt_additions:
            prompt += "\n" + "\n".join(self._runtime_system_prompt_additions)
        return prompt + self.get_identity_prompt()

    # ---- Message history (plain dict-level access) ------------------------
    def get_message_history(self) -> List[Any]:
        return self._message_history

    def set_message_history(self, history: List[Any]) -> None:
        self._message_history = history

    def clear_message_history(self) -> None:
        self._message_history = []
        self._compacted_message_hashes.clear()

    def append_to_message_history(self, message: Any) -> None:
        self._message_history.append(message)

    # ---- Token / context helpers ------------------------------------------
    def estimate_tokens_for_message(self, message: Any) -> int:
        return estimate_tokens_for_message(message, self.get_model_name())

    def hash_message(self, message: Any) -> str:
        return hash_message(message)

    def _get_model_context_length(self) -> int:
        """Context window for the agent's effective model (fallback: 128k)."""
        try:
            configs = ModelFactory.load_config()
            cfg = configs.get(self.get_model_name(), {})
            return int(cfg.get("context_length", 128000))
        except Exception:
            return 128000

    def _estimate_context_overhead(self) -> int:
        """Tokens used by system prompt + registered pydantic tools."""
        system_prompt = self.get_full_system_prompt()
        try:
            from code_puppy.model_utils import prepare_prompt_for_model

            prepared = prepare_prompt_for_model(
                model_name=self.get_model_name() or "",
                system_prompt=system_prompt,
                user_prompt="",
                prepend_system_to_user=False,
            )
            resolved = prepared.instructions or system_prompt
        except Exception:
            resolved = system_prompt

        tools_source = self.pydantic_agent or self._get_tool_probe()
        tools = _extract_pydantic_agent_tools(tools_source) if tools_source else None
        mcp_servers = getattr(self, "_mcp_servers", None) or None
        return estimate_context_overhead(
            resolved,
            tools,
            self.get_model_name(),
            mcp_servers=mcp_servers,
        )

    def _get_tool_probe(self) -> Any:
        """Lazily build (and cache) a tool-probe pydantic agent.

        Used so context-window estimators can count tool docs/schemas even on a
        fresh session, before the real pydantic agent has been constructed.
        The probe is invalidated whenever the agent's effective model name
        changes.
        """
        current_model = self.get_model_name()
        if (
            self._tool_probe_agent is not None
            and self._probe_model_name == current_model
        ):
            return self._tool_probe_agent
        probe = build_tool_probe_for_agent(self)
        if probe is not None:
            self._tool_probe_agent = probe
            self._probe_model_name = current_model
        return probe

    # ---- Orchestration (thin delegations) ---------------------------------
    def reload_code_generation_agent(self, message_group: Optional[str] = None) -> Any:
        return build_pydantic_agent(self, output_type=str, message_group=message_group)

    async def run_with_mcp(self, prompt: str, **kwargs: Any) -> Any:
        return await run_with_mcp(self, prompt, **kwargs)

    # ---- MCP integration shims --------------------------------------------
    def update_mcp_tool_cache_sync(self) -> None:
        """Best-effort warm of each MCP toolset's tool-definition cache.

        Pydantic-ai caches MCP tool defs on each toolset after the first
        ``list_tools()`` call. We piggy-back on that cache for context-window
        overhead estimates (see ``_history._estimate_mcp_tool_tokens``).

        Without this warm-up the cache stays empty until the first agent run,
        so the ``/context`` badge under-reports MCP overhead right after
        ``/mcp start``. Here we schedule ``list_tools()`` for any server that
        looks running, but we never block and we swallow all errors — the
        cache will eventually be populated by the agent run itself.
        """
        import asyncio

        servers = getattr(self, "_mcp_servers", None) or []
        if not servers:
            return None

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return None
        if loop is None or not loop.is_running():
            return None

        async def _warm(server: Any) -> None:
            from code_puppy.mcp_.toolset_utils import toolset_is_running, unwrap_toolset

            try:
                leaf = unwrap_toolset(server)
                if getattr(leaf, "_cached_tools", None):
                    return
                if not toolset_is_running(leaf):
                    return
                await leaf.list_tools()
            except Exception:
                # Cache stays empty; estimator handles that gracefully.
                return

        for server in servers:
            try:
                loop.create_task(_warm(server))
            except Exception:
                continue
        return None

    def reload_mcp_servers(self) -> List[Any]:
        return reload_mcp_servers(agent_name=self.name)
