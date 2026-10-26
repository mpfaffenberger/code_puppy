"""Pin the startup error handlers and keep their ``errors.log`` contexts honest.

``data/error_pipeline_sites.tsv`` lists handlers by ``(file, qualname, ordinal)`` -- never by line
number -- so edits elsewhere in a large file such as ``cli_runner.py`` do not disturb the pins.
Routes:

* ``ERROR``    startup site that calls ``log_error(<exc>, context=<context>)``.
* ``EXPECTED`` startup site that calls ``logger.debug(<context>, exc_info=True)``.
* ``DEFERRED`` runtime handler that is still silent; a later change owns it. The row goes stale
  (and this test fails) the moment the handler records something, so the list can only shrink.
* ``INTERNAL`` the sink's own handler; recording its failure would recurse, so it stays silent.

Any silent handler in the scanned files that is not listed fails the build, so a new silent
``except`` cannot slip in, and a startup site turned back into ``pass`` fails its pin. Ordinals
shift only when a handler is added or removed earlier in the same function; the failure names the
identity to re-pin. Contexts follow ``<module>::<qualname>: <phrase>``: the qualname must be the
real enclosing function and the phrase unique per file (rule 15c).

AST helpers live in ``tests/error_ast_support.py``.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

import pytest

from tests.error_ast_support import (
    CONTROL_FLOW,
    find_handler,
    is_silent,
    scopes,
    silent_sites,
    type_names,
)

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).parent / "data" / "error_pipeline_sites.tsv"
PIPELINE_FILES = (
    "code_puppy/callbacks.py",
    "code_puppy/cli_runner.py",
    "code_puppy/error_format.py",
    "code_puppy/error_hooks.py",
    "code_puppy/error_logging.py",
    "code_puppy/main.py",
    "code_puppy/plugins/__init__.py",
    "code_puppy/pydantic_patches.py",
)
ROUTES = {"ERROR", "EXPECTED", "DEFERRED", "INTERNAL"}
SILENT_ROUTES = {"DEFERRED", "INTERNAL"}
# A helper that records on behalf of the function named in the context prefix: the failing ``try``
# body lives in that caller, which hands the exceptions over once the last patch has run.
RECORDS_ON_BEHALF_OF = {
    ("code_puppy/pydantic_patches.py", "_report_patch_failures"): "apply_all_patches",
}
CONTEXT = re.compile(
    r"(?P<module>code_puppy[\w.]*)::(?P<qualname>[\w.]+): (?P<phrase>.+)", re.S
)


def _load_rows() -> list[dict[str, str]]:
    lines = DATA.read_text(encoding="utf-8").splitlines()
    head = lines[0].split("\t")
    return [
        dict(zip(head, line.split("\t"), strict=True))
        for line in lines[1:]
        if line.strip()
    ]


ROWS = _load_rows()
IDS = [f"{r['file']}::{r['enclosing_qualname']}#{r['ordinal']}" for r in ROWS]


def _scope() -> list[str]:
    new_modules = (
        p.relative_to(ROOT).as_posix() for p in ROOT.glob("code_puppy/error_*.py")
    )
    return sorted({*PIPELINE_FILES, *new_modules})


def _parse(rel: str) -> ast.Module:
    return ast.parse((ROOT / rel).read_text(encoding="utf-8"))


def _literal(node: ast.expr) -> str | None:
    """Static text of a string or f-string, with each interpolation shown as ``{expr}``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value
            if isinstance(part, ast.Constant)
            else "{" + ast.unparse(part.value) + "}"
            for part in node.values
        )
    return None


def _recorded_context(handler: ast.ExceptHandler, route: str) -> str | None:
    """Context of the handler's first statement when it records as *route* says, else ``None``."""
    first = handler.body[0]
    call = first.value if isinstance(first, ast.Expr) else None
    if not isinstance(call, ast.Call):
        return None
    keywords = {k.arg: k.value for k in call.keywords}
    if route == "ERROR":
        if not (isinstance(call.func, ast.Name) and call.func.id == "log_error"):
            return None
        first_arg = call.args[0] if call.args else None
        if not (isinstance(first_arg, ast.Name) and first_arg.id == handler.name):
            return None
        return _literal(keywords["context"]) if list(keywords) == ["context"] else None
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == "debug"):
        return None
    exc_info = keywords.get("exc_info")
    if list(keywords) != ["exc_info"] or not (
        isinstance(exc_info, ast.Constant) and exc_info.value is True
    ):
        return None
    return _literal(call.args[0]) if call.args else None


def test_site_list_is_unique_and_in_scope() -> None:
    assert ROWS
    assert len(set(IDS)) == len(IDS)
    assert {r["route"] for r in ROWS} <= ROUTES
    assert {r["file"] for r in ROWS} <= set(_scope())


@pytest.mark.parametrize("row", ROWS, ids=IDS)
def test_pinned_handler_matches_its_route(row: dict[str, str]) -> None:
    handler, _ = find_handler(
        _parse(row["file"]), row["enclosing_qualname"], int(row["ordinal"])
    )
    route = row["route"]
    if route in SILENT_ROUTES:
        assert is_silent(handler), (
            "no longer silent: drop this row or give it a recording route"
        )
        assert route != "INTERNAL" or row["file"].startswith("code_puppy/error_")
        return
    assert _recorded_context(handler, route) == row["context"]
    if set(type_names(handler.type)) & CONTROL_FLOW:
        assert route == "EXPECTED", "control flow must never reach errors.log"


def test_every_silent_handler_is_pinned_or_deferred() -> None:
    pinned = {(r["file"], r["enclosing_qualname"], int(r["ordinal"])) for r in ROWS}
    offenders = [
        f"{rel}\t{qualname}\t{ordinal}\tDEFERRED\t(line {handler.lineno})"
        for rel in _scope()
        for qualname, ordinal, handler, _ in silent_sites(_parse(rel))
        if (rel, qualname, ordinal) not in pinned
    ]
    assert offenders == [], (
        "silent handler with no pin; record it or defer it explicitly"
    )


class _ContextLiterals(ast.NodeVisitor):
    """Collect ``<module>::<qualname>: <phrase>`` literals with their enclosing scope."""

    def __init__(self) -> None:
        self.stack: list[str] = []
        self.found: list[tuple[re.Match[str], str, int]] = []

    def _enter(
        self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_ClassDef = visit_FunctionDef = visit_AsyncFunctionDef = _enter

    def _see(self, node: ast.Constant | ast.JoinedStr) -> None:
        text = _literal(node)
        match = CONTEXT.fullmatch(text) if text else None
        if match:
            self.found.append((match, ".".join(self.stack), node.lineno))

    visit_Constant = _see

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        self._see(node)  # whole f-string; its pieces are not separate contexts


@pytest.mark.parametrize("rel", _scope())
def test_contexts_name_the_real_function_and_are_unique(rel: str) -> None:
    tree = _parse(rel)
    known = {qualname for qualname, _ in scopes(tree)}
    module = rel.removesuffix(".py").removesuffix("/__init__").replace("/", ".")
    visitor = _ContextLiterals()
    visitor.visit(tree)
    problems: list[str] = []
    for match, enclosing, lineno in visitor.found:
        qualname = match["qualname"]
        # Module-level constants (shared by dispatchers) can only name an existing function.
        allowed = (
            {enclosing, RECORDS_ON_BEHALF_OF.get((rel, enclosing))}
            if enclosing
            else known
        )
        if match["module"] != module or qualname not in allowed:
            problems.append(
                f"{rel}:{lineno} prefix {match['module']}::{qualname} != {module}::{enclosing}"
            )
    phrases = Counter(match["phrase"] for match, _, _ in visitor.found)
    problems += [
        f"{rel}: duplicate phrase {phrase!r}" for phrase, n in phrases.items() if n > 1
    ]
    assert problems == []
