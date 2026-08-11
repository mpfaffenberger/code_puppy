"""Ownership-aware provider seam for the optional Universal Constructor plugin."""

from dataclasses import dataclass
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


@dataclass(frozen=True)
class UniversalConstructorProviderRegistration:
    """Identity token for one provider registration and its plugin owner."""

    provider: UniversalConstructorProvider
    owner: str | None


_registration: UniversalConstructorProviderRegistration | None = None


def register_universal_constructor_provider(
    provider: UniversalConstructorProvider,
    *,
    owner: str | None = None,
) -> UniversalConstructorProviderRegistration:
    """Install a provider and return an ownership-aware identity token.

    Re-registering replaces the current provider. The returned token can be
    explicitly unregistered; stale tokens cannot remove a newer registration.
    When no owner is supplied, the plugin loader's current owner is captured.
    """
    from code_puppy.callbacks import get_loading_context

    registration = UniversalConstructorProviderRegistration(
        provider=provider,
        owner=owner if owner is not None else get_loading_context(),
    )
    global _registration
    _registration = registration
    return registration


def unregister_universal_constructor_provider(
    registration: UniversalConstructorProviderRegistration,
) -> bool:
    """Unregister ``registration`` only if it is still active."""
    global _registration
    if _registration is not registration:
        return False
    _registration = None
    return True


def get_universal_constructor_provider() -> UniversalConstructorProvider | None:
    """Return the provider only while its owning plugin is enabled."""
    registration = _registration
    if registration is None:
        return None

    from code_puppy.callbacks import is_callback_owner_enabled

    if not is_callback_owner_enabled(registration.owner):
        return None
    return registration.provider
