"""Regression coverage for the cli_runner facade's pydantic-patch guarantee.

``code_puppy.cli_runner`` calls ``apply_all_patches()`` before any
pydantic-ai import (see its module docstring). Several tests import the
runner-split leaf modules (``interactive_runner``, ``interactive_support``)
directly for cleaner mock targets; each now imports ``code_puppy.cli_runner``
first precisely so that guarantee still holds for them (see
``tests/test_double_ctrl_c_exit.py``, ``tests/test_cli_runner_persistent_prompt.py``,
``tests/test_cancel_escape_hatch.py``, ``tests/messaging/test_history_persistence.py``).

Each probe below is a genuinely fresh, socket-denied subprocess: import
caching and patch application are both process-global, so an in-process
check would report "already true" regardless of what is being exercised.
The child denies socket connections before importing anything (including
``code_puppy``) and self-tests that denial, then tracks two ordered events
-- the ``apply_all_patches`` *invocation* (not merely its import) and the
first ``pydantic_ai`` import -- by wrapping ``builtins.__import__``.
Checking only ``'code_puppy.pydantic_patches' in sys.modules`` is insufficient:
membership does not show whether patches were invoked or whether that
invocation preceded the first ``pydantic_ai`` import.
"""

import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Installed before anything else imports, including code_puppy itself.
_PROBE_BOOTSTRAP = """
import builtins
import json
import socket
import ssl

_original_ssl_socket = ssl.SSLSocket


def _deny(*_args, **_kwargs):
    raise PermissionError("import-ordering probe: sockets denied")


socket.socket.connect = _deny
socket.socket.connect_ex = _deny
socket.create_connection = _deny
assert ssl.SSLSocket is _original_ssl_socket

for _denied in (socket.socket.connect, socket.socket.connect_ex, socket.create_connection):
    try:
        _denied(None, ("127.0.0.1", 1))
    except PermissionError:
        pass
    else:
        raise AssertionError("socket guard did not install before import tracking")

_events = []
_original_import = builtins.__import__


def _track(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "code_puppy.pydantic_patches":
        module = _original_import(name, globals, locals, fromlist, level)
        _original_apply = module.apply_all_patches

        def _apply(*a, **k):
            _events.append("patches")
            return _original_apply(*a, **k)

        module.apply_all_patches = _apply
        return module
    if name.startswith("pydantic_ai"):
        _events.append("pydantic_ai")
    return _original_import(name, globals, locals, fromlist, level)


builtins.__import__ = _track
"""

# Printed last, after the probed import statements have run.
_PROBE_REPORT = """
builtins.__import__ = _original_import
_result = {
    "events": _events,
    "patches_called": "patches" in _events,
    "patches_before_pydantic_ai": (
        "patches" in _events
        and "pydantic_ai" in _events
        and _events.index("patches") < _events.index("pydantic_ai")
    ),
}
print("PROBE_RESULT:" + json.dumps(_result), flush=True)
"""


def _run_cold_probe(import_lines: str) -> dict:
    """Execute ``import_lines`` in a fresh, offline, patch-ordering-tracking
    subprocess and return its parsed result. Uses only ``sys.executable``
    (the interpreter already running this test, with ``code_puppy`` already
    installed) -- no package index, network, or sitecustomize dependency.
    """
    script = _PROBE_BOOTSTRAP + "\n" + import_lines + "\n" + _PROBE_REPORT
    with tempfile.TemporaryDirectory() as scratch:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": scratch,
            "XDG_CONFIG_HOME": scratch,
            "XDG_DATA_HOME": scratch,
            "XDG_CACHE_HOME": scratch,
            "XDG_STATE_HOME": scratch,
            "PUPPY_SECRET_PATH": scratch,
            "CODE_PUPPY_NO_TUI": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        if sys.platform == "win32":
            for key in ("SYSTEMROOT", "TEMP", "TMP", "PATHEXT", "COMSPEC"):
                if key in os.environ:
                    env[key] = os.environ[key]
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=30,
        )
    for line in result.stdout.splitlines():
        if line.startswith("PROBE_RESULT:"):
            return json.loads(line[len("PROBE_RESULT:") :])
    raise AssertionError(
        "no PROBE_RESULT sentinel in child output: "
        f"stdout={result.stdout!r} stderr={result.stderr!r} "
        f"returncode={result.returncode}"
    )


def test_facade_import_calls_patches_before_pydantic_ai():
    """Baseline: importing the facade alone invokes apply_all_patches()
    before any pydantic_ai import -- not merely leaves the patch module
    importable in sys.modules.
    """
    probe = _run_cold_probe("import code_puppy.cli_runner")
    assert probe["patches_called"], probe
    assert probe["patches_before_pydantic_ai"], probe


@pytest.mark.parametrize("leaf", ["interactive_runner", "interactive_support"])
def test_facade_first_then_leaf_keeps_patches_applied(leaf):
    """Importing the facade before a leaf module invokes patches before
    any pydantic_ai import.
    """
    probe = _run_cold_probe(f"import code_puppy.cli_runner\nimport code_puppy.{leaf}")
    assert probe["patches_called"], probe
    assert probe["patches_before_pydantic_ai"], probe


def _extract_leading_import_lines(path: Path) -> str:
    """Return a file's module-level import block (after any module
    docstring, up to the first non-import statement) as executable source,
    reconstructed from the live AST rather than a hand-copied snapshot.
    Reading the real file means a future edit that removes or reorders the
    facade bootstrap import changes what this test actually executes.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return _unparse_import_nodes(_leading_import_nodes(tree.body))


def _leading_import_nodes(body: list) -> list:
    nodes = []
    for node in body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            nodes.append(node)
        elif isinstance(node, ast.Expr) and isinstance(
            getattr(node, "value", None), ast.Constant
        ):
            continue  # module docstring
        else:
            break
    return nodes


def _unparse_import_nodes(nodes: list) -> str:
    return "\n".join(ast.unparse(node) for node in nodes)


# All four callers bootstrap at module scope, so extracting their leading
# import blocks checks the real import sequence.
_AFFECTED_CALLERS = [
    "tests/test_double_ctrl_c_exit.py",
    "tests/test_cli_runner_persistent_prompt.py",
    "tests/test_cancel_escape_hatch.py",
    "tests/messaging/test_history_persistence.py",
]


@pytest.mark.parametrize("relative_path", _AFFECTED_CALLERS)
def test_affected_caller_bootstrap_precedes_pydantic_ai(relative_path):
    """Execute each caller's actual import statements (not a hand-written
    stand-in) and prove patches are invoked before
    that file's own first pydantic_ai import. Catches a removed facade-first
    import and a facade import left in the wrong position (e.g. after a
    pydantic_ai-importing module in the same file).
    """
    import_lines = _extract_leading_import_lines(_REPO_ROOT / relative_path)
    assert "code_puppy.cli_runner" in import_lines, (
        relative_path,
        "facade bootstrap import is missing from this file's leading import block",
    )
    probe = _run_cold_probe(import_lines)
    assert probe["patches_called"], (relative_path, probe)
    assert probe["patches_before_pydantic_ai"], (relative_path, probe)
