"""Base agent configuration class for defining agent properties."""

import json
import queue
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Tuple

import pydantic
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    TextPart,
    ToolCallPart,
    ToolCallPartDelta,
    ToolReturn,
    ToolReturnPart,
)


class BaseAgent(ABC):
    """Base class for all agent configurations."""
    
    def __init__(self):
        self.id = str(uuid.uuid4())
        self._message_history: List[Any] = []
        self._compacted_message_hashes: Set[str] = set()

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
            Model name to use for this agent, or None to use global default.
        """
        from ..config import get_agent_pinned_model
        return get_agent_pinned_model(self.name)

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
            attributes.append(f"content={json.dumps(content.model_dump(), sort_keys=True)}")
        elif isinstance(content, dict):
            attributes.append(f"content={json.dumps(content, sort_keys=True)}")
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

        part_strings = [self._stringify_part(part) for part in getattr(message, "parts", [])]
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

    def estimate_tokens_for_message(self, message: ModelMessage) -> int:
        """
        Estimate the number of tokens in a message using len(message) - 4.
        Simple and fast replacement for tiktoken.
        """
        total_tokens = 0

        for part in message.parts:
            part_str = self.stringify_message_part(part)
            if part_str:
                total_tokens += len(part_str)

        return int(max(1, total_tokens) / 4)

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
        if not messages:
            return []

        # Never drop the system prompt, even if it is extremely large.
        system_message, *rest = messages
        filtered_rest = [
            m for m in rest if self.estimate_tokens_for_message(m) < 50000
        ]
        return [system_message] + filtered_rest

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
        from ..config import get_protected_token_count
        protected_tokens_limit = get_protected_token_count()

        # Calculate tokens for messages from most recent backwards (excluding system message)
        protected_messages = []
        protected_token_count = system_tokens  # Start with system message tokens

        # Go backwards through non-system messages to find protected zone
        for i in range(len(messages) - 1, 0, -1):  # Stop at 1, not 0 (skip system message)
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
        from ..messaging import emit_info
        emit_info(
            f"🔒 Protecting {len(protected_messages)} recent messages ({protected_token_count} tokens, limit: {protected_tokens_limit})"
        )
        emit_info(f"📝 Summarizing {len(messages_to_summarize)} older messages")

        return messages_to_summarize, protected_messages

    def summarize_messages(
        self,
        messages: List[ModelMessage],
        with_protection: bool = True
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
            from ..summarization_agent import run_summarization_sync
            new_messages = run_summarization_sync(
                instructions, message_history=messages_to_summarize
            )

            if not isinstance(new_messages, list):
                from ..messaging import emit_warning
                emit_warning(
                    "Summarization agent returned non-list output; wrapping into message request"
                )
                new_messages = [ModelRequest([TextPart(str(new_messages))])]

            compacted: List[ModelMessage] = [system_message] + list(new_messages)

            # Drop the system message from protected_messages because we already included it
            protected_tail = [msg for msg in protected_messages if msg is not system_message]

            compacted.extend(protected_tail)

            return self.prune_interrupted_tool_calls(compacted), messages_to_summarize
        except Exception as e:
            from ..messaging import emit_error
            emit_error(f"Summarization failed during compaction: {e}")
            return messages, []  # Return original messages on failure

    def summarize_message(self, message: ModelMessage) -> ModelMessage:
        try:
            # If the message looks like a system/instructions message, skip summarization
            instructions = getattr(message, "instructions", None)
            if instructions:
                return message
            # If any part is a tool call, skip summarization
            for part in message.parts:
                if isinstance(part, ToolCallPart) or getattr(part, "tool_name", None):
                    return message
            # Build prompt from textual content parts
            content_bits: List[str] = []
            for part in message.parts:
                s = self.stringify_message_part(part)
                if s:
                    content_bits.append(s)
            if not content_bits:
                return message
            prompt = "Please summarize the following user message:\n" + "\n".join(
                content_bits
            )
            
            from ..summarization_agent import run_summarization_sync
            output_text = run_summarization_sync(prompt)
            summarized = ModelRequest([TextPart(output_text)])
            return summarized
        except Exception as e:
            from ..messaging import emit_error
            emit_error(f"Summarization failed: {e}")
            return message

    def get_model_context_length(self) -> int:
        """
        Get the context length for the currently configured model from models.json
        """
        from ..config import get_model_name
        from ..model_factory import ModelFactory

        model_configs = ModelFactory.load_config()
        model_name = get_model_name()

        # Get context length from model config
        model_config = model_configs.get(model_name, {})
        context_length = model_config.get("context_length", 128000)  # Default value

        return int(context_length)

    def prune_interrupted_tool_calls(self, messages: List[ModelMessage]) -> List[ModelMessage]:
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

                if self._is_tool_call_part(part) and not self._is_tool_return_part(part):
                    tool_call_ids.add(tool_call_id)
                elif self._is_tool_return_part(part):
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

        if dropped_count:
            from ..messaging import emit_warning
            emit_warning(
                f"Pruned {dropped_count} message(s) with mismatched tool_call_id pairs"
            )
        return pruned
