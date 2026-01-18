"""Tests for the Universal Constructor plugin.

Comprehensive tests covering:
- Pydantic models validation
- Registry scanning and tool discovery
- Sandbox code validation
- Dangerous pattern detection
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from code_puppy.plugins.universal_constructor import USER_UC_DIR
from code_puppy.plugins.universal_constructor.models import (
    ToolMeta,
    UCCallOutput,
    UCCreateOutput,
    UCInfoOutput,
    UCListOutput,
    UCToolInfo,
    UCUpdateOutput,
)
from code_puppy.plugins.universal_constructor.registry import UCRegistry, get_registry
from code_puppy.plugins.universal_constructor.sandbox import (
    DANGEROUS_OPEN_MODES,
    ToolFileValidationResult,
    ValidationResult,
    _extract_tool_meta,
    _find_main_function,
    _validate_tool_meta,
    check_dangerous_patterns,
    extract_function_info,
    full_validation,
    validate_and_write_tool,
    validate_syntax,
    validate_tool_file,
)

# =============================================================================
# Test __init__.py
# =============================================================================


class TestInit:
    """Test the __init__.py module."""

    def test_user_uc_dir_is_path(self):
        """Test that USER_UC_DIR is a Path object."""
        assert isinstance(USER_UC_DIR, Path)

    def test_user_uc_dir_under_code_puppy(self):
        """Test that USER_UC_DIR is under .code_puppy."""
        assert ".code_puppy" in str(USER_UC_DIR)
        assert "universal_constructor" in str(USER_UC_DIR)

    def test_user_uc_dir_in_home(self):
        """Test that USER_UC_DIR is in home directory."""
        home = Path.home()
        assert str(USER_UC_DIR).startswith(str(home))


# =============================================================================
# Test Pydantic Models
# =============================================================================


class TestToolMeta:
    """Test ToolMeta model."""

    def test_minimal_valid_meta(self):
        """Test creating ToolMeta with minimal required fields."""
        meta = ToolMeta(name="test", description="A test tool")
        assert meta.name == "test"
        assert meta.description == "A test tool"
        assert meta.enabled is True  # default
        assert meta.version == "1.0.0"  # default
        assert meta.namespace == ""  # default

    def test_full_meta(self):
        """Test creating ToolMeta with all fields."""
        now = datetime.now()
        meta = ToolMeta(
            name="full_tool",
            namespace="utils",
            description="A fully specified tool",
            enabled=False,
            version="2.3.1",
            author="Test Author",
            created_at=now,
        )
        assert meta.name == "full_tool"
        assert meta.namespace == "utils"
        assert meta.enabled is False
        assert meta.version == "2.3.1"
        assert meta.author == "Test Author"
        assert meta.created_at == now

    def test_meta_allows_extra_fields(self):
        """Test that ToolMeta allows extra fields."""
        meta = ToolMeta(
            name="test",
            description="Test",
            custom_field="custom_value",
            tags=["a", "b"],
        )
        assert meta.name == "test"
        # Extra fields should be accessible
        assert meta.model_extra.get("custom_field") == "custom_value"

    def test_meta_requires_name(self):
        """Test that name is required."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            ToolMeta(description="Missing name")

    def test_meta_requires_description(self):
        """Test that description is required."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            ToolMeta(name="test")


class TestUCToolInfo:
    """Test UCToolInfo model."""

    def test_create_tool_info(self):
        """Test creating UCToolInfo."""
        meta = ToolMeta(name="greet", description="Greeting tool")
        info = UCToolInfo(
            meta=meta,
            signature="greet(name: str) -> str",
            source_path=Path("/tmp/greet.py"),
        )
        assert info.meta.name == "greet"
        assert info.signature == "greet(name: str) -> str"
        assert info.source_path == Path("/tmp/greet.py")

    def test_full_name_without_namespace(self):
        """Test full_name property without namespace."""
        meta = ToolMeta(name="tool", description="Test")
        info = UCToolInfo(
            meta=meta, signature="tool()", source_path=Path("/tmp/tool.py")
        )
        assert info.full_name == "tool"

    def test_full_name_with_namespace(self):
        """Test full_name property with namespace."""
        meta = ToolMeta(name="weather", namespace="api", description="Weather API")
        info = UCToolInfo(
            meta=meta, signature="weather()", source_path=Path("/tmp/api/weather.py")
        )
        assert info.full_name == "api.weather"

    def test_tool_info_with_docstring(self):
        """Test UCToolInfo with docstring."""
        meta = ToolMeta(name="doc_tool", description="Tool with docs")
        info = UCToolInfo(
            meta=meta,
            signature="doc_tool(x: int)",
            source_path=Path("/tmp/doc.py"),
            function_name="doc_tool",
            docstring="This is the docstring.",
        )
        assert info.docstring == "This is the docstring."
        assert info.function_name == "doc_tool"


class TestResponseModels:
    """Test response models."""

    def test_uc_list_output(self):
        """Test UCListOutput model."""
        output = UCListOutput(total_count=10, enabled_count=7)
        assert output.total_count == 10
        assert output.enabled_count == 7
        assert output.tools == []
        assert output.error is None

    def test_uc_list_output_with_error(self):
        """Test UCListOutput with error."""
        output = UCListOutput(error="Failed to scan")
        assert output.error == "Failed to scan"

    def test_uc_call_output_success(self):
        """Test UCCallOutput for successful call."""
        output = UCCallOutput(
            success=True, tool_name="greet", result="Hello, World!", execution_time=0.05
        )
        assert output.success is True
        assert output.tool_name == "greet"
        assert output.result == "Hello, World!"
        assert output.execution_time == 0.05
        assert output.error is None

    def test_uc_call_output_failure(self):
        """Test UCCallOutput for failed call."""
        output = UCCallOutput(
            success=False, tool_name="broken", error="Tool raised exception"
        )
        assert output.success is False
        assert output.error == "Tool raised exception"

    def test_uc_create_output(self):
        """Test UCCreateOutput model."""
        output = UCCreateOutput(
            success=True,
            tool_name="new_tool",
            source_path=Path("/tmp/new_tool.py"),
            validation_warnings=["Uses subprocess"],
        )
        assert output.success is True
        assert output.tool_name == "new_tool"
        assert len(output.validation_warnings) == 1

    def test_uc_update_output(self):
        """Test UCUpdateOutput model."""
        output = UCUpdateOutput(
            success=True,
            tool_name="updated",
            changes_applied=["Updated description", "Changed version"],
        )
        assert output.success is True
        assert len(output.changes_applied) == 2

    def test_uc_info_output(self):
        """Test UCInfoOutput model."""
        meta = ToolMeta(name="info_test", description="Test")
        tool = UCToolInfo(
            meta=meta, signature="info_test()", source_path=Path("/tmp/test.py")
        )
        output = UCInfoOutput(
            success=True, tool=tool, source_code="def info_test(): pass"
        )
        assert output.success is True
        assert output.tool is not None
        assert output.source_code is not None


# =============================================================================
# Test Registry
# =============================================================================


class TestUCRegistry:
    """Test UCRegistry class."""

    def test_registry_init_with_custom_dir(self):
        """Test registry initialization with custom directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = UCRegistry(Path(tmpdir))
            assert registry._tools_dir == Path(tmpdir)

    def test_registry_ensure_tools_dir(self):
        """Test ensure_tools_dir creates directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir) / "new_dir"
            registry = UCRegistry(tools_dir)
            result = registry.ensure_tools_dir()
            assert result == tools_dir
            assert tools_dir.exists()

    def test_registry_scan_empty_dir(self):
        """Test scanning empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = UCRegistry(Path(tmpdir))
            count = registry.scan()
            assert count == 0

    def test_registry_scan_nonexistent_dir(self):
        """Test scanning nonexistent directory."""
        registry = UCRegistry(Path("/nonexistent/path/that/does/not/exist"))
        count = registry.scan()
        assert count == 0

    def test_registry_scan_valid_tool(self):
        """Test scanning directory with valid tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)
            tool_code = '''
TOOL_META = {
    "name": "greet",
    "description": "A greeting tool",
    "version": "1.0.0",
    "enabled": True,
}

def greet(name: str = "World") -> str:
    """Generate a greeting."""
    return f"Hello, {name}!"
'''
            (tools_dir / "greet.py").write_text(tool_code)

            registry = UCRegistry(tools_dir)
            count = registry.scan()
            assert count == 1

            tools = registry.list_tools()
            assert len(tools) == 1
            assert tools[0].meta.name == "greet"

    def test_registry_scan_namespaced_tool(self):
        """Test scanning with namespace from subdirectory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)
            api_dir = tools_dir / "api"
            api_dir.mkdir()

            tool_code = """
TOOL_META = {
    "name": "weather",
    "description": "Weather API",
}

def weather(city: str) -> str:
    return f"Weather in {city}: Sunny!"
"""
            (api_dir / "weather.py").write_text(tool_code)

            registry = UCRegistry(tools_dir)
            registry.scan()

            tool = registry.get_tool("api.weather")
            assert tool is not None
            assert tool.meta.namespace == "api"
            assert tool.full_name == "api.weather"

    def test_registry_scan_skips_init_files(self):
        """Test that __init__.py files are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)
            (tools_dir / "__init__.py").write_text("# init file")
            (tools_dir / "_private.py").write_text("# private file")

            registry = UCRegistry(tools_dir)
            count = registry.scan()
            assert count == 0

    def test_registry_scan_skips_invalid_meta(self):
        """Test that files without TOOL_META are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)
            (tools_dir / "no_meta.py").write_text("def foo(): pass")

            registry = UCRegistry(tools_dir)
            count = registry.scan()
            assert count == 0

    def test_registry_list_tools_excludes_disabled(self):
        """Test that disabled tools are excluded by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)

            enabled_code = """
TOOL_META = {"name": "enabled", "description": "Enabled", "enabled": True}
def enabled(): pass
"""
            disabled_code = """
TOOL_META = {"name": "disabled", "description": "Disabled", "enabled": False}
def disabled(): pass
"""
            (tools_dir / "enabled.py").write_text(enabled_code)
            (tools_dir / "disabled.py").write_text(disabled_code)

            registry = UCRegistry(tools_dir)
            registry.scan()

            # Default: exclude disabled
            tools = registry.list_tools()
            assert len(tools) == 1
            assert tools[0].meta.name == "enabled"

            # Include disabled
            all_tools = registry.list_tools(include_disabled=True)
            assert len(all_tools) == 2

    def test_registry_get_tool_function(self):
        """Test getting and calling a tool function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)
            tool_code = """
TOOL_META = {"name": "add", "description": "Add numbers"}
def add(a: int, b: int) -> int:
    return a + b
"""
            (tools_dir / "add.py").write_text(tool_code)

            registry = UCRegistry(tools_dir)
            registry.scan()

            func = registry.get_tool_function("add")
            assert func is not None
            assert func(2, 3) == 5

    def test_registry_load_tool_module(self):
        """Test loading tool module."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)
            tool_code = """
TOOL_META = {"name": "mod_test", "description": "Module test"}
CONSTANT = 42
def mod_test(): pass
"""
            (tools_dir / "mod_test.py").write_text(tool_code)

            registry = UCRegistry(tools_dir)
            registry.scan()

            module = registry.load_tool_module("mod_test")
            assert module is not None
            assert hasattr(module, "CONSTANT")
            assert module.CONSTANT == 42

    def test_registry_reload(self):
        """Test reloading the registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)

            registry = UCRegistry(tools_dir)
            assert registry.scan() == 0

            # Add a tool
            tool_code = """
TOOL_META = {"name": "new", "description": "New tool"}
def new(): pass
"""
            (tools_dir / "new.py").write_text(tool_code)

            # Reload should find it
            assert registry.reload() == 1


class TestGetRegistry:
    """Test get_registry singleton function."""

    def test_get_registry_returns_instance(self):
        """Test that get_registry returns a UCRegistry."""
        registry = get_registry()
        assert isinstance(registry, UCRegistry)

    def test_get_registry_same_instance(self):
        """Test that get_registry returns the same instance."""
        reg1 = get_registry()
        reg2 = get_registry()
        assert reg1 is reg2


# =============================================================================
# Test Sandbox
# =============================================================================


class TestValidateSyntax:
    """Test validate_syntax function."""

    def test_valid_syntax(self):
        """Test validation of valid Python code."""
        code = "def hello(): return 'world'"
        result = validate_syntax(code)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_invalid_syntax(self):
        """Test validation of invalid Python code."""
        code = "def broken(\n    return 'oops'"
        result = validate_syntax(code)
        assert result.valid is False
        assert len(result.errors) > 0

    def test_empty_code(self):
        """Test validation of empty code."""
        result = validate_syntax("")
        assert result.valid is True

    def test_syntax_error_has_line_info(self):
        """Test that syntax errors include line information."""
        code = "x = 1\ny = \nz = 3"
        result = validate_syntax(code)
        assert result.valid is False
        assert "line" in result.errors[0].lower()


class TestExtractFunctionInfo:
    """Test extract_function_info function."""

    def test_extract_simple_function(self):
        """Test extracting a simple function."""
        code = '''
def greet(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}!"
'''
        result = extract_function_info(code)
        assert result.valid is True
        assert len(result.functions) == 1

        func = result.functions[0]
        assert func.name == "greet"
        assert "name: str" in func.signature
        assert "-> str" in func.signature
        assert func.docstring == "Say hello."

    def test_extract_async_function(self):
        """Test extracting an async function."""
        code = '''
async def fetch(url: str) -> str:
    """Fetch a URL."""
    return "content"
'''
        result = extract_function_info(code)
        assert len(result.functions) == 1
        assert result.functions[0].is_async is True

    def test_extract_function_with_args_kwargs(self):
        """Test extracting function with *args and **kwargs."""
        code = "def varfunc(*args, **kwargs): pass"
        result = extract_function_info(code)
        func = result.functions[0]
        assert "*args" in func.signature
        assert "**kwargs" in func.signature

    def test_extract_decorated_function(self):
        """Test extracting decorated function."""
        code = """
@decorator
@another_decorator
def decorated(): pass
"""
        result = extract_function_info(code)
        func = result.functions[0]
        assert len(func.decorators) == 2
        assert "decorator" in func.decorators

    def test_extract_multiple_functions(self):
        """Test extracting multiple functions."""
        code = """
def func1(): pass
def func2(): pass
def func3(): pass
"""
        result = extract_function_info(code)
        assert len(result.functions) == 3

    def test_extract_from_invalid_code(self):
        """Test extraction from invalid code returns errors."""
        code = "def broken("
        result = extract_function_info(code)
        assert result.valid is False


class TestCheckDangerousPatterns:
    """Test check_dangerous_patterns function."""

    def test_safe_code_no_warnings(self):
        """Test that safe code produces no warnings."""
        code = """
import json
import math

def safe_func(x):
    return math.sqrt(x)
"""
        result = check_dangerous_patterns(code)
        assert result.valid is True
        assert len(result.warnings) == 0

    def test_detects_subprocess_import(self):
        """Test detection of subprocess import."""
        code = "import subprocess"
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0
        assert "subprocess" in result.warnings[0].lower()

    def test_detects_eval_call(self):
        """Test detection of eval() call."""
        code = """
def dangerous(code):
    return eval(code)
"""
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0
        assert "eval" in result.warnings[0].lower()

    def test_detects_exec_call(self):
        """Test detection of exec() call."""
        code = "exec('print(1)')"
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0
        assert "exec" in result.warnings[0].lower()

    def test_detects_os_system_import(self):
        """Test detection of os.system import."""
        code = "from os import system"
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0

    def test_invalid_code_returns_syntax_error(self):
        """Test that invalid code returns syntax error."""
        code = "def broken("
        result = check_dangerous_patterns(code)
        assert result.valid is False


class TestFullValidation:
    """Test full_validation function."""

    def test_full_validation_valid_code(self):
        """Test full validation of valid safe code."""
        code = '''
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b
'''
        result = full_validation(code)
        assert result.valid is True
        assert len(result.functions) == 1
        assert len(result.errors) == 0

    def test_full_validation_warns_no_functions(self):
        """Test that code without functions gets a warning."""
        code = "x = 1\ny = 2"
        result = full_validation(code)
        assert result.valid is True
        assert any("No functions" in w for w in result.warnings)

    def test_full_validation_includes_danger_warnings(self):
        """Test that dangerous patterns are included in warnings."""
        code = """
import subprocess
def run(cmd):
    return subprocess.run(cmd)
"""
        result = full_validation(code)
        assert result.valid is True
        assert len(result.warnings) > 0
        assert any("subprocess" in w.lower() for w in result.warnings)


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_default_values(self):
        """Test default values for ValidationResult."""
        result = ValidationResult(valid=True)
        assert result.errors == []
        assert result.warnings == []
        assert result.functions == []

    def test_with_values(self):
        """Test ValidationResult with values."""
        result = ValidationResult(
            valid=False, errors=["Error 1", "Error 2"], warnings=["Warning 1"]
        )
        assert result.valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1


# =============================================================================
# Test Callback Registration
# =============================================================================


class TestCallbackRegistration:
    """Test that callbacks are properly registered."""

    def test_startup_callback_registered(self):
        """Test that startup callback is registered."""
        from code_puppy.callbacks import get_callbacks
        from code_puppy.plugins.universal_constructor.register_callbacks import (
            _on_startup,
        )

        callbacks = get_callbacks("startup")
        # _on_startup should be registered
        assert any(
            cb is _on_startup or getattr(cb, "__wrapped__", None) is _on_startup
            for cb in callbacks
        )


# =============================================================================
# Test Enhanced Dangerous Pattern Detection
# =============================================================================


class TestEnhancedDangerousPatterns:
    """Test enhanced dangerous pattern detection."""

    def test_detects_socket_import(self):
        """Test detection of socket import (network)."""
        code = "import socket"
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0
        assert "socket" in result.warnings[0].lower()

    def test_detects_urllib_import(self):
        """Test detection of urllib import (network)."""
        code = "import urllib"
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0
        assert "urllib" in result.warnings[0].lower()

    def test_detects_requests_import(self):
        """Test detection of requests import (external API)."""
        code = "import requests"
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0
        assert "requests" in result.warnings[0].lower()

    def test_detects_platform_import(self):
        """Test detection of platform import (system access)."""
        code = "import platform"
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0
        assert "platform" in result.warnings[0].lower()

    def test_detects_ctypes_import(self):
        """Test detection of ctypes import (system access)."""
        code = "import ctypes"
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0
        assert "ctypes" in result.warnings[0].lower()

    def test_detects_globals_call(self):
        """Test detection of globals() call."""
        code = """
def dangerous():
    return globals()
"""
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0
        assert "globals" in result.warnings[0].lower()

    def test_detects_locals_call(self):
        """Test detection of locals() call."""
        code = """
def dangerous():
    return locals()
"""
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0
        assert "locals" in result.warnings[0].lower()

    def test_detects_import_module_call(self):
        """Test detection of import_module() call."""
        code = """
from importlib import import_module
mod = import_module("os")
"""
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0
        # Should detect both the importlib import and the import_module call
        warning = result.warnings[0].lower()
        assert "importlib" in warning or "import_module" in warning


class TestOpenWriteModeDetection:
    """Test open() with write mode detection."""

    def test_open_read_mode_safe(self):
        """Test that open() with read mode is safe."""
        code = 'f = open("file.txt", "r")'
        result = check_dangerous_patterns(code)
        assert len(result.warnings) == 0

    def test_open_default_mode_safe(self):
        """Test that open() without mode (default 'r') is safe."""
        code = 'f = open("file.txt")'
        result = check_dangerous_patterns(code)
        assert len(result.warnings) == 0

    def test_open_write_mode_dangerous(self):
        """Test that open() with write mode is detected."""
        code = 'f = open("file.txt", "w")'
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0
        assert "open()" in result.warnings[0].lower()
        assert "write" in result.warnings[0].lower()

    def test_open_append_mode_dangerous(self):
        """Test that open() with append mode is detected."""
        code = 'f = open("file.txt", "a")'
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0

    def test_open_write_binary_dangerous(self):
        """Test that open() with binary write mode is detected."""
        code = 'f = open("file.bin", "wb")'
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0

    def test_open_write_mode_keyword(self):
        """Test that open() with mode keyword argument is detected."""
        code = 'f = open("file.txt", mode="w")'
        result = check_dangerous_patterns(code)
        assert len(result.warnings) > 0

    def test_dangerous_open_modes_constant(self):
        """Test that DANGEROUS_OPEN_MODES contains expected modes."""
        assert "w" in DANGEROUS_OPEN_MODES
        assert "a" in DANGEROUS_OPEN_MODES
        assert "x" in DANGEROUS_OPEN_MODES
        assert "wb" in DANGEROUS_OPEN_MODES
        assert "w+" in DANGEROUS_OPEN_MODES


# =============================================================================
# Test Tool File Validation
# =============================================================================


class TestExtractToolMeta:
    """Test _extract_tool_meta function."""

    def test_extract_valid_meta(self):
        """Test extracting valid TOOL_META."""
        code = """
TOOL_META = {
    "name": "greet",
    "description": "A greeting tool",
    "version": "1.0.0",
}

def greet(name: str) -> str:
    return f"Hello, {name}!"
"""
        meta = _extract_tool_meta(code)
        assert meta is not None
        assert meta["name"] == "greet"
        assert meta["description"] == "A greeting tool"
        assert meta["version"] == "1.0.0"

    def test_extract_no_meta(self):
        """Test that missing TOOL_META returns None."""
        code = "def foo(): pass"
        meta = _extract_tool_meta(code)
        assert meta is None

    def test_extract_invalid_syntax(self):
        """Test that invalid syntax returns None."""
        code = "TOOL_META = {"
        meta = _extract_tool_meta(code)
        assert meta is None

    def test_extract_non_dict_meta(self):
        """Test that non-dict TOOL_META returns None."""
        code = 'TOOL_META = "not a dict"'
        meta = _extract_tool_meta(code)
        assert meta is None


class TestValidateToolMeta:
    """Test _validate_tool_meta function."""

    def test_valid_meta(self):
        """Test validation of complete meta."""
        meta = {"name": "test", "description": "Test tool"}
        errors = _validate_tool_meta(meta)
        assert len(errors) == 0

    def test_missing_name(self):
        """Test that missing name produces error."""
        meta = {"description": "Test tool"}
        errors = _validate_tool_meta(meta)
        assert len(errors) > 0
        assert any("name" in e for e in errors)

    def test_missing_description(self):
        """Test that missing description produces error."""
        meta = {"name": "test"}
        errors = _validate_tool_meta(meta)
        assert len(errors) > 0
        assert any("description" in e for e in errors)

    def test_empty_name(self):
        """Test that empty name produces error."""
        meta = {"name": "", "description": "Test"}
        errors = _validate_tool_meta(meta)
        assert len(errors) > 0
        assert any("name" in e and "empty" in e for e in errors)


class TestFindMainFunction:
    """Test _find_main_function function."""

    def test_finds_matching_function(self):
        """Test finding function that matches tool name."""
        code = """
def greet(name: str) -> str:
    return f"Hello, {name}!"

def helper(): pass
"""
        result = extract_function_info(code)
        main_func = _find_main_function(result.functions, "greet")
        assert main_func is not None
        assert main_func.name == "greet"

    def test_not_found_returns_none(self):
        """Test that missing function returns None."""
        code = "def other(): pass"
        result = extract_function_info(code)
        main_func = _find_main_function(result.functions, "greet")
        assert main_func is None


class TestValidateToolFile:
    """Test validate_tool_file function."""

    def test_validate_valid_tool_file(self):
        """Test validation of valid tool file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = Path(tmpdir) / "greet.py"
            code = '''
TOOL_META = {
    "name": "greet",
    "description": "A greeting tool",
}

def greet(name: str = "World") -> str:
    """Generate a greeting."""
    return f"Hello, {name}!"
'''
            tool_path.write_text(code)

            result = validate_tool_file(tool_path)
            assert result.valid is True
            assert result.tool_meta is not None
            assert result.tool_meta["name"] == "greet"
            assert result.main_function is not None
            assert result.main_function.name == "greet"
            assert result.file_path == tool_path

    def test_validate_nonexistent_file(self):
        """Test validation of nonexistent file."""
        result = validate_tool_file(Path("/nonexistent/path.py"))
        assert result.valid is False
        assert any("not found" in e.lower() for e in result.errors)

    def test_validate_directory_fails(self):
        """Test that validating a directory fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_tool_file(Path(tmpdir))
            assert result.valid is False
            assert any("not a file" in e.lower() for e in result.errors)

    def test_validate_file_with_syntax_error(self):
        """Test validation of file with syntax error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = Path(tmpdir) / "broken.py"
            tool_path.write_text("def broken(")

            result = validate_tool_file(tool_path)
            assert result.valid is False
            assert any("syntax" in e.lower() for e in result.errors)

    def test_validate_file_missing_tool_meta(self):
        """Test validation of file without TOOL_META."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = Path(tmpdir) / "no_meta.py"
            tool_path.write_text("def foo(): pass")

            result = validate_tool_file(tool_path)
            assert result.valid is False
            assert any("tool_meta" in e.lower() for e in result.errors)

    def test_validate_file_incomplete_meta(self):
        """Test validation of file with incomplete TOOL_META."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = Path(tmpdir) / "incomplete.py"
            code = """
TOOL_META = {"name": "test"}
def test(): pass
"""
            tool_path.write_text(code)

            result = validate_tool_file(tool_path)
            assert result.valid is False
            assert any("description" in e for e in result.errors)

    def test_validate_file_warns_missing_main_function(self):
        """Test that missing main function generates warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = Path(tmpdir) / "mismatch.py"
            code = """
TOOL_META = {"name": "greet", "description": "Greeting"}
def other_func(): pass
"""
            tool_path.write_text(code)

            result = validate_tool_file(tool_path)
            assert result.valid is True  # Still valid, just a warning
            assert any("greet" in w and "found" in w.lower() for w in result.warnings)

    def test_validate_file_with_dangerous_patterns(self):
        """Test that dangerous patterns generate warnings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = Path(tmpdir) / "dangerous.py"
            code = """
import subprocess
TOOL_META = {"name": "runner", "description": "Runs commands"}
def runner(cmd): return subprocess.run(cmd)
"""
            tool_path.write_text(code)

            result = validate_tool_file(tool_path)
            assert result.valid is True  # Dangerous patterns are warnings, not errors
            assert len(result.warnings) > 0


class TestValidateAndWriteTool:
    """Test validate_and_write_tool function."""

    def test_write_valid_tool(self):
        """Test writing valid tool code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = Path(tmpdir) / "new_tool.py"
            code = """
TOOL_META = {
    "name": "new_tool",
    "description": "A new tool",
}

def new_tool() -> str:
    return "Hello!"
"""
            result = validate_and_write_tool(code, tool_path)
            assert result.valid is True
            assert tool_path.exists()
            assert tool_path.read_text() == code
            assert result.tool_meta["name"] == "new_tool"

    def test_write_creates_parent_directories(self):
        """Test that parent directories are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = Path(tmpdir) / "subdir" / "nested" / "tool.py"
            code = """
TOOL_META = {"name": "tool", "description": "Test"}
def tool(): pass
"""
            result = validate_and_write_tool(code, tool_path)
            assert result.valid is True
            assert tool_path.exists()

    def test_write_invalid_syntax_no_file(self):
        """Test that invalid syntax doesn't create file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = Path(tmpdir) / "broken.py"
            code = "def broken("

            result = validate_and_write_tool(code, tool_path)
            assert result.valid is False
            assert not tool_path.exists()

    def test_write_missing_meta_no_file(self):
        """Test that missing TOOL_META doesn't create file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = Path(tmpdir) / "no_meta.py"
            code = "def foo(): pass"

            result = validate_and_write_tool(code, tool_path)
            assert result.valid is False
            assert not tool_path.exists()

    def test_write_incomplete_meta_no_file(self):
        """Test that incomplete TOOL_META doesn't create file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = Path(tmpdir) / "incomplete.py"
            code = """
TOOL_META = {"name": "incomplete"}
def incomplete(): pass
"""
            result = validate_and_write_tool(code, tool_path)
            assert result.valid is False
            assert not tool_path.exists()

    def test_write_with_warnings_still_writes(self):
        """Test that code with warnings is still written."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = Path(tmpdir) / "warned.py"
            code = """
import subprocess
TOOL_META = {"name": "warned", "description": "Warned tool"}
def warned(): pass
"""
            result = validate_and_write_tool(code, tool_path)
            assert result.valid is True
            assert len(result.warnings) > 0  # Has warnings
            assert tool_path.exists()  # But still written


class TestToolFileValidationResult:
    """Test ToolFileValidationResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = ToolFileValidationResult(valid=True)
        assert result.valid is True
        assert result.tool_meta is None
        assert result.main_function is None
        assert result.file_path is None
        assert result.errors == []
        assert result.warnings == []
        assert result.functions == []

    def test_inherits_from_validation_result(self):
        """Test that it inherits from ValidationResult."""
        result = ToolFileValidationResult(valid=True)
        assert isinstance(result, ValidationResult)


# =============================================================================
# Test Universal Constructor Tool Handlers
# =============================================================================


class TestHandleInfoAction:
    """Test _handle_info_action function."""

    def test_info_requires_tool_name(self):
        """Test that info action requires tool_name."""
        from unittest.mock import Mock

        from code_puppy.tools.universal_constructor import _handle_info_action

        context = Mock()
        result = _handle_info_action(context, None)
        assert result.success is False
        assert result.action == "info"
        assert "tool_name is required" in result.error

    def test_info_tool_not_found(self):
        """Test info action with nonexistent tool."""
        from unittest.mock import Mock, patch

        from code_puppy.tools.universal_constructor import _handle_info_action

        context = Mock()
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry"
        ) as mock_get_registry:
            mock_registry = Mock()
            mock_registry.get_tool.return_value = None
            mock_get_registry.return_value = mock_registry

            result = _handle_info_action(context, "nonexistent")
            assert result.success is False
            assert "not found" in result.error

    def test_info_success(self):
        """Test successful info action."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)
            tool_code = '''
TOOL_META = {
    "name": "greet",
    "description": "A greeting tool",
}

def greet(name: str = "World") -> str:
    """Generate a greeting."""
    return f"Hello, {name}!"
'''
            tool_file = tools_dir / "greet.py"
            tool_file.write_text(tool_code)

            from unittest.mock import Mock, patch

            from code_puppy.plugins.universal_constructor.models import (
                ToolMeta,
                UCToolInfo,
            )
            from code_puppy.tools.universal_constructor import _handle_info_action

            meta = ToolMeta(name="greet", description="A greeting tool")
            tool_info = UCToolInfo(
                meta=meta,
                signature="greet(name: str = 'World') -> str",
                source_path=tool_file,
                function_name="greet",
                docstring="Generate a greeting.",
            )

            context = Mock()
            with patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry"
            ) as mock_get_registry:
                mock_registry = Mock()
                mock_registry.get_tool.return_value = tool_info
                mock_get_registry.return_value = mock_registry

                result = _handle_info_action(context, "greet")
                assert result.success is True
                assert result.action == "info"
                assert result.info_result is not None
                assert result.info_result.success is True
                assert result.info_result.tool.meta.name == "greet"
                assert "TOOL_META" in result.info_result.source_code
                assert "def greet" in result.info_result.source_code

    def test_info_source_file_not_found(self):
        """Test info when source file doesn't exist."""
        from unittest.mock import Mock, patch

        from code_puppy.plugins.universal_constructor.models import ToolMeta, UCToolInfo
        from code_puppy.tools.universal_constructor import _handle_info_action

        meta = ToolMeta(name="missing", description="Missing source")
        tool_info = UCToolInfo(
            meta=meta,
            signature="missing()",
            source_path=Path("/nonexistent/path/missing.py"),
        )

        context = Mock()
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry"
        ) as mock_get_registry:
            mock_registry = Mock()
            mock_registry.get_tool.return_value = tool_info
            mock_get_registry.return_value = mock_registry

            result = _handle_info_action(context, "missing")
            assert result.success is True
            assert result.info_result.source_code == "[Source file not found]"


class TestHandleUpdateAction:
    """Test _handle_update_action function."""

    def test_update_requires_tool_name(self):
        """Test that update action requires tool_name."""
        from unittest.mock import Mock

        from code_puppy.tools.universal_constructor import _handle_update_action

        context = Mock()
        result = _handle_update_action(context, None, None, None)
        assert result.success is False
        assert result.action == "update"
        assert "tool_name is required" in result.error

    def test_update_requires_python_code(self):
        """Test that update requires python_code."""
        from unittest.mock import Mock

        from code_puppy.tools.universal_constructor import _handle_update_action

        context = Mock()
        result = _handle_update_action(context, "some_tool", None, None)
        assert result.success is False
        assert "python_code is required" in result.error

    def test_update_tool_not_found(self):
        """Test update action with nonexistent tool."""
        from unittest.mock import Mock, patch

        from code_puppy.tools.universal_constructor import _handle_update_action

        context = Mock()
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry"
        ) as mock_get_registry:
            mock_registry = Mock()
            mock_registry.get_tool.return_value = None
            mock_get_registry.return_value = mock_registry

            result = _handle_update_action(
                context, "nonexistent", "def foo(): pass", None
            )
            assert result.success is False
            assert "not found" in result.error

    def test_update_invalid_syntax(self):
        """Test update with invalid syntax code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)
            tool_file = tools_dir / "test_tool.py"
            original_code = """
TOOL_META = {"name": "test_tool", "description": "Test"}
def test_tool(): pass
"""
            tool_file.write_text(original_code)

            from unittest.mock import Mock, patch

            from code_puppy.plugins.universal_constructor.models import (
                ToolMeta,
                UCToolInfo,
            )
            from code_puppy.tools.universal_constructor import _handle_update_action

            meta = ToolMeta(name="test_tool", description="Test")
            tool_info = UCToolInfo(
                meta=meta,
                signature="test_tool()",
                source_path=tool_file,
            )

            context = Mock()
            with patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry"
            ) as mock_get_registry:
                mock_registry = Mock()
                mock_registry.get_tool.return_value = tool_info
                mock_get_registry.return_value = mock_registry

                # Try to update with invalid syntax
                result = _handle_update_action(
                    context, "test_tool", "def broken(", None
                )
                assert result.success is False
                assert "Syntax error" in result.error

    def test_update_missing_tool_meta(self):
        """Test update with code missing TOOL_META."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)
            tool_file = tools_dir / "test_tool.py"
            original_code = """
TOOL_META = {"name": "test_tool", "description": "Test"}
def test_tool(): pass
"""
            tool_file.write_text(original_code)

            from unittest.mock import Mock, patch

            from code_puppy.plugins.universal_constructor.models import (
                ToolMeta,
                UCToolInfo,
            )
            from code_puppy.tools.universal_constructor import _handle_update_action

            meta = ToolMeta(name="test_tool", description="Test")
            tool_info = UCToolInfo(
                meta=meta,
                signature="test_tool()",
                source_path=tool_file,
            )

            context = Mock()
            with patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry"
            ) as mock_get_registry:
                mock_registry = Mock()
                mock_registry.get_tool.return_value = tool_info
                mock_get_registry.return_value = mock_registry

                # Try to update with code that has no TOOL_META
                result = _handle_update_action(
                    context, "test_tool", "def foo(): pass", None
                )
                assert result.success is False
                assert "TOOL_META" in result.error

    def test_update_code_success(self):
        """Test successful code update."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)
            tool_file = tools_dir / "updatable.py"
            original_code = """
TOOL_META = {"name": "updatable", "description": "Original"}
def updatable(): return "original"
"""
            tool_file.write_text(original_code)

            from unittest.mock import Mock, patch

            from code_puppy.plugins.universal_constructor.models import (
                ToolMeta,
                UCToolInfo,
            )
            from code_puppy.tools.universal_constructor import _handle_update_action

            meta = ToolMeta(name="updatable", description="Original")
            tool_info = UCToolInfo(
                meta=meta,
                signature="updatable()",
                source_path=tool_file,
            )

            context = Mock()
            with patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry"
            ) as mock_get_registry:
                mock_registry = Mock()
                mock_registry.get_tool.return_value = tool_info
                mock_get_registry.return_value = mock_registry

                new_code = """
TOOL_META = {"name": "updatable", "description": "Updated"}
def updatable(): return "updated"
"""
                result = _handle_update_action(context, "updatable", new_code, None)
                assert result.success is True
                assert result.update_result is not None
                assert result.update_result.success is True
                assert result.update_result.tool_name == "updatable"
                assert "Replaced source code" in result.update_result.changes_applied

                # Verify file was updated
                updated_content = tool_file.read_text()
                assert 'return "updated"' in updated_content
                mock_registry.reload.assert_called_once()

    def test_update_description_only_fails(self):
        """Test that description-only update fails (requires python_code)."""
        from unittest.mock import Mock

        from code_puppy.tools.universal_constructor import _handle_update_action

        context = Mock()
        # Try to update with only description, no python_code
        result = _handle_update_action(context, "some_tool", None, "New description")
        assert result.success is False
        assert "python_code is required" in result.error

    def test_update_no_source_path(self):
        """Test update when tool has no source path."""
        from unittest.mock import Mock, patch

        from code_puppy.plugins.universal_constructor.models import ToolMeta, UCToolInfo
        from code_puppy.tools.universal_constructor import _handle_update_action

        meta = ToolMeta(name="no_path", description="No path")
        tool_info = UCToolInfo(
            meta=meta,
            signature="no_path()",
            source_path=Path("/nonexistent/path.py"),
        )

        context = Mock()
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry"
        ) as mock_get_registry:
            mock_registry = Mock()
            mock_registry.get_tool.return_value = tool_info
            mock_get_registry.return_value = mock_registry

            result = _handle_update_action(
                context, "no_path", "TOOL_META = {}\ndef foo(): pass", None
            )
            assert result.success is False
            assert "does not exist" in result.error.lower()
