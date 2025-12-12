"""Tests for session logging functionality."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from code_puppy.session_logging.config_schema import (
    SessionLoggingConfig,
    load_session_logging_config_from_dict,
)
from code_puppy.session_logging.formatters import (
    JSONFormatter,
    MarkdownFormatter,
    create_formatter,
)
from code_puppy.session_logging.logger import SessionLogger


class TestSessionLoggingConfig:
    """Tests for SessionLoggingConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SessionLoggingConfig()
        assert config.enabled is False
        assert config.format == "markdown"
        assert config.include_user_prompts is True
        assert config.include_agent_reasoning is True
        assert config.timestamp_format == "ISO8601"

    def test_resolve_log_path(self):
        """Test log path resolution with session_id substitution."""
        config = SessionLoggingConfig(
            log_file="~/.code_puppy/sessions/{session_id}.md"
        )
        path = config.resolve_log_path("test-session-123")
        assert "test-session-123.md" in str(path)
        assert str(path).startswith("/")  # Should be absolute

    def test_load_from_dict(self):
        """Test loading config from dictionary."""
        config_dict = {
            "enabled": True,
            "format": "json",
            "user_prompts": False,
            "timestamp_format": "unix",
        }
        config = load_session_logging_config_from_dict(config_dict)
        assert config.enabled is True
        assert config.format == "json"
        assert config.include_user_prompts is False
        assert config.timestamp_format == "unix"


class TestFormatters:
    """Tests for log formatters."""

    def test_create_formatter_markdown(self):
        """Test creating markdown formatter."""
        formatter = create_formatter("markdown", "ISO8601")
        assert isinstance(formatter, MarkdownFormatter)

    def test_create_formatter_json(self):
        """Test creating JSON formatter."""
        formatter = create_formatter("json", "unix")
        assert isinstance(formatter, JSONFormatter)

    def test_markdown_header(self):
        """Test markdown header formatting."""
        formatter = MarkdownFormatter("ISO8601")
        header = formatter.format_header("test-session", datetime.now())
        assert "# Session Log: test-session" in header
        assert "**Started:**" in header

    def test_markdown_user_prompt(self):
        """Test markdown user prompt formatting."""
        formatter = MarkdownFormatter("ISO8601")
        prompt = formatter.format_user_prompt("Test prompt", datetime.now())
        assert "## 👤 User Prompt" in prompt
        assert "Test prompt" in prompt

    def test_markdown_tool_call(self):
        """Test markdown tool call formatting."""
        formatter = MarkdownFormatter("ISO8601")
        tool_call = formatter.format_tool_call(
            "edit_file", {"file_path": "test.py"}, datetime.now()
        )
        assert "### 🔧 Tool Call: `edit_file`" in tool_call
        assert "file_path" in tool_call
        assert "```json" in tool_call

    def test_json_entries(self):
        """Test JSON formatter creates entries."""
        formatter = JSONFormatter("ISO8601")
        formatter.format_header("test-session", datetime.now())
        formatter.format_user_prompt("Test prompt", datetime.now())

        assert len(formatter.entries) == 2
        assert formatter.entries[0]["type"] == "session_start"
        assert formatter.entries[1]["type"] == "user_prompt"

    def test_timestamp_formats(self):
        """Test different timestamp formats."""
        dt = datetime(2025, 1, 1, 12, 0, 0)

        iso_formatter = MarkdownFormatter("ISO8601")
        iso_ts = iso_formatter.format_timestamp(dt)
        assert "2025-01-01" in iso_ts

        unix_formatter = MarkdownFormatter("unix")
        unix_ts = unix_formatter.format_timestamp(dt)
        assert unix_ts.isdigit()

        human_formatter = MarkdownFormatter("human")
        human_ts = human_formatter.format_timestamp(dt)
        assert "2025-01-01 12:00:00" == human_ts


class TestSessionLogger:
    """Tests for SessionLogger."""

    @pytest.mark.asyncio
    async def test_logger_initialization(self):
        """Test logger initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=True, log_file=log_file)
            logger = SessionLogger(config, "test-session")

            await logger.initialize()

            assert logger._initialized is True
            assert Path(log_file).exists()

            await logger.close()

    @pytest.mark.asyncio
    async def test_disabled_logger_no_file(self):
        """Test that disabled logger doesn't create files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "should_not_exist.md")
            config = SessionLoggingConfig(enabled=False, log_file=log_file)
            logger = SessionLogger(config, "test-session")

            await logger.initialize()
            await logger.log_user_prompt("Test")
            await logger.close()

            assert not Path(log_file).exists()

    @pytest.mark.asyncio
    async def test_log_user_prompt(self):
        """Test logging user prompts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(
                enabled=True, log_file=log_file, format="markdown"
            )
            logger = SessionLogger(config, "test-session")
            await logger.initialize()

            await logger.log_user_prompt("Create a file")
            await logger.close()

            content = Path(log_file).read_text()
            assert "Create a file" in content
            assert "👤 User Prompt" in content

    @pytest.mark.asyncio
    async def test_log_agent_reasoning(self):
        """Test logging agent reasoning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=True, log_file=log_file)
            logger = SessionLogger(config, "test-session")
            await logger.initialize()

            await logger.log_agent_reasoning("I need to analyze the code")
            await logger.close()

            content = Path(log_file).read_text()
            assert "I need to analyze the code" in content
            assert "🤔 Agent Reasoning" in content

    @pytest.mark.asyncio
    async def test_log_tool_calls(self):
        """Test logging tool calls and outputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=True, log_file=log_file)
            logger = SessionLogger(config, "test-session")
            await logger.initialize()

            await logger.log_tool_call("list_files", {"directory": "."})
            await logger.log_tool_output("list_files", {"files": ["a.py", "b.py"]})
            await logger.close()

            content = Path(log_file).read_text()
            assert "list_files" in content
            assert "directory" in content
            assert "a.py" in content

    @pytest.mark.asyncio
    async def test_json_format_logging(self):
        """Test JSON format logging."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.json")
            config = SessionLoggingConfig(
                enabled=True, log_file=log_file, format="json"
            )
            logger = SessionLogger(config, "test-session")
            await logger.initialize()

            await logger.log_user_prompt("Test prompt")
            await logger.log_agent_response("Test response")
            await logger.close()

            content = Path(log_file).read_text()
            lines = content.strip().split("\n")

            # Each line should be valid JSON
            for line in lines:
                entry = json.loads(line)
                assert "type" in entry
                assert "timestamp" in entry

    @pytest.mark.asyncio
    async def test_selective_logging(self):
        """Test selective logging with config options."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(
                enabled=True,
                log_file=log_file,
                include_user_prompts=True,
                include_agent_responses=False,  # Disabled
            )
            logger = SessionLogger(config, "test-session")
            await logger.initialize()

            await logger.log_user_prompt("User input")
            await logger.log_agent_response("Agent output")
            await logger.close()

            content = Path(log_file).read_text()
            assert "User input" in content
            assert "Agent output" not in content  # Should be excluded

    @pytest.mark.asyncio
    async def test_truncate_long_output(self):
        """Test that very long outputs are truncated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=True, log_file=log_file)
            logger = SessionLogger(config, "test-session")
            await logger.initialize()

            # Create a very long output (>5000 chars)
            long_output = "x" * 6000
            await logger.log_tool_output("some_tool", long_output)
            await logger.close()

            content = Path(log_file).read_text()
            assert "(truncated)" in content
            assert len(content) < 7000  # Should be truncated

    @pytest.mark.asyncio
    async def test_runtime_enable_disable(self):
        """Test runtime enable/disable functionality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=True, log_file=log_file)
            logger = SessionLogger(config, "test-session")

            # Initially enabled
            assert logger.is_enabled() is True

            # Disable at runtime
            logger.set_enabled(False)
            assert logger.is_enabled() is False

            # Log should be ignored when disabled
            await logger.initialize()
            await logger.log_user_prompt("Should not be logged")

            # Re-enable
            logger.set_enabled(True)
            assert logger.is_enabled() is True

            await logger.initialize()
            await logger.log_user_prompt("Should be logged")
            await logger.close()

            content = Path(log_file).read_text()
            assert "Should not be logged" not in content
            assert "Should be logged" in content
