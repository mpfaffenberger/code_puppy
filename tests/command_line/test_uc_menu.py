"""Headless tests for the termflow UC tool browser."""

from io import StringIO
from unittest.mock import patch

from code_puppy.command_line import uc_menu
from code_puppy_core_plugins.universal_constructor.models import ToolMeta, UCToolInfo


def make_tool(name="hammer", enabled=True, namespace="shed", source_path=None):
    return UCToolInfo(
        meta=ToolMeta(
            name=name,
            namespace=namespace,
            description=f"The {name} tool.",
            enabled=enabled,
            version="1.0",
            author="Testy",
        ),
        signature=f"{name}(x: int) -> int",
        source_path=source_path or f"/fake/{namespace}/{name}.py",
        function_name=name,
        docstring=f"Does {name} things.",
    )


def scripted_menu(keys):
    def factory(tools, initial_index=0, **kw):
        script = iter(keys.pop(0))
        return uc_menu.build_tools_menu(
            tools,
            initial_index=initial_index,
            key_source=lambda: next(script),
            output=StringIO(),
            size=lambda: (110, 30),
        )

    return factory


class TestToolsMenu:
    def test_enter_returns_tool(self):
        menu = uc_menu.build_tools_menu(
            [make_tool()],
            key_source=iter(["enter"]).__next__,
            output=StringIO(),
            size=lambda: (110, 30),
        )
        result = menu.run()
        assert result.item.value.full_name == "shed.hammer"

    def test_e_and_d_return_action_sentinels(self):
        for key, sentinel in (("e", uc_menu._TOGGLE), ("d", uc_menu._DELETE)):
            menu = uc_menu.build_tools_menu(
                [make_tool()],
                key_source=iter([key]).__next__,
                output=StringIO(),
                size=lambda: (110, 30),
            )
            action, tool = menu.run().item.value
            assert action == sentinel
            assert tool.full_name == "shed.hammer"

    def test_preview_shows_details(self):
        out = StringIO()
        menu = uc_menu.build_tools_menu(
            [make_tool()],
            key_source=iter(["escape"]).__next__,
            output=out,
            size=lambda: (110, 30),
        )
        menu.run()
        assert "TOOL DETAILS" in out.getvalue()


class TestSourceViewer:
    def test_pager_shows_highlighted_source(self, tmp_path):
        source = tmp_path / "tool.py"
        source.write_text("def hammer(x):\n    return x\n")
        tool = make_tool(source_path=str(source))
        out = StringIO()
        uc_menu.view_tool_source(
            tool,
            key_source=iter(["q"]).__next__,
            output=out,
            size=lambda: (100, 30),
        )
        assert "hammer" in out.getvalue()

    def test_pager_shows_read_error(self):
        tool = make_tool()
        out = StringIO()
        with patch.object(
            uc_menu, "_load_source_code", return_value=([], "Could not read source: no")
        ):
            uc_menu.view_tool_source(
                tool,
                key_source=iter(["q"]).__next__,
                output=out,
                size=lambda: (100, 30),
            )
        assert "Could not read source" in out.getvalue()


class TestFlow:
    def test_view_then_exit_returns_tool_name(self):
        viewed = []
        with patch.object(uc_menu, "_get_tool_entries", return_value=[make_tool()]):
            result = uc_menu.run_uc_picker_flow(
                tools_menu_factory=scripted_menu([["enter"], ["escape"]]),
                source_viewer=lambda tool, **kw: viewed.append(tool.full_name),
            )
        assert result == "shed.hammer"
        assert viewed == ["shed.hammer"]

    def test_toggle_action_calls_toggle_and_reopens(self):
        toggled = []
        with patch.object(uc_menu, "_get_tool_entries", return_value=[make_tool()]):
            result = uc_menu.run_uc_picker_flow(
                tools_menu_factory=scripted_menu([["e"], ["escape"]]),
                toggle_tool=lambda tool: toggled.append(tool.full_name) or True,
            )
        assert toggled == ["shed.hammer"]
        assert result is None

    def test_delete_action_calls_delete(self):
        deleted = []
        with patch.object(uc_menu, "_get_tool_entries", return_value=[make_tool()]):
            uc_menu.run_uc_picker_flow(
                tools_menu_factory=scripted_menu([["d"], ["escape"]]),
                delete_tool=lambda tool: deleted.append(tool.full_name) or True,
            )
        assert deleted == ["shed.hammer"]

    def test_cancel_returns_none(self):
        with patch.object(uc_menu, "_get_tool_entries", return_value=[make_tool()]):
            result = uc_menu.run_uc_picker_flow(
                tools_menu_factory=scripted_menu([["escape"]])
            )
        assert result is None
