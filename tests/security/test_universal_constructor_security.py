"""Security regression tests for Universal Constructor hardening (P0-07)."""

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.plugins.universal_constructor.safety import (
    UCApprovalStore,
    check_code_safety,
    compute_code_hash,
    is_path_within_uc_dir,
    validate_full_tool_name,
    validate_namespace,
    validate_tool_name,
)
from code_puppy.plugins.universal_constructor.runner import (
    run_tool_subprocess,
    _cap_output,
)


class TestToolNameValidation:
    """Strict validation of tool names/namespaces."""

    def test_valid_name_accepted(self):
        assert validate_tool_name("weather") is None
        assert validate_tool_name("api_v2") is None

    def test_underscore_prefix_rejected_as_hidden(self):
        assert validate_tool_name("_internal") is not None

    def test_empty_name_rejected(self):
        assert validate_tool_name("") is not None

    def test_dot_rejected(self):
        assert validate_tool_name("a.b") is not None

    def test_path_traversal_rejected(self):
        assert validate_tool_name("../escape") is not None
        assert validate_tool_name("foo/..") is not None
        assert validate_tool_name("foo\\bar") is not None

    def test_hidden_name_rejected(self):
        assert validate_tool_name(".hidden") is not None

    def test_dunder_rejected(self):
        assert validate_tool_name("__init__") is not None
        assert validate_tool_name("__pycache__") is not None

    def test_reserved_module_name_rejected(self):
        assert validate_tool_name("os") is not None
        assert validate_tool_name("subprocess") is not None
        assert validate_tool_name("pickle") is not None
        assert validate_tool_name("json") is not None  # json is reserved

    def test_full_tool_name_with_namespace(self):
        assert validate_full_tool_name("api.weather") is None
        assert validate_full_tool_name("api.finance.stocks") is None

    def test_full_tool_name_traversal_rejected(self):
        assert validate_full_tool_name("../escape") is not None
        assert validate_full_tool_name("a.b/c") is not None

    def test_namespace_validation(self):
        assert validate_namespace("api") is None
        assert validate_namespace("api.finance") is None
        assert validate_namespace("api./escape") is not None


class TestPathContainment:
    """Enforce path containment inside USER_UC_DIR."""

    def test_path_inside_uc_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            uc_dir = Path(tmpdir) / "uc"
            uc_dir.mkdir()
            file_path = uc_dir / "tool.py"
            assert is_path_within_uc_dir(file_path, uc_dir) is True

    def test_path_outside_uc_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            uc_dir = Path(tmpdir) / "uc"
            uc_dir.mkdir()
            outside = Path(tmpdir) / "outside.py"
            assert is_path_within_uc_dir(outside, uc_dir) is False

    def test_symlink_escape_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            uc_dir = Path(tmpdir) / "uc"
            uc_dir.mkdir()
            outside = Path(tmpdir) / "secret.py"
            symlink = uc_dir / "link.py"
            try:
                symlink.symlink_to(outside)
            except OSError:
                pytest.skip("Symlink creation not supported on this platform")
            assert is_path_within_uc_dir(symlink, uc_dir) is False


class TestDangerousCodeBlocking:
    """Dangerous patterns must block or require approval."""

    def test_safe_code_passes(self):
        code = "def hello(): return 'world'"
        result = check_code_safety(code)
        assert result.blocked is False
        assert result.requires_approval is False

    def test_eval_blocked(self):
        code = "def bad(x): return eval(x)"
        result = check_code_safety(code)
        assert result.blocked is True
        assert any("eval" in e.lower() for e in result.errors)

    def test_exec_blocked(self):
        code = "exec('print(1)')"
        result = check_code_safety(code)
        assert result.blocked is True

    def test_subprocess_import_blocked(self):
        code = "import subprocess\ndef run(cmd): subprocess.call(cmd)"
        result = check_code_safety(code)
        assert result.blocked is True
        assert any("subprocess" in e.lower() for e in result.errors)

    def test_os_system_blocked(self):
        code = "from os import system\ndef bad(): system('rm -rf /')"
        result = check_code_safety(code)
        assert result.blocked is True

    def test_pickle_blocked(self):
        code = "import pickle\ndef load(data): return pickle.loads(data)"
        result = check_code_safety(code)
        assert result.blocked is True

    def test_open_write_blocked(self):
        code = "def write(path, data):\n    with open(path, 'w') as f:\n        f.write(data)"
        result = check_code_safety(code)
        assert result.blocked is True
        assert any("open()" in e for e in result.errors)

    def test_requests_requires_approval(self):
        code = "import requests\ndef fetch(url): return requests.get(url).text"
        result = check_code_safety(code)
        assert result.blocked is False
        assert result.requires_approval is True
        assert any("requests" in w.lower() for w in result.warnings)

    def test_invalid_syntax_returns_error(self):
        code = "def broken("
        result = check_code_safety(code)
        assert result.blocked is False  # syntax error is reported differently
        assert result.safe is False
        assert len(result.errors) > 0


class TestUCApprovalStore:
    """Approval stored with code hash; invalidated on changes."""

    def test_not_approved_by_default(self):
        store = UCApprovalStore()
        assert store.is_approved("my_tool", "hash123") is False

    def test_approve_and_check(self):
        store = UCApprovalStore()
        store.approve("my_tool", "hash123")
        assert store.is_approved("my_tool", "hash123") is True

    def test_approval_invalidated_on_hash_change(self):
        store = UCApprovalStore()
        store.approve("my_tool", "hash_v1")
        assert store.is_approved("my_tool", "hash_v1") is True
        assert store.is_approved("my_tool", "hash_v2") is False

    def test_revoke_approval(self):
        store = UCApprovalStore()
        store.approve("my_tool", "hash123")
        store.revoke("my_tool", "hash123")
        assert store.is_approved("my_tool", "hash123") is False


class TestSubprocessRunner:
    """Killable subprocess runner with JSON-only serialization."""

    def test_run_simple_function(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            module_path = Path(tmpdir) / "adder.py"
            module_path.write_text(
                "def add(a, b):\n    return a + b\n",
                encoding="utf-8",
            )
            result = run_tool_subprocess(
                str(module_path), "add", {"a": 2, "b": 3}, timeout=5.0
            )
            assert result["success"] is True
            assert result["result"] == 5
            assert result["execution_time"] > 0

    def test_run_nonexistent_function(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            module_path = Path(tmpdir) / "empty.py"
            module_path.write_text("x = 1\n", encoding="utf-8")
            result = run_tool_subprocess(str(module_path), "missing", {}, timeout=5.0)
            assert result["success"] is False
            assert "not found" in result.get("error", "").lower()

    def test_timeout_kills_worker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            module_path = Path(tmpdir) / "slow.py"
            module_path.write_text(
                "import time\ndef slow():\n    time.sleep(60)\n    return 'done'\n",
                encoding="utf-8",
            )
            start = time.time()
            result = run_tool_subprocess(str(module_path), "slow", {}, timeout=0.5)
            elapsed = time.time() - start
            assert result["success"] is False
            assert "timed out" in result.get("error", "").lower()
            assert elapsed < 5.0  # should not wait 60s

    def test_non_json_serializable_result_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            module_path = Path(tmpdir) / "weird.py"
            module_path.write_text(
                "class Weird:\n    pass\ndef get():\n    return Weird()\n",
                encoding="utf-8",
            )
            result = run_tool_subprocess(str(module_path), "get", {}, timeout=5.0)
            assert result["success"] is False
            assert "JSON" in result.get("error", "")

    def test_output_capped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            module_path = Path(tmpdir) / "chatty.py"
            module_path.write_text(
                "def chat():\n    for i in range(500):\n        print('line', i)\n    return 'ok'\n",
                encoding="utf-8",
            )
            result = run_tool_subprocess(str(module_path), "chat", {}, timeout=5.0)
            assert result["success"] is True
            stdout = result.get("stdout", "")
            assert "... [output truncated]" in stdout or stdout.count("\n") <= 300

    def test_cap_output_function(self):
        long_text = "\n".join(f"line {i}" for i in range(500))
        capped = _cap_output(long_text, max_chars=10000, max_lines=256)
        assert "... [output truncated]" in capped
        assert capped.count("\n") <= 257


class TestRegistryHardening:
    """Registry must parse AST before import and skip untrusted tools."""

    def test_scan_skips_disabled_tools_without_import(self):
        from code_puppy.plugins.universal_constructor.registry import UCRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)
            disabled_code = """
TOOL_META = {"name": "disabled_tool", "description": "Test", "enabled": False}
def disabled_tool(): raise RuntimeError("should not execute")
"""
            (tools_dir / "disabled_tool.py").write_text(disabled_code)
            registry = UCRegistry(tools_dir)
            registry.scan()
            tool = registry.get_tool("disabled_tool")
            assert tool is not None
            assert tool.meta.enabled is False
            # Module should NOT have been imported
            assert "disabled_tool" not in registry._modules

    def test_scan_skips_blocked_tools_without_import(self):
        from code_puppy.plugins.universal_constructor.registry import UCRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)
            dangerous_code = """
TOOL_META = {"name": "dangerous", "description": "Test", "enabled": True}
import subprocess
def dangerous(): subprocess.call("ls")
"""
            (tools_dir / "dangerous.py").write_text(dangerous_code)
            registry = UCRegistry(tools_dir)
            registry.scan()
            tool = registry.get_tool("dangerous")
            assert tool is not None
            # Function should NOT be importable because blocked
            func = registry.get_tool_function("dangerous")
            assert func is None

    def test_scan_skips_tools_outside_uc_dir(self):
        from code_puppy.plugins.universal_constructor.registry import UCRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir) / "uc"
            tools_dir.mkdir()
            outside_dir = Path(tmpdir) / "outside"
            outside_dir.mkdir()
            code = """
TOOL_META = {"name": "bad", "description": "Test"}
def bad(): pass
"""
            # Write to a file that _appears_ inside but is symlinked outside
            real_file = outside_dir / "bad.py"
            real_file.write_text(code)
            symlink = tools_dir / "bad.py"
            try:
                symlink.symlink_to(real_file)
            except OSError:
                pytest.skip("Symlink creation not supported")
            registry = UCRegistry(tools_dir)
            count = registry.scan()
            assert count == 0

    def test_list_does_not_execute_top_level_for_untrusted(self):
        from code_puppy.plugins.universal_constructor.registry import UCRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            tools_dir = Path(tmpdir)
            # This code has top-level side effects
            code = """
import os
os.environ["UC_SIDE_EFFECT"] = "executed"
TOOL_META = {"name": "sidefx", "description": "Test", "enabled": True}
import subprocess
def sidefx(): pass
"""
            (tools_dir / "sidefx.py").write_text(code)
            # Ensure env var is not set initially
            os.environ.pop("UC_SIDE_EFFECT", None)
            registry = UCRegistry(tools_dir)
            registry.scan()
            # The tool should be present but not imported
            tool = registry.get_tool("sidefx")
            assert tool is not None
            # Env var should NOT be set because we didn't import the module
            assert os.environ.get("UC_SIDE_EFFECT") is None


class TestToolCreationHardening:
    """Create/update actions must reject path traversal and dangerous code."""

    def test_create_rejects_path_traversal_name(self):
        from code_puppy.tools.universal_constructor import _handle_create_action
        from unittest.mock import MagicMock

        result = _handle_create_action(
            MagicMock(),
            tool_name="../escape",
            python_code="def escape(): pass",
            description="bad",
        )
        assert result.success is False
        assert (
            "cannot start or end with" in result.error.lower()
            or "traversal" in result.error.lower()
            or "invalid" in result.error.lower()
        )

    def test_create_rejects_reserved_name(self):
        from code_puppy.tools.universal_constructor import _handle_create_action
        from unittest.mock import MagicMock

        result = _handle_create_action(
            MagicMock(),
            tool_name="subprocess",
            python_code="def subprocess(): pass",
            description="bad",
        )
        assert result.success is False
        assert "reserved" in result.error.lower()

    def test_create_blocks_dangerous_code(self):
        from code_puppy.tools.universal_constructor import _handle_create_action
        from unittest.mock import MagicMock

        result = _handle_create_action(
            MagicMock(),
            tool_name="evil",
            python_code="import os\ndef evil(): os.system('rm -rf /')",
            description="bad",
        )
        assert result.success is False
        assert "blocked" in result.error.lower()

    def test_update_rejects_outside_uc_dir(self):
        from code_puppy.tools.universal_constructor import _handle_update_action
        from unittest.mock import MagicMock

        # Mock a tool whose source_path is outside UC dir
        mock_tool = MagicMock()
        mock_tool.source_path = "/tmp/evil.py"
        mock_reg = MagicMock()
        mock_reg.get_tool.return_value = mock_tool
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            with patch("pathlib.Path.exists", return_value=True):
                result = _handle_update_action(
                    MagicMock(),
                    tool_name="evil",
                    python_code="def evil(): pass",
                    description=None,
                )
        assert result.success is False
        assert "escapes" in result.error.lower() or "outside" in result.error.lower()


class TestApprovalInvalidationOnCodeChange:
    """Approval must be invalidated when code hash changes."""

    def test_approval_store_invalidates_on_hash_change(self):
        # Use a fresh in-memory store by clearing any persisted state
        store = UCApprovalStore()
        store._db = {}
        store._loaded = True
        code_v1 = "def greet(): return 'hello'"
        code_v2 = "def greet(): return 'hi'"
        h1 = compute_code_hash(code_v1)
        h2 = compute_code_hash(code_v2)
        store.approve("greet", h1)
        assert store.is_approved("greet", h1) is True
        assert store.is_approved("greet", h2) is False
        store.approve("greet", h2)
        assert store.is_approved("greet", h2) is True
        # Old hash should still be valid too (it's a separate entry)
        assert store.is_approved("greet", h1) is True
