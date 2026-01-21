"""Code validation and safety checking for UC tools.

This module provides utilities for validating tool code before
execution or storage, including syntax checking, function extraction,
and dangerous pattern detection.
"""

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Required fields for TOOL_META
TOOL_META_REQUIRED_FIELDS = {"name", "description"}

# Imports that might indicate dangerous operations
DANGEROUS_IMPORTS: Set[str] = {
    # Execution/code generation
    "subprocess",
    "os.system",
    "shutil.rmtree",
    "eval",
    "exec",
    "compile",
    "__import__",
    "importlib",
    "multiprocessing",
    "pickle",
    "marshal",
    # Network access
    "socket",
    "urllib",
    "http.client",
    "requests",
    # System access
    "platform",
    "ctypes",
}

# Dangerous function calls
DANGEROUS_CALLS: Set[str] = {
    # Code execution
    "eval",
    "exec",
    "compile",
    "__import__",
    "import_module",
    # Process creation
    "system",
    "popen",
    "spawn",
    "fork",
    "execv",
    "execve",
    "execvp",
    "execl",
    "execle",
    "execlp",
    # Scope manipulation
    "globals",
    "locals",
}

# open() calls with write modes are dangerous
DANGEROUS_OPEN_MODES = {"w", "a", "x", "wb", "ab", "xb", "w+", "a+", "r+", "rb+", "wb+"}


@dataclass
class FunctionInfo:
    """Information extracted from a function definition."""

    name: str
    signature: str
    docstring: Optional[str] = None
    parameters: List[str] = field(default_factory=list)
    return_annotation: Optional[str] = None
    is_async: bool = False
    decorators: List[str] = field(default_factory=list)
    line_number: int = 0


@dataclass
class ValidationResult:
    """Result of code validation."""

    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    functions: List[FunctionInfo] = field(default_factory=list)


def validate_syntax(code: str) -> ValidationResult:
    """Validate Python syntax.

    Args:
        code: Python source code to validate.

    Returns:
        ValidationResult with valid=True if syntax is correct,
        or valid=False with error details.
    """
    result = ValidationResult(valid=True)

    try:
        ast.parse(code)
    except SyntaxError as e:
        result.valid = False
        line_info = f" (line {e.lineno})" if e.lineno else ""
        result.errors.append(f"Syntax error{line_info}: {e.msg}")

    return result


def extract_function_info(code: str) -> ValidationResult:
    """Extract function information from Python code.

    Parses the code and extracts information about all function
    definitions including name, signature, docstring, and parameters.

    Args:
        code: Python source code.

    Returns:
        ValidationResult containing list of FunctionInfo objects.
    """
    result = validate_syntax(code)
    if not result.valid:
        return result

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return result

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_info = _extract_single_function(node)
            result.functions.append(func_info)

    return result


def _extract_single_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> FunctionInfo:
    """Extract info from a single function AST node."""
    # Get parameter names
    params = []
    for arg in node.args.args:
        param_str = arg.arg
        if arg.annotation:
            param_str += f": {ast.unparse(arg.annotation)}"
        params.append(param_str)

    # Handle *args and **kwargs
    if node.args.vararg:
        vararg = f"*{node.args.vararg.arg}"
        if node.args.vararg.annotation:
            vararg += f": {ast.unparse(node.args.vararg.annotation)}"
        params.append(vararg)

    if node.args.kwarg:
        kwarg = f"**{node.args.kwarg.arg}"
        if node.args.kwarg.annotation:
            kwarg += f": {ast.unparse(node.args.kwarg.annotation)}"
        params.append(kwarg)

    # Build signature string
    signature = f"{node.name}({', '.join(params)})"

    # Get return annotation
    return_annotation = None
    if node.returns:
        return_annotation = ast.unparse(node.returns)
        signature += f" -> {return_annotation}"

    # Get docstring
    docstring = ast.get_docstring(node)

    # Get decorators
    decorators = []
    for dec in node.decorator_list:
        decorators.append(ast.unparse(dec))

    return FunctionInfo(
        name=node.name,
        signature=signature,
        docstring=docstring,
        parameters=params,
        return_annotation=return_annotation,
        is_async=isinstance(node, ast.AsyncFunctionDef),
        decorators=decorators,
        line_number=node.lineno,
    )


def check_dangerous_patterns(code: str) -> ValidationResult:
    """Check for potentially dangerous patterns in code.

    This is an advisory check - it warns about patterns that might
    be dangerous but doesn't prevent tool execution. Users should
    review warned code before trusting it.

    Args:
        code: Python source code to check.

    Returns:
        ValidationResult with warnings for dangerous patterns.
    """
    result = validate_syntax(code)
    if not result.valid:
        return result

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return result

    # Track dangerous imports
    dangerous_found: List[str] = []

    for node in ast.walk(tree):
        # Check imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in DANGEROUS_IMPORTS:
                    dangerous_found.append(f"import {alias.name}")

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                full_name = f"{module}.{alias.name}"
                if module in DANGEROUS_IMPORTS or full_name in DANGEROUS_IMPORTS:
                    dangerous_found.append(f"from {module} import {alias.name}")

        # Check function calls
        elif isinstance(node, ast.Call):
            func_name = _get_call_name(node)
            if func_name in DANGEROUS_CALLS:
                line = getattr(node, "lineno", "?")
                dangerous_found.append(f"{func_name}() call at line {line}")
            # Special handling for open() - check if write mode is used
            elif func_name == "open":
                if _is_dangerous_open_call(node):
                    line = getattr(node, "lineno", "?")
                    dangerous_found.append(f"open() with write mode at line {line}")

    # Add warnings for dangerous patterns
    if dangerous_found:
        result.warnings.append(
            f"Potentially dangerous patterns found: {', '.join(dangerous_found)}"
        )

    return result


def _get_call_name(node: ast.Call) -> str:
    """Extract the function name from a Call node."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    elif isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _is_dangerous_open_call(node: ast.Call) -> bool:
    """Check if an open() call uses a dangerous (write) mode.

    Args:
        node: AST Call node for open()

    Returns:
        True if the open call uses a write mode, False otherwise.
    """
    # Check positional args - mode is typically the second argument
    if len(node.args) >= 2:
        mode_arg = node.args[1]
        if isinstance(mode_arg, ast.Constant) and isinstance(mode_arg.value, str):
            return mode_arg.value in DANGEROUS_OPEN_MODES

    # Check keyword arguments
    for kw in node.keywords:
        if kw.arg == "mode":
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value in DANGEROUS_OPEN_MODES

    # If no mode specified, open() defaults to "r" which is safe
    return False


def full_validation(code: str) -> ValidationResult:
    """Perform full validation including syntax, function extraction, and safety.

    Args:
        code: Python source code to validate.

    Returns:
        Complete ValidationResult with all checks performed.
    """
    # Start with syntax validation
    result = validate_syntax(code)
    if not result.valid:
        return result

    # Extract function info
    func_result = extract_function_info(code)
    result.functions = func_result.functions

    # Check dangerous patterns
    safety_result = check_dangerous_patterns(code)
    result.warnings.extend(safety_result.warnings)

    # Additional validation: ensure there's at least one function
    if not result.functions:
        result.warnings.append("No functions found in code - tool may not be callable")

    return result


@dataclass
class ToolFileValidationResult(ValidationResult):
    """Extended validation result for tool files.

    Includes TOOL_META extraction and main function validation.
    """

    tool_meta: Optional[Dict[str, Any]] = None
    main_function: Optional[FunctionInfo] = None
    file_path: Optional[Path] = None


def _extract_tool_meta(code: str) -> Optional[Dict[str, Any]]:
    """Extract TOOL_META dictionary from code.

    Args:
        code: Python source code containing TOOL_META.

    Returns:
        The TOOL_META dict if found and valid, None otherwise.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TOOL_META":
                    # Try to evaluate the dict literal
                    if isinstance(node.value, ast.Dict):
                        try:
                            # Safely evaluate the dict using ast.literal_eval
                            meta_str = ast.unparse(node.value)
                            return ast.literal_eval(meta_str)
                        except (ValueError, SyntaxError):
                            return None
    return None


def _validate_tool_meta(meta: Dict[str, Any]) -> List[str]:
    """Validate that TOOL_META has required fields.

    Args:
        meta: The TOOL_META dictionary to validate.

    Returns:
        List of error messages (empty if valid).
    """
    errors = []
    for field_name in TOOL_META_REQUIRED_FIELDS:
        if field_name not in meta:
            errors.append(f"TOOL_META missing required field: '{field_name}'")
        elif not meta[field_name]:
            errors.append(f"TOOL_META field '{field_name}' cannot be empty")
    return errors


def _find_main_function(
    functions: List[FunctionInfo], tool_name: str
) -> Optional[FunctionInfo]:
    """Find the main function for a tool.

    The main function is expected to have the same name as the tool.

    Args:
        functions: List of functions found in the code.
        tool_name: Expected name of the main function.

    Returns:
        The main FunctionInfo if found, None otherwise.
    """
    for func in functions:
        if func.name == tool_name:
            return func
    return None


def validate_tool_file(file_path: Path) -> ToolFileValidationResult:
    """Validate a tool file including TOOL_META and main function.

    This function performs comprehensive validation:
    1. Reads the file content
    2. Validates Python syntax
    3. Extracts and validates TOOL_META dict
    4. Extracts and validates the main function
    5. Checks for dangerous patterns

    Args:
        file_path: Path to the tool file to validate.

    Returns:
        ToolFileValidationResult with all validation details.
    """
    result = ToolFileValidationResult(valid=True, file_path=file_path)

    # Check file exists
    if not file_path.exists():
        result.valid = False
        result.errors.append(f"File not found: {file_path}")
        return result

    if not file_path.is_file():
        result.valid = False
        result.errors.append(f"Path is not a file: {file_path}")
        return result

    # Read file content
    try:
        code = file_path.read_text(encoding="utf-8")
    except Exception as e:
        result.valid = False
        result.errors.append(f"Failed to read file: {e}")
        return result

    # Validate syntax
    syntax_result = validate_syntax(code)
    if not syntax_result.valid:
        result.valid = False
        result.errors.extend(syntax_result.errors)
        return result

    # Extract TOOL_META
    meta = _extract_tool_meta(code)
    if meta is None:
        result.valid = False
        result.errors.append("TOOL_META not found or invalid in file")
        return result

    result.tool_meta = meta

    # Validate TOOL_META has required fields
    meta_errors = _validate_tool_meta(meta)
    if meta_errors:
        result.valid = False
        result.errors.extend(meta_errors)
        return result

    # Extract functions
    func_result = extract_function_info(code)
    result.functions = func_result.functions

    # Find main function (should match tool name)
    tool_name = meta.get("name", "")
    main_func = _find_main_function(result.functions, tool_name)
    if main_func is None:
        result.warnings.append(
            f"No function named '{tool_name}' found - "
            f"tool may not be callable as expected"
        )
    else:
        result.main_function = main_func

    # Check dangerous patterns
    safety_result = check_dangerous_patterns(code)
    result.warnings.extend(safety_result.warnings)

    return result


def _validate_safe_path(file_path: Path, safe_root: Path) -> bool:
    """Validate that file_path is contained within safe_root.

    Args:
        file_path: The path to validate.
        safe_root: The root directory that file_path must be within.

    Returns:
        True if file_path is safely within safe_root, False otherwise.
    """
    try:
        # Resolve both paths to absolute paths
        resolved_path = file_path.resolve()
        resolved_root = safe_root.resolve()
        # Check if the resolved path is relative to the root
        resolved_path.relative_to(resolved_root)
        return True
    except ValueError:
        return False


def validate_and_write_tool(
    code: str, file_path: Path, safe_root: Optional[Path] = None
) -> ToolFileValidationResult:
    """Validate code and write to file only if valid.

    This function performs full validation before writing,
    ensuring only valid tool code is persisted to disk.

    Args:
        code: Python source code for the tool.
        file_path: Path where the tool file should be written.
        safe_root: Optional root directory to validate against. Defaults to USER_UC_DIR.
            Pass the parent directory of file_path to skip validation (for testing).

    Returns:
        ToolFileValidationResult indicating success/failure.
        If valid, the file will be written to file_path.
    """
    from . import USER_UC_DIR

    result = ToolFileValidationResult(valid=True, file_path=file_path)

    # Validate path is within safe root directory (prevent path traversal)
    root_to_check = safe_root if safe_root is not None else USER_UC_DIR
    if not _validate_safe_path(file_path, root_to_check):
        result.valid = False
        result.errors.append(f"Unsafe file path: must be within {root_to_check}")
        return result
    syntax_result = validate_syntax(code)
    if not syntax_result.valid:
        result.valid = False
        result.errors.extend(syntax_result.errors)
        return result

    # Extract and validate TOOL_META
    meta = _extract_tool_meta(code)
    if meta is None:
        result.valid = False
        result.errors.append("TOOL_META not found or invalid in code")
        return result

    result.tool_meta = meta

    # Validate TOOL_META has required fields
    meta_errors = _validate_tool_meta(meta)
    if meta_errors:
        result.valid = False
        result.errors.extend(meta_errors)
        return result

    # Extract functions
    func_result = extract_function_info(code)
    result.functions = func_result.functions

    # Find main function
    tool_name = meta.get("name", "")
    main_func = _find_main_function(result.functions, tool_name)
    if main_func is None:
        result.warnings.append(
            f"No function named '{tool_name}' found - "
            f"tool may not be callable as expected"
        )
    else:
        result.main_function = main_func

    # Check dangerous patterns (warnings only, don't fail)
    safety_result = check_dangerous_patterns(code)
    result.warnings.extend(safety_result.warnings)

    # If we got here, validation passed - write the file
    try:
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(code, encoding="utf-8")
    except Exception as e:
        result.valid = False
        result.errors.append(f"Failed to write file: {e}")
        return result

    return result
