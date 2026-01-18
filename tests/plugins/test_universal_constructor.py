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
    ValidationResult,
    check_dangerous_patterns,
    extract_function_info,
    full_validation,
    validate_syntax,
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

            tool_code = '''
TOOL_META = {
    "name": "weather",
    "description": "Weather API",
}

def weather(city: str) -> str:
    return f"Weather in {city}: Sunny!"
'''
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

            enabled_code = '''
TOOL_META = {"name": "enabled", "description": "Enabled", "enabled": True}
def enabled(): pass
'''
            disabled_code = '''
TOOL_META = {"name": "disabled", "description": "Disabled", "enabled": False}
def disabled(): pass
'''
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
            tool_code = '''
TOOL_META = {"name": "add", "description": "Add numbers"}
def add(a: int, b: int) -> int:
    return a + b
'''
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
            tool_code = '''
TOOL_META = {"name": "mod_test", "description": "Module test"}
CONSTANT = 42
def mod_test(): pass
'''
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
            tool_code = '''
TOOL_META = {"name": "new", "description": "New tool"}
def new(): pass
'''
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
        code = '''
@decorator
@another_decorator
def decorated(): pass
'''
        result = extract_function_info(code)
        func = result.functions[0]
        assert len(func.decorators) == 2
        assert "decorator" in func.decorators

    def test_extract_multiple_functions(self):
        """Test extracting multiple functions."""
        code = '''
def func1(): pass
def func2(): pass
def func3(): pass
'''
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
        code = '''
import json
import math

def safe_func(x):
    return math.sqrt(x)
'''
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
        code = '''
def dangerous(code):
    return eval(code)
'''
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
        code = '''
import subprocess
def run(cmd):
    return subprocess.run(cmd)
'''
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
