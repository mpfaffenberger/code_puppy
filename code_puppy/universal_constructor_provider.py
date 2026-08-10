"""Provider seam for the optional Universal Constructor plugin."""

from pathlib import Path
from typing import Any, Callable, Protocol


class UniversalConstructorProvider(Protocol):
    """Capabilities core consumers need from a Universal Constructor plugin."""

    @property
    def tools_dir(self) -> Path:
        """Directory containing user-created tools."""

    def list_tools(self, include_disabled: bool = False) -> list[Any]:
        """Return discovered tools."""

    def get_tool(self, name: str) -> Any | None:
        """Return tool metadata by full name."""

    def get_tool_function(self, name: str) -> Callable[..., Any] | None:
        """Return a tool's callable implementation."""

    def reload(self) -> int:
        """Reload all tools and return the number discovered."""

    def validate_syntax(self, code: str) -> Any:
        """Validate Python syntax."""

    def extract_function_info(self, code: str) -> Any:
        """Extract callable metadata from Python source."""

    def extract_tool_meta(self, code: str) -> dict[str, Any] | None:
        """Extract TOOL_META from Python source."""

    def validate_tool_meta(self, meta: dict[str, Any]) -> list[str]:
        """Validate TOOL_META fields."""

    def check_dangerous_patterns(self, code: str) -> Any:
        """Return non-blocking safety warnings for Python source."""


_provider: UniversalConstructorProvider | None = None


def register_universal_constructor_provider(
    provider: UniversalConstructorProvider,
) -> None:
    """Register the process-wide Universal Constructor provider."""
    global _provider
    _provider = provider


def get_universal_constructor_provider() -> UniversalConstructorProvider | None:
    """Return the registered provider, or ``None`` when the plugin is absent."""
    return _provider


def clear_universal_constructor_provider() -> None:
    """Clear the provider, primarily for plugin unloads and isolated tests."""
    global _provider
    _provider = None
