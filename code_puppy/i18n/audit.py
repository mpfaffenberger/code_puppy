"""Static i18n extraction audit for CLI/TUI user-facing strings.

The extraction workstreams (PUP-480 public CLI, PUP-481 private CLI) have to
migrate ~2,000 ``emit_*`` / ``console.print`` call sites from raw literals to
``t()`` catalog keys. Grinding that blind is how strings get missed and PRs
become un-reviewable, so this module turns "how much is left?" into a number.

What it does
------------
Walk the source tree, parse each module with :mod:`ast`, and classify every
user-facing emit call site by its *first positional argument*:

* **extracted** - the text is already a translation call
  (``t()`` / ``i18n.t()`` / ``ngettext()`` / ``lazy()`` / ``gettext()``).
* **raw** - the text is a hard-coded literal (``str`` constant, f-string, or
  string concatenation). These are the sites still needing extraction.
* **dynamic** - the argument is a bare variable / other expression, so the
  string was produced elsewhere. Neither credited nor blamed; reported
  separately so a reviewer can eyeball them.

Coverage = ``extracted / (extracted + raw)``. Dynamic sites are excluded from
the denominator because there is no literal here to extract.

Usage
-----
::

    python -m code_puppy.i18n.audit                 # human summary
    python -m code_puppy.i18n.audit --list          # + every raw site
    python -m code_puppy.i18n.audit --top 15        # worst 15 files
    python -m code_puppy.i18n.audit --json          # machine-readable
    python -m code_puppy.i18n.audit --fail-under 25 # CI gate (exit 1 if under)

Intentionally stdlib-only so it can run as a lightweight CI gate without
importing the app.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

# Emit helpers all share the ``emit_`` prefix (emit_info/warning/error/...).
# console.print is the other big user-facing sink.
_EMIT_PREFIX = "emit_"
_CONSOLE_PRINT = ("console", "print")

# Calls that mean "this text is already externalized".
_TRANSLATION_FUNCS = frozenset({"t", "gettext", "ngettext", "lazy"})

# Directories we never audit (not user-facing CLI output, or generated).
_SKIP_DIRS = frozenset({"__pycache__", "tests", "test", ".git", "i18n"})


@dataclass
class Site:
    """A single user-facing emit call site."""

    path: str
    line: int
    call: str  # e.g. "emit_info" or "console.print"
    kind: str  # "extracted" | "raw" | "dynamic"
    preview: str = ""


@dataclass
class Report:
    """Aggregated audit results."""

    sites: List[Site] = field(default_factory=list)

    @property
    def extracted(self) -> List[Site]:
        return [s for s in self.sites if s.kind == "extracted"]

    @property
    def raw(self) -> List[Site]:
        return [s for s in self.sites if s.kind == "raw"]

    @property
    def dynamic(self) -> List[Site]:
        return [s for s in self.sites if s.kind == "dynamic"]

    @property
    def coverage(self) -> float:
        translatable = len(self.extracted) + len(self.raw)
        if translatable == 0:
            return 100.0
        return 100.0 * len(self.extracted) / translatable


def _callee_name(func: ast.expr) -> Optional[str]:
    """Return a normalized callee name for an emit-like call, else None.

    ``emit_info(...)``          -> "emit_info"
    ``mod.emit_warning(...)``   -> "emit_warning"
    ``console.print(...)``      -> "console.print"
    """
    if isinstance(func, ast.Name):
        if func.id.startswith(_EMIT_PREFIX):
            return func.id
        return None
    if isinstance(func, ast.Attribute):
        if func.attr.startswith(_EMIT_PREFIX):
            return func.attr
        # console.print — match the value's trailing name to be robust to
        # aliasing (self.console.print, cp.console.print, ...).
        if (
            func.attr == _CONSOLE_PRINT[1]
            and isinstance(func.value, (ast.Name, ast.Attribute))
            and _trailing_name(func.value) == _CONSOLE_PRINT[0]
        ):
            return "console.print"
    return None


def _trailing_name(node: ast.expr) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_translation_call(node: ast.expr) -> bool:
    """True if node is a t()/ngettext()/lazy()/i18n.t() style call."""
    if not isinstance(node, ast.Call):
        return False
    name = _trailing_name(node.func)
    return name in _TRANSLATION_FUNCS


def _has_string_literal(node: ast.expr) -> bool:
    """True if the expression *contains* a hard-coded string literal.

    For f-strings we only return True when at least one constant segment
    contains non-whitespace text.  Pure-variable f-strings like ``f"{x}"``
    or ``f"  {x}"`` carry no translatable literal and are classified as
    dynamic instead.
    """
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.JoinedStr):  # f-string
        # An f-string is only "raw" when it has at least one constant part
        # with meaningful (non-whitespace) text, e.g. f"Error: {e}".
        # Pure-variable forms like f"{var}" or f"  {var}" are dynamic.
        #
        # Also recurse into ``FormattedValue.value`` so a wrapped literal
        # like ``f"{'Error: connection refused'}"`` (which parses as
        # ``JoinedStr([FormattedValue(Constant('...'))])``) is still
        # classified as raw instead of being dropped as dynamic.
        return any(
            (
                isinstance(v, ast.Constant)
                and isinstance(v.value, str)
                and v.value.strip()
            )
            or (
                isinstance(v, ast.FormattedValue)
                and isinstance(v.value, ast.Constant)
                and isinstance(v.value.value, str)
                and v.value.value.strip()
            )
            for v in node.values
        )
    if isinstance(node, ast.BinOp):  # "a" + x, "a" % x
        return _has_string_literal(node.left) or _has_string_literal(node.right)
    if isinstance(node, ast.Call):
        # "sep".join(...) / "text".format(...) — the literal is the receiver.
        return _trailing_name(node.func) in {"join", "format"} and _has_string_literal(
            node.func.value if isinstance(node.func, ast.Attribute) else node
        )
    return False


def _classify(first_arg: Optional[ast.expr]) -> str:
    if first_arg is None:
        return "dynamic"
    if _is_translation_call(first_arg):
        return "extracted"
    if _has_string_literal(first_arg):
        return "raw"
    return "dynamic"


def _preview(node: ast.expr, source: str) -> str:
    try:
        text = ast.get_source_segment(source, node) or ""
    except Exception:  # pragma: no cover - defensive
        text = ""
    text = " ".join(text.split())
    return text[:80] + ("…" if len(text) > 80 else "")


def audit_source(source: str, path: str) -> List[Site]:
    """Classify every user-facing emit call site in one module's source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover - skip unparseable files
        return []
    sites: List[Site] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call = _callee_name(node.func)
        if call is None:
            continue
        first_arg = node.args[0] if node.args else None
        kind = _classify(first_arg)
        sites.append(
            Site(
                path=path,
                line=node.lineno,
                call=call,
                kind=kind,
                preview=_preview(first_arg, source) if first_arg else "",
            )
        )
    return sites


def _iter_py_files(root: str) -> Iterable[str]:
    """Yield every .py file under ``root``.

    If ``root`` is itself a ``.py`` file it is yielded directly so that
    ``python -m code_puppy.i18n.audit path/to/module.py`` works as
    expected instead of silently producing an empty report.
    """
    if os.path.isfile(root):
        if root.endswith(".py"):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def audit_tree(root: str) -> Report:
    """Audit every Python module under ``root``, or ``root`` itself when it is a ``.py`` file."""
    if not os.path.isdir(root) and not os.path.isfile(root):
        # Silent-zero is worse than useless — an empty Report has
        # coverage == 100.0, so a typo'd path would sail past
        # ``--fail-under`` and tell CI everything is fine. Fail loud:
        # this is a config/programming error, not a data condition.
        raise FileNotFoundError(f"audit root does not exist: {root!r}")
    report = Report()
    for path in sorted(_iter_py_files(root)):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                source = fh.read()
        except OSError:  # pragma: no cover - defensive
            continue
        report.sites.extend(audit_source(source, path))
    return report


# --- CLI ------------------------------------------------------------------
def _default_root() -> str:
    # Audit the whole code_puppy package by default.
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _print_human(report: Report, root: str, list_raw: bool, top: int) -> None:
    rel = lambda p: os.path.relpath(p, os.path.dirname(root))  # noqa: E731
    print("i18n extraction audit")
    print("=" * 40)
    print(f"  extracted (t/ngettext/lazy) : {len(report.extracted)}")
    print(f"  raw literals  (TODO)        : {len(report.raw)}")
    print(f"  dynamic (no literal)        : {len(report.dynamic)}")
    print(f"  coverage                    : {report.coverage:.1f}%")

    if top:
        by_file: dict[str, int] = {}
        for s in report.raw:
            by_file[s.path] = by_file.get(s.path, 0) + 1
        worst = sorted(by_file.items(), key=lambda kv: kv[1], reverse=True)[:top]
        if worst:
            print(f"\nTop {len(worst)} files by raw strings:")
            for path, count in worst:
                print(f"  {count:5}  {rel(path)}")

    if list_raw:
        print("\nRaw (un-extracted) sites:")
        for s in report.raw:
            print(f"  {rel(s.path)}:{s.line}  {s.call}  {s.preview}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", nargs="?", default=_default_root())
    parser.add_argument("--list", action="store_true", help="list every raw site")
    parser.add_argument("--top", type=int, default=10, help="worst-N files (0=off)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        metavar="PCT",
        help="exit 1 if coverage is below PCT (CI gate)",
    )
    args = parser.parse_args(argv)

    report = audit_tree(args.root)

    if args.json:
        print(
            json.dumps(
                {
                    "extracted": len(report.extracted),
                    "raw": len(report.raw),
                    "dynamic": len(report.dynamic),
                    "coverage": round(report.coverage, 2),
                    "raw_sites": [
                        {"path": s.path, "line": s.line, "call": s.call}
                        for s in report.raw
                    ],
                },
                indent=2,
            )
        )
    else:
        _print_human(report, args.root, args.list, args.top)

    if args.fail_under is not None and report.coverage < args.fail_under:
        print(
            f"\nFAIL: coverage {report.coverage:.1f}% < required {args.fail_under:.1f}%",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
