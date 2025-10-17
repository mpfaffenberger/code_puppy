"""Base agent configuration class for defining agent properties."""

import asyncio
import json
import math
import signal
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from dbos import DBOS, SetWorkflowID
import mcp
import pydantic
import pydantic_ai.models
from pydantic_ai import Agent as PydanticAgent
from pydantic_ai import BinaryContent, DocumentUrl, ImageUrl
from pydantic_ai import RunContext, UsageLimitExceeded, UsageLimits
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    TextPart,
    ToolCallPart,
    ToolCallPartDelta,
    ToolReturn,
    ToolReturnPart,
)
from pydantic_ai.models.openai import OpenAIChatModelSettings
from pydantic_ai.settings import ModelSettings
from pydantic_ai.durable_exec.dbos import DBOSAgent

# Consolidated relative imports
from code_puppy.config import (
    USE_DBOS,
    get_agent_pinned_model,
    get_compaction_strategy,
    get_compaction_threshold,
    get_global_model_name,
    get_openai_reasoning_effort,
    get_protected_token_count,
    get_value,
    load_mcp_server_configs,
    get_message_limit,
)
from code_puppy.mcp_ import ServerConfig, get_mcp_manager
from code_puppy.messaging import (
    emit_error,
    emit_info,
    emit_system_message,
    emit_warning,
)
from code_puppy.messaging.spinner import (
    SpinnerBase,
    update_spinner_context,
)
from code_puppy.model_factory import ModelFactory
from code_puppy.summarization_agent import run_summarization_sync
from code_puppy.tools.common import console

_reload_count = 0


class BaseAgent(ABC):
    """Base class for all agent configurations."""

    def __init__(self):
        self.id = str(uuid.uuid4())
        self._message_history: List[Any] = []
        self._compacted_message_hashes: Set[str] = set()
        # Agent construction cache
        self._code_generation_agent = None
        self._last_model_name: Optional[str] = None
        # Puppy rules loaded lazily
        self._puppy_rules: Optional[str] = None
        self.cur_model: pydantic_ai.models.Model

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for the agent."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for the agent."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Brief description of what this agent does."""
        pass

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Get the system prompt for this agent."""
        pass

    @abstractmethod
    def get_available_tools(self) -> List[str]:
        """Get list of tool names that this agent should have access to.

        Returns:
            List of tool names to register for this agent.
        """
        pass

    def get_tools_config(self) -> Optional[Dict[str, Any]]:
        """Get tool configuration for this agent.

        Returns:
            Dict with tool configuration, or None to use default tools.
        """
        return None

    def get_user_prompt(self) -> Optional[str]:
        """Get custom user prompt for this agent.

        Returns:
            Custom prompt string, or None to use default.
        """
        return None

    # Message history management methods
    def get_message_history(self) -> List[Any]:
        """Get the message history for this agent.

        Returns:
            List of messages in this agent's conversation history.
        """
        return self._message_history

    def set_message_history(self, history: List[Any]) -> None:
        """Set the message history for this agent.

        Args:
            history: List of messages to set as the conversation history.
        """
        self._message_history = history

    def clear_message_history(self) -> None:
        """Clear the message history for this agent."""
        self._message_history = []
        self._compacted_message_hashes.clear()

    def append_to_message_history(self, message: Any) -> None:
        """Append a message to this agent's history.

        Args:
            message: Message to append to the conversation history.
        """
        self._message_history.append(message)

    def extend_message_history(self, history: List[Any]) -> None:
        """Extend this agent's message history with multiple messages.

        Args:
            history: List of messages to append to the conversation history.
        """
        self._message_history.extend(history)

    def get_compacted_message_hashes(self) -> Set[str]:
        """Get the set of compacted message hashes for this agent.

        Returns:
            Set of hashes for messages that have been compacted/summarized.
        """
        return self._compacted_message_hashes

    def add_compacted_message_hash(self, message_hash: str) -> None:
        """Add a message hash to the set of compacted message hashes.

        Args:
            message_hash: Hash of a message that has been compacted/summarized.
        """
        self._compacted_message_hashes.add(message_hash)

    def get_model_name(self) -> Optional[str]:
        """Get pinned model name for this agent, if specified.

        Returns:
            Model name to use for this agent, or global default if none pinned.
        """
        pinned = get_agent_pinned_model(self.name)
        if pinned == "" or pinned is None:
            return get_global_model_name()
        return pinned

    def _clean_binaries(self, messages: List[ModelMessage]) -> List[ModelMessage]:
        cleaned = []
        for message in messages:
            parts = []
            for part in message.parts:
                if hasattr(part, "content") and isinstance(part.content, list):
                    content = []
                    for item in part.content:
                        if not isinstance(item, BinaryContent):
                            content.append(item)
                    part.content = content
                parts.append(part)
            cleaned.append(message)
        return cleaned

    # Message history processing methods (moved from state_management.py and message_history_processor.py)
    def _stringify_part(self, part: Any) -> str:
        """Create a stable string representation for a message part.

        We deliberately ignore timestamps so identical content hashes the same even when
        emitted at different times. This prevents status updates from blowing up the
        history when they are repeated with new timestamps."""

        attributes: List[str] = [part.__class__.__name__]

        # Role/instructions help disambiguate parts that otherwise share content
        if hasattr(part, "role") and part.role:
            attributes.append(f"role={part.role}")
        if hasattr(part, "instructions") and part.instructions:
            attributes.append(f"instructions={part.instructions}")

        if hasattr(part, "tool_call_id") and part.tool_call_id:
            attributes.append(f"tool_call_id={part.tool_call_id}")

        if hasattr(part, "tool_name") and part.tool_name:
            attributes.append(f"tool_name={part.tool_name}")

        content = getattr(part, "content", None)
        if content is None:
            attributes.append("content=None")
        elif isinstance(content, str):
            attributes.append(f"content={content}")
        elif isinstance(content, pydantic.BaseModel):
            attributes.append(
                f"content={json.dumps(content.model_dump(), sort_keys=True)}"
            )
        elif isinstance(content, dict):
            attributes.append(f"content={json.dumps(content, sort_keys=True)}")
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, str):
                    attributes.append(f"content={item}")
                if isinstance(item, BinaryContent):
                    attributes.append(f"BinaryContent={hash(item.data)}")
        else:
            attributes.append(f"content={repr(content)}")
        result = "|".join(attributes)
        return result

    def hash_message(self, message: Any) -> int:
        """Create a stable hash for a model message that ignores timestamps."""
        role = getattr(message, "role", None)
        instructions = getattr(message, "instructions", None)
        header_bits: List[str] = []
        if role:
            header_bits.append(f"role={role}")
        if instructions:
            header_bits.append(f"instructions={instructions}")

        part_strings = [
            self._stringify_part(part) for part in getattr(message, "parts", [])
        ]
        canonical = "||".join(header_bits + part_strings)
        return hash(canonical)

    def stringify_message_part(self, part) -> str:
        """
        Convert a message part to a string representation for token estimation or other uses.

        Args:
            part: A message part that may contain content or be a tool call

        Returns:
            String representation of the message part
        """
        result = ""
        if hasattr(part, "part_kind"):
            result += part.part_kind + ": "
        else:
            result += str(type(part)) + ": "

        # Handle content
        if hasattr(part, "content") and part.content:
            # Handle different content types
            if isinstance(part.content, str):
                result = part.content
            elif isinstance(part.content, pydantic.BaseModel):
                result = json.dumps(part.content.model_dump())
            elif isinstance(part.content, dict):
                result = json.dumps(part.content)
            elif isinstance(part.content, list):
                result = ""
                for item in part.content:
                    if isinstance(item, str):
                        result += item + "\n"
                    if isinstance(item, BinaryContent):
                        result += f"BinaryContent={hash(item.data)}\n"
            else:
                result = str(part.content)

        # Handle tool calls which may have additional token costs
        # If part also has content, we'll process tool calls separately
        if hasattr(part, "tool_name") and part.tool_name:
            # Estimate tokens for tool name and parameters
            tool_text = part.tool_name
            if hasattr(part, "args"):
                tool_text += f" {str(part.args)}"
            result += tool_text

        return result

    def estimate_token_count(self, text: str) -> int:
        """
        Simple token estimation using len(message) / 3.
        This replaces tiktoken with a much simpler approach.
        """
        return max(1, math.floor((len(text) / 3)))

    def estimate_tokens_for_message(self, message: ModelMessage) -> int:
        """
        Estimate the number of tokens in a message using len(message)
        Simple and fast replacement for tiktoken.
        """
        total_tokens = 0

        for part in message.parts:
            part_str = self.stringify_message_part(part)
            if part_str:
                total_tokens += self.estimate_token_count(part_str)

        return max(1, total_tokens)

    def _is_tool_call_part(self, part: Any) -> bool:
        if isinstance(part, (ToolCallPart, ToolCallPartDelta)):
            return True

        part_kind = (getattr(part, "part_kind", "") or "").replace("_", "-")
        if part_kind == "tool-call":
            return True

        has_tool_name = getattr(part, "tool_name", None) is not None
        has_args = getattr(part, "args", None) is not None
        has_args_delta = getattr(part, "args_delta", None) is not None

        return bool(has_tool_name and (has_args or has_args_delta))

    def _is_tool_return_part(self, part: Any) -> bool:
        if isinstance(part, (ToolReturnPart, ToolReturn)):
            return True

        part_kind = (getattr(part, "part_kind", "") or "").replace("_", "-")
        if part_kind in {"tool-return", "tool-result"}:
            return True

        if getattr(part, "tool_call_id", None) is None:
            return False

        has_content = getattr(part, "content", None) is not None
        has_content_delta = getattr(part, "content_delta", None) is not None
        return bool(has_content or has_content_delta)

    def filter_huge_messages(self, messages: List[ModelMessage]) -> List[ModelMessage]:
        filtered = [m for m in messages if self.estimate_tokens_for_message(m) < 50000]
        pruned = self.prune_interrupted_tool_calls(filtered)
        return pruned

    def split_messages_for_protected_summarization(
        self,
        messages: List[ModelMessage],
    ) -> Tuple[List[ModelMessage], List[ModelMessage]]:
        """
        Split messages into two groups: messages to summarize and protected recent messages.

        Returns:
            Tuple of (messages_to_summarize, protected_messages)

        The protected_messages are the most recent messages that total up to the configured protected token count.
        The system message (first message) is always protected.
        All other messages that don't fit in the protected zone will be summarized.
        """
        if len(messages) <= 1:  # Just system message or empty
            return [], messages

        # Always protect the system message (first message)
        system_message = messages[0]
        system_tokens = self.estimate_tokens_for_message(system_message)

        if len(messages) == 1:
            return [], messages

        # Get the configured protected token count
        protected_tokens_limit = get_protected_token_count()

        # Calculate tokens for messages from most recent backwards (excluding system message)
        protected_messages = []
        protected_token_count = system_tokens  # Start with system message tokens

        # Go backwards through non-system messages to find protected zone
        for i in range(
            len(messages) - 1, 0, -1
        ):  # Stop at 1, not 0 (skip system message)
            message = messages[i]
            message_tokens = self.estimate_tokens_for_message(message)

            # If adding this message would exceed protected tokens, stop here
            if protected_token_count + message_tokens > protected_tokens_limit:
                break

            protected_messages.append(message)
            protected_token_count += message_tokens

        # Messages that were added while scanning backwards are currently in reverse order.
        # Reverse them to restore chronological ordering, then prepend the system prompt.
        protected_messages.reverse()
        protected_messages.insert(0, system_message)

        # Messages to summarize are everything between the system message and the
        # protected tail zone we just constructed.
        protected_start_idx = max(1, len(messages) - (len(protected_messages) - 1))
        messages_to_summarize = messages[1:protected_start_idx]

        # Emit info messages
        emit_info(
            f"🔒 Protecting {len(protected_messages)} recent messages ({protected_token_count} tokens, limit: {protected_tokens_limit})"
        )
        emit_info(f"📝 Summarizing {len(messages_to_summarize)} older messages")

        return messages_to_summarize, protected_messages

    def summarize_messages(
        self, messages: List[ModelMessage], with_protection: bool = True
    ) -> Tuple[List[ModelMessage], List[ModelMessage]]:
        """
        Summarize messages while protecting recent messages up to PROTECTED_TOKENS.

        Returns:
            Tuple of (compacted_messages, summarized_source_messages)
            where compacted_messages always preserves the original system message
            as the first entry.
        """
        messages_to_summarize: List[ModelMessage]
        protected_messages: List[ModelMessage]

        if with_protection:
            messages_to_summarize, protected_messages = (
                self.split_messages_for_protected_summarization(messages)
            )
        else:
            messages_to_summarize = messages[1:] if messages else []
            protected_messages = messages[:1]

        if not messages:
            return [], []

        system_message = messages[0]

        if not messages_to_summarize:
            # Nothing to summarize, so just return the original sequence
            return self.prune_interrupted_tool_calls(messages), []

        instructions = (
            "The input will be a log of Agentic AI steps that have been taken"
            " as well as user queries, etc. Summarize the contents of these steps."
            " The high level details should remain but the bulk of the content from tool-call"
            " responses should be compacted and summarized. For example if you see a tool-call"
            " reading a file, and the file contents are large, then in your summary you might just"
            " write: * used read_file on space_invaders.cpp - contents removed."
            "\n Make sure your result is a bulleted list of all steps and interactions."
            "\n\nNOTE: This summary represents older conversation history. Recent messages are preserved separately."
        )

        try:
            new_messages = run_summarization_sync(
                instructions, message_history=messages_to_summarize
            )

            if not isinstance(new_messages, list):
                emit_warning(
                    "Summarization agent returned non-list output; wrapping into message request"
                )
                new_messages = [ModelRequest([TextPart(str(new_messages))])]

            compacted: List[ModelMessage] = [system_message] + list(new_messages)

            # Drop the system message from protected_messages because we already included it
            protected_tail = [
                msg for msg in protected_messages if msg is not system_message
            ]

            compacted.extend(protected_tail)

            return self.prune_interrupted_tool_calls(compacted), messages_to_summarize
        except Exception as e:
            emit_error(f"Summarization failed during compaction: {e}")
            return messages, []  # Return original messages on failure

    def get_model_context_length(self) -> int:
        """
        Return the context length for this agent's effective model.

        Honors per-agent pinned model via `self.get_model_name()`; falls back
        to global model when no pin is set. Defaults conservatively on failure.
        """
        try:
            model_configs = ModelFactory.load_config()
            # Use the agent's effective model (respects /pin_model)
            model_name = self.get_model_name()
            model_config = model_configs.get(model_name, {})
            context_length = model_config.get("context_length", 128000)
            return int(context_length)
        except Exception:
            # Be safe; don't blow up status/compaction if model lookup fails
            return 128000

    def prune_interrupted_tool_calls(
        self, messages: List[ModelMessage]
    ) -> List[ModelMessage]:
        """
        Remove any messages that participate in mismatched tool call sequences.

        A mismatched tool call id is one that appears in a ToolCall (model/tool request)
        without a corresponding tool return, or vice versa. We preserve original order
        and only drop messages that contain parts referencing mismatched tool_call_ids.
        """
        if not messages:
            return messages

        tool_call_ids: Set[str] = set()
        tool_return_ids: Set[str] = set()

        # First pass: collect ids for calls vs returns
        for msg in messages:
            for part in getattr(msg, "parts", []) or []:
                tool_call_id = getattr(part, "tool_call_id", None)
                if not tool_call_id:
                    continue
                # Heuristic: if it's an explicit ToolCallPart or has a tool_name/args,
                # consider it a call; otherwise it's a return/result.
                if part.part_kind == "tool-call":
                    tool_call_ids.add(tool_call_id)
                else:
                    tool_return_ids.add(tool_call_id)

        mismatched: Set[str] = tool_call_ids.symmetric_difference(tool_return_ids)
        if not mismatched:
            return messages

        pruned: List[ModelMessage] = []
        dropped_count = 0
        for msg in messages:
            has_mismatched = False
            for part in getattr(msg, "parts", []) or []:
                tcid = getattr(part, "tool_call_id", None)
                if tcid and tcid in mismatched:
                    has_mismatched = True
                    break
            if has_mismatched:
                dropped_count += 1
                continue
            pruned.append(msg)
        return pruned

    def message_history_processor(
        self, ctx: RunContext, messages: List[ModelMessage]
    ) -> List[ModelMessage]:
        # First, prune any interrupted/mismatched tool-call conversations
        model_max = self.get_model_context_length()

        total_current_tokens = sum(
            self.estimate_tokens_for_message(msg) for msg in messages
        )
        proportion_used = total_current_tokens / model_max

        # Check if we're in TUI mode and can update the status bar
        from code_puppy.tui_state import get_tui_app_instance, is_tui_mode

        context_summary = SpinnerBase.format_context_info(
            total_current_tokens, model_max, proportion_used
        )
        update_spinner_context(context_summary)

        if is_tui_mode():
            tui_app = get_tui_app_instance()
            if tui_app:
                try:
                    # Update the status bar instead of emitting a chat message
                    status_bar = tui_app.query_one("StatusBar")
                    status_bar.update_token_info(
                        total_current_tokens, model_max, proportion_used
                    )
                except Exception as e:
                    emit_error(e)
            else:
                emit_info(
                    f"Final token count after processing: {total_current_tokens}",
                    message_group="token_context_status",
                )
        # Get the configured compaction threshold
        compaction_threshold = get_compaction_threshold()

        # Get the configured compaction strategy
        compaction_strategy = get_compaction_strategy()

        if proportion_used > compaction_threshold:
            if compaction_strategy == "truncation":
                # Use truncation instead of summarization
                protected_tokens = get_protected_token_count()
                result_messages = self.truncation(
                    self.filter_huge_messages(messages), protected_tokens
                )
                summarized_messages = []  # No summarization in truncation mode
            else:
                # Default to summarization
                result_messages, summarized_messages = self.summarize_messages(
                    self.filter_huge_messages(messages)
                )

            final_token_count = sum(
                self.estimate_tokens_for_message(msg) for msg in result_messages
            )
            # Update status bar with final token count if in TUI mode
            final_summary = SpinnerBase.format_context_info(
                final_token_count, model_max, final_token_count / model_max
            )
            update_spinner_context(final_summary)

            if is_tui_mode():
                tui_app = get_tui_app_instance()
                if tui_app:
                    try:
                        status_bar = tui_app.query_one("StatusBar")
                        status_bar.update_token_info(
                            final_token_count, model_max, final_token_count / model_max
                        )
                    except Exception:
                        emit_info(
                            f"Final token count after processing: {final_token_count}",
                            message_group="token_context_status",
                        )
                else:
                    emit_info(
                        f"Final token count after processing: {final_token_count}",
                        message_group="token_context_status",
                    )

            self.set_message_history(result_messages)
            for m in summarized_messages:
                self.add_compacted_message_hash(self.hash_message(m))
            return result_messages
        return messages

    def truncation(
        self, messages: List[ModelMessage], protected_tokens: int
    ) -> List[ModelMessage]:
        """
        Truncate message history to manage token usage.

        Args:
            messages: List of messages to truncate
            protected_tokens: Number of tokens to protect

        Returns:
            Truncated list of messages
        """
        import queue

        emit_info("Truncating message history to manage token usage")
        result = [messages[0]]  # Always keep the first message (system prompt)
        num_tokens = 0
        stack = queue.LifoQueue()

        # Put messages in reverse order (most recent first) into the stack
        # but break when we exceed protected_tokens
        for idx, msg in enumerate(reversed(messages[1:])):  # Skip the first message
            num_tokens += self.estimate_tokens_for_message(msg)
            if num_tokens > protected_tokens:
                break
            stack.put(msg)

        # Pop messages from stack to get them in chronological order
        while not stack.empty():
            result.append(stack.get())

        result = self.prune_interrupted_tool_calls(result)
        return result

    def run_summarization_sync(
        self,
        instructions: str,
        message_history: List[ModelMessage],
    ) -> Union[List[ModelMessage], str]:
        """
        Run summarization synchronously using the configured summarization agent.
        This is exposed as a method so it can be overridden by subclasses if needed.

        Args:
            instructions: Instructions for the summarization agent
            message_history: List of messages to summarize

        Returns:
            Summarized messages or text
        """
        return run_summarization_sync(instructions, message_history)

    # ===== Agent wiring formerly in code_puppy/agent.py =====
    def load_puppy_rules(self) -> Optional[str]:
        """Load AGENT(S).md if present and cache the contents."""
        if self._puppy_rules is not None:
            return self._puppy_rules
        from pathlib import Path

        possible_paths = ["AGENTS.md", "AGENT.md", "agents.md", "agent.md"]
        for path_str in possible_paths:
            puppy_rules_path = Path(path_str)
            if puppy_rules_path.exists():
                with open(puppy_rules_path, "r") as f:
                    self._puppy_rules = f.read()
                    break
        return self._puppy_rules

    def load_mcp_servers(self, extra_headers: Optional[Dict[str, str]] = None):
        """Load MCP servers through the manager and return pydantic-ai compatible servers."""

        mcp_disabled = get_value("disable_mcp_servers")
        if mcp_disabled and str(mcp_disabled).lower() in ("1", "true", "yes", "on"):
            emit_system_message("[dim]MCP servers disabled via config[/dim]")
            return []

        manager = get_mcp_manager()
        configs = load_mcp_server_configs()
        if not configs:
            existing_servers = manager.list_servers()
            if not existing_servers:
                emit_system_message("[dim]No MCP servers configured[/dim]")
                return []
        else:
            for name, conf in configs.items():
                try:
                    server_config = ServerConfig(
                        id=conf.get("id", f"{name}_{hash(name)}"),
                        name=name,
                        type=conf.get("type", "sse"),
                        enabled=conf.get("enabled", True),
                        config=conf,
                    )
                    existing = manager.get_server_by_name(name)
                    if not existing:
                        manager.register_server(server_config)
                        emit_system_message(f"[dim]Registered MCP server: {name}[/dim]")
                    else:
                        if existing.config != server_config.config:
                            manager.update_server(existing.id, server_config)
                            emit_system_message(
                                f"[dim]Updated MCP server: {name}[/dim]"
                            )
                except Exception as e:
                    emit_error(f"Failed to register MCP server '{name}': {str(e)}")
                    continue

        servers = manager.get_servers_for_agent()
        if servers:
            emit_system_message(
                f"[green]Successfully loaded {len(servers)} MCP server(s)[/green]"
            )
        # Stay silent when there are no servers configured/available
        return servers

    def reload_mcp_servers(self):
        """Reload MCP servers and return updated servers."""
        self.load_mcp_servers()
        manager = get_mcp_manager()
        return manager.get_servers_for_agent()

    def _load_model_with_fallback(
        self,
        requested_model_name: str,
        models_config: Dict[str, Any],
        message_group: str,
    ) -> Tuple[Any, str]:
        """Load the requested model, applying a friendly fallback when unavailable."""
        try:
            model = ModelFactory.get_model(requested_model_name, models_config)
            return model, requested_model_name
        except ValueError as exc:
            available_models = list(models_config.keys())
            available_str = (
                ", ".join(sorted(available_models))
                if available_models
                else "no configured models"
            )
            emit_warning(
                (
                    f"[yellow]Model '{requested_model_name}' not found. "
                    f"Available models: {available_str}[/yellow]"
                ),
                message_group=message_group,
            )

            fallback_candidates: List[str] = []
            global_candidate = get_global_model_name()
            if global_candidate:
                fallback_candidates.append(global_candidate)

            for candidate in available_models:
                if candidate not in fallback_candidates:
                    fallback_candidates.append(candidate)

            for candidate in fallback_candidates:
                if not candidate or candidate == requested_model_name:
                    continue
                try:
                    model = ModelFactory.get_model(candidate, models_config)
                    emit_info(
                        f"[bold cyan]Using fallback model: {candidate}[/bold cyan]",
                        message_group=message_group,
                    )
                    return model, candidate
                except ValueError:
                    continue

            friendly_message = (
                "No valid model could be loaded. Update the model configuration or set "
                "a valid model with `config set`."
            )
            emit_error(
                f"[bold red]{friendly_message}[/bold red]",
                message_group=message_group,
            )
            raise ValueError(friendly_message) from exc

    def reload_code_generation_agent(self, message_group: Optional[str] = None):
        """Force-reload the pydantic-ai Agent based on current config and model."""
        from code_puppy.tools import register_tools_for_agent

        if message_group is None:
            message_group = str(uuid.uuid4())

        model_name = self.get_model_name()

        emit_info(
            f"[bold cyan]Loading Model: {model_name}[/bold cyan]",
            message_group=message_group,
        )
        models_config = ModelFactory.load_config()
        model, resolved_model_name = self._load_model_with_fallback(
            model_name,
            models_config,
            message_group,
        )

        emit_info(
            f"[bold magenta]Loading Agent: {self.name}[/bold magenta]",
            message_group=message_group,
        )

        instructions = self.get_system_prompt()
        puppy_rules = self.load_puppy_rules()
        if puppy_rules:
            instructions += f"\n{puppy_rules}"

        mcp_servers = self.load_mcp_servers()

        model_settings_dict: Dict[str, Any] = {"seed": 42}
        output_tokens = max(
            2048,
            min(int(0.05 * self.get_model_context_length()) - 1024, 16384),
        )
        console.print(f"Max output tokens per message: {output_tokens}")
        model_settings_dict["max_tokens"] = output_tokens

        model_settings: ModelSettings = ModelSettings(**model_settings_dict)
        if "gpt-5" in model_name:
            model_settings_dict["openai_reasoning_effort"] = (
                get_openai_reasoning_effort()
            )
            model_settings_dict["extra_body"] = {"verbosity": "low"}
            model_settings = OpenAIChatModelSettings(**model_settings_dict)

        self.cur_model = model
        p_agent = PydanticAgent(
            model=model,
            instructions=instructions,
            output_type=str,
            retries=3,
            toolsets=mcp_servers,
            history_processors=[self.message_history_accumulator],
            model_settings=model_settings,
        )

        agent_tools = self.get_available_tools()
        register_tools_for_agent(p_agent, agent_tools)

        self._last_model_name = resolved_model_name
        # expose for run_with_mcp
        # Wrap it with DBOS
        global _reload_count
        _reload_count += 1
        if USE_DBOS:
            dbos_agent = DBOSAgent(p_agent, name=f"{self.name}-{_reload_count}")
            self.pydantic_agent = dbos_agent
            self._code_generation_agent = dbos_agent
        else:
            self.pydantic_agent = p_agent
            self._code_generation_agent = p_agent
        return self._code_generation_agent

    # It's okay to decorate it with DBOS.step even if not using DBOS; the decorator is a no-op in that case.
    @DBOS.step()
    def message_history_accumulator(self, ctx: RunContext, messages: List[Any]):
        _message_history = self.get_message_history()
        message_history_hashes = set([self.hash_message(m) for m in _message_history])
        for msg in messages:
            if (
                self.hash_message(msg) not in message_history_hashes
                and self.hash_message(msg) not in self.get_compacted_message_hashes()
            ):
                _message_history.append(msg)

        # Apply message history trimming using the main processor
        # This ensures we maintain global state while still managing context limits
        self.message_history_processor(ctx, _message_history)
        return self.get_message_history()

    async def run_with_mcp(
        self,
        prompt: str,
        *,
        attachments: Optional[Sequence[BinaryContent]] = None,
        link_attachments: Optional[Sequence[Union[ImageUrl, DocumentUrl]]] = None,
        **kwargs,
    ) -> Any:
        """Run the agent with MCP servers, attachments, and full cancellation support.

        Args:
            prompt: Primary user prompt text (may be empty when attachments present).
            attachments: Local binary payloads (e.g., dragged images) to include.
            link_attachments: Remote assets (image/document URLs) to include.
            **kwargs: Additional arguments forwarded to `pydantic_ai.Agent.run`.

        Returns:
            The agent's response.

        Raises:
            asyncio.CancelledError: When execution is cancelled by user.
        """
        group_id = str(uuid.uuid4())
        # Avoid double-loading: reuse existing agent if already built
        pydantic_agent = (
            self._code_generation_agent or self.reload_code_generation_agent()
        )

        # Build combined prompt payload when attachments are provided.
        attachment_parts: List[Any] = []
        if attachments:
            attachment_parts.extend(list(attachments))
        if link_attachments:
            attachment_parts.extend(list(link_attachments))

        if attachment_parts:
            prompt_payload: Union[str, List[Any]] = []
            if prompt:
                prompt_payload.append(prompt)
            prompt_payload.extend(attachment_parts)
        else:
            prompt_payload = prompt

        async def run_agent_task():
            try:
                self.set_message_history(
                    self.prune_interrupted_tool_calls(self.get_message_history())
                )
                usage_limits = UsageLimits(request_limit=get_message_limit())
                if USE_DBOS:
                    # Set the workflow ID for DBOS context so DBOS and Code Puppy ID match
                    with SetWorkflowID(group_id):
                        result_ = await pydantic_agent.run(
                            prompt_payload,
                            message_history=self.get_message_history(),
                            usage_limits=usage_limits,
                            **kwargs,
                        )
                else:
                    result_ = await pydantic_agent.run(
                        prompt_payload,
                        message_history=self.get_message_history(),
                        usage_limits=usage_limits,
                        **kwargs,
                    )
                return result_
            except* UsageLimitExceeded as ule:
                emit_info(f"Usage limit exceeded: {str(ule)}", group_id=group_id)
                emit_info(
                    "The agent has reached its usage limit. You can ask it to continue by saying 'please continue' or similar.",
                    group_id=group_id,
                )
            except* mcp.shared.exceptions.McpError as mcp_error:
                emit_info(f"MCP server error: {str(mcp_error)}", group_id=group_id)
                emit_info(f"{str(mcp_error)}", group_id=group_id)
                emit_info(
                    "Try disabling any malfunctioning MCP servers", group_id=group_id
                )
            except* asyncio.exceptions.CancelledError:
                emit_info("Cancelled")
                if USE_DBOS:
                    await DBOS.cancel_workflow_async(group_id)
            except* InterruptedError as ie:
                emit_info(f"Interrupted: {str(ie)}")
                if USE_DBOS:
                    await DBOS.cancel_workflow_async(group_id)
            except* Exception as other_error:
                # Filter out CancelledError and UsageLimitExceeded from the exception group - let it propagate
                remaining_exceptions = []

                def collect_non_cancelled_exceptions(exc):
                    if isinstance(exc, ExceptionGroup):
                        for sub_exc in exc.exceptions:
                            collect_non_cancelled_exceptions(sub_exc)
                    elif not isinstance(
                        exc, (asyncio.CancelledError, UsageLimitExceeded)
                    ):
                        remaining_exceptions.append(exc)
                        emit_info(f"Unexpected error: {str(exc)}", group_id=group_id)
                        emit_info(f"{str(exc.args)}", group_id=group_id)

                collect_non_cancelled_exceptions(other_error)

                # If there are CancelledError exceptions in the group, re-raise them
                cancelled_exceptions = []

                def collect_cancelled_exceptions(exc):
                    if isinstance(exc, ExceptionGroup):
                        for sub_exc in exc.exceptions:
                            collect_cancelled_exceptions(sub_exc)
                    elif isinstance(exc, asyncio.CancelledError):
                        cancelled_exceptions.append(exc)

                collect_cancelled_exceptions(other_error)
            finally:
                self.set_message_history(
                    self.prune_interrupted_tool_calls(self.get_message_history())
                )

        # Create the task FIRST
        agent_task = asyncio.create_task(run_agent_task())

        # Import shell process killer
        from code_puppy.tools.command_runner import kill_all_running_shell_processes

        # Ensure the interrupt handler only acts once per task
        def keyboard_interrupt_handler(sig, frame):
            """Signal handler for Ctrl+C - replicating exact original logic"""

            # First, nuke any running shell processes triggered by tools
            try:
                killed = kill_all_running_shell_processes()
                if killed:
                    emit_info(f"Cancelled {killed} running shell process(es).")
                else:
                    # Only cancel the agent task if no shell processes were killed
                    if not agent_task.done():
                        agent_task.cancel()
            except Exception as e:
                emit_info(f"Shell kill error: {e}")
                if not agent_task.done():
                    agent_task.cancel()
            # Don't call the original handler
            # This prevents the application from exiting

        try:
            # Save original handler and set our custom one AFTER task is created
            original_handler = signal.signal(signal.SIGINT, keyboard_interrupt_handler)

            # Wait for the task to complete or be cancelled
            result = await agent_task
            return result
        except asyncio.CancelledError:
            agent_task.cancel()
        except KeyboardInterrupt:
            # Handle direct keyboard interrupt during await
            if not agent_task.done():
                agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                pass
        finally:
            # Restore original signal handler
            if original_handler:
                signal.signal(signal.SIGINT, original_handler)
