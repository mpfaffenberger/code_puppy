"""Standalone (stdlib-only) AST helpers for locating and classifying silent ``except`` handlers.

Locate and classify silent handlers. A handler is *silent* when it catches a broad type set, neither re-raises,
reports, emits, logs, nor uses its exception, and its body is either trivial (pass/continue/break/
bare constants) or ends in a default return/assignment.

Identity of a handler: ``(qualname, ordinal)`` where ``qualname`` is the dotted chain of enclosing
class/def names (``<module>`` at module level) and ``ordinal`` is the 1-based pre-order index among
the handlers directly inside that scope (nested defs/classes/lambdas excluded, handlers nested in
handlers included). Class bodies themselves have no handlers of their own in this scheme.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator
from pathlib import Path

CANCEL = {
    "CancelledError",
    "KeyboardInterrupt",
    "SystemExit",
    "GeneratorExit",
    "EOFError",
    "BrokenPipeError",
}
CONTROL_FLOW = {
    "CancelledError",
    "KeyboardInterrupt",
    "SystemExit",
    "GeneratorExit",
    "BaseException",
    "<bare>",
}
IMPORT = {"ImportError", "ModuleNotFoundError"}
NARROW = {
    "KeyError", "IndexError", "AttributeError", "LookupError", "StopIteration", "StopAsyncIteration",
    "Empty", "QueueEmpty", "TimeoutError", "FileNotFoundError", "NotADirectoryError", "IsADirectoryError",
    "FileExistsError", "ProcessLookupError", "ChildProcessError", "JSONDecodeError", "UnicodeDecodeError",
    "UnicodeEncodeError", "ValueError", "TypeError", "PermissionError", "OSError", "IOError",
    "UnsupportedOperation", "InvalidVersion", "InvalidStateError", "RuntimeError", "NotImplementedError",
    "ZeroDivisionError", "OverflowError", "binascii.Error", "Error", "ClosedResourceError",
    "BrokenResourceError", "EndOfStream", "WouldBlock", "TclError", "SSLError", "ConnectionError",
    "ConnectionResetError", "ConnectionRefusedError", "UnicodeError", "CalledProcessError",
    "TimeoutExpired", "ParseError", "ExpatError", "YAMLError", "TOMLDecodeError",
}  # fmt: skip
LOG_ERROR = {
    "log_error",
    "log_error_message",
    "_log_error",
    "report_error",
    "_note_failure",
    "_report_failure",
}
USER_EMIT = {
    "emit_error",
    "emit_warning",
    "emit_info",
    "emit_system_message",
    "print_exception",
    "print",
}
LOG_METHODS = {
    "debug",
    "info",
    "warning",
    "warn",
    "error",
    "exception",
    "critical",
    "log",
}


def scopes(tree: ast.Module) -> Iterator[tuple[str, ast.AST]]:
    """Yield ``(qualname, scope)`` for the module and every class/def."""
    yield "<module>", tree
    stack: list[tuple[tuple[str, ...], ast.AST]] = [((), tree)]
    while stack:
        prefix, node = stack.pop(0)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                names = (*prefix, child.name)
                yield ".".join(names), child
                stack.append((names, child))
            else:
                stack.append((prefix, child))


def direct_handlers(scope: ast.AST) -> list[ast.ExceptHandler]:
    """Handlers directly in ``scope`` (module/def bodies only), excluding nested defs and lambdas."""
    found: list[ast.ExceptHandler] = []

    class Visitor(ast.NodeVisitor):
        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
            found.append(node)
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.AST) -> None:
            return None

        visit_AsyncFunctionDef = visit_ClassDef = visit_Lambda = visit_FunctionDef

    if isinstance(scope, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)):
        visitor = Visitor()
        for statement in scope.body:
            visitor.visit(statement)
    return found


def type_names(node: ast.expr | None) -> list[str]:
    if node is None:
        return ["<bare>"]
    elements = node.elts if isinstance(node, ast.Tuple) else [node]
    out: list[str] = []
    for element in elements:
        if isinstance(element, ast.Name):
            out.append(element.id)
        elif isinstance(element, ast.Attribute):
            out.append(element.attr)
        else:
            out.append(ast.unparse(element))
    return out


def _calls_in(body: list[ast.stmt]) -> Iterator[tuple[str, str | None]]:
    for stmt in body:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                yield func.id, None
            elif isinstance(func, ast.Attribute):
                owner = func.value
                owner_name = (
                    owner.id
                    if isinstance(owner, ast.Name)
                    else owner.attr
                    if isinstance(owner, ast.Attribute)
                    else ""
                )
                yield func.attr, owner_name


def _is_trivial(body: list[ast.stmt]) -> bool:
    return all(
        isinstance(s, (ast.Pass, ast.Continue, ast.Break))
        or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
        for s in body
    )


def _returns_default(body: list[ast.stmt]) -> bool:
    last = body[-1]
    simple = (
        ast.Constant,
        ast.List,
        ast.Dict,
        ast.Tuple,
        ast.Set,
        ast.Name,
        ast.Attribute,
    )
    if isinstance(last, ast.Return):
        return last.value is None or isinstance(last.value, simple)
    if isinstance(last, (ast.Assign, ast.AnnAssign)) and len(body) <= 2:
        return isinstance(
            last.value, (ast.Constant, ast.List, ast.Dict, ast.Tuple, ast.Name)
        )
    return False


def _uses_name(body: list[ast.stmt], name: str | None) -> bool:
    return bool(name) and any(
        isinstance(n, ast.Name) and n.id == name for s in body for n in ast.walk(s)
    )


def is_silent(handler: ast.ExceptHandler) -> bool:
    """True for the 'broad silent pass/continue' and 'broad silent default' categories."""
    types = set(type_names(handler.type))
    body = handler.body
    calls = list(_calls_in(body))
    names = {callee for callee, _ in calls}
    if types <= CANCEL:
        return False
    if any(isinstance(n, ast.Raise) for s in body for n in ast.walk(s)):
        return False
    if names & LOG_ERROR or names & USER_EMIT:
        return False
    if any(c in LOG_METHODS and owner and "log" in owner.lower() for c, owner in calls):
        return False
    if types & IMPORT and types <= IMPORT | NARROW:
        return False
    if types <= NARROW:
        return False
    if _uses_name(body, handler.name):
        return False
    return _is_trivial(body) or _returns_default(body)


def silent_sites(tree: ast.Module) -> list[tuple[str, int, ast.ExceptHandler, ast.AST]]:
    """All silent handlers as ``(qualname, ordinal, handler, scope)`` in scope order."""
    out = []
    for qualname, scope in scopes(tree):
        for ordinal, handler in enumerate(direct_handlers(scope), 1):
            if is_silent(handler):
                out.append((qualname, ordinal, handler, scope))
    return out


def find_handler(
    tree: ast.Module, qualname: str, ordinal: int
) -> tuple[ast.ExceptHandler, ast.AST]:
    for name, scope in scopes(tree):
        if name == qualname:
            handlers = direct_handlers(scope)
            if 1 <= ordinal <= len(handlers):
                return handlers[ordinal - 1], scope
    raise LookupError(f"no handler {qualname}#{ordinal}")


def _imported_names(nodes: Iterable[ast.AST]) -> set[str]:
    found: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add("." * node.level + (node.module or ""))
    return found


def module_imports(path: str | Path) -> set[str]:
    """Dotted module names imported anywhere in the file at *path*."""
    return _imported_names(ast.walk(ast.parse(Path(path).read_text(encoding="utf-8"))))


def module_scope_imports(path: str | Path) -> set[str]:
    """Dotted module names imported at module scope of the file at *path*."""
    return _imported_names(ast.parse(Path(path).read_text(encoding="utf-8")).body)
