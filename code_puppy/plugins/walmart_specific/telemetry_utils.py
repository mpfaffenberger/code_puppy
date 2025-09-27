"""Telemetry utility functions for collecting and formatting telemetry data."""

import os
import platform
from typing import Any, Dict, Union

from code_puppy import __version__
from code_puppy.agents import get_current_agent
from code_puppy.config import get_puppy_name
from code_puppy.tools.command_runner import ShellCommandOutput
from code_puppy.tools.file_modifications import EditFilePayload


def build_telemetry_data(payload: EditFilePayload, session_id: str) -> dict:
    """Build telemetry data payload from EditFilePayload."""
    file_path = getattr(payload, "file_path", "unknown")
    file_name = os.path.basename(file_path) if file_path else "unknown"

    # Count lines created and deleted separately
    lines_created, lines_deleted = count_created_and_deleted_lines(payload)
    total_lines = (
        lines_created + lines_deleted
    )  # Total activity (additions + deletions)

    # Count characters created and deleted separately
    chars_created, chars_deleted = count_created_and_deleted_characters(payload)
    total_chars = (
        chars_created + chars_deleted
    )  # Total activity (additions + deletions)

    # Detect language from file extension
    language = detect_language(file_path)

    # Determine operation type
    operation_type = determine_operation_type(payload)
    agent = get_current_agent()
    # Build base telemetry data with separate created/deleted tracking
    telemetry_data = {
        "puppy_name": get_puppy_name(),
        "puppy_version": __version__,
        "tool_name": "edit_file",
        "model_name": agent.get_model_name(),
        "lines_created": lines_created,
        "lines_deleted": lines_deleted,
        "total_lines_of_code": total_lines,  # Total activity (created + deleted)
        "characters_created": chars_created,
        "characters_deleted": chars_deleted,
        "total_characters_generated": total_chars,  # Total activity (created + deleted)
        "operating_system": platform.system(),
        "file_name": file_name,
        "language_detected": language,
        "file_types_involved": [get_file_extension(file_path)],
        "operation_type": operation_type,
        "session_id": session_id,
        "success_status": "success",
        "has_tests_generated": has_test_content(payload),
        "has_documentation_generated": has_documentation_content(payload),
    }

    return telemetry_data


def count_created_and_deleted_lines(payload: EditFilePayload) -> tuple[int, int]:
    """Count lines created and deleted from the payload.

    Returns:
        tuple[int, int]: (lines_created, lines_deleted)
    """
    try:
        lines_created = 0
        lines_deleted = 0

        if hasattr(payload, "content") and payload.content:
            # ContentPayload: All content is considered "created"
            # Note: We can't easily track what was deleted without reading the original file
            lines_created = len(payload.content.splitlines())
            lines_deleted = 0  # Would need original file content to calculate

        elif hasattr(payload, "replacements") and payload.replacements:
            # ReplacementsPayload: Track both old (deleted) and new (created) content
            for replacement in payload.replacements:
                if hasattr(replacement, "old_str") and replacement.old_str:
                    lines_deleted += len(replacement.old_str.splitlines())
                if hasattr(replacement, "new_str") and replacement.new_str:
                    lines_created += len(replacement.new_str.splitlines())

        elif hasattr(payload, "delete_snippet") and payload.delete_snippet:
            # DeleteSnippetPayload: Only deletes content
            lines_deleted = len(payload.delete_snippet.splitlines())
            lines_created = 0

        return lines_created, lines_deleted
    except Exception:
        return 0, 0


def count_created_and_deleted_characters(payload: EditFilePayload) -> tuple[int, int]:
    """Count characters created and deleted from the payload.

    Returns:
        tuple[int, int]: (characters_created, characters_deleted)
    """
    try:
        chars_created = 0
        chars_deleted = 0

        if hasattr(payload, "content") and payload.content:
            # ContentPayload: All content is considered "created"
            chars_created = len(payload.content)
            chars_deleted = 0  # Would need original file content to calculate

        elif hasattr(payload, "replacements") and payload.replacements:
            # ReplacementsPayload: Track both old (deleted) and new (created) content
            for replacement in payload.replacements:
                if hasattr(replacement, "old_str") and replacement.old_str:
                    chars_deleted += len(replacement.old_str)
                if hasattr(replacement, "new_str") and replacement.new_str:
                    chars_created += len(replacement.new_str)

        elif hasattr(payload, "delete_snippet") and payload.delete_snippet:
            # DeleteSnippetPayload: Only deletes content
            chars_deleted = len(payload.delete_snippet)
            chars_created = 0

        return chars_created, chars_deleted
    except Exception:
        return 0, 0


def count_total_characters(payload: EditFilePayload) -> int:
    """Count net characters generated from the payload (for backward compatibility)."""
    chars_created, chars_deleted = count_created_and_deleted_characters(payload)
    return chars_created - chars_deleted


def detect_language(file_path: str) -> str:
    """Detect programming language from file extension."""
    if not file_path:
        return "other"

    ext = os.path.splitext(file_path)[1].lower()
    language_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "jsx",
        ".tsx": "tsx",
        ".java": "java",
        ".cpp": "cpp",
        ".c": "c",
        ".cs": "csharp",
        ".go": "go",
        ".rs": "rust",
        ".php": "php",
        ".rb": "ruby",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".sql": "sql",
        ".sh": "bash",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".xml": "xml",
        ".md": "markdown",
    }
    return language_map.get(ext, "other")


def get_file_extension(file_path: str) -> str:
    """Get file extension from file path."""
    if not file_path:
        return "unknown"
    ext = os.path.splitext(file_path)[1]
    return ext if ext else "no_extension"


def determine_operation_type(payload: EditFilePayload) -> str:
    """Determine the type of operation from the payload."""
    try:
        if hasattr(payload, "content") and payload.content:
            # Full content replacement suggests create or major edit
            return "create"
        elif hasattr(payload, "replacements") and payload.replacements:
            return "edit"
        elif hasattr(payload, "delete_snippet") and payload.delete_snippet:
            return "delete"
        return "edit"
    except Exception:
        return "edit"


def has_test_content(payload: EditFilePayload) -> bool:
    """Check if the generated content includes test-related code."""
    try:
        content_to_check = ""
        if hasattr(payload, "content") and payload.content:
            content_to_check = payload.content.lower()
        elif hasattr(payload, "replacements") and payload.replacements:
            for replacement in payload.replacements:
                if hasattr(replacement, "new_str") and replacement.new_str:
                    content_to_check += replacement.new_str.lower()

        test_indicators = [
            "test_",
            "def test",
            "class test",
            "it(",
            "describe(",
            "expect(",
            "assert",
            "unittest",
        ]
        return any(indicator in content_to_check for indicator in test_indicators)
    except Exception:
        return False


def has_documentation_content(payload: EditFilePayload) -> bool:
    """Check if the generated content includes documentation."""
    try:
        content_to_check = ""
        if hasattr(payload, "content") and payload.content:
            content_to_check = payload.content.lower()
        elif hasattr(payload, "replacements") and payload.replacements:
            for replacement in payload.replacements:
                if hasattr(replacement, "new_str") and replacement.new_str:
                    content_to_check += replacement.new_str.lower()

        doc_indicators = [
            '"""',
            "'''",
            "/**",
            "##",
            "readme",
            "docs",
            "@param",
            "@return",
            "docstring",
        ]
        return any(indicator in content_to_check for indicator in doc_indicators)
    except Exception:
        return False


def build_delete_file_telemetry_data(result: Dict[str, Any], session_id: str) -> dict:
    """Build telemetry data payload from delete_file result."""
    file_path = result.get("path", "unknown")
    file_name = os.path.basename(file_path) if file_path else "unknown"

    # For delete operations, we don't generate code, but we can track the file being deleted
    language = detect_language(file_path)

    # Build telemetry data for delete operation
    # Note: We'd need the original file content to accurately count deleted lines
    # This would require modifying the delete_file tool to capture content first
    lines_deleted = len(result["diff"].split("\n")) if result.get("diff") else 0
    chars_deleted = len(result["diff"]) if result.get("diff") else 0
    agent = get_current_agent()
    telemetry_data = {
        "puppy_name": get_puppy_name(),
        "puppy_version": __version__,
        "tool_name": "delete_file",
        "model_name": agent.get_model_name(),
        "lines_created": 0,  # Delete operations don't create lines
        "lines_deleted": lines_deleted,
        "total_lines_of_code": lines_deleted,  # Total activity (0 + deleted)
        "characters_created": 0,
        "characters_deleted": chars_deleted,
        "total_characters_generated": chars_deleted,  # Total activity (0 + deleted)
        "operating_system": platform.system(),
        "file_name": file_name,
        "language_detected": language,
        "file_types_involved": [get_file_extension(file_path)],
        "operation_type": "delete",
        "session_id": session_id,
        "success_status": "success" if result.get("success", False) else "failure",
        "has_tests_generated": False,  # Delete operations don't generate tests
        "has_documentation_generated": False,  # Delete operations don't generate docs
    }

    # Add error information if deletion failed
    if not result.get("success", False) and "error" in result:
        telemetry_data["error_type"] = "deletion_failed"

    return telemetry_data


def build_shell_command_telemetry_data(
    result: Union[ShellCommandOutput, Dict[str, Any]], session_id: str
) -> dict:
    """Build telemetry data payload from run_shell_command result.

    Args:
        result: ShellCommandOutput object or dict with command execution results
        session_id: Session identifier
    """
    # Handle both ShellCommandOutput objects and dict results
    if hasattr(result, "command"):
        # ShellCommandOutput object - access attributes directly
        command = result.command or "unknown"
        success = result.success
        execution_time = result.execution_time
        timeout = result.timeout
        user_interrupted = result.user_interrupted
        exit_code = result.exit_code
    else:
        # Dict result - use .get() method
        command = result.get("command", "unknown")
        success = result.get("success", False)
        execution_time = result.get("execution_time", 0)
        timeout = result.get("timeout", False)
        user_interrupted = result.get("user_interrupted", False)
        exit_code = result.get("exit_code")

    # Determine command type and potential language
    command_type, detected_language = analyze_shell_command(command)

    # Build telemetry data for shell command operation
    command_lines = len(command.split("\n")) if command else 0
    command_chars = len(command) if command else 0
    agent = get_current_agent()
    telemetry_data = {
        "puppy_name": get_puppy_name(),
        "puppy_version": __version__,
        "tool_name": "run_shell_command",
        "model_name": agent.get_model_name(),
        "lines_created": command_lines,  # Shell commands don't directly create lines
        "lines_deleted": 0,  # Shell commands don't directly delete lines
        "total_lines_of_code": command_lines,  # Total activity (created + 0)
        "characters_created": command_chars,  # Shell commands don't directly create characters
        "characters_deleted": 0,  # Shell commands don't directly delete characters
        "total_characters_generated": command_chars,  # Total activity (created + 0)
        "operating_system": platform.system(),
        "file_name": "terminal",  # Shell commands don't work on specific files, use 'terminal' as default
        "language_detected": detected_language,
        "file_types_involved": [],  # Shell commands don't directly involve files
        "operation_type": command_type,
        "session_id": session_id,
        "success_status": "success" if success else "failure",
        "has_tests_generated": has_test_command(command),
        "has_documentation_generated": has_docs_command(command),
        "execution_time_ms": int((execution_time or 0) * 1000),
    }

    # Add error information if command failed
    if not success:
        if timeout:
            telemetry_data["error_type"] = "timeout"
        elif user_interrupted:
            telemetry_data["error_type"] = "user_interrupted"
        elif exit_code and exit_code != 0:
            telemetry_data["error_type"] = f"exit_code_{exit_code}"
        else:
            telemetry_data["error_type"] = "command_failed"

    return telemetry_data


def analyze_shell_command(command: str) -> tuple[str, str]:
    """Analyze shell command to determine operation type and language."""
    if not command:
        return "unknown", "other"

    cmd_lower = command.lower().strip()

    # Determine operation type
    if any(
        cmd in cmd_lower
        for cmd in ["test", "pytest", "npm test", "yarn test", "jest", "mocha"]
    ):
        operation_type = "test"
    elif any(
        cmd in cmd_lower
        for cmd in ["build", "compile", "make", "npm run build", "yarn build"]
    ):
        operation_type = "build"
    elif any(
        cmd in cmd_lower
        for cmd in [
            "install",
            "pip install",
            "npm install",
            "yarn install",
            "apt install",
        ]
    ):
        operation_type = "install"
    elif any(cmd in cmd_lower for cmd in ["git", "clone", "push", "pull", "commit"]):
        operation_type = "git"
    elif any(cmd in cmd_lower for cmd in ["docker", "kubectl", "helm"]):
        operation_type = "container"
    elif any(
        cmd in cmd_lower for cmd in ["ls", "dir", "find", "grep", "cat", "head", "tail"]
    ):
        operation_type = "file_operation"
    elif any(cmd in cmd_lower for cmd in ["start", "run", "serve", "dev"]):
        operation_type = "run"
    else:
        operation_type = "shell"

    # Determine language/technology
    if any(tech in cmd_lower for tech in ["python", "pip", "pytest", "poetry", "uv"]):
        language = "python"
    elif any(tech in cmd_lower for tech in ["npm", "yarn", "node", "jest", "mocha"]):
        language = "javascript"
    elif any(tech in cmd_lower for tech in ["java", "mvn", "gradle"]):
        language = "java"
    elif any(tech in cmd_lower for tech in ["docker", "dockerfile"]):
        language = "docker"
    elif any(tech in cmd_lower for tech in ["git"]):
        language = "git"
    elif any(tech in cmd_lower for tech in ["go ", "golang"]):
        language = "go"
    elif any(tech in cmd_lower for tech in ["rust", "cargo"]):
        language = "rust"
    elif any(tech in cmd_lower for tech in ["dotnet", "csharp", ".net"]):
        language = "csharp"
    else:
        language = "shell"

    return operation_type, language


def has_test_command(command: str) -> bool:
    """Check if the shell command is test-related."""
    if not command:
        return False

    cmd_lower = command.lower()
    test_indicators = ["test", "pytest", "jest", "mocha", "spec", "karma", "cypress"]
    return any(indicator in cmd_lower for indicator in test_indicators)


def has_docs_command(command: str) -> bool:
    """Check if the shell command is documentation-related."""
    if not command:
        return False

    cmd_lower = command.lower()
    doc_indicators = [
        "docs",
        "documentation",
        "sphinx",
        "mkdocs",
        "javadoc",
        "typedoc",
        "readme",
    ]
    return any(indicator in cmd_lower for indicator in doc_indicators)


def enqueue_telemetry_data(telemetry_data: Dict[str, Any]) -> None:
    """Enqueue telemetry data for background processing.

    This is the centralized function for all telemetry collection that follows
    DRY principles by avoiding duplicate HTTP request code.

    Args:
        telemetry_data: Telemetry payload to enqueue for processing
    """
    try:
        from code_puppy.plugins.walmart_specific.telemetry_queue import (
            get_telemetry_queue,
        )

        queue = get_telemetry_queue()
        queue.enqueue_telemetry(telemetry_data)
    except ImportError:
        # Fallback if telemetry_queue is not available
        from code_puppy.messaging import emit_system_message

        emit_system_message(
            "[dim yellow]Telemetry queue not available, skipping telemetry[/dim yellow]"
        )
    except Exception as e:
        from code_puppy.messaging import emit_system_message

        emit_system_message(
            f"[dim red]Failed to enqueue telemetry: {str(e)[:50]}[/dim red]"
        )
