"""Formatters for session logs in different output formats."""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal


class LogFormatter(ABC):
    """Abstract base class for log formatters."""

    def __init__(self, timestamp_format: Literal["ISO8601", "unix", "human"]):
        self.timestamp_format = timestamp_format

    def format_timestamp(self, dt: datetime) -> str:
        """Format timestamp according to configuration."""
        if self.timestamp_format == "ISO8601":
            return dt.isoformat()
        elif self.timestamp_format == "unix":
            return str(int(dt.timestamp()))
        else:  # human
            return dt.strftime("%Y-%m-%d %H:%M:%S")

    @abstractmethod
    def format_header(self, session_id: str, start_time: datetime) -> str:
        """Format session header."""
        pass

    @abstractmethod
    def format_user_prompt(self, prompt: str, timestamp: datetime) -> str:
        """Format user prompt entry."""
        pass

    @abstractmethod
    def format_agent_reasoning(self, reasoning: str, timestamp: datetime) -> str:
        """Format agent reasoning entry."""
        pass

    @abstractmethod
    def format_agent_response(self, response: str, timestamp: datetime) -> str:
        """Format agent response entry."""
        pass

    @abstractmethod
    def format_tool_call(
        self, tool_name: str, arguments: dict, timestamp: datetime
    ) -> str:
        """Format tool call entry."""
        pass

    @abstractmethod
    def format_tool_output(self, tool_name: str, output: Any, timestamp: datetime) -> str:
        """Format tool output entry."""
        pass

    @abstractmethod
    def format_context_cleared(self, timestamp: datetime) -> str:
        """Format context cleared marker."""
        pass


class MarkdownFormatter(LogFormatter):
    """Markdown format for session logs."""

    def format_header(self, session_id: str, start_time: datetime) -> str:
        ts = self.format_timestamp(start_time)
        return f"# Session Log: {session_id}\n\n**Started:** {ts}\n\n---\n\n"

    def format_user_prompt(self, prompt: str, timestamp: datetime) -> str:
        ts = self.format_timestamp(timestamp)
        return f"## 👤 User Prompt\n**Time:** {ts}\n\n{prompt}\n\n---\n\n"

    def format_agent_reasoning(self, reasoning: str, timestamp: datetime) -> str:
        ts = self.format_timestamp(timestamp)
        return f"### 🤔 Agent Reasoning\n**Time:** {ts}\n\n{reasoning}\n\n"

    def format_agent_response(self, response: str, timestamp: datetime) -> str:
        ts = self.format_timestamp(timestamp)
        return f"## 🤖 Agent Response\n**Time:** {ts}\n\n{response}\n\n---\n\n"

    def format_tool_call(
        self, tool_name: str, arguments: dict, timestamp: datetime
    ) -> str:
        ts = self.format_timestamp(timestamp)
        args_json = json.dumps(arguments, indent=2)
        return (
            f"### 🔧 Tool Call: `{tool_name}`\n"
            f"**Time:** {ts}\n\n"
            f"```json\n{args_json}\n```\n\n"
        )

    def format_tool_output(self, tool_name: str, output: Any, timestamp: datetime) -> str:
        ts = self.format_timestamp(timestamp)
        # Safely convert output to string
        if isinstance(output, dict):
            output_str = json.dumps(output, indent=2)
            lang = "json"
        elif isinstance(output, str):
            output_str = output
            lang = "text"
        else:
            output_str = str(output)
            lang = "text"

        # Truncate very long outputs
        if len(output_str) > 5000:
            output_str = output_str[:5000] + "\n\n... (truncated)"

        return (
            f"### ✅ Tool Output: `{tool_name}`\n"
            f"**Time:** {ts}\n\n"
            f"```{lang}\n{output_str}\n```\n\n"
        )

    def format_context_cleared(self, timestamp: datetime) -> str:
        ts = self.format_timestamp(timestamp)
        return (
            f"---\n\n"
            f"## 🔄 CONTEXT CLEARED\n"
            f"**Time:** {ts}\n\n"
            f"User cleared conversation history. Starting new conversation in same session.\n\n"
            f"---\n\n"
        )


class JSONFormatter(LogFormatter):
    """JSON format for session logs."""

    def __init__(self, timestamp_format: Literal["ISO8601", "unix", "human"]):
        super().__init__(timestamp_format)
        self.entries = []

    def format_header(self, session_id: str, start_time: datetime) -> str:
        ts = self.format_timestamp(start_time)
        entry = {
            "type": "session_start",
            "session_id": session_id,
            "timestamp": ts,
        }
        self.entries.append(entry)
        return json.dumps(entry) + "\n"

    def format_user_prompt(self, prompt: str, timestamp: datetime) -> str:
        ts = self.format_timestamp(timestamp)
        entry = {"type": "user_prompt", "timestamp": ts, "content": prompt}
        self.entries.append(entry)
        return json.dumps(entry) + "\n"

    def format_agent_reasoning(self, reasoning: str, timestamp: datetime) -> str:
        ts = self.format_timestamp(timestamp)
        entry = {"type": "agent_reasoning", "timestamp": ts, "content": reasoning}
        self.entries.append(entry)
        return json.dumps(entry) + "\n"

    def format_agent_response(self, response: str, timestamp: datetime) -> str:
        ts = self.format_timestamp(timestamp)
        entry = {"type": "agent_response", "timestamp": ts, "content": response}
        self.entries.append(entry)
        return json.dumps(entry) + "\n"

    def format_tool_call(
        self, tool_name: str, arguments: dict, timestamp: datetime
    ) -> str:
        ts = self.format_timestamp(timestamp)
        entry = {
            "type": "tool_call",
            "timestamp": ts,
            "tool_name": tool_name,
            "arguments": arguments,
        }
        self.entries.append(entry)
        return json.dumps(entry) + "\n"

    def format_tool_output(self, tool_name: str, output: Any, timestamp: datetime) -> str:
        ts = self.format_timestamp(timestamp)
        # Convert output to JSON-serializable format
        if isinstance(output, (dict, list, str, int, float, bool, type(None))):
            output_serialized = output
        else:
            output_serialized = str(output)

        # Truncate very long outputs
        if isinstance(output_serialized, str) and len(output_serialized) > 5000:
            output_serialized = output_serialized[:5000] + " ... (truncated)"

        entry = {
            "type": "tool_output",
            "timestamp": ts,
            "tool_name": tool_name,
            "output": output_serialized,
        }
        self.entries.append(entry)
        return json.dumps(entry) + "\n"

    def format_context_cleared(self, timestamp: datetime) -> str:
        ts = self.format_timestamp(timestamp)
        entry = {
            "type": "context_cleared",
            "timestamp": ts,
            "message": "User cleared conversation history. Starting new conversation in same session.",
        }
        self.entries.append(entry)
        return json.dumps(entry) + "\n"


def create_formatter(
    format_type: Literal["markdown", "json"],
    timestamp_format: Literal["ISO8601", "unix", "human"],
) -> LogFormatter:
    """Create a log formatter based on format type."""
    if format_type == "markdown":
        return MarkdownFormatter(timestamp_format)
    elif format_type == "json":
        return JSONFormatter(timestamp_format)
    else:
        raise ValueError(f"Unsupported format type: {format_type}")
