"""
Data models for the hook engine.

Defines all data structures used throughout the hook engine with full type
safety and validation.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


@dataclass
class HookConfig:
    """
    Configuration for a single hook.

    Attributes:
        matcher: Pattern to match against events (e.g., "Edit && .py")
        type: Type of hook action ("command" or "prompt")
        command: Command or prompt text to execute
        timeout: Maximum execution time in milliseconds (default: 5000)
        once: Execute only once per session (default: False)
        enabled: Whether this hook is enabled (default: True)
        id: Optional unique identifier for this hook
    """

    matcher: str
    type: Literal["command", "prompt"]
    command: str
    timeout: int = 5000
    once: bool = False
    enabled: bool = True
    id: Optional[str] = None

    def __post_init__(self):
        """Validate hook configuration after initialization."""
        if not self.matcher:
            raise ValueError("Hook matcher cannot be empty")

        if self.type not in ("command", "prompt"):
            raise ValueError(
                f"Hook type must be 'command' or 'prompt', got: {self.type}"
            )

        if not self.command:
            raise ValueError("Hook command cannot be empty")

        if self.timeout < 100:
            raise ValueError(f"Hook timeout must be >= 100ms, got: {self.timeout}")

        if self.id is None:
            import hashlib

            content = f"{self.matcher}:{self.type}:{self.command}"
            self.id = hashlib.sha256(content.encode()).hexdigest()[:12]


@dataclass
class EventData:
    """
    Input data for hook processing.

    Attributes:
        event_type: Type of event (PreToolUse, PostToolUse, etc.)
        tool_name: Name of the tool being called
        tool_args: Arguments passed to the tool
        context: Optional context metadata (result, duration, etc.)
    """

    event_type: str
    tool_name: str
    tool_args: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.event_type:
            raise ValueError("Event type cannot be empty")
        if not self.tool_name:
            raise ValueError("Tool name cannot be empty")


@dataclass
class ExecutionResult:
    """
    Result from executing a hook.

    Attributes:
        blocked: Whether the hook blocked the operation
        hook_command: The command that was executed
        stdout: Standard output from command
        stderr: Standard error from command
        exit_code: Exit code from command execution
        duration_ms: Execution duration in milliseconds
        error: Error message if execution failed
        hook_id: ID of the hook that was executed
    """

    blocked: bool
    hook_command: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None
    hook_id: Optional[str] = None

    @property
    def success(self) -> bool:
        """Whether the hook executed successfully (exit code 0)."""
        return self.exit_code == 0 and self.error is None

    @property
    def output(self) -> str:
        """Combined stdout and stderr."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(self.stderr)
        return "\n".join(parts)


@dataclass
class HookGroup:
    """A group of hooks that share the same matcher."""

    matcher: str
    hooks: List[HookConfig] = field(default_factory=list)

    def __post_init__(self):
        if not self.matcher:
            raise ValueError("Hook group matcher cannot be empty")


@dataclass
class HookRegistry:
    """Registry of all hooks organized by event type."""

    pre_tool_use: List[HookConfig] = field(default_factory=list)
    post_tool_use: List[HookConfig] = field(default_factory=list)
    session_start: List[HookConfig] = field(default_factory=list)
    session_end: List[HookConfig] = field(default_factory=list)
    pre_compact: List[HookConfig] = field(default_factory=list)
    user_prompt_submit: List[HookConfig] = field(default_factory=list)
    notification: List[HookConfig] = field(default_factory=list)
    stop: List[HookConfig] = field(default_factory=list)
    subagent_stop: List[HookConfig] = field(default_factory=list)

    _executed_once_hooks: set = field(default_factory=set, repr=False)

    def get_hooks_for_event(self, event_type: str) -> List[HookConfig]:
        attr_name = self._normalize_event_type(event_type)
        if not hasattr(self, attr_name):
            return []
        all_hooks = getattr(self, attr_name)
        enabled_hooks = []
        for hook in all_hooks:
            if not hook.enabled:
                continue
            if hook.once and hook.id in self._executed_once_hooks:
                continue
            enabled_hooks.append(hook)
        return enabled_hooks

    def mark_hook_executed(self, hook_id: str) -> None:
        self._executed_once_hooks.add(hook_id)

    def reset_once_hooks(self) -> None:
        self._executed_once_hooks.clear()

    @staticmethod
    def _normalize_event_type(event_type: str) -> str:
        import re

        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", event_type)
        return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    def add_hook(self, event_type: str, hook: HookConfig) -> None:
        attr_name = self._normalize_event_type(event_type)
        if not hasattr(self, attr_name):
            raise ValueError(f"Unknown event type: {event_type}")
        getattr(self, attr_name).append(hook)

    def remove_hook(self, event_type: str, hook_id: str) -> bool:
        attr_name = self._normalize_event_type(event_type)
        if not hasattr(self, attr_name):
            return False
        hooks_list = getattr(self, attr_name)
        for i, hook in enumerate(hooks_list):
            if hook.id == hook_id:
                hooks_list.pop(i)
                return True
        return False

    def count_hooks(self, event_type: Optional[str] = None) -> int:
        if event_type is None:
            total = 0
            for attr in [
                "pre_tool_use",
                "post_tool_use",
                "session_start",
                "session_end",
                "pre_compact",
                "user_prompt_submit",
                "notification",
                "stop",
                "subagent_stop",
            ]:
                total += len(getattr(self, attr))
            return total
        attr_name = self._normalize_event_type(event_type)
        if not hasattr(self, attr_name):
            return 0
        return len(getattr(self, attr_name))


@dataclass
class ProcessEventResult:
    """Result from processing an event through the hook engine."""

    blocked: bool
    executed_hooks: int
    results: List[ExecutionResult]
    blocking_reason: Optional[str] = None
    total_duration_ms: float = 0.0

    @property
    def all_successful(self) -> bool:
        return all(result.success for result in self.results)

    @property
    def failed_hooks(self) -> List[ExecutionResult]:
        return [result for result in self.results if not result.success]

    def get_combined_output(self) -> str:
        outputs = []
        for result in self.results:
            if result.output:
                outputs.append(f"[{result.hook_command}]\n{result.output}")
        return "\n\n".join(outputs)
