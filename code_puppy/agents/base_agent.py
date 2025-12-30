"""Base agent configuration class for defining agent properties."""

import asyncio
import json
import math
import signal
import threading
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
)

import mcp
import pydantic
import pydantic_ai.models
from dbos import DBOS, SetWorkflowID
from pydantic_ai import Agent as PydanticAgent
from pydantic_ai import (
    BinaryContent,
    DocumentUrl,
    ImageUrl,
    PartEndEvent,
    RunContext,
    UsageLimitExceeded,
    UsageLimits,
)
from pydantic_ai.durable_exec.dbos import DBOSAgent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolCallPartDelta,
    ToolReturn,
    ToolReturnPart,
)
from rich.text import Text

# Consolidated relative imports
from code_puppy.config import (
    get_agent_pinned_model,
    get_compaction_strategy,
    get_compaction_threshold,
    get_global_model_name,
    get_message_limit,
    get_protected_token_count,
    get_use_dbos,
    get_value,
)
from code_puppy.error_logging import log_error
from code_puppy.keymap import cancel_agent_uses_signal, get_cancel_agent_char_code
from code_puppy.mcp_ import get_mcp_manager
from code_puppy.messaging import (
    emit_error,
    emit_info,
    emit_warning,
)
from code_puppy.messaging.spinner import (
    SpinnerBase,
    update_spinner_context,
)
from code_puppy.model_factory import ModelFactory, make_model_settings
from code_puppy.summarization_agent import run_summarization_sync
from code_puppy.tools.agent_tools import _active_subagent_tasks
from code_puppy.tools.command_runner import (
    is_awaiting_user_input,
)

# Global flag to track delayed compaction requests
_delayed_compaction_requested = False

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
        # Cache for MCP tool definitions (for token estimation)
        # This is populated after the first successful run when MCP tools are retrieved
        self._mcp_tool_definitions_cache: List[Dict[str, Any]] = []
        # Shared console for streaming output - should be set by cli_runner
        # to avoid conflicts between spinner's Live display and response streaming
        self._console: Optional[Any] = None

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

    def estimate_context_overhead_tokens(self) -> int:
        """
        Estimate the token overhead from system prompt and tool definitions.

        This accounts for tokens that are always present in the context:
        - System prompt (for non-Claude-Code models)
        - Tool definitions (name, description, parameter schema)
        - MCP tool definitions

        Note: For Claude Code models, the system prompt is prepended to the first
        user message, so it's already counted in the message history tokens.
        We only count the short fixed instructions for Claude Code models.
        """
        total_tokens = 0

        # 1. Estimate tokens for system prompt / instructions
        # For Claude Code models, the full system prompt is prepended to the first
        # user message (already in message history), so we only count the short
        # fixed instructions. For other models, count the full system prompt.
        try:
            from code_puppy.model_utils import (
                get_chatgpt_codex_instructions,
                get_claude_code_instructions,
                is_chatgpt_codex_model,
                is_claude_code_model,
            )

            model_name = (
                self.get_model_name() if hasattr(self, "get_model_name") else ""
            )
            if is_claude_code_model(model_name):
                # For Claude Code models, only count the short fixed instructions
                # The full system prompt is already in the message history
                instructions = get_claude_code_instructions()
                total_tokens += self.estimate_token_count(instructions)
            elif is_chatgpt_codex_model(model_name):
                # For ChatGPT Codex models, only count the short fixed instructions
                # The full system prompt is already in the message history
                instructions = get_chatgpt_codex_instructions()
                total_tokens += self.estimate_token_count(instructions)
            else:
                # For other models, count the full system prompt
                system_prompt = self.get_system_prompt()
                if system_prompt:
                    total_tokens += self.estimate_token_count(system_prompt)
        except Exception:
            pass  # If we can't get system prompt, skip it

        # 2. Estimate tokens for pydantic_agent tool definitions
        pydantic_agent = getattr(self, "pydantic_agent", None)
        if pydantic_agent:
            tools = getattr(pydantic_agent, "_tools", None)
            if tools and isinstance(tools, dict):
                for tool_name, tool_func in tools.items():
                    try:
                        # Estimate tokens from tool name
                        total_tokens += self.estimate_token_count(tool_name)

                        # Estimate tokens from tool description
                        description = getattr(tool_func, "__doc__", None) or ""
                        if description:
                            total_tokens += self.estimate_token_count(description)

                        # Estimate tokens from parameter schema
                        # Tools may have a schema attribute or we can try to get it from annotations
                        schema = getattr(tool_func, "schema", None)
                        if schema:
                            schema_str = (
                                json.dumps(schema)
                                if isinstance(schema, dict)
                                else str(schema)
                            )
                            total_tokens += self.estimate_token_count(schema_str)
                        else:
                            # Try to get schema from function annotations
                            annotations = getattr(tool_func, "__annotations__", None)
                            if annotations:
                                total_tokens += self.estimate_token_count(
                                    str(annotations)
                                )
                    except Exception:
                        continue  # Skip tools we can't process

        # 3. Estimate tokens for MCP tool definitions from cache
        # MCP tools are fetched asynchronously, so we use a cache that's populated
        # after the first successful run. See _update_mcp_tool_cache() method.
        mcp_tool_cache = getattr(self, "_mcp_tool_definitions_cache", [])
        if mcp_tool_cache:
            for tool_def in mcp_tool_cache:
                try:
                    # Estimate tokens from tool name
                    tool_name = tool_def.get("name", "")
                    if tool_name:
                        total_tokens += self.estimate_token_count(tool_name)

                    # Estimate tokens from tool description
                    description = tool_def.get("description", "")
                    if description:
                        total_tokens += self.estimate_token_count(description)

                    # Estimate tokens from parameter schema (inputSchema)
                    input_schema = tool_def.get("inputSchema")
                    if input_schema:
                        schema_str = (
                            json.dumps(input_schema)
                            if isinstance(input_schema, dict)
                            else str(input_schema)
                        )
                        total_tokens += self.estimate_token_count(schema_str)
                except Exception:
                    continue  # Skip tools we can't process

        return total_tokens

    async def _update_mcp_tool_cache(self) -> None:
        """
        Update the MCP tool definitions cache by fetching tools from running MCP servers.

        This should be called after a successful run to populate the cache for
        accurate token estimation in subsequent runs.
        """
        mcp_servers = getattr(self, "_mcp_servers", None)
        if not mcp_servers:
            return

        tool_definitions = []
        for mcp_server in mcp_servers:
            try:
                # Check if the server has list_tools method (pydantic-ai MCP servers)
                if hasattr(mcp_server, "list_tools"):
                    # list_tools() returns list[mcp_types.Tool]
                    tools = await mcp_server.list_tools()
                    for tool in tools:
                        tool_def = {
                            "name": getattr(tool, "name", ""),
                            "description": getattr(tool, "description", ""),
                            "inputSchema": getattr(tool, "inputSchema", {}),
                        }
                        tool_definitions.append(tool_def)
            except Exception:
                # Server might not be running or accessible, skip it
                continue

        self._mcp_tool_definitions_cache = tool_definitions

    def update_mcp_tool_cache_sync(self) -> None:
        """
        Synchronously clear the MCP tool cache.

        This clears the cache so that token counts will be recalculated on the next
        agent run. Call this after starting/stopping MCP servers.

        Note: We don't try to fetch tools synchronously because MCP servers require
        async context management that doesn't work well from sync code. The cache
        will be repopulated on the next successful agent run.
        """
        # Simply clear the cache - it will be repopulated on the next agent run
        # This is safer than trying to call async methods from sync context
        self._mcp_tool_definitions_cache = []

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

    def has_pending_tool_calls(self, messages: List[ModelMessage]) -> bool:
        """
        Check if there are any pending tool calls in the message history.

        A pending tool call is one that has a ToolCallPart without a corresponding
        ToolReturnPart. This indicates the model is still waiting for tool execution.

        Returns:
            True if there are pending tool calls, False otherwise
        """
        if not messages:
            return False

        tool_call_ids: Set[str] = set()
        tool_return_ids: Set[str] = set()

        # Collect all tool call and return IDs
        for msg in messages:
            for part in getattr(msg, "parts", []) or []:
                tool_call_id = getattr(part, "tool_call_id", None)
                if not tool_call_id:
                    continue

                if part.part_kind == "tool-call":
                    tool_call_ids.add(tool_call_id)
                elif part.part_kind == "tool-return":
                    tool_return_ids.add(tool_call_id)

        # Pending tool calls are those without corresponding returns
        pending_calls = tool_call_ids - tool_return_ids
        return len(pending_calls) > 0

    def request_delayed_compaction(self) -> None:
        """
        Request that compaction be attempted after the current tool calls complete.

        This sets a global flag that will be checked during the next message
        processing cycle to trigger compaction when it's safe to do so.
        """
        global _delayed_compaction_requested
        _delayed_compaction_requested = True
        emit_info(
            "🔄 Delayed compaction requested - will attempt after tool calls complete",
            message_group="token_context_status",
        )

    def should_attempt_delayed_compaction(self) -> bool:
        """
        Check if delayed compaction was requested and it's now safe to proceed.

        Returns:
            True if delayed compaction was requested and no tool calls are pending
        """
        global _delayed_compaction_requested
        if not _delayed_compaction_requested:
            return False

        # Check if it's now safe to compact
        messages = self.get_message_history()
        if not self.has_pending_tool_calls(messages):
            _delayed_compaction_requested = False  # Reset the flag
            return True

        return False

    def get_pending_tool_call_count(self, messages: List[ModelMessage]) -> int:
        """
        Get the count of pending tool calls for debugging purposes.

        Returns:
            Number of tool calls waiting for execution
        """
        if not messages:
            return 0

        tool_call_ids: Set[str] = set()
        tool_return_ids: Set[str] = set()

        for msg in messages:
            for part in getattr(msg, "parts", []) or []:
                tool_call_id = getattr(part, "tool_call_id", None)
                if not tool_call_id:
                    continue

                if part.part_kind == "tool-call":
                    tool_call_ids.add(tool_call_id)
                elif part.part_kind == "tool-return":
                    tool_return_ids.add(tool_call_id)

        pending_calls = tool_call_ids - tool_return_ids
        return len(pending_calls)

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

        message_tokens = sum(self.estimate_tokens_for_message(msg) for msg in messages)
        context_overhead = self.estimate_context_overhead_tokens()
        total_current_tokens = message_tokens + context_overhead
        proportion_used = total_current_tokens / model_max

        context_summary = SpinnerBase.format_context_info(
            total_current_tokens, model_max, proportion_used
        )
        update_spinner_context(context_summary)

        # Get the configured compaction threshold
        compaction_threshold = get_compaction_threshold()

        # Get the configured compaction strategy
        compaction_strategy = get_compaction_strategy()

        if proportion_used > compaction_threshold:
            # RACE CONDITION PROTECTION: Check for pending tool calls before summarization
            if compaction_strategy == "summarization" and self.has_pending_tool_calls(
                messages
            ):
                pending_count = self.get_pending_tool_call_count(messages)
                emit_warning(
                    f"⚠️  Summarization deferred: {pending_count} pending tool call(s) detected. "
                    "Waiting for tool execution to complete before compaction.",
                    message_group="token_context_status",
                )
                # Request delayed compaction for when tool calls complete
                self.request_delayed_compaction()
                # Return original messages without compaction
                return messages, []

            if compaction_strategy == "truncation":
                # Use truncation instead of summarization
                protected_tokens = get_protected_token_count()
                result_messages = self.truncation(
                    self.filter_huge_messages(messages), protected_tokens
                )
                summarized_messages = []  # No summarization in truncation mode
            else:
                # Default to summarization (safe to proceed - no pending tool calls)
                result_messages, summarized_messages = self.summarize_messages(
                    self.filter_huge_messages(messages)
                )

            final_token_count = sum(
                self.estimate_tokens_for_message(msg) for msg in result_messages
            )
            # Update spinner with final token count
            final_summary = SpinnerBase.format_context_info(
                final_token_count, model_max, final_token_count / model_max
            )
            update_spinner_context(final_summary)

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
        """Load AGENT(S).md from both global config and project directory.

        Checks for AGENTS.md/AGENT.md/agents.md/agent.md in this order:
        1. Global config directory (~/.code_puppy/ or XDG config)
        2. Current working directory (project-specific)

        If both exist, they are combined with global rules first, then project rules.
        This allows project-specific rules to override or extend global rules.
        """
        if self._puppy_rules is not None:
            return self._puppy_rules
        from pathlib import Path

        possible_paths = ["AGENTS.md", "AGENT.md", "agents.md", "agent.md"]

        # Load global rules from CONFIG_DIR
        global_rules = None
        from code_puppy.config import CONFIG_DIR

        for path_str in possible_paths:
            global_path = Path(CONFIG_DIR) / path_str
            if global_path.exists():
                global_rules = global_path.read_text(encoding="utf-8-sig")
                break

        # Load project-local rules from current working directory
        project_rules = None
        for path_str in possible_paths:
            project_path = Path(path_str)
            if project_path.exists():
                project_rules = project_path.read_text(encoding="utf-8-sig")
                break

        # Combine global and project rules
        # Global rules come first, project rules second (allowing project to override)
        rules = [r for r in [global_rules, project_rules] if r]
        self._puppy_rules = "\n\n".join(rules) if rules else None
        return self._puppy_rules

    def load_mcp_servers(self, extra_headers: Optional[Dict[str, str]] = None):
        """Load MCP servers through the manager and return pydantic-ai compatible servers.

        Note: The manager automatically syncs from mcp_servers.json during initialization,
        so we don't need to sync here. Use reload_mcp_servers() to force a re-sync.
        """

        mcp_disabled = get_value("disable_mcp_servers")
        if mcp_disabled and str(mcp_disabled).lower() in ("1", "true", "yes", "on"):
            return []

        manager = get_mcp_manager()
        return manager.get_servers_for_agent()

    def reload_mcp_servers(self):
        """Reload MCP servers and return updated servers.

        Forces a re-sync from mcp_servers.json to pick up any configuration changes.
        """
        # Clear the MCP tool cache when servers are reloaded
        self._mcp_tool_definitions_cache = []

        # Force re-sync from mcp_servers.json
        manager = get_mcp_manager()
        manager.sync_from_config()

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
                    f"Model '{requested_model_name}' not found. "
                    f"Available models: {available_str}"
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
                        f"Using fallback model: {candidate}",
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
                friendly_message,
                message_group=message_group,
            )
            raise ValueError(friendly_message) from exc

    def reload_code_generation_agent(self, message_group: Optional[str] = None):
        """Force-reload the pydantic-ai Agent based on current config and model."""
        from code_puppy.tools import register_tools_for_agent

        if message_group is None:
            message_group = str(uuid.uuid4())

        model_name = self.get_model_name()

        models_config = ModelFactory.load_config()
        model, resolved_model_name = self._load_model_with_fallback(
            model_name,
            models_config,
            message_group,
        )

        instructions = self.get_system_prompt()
        puppy_rules = self.load_puppy_rules()
        if puppy_rules:
            instructions += f"\n{puppy_rules}"

        mcp_servers = self.load_mcp_servers()

        model_settings = make_model_settings(resolved_model_name)

        # Handle claude-code models: swap instructions (prompt prepending happens in run_with_mcp)
        from code_puppy.model_utils import prepare_prompt_for_model

        prepared = prepare_prompt_for_model(
            model_name, instructions, "", prepend_system_to_user=False
        )
        instructions = prepared.instructions

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

        # Get existing tool names to filter out conflicts with MCP tools
        existing_tool_names = set()
        try:
            # Get tools from the agent to find existing tool names
            tools = getattr(p_agent, "_tools", None)
            if tools:
                existing_tool_names = set(tools.keys())
        except Exception:
            # If we can't get tool names, proceed without filtering
            pass

        # Filter MCP server toolsets to remove conflicting tools
        filtered_mcp_servers = []
        if mcp_servers and existing_tool_names:
            for mcp_server in mcp_servers:
                try:
                    # Get tools from this MCP server
                    server_tools = getattr(mcp_server, "tools", None)
                    if server_tools:
                        # Filter out conflicting tools
                        filtered_tools = {}
                        for tool_name, tool_func in server_tools.items():
                            if tool_name not in existing_tool_names:
                                filtered_tools[tool_name] = tool_func

                        # Create a filtered version of the MCP server if we have tools
                        if filtered_tools:
                            # Create a new toolset with filtered tools
                            from pydantic_ai.tools import ToolSet

                            filtered_toolset = ToolSet()
                            for tool_name, tool_func in filtered_tools.items():
                                filtered_toolset._tools[tool_name] = tool_func
                            filtered_mcp_servers.append(filtered_toolset)
                        else:
                            # No tools left after filtering, skip this server
                            pass
                    else:
                        # Can't get tools from this server, include as-is
                        filtered_mcp_servers.append(mcp_server)
                except Exception:
                    # Error processing this server, include as-is to be safe
                    filtered_mcp_servers.append(mcp_server)
        else:
            # No filtering needed or possible
            filtered_mcp_servers = mcp_servers if mcp_servers else []

        if len(filtered_mcp_servers) != len(mcp_servers):
            emit_info(
                Text.from_markup(
                    f"[dim]Filtered {len(mcp_servers) - len(filtered_mcp_servers)} conflicting MCP tools[/dim]"
                )
            )

        self._last_model_name = resolved_model_name
        # expose for run_with_mcp
        # Wrap it with DBOS, but handle MCP servers separately to avoid serialization issues
        global _reload_count
        _reload_count += 1
        if get_use_dbos():
            # Don't pass MCP servers to the agent constructor when using DBOS
            # This prevents the "cannot pickle async_generator object" error
            # MCP servers will be handled separately in run_with_mcp
            agent_without_mcp = PydanticAgent(
                model=model,
                instructions=instructions,
                output_type=str,
                retries=3,
                toolsets=[],  # Don't include MCP servers here
                history_processors=[self.message_history_accumulator],
                model_settings=model_settings,
            )

            # Register regular tools (non-MCP) on the new agent
            agent_tools = self.get_available_tools()
            register_tools_for_agent(agent_without_mcp, agent_tools)

            # Wrap with DBOS
            dbos_agent = DBOSAgent(
                agent_without_mcp, name=f"{self.name}-{_reload_count}"
            )
            self.pydantic_agent = dbos_agent
            self._code_generation_agent = dbos_agent

            # Store filtered MCP servers separately for runtime use
            self._mcp_servers = filtered_mcp_servers
        else:
            # Normal path without DBOS - include filtered MCP servers in the agent
            # Re-create agent with filtered MCP servers
            p_agent = PydanticAgent(
                model=model,
                instructions=instructions,
                output_type=str,
                retries=3,
                toolsets=filtered_mcp_servers,
                history_processors=[self.message_history_accumulator],
                model_settings=model_settings,
            )
            # Register regular tools on the agent
            agent_tools = self.get_available_tools()
            register_tools_for_agent(p_agent, agent_tools)

            self.pydantic_agent = p_agent
            self._code_generation_agent = p_agent
            self._mcp_servers = filtered_mcp_servers
            self._mcp_servers = mcp_servers
        return self._code_generation_agent

    def _create_agent_with_output_type(self, output_type: Type[Any]) -> PydanticAgent:
        """Create a temporary agent configured with a custom output_type.

        This is used when structured output is requested via run_with_mcp.
        The agent is created fresh with the same configuration as the main agent
        but with the specified output_type instead of str.

        Args:
            output_type: The Pydantic model or type for structured output.

        Returns:
            A configured PydanticAgent (or DBOSAgent wrapper) with the custom output_type.
        """
        from code_puppy.model_utils import prepare_prompt_for_model
        from code_puppy.tools import register_tools_for_agent

        model_name = self.get_model_name()
        models_config = ModelFactory.load_config()
        model, resolved_model_name = self._load_model_with_fallback(
            model_name, models_config, str(uuid.uuid4())
        )

        instructions = self.get_system_prompt()
        puppy_rules = self.load_puppy_rules()
        if puppy_rules:
            instructions += f"\n{puppy_rules}"

        mcp_servers = getattr(self, "_mcp_servers", []) or []
        model_settings = make_model_settings(resolved_model_name)

        prepared = prepare_prompt_for_model(
            model_name, instructions, "", prepend_system_to_user=False
        )
        instructions = prepared.instructions

        global _reload_count
        _reload_count += 1

        if get_use_dbos():
            temp_agent = PydanticAgent(
                model=model,
                instructions=instructions,
                output_type=output_type,
                retries=3,
                toolsets=[],
                history_processors=[self.message_history_accumulator],
                model_settings=model_settings,
            )
            agent_tools = self.get_available_tools()
            register_tools_for_agent(temp_agent, agent_tools)
            dbos_agent = DBOSAgent(
                temp_agent, name=f"{self.name}-structured-{_reload_count}"
            )
            return dbos_agent
        else:
            temp_agent = PydanticAgent(
                model=model,
                instructions=instructions,
                output_type=output_type,
                retries=3,
                toolsets=mcp_servers,
                history_processors=[self.message_history_accumulator],
                model_settings=model_settings,
            )
            agent_tools = self.get_available_tools()
            register_tools_for_agent(temp_agent, agent_tools)
            return temp_agent

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
        result_messages_filtered_empty_thinking = []
        for msg in self.get_message_history():
            if len(msg.parts) == 1:
                if isinstance(msg.parts[0], ThinkingPart):
                    if msg.parts[0].content == "":
                        continue
            result_messages_filtered_empty_thinking.append(msg)
            self.set_message_history(result_messages_filtered_empty_thinking)
        return self.get_message_history()

    async def _event_stream_handler(
        self, ctx: RunContext, events: AsyncIterable[Any]
    ) -> None:
        """Handle streaming events from the agent run.

        This method processes streaming events and emits TextPart, ThinkingPart,
        and ToolCallPart content with styled banners/tokens as they stream in.

        Args:
            ctx: The run context.
            events: Async iterable of streaming events (PartStartEvent, PartDeltaEvent, etc.).
        """
        from pydantic_ai import PartDeltaEvent, PartStartEvent
        from pydantic_ai.messages import (
            TextPartDelta,
            ThinkingPartDelta,
            ToolCallPartDelta,
        )
        from rich.console import Console
        from rich.markdown import Markdown
        from rich.markup import escape

        from code_puppy.messaging.spinner import pause_all_spinners

        # IMPORTANT: Use the shared console (set by cli_runner) to avoid conflicts
        # with the spinner's Live display. Multiple Console instances with separate
        # Live displays cause cursor positioning chaos and line duplication.
        if self._console is not None:
            console = self._console
        else:
            # Fallback if console not set (shouldn't happen in normal use)
            console = Console()

        # Track which part indices we're currently streaming (for Text/Thinking/Tool parts)
        streaming_parts: set[int] = set()
        thinking_parts: set[int] = (
            set()
        )  # Track which parts are thinking (for dim style)
        text_parts: set[int] = set()  # Track which parts are text
        tool_parts: set[int] = set()  # Track which parts are tool calls
        banner_printed: set[int] = set()  # Track if banner was already printed
        text_buffer: dict[int, list[str]] = {}  # Buffer text for final markdown render
        token_count: dict[int, int] = {}  # Track token count per text/tool part
        did_stream_anything = False  # Track if we streamed any content

        def _print_thinking_banner() -> None:
            """Print the THINKING banner with spinner pause and line clear."""
            nonlocal did_stream_anything
            import time

            from code_puppy.config import get_banner_color

            pause_all_spinners()
            time.sleep(0.1)  # Delay to let spinner fully clear
            # Clear line and print newline before banner
            console.print(" " * 50, end="\r")
            console.print()  # Newline before banner
            # Bold banner with configurable color and lightning bolt
            thinking_color = get_banner_color("thinking")
            console.print(
                Text.from_markup(
                    f"[bold white on {thinking_color}] THINKING [/bold white on {thinking_color}] [dim]⚡ "
                ),
                end="",
            )
            did_stream_anything = True

        def _print_response_banner() -> None:
            """Print the AGENT RESPONSE banner with spinner pause and line clear."""
            nonlocal did_stream_anything
            import time

            from code_puppy.config import get_banner_color

            pause_all_spinners()
            time.sleep(0.1)  # Delay to let spinner fully clear
            # Clear line and print newline before banner
            console.print(" " * 50, end="\r")
            console.print()  # Newline before banner
            response_color = get_banner_color("agent_response")
            console.print(
                Text.from_markup(
                    f"[bold white on {response_color}] AGENT RESPONSE [/bold white on {response_color}]"
                )
            )
            did_stream_anything = True

        async for event in events:
            # PartStartEvent - register the part but defer banner until content arrives
            if isinstance(event, PartStartEvent):
                part = event.part
                if isinstance(part, ThinkingPart):
                    streaming_parts.add(event.index)
                    thinking_parts.add(event.index)
                    # If there's initial content, print banner + content now
                    if part.content and part.content.strip():
                        _print_thinking_banner()
                        escaped = escape(part.content)
                        console.print(f"[dim]{escaped}[/dim]", end="")
                        banner_printed.add(event.index)
                elif isinstance(part, TextPart):
                    streaming_parts.add(event.index)
                    text_parts.add(event.index)
                    text_buffer[event.index] = []  # Initialize buffer
                    token_count[event.index] = 0  # Initialize token counter
                    # Buffer initial content if present
                    if part.content and part.content.strip():
                        text_buffer[event.index].append(part.content)
                        # Count chunks (each part counts as 1)
                        token_count[event.index] += 1
                elif isinstance(part, ToolCallPart):
                    streaming_parts.add(event.index)
                    tool_parts.add(event.index)
                    token_count[event.index] = 0  # Initialize token counter
                    # Track tool name for display
                    banner_printed.add(
                        event.index
                    )  # Use banner_printed to track if we've shown tool info

            # PartDeltaEvent - stream the content as it arrives
            elif isinstance(event, PartDeltaEvent):
                if event.index in streaming_parts:
                    delta = event.delta
                    if isinstance(delta, (TextPartDelta, ThinkingPartDelta)):
                        if delta.content_delta:
                            # For text parts, show token counter then render at end
                            if event.index in text_parts:
                                # Print banner on first content
                                if event.index not in banner_printed:
                                    _print_response_banner()
                                    banner_printed.add(event.index)
                                # Accumulate text for final markdown render
                                text_buffer[event.index].append(delta.content_delta)
                                # Count chunks received
                                token_count[event.index] += 1
                                # Update chunk counter in place (single line)
                                count = token_count[event.index]
                                console.print(
                                    f"  ⏳ Receiving... {count} chunks   ",
                                    end="\r",
                                )
                            else:
                                # For thinking parts, stream immediately (dim)
                                if event.index not in banner_printed:
                                    _print_thinking_banner()
                                    banner_printed.add(event.index)
                                escaped = escape(delta.content_delta)
                                console.print(f"[dim]{escaped}[/dim]", end="")
                    elif isinstance(delta, ToolCallPartDelta):
                        # For tool calls, count chunks received
                        token_count[event.index] += 1
                        # Get tool name if available
                        tool_name = getattr(delta, "tool_name_delta", "")
                        count = token_count[event.index]
                        # Display with tool wrench icon and tool name
                        if tool_name:
                            console.print(
                                f"  🔧 Calling {tool_name}... {count} chunks   ",
                                end="\r",
                            )
                        else:
                            console.print(
                                f"  🔧 Calling tool... {count} chunks   ",
                                end="\r",
                            )

            # PartEndEvent - finish the streaming with a newline
            elif isinstance(event, PartEndEvent):
                if event.index in streaming_parts:
                    # For text parts, clear counter line and render markdown
                    if event.index in text_parts:
                        # Clear the chunk counter line by printing spaces and returning
                        console.print(" " * 50, end="\r")
                        # Render the final markdown nicely
                        if event.index in text_buffer:
                            try:
                                final_content = "".join(text_buffer[event.index])
                                if final_content.strip():
                                    console.print(Markdown(final_content))
                            except Exception:
                                pass
                            del text_buffer[event.index]
                    # For tool parts, clear the chunk counter line
                    elif event.index in tool_parts:
                        # Clear the chunk counter line by printing spaces and returning
                        console.print(" " * 50, end="\r")
                    # For thinking parts, just print newline
                    elif event.index in banner_printed:
                        console.print()  # Final newline after streaming

                    # Clean up token count
                    token_count.pop(event.index, None)
                    # Clean up all tracking sets
                    streaming_parts.discard(event.index)
                    thinking_parts.discard(event.index)
                    text_parts.discard(event.index)
                    tool_parts.discard(event.index)
                    banner_printed.discard(event.index)

                    # Resume spinner if next part is NOT text/thinking/tool (avoid race condition)
                    # If next part is None or handled differently, it's safe to resume
                    # Note: spinner itself handles blank line before appearing
                    from code_puppy.messaging.spinner import resume_all_spinners

                    next_kind = getattr(event, "next_part_kind", None)
                    if next_kind not in ("text", "thinking", "tool-call"):
                        resume_all_spinners()

        # Spinner is resumed in PartEndEvent when appropriate (based on next_part_kind)

    def _spawn_ctrl_x_key_listener(
        self,
        stop_event: threading.Event,
        on_escape: Callable[[], None],
        on_cancel_agent: Optional[Callable[[], None]] = None,
    ) -> Optional[threading.Thread]:
        """Start a keyboard listener thread for CLI sessions.

        Listens for Ctrl+X (shell command cancel) and optionally the configured
        cancel_agent_key (when not using SIGINT/Ctrl+C).

        Args:
            stop_event: Event to signal the listener to stop.
            on_escape: Callback for Ctrl+X (shell command cancel).
            on_cancel_agent: Optional callback for cancel_agent_key (only used
                when cancel_agent_uses_signal() returns False).
        """
        try:
            import sys
        except ImportError:
            return None

        stdin = getattr(sys, "stdin", None)
        if stdin is None or not hasattr(stdin, "isatty"):
            return None
        try:
            if not stdin.isatty():
                return None
        except Exception:
            return None

        def listener() -> None:
            try:
                if sys.platform.startswith("win"):
                    self._listen_for_ctrl_x_windows(
                        stop_event, on_escape, on_cancel_agent
                    )
                else:
                    self._listen_for_ctrl_x_posix(
                        stop_event, on_escape, on_cancel_agent
                    )
            except Exception:
                emit_warning(
                    "Key listener stopped unexpectedly; press Ctrl+C to cancel."
                )

        thread = threading.Thread(
            target=listener, name="code-puppy-key-listener", daemon=True
        )
        thread.start()
        return thread

    def _listen_for_ctrl_x_windows(
        self,
        stop_event: threading.Event,
        on_escape: Callable[[], None],
        on_cancel_agent: Optional[Callable[[], None]] = None,
    ) -> None:
        import msvcrt
        import time

        # Get the cancel agent char code if we're using keyboard-based cancel
        cancel_agent_char: Optional[str] = None
        if on_cancel_agent is not None and not cancel_agent_uses_signal():
            cancel_agent_char = get_cancel_agent_char_code()

        while not stop_event.is_set():
            try:
                if msvcrt.kbhit():
                    key = msvcrt.getwch()
                    if key == "\x18":  # Ctrl+X
                        try:
                            on_escape()
                        except Exception:
                            emit_warning(
                                "Ctrl+X handler raised unexpectedly; Ctrl+C still works."
                            )
                    elif (
                        cancel_agent_char
                        and on_cancel_agent
                        and key == cancel_agent_char
                    ):
                        try:
                            on_cancel_agent()
                        except Exception:
                            emit_warning("Cancel agent handler raised unexpectedly.")
            except Exception:
                emit_warning(
                    "Windows key listener error; Ctrl+C is still available for cancel."
                )
                return
            time.sleep(0.05)

    def _listen_for_ctrl_x_posix(
        self,
        stop_event: threading.Event,
        on_escape: Callable[[], None],
        on_cancel_agent: Optional[Callable[[], None]] = None,
    ) -> None:
        import select
        import sys
        import termios
        import tty

        # Get the cancel agent char code if we're using keyboard-based cancel
        cancel_agent_char: Optional[str] = None
        if on_cancel_agent is not None and not cancel_agent_uses_signal():
            cancel_agent_char = get_cancel_agent_char_code()

        stdin = sys.stdin
        try:
            fd = stdin.fileno()
        except (AttributeError, ValueError, OSError):
            return
        try:
            original_attrs = termios.tcgetattr(fd)
        except Exception:
            return

        try:
            tty.setcbreak(fd)
            while not stop_event.is_set():
                try:
                    read_ready, _, _ = select.select([stdin], [], [], 0.05)
                except Exception:
                    break
                if not read_ready:
                    continue
                data = stdin.read(1)
                if not data:
                    break
                if data == "\x18":  # Ctrl+X
                    try:
                        on_escape()
                    except Exception:
                        emit_warning(
                            "Ctrl+X handler raised unexpectedly; Ctrl+C still works."
                        )
                elif (
                    cancel_agent_char and on_cancel_agent and data == cancel_agent_char
                ):
                    try:
                        on_cancel_agent()
                    except Exception:
                        emit_warning("Cancel agent handler raised unexpectedly.")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)

    async def run_with_mcp(
        self,
        prompt: str,
        *,
        attachments: Optional[Sequence[BinaryContent]] = None,
        link_attachments: Optional[Sequence[Union[ImageUrl, DocumentUrl]]] = None,
        output_type: Optional[Type[Any]] = None,
        **kwargs,
    ) -> Any:
        """Run the agent with MCP servers, attachments, and full cancellation support.

        Args:
            prompt: Primary user prompt text (may be empty when attachments present).
            attachments: Local binary payloads (e.g., dragged images) to include.
            link_attachments: Remote assets (image/document URLs) to include.
            output_type: Optional Pydantic model or type for structured output.
                When provided, creates a temporary agent configured to return
                this type instead of the default string output.
            **kwargs: Additional arguments forwarded to `pydantic_ai.Agent.run`.

        Returns:
            The agent's response (typed according to output_type if specified).

        Raises:
            asyncio.CancelledError: When execution is cancelled by user.
        """
        # Sanitize prompt to remove invalid Unicode surrogates that can cause
        # encoding errors (especially common on Windows with copy-paste)
        if prompt:
            try:
                prompt = prompt.encode("utf-8", errors="surrogatepass").decode(
                    "utf-8", errors="replace"
                )
            except (UnicodeEncodeError, UnicodeDecodeError):
                # Fallback: filter out surrogate characters directly
                prompt = "".join(
                    char if ord(char) < 0xD800 or ord(char) > 0xDFFF else "\ufffd"
                    for char in prompt
                )

        group_id = str(uuid.uuid4())
        # Avoid double-loading: reuse existing agent if already built
        pydantic_agent = (
            self._code_generation_agent or self.reload_code_generation_agent()
        )

        # If a custom output_type is specified, create a temporary agent with that type
        if output_type is not None:
            pydantic_agent = self._create_agent_with_output_type(output_type)

        # Handle claude-code and chatgpt-codex models: prepend system prompt to first user message
        from code_puppy.model_utils import is_chatgpt_codex_model, is_claude_code_model

        if is_claude_code_model(self.get_model_name()) or is_chatgpt_codex_model(
            self.get_model_name()
        ):
            if len(self.get_message_history()) == 0:
                system_prompt = self.get_system_prompt()
                puppy_rules = self.load_puppy_rules()
                if puppy_rules:
                    system_prompt += f"\n{puppy_rules}"
                prompt = system_prompt + "\n\n" + prompt

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

                # DELAYED COMPACTION: Check if we should attempt delayed compaction
                if self.should_attempt_delayed_compaction():
                    emit_info(
                        "🔄 Attempting delayed compaction (tool calls completed)",
                        message_group="token_context_status",
                    )
                    current_messages = self.get_message_history()
                    compacted_messages, _ = self.compact_messages(current_messages)
                    if compacted_messages != current_messages:
                        self.set_message_history(compacted_messages)
                        emit_info(
                            "✅ Delayed compaction completed successfully",
                            message_group="token_context_status",
                        )

                usage_limits = UsageLimits(request_limit=get_message_limit())

                # Handle MCP servers - add them temporarily when using DBOS
                if (
                    get_use_dbos()
                    and hasattr(self, "_mcp_servers")
                    and self._mcp_servers
                ):
                    # Temporarily add MCP servers to the DBOS agent using internal _toolsets
                    original_toolsets = pydantic_agent._toolsets
                    pydantic_agent._toolsets = original_toolsets + self._mcp_servers
                    pydantic_agent._toolsets = original_toolsets + self._mcp_servers

                    try:
                        # Set the workflow ID for DBOS context so DBOS and Code Puppy ID match
                        with SetWorkflowID(group_id):
                            result_ = await pydantic_agent.run(
                                prompt_payload,
                                message_history=self.get_message_history(),
                                usage_limits=usage_limits,
                                event_stream_handler=self._event_stream_handler,
                                **kwargs,
                            )
                    finally:
                        # Always restore original toolsets
                        pydantic_agent._toolsets = original_toolsets
                elif get_use_dbos():
                    # DBOS without MCP servers
                    with SetWorkflowID(group_id):
                        result_ = await pydantic_agent.run(
                            prompt_payload,
                            message_history=self.get_message_history(),
                            usage_limits=usage_limits,
                            event_stream_handler=self._event_stream_handler,
                            **kwargs,
                        )
                else:
                    # Non-DBOS path (MCP servers are already included)
                    result_ = await pydantic_agent.run(
                        prompt_payload,
                        message_history=self.get_message_history(),
                        usage_limits=usage_limits,
                        event_stream_handler=self._event_stream_handler,
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
                if get_use_dbos():
                    await DBOS.cancel_workflow_async(group_id)
            except* InterruptedError as ie:
                emit_info(f"Interrupted: {str(ie)}")
                if get_use_dbos():
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
                        # Log to file for debugging
                        log_error(
                            exc,
                            context=f"Agent run (group_id={group_id})",
                            include_traceback=True,
                        )

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

        # Import shell process status helper

        loop = asyncio.get_running_loop()

        def schedule_agent_cancel() -> None:
            from code_puppy.tools.command_runner import _RUNNING_PROCESSES

            if len(_RUNNING_PROCESSES):
                emit_warning(
                    "Refusing to cancel Agent while a shell command is currently running - press Ctrl+X to cancel the shell command."
                )
                return
            if agent_task.done():
                return

            # Cancel all active subagent tasks
            if _active_subagent_tasks:
                emit_warning(
                    f"Cancelling {len(_active_subagent_tasks)} active subagent task(s)..."
                )
                for task in list(
                    _active_subagent_tasks
                ):  # Create a copy since we'll be modifying the set
                    if not task.done():
                        loop.call_soon_threadsafe(task.cancel)
            loop.call_soon_threadsafe(agent_task.cancel)

        def keyboard_interrupt_handler(_sig, _frame):
            # If we're awaiting user input (e.g., file permission prompt),
            # don't cancel the agent - let the input() call handle the interrupt naturally
            if is_awaiting_user_input():
                # Don't do anything here - let the input() call raise KeyboardInterrupt naturally
                return

            schedule_agent_cancel()

        def graceful_sigint_handler(_sig, _frame):
            # When using keyboard-based cancel, SIGINT should be a no-op
            # (just show a hint to user about the configured cancel key)
            # Also reset terminal to prevent bricking on Windows+uvx
            from code_puppy.keymap import get_cancel_agent_display_name
            from code_puppy.terminal_utils import reset_windows_terminal_full

            # Reset terminal state first to prevent bricking
            reset_windows_terminal_full()

            cancel_key = get_cancel_agent_display_name()
            emit_info(f"Use {cancel_key} to cancel the agent task.")

        original_handler = None
        key_listener_stop_event = None
        _key_listener_thread = None

        try:
            if cancel_agent_uses_signal():
                # Use SIGINT-based cancellation (default Ctrl+C behavior)
                original_handler = signal.signal(
                    signal.SIGINT, keyboard_interrupt_handler
                )
            else:
                # Use keyboard listener for agent cancellation
                # Set a graceful SIGINT handler that shows a hint
                original_handler = signal.signal(signal.SIGINT, graceful_sigint_handler)
                # Spawn keyboard listener with the cancel agent callback
                key_listener_stop_event = threading.Event()
                _key_listener_thread = self._spawn_ctrl_x_key_listener(
                    key_listener_stop_event,
                    on_escape=lambda: None,  # Ctrl+X handled by command_runner
                    on_cancel_agent=schedule_agent_cancel,
                )

            # Wait for the task to complete or be cancelled
            result = await agent_task

            # Update MCP tool cache after successful run for accurate token estimation
            if hasattr(self, "_mcp_servers") and self._mcp_servers:
                try:
                    await self._update_mcp_tool_cache()
                except Exception:
                    pass  # Don't fail the run if cache update fails

            return result
        except asyncio.CancelledError:
            agent_task.cancel()
        except KeyboardInterrupt:
            # Handle direct keyboard interrupt during await
            if not agent_task.done():
                agent_task.cancel()
        finally:
            # Stop keyboard listener if it was started
            if key_listener_stop_event is not None:
                key_listener_stop_event.set()
            # Restore original signal handler
            if (
                original_handler is not None
            ):  # Explicit None check - SIG_DFL can be 0/falsy!
                signal.signal(signal.SIGINT, original_handler)
