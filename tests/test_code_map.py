"""
pytest suite that checks our Tree-sitter–powered code-map works across
**every** language declared in `tree_langs.LANGS`, including JSX/TSX.

Run:

    pytest -q test_tree_map.py

Each test creates a temporary file, feeds it into `map_code_file`,
renders the Rich tree into a string, and asserts that the expected
labels (function/class/…) appear.  Tests are skipped automatically if
the relevant parser is missing locally.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Dict, List

import pytest
from rich.console import Console

# ── System-under-test --------------------------------------------------
from code_puppy.tools.ts_code_map import (
    LANGS,
    map_code_file,
)  # builds Rich tree from a file path

# ----------------------------------------------------------------------
# 1.  Minimal sample snippets for each **primary** extension. Aliases
#     (e.g. .jsx -> .js) are filled in later – but ONLY if a unique
#     example hasn’t been provided here first.
# ----------------------------------------------------------------------
SAMPLES: Dict[str, str] = {
    # ——— scripting / dynamic ———
    ".py": "def foo():\n    pass\n\nclass Bar:\n    pass\n",
    ".rb": "class Bar\n  def foo; end\nend\n",
    ".php": "<?php function foo() {} class Bar {} ?>\n",
    ".lua": "function foo() end\n",
    ".pl": "sub foo { return 1; }\n",
    ".r": "foo <- function(x) { x }\n",
    ".js": "function foo() {}\nclass Bar {}\n",
    ".jsx": (
        "function Foo() {\n"
        "  return <div>Hello</div>;\n"  # simple JSX return
        "}\n\n"
        "class Bar extends React.Component {\n"
        "  render() { return <span>Hi</span>; }\n"
        "}\n"
    ),
    ".ts": "function foo(): void {}\nclass Bar {}\n",
    ".tsx": (
        "interface Props { greeting: string }\n"
        "function Foo(props: Props): JSX.Element {\n"
        "  return <div>{props.greeting}</div>;\n"  # TSX generic usage
        "}\n\n"
        "class Bar extends React.Component<Props> {\n"
        "  render() { return <span>Hi</span>; }\n"
        "}\n"
    ),
    # ——— systems / compiled ———
    ".c": "int foo() { return 0; }\nstruct Bar { int x; };\n",
    ".cpp": "struct Bar {};\nint foo(){return 0;}\n",
    ".cs": "class Bar { void Foo() {} }\n",
    ".java": "class Bar { void foo() {} }\n",
    ".kt": "class Bar { fun foo() {} }\n",
    ".swift": "class Bar { func foo() {} }\n",
    ".go": "type Bar struct {}\nfunc Foo() {}\n",
    ".rs": "struct Bar;\nfn foo() {}\n",
    ".zig": "const Bar = struct {};\nfn foo() void {}\n",
    ".scala": "class Bar { def foo() = 0 }\n",
    ".hs": "foo x = x\n\ndata Bar = Bar\n",
    ".jl": "struct Bar end\nfunction foo() end\n",
    # ——— shell / infra ———
    ".sh": "foo() { echo hi; }\n",
    ".ps1": "function Foo { param() }\n",
    # ——— markup / style ———
    ".html": "<div>Hello</div>\n",
    ".css": ".foo { color: red; } #bar { color: blue; }\n",
}

# ----------------------------------------------------------------------
# 2.  Expected substrings in rendered Rich trees
# ----------------------------------------------------------------------
EXPECTS: Dict[str, List[str]] = {
    ".py": ["def foo()", "class Bar"],
    ".rb": ["def foo", "class Bar"],
    ".php": ["function foo()", "class Bar"],
    ".lua": ["function foo()"],
    ".pl": ["sub foo()"],
    ".r": ["func foo()"],
    ".js": ["function foo()", "class Bar"],
    ".jsx": ["function Foo()", "class Bar"],
    ".ts": ["function foo()", "class Bar"],
    ".tsx": ["function Foo()", "class Bar"],
    ".c": ["fn foo()", "struct Bar"],
    ".cpp": ["fn foo()", "struct Bar"],
    ".cs": ["method Foo()", "class Bar"],
    ".java": ["method foo()", "class Bar"],
    ".kt": ["fun foo()", "class Bar"],
    ".swift": ["func foo()", "class Bar"],
    ".go": ["func Foo()", "type Bar"],
    ".rs": ["fn foo()", "struct Bar"],
    ".zig": ["fn foo()", "struct Bar"],
    ".scala": ["def foo()", "class Bar"],
    ".hs": ["fun foo", "type Bar"],
    ".jl": ["function foo()", "struct Bar"],
    ".sh": ["fn foo()"],
    ".ps1": ["function Foo()"],
    ".html": ["<div>"],
    ".css": [".foo", "#bar"],
}

# ----------------------------------------------------------------------
# 3.  Fill in alias samples/expectations **only if** not already present
# ----------------------------------------------------------------------
for ext, alias in list(LANGS.items()):
    if isinstance(alias, str):
        # Skip if we already provided a bespoke snippet for that ext
        if ext in SAMPLES:
            continue
        if alias in SAMPLES:
            SAMPLES[ext] = SAMPLES[alias]
            EXPECTS[ext] = EXPECTS[alias]


# ----------------------------------------------------------------------
# 4.  Test for path traversal bug fix
# ----------------------------------------------------------------------
def test_make_code_map_handles_path_traversal_gracefully(tmp_path: Path, monkeypatch):
    """Test that make_code_map handles paths outside the base directory gracefully.

    This test verifies the fix for the "not in subpath" error that occurs when
    os.walk encounters paths that can't be computed relative to the base directory.
    """
    from code_puppy.tools.ts_code_map import make_code_map
    from pathlib import Path
    import os

    # Create a test directory structure
    test_dir = tmp_path / "test_project"
    test_dir.mkdir()

    # Create a simple Python file to ensure basic functionality works
    py_file = test_dir / "example.py"
    py_file.write_text("def hello(): pass\n")

    # Mock os.walk to simulate a problematic path that would cause the relative_to error
    original_walk = os.walk

    def mock_walk(directory):
        # First yield the normal directory
        for item in original_walk(directory):
            yield item
        # Then yield a problematic path that would cause relative_to to fail
        # This simulates a symlink or path that escapes the base directory
        problematic_path = "/some/outside/path"
        yield (problematic_path, [], ["badfile.py"])

    monkeypatch.setattr(os, "walk", mock_walk)

    # This should not raise a ValueError about "not in subpath"
    # Before the fix, this would crash with the relative_to error
    result = make_code_map(str(test_dir))

    # Verify we get a reasonable result (the function doesn't crash)
    assert isinstance(result, str)
    assert len(result) > 0
    # The result should contain the project name
    assert "test_project" in result


# ----------------------------------------------------------------------
# 5.  Parametrised test
# ----------------------------------------------------------------------
@pytest.mark.parametrize("ext,snippet", sorted(SAMPLES.items()))
def test_code_map_extracts_nodes(ext: str, snippet: str, tmp_path: Path):
    """Verify `map_code_file` surfaces expected labels for each language."""

    # Skip if parser not available ------------------------------------------------
    lang_cfg = LANGS[ext] if not isinstance(LANGS[ext], str) else LANGS[LANGS[ext]]
    lang_name: str = lang_cfg["lang"]
    try:
        importlib.import_module(f"tree_sitter_languages.{lang_name}")
    except ModuleNotFoundError:
        pytest.skip(f"Parser for '{lang_name}' not available in this environment")

    # Write temp file -------------------------------------------------------------
    sample_file = tmp_path / f"sample{ext}"
    sample_file.write_text(snippet, encoding="utf-8")

    # Build Rich tree -------------------------------------------------------------
    rich_tree = map_code_file(str(sample_file))

    # Render Rich tree to plain text ---------------------------------------------
    buf = Console(record=True, width=120, quiet=True)
    buf.print(rich_tree)
    rendered = buf.export_text()

    # Assertions ------------------------------------------------------------------
    for expected in EXPECTS[ext]:
        assert expected in rendered, (
            f"{ext}: '{expected}' not found in output for sample file\n{rendered}"
        )
