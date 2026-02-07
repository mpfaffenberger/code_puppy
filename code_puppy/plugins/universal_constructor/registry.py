"""UC Tool Registry - discovers and manages user-created tools.

This module provides the core registry that scans the user's UC directory,
loads tool metadata, extracts function signatures, and provides access
to enabled tools for the LLM.
"""

import importlib.util
import inspect
import logging
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Callable, Dict, List, Optional, Tuple

from . import USER_UC_DIR
from .models import ToolMeta, UCToolInfo

logger = logging.getLogger(__name__)


class UCRegistry:
    """Registry for discovering and managing UC tools.

    Scans the user's UC directory recursively, loading tool metadata
    and providing access to enabled tools. Supports namespacing via
    subdirectories (e.g., api/weather.py → "api.weather").
    """

    def __init__(self, tools_dir: Optional[Path] = None):
        """Initialize the registry.

        Args:
            tools_dir: Directory to scan for tools. Defaults to USER_UC_DIR.
        """
        self._tools_dir = tools_dir or USER_UC_DIR
        self._tools: Dict[str, UCToolInfo] = {}
        self._modules: Dict[str, ModuleType] = {}
        self._last_scan: Optional[datetime] = None

    def ensure_tools_dir(self) -> Path:
        """Ensure the tools directory exists.

        Returns:
            Path to the tools directory.
        """
        self._tools_dir.mkdir(parents=True, exist_ok=True)
        return self._tools_dir

    def scan(self) -> int:
        """Scan the tools directory and load all tools.

        Returns:
            Number of tools found.
        """
        self._tools.clear()
        self._modules.clear()

        if not self._tools_dir.exists():
            logger.debug(f"Tools directory does not exist: {self._tools_dir}")
            return 0

        # Find all Python files recursively
        tool_files = list(self._tools_dir.rglob("*.py"))

        for tool_file in tool_files:
            # Skip __init__.py and hidden files
            if tool_file.name.startswith("_") or tool_file.name.startswith("."):
                continue

            try:
                tool_info = self._load_tool_file(tool_file)
                if tool_info:
                    self._tools[tool_info.full_name] = tool_info
                    logger.debug(f"Loaded tool: {tool_info.full_name}")
            except Exception as e:
                logger.warning(f"Failed to load tool from {tool_file}: {e}")

        self._last_scan = datetime.now()
        logger.info(f"Scanned {len(self._tools)} tools from {self._tools_dir}")
        return len(self._tools)

    def _load_tool_file(self, file_path: Path) -> Optional[UCToolInfo]:
        """Load a tool from a Python file.

        Args:
            file_path: Path to the Python file.

        Returns:
            UCToolInfo if valid tool, None otherwise.
        """
        # Calculate namespace from relative path
        try:
            rel_path = file_path.relative_to(self._tools_dir)
            namespace_parts = list(rel_path.parent.parts)
            namespace = ".".join(namespace_parts) if namespace_parts else ""
        except ValueError:
            namespace = ""

        # Load the module
        module = self._load_module(file_path)
        if module is None:
            return None

        # Check for TOOL_META
        if not hasattr(module, "TOOL_META"):
            logger.debug(f"No TOOL_META found in {file_path}")
            return None

        raw_meta = dict(module.TOOL_META)  # Copy to avoid mutating module constant
        if not isinstance(raw_meta, dict):
            logger.warning(f"TOOL_META is not a dict in {file_path}")
            return None

        # Set namespace from directory structure
        raw_meta["namespace"] = namespace

        # Parse metadata
        try:
            meta = ToolMeta(**raw_meta)
        except Exception as e:
            logger.warning(f"Invalid TOOL_META in {file_path}: {e}")
            return None

        # Find the callable function
        func, func_name = self._find_tool_function(module, meta.name)
        if func is None:
            logger.warning(f"No callable function found in {file_path}")
            return None

        # Extract signature
        try:
            sig = inspect.signature(func)
            signature_str = f"{func_name}{sig}"
        except (ValueError, TypeError):
            signature_str = f"{func_name}(...)"

        # Extract docstring
        docstring = inspect.getdoc(func)

        # Store module reference for later calls
        full_name = f"{namespace}.{meta.name}" if namespace else meta.name
        self._modules[full_name] = module

        return UCToolInfo(
            meta=meta,
            signature=signature_str,
            source_path=str(file_path),
            function_name=func_name,
            docstring=docstring,
        )

    def _load_module(self, file_path: Path) -> Optional[ModuleType]:
        """Load a Python module from a file path.

        Args:
            file_path: Path to the Python file.

        Returns:
            Loaded module or None if failed.
        """
        module_name = f"uc_tool_{file_path.stem}_{hash(str(file_path))}"

        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return module
        except Exception:
            return None

    def _find_tool_function(
        self, module: ModuleType, tool_name: str
    ) -> Tuple[Optional[Callable], str]:
        """Find the callable function in a tool module.

        Looks for:
        1. A function with the same name as the tool
        2. A function named 'run'
        3. A function named 'execute'
        4. Any public function (not starting with _)

        Args:
            module: The loaded module.
            tool_name: The tool name from metadata.

        Returns:
            Tuple of (function, function_name) or (None, "") if not found.
        """
        # Priority order for finding the function
        candidates = [tool_name, "run", "execute"]

        for name in candidates:
            if hasattr(module, name):
                func = getattr(module, name)
                if callable(func) and not isinstance(func, type):
                    return func, name

        # Fall back to first public callable
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if callable(obj) and not isinstance(obj, type):
                return obj, name

        return None, ""

    def list_tools(self, include_disabled: bool = False) -> List[UCToolInfo]:
        """List all discovered tools.

        Args:
            include_disabled: Whether to include disabled tools.

        Returns:
            List of tool info objects.
        """
        if not self._tools:
            self.scan()

        tools = list(self._tools.values())
        if not include_disabled:
            tools = [t for t in tools if t.meta.enabled]

        return sorted(tools, key=lambda t: t.full_name)

    def get_tool(self, name: str) -> Optional[UCToolInfo]:
        """Get a specific tool by name.

        Args:
            name: Full tool name (including namespace).

        Returns:
            Tool info or None if not found.
        """
        if not self._tools:
            self.scan()

        return self._tools.get(name)

    def get_tool_function(self, name: str) -> Optional[Callable]:
        """Get the callable function for a tool.

        Args:
            name: Full tool name (including namespace).

        Returns:
            Callable function or None if not found.
        """
        tool = self.get_tool(name)
        if tool is None:
            return None

        module = self._modules.get(name)
        if module is None:
            return None

        func, _ = self._find_tool_function(module, tool.meta.name)
        return func

    def load_tool_module(self, name: str) -> Optional[ModuleType]:
        """Get the loaded module for a tool.

        Args:
            name: Full tool name (including namespace).

        Returns:
            Module or None if not found.
        """
        if not self._tools:
            self.scan()

        return self._modules.get(name)

    def reload(self) -> int:
        """Force a rescan of all tools.

        Returns:
            Number of tools found.
        """
        return self.scan()


# Global registry instance
_registry: Optional[UCRegistry] = None


def get_registry() -> UCRegistry:
    """Get the global UC registry instance.

    Returns:
        The global UCRegistry instance.
    """
    global _registry
    if _registry is None:
        _registry = UCRegistry()
    return _registry
