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
from typing import Any, Dict, List, Optional, Set

import pydantic_ai.models

from code_puppy.agents._builder import (
    build_pydantic_agent,
    reload_mcp_servers,
)
from code_puppy.agents._compaction import summarize
from code_puppy.agents._history import (
    estimate_context_overhead,
    estimate_tokens_for_message,
    hash_message,
)
from code_puppy.agents._runtime import run_with_mcp, should_retry_streaming
from code_puppy.config import (
    get_agent_pinned_model,
    get_global_model_name,
    get_protected_token_count,
)
from code_puppy.model_factory import ModelFactory

# Backward-compat alias: existing tests import this name directly.
should_retry_streaming_exception = should_retry_streaming

__all__ = ["BaseAgent", "should_retry_streaming_exception"]


class BaseAgent(ABC):
    """Abstract base for all Code Puppy agents."""

    def __init__(self) -> None:
        self.id: str = str(uuid.uuid4())
        self._message_history: List[Any] = []
        self._compacted_message_hashes: Set[int] = set()
        self._code_generation_agent: Any = None
        self._last_model_name: Optional[str] = None
        self._puppy_rules: Optional[str] = None
        self._mcp_servers: List[Any] = []
        self.cur_model: Optional[pydantic_ai.models.Model] = None
        self.pydantic_agent: Any = None

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

    def get_model_name(self) -> Optional[str]:
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
        return self.get_system_prompt() + self.get_identity_prompt()

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

    def hash_message(self, message: Any) -> int:
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

        tools = (
            getattr(self.pydantic_agent, "_tools", None)
            if self.pydantic_agent
            else None
        )
        return estimate_context_overhead(resolved, tools, self.get_model_name())

    # ---- Orchestration (thin delegations) ---------------------------------
    def summarize_messages(
        self,
        messages: List[Any],
        with_protection: bool = True,
    ) -> tuple[list, list]:
        """Delegate to ``_compaction.summarize`` with config-derived protection."""
        return summarize(
            messages,
            get_protected_token_count(),
            with_protection=with_protection,
            model_name=self.get_model_name(),
        )

    def reload_code_generation_agent(self, message_group: Optional[str] = None) -> Any:
        return build_pydantic_agent(self, output_type=str, message_group=message_group)

    async def run_with_mcp(self, prompt: str, **kwargs: Any) -> Any:
        return await run_with_mcp(self, prompt, **kwargs)

    # ---- MCP integration shims --------------------------------------------
    def update_mcp_tool_cache_sync(self) -> None:
        """No-op. MCP token-overhead cache was deleted in the refactor;
        retained so MCP start/stop commands don't need edits yet."""
        return None

    def reload_mcp_servers(self) -> List[Any]:
        return reload_mcp_servers(agent_name=self.name)
