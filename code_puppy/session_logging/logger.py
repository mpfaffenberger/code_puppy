"""Core session logger implementation."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from code_puppy.session_logging.config_schema import SessionLoggingConfig
from code_puppy.session_logging.formatters import LogFormatter, create_formatter


class SessionLogger:
    """Logs interactive sessions to files in configurable formats."""

    def __init__(self, config: SessionLoggingConfig, session_id: str):
        self.config = config
        self.session_id = session_id
        self.log_path = config.resolve_log_path(session_id)
        self.formatter = create_formatter(config.format, config.timestamp_format)
        self._file_handle: Optional[Any] = None
        self._write_lock = asyncio.Lock()
        self._initialized = False
        self._runtime_enabled = config.enabled  # Runtime toggle separate from config

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable logging at runtime."""
        self._runtime_enabled = enabled

    def is_enabled(self) -> bool:
        """Check if logging is currently enabled."""
        return self._runtime_enabled

    async def initialize(self) -> None:
        """Initialize the logger and write session header."""
        if not self._runtime_enabled:
            return

        if self._initialized:
            return

        # Ensure log directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Open log file in append mode
        self._file_handle = open(self.log_path, "a", encoding="utf-8")

        # Write session header
        header = self.formatter.format_header(self.session_id, datetime.now())
        await self._write(header)

        self._initialized = True

    async def _write(self, content: str) -> None:
        """Write content to log file (thread-safe)."""
        if not self._runtime_enabled or not self._file_handle:
            return

        async with self._write_lock:
            try:
                # Write synchronously but within async lock
                self._file_handle.write(content)
                self._file_handle.flush()
            except Exception:
                # Silently ignore write errors to avoid disrupting the session
                pass

    async def log_user_prompt(self, prompt: str) -> None:
        """Log a user prompt."""
        if not self._runtime_enabled or not self.config.include_user_prompts:
            return

        if not self._initialized:
            await self.initialize()

        content = self.formatter.format_user_prompt(prompt, datetime.now())
        await self._write(content)

    async def log_agent_reasoning(self, reasoning: str) -> None:
        """Log agent reasoning."""
        if not self._runtime_enabled or not self.config.include_agent_reasoning:
            return

        if not self._initialized:
            await self.initialize()

        content = self.formatter.format_agent_reasoning(reasoning, datetime.now())
        await self._write(content)

    async def log_agent_response(self, response: str) -> None:
        """Log agent response."""
        if not self._runtime_enabled or not self.config.include_agent_responses:
            return

        if not self._initialized:
            await self.initialize()

        content = self.formatter.format_agent_response(response, datetime.now())
        await self._write(content)

    async def log_context_cleared(self) -> None:
        """Log a context cleared event."""
        if not self._runtime_enabled:
            return

        if not self._initialized:
            await self.initialize()

        content = self.formatter.format_context_cleared(datetime.now())
        await self._write(content)

    async def log_tool_call(self, tool_name: str, arguments: dict) -> None:
        """Log a tool call."""
        if not self._runtime_enabled or not self.config.include_tool_calls:
            return

        if not self._initialized:
            await self.initialize()

        content = self.formatter.format_tool_call(tool_name, arguments, datetime.now())
        await self._write(content)

    async def log_tool_output(self, tool_name: str, output: Any) -> None:
        """Log tool output."""
        if not self._runtime_enabled or not self.config.include_tool_outputs:
            return

        if not self._initialized:
            await self.initialize()

        content = self.formatter.format_tool_output(tool_name, output, datetime.now())
        await self._write(content)

    async def close(self) -> None:
        """Close the log file."""
        if self._file_handle:
            async with self._write_lock:
                try:
                    self._file_handle.close()
                except Exception:
                    pass
                finally:
                    self._file_handle = None
                    self._initialized = False

    def __del__(self):
        """Ensure file handle is closed on deletion."""
        if self._file_handle:
            try:
                self._file_handle.close()
            except Exception:
                pass
