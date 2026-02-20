"""Full coverage tests for tools/universal_constructor.py."""

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.universal_constructor import (
    UniversalConstructorOutput,
    _build_summary,
    _emit_uc_message,
    _generate_preview,
    _run_ruff_format,
    _stub_not_implemented,
    universal_constructor_impl,
)


class TestGeneratePreview:
    def test_short_code(self):
        assert _generate_preview("a\nb") == "a\nb"

    def test_long_code(self):
        code = "\n".join(f"line{i}" for i in range(20))
        preview = _generate_preview(code, max_lines=5)
        assert "truncated" in preview
        assert preview.count("\n") == 5


class TestRunRuffFormat:
    def test_success(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x=1")
        result = _run_ruff_format(f)
        assert result is None or isinstance(result, str)

    def test_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _run_ruff_format("/fake")
            assert "not found" in result

    def test_timeout(self):
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ruff", 10)):
            result = _run_ruff_format("/fake")
            assert "timed out" in result

    def test_nonzero_exit(self):
        mock_result = MagicMock(returncode=1, stderr="error")
        with patch("subprocess.run", return_value=mock_result):
            result = _run_ruff_format("/fake")
            assert "failed" in result

    def test_generic_exception(self):
        with patch("subprocess.run", side_effect=Exception("boom")):
            result = _run_ruff_format("/fake")
            assert "error" in result


class TestStubNotImplemented:
    def test_returns_error(self):
        result = _stub_not_implemented("test")
        assert result.success is False
        assert "Not implemented" in result.error


class TestEmitUcMessage:
    def test_emits(self):
        with patch("code_puppy.tools.universal_constructor.get_message_bus") as mb:
            _emit_uc_message("list", True, "summary", "tool", "details")
            mb().emit.assert_called_once()


class TestBuildSummary:
    def test_error(self):
        r = UniversalConstructorOutput(action="x", success=False, error="fail")
        assert _build_summary(r) == "fail"

    def test_error_none(self):
        r = UniversalConstructorOutput(action="x", success=False)
        assert _build_summary(r) == "Operation failed"

    def test_list_result(self):
        from code_puppy.plugins.universal_constructor.models import UCListOutput

        r = UniversalConstructorOutput(
            action="list",
            success=True,
            list_result=UCListOutput(tools=[], total_count=5, enabled_count=3),
        )
        assert "3" in _build_summary(r)

    def test_call_result(self):
        from code_puppy.plugins.universal_constructor.models import UCCallOutput

        r = UniversalConstructorOutput(
            action="call",
            success=True,
            call_result=UCCallOutput(
                success=True, tool_name="t", result="ok", execution_time=1.5
            ),
        )
        assert "1.50" in _build_summary(r)

    def test_create_result(self):
        from code_puppy.plugins.universal_constructor.models import UCCreateOutput

        r = UniversalConstructorOutput(
            action="create",
            success=True,
            create_result=UCCreateOutput(success=True, tool_name="t", source_path="/p"),
        )
        assert "Created" in _build_summary(r)

    def test_update_result(self):
        from code_puppy.plugins.universal_constructor.models import UCUpdateOutput

        r = UniversalConstructorOutput(
            action="update",
            success=True,
            update_result=UCUpdateOutput(success=True, tool_name="t", source_path="/p"),
        )
        assert "Updated" in _build_summary(r)

    def test_info_result(self):
        from code_puppy.plugins.universal_constructor.models import (
            ToolMeta,
            UCInfoOutput,
            UCToolInfo,
        )

        meta = ToolMeta(name="test", namespace="ns", description="d", enabled=True)
        tool_info = UCToolInfo(
            meta=meta, signature="def f()", source_path="/p", function_name="f"
        )
        r = UniversalConstructorOutput(
            action="info",
            success=True,
            info_result=UCInfoOutput(success=True, tool=tool_info, source_code="x"),
        )
        assert "ns.test" in _build_summary(r)

    def test_no_specific_result(self):
        r = UniversalConstructorOutput(action="x", success=True)
        assert _build_summary(r) == "Operation completed"


class TestHandleListAction:
    @pytest.mark.anyio
    async def test_list_empty(self):
        mock_registry = MagicMock()
        mock_registry.list_tools.return_value = []
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(MagicMock(), "list")
            assert result.success is True

    @pytest.mark.anyio
    async def test_list_error(self):
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                side_effect=Exception("boom"),
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(MagicMock(), "list")
            assert result.success is False


class TestHandleCallAction:
    @pytest.mark.anyio
    async def test_no_tool_name(self):
        with patch("code_puppy.tools.universal_constructor.get_message_bus"):
            result = await universal_constructor_impl(MagicMock(), "call")
            assert result.success is False
            assert "required" in result.error

    @pytest.mark.anyio
    async def test_tool_not_found(self):
        mock_registry = MagicMock()
        mock_registry.get_tool.return_value = None
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "call", tool_name="x"
            )
            assert "not found" in result.error

    @pytest.mark.anyio
    async def test_tool_disabled(self):
        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_tool.meta.enabled = False
        mock_registry.get_tool.return_value = mock_tool
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "call", tool_name="x"
            )
            assert "disabled" in result.error

    @pytest.mark.anyio
    async def test_call_no_function(self):
        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_tool.meta.enabled = True
        mock_tool.source_path = None
        mock_registry.get_tool.return_value = mock_tool
        mock_registry.get_tool_function.return_value = None
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "call", tool_name="x"
            )
            assert "Could not load" in result.error

    @pytest.mark.anyio
    async def test_call_invalid_json_args(self):
        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_tool.meta.enabled = True
        mock_tool.source_path = None
        mock_registry.get_tool.return_value = mock_tool
        mock_registry.get_tool_function.return_value = lambda: None
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "call", tool_name="x", tool_args="{bad"
            )
            assert "Invalid" in result.error

    @pytest.mark.anyio
    async def test_call_non_dict_args(self):
        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_tool.meta.enabled = True
        mock_tool.source_path = None
        mock_registry.get_tool.return_value = mock_tool
        mock_registry.get_tool_function.return_value = lambda: None
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "call", tool_name="x", tool_args=[1, 2]
            )
            assert "must be a dict" in result.error

    @pytest.mark.anyio
    async def test_call_success(self):
        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_tool.meta.enabled = True
        mock_tool.source_path = None
        mock_registry.get_tool.return_value = mock_tool
        mock_registry.get_tool_function.return_value = lambda: "result"
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "call", tool_name="x"
            )
            assert result.success is True

    @pytest.mark.anyio
    async def test_call_type_error(self):
        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_tool.meta.enabled = True
        mock_tool.source_path = None
        mock_registry.get_tool.return_value = mock_tool

        def bad_func(**kw):
            raise TypeError("wrong args")

        mock_registry.get_tool_function.return_value = bad_func
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "call", tool_name="x"
            )
            assert "Invalid arguments" in result.error

    @pytest.mark.anyio
    async def test_call_generic_exception(self):
        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_tool.meta.enabled = True
        mock_tool.source_path = None
        mock_registry.get_tool.return_value = mock_tool

        def fail_func(**kw):
            raise RuntimeError("boom")

        mock_registry.get_tool_function.return_value = fail_func
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "call", tool_name="x"
            )
            assert "execution failed" in result.error


class TestHandleCreateAction:
    @pytest.mark.anyio
    async def test_no_code(self):
        with patch("code_puppy.tools.universal_constructor.get_message_bus"):
            result = await universal_constructor_impl(
                MagicMock(), "create", python_code=""
            )
            assert "required" in result.error

    @pytest.mark.anyio
    async def test_syntax_error(self):
        with patch("code_puppy.tools.universal_constructor.get_message_bus"):
            result = await universal_constructor_impl(
                MagicMock(), "create", python_code="def f("
            )
            assert "Syntax" in result.error

    @pytest.mark.anyio
    async def test_no_functions(self):
        with patch("code_puppy.tools.universal_constructor.get_message_bus"):
            result = await universal_constructor_impl(
                MagicMock(), "create", python_code="x = 1"
            )
            assert "No functions" in result.error

    @pytest.mark.anyio
    async def test_create_with_tool_name(self, tmp_path):
        code = 'def hello():\n    return "hi"'
        with (
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
            patch("code_puppy.plugins.universal_constructor.USER_UC_DIR", tmp_path),
            patch("code_puppy.plugins.universal_constructor.registry.get_registry"),
        ):
            result = await universal_constructor_impl(
                MagicMock(),
                "create",
                tool_name="hello",
                python_code=code,
                description="test",
            )
            assert result.success is True

    @pytest.mark.anyio
    async def test_create_with_namespace(self, tmp_path):
        code = 'def hello():\n    return "hi"'
        with (
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
            patch("code_puppy.plugins.universal_constructor.USER_UC_DIR", tmp_path),
            patch("code_puppy.plugins.universal_constructor.registry.get_registry"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "create", tool_name="ns.hello", python_code=code
            )
            assert result.success is True

    @pytest.mark.anyio
    async def test_create_with_tool_meta(self, tmp_path):
        code = 'TOOL_META = {"name": "mytool", "description": "test", "enabled": True}\ndef f():\n    pass'
        with (
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
            patch("code_puppy.plugins.universal_constructor.USER_UC_DIR", tmp_path),
            patch("code_puppy.plugins.universal_constructor.registry.get_registry"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "create", python_code=code
            )
            assert result.success is True


class TestHandleUpdateAction:
    @pytest.mark.anyio
    async def test_no_tool_name(self):
        with patch("code_puppy.tools.universal_constructor.get_message_bus"):
            result = await universal_constructor_impl(MagicMock(), "update")
            assert "required" in result.error

    @pytest.mark.anyio
    async def test_no_code(self):
        with patch("code_puppy.tools.universal_constructor.get_message_bus"):
            result = await universal_constructor_impl(
                MagicMock(), "update", tool_name="x"
            )
            assert "required" in result.error

    @pytest.mark.anyio
    async def test_tool_not_found(self):
        mock_registry = MagicMock()
        mock_registry.get_tool.return_value = None
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "update", tool_name="x", python_code="x=1"
            )
            assert "not found" in result.error

    @pytest.mark.anyio
    async def test_no_source_path(self):
        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_tool.source_path = None
        mock_registry.get_tool.return_value = mock_tool
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "update", tool_name="x", python_code="x=1"
            )
            assert result.success is False

    @pytest.mark.anyio
    async def test_update_success(self, tmp_path):
        code = 'TOOL_META = {"name": "x", "description": "test", "enabled": True}\ndef f():\n    pass'
        src = tmp_path / "x.py"
        src.write_text("old")
        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_tool.source_path = str(src)
        mock_registry.get_tool.return_value = mock_tool
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "update", tool_name="x", python_code=code
            )
            assert result.success is True

    @pytest.mark.anyio
    async def test_update_no_meta(self, tmp_path):
        code = "def f():\n    pass"
        src = tmp_path / "x.py"
        src.write_text("old")
        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_tool.source_path = str(src)
        mock_registry.get_tool.return_value = mock_tool
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "update", tool_name="x", python_code=code
            )
            assert "TOOL_META" in result.error

    @pytest.mark.anyio
    async def test_update_syntax_error(self, tmp_path):
        src = tmp_path / "x.py"
        src.write_text("old")
        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_tool.source_path = str(src)
        mock_registry.get_tool.return_value = mock_tool
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "update", tool_name="x", python_code="def f("
            )
            assert "Syntax" in result.error


class TestHandleInfoAction:
    @pytest.mark.anyio
    async def test_no_tool_name(self):
        with patch("code_puppy.tools.universal_constructor.get_message_bus"):
            result = await universal_constructor_impl(MagicMock(), "info")
            assert "required" in result.error

    @pytest.mark.anyio
    async def test_tool_not_found(self):
        mock_registry = MagicMock()
        mock_registry.get_tool.return_value = None
        with (
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
            patch("code_puppy.tools.universal_constructor.get_message_bus"),
        ):
            result = await universal_constructor_impl(
                MagicMock(), "info", tool_name="x"
            )
            assert "not found" in result.error


class TestUnknownAction:
    @pytest.mark.anyio
    async def test_unknown(self):
        with patch("code_puppy.tools.universal_constructor.get_message_bus"):
            result = await universal_constructor_impl(MagicMock(), "unknown")
            assert result.success is False
            assert "Unknown" in result.error
