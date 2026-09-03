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


def _extract_pydantic_agent_tools(pyd_agent: Any) -> Optional[Dict[str, Any]]:
    """Return the registered tool dict for a pydantic-ai agent, or None.

    Handles the modern shape (``agent._function_toolset.tools``) and falls
    back to the legacy ``agent._tools`` attribute so older pydantic-ai
    versions still work. Returns ``None`` when neither is populated.
    """
    if pyd_agent is None:
        return None
    fts = getattr(pyd_agent, "_function_toolset", None)
    if fts is not None:
        tools = getattr(fts, "tools", None)
        if tools:
            return tools
    legacy = getattr(pyd_agent, "_tools", None)
    return legacy or None


HEADLESS_AUTONOMY_PROMPT = """\
This is an unattended, non-interactive run. Never ask for confirmation, approval,
clarification, or manual verification, including through tools or MCP servers. Use
reasonable defaults, proceed autonomously, and validate with the tools available to
you. State any assumptions or optional manual checks only in the final response.\
"""
"""Scoped instruction for an unattended run, applied by the headless entry point.

Defined here rather than in ``cli_runner`` because the prompt assembler has to
recognise it: earlier builds wrote it INSIDE the durable part of the
prompt, and ``set_message_history`` has to undo that. One definition, so the
text the CLI applies and the text a resume heals cannot drift apart.
"""


class BaseAgent(ABC):
    """Abstract base for all Code Puppy agents."""

    def __init__(self) -> None:
        self.id: str = str(uuid.uuid4())
        self._message_history: List[Any] = []
        # ``load_prompt`` fragments as this conversation opened with them.
        # ``None`` means "not gathered yet"; an empty list is a real answer
        # (no plugin contributed) and must not re-trigger a gather.
        # See ``get_full_system_prompt`` for why these are frozen per
        # conversation rather than recomputed per turn.
        self._standing_prompt_additions: Optional[List[str]] = None
        # The system prompt a RESUMED conversation was built with, adopted
        # verbatim so the provider's cache prefix survives the resume.
        # ``None`` means this agent is not resuming anything.
        self._adopted_prompt_body: Optional[str] = None
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

    def get_model_settings_overrides(self) -> Dict[str, Any]:
        """Return request-setting overrides scoped to this agent.

        Values use the same setting names as ``/model_settings`` and take
        precedence over global and per-model standard settings. Unsupported
        settings are filtered for the effective model before requests run.
        """
        return {}

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

        Fragments are gathered ONCE PER CONVERSATION, not once per turn.
        pydantic-ai stamps this string into ``instructions`` on every request,
        and ``instructions`` is the provider's cache prefix — so a fragment
        that changes between turns invalidates the cache on every turn. A
        memory/recall plugin is the worst case: it recalls what the previous
        turn wrote, so it grows precisely as the conversation gets long enough
        for caching to matter. Measured on one such thread, the block went
        5571 → 6129 characters between turn 1 and turn 2, missing the cache
        each time.

        The system prompt is the CONTRACT and does not change mid-conversation;
        recall is CONTEXT and belongs in the message stream. Keeping the prefix
        fixed is what makes a long conversation affordable.

        Gathered on the first call and reused thereafter, rather than keyed on
        whether history exists: the setup path calls this more than once before
        any history does, so a history-keyed cache would still re-poll and
        still drift, only earlier. ``clear_message_history`` (i.e. ``/clear``)
        is the one reset — the prefix is allowed to change exactly when the
        conversation does.
        """
        from code_puppy import callbacks

        # A resumed conversation already has a prompt BODY, and it is
        # authoritative: it is what the provider cached and what every stored
        # message was sent under, and recomputing it would drift. The identity
        # line is not part of it -- see ``set_message_history`` for why.
        #
        # It replaces the authored prompt and the standing fragments; it does
        # NOT replace the runtime additions below. Those are scoped to THIS
        # run, so a resumed conversation must still get them -- returning here
        # would silently drop the headless autonomy instruction on every
        # `code-puppy -p` against an existing session.
        if self._adopted_prompt_body is not None:
            prompt = self._adopted_prompt_body
        else:
            prompt = self.get_system_prompt()
            # Gathered on the FIRST call and reused thereafter, not merely on
            # turns after the first. The setup path calls this more than once
            # before any history exists -- `_estimate_context_overhead` is one
            # such caller -- so keying on "history is empty" would still
            # re-poll and still drift, just earlier. Measured on this branch
            # before the fix: 2 polls and a changed prompt before turn one had
            # run.
            #
            # `None` means "not gathered yet"; `[]` is a real answer meaning no
            # plugin contributed, and conflating them re-polls forever for
            # conversations that have no fragments. Reset by
            # `clear_message_history`, which is the one moment a new
            # conversation legitimately begins.
            if self._standing_prompt_additions is None:
                self._standing_prompt_additions = callbacks.on_load_prompt()
            prompt_additions = self._standing_prompt_additions
            if prompt_additions:
                prompt += "\n" + "\n".join(prompt_additions)
        prompt += self.get_identity_prompt()
        # Runtime additions go AFTER the identity line, which makes them
        # unadoptable by construction: ``_strip_identity_prompt`` keeps only
        # the text BEFORE that marker, so scoped text cannot survive into the
        # next conversation's cached prefix. It also leaves the durable part
        # (body + identity) as a maximal stable prefix, which is what the
        # provider actually caches.
        #
        # The ordering matters because the headless loop calls
        # ``set_message_history`` after the scoped block has already exited:
        # the list is empty by then, so nothing on this object can tell the
        # resume which bytes were ephemeral. Position is the only reliable
        # signal, and it survives the trip through storage into another
        # process.
        if self._runtime_system_prompt_additions:
            prompt += "\n" + "\n".join(self._runtime_system_prompt_additions)
        return prompt

    # ---- Message history (plain dict-level access) ------------------------
    def get_message_history(self) -> List[Any]:
        return self._message_history

    def set_message_history(
        self, history: List[Any], *, agent_id: Optional[str] = None
    ) -> None:
        """Adopt ``history``, and with it the conversation's prompt and id.

        This is the resume door. Every front door that continues a
        conversation arrives here -- the CLI through
        ``restore_named_session``, an embedding runner by calling it
        directly, a headless loop that rebuilds an agent per turn -- so
        resume behaviour belongs here rather than in any one caller. Putting
        it in a caller fixes exactly that caller, which is how an earlier
        attempt at this passed its own tests while every other front end was
        unchanged.

        Non-empty history means a conversation is being resumed:

        * Its opening ``instructions`` become this agent's system prompt.
          pydantic-ai stamps the prompt onto every request message, so the
          history knows what it was built with, and that string is the
          provider's cache prefix. Recomputing it in a fresh process yields
          a different one -- a live timestamp, a grown recall block -- and
          the cache then misses on every turn of a long conversation, which
          is exactly when it was worth having.
        * ``agent_id``, when the caller knows it, replaces the uuid minted
          in ``__init__``. It is not in the history, so it has to be passed;
          the prompt tells the agent to use its id "for claiming task
          ownership or coordination with other agents", and an id minted per
          process cannot own anything.

        Setting an empty history is not a resume: nothing is adopted, and
        the agent keeps its own identity and computes its own prompt.
        """
        self._message_history = history
        if not history:
            return
        if agent_id:
            self.id = agent_id
        prior = self._opening_instructions(history)
        if prior:
            # Adopt the BODY, not the whole string. ``get_identity_prompt`` is
            # appended last and is a pure function of ``self.id``, so keeping
            # it out of the frozen text leaves exactly one representation of
            # the identity -- the field -- instead of a field plus a copy
            # rendered into English that the two could drift apart on.
            #
            # The alternative, recovering the id by matching the rendered
            # sentence, closes the gap and opens worse ones: the line shows
            # six characters of a uuid, so the round trip is lossy, and the
            # wording of a user-facing sentence becomes load-bearing -- a
            # translation or a reword would silently corrupt identity.
            #
            # Nothing is lost by excluding it. The body is what drifted (live
            # timestamps, a growing recall block); the identity line is stable
            # by construction once the id is, so re-rendering it yields the
            # same bytes and the cache prefix still holds.
            self._adopted_prompt_body = self._heal_legacy_body(
                self._strip_identity_prompt(prior)
            )

    @staticmethod
    def _heal_legacy_body(body: str) -> str:
        """``body`` without a scoped addition an older build froze into it.

        Earlier builds appended runtime additions BEFORE the identity line, so in a session saved by one of those the autonomy instruction
        sits inside the durable body and the ordering fix cannot reach it.
        Adopting it verbatim re-applies it to every later turn -- including
        interactive ones, which would tell a user's own session never to ask
        them for confirmation, with ``/clear`` as the only escape.

        Measured on a session written in the legacy layout: present on turns
        2, 3, 4 and 5 of an interactive resume.

        Removing the exact known string is deliberately narrow. Anything
        looser -- a heuristic, a marker, a regex over prompt prose -- would
        risk eating authored text that merely resembles it, and the whole
        design already refuses to make user-facing wording load-bearing. A
        prompt that never contained it is returned unchanged, so this costs
        nothing once the old sessions age out.
        """
        return body.replace("\n" + HEADLESS_AUTONOMY_PROMPT, "").replace(
            HEADLESS_AUTONOMY_PROMPT, ""
        )

    def _strip_identity_prompt(self, prompt: str) -> str:
        """``prompt`` without the trailing identity line this class appends.

        Splits on the marker rather than recomputing the suffix for THIS
        agent: the stored prompt carries the id of the conversation, which is
        not necessarily the uuid this process minted, so
        ``removesuffix(self.get_identity_prompt())`` would silently fail to
        strip and re-introduce the duplication this avoids.

        A prompt with no identity line -- from another tool, or an older
        version -- is returned unchanged.
        """
        marker = "\n\nYour ID is `"
        head, sep, _ = prompt.rpartition(marker)
        return head if sep else prompt

    @staticmethod
    def _opening_instructions(history: List[Any]) -> Optional[str]:
        """The system prompt the first request in ``history`` was sent with.

        Reads the FIRST request rather than the last: the opener is the
        prefix every later message was cached against, and a later message
        may carry a prompt that had already drifted. Tolerant of shape --
        histories arrive as pydantic-ai objects or as plain dicts depending
        on the caller, and a resume must not fail over an attribute.
        """
        for message in history:
            if isinstance(message, dict):
                instructions = message.get("instructions")
            else:
                instructions = getattr(message, "instructions", None)
            if isinstance(instructions, str) and instructions:
                return instructions
        return None

    def clear_message_history(self) -> None:
        self._message_history = []
        # A new conversation gets fresh fragments and drops any prompt
        # adopted from the old one: this is the single moment the cache
        # prefix is meant to change.
        self._standing_prompt_additions = None
        self._adopted_prompt_body = None
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
            resolved = prepared.system_text or system_prompt
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
    def transform_mcp_toolsets(self, toolsets: List[Any]) -> List[Any]:
        """Extension seam: post-process resolved MCP toolsets before build.

        Called exactly once by ``_builder.build_pydantic_agent`` after MCP
        toolsets have been resolved and filtered for tool-name collisions,
        but before the final ``pydantic_ai.Agent`` is constructed. The
        default implementation is a no-op identity transform. Subclasses may
        override this to wrap, filter, or replace toolsets -- for example to
        compact oversized tool results, or gate certain servers behind
        runtime conditions.

        Must return a list of toolsets; the builder fails open on a raise
        or a non-list return (falls back to the pre-override list), so
        gating logic that must never be bypassed should fail closed itself
        (e.g. return an empty list) rather than rely on that fallback.
        """
        return toolsets

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
