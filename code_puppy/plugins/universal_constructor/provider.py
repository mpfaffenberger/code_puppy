"""Universal Constructor implementation of the core provider seam."""

from pathlib import Path
from typing import Any, Callable


class PluginUniversalConstructorProvider:
    """Expose UC plugin capabilities without leaking plugin imports into core."""

    @property
    def tools_dir(self) -> Path:
        from . import USER_UC_DIR

        return USER_UC_DIR

    def list_tools(self, include_disabled: bool = False) -> list[Any]:
        from .registry import get_registry

        return get_registry().list_tools(include_disabled=include_disabled)

    def get_tool(self, name: str) -> Any | None:
        from .registry import get_registry

        return get_registry().get_tool(name)

    def get_tool_function(self, name: str) -> Callable[..., Any] | None:
        from .registry import get_registry

        return get_registry().get_tool_function(name)

    def reload(self) -> int:
        from .registry import get_registry

        return get_registry().reload()

    def validate_syntax(self, code: str) -> Any:
        from .sandbox import validate_syntax

        return validate_syntax(code)

    def extract_function_info(self, code: str) -> Any:
        from .sandbox import extract_function_info

        return extract_function_info(code)

    def extract_tool_meta(self, code: str) -> dict[str, Any] | None:
        from .sandbox import _extract_tool_meta

        return _extract_tool_meta(code)

    def validate_tool_meta(self, meta: dict[str, Any]) -> list[str]:
        from .sandbox import _validate_tool_meta

        return _validate_tool_meta(meta)

    def check_dangerous_patterns(self, code: str) -> Any:
        from .sandbox import check_dangerous_patterns

        return check_dangerous_patterns(code)


provider = PluginUniversalConstructorProvider()
