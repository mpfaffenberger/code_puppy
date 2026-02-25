"""Tests for code_puppy/tools/universal_constructor.py - 100% coverage."""

from unittest.mock import MagicMock, patch

import pytest


class TestHelpers:
    def test_stub_not_implemented(self):
        from code_puppy.tools.universal_constructor import _stub_not_implemented

        r = _stub_not_implemented("test")
        assert not r.success
        assert "Not implemented" in r.error

    def test_run_ruff_format_success(self):
        from code_puppy.tools.universal_constructor import _run_ruff_format

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert _run_ruff_format("/tmp/test.py") is None

    def test_run_ruff_format_fail(self):
        from code_puppy.tools.universal_constructor import _run_ruff_format

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="err")
            result = _run_ruff_format("/tmp/test.py")
            assert "ruff format failed" in result

    def test_run_ruff_format_not_found(self):
        from code_puppy.tools.universal_constructor import _run_ruff_format

        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _run_ruff_format("/tmp/test.py")
            assert "ruff not found" in result

    def test_run_ruff_format_timeout(self):
        import subprocess

        from code_puppy.tools.universal_constructor import _run_ruff_format

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ruff", 10)):
            result = _run_ruff_format("/tmp/test.py")
            assert "timed out" in result

    def test_run_ruff_format_other_error(self):
        from code_puppy.tools.universal_constructor import _run_ruff_format

        with patch("subprocess.run", side_effect=RuntimeError("boom")):
            result = _run_ruff_format("/tmp/test.py")
            assert "ruff format error" in result

    def test_generate_preview_short(self):
        from code_puppy.tools.universal_constructor import _generate_preview

        assert _generate_preview("a\nb") == "a\nb"

    def test_generate_preview_long(self):
        from code_puppy.tools.universal_constructor import _generate_preview

        code = "\n".join(f"line {i}" for i in range(20))
        result = _generate_preview(code, max_lines=5)
        assert "truncated" in result

    def test_emit_uc_message(self):
        from code_puppy.tools.universal_constructor import _emit_uc_message

        with patch(
            "code_puppy.tools.universal_constructor.get_message_bus"
        ) as mock_bus:
            _emit_uc_message("list", True, "ok", "tool", "details")
            mock_bus.return_value.emit.assert_called_once()

    def test_build_summary_error(self):
        from code_puppy.tools.universal_constructor import (
            UniversalConstructorOutput,
            _build_summary,
        )

        r = UniversalConstructorOutput(action="x", success=False, error="bad")
        assert _build_summary(r) == "bad"

    def test_build_summary_no_error(self):
        from code_puppy.tools.universal_constructor import (
            UniversalConstructorOutput,
            _build_summary,
        )

        r = UniversalConstructorOutput(action="x", success=False, error=None)
        assert _build_summary(r) == "Operation failed"

    def test_build_summary_list(self):
        from code_puppy.plugins.universal_constructor.models import UCListOutput
        from code_puppy.tools.universal_constructor import (
            UniversalConstructorOutput,
            _build_summary,
        )

        r = UniversalConstructorOutput(
            action="list",
            success=True,
            list_result=UCListOutput(tools=[], total_count=5, enabled_count=3),
        )
        assert "3" in _build_summary(r)

    def test_build_summary_call(self):
        from code_puppy.plugins.universal_constructor.models import UCCallOutput
        from code_puppy.tools.universal_constructor import (
            UniversalConstructorOutput,
            _build_summary,
        )

        r = UniversalConstructorOutput(
            action="call",
            success=True,
            call_result=UCCallOutput(
                success=True, tool_name="t", result="x", execution_time=1.5
            ),
        )
        assert "1.50s" in _build_summary(r)

    def test_build_summary_create(self):
        from code_puppy.plugins.universal_constructor.models import UCCreateOutput
        from code_puppy.tools.universal_constructor import (
            UniversalConstructorOutput,
            _build_summary,
        )

        r = UniversalConstructorOutput(
            action="create",
            success=True,
            create_result=UCCreateOutput(
                success=True, tool_name="t", source_path="/x", preview="p"
            ),
        )
        assert "Created t" in _build_summary(r)

    def test_build_summary_update(self):
        from code_puppy.plugins.universal_constructor.models import UCUpdateOutput
        from code_puppy.tools.universal_constructor import (
            UniversalConstructorOutput,
            _build_summary,
        )

        r = UniversalConstructorOutput(
            action="update",
            success=True,
            update_result=UCUpdateOutput(
                success=True, tool_name="t", source_path="/x", preview="p"
            ),
        )
        assert "Updated t" in _build_summary(r)

    def test_build_summary_info(self):
        from code_puppy.plugins.universal_constructor.models import (
            ToolMeta,
            UCInfoOutput,
            UCToolInfo,
        )
        from code_puppy.tools.universal_constructor import (
            UniversalConstructorOutput,
            _build_summary,
        )

        meta = ToolMeta(name="tool", namespace="ns", description="d")
        tool = UCToolInfo(
            meta=meta, signature="", source_path="", function_name="f", docstring=""
        )
        r = UniversalConstructorOutput(
            action="info",
            success=True,
            info_result=UCInfoOutput(success=True, tool=tool, source_code="c"),
        )
        assert "ns.tool" in _build_summary(r)

    def test_build_summary_success_no_result(self):
        from code_puppy.tools.universal_constructor import (
            UniversalConstructorOutput,
            _build_summary,
        )

        r = UniversalConstructorOutput(action="x", success=True)
        assert _build_summary(r) == "Operation completed"


class TestUniversalConstructorImpl:
    @pytest.mark.asyncio
    async def test_unknown_action(self):
        from code_puppy.tools.universal_constructor import universal_constructor_impl

        ctx = MagicMock()
        with patch("code_puppy.tools.universal_constructor._emit_uc_message"):
            r = await universal_constructor_impl(ctx, "unknown")
        assert not r.success
        assert "Unknown action" in r.error

    @pytest.mark.asyncio
    @patch("code_puppy.tools.universal_constructor._emit_uc_message")
    @patch("code_puppy.tools.universal_constructor._handle_list_action")
    async def test_routes_list(self, mock_list, mock_emit):
        from code_puppy.tools.universal_constructor import (
            UniversalConstructorOutput,
            universal_constructor_impl,
        )

        mock_list.return_value = UniversalConstructorOutput(action="list", success=True)
        ctx = MagicMock()
        await universal_constructor_impl(ctx, "list")
        mock_list.assert_called_once()

    @pytest.mark.asyncio
    @patch("code_puppy.tools.universal_constructor._emit_uc_message")
    @patch("code_puppy.tools.universal_constructor._handle_call_action")
    async def test_routes_call(self, mock_call, mock_emit):
        from code_puppy.tools.universal_constructor import (
            UniversalConstructorOutput,
            universal_constructor_impl,
        )

        mock_call.return_value = UniversalConstructorOutput(action="call", success=True)
        ctx = MagicMock()
        await universal_constructor_impl(ctx, "call", tool_name="t", tool_args={})
        mock_call.assert_called_once()

    @pytest.mark.asyncio
    @patch("code_puppy.tools.universal_constructor._emit_uc_message")
    @patch("code_puppy.tools.universal_constructor._handle_create_action")
    async def test_routes_create(self, mock_create, mock_emit):
        from code_puppy.tools.universal_constructor import (
            UniversalConstructorOutput,
            universal_constructor_impl,
        )

        mock_create.return_value = UniversalConstructorOutput(
            action="create", success=True
        )
        ctx = MagicMock()
        await universal_constructor_impl(ctx, "create", python_code="x")
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    @patch("code_puppy.tools.universal_constructor._emit_uc_message")
    @patch("code_puppy.tools.universal_constructor._handle_update_action")
    async def test_routes_update(self, mock_update, mock_emit):
        from code_puppy.tools.universal_constructor import (
            UniversalConstructorOutput,
            universal_constructor_impl,
        )

        mock_update.return_value = UniversalConstructorOutput(
            action="update", success=True
        )
        ctx = MagicMock()
        await universal_constructor_impl(ctx, "update", tool_name="t", python_code="x")
        mock_update.assert_called_once()

    @pytest.mark.asyncio
    @patch("code_puppy.tools.universal_constructor._emit_uc_message")
    @patch("code_puppy.tools.universal_constructor._handle_info_action")
    async def test_routes_info(self, mock_info, mock_emit):
        from code_puppy.tools.universal_constructor import (
            UniversalConstructorOutput,
            universal_constructor_impl,
        )

        mock_info.return_value = UniversalConstructorOutput(action="info", success=True)
        ctx = MagicMock()
        await universal_constructor_impl(ctx, "info", tool_name="t")
        mock_info.assert_called_once()


class TestHandleListAction:
    def test_success(self):
        from code_puppy.plugins.universal_constructor.models import ToolMeta, UCToolInfo
        from code_puppy.tools.universal_constructor import _handle_list_action

        meta1 = ToolMeta(name="t1", description="d", enabled=True)
        meta2 = ToolMeta(name="t2", description="d", enabled=False)
        t1 = UCToolInfo(meta=meta1, signature="", source_path="")
        t2 = UCToolInfo(meta=meta2, signature="", source_path="")
        mock_reg = MagicMock()
        mock_reg.list_tools.return_value = [t1, t2]
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_list_action(MagicMock())
        assert r.success
        assert r.list_result.enabled_count == 1

    def test_error(self):
        from code_puppy.tools.universal_constructor import _handle_list_action

        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            side_effect=Exception("boom"),
        ):
            r = _handle_list_action(MagicMock())
        assert not r.success


class TestHandleCallAction:
    def test_no_tool_name(self):
        from code_puppy.tools.universal_constructor import _handle_call_action

        r = _handle_call_action(MagicMock(), None, None)
        assert not r.success

    def test_tool_not_found(self):
        from code_puppy.tools.universal_constructor import _handle_call_action

        mock_reg = MagicMock()
        mock_reg.get_tool.return_value = None
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_call_action(MagicMock(), "bad", None)
        assert not r.success

    def test_tool_disabled(self):
        from code_puppy.tools.universal_constructor import _handle_call_action

        mock_reg = MagicMock()
        tool = MagicMock()
        tool.meta.enabled = False
        mock_reg.get_tool.return_value = tool
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_call_action(MagicMock(), "t", None)
        assert not r.success
        assert "disabled" in r.error

    def test_no_function(self):
        from code_puppy.tools.universal_constructor import _handle_call_action

        mock_reg = MagicMock()
        tool = MagicMock()
        tool.meta.enabled = True
        tool.source_path = None
        mock_reg.get_tool.return_value = tool
        mock_reg.get_tool_function.return_value = None
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_call_action(MagicMock(), "t", None)
        assert not r.success

    def test_invalid_json_args(self):
        from code_puppy.tools.universal_constructor import _handle_call_action

        mock_reg = MagicMock()
        tool = MagicMock()
        tool.meta.enabled = True
        tool.source_path = None
        mock_reg.get_tool.return_value = tool
        mock_reg.get_tool_function.return_value = lambda: None
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_call_action(MagicMock(), "t", "not{json")
        assert not r.success

    def test_non_dict_args(self):
        from code_puppy.tools.universal_constructor import _handle_call_action

        mock_reg = MagicMock()
        tool = MagicMock()
        tool.meta.enabled = True
        tool.source_path = None
        mock_reg.get_tool.return_value = tool
        mock_reg.get_tool_function.return_value = lambda: None
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_call_action(MagicMock(), "t", [1, 2])
        assert not r.success
        assert "dict" in r.error

    def test_success(self):
        from code_puppy.tools.universal_constructor import _handle_call_action

        mock_reg = MagicMock()
        tool = MagicMock()
        tool.meta.enabled = True
        tool.source_path = None
        mock_reg.get_tool.return_value = tool
        mock_reg.get_tool_function.return_value = lambda x=1: x * 2
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_call_action(MagicMock(), "t", {"x": 5})
        assert r.success
        assert r.call_result.result == 10

    def test_timeout(self):
        import time

        from code_puppy.tools.universal_constructor import _handle_call_action

        mock_reg = MagicMock()
        tool = MagicMock()
        tool.meta.enabled = True
        tool.source_path = None
        mock_reg.get_tool.return_value = tool

        def slow_func():
            time.sleep(100)

        mock_reg.get_tool_function.return_value = slow_func
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            with patch(
                "code_puppy.tools.universal_constructor.ThreadPoolExecutor"
            ) as mock_exec:
                from concurrent.futures import TimeoutError as FTE

                mock_future = MagicMock()
                mock_future.result.side_effect = FTE()
                mock_exec.return_value.__enter__ = MagicMock(
                    return_value=MagicMock(submit=MagicMock(return_value=mock_future))
                )
                mock_exec.return_value.__exit__ = MagicMock(return_value=False)
                r = _handle_call_action(MagicMock(), "t", {})
        assert not r.success
        assert "timed out" in r.error

    def test_type_error(self):
        from code_puppy.tools.universal_constructor import _handle_call_action

        mock_reg = MagicMock()
        tool = MagicMock()
        tool.meta.enabled = True
        tool.source_path = None
        mock_reg.get_tool.return_value = tool

        def bad_func():
            raise TypeError("wrong args")

        mock_reg.get_tool_function.return_value = bad_func
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            # ThreadPoolExecutor will propagate the TypeError
            r = _handle_call_action(MagicMock(), "t", {})
        assert not r.success

    def test_general_exception(self):
        from code_puppy.tools.universal_constructor import _handle_call_action

        mock_reg = MagicMock()
        tool = MagicMock()
        tool.meta.enabled = True
        tool.source_path = None
        mock_reg.get_tool.return_value = tool

        def bad_func():
            raise RuntimeError("boom")

        mock_reg.get_tool_function.return_value = bad_func
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_call_action(MagicMock(), "t", {})
        assert not r.success

    def test_with_source_preview(self):
        from code_puppy.tools.universal_constructor import _handle_call_action

        mock_reg = MagicMock()
        tool = MagicMock()
        tool.meta.enabled = True
        tool.source_path = "/tmp/test.py"
        mock_reg.get_tool.return_value = tool
        mock_reg.get_tool_function.return_value = lambda: 42
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            with patch("pathlib.Path.read_text", return_value="def f(): pass"):
                r = _handle_call_action(MagicMock(), "t", {})
        assert r.success
        assert r.call_result.source_preview is not None

    def test_valid_json_string_args(self):
        from code_puppy.tools.universal_constructor import _handle_call_action

        mock_reg = MagicMock()
        tool = MagicMock()
        tool.meta.enabled = True
        tool.source_path = None
        mock_reg.get_tool.return_value = tool
        mock_reg.get_tool_function.return_value = lambda x=1: x
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_call_action(MagicMock(), "t", '{"x": 42}')
        assert r.success


class TestHandleCreateAction:
    def test_no_code(self):
        from code_puppy.tools.universal_constructor import _handle_create_action

        r = _handle_create_action(MagicMock(), "t", None, None)
        assert not r.success

    def test_empty_code(self):
        from code_puppy.tools.universal_constructor import _handle_create_action

        r = _handle_create_action(MagicMock(), "t", "  ", None)
        assert not r.success

    def test_syntax_error(self):
        from code_puppy.tools.universal_constructor import _handle_create_action

        with patch(
            "code_puppy.plugins.universal_constructor.sandbox.validate_syntax"
        ) as mock_val:
            mock_val.return_value = MagicMock(valid=False, errors=["bad syntax"])
            r = _handle_create_action(MagicMock(), "t", "def (:", None)
        assert not r.success
        assert "Syntax error" in r.error

    def test_no_functions(self):
        from code_puppy.tools.universal_constructor import _handle_create_action

        with (
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.validate_syntax"
            ) as mock_val,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.extract_function_info"
            ) as mock_ext,
        ):
            mock_val.return_value = MagicMock(valid=True)
            mock_ext.return_value = MagicMock(functions=[], warnings=[])
            r = _handle_create_action(MagicMock(), "t", "x = 1", None)
        assert not r.success
        assert "No functions" in r.error

    def test_no_name(self):
        from types import SimpleNamespace

        from code_puppy.tools.universal_constructor import _handle_create_action

        func = SimpleNamespace(name="", docstring="")
        with (
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.validate_syntax"
            ) as mock_val,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.extract_function_info"
            ) as mock_ext,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox._extract_tool_meta",
                return_value=None,
            ),
        ):
            mock_val.return_value = MagicMock(valid=True)
            mock_ext.return_value = SimpleNamespace(functions=[func], warnings=[])
            r = _handle_create_action(MagicMock(), None, "def f(): pass", None)
        assert not r.success

    def test_meta_validation_error(self):
        from code_puppy.tools.universal_constructor import _handle_create_action

        func = MagicMock(name="f", docstring="")
        with (
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.validate_syntax"
            ) as mock_val,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.extract_function_info"
            ) as mock_ext,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox._extract_tool_meta",
                return_value={"name": "t"},
            ),
            patch(
                "code_puppy.plugins.universal_constructor.sandbox._validate_tool_meta",
                return_value=["missing field"],
            ),
        ):
            mock_val.return_value = MagicMock(valid=True)
            mock_ext.return_value = MagicMock(functions=[func], warnings=[])
            r = _handle_create_action(MagicMock(), "t", "def f(): pass", None)
        assert not r.success
        assert "Invalid TOOL_META" in r.error

    def test_write_error(self):
        from code_puppy.tools.universal_constructor import _handle_create_action

        func = MagicMock(name="f", docstring="")
        with (
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.validate_syntax"
            ) as mock_val,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.extract_function_info"
            ) as mock_ext,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox._extract_tool_meta",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.check_dangerous_patterns"
            ) as mock_safe,
            patch("pathlib.Path.mkdir", side_effect=OSError("perm")),
        ):
            mock_val.return_value = MagicMock(valid=True)
            mock_ext.return_value = MagicMock(functions=[func], warnings=[])
            mock_safe.return_value = MagicMock(warnings=[])
            r = _handle_create_action(MagicMock(), "test", "def f(): pass", "desc")
        assert not r.success
        assert "Failed to write" in r.error

    def test_success_with_namespace(self, tmp_path):
        from code_puppy.tools.universal_constructor import _handle_create_action

        func = MagicMock(name="f", docstring="")
        with (
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.validate_syntax"
            ) as mock_val,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.extract_function_info"
            ) as mock_ext,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox._extract_tool_meta",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.check_dangerous_patterns"
            ) as mock_safe,
            patch("code_puppy.plugins.universal_constructor.USER_UC_DIR", tmp_path),
            patch(
                "code_puppy.tools.universal_constructor._run_ruff_format",
                return_value=None,
            ),
            patch("code_puppy.plugins.universal_constructor.registry.get_registry"),
        ):
            mock_val.return_value = MagicMock(valid=True)
            mock_ext.return_value = MagicMock(functions=[func], warnings=[])
            mock_safe.return_value = MagicMock(warnings=[])
            r = _handle_create_action(
                MagicMock(), "api.weather", "def f(): pass", "desc"
            )
        assert r.success
        assert "api.weather" in r.create_result.tool_name

    def test_success_with_existing_meta(self, tmp_path):
        from code_puppy.tools.universal_constructor import _handle_create_action

        func = MagicMock(name="f", docstring="")
        meta = {"name": "tool", "namespace": "ns", "description": "d"}
        with (
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.validate_syntax"
            ) as mock_val,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.extract_function_info"
            ) as mock_ext,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox._extract_tool_meta",
                return_value=meta,
            ),
            patch(
                "code_puppy.plugins.universal_constructor.sandbox._validate_tool_meta",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.check_dangerous_patterns"
            ) as mock_safe,
            patch("code_puppy.plugins.universal_constructor.USER_UC_DIR", tmp_path),
            patch(
                "code_puppy.tools.universal_constructor._run_ruff_format",
                return_value="warn",
            ),
            patch("code_puppy.plugins.universal_constructor.registry.get_registry"),
        ):
            mock_val.return_value = MagicMock(valid=True)
            mock_ext.return_value = MagicMock(functions=[func], warnings=["w"])
            mock_safe.return_value = MagicMock(warnings=["unsafe"])
            r = _handle_create_action(MagicMock(), None, "def f(): pass", None)
        assert r.success

    def test_registry_reload_fail(self, tmp_path):
        from code_puppy.tools.universal_constructor import _handle_create_action

        func = MagicMock(name="f", docstring="")
        with (
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.validate_syntax"
            ) as mock_val,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.extract_function_info"
            ) as mock_ext,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox._extract_tool_meta",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.check_dangerous_patterns"
            ) as mock_safe,
            patch("code_puppy.plugins.universal_constructor.USER_UC_DIR", tmp_path),
            patch(
                "code_puppy.tools.universal_constructor._run_ruff_format",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry"
            ) as mock_reg,
        ):
            mock_val.return_value = MagicMock(valid=True)
            mock_ext.return_value = MagicMock(functions=[func], warnings=[])
            mock_safe.return_value = MagicMock(warnings=[])
            mock_reg.return_value.reload.side_effect = Exception("boom")
            r = _handle_create_action(MagicMock(), "tool", "def f(): pass", "desc")
        assert r.success  # partial success


class TestHandleUpdateAction:
    def test_no_tool_name(self):
        from code_puppy.tools.universal_constructor import _handle_update_action

        r = _handle_update_action(MagicMock(), None, "code", None)
        assert not r.success

    def test_no_code(self):
        from code_puppy.tools.universal_constructor import _handle_update_action

        r = _handle_update_action(MagicMock(), "t", None, None)
        assert not r.success

    def test_tool_not_found(self):
        from code_puppy.tools.universal_constructor import _handle_update_action

        mock_reg = MagicMock()
        mock_reg.get_tool.return_value = None
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_update_action(MagicMock(), "t", "code", None)
        assert not r.success

    def test_no_source_path(self):
        from code_puppy.tools.universal_constructor import _handle_update_action

        mock_reg = MagicMock()
        tool = MagicMock()
        tool.source_path = None
        mock_reg.get_tool.return_value = tool
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_update_action(MagicMock(), "t", "code", None)
        assert not r.success

    def test_syntax_error(self, tmp_path):
        from code_puppy.tools.universal_constructor import _handle_update_action

        f = tmp_path / "tool.py"
        f.write_text("old")
        mock_reg = MagicMock()
        tool = MagicMock()
        tool.source_path = str(f)
        mock_reg.get_tool.return_value = tool
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_reg,
            ),
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.validate_syntax"
            ) as mock_val,
        ):
            mock_val.return_value = MagicMock(valid=False, errors=["bad"])
            r = _handle_update_action(MagicMock(), "t", "def (:", None)
        assert not r.success

    def test_no_tool_meta(self, tmp_path):
        from code_puppy.tools.universal_constructor import _handle_update_action

        f = tmp_path / "tool.py"
        f.write_text("old")
        mock_reg = MagicMock()
        tool = MagicMock()
        tool.source_path = str(f)
        mock_reg.get_tool.return_value = tool
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_reg,
            ),
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.validate_syntax"
            ) as mock_val,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox._extract_tool_meta",
                return_value=None,
            ),
        ):
            mock_val.return_value = MagicMock(valid=True)
            r = _handle_update_action(MagicMock(), "t", "def f(): pass", None)
        assert not r.success
        assert "TOOL_META" in r.error

    def test_invalid_meta(self, tmp_path):
        from code_puppy.tools.universal_constructor import _handle_update_action

        f = tmp_path / "tool.py"
        f.write_text("old")
        mock_reg = MagicMock()
        tool = MagicMock()
        tool.source_path = str(f)
        mock_reg.get_tool.return_value = tool
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_reg,
            ),
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.validate_syntax"
            ) as mock_val,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox._extract_tool_meta",
                return_value={"name": "t"},
            ),
            patch(
                "code_puppy.plugins.universal_constructor.sandbox._validate_tool_meta",
                return_value=["err"],
            ),
        ):
            mock_val.return_value = MagicMock(valid=True)
            r = _handle_update_action(MagicMock(), "t", "def f(): pass", None)
        assert not r.success

    def test_success(self, tmp_path):
        from code_puppy.tools.universal_constructor import _handle_update_action

        f = tmp_path / "tool.py"
        f.write_text("old")
        mock_reg = MagicMock()
        tool = MagicMock()
        tool.source_path = str(f)
        mock_reg.get_tool.return_value = tool
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_reg,
            ),
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.validate_syntax"
            ) as mock_val,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox._extract_tool_meta",
                return_value={"name": "t"},
            ),
            patch(
                "code_puppy.plugins.universal_constructor.sandbox._validate_tool_meta",
                return_value=[],
            ),
            patch(
                "code_puppy.tools.universal_constructor._run_ruff_format",
                return_value=None,
            ),
        ):
            mock_val.return_value = MagicMock(valid=True)
            r = _handle_update_action(MagicMock(), "t", "def f(): pass", None)
        assert r.success

    def test_update_exception(self, tmp_path):
        from code_puppy.tools.universal_constructor import _handle_update_action

        f = tmp_path / "tool.py"
        f.write_text("old")
        mock_reg = MagicMock()
        tool = MagicMock()
        tool.source_path = str(f)
        mock_reg.get_tool.return_value = tool
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_reg,
            ),
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.validate_syntax",
                side_effect=Exception("boom"),
            ),
        ):
            r = _handle_update_action(MagicMock(), "t", "code", None)
        assert not r.success


def _make_uc_tool_info(source_path=""):
    from code_puppy.plugins.universal_constructor.models import ToolMeta, UCToolInfo

    meta = ToolMeta(name="t", description="d")
    return UCToolInfo(meta=meta, signature="", source_path=source_path)


class TestHandleInfoAction:
    def test_no_tool_name(self):
        from code_puppy.tools.universal_constructor import _handle_info_action

        r = _handle_info_action(MagicMock(), None)
        assert not r.success

    def test_tool_not_found(self):
        from code_puppy.tools.universal_constructor import _handle_info_action

        mock_reg = MagicMock()
        mock_reg.get_tool.return_value = None
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_info_action(MagicMock(), "bad")
        assert not r.success

    def test_with_source(self, tmp_path):
        from code_puppy.tools.universal_constructor import _handle_info_action

        f = tmp_path / "tool.py"
        f.write_text("def f(): pass")
        tool = _make_uc_tool_info(str(f))
        mock_reg = MagicMock()
        mock_reg.get_tool.return_value = tool
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_info_action(MagicMock(), "t")
        assert r.success
        assert "def f" in r.info_result.source_code

    def test_source_not_found(self):
        from code_puppy.tools.universal_constructor import _handle_info_action

        tool = _make_uc_tool_info("/nonexistent/path.py")
        mock_reg = MagicMock()
        mock_reg.get_tool.return_value = tool
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_info_action(MagicMock(), "t")
        assert r.success
        assert "not found" in r.info_result.source_code

    def test_source_no_path(self):
        from code_puppy.tools.universal_constructor import _handle_info_action

        tool = _make_uc_tool_info("")
        mock_reg = MagicMock()
        mock_reg.get_tool.return_value = tool
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_info_action(MagicMock(), "t")
        assert r.success
        assert "not found" in r.info_result.source_code


class TestHandleCallSourceReadError:
    def test_source_read_exception(self):
        from code_puppy.tools.universal_constructor import _handle_call_action

        mock_reg = MagicMock()
        tool = MagicMock()
        tool.meta.enabled = True
        tool.source_path = "/tmp/nonexistent_12345.py"
        mock_reg.get_tool.return_value = tool
        mock_reg.get_tool_function.return_value = lambda: 42
        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_reg,
        ):
            r = _handle_call_action(MagicMock(), "t", {})
        assert r.success


class TestHandleInfoReadError:
    def test_source_read_exception(self, tmp_path):
        from code_puppy.tools.universal_constructor import _handle_info_action

        f = tmp_path / "tool.py"
        f.write_text("code")
        # Make it unreadable by patching
        tool = _make_uc_tool_info(str(f))
        mock_reg = MagicMock()
        mock_reg.get_tool.return_value = tool
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_reg,
            ),
            patch("pathlib.Path.read_text", side_effect=Exception("perm denied")),
        ):
            r = _handle_info_action(MagicMock(), "t")
        assert r.success
        assert "Could not read" in r.info_result.source_code


class TestHandleUpdateFormatWarning:
    def test_format_warning(self, tmp_path):
        from code_puppy.tools.universal_constructor import _handle_update_action

        f = tmp_path / "tool.py"
        f.write_text("old")
        mock_reg = MagicMock()
        tool = MagicMock()
        tool.source_path = str(f)
        mock_reg.get_tool.return_value = tool
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_reg,
            ),
            patch(
                "code_puppy.plugins.universal_constructor.sandbox.validate_syntax"
            ) as mock_val,
            patch(
                "code_puppy.plugins.universal_constructor.sandbox._extract_tool_meta",
                return_value={"name": "t"},
            ),
            patch(
                "code_puppy.plugins.universal_constructor.sandbox._validate_tool_meta",
                return_value=[],
            ),
            patch(
                "code_puppy.tools.universal_constructor._run_ruff_format",
                return_value="ruff warning",
            ),
        ):
            mock_val.return_value = MagicMock(valid=True)
            r = _handle_update_action(MagicMock(), "t", "def f(): pass", None)
        assert r.success


class TestImplRegistration:
    @pytest.mark.asyncio
    async def test_registered_tool_calls_impl(self):
        from code_puppy.tools.universal_constructor import (
            register_universal_constructor,
        )

        agent = MagicMock()
        captured = {}

        def tool_decorator(fn):
            captured["fn"] = fn
            return fn

        agent.tool = tool_decorator
        register_universal_constructor(agent)
        ctx = MagicMock()
        with patch(
            "code_puppy.tools.universal_constructor.universal_constructor_impl"
        ) as mock_impl:
            from code_puppy.tools.universal_constructor import (
                UniversalConstructorOutput,
            )

            mock_impl.return_value = UniversalConstructorOutput(
                action="list", success=True
            )
            await captured["fn"](ctx, action="list")
            mock_impl.assert_called_once()


class TestRegisterUniversalConstructor:
    def test_register(self):
        from code_puppy.tools.universal_constructor import (
            register_universal_constructor,
        )

        agent = MagicMock()
        captured = {}

        def tool_decorator(fn):
            captured["fn"] = fn
            return fn

        agent.tool = tool_decorator
        register_universal_constructor(agent)
        assert "fn" in captured
