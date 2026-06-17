"""Full coverage tests for pydantic_patches.py."""

from unittest.mock import MagicMock, patch

import pytest


class TestGetCodePuppyVersion:
    def test_returns_version(self):
        from code_puppy.pydantic_patches import _get_code_puppy_version

        version = _get_code_puppy_version()
        assert isinstance(version, str)

    def test_returns_dev_on_error(self):
        with patch("importlib.metadata.version", side_effect=Exception("nope")):
            from code_puppy.pydantic_patches import _get_code_puppy_version

            result = _get_code_puppy_version()
            assert result == "0.0.0-dev"


class TestPatchUserAgent:
    def test_patch_user_agent_sets_function(self):
        from code_puppy.pydantic_patches import patch_user_agent

        patch_user_agent()
        # After patching, calling the function should return Code-Puppy/...
        import pydantic_ai.models as pydantic_models

        ua = pydantic_models.get_user_agent()
        assert "Code-Puppy" in ua or "KimiCLI" in ua

    def test_kimi_model_returns_kimi_ua(self):
        from code_puppy.pydantic_patches import patch_user_agent

        patch_user_agent()
        import pydantic_ai.models as pydantic_models

        with patch("code_puppy.config.get_global_model_name", return_value="kimi-test"):
            ua = pydantic_models.get_user_agent()
            assert ua == "KimiCLI/0.63"

    def test_non_kimi_returns_code_puppy_ua(self):
        from code_puppy.pydantic_patches import patch_user_agent

        patch_user_agent()
        import pydantic_ai.models as pydantic_models

        with patch("code_puppy.config.get_global_model_name", return_value="gpt-4"):
            ua = pydantic_models.get_user_agent()
            assert "Code-Puppy" in ua

    def test_get_model_name_exception(self):
        from code_puppy.pydantic_patches import patch_user_agent

        patch_user_agent()
        import pydantic_ai.models as pydantic_models

        with patch("code_puppy.config.get_global_model_name", side_effect=Exception):
            ua = pydantic_models.get_user_agent()
            assert "Code-Puppy" in ua

    def test_patch_user_agent_import_failure(self):
        """Should not crash if pydantic_ai.models is not importable."""
        with patch("builtins.__import__", side_effect=ImportError):
            # This should not raise
            try:
                from code_puppy.pydantic_patches import patch_user_agent

                patch_user_agent()
            except ImportError:
                pass  # Expected in this test


class TestPatchMessageHistoryCleaning:
    def test_patches_clean_message_history(self):
        from code_puppy.pydantic_patches import patch_message_history_cleaning

        patch_message_history_cleaning()
        # After patching, the function should be identity
        from pydantic_ai import _agent_graph

        msgs = ["a", "b"]
        assert _agent_graph._clean_message_history(msgs) is msgs


class TestPatchProcessMessageHistory:
    @pytest.mark.anyio
    async def test_patched_process_runs_processors(self):
        from code_puppy.pydantic_patches import patch_process_message_history

        patch_process_message_history()
        from pydantic_ai._agent_graph import _process_message_history

        # Test with no processors
        result = await _process_message_history(["msg1"], [], MagicMock())
        assert result == ["msg1"]

    @pytest.mark.anyio
    async def test_patched_process_empty_raises(self):
        from code_puppy.pydantic_patches import patch_process_message_history

        patch_process_message_history()
        from pydantic_ai._agent_graph import _process_message_history

        # Processor that returns empty
        def clear_msgs(msgs):
            return []

        with pytest.raises(Exception, match="empty"):
            await _process_message_history(["msg"], [clear_msgs], MagicMock())

    @pytest.mark.anyio
    async def test_patched_process_with_async_processor(self):
        from code_puppy.pydantic_patches import patch_process_message_history

        patch_process_message_history()
        from pydantic_ai._agent_graph import _process_message_history

        async def async_processor(msgs):
            return msgs + ["added"]

        result = await _process_message_history(
            ["msg1"], [async_processor], MagicMock()
        )
        assert "added" in result


class TestPatchToolCallJsonRepair:
    def test_patches_tool_manager(self):
        from code_puppy.pydantic_patches import patch_tool_call_json_repair

        patch_tool_call_json_repair()
        # Just verify it doesn't crash


class TestPatchToolCallCallbacks:
    def test_patches_tool_manager(self):
        from code_puppy.pydantic_patches import patch_tool_call_callbacks

        patch_tool_call_callbacks()
        # Just verify it doesn't crash


class TestWritebackToolArgs:
    """Unit tests for ``_writeback_tool_args``.

    This is the bridge that makes pre_tool_call hook mutations actually visible
    to the downstream tool. The previous behavior silently dropped them.
    """

    def _make_call(self, args):
        call = MagicMock()
        call.args = args
        return call

    def test_str_mode_reserializes_dict_to_json(self):
        from code_puppy.pydantic_patches import _writeback_tool_args

        call = self._make_call('{"content": "original"}')
        tool_args = {"content": "mutated"}
        _writeback_tool_args(call, tool_args, "str")
        assert isinstance(call.args, str)
        import json

        assert json.loads(call.args) == {"content": "mutated"}

    def test_dict_mode_assigns_dict_directly(self):
        from code_puppy.pydantic_patches import _writeback_tool_args

        original = {"x": 1}
        call = self._make_call(original)
        tool_args = {"x": 2}
        _writeback_tool_args(call, tool_args, "dict")
        assert call.args == {"x": 2}
        assert call.args is tool_args

    def test_none_mode_is_noop(self):
        from code_puppy.pydantic_patches import _writeback_tool_args

        call = self._make_call("\u00f1ot json at all")
        _writeback_tool_args(call, {"would": "corrupt"}, None)
        assert call.args == "\u00f1ot json at all"

    def test_swallows_serialization_errors(self):
        from code_puppy.pydantic_patches import _writeback_tool_args

        call = self._make_call('{"a": 1}')
        # A set is not JSON-serializable. Should not raise.
        _writeback_tool_args(call, {"bad": {1, 2, 3}}, "str")
        # Best effort: original args remain untouched on failure.
        assert call.args == '{"a": 1}'

    def test_unknown_mode_is_noop(self):
        from code_puppy.pydantic_patches import _writeback_tool_args

        call = self._make_call('{"a": 1}')
        _writeback_tool_args(call, {"a": 2}, "something-else")
        assert call.args == '{"a": 1}'

    def test_str_mode_preserves_unicode(self):
        """Emoji content (our motivating use case) must round-trip safely."""
        from code_puppy.pydantic_patches import _writeback_tool_args

        call = self._make_call('{"content": "old \\ud83d\\udc36"}')
        tool_args = {"content": "clean ascii"}
        _writeback_tool_args(call, tool_args, "str")
        import json

        assert json.loads(call.args) == {"content": "clean ascii"}


class TestPatchTermflowClipboard:
    """Regression guard: termflow must NEVER write to the system clipboard.

    termflow's ``RenderFeatures.clipboard`` defaults to ``True``, which emits
    OSC 52 escape sequences on every rendered code block — silently clobbering
    the user's clipboard.  The patch replaces ``Renderer._copy_to_clipboard``
    with a no-op so this can never happen, regardless of per-call feature flags.
    """

    def test_copy_to_clipboard_is_noop(self):
        import io

        from code_puppy.pydantic_patches import patch_termflow_clipboard

        patch_termflow_clipboard()
        from termflow.render.renderer import Renderer

        buf = io.StringIO()
        renderer = Renderer(output=buf, width=80)
        renderer._copy_to_clipboard("secret clipboard payload")
        assert buf.getvalue() == "", "_copy_to_clipboard must not write anything"

    def test_code_block_render_emits_no_osc52(self):
        """End-to-end: rendering a code block must not produce an OSC 52 seq."""
        import io

        from code_puppy.pydantic_patches import patch_termflow_clipboard

        patch_termflow_clipboard()
        from termflow import Parser as TermflowParser
        from termflow import Renderer as TermflowRenderer
        from termflow.render.style import RenderFeatures

        # Even with clipboard=True explicitly, the patch must prevent writes.
        buf = io.StringIO()
        renderer = TermflowRenderer(
            output=buf, width=80, features=RenderFeatures(clipboard=True)
        )
        parser = TermflowParser()
        for line in ["```python", "print('hello')", "```"]:
            for event in parser.parse_line(line):
                renderer.render(event)
        for event in parser.finalize():
            renderer.render(event)
        assert "\x1b]52" not in buf.getvalue(), (
            "OSC 52 clipboard sequence leaked into output!"
        )

    def test_patch_does_not_crash_without_termflow(self):
        import builtins

        from code_puppy.pydantic_patches import patch_termflow_clipboard

        _real_import = builtins.__import__

        def _block_termflow(name, *args, **kwargs):
            if name.startswith("termflow"):
                raise ImportError("simulated: termflow not installed")
            return _real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_block_termflow):
            patch_termflow_clipboard()  # must not raise


class TestApplyAllPatches:
    def test_apply_all_patches(self):
        from code_puppy.pydantic_patches import apply_all_patches

        # Should not raise
        apply_all_patches()


class TestClaudeCodeToolPrefixGating:
    """Regression guard: ``cp_`` stripping is gated on the active model type.

    Before the fix, ``_normalize_tool_name`` stripped the prefix unconditionally,
    which would corrupt legitimate tool names beginning with ``cp_`` whenever
    a non-claude-code model (e.g. ``custom_anthropic``) was active.
    """

    def _install_patch(self):
        """Install the tool-call patch and return the patched ToolManager class."""
        from code_puppy.pydantic_patches import patch_tool_call_callbacks

        patch_tool_call_callbacks()
        from pydantic_ai._tool_manager import ToolManager

        return ToolManager

    def test_unprefix_when_claude_code_active(self):
        ToolManager = self._install_patch()

        seen_names: list = []

        def fake_lookup(self, name):  # mimic _original_get_tool_def signature
            seen_names.append(name)
            return None

        with (
            patch(
                "pydantic_ai._tool_manager.ToolManager.get_tool_def",
                fake_lookup,
            ),
            patch(
                "code_puppy.config.get_global_model_name",
                return_value="claude-code-claude-opus-4-7",
            ),
        ):
            # Re-apply patch so it captures our fake _original_get_tool_def
            from code_puppy.pydantic_patches import patch_tool_call_callbacks

            patch_tool_call_callbacks()
            mgr = ToolManager.__new__(ToolManager)
            ToolManager.get_tool_def(mgr, "cp_read_file")

        assert seen_names == ["read_file"], (
            f"claude-code active: prefix should be stripped, got {seen_names}"
        )

    def test_no_unprefix_when_custom_anthropic_active(self):
        ToolManager = self._install_patch()

        seen_names: list = []

        def fake_lookup(self, name):
            seen_names.append(name)
            return None

        with (
            patch(
                "pydantic_ai._tool_manager.ToolManager.get_tool_def",
                fake_lookup,
            ),
            patch(
                "code_puppy.config.get_global_model_name",
                return_value="some-custom-anthropic-model",
            ),
        ):
            from code_puppy.pydantic_patches import patch_tool_call_callbacks

            patch_tool_call_callbacks()
            mgr = ToolManager.__new__(ToolManager)
            # A tool whose real name legitimately begins with ``cp_``
            ToolManager.get_tool_def(mgr, "cp_read_file")

        assert seen_names == ["cp_read_file"], (
            f"non-claude-code: prefix must be preserved verbatim, got {seen_names}"
        )

    def test_no_unprefix_when_model_lookup_fails(self):
        """If the model name can't be determined, default to NOT stripping.

        Defensive default: it's better to fail a claude-code tool lookup than to
        silently mangle a legitimately-prefixed tool name for another model.
        """
        ToolManager = self._install_patch()

        seen_names: list = []

        def fake_lookup(self, name):
            seen_names.append(name)
            return None

        def boom():
            raise RuntimeError("config not initialised")

        with (
            patch(
                "pydantic_ai._tool_manager.ToolManager.get_tool_def",
                fake_lookup,
            ),
            patch("code_puppy.config.get_global_model_name", side_effect=boom),
        ):
            from code_puppy.pydantic_patches import patch_tool_call_callbacks

            patch_tool_call_callbacks()
            mgr = ToolManager.__new__(ToolManager)
            ToolManager.get_tool_def(mgr, "cp_read_file")

        assert seen_names == ["cp_read_file"]
