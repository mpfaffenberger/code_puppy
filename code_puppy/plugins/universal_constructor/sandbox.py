"""Code validation and safety checking for UC tools.

This module provides utilities for validating tool code before
execution or storage, including syntax checking, function extraction,
and dangerous pattern detection.
"""

import ast
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

# Imports that might indicate dangerous operations
DANGEROUS_IMPORTS: Set[str] = {
    "subprocess",
    "os.system",
    "shutil.rmtree",
    "eval",
    "exec",
    "compile",
    "__import__",
    "importlib",
    "ctypes",
    "multiprocessing",
    "pickle",
    "marshal",
}

# Dangerous function calls
DANGEROUS_CALLS: Set[str] = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",  # Could be dangerous depending on mode
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
}


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
