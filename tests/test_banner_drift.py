"""Terminal tool banners must come from the BannerDef that ACP also uses.

Drift cases prove the renderer and list_agents read name and label from
``banners.get_banner_def``. Legacy cases pin the exact pre-contract markup so
terminal output stays byte-identical.
"""

from unittest.mock import MagicMock, Mock

import pytest
from rich.console import Console
from rich.text import Text

from code_puppy import banners, config
from code_puppy.banners import BannerDef, banner_for_call
from code_puppy.messaging.bus import MessageBus
from code_puppy.messaging.messages import (
    AgentReasoningMessage,
    DiffMessage,
    FileContentMessage,
    FileListingMessage,
    GrepResultMessage,
    ShellStartMessage,
    SkillActivateMessage,
    SkillListMessage,
    SubAgentInvocationMessage,
    UniversalConstructorMessage,
)
from code_puppy.messaging import rich_renderer
from code_puppy.messaging.rich_renderer import RichConsoleRenderer
from code_puppy.tools import agent_tools

FILE = "/work/src/app.py"
ROBOT = "\U0001f916 "
SKILL_LIST = SkillListMessage(skills=[], total_count=0, query="pdf")
SKILL_ACTIVATE = SkillActivateMessage(
    skill_name="pdf",
    skill_path="/skills/pdf",
    content_preview="",
    resource_count=0,
)

# (message, renderer method, tool name, tool args, banner prefix)
RENDERED = [
    pytest.param(
        FileContentMessage(path=FILE, content="x", total_lines=1, num_tokens=1),
        "_render_file_content",
        "read_file",
        {"file_path": FILE},
        "",
        id="read_file",
    ),
    pytest.param(
        FileListingMessage(
            directory="/work",
            files=[],
            recursive=False,
            total_size=0,
            dir_count=0,
            file_count=0,
        ),
        "_render_file_listing",
        "list_files",
        {"directory": "/work"},
        "",
        id="list_files",
    ),
    pytest.param(
        GrepResultMessage(
            search_term="needle",
            directory="/work",
            matches=[],
            total_matches=0,
            files_searched=1,
        ),
        "_render_grep_result",
        "grep",
        {"search_string": "needle"},
        "",
        id="grep",
    ),
    pytest.param(
        DiffMessage(path=FILE, operation="create"),
        "_render_diff",
        "create_file",
        {"file_path": FILE},
        "",
        id="create_file",
    ),
    pytest.param(
        DiffMessage(path=FILE, operation="delete"),
        "_render_diff",
        "delete_file",
        {"file_path": FILE},
        "",
        id="delete_file",
    ),
    pytest.param(
        DiffMessage(path=FILE, operation="modify"),
        "_render_diff",
        "replace_in_file",
        {"file_path": FILE},
        "",
        id="replace_in_file",
    ),
    pytest.param(
        ShellStartMessage(command="ls -la"),
        "_render_shell_start",
        "shell",
        {"command": "ls -la"},
        "",
        id="shell",
    ),
    pytest.param(
        AgentReasoningMessage(reasoning="thinking"),
        "_render_agent_reasoning",
        "agent_share_your_reasoning",
        {"reasoning": "thinking"},
        "",
        id="agent_share_your_reasoning",
    ),
    pytest.param(
        SubAgentInvocationMessage(
            agent_name="pack-leader",
            session_id="s1",
            prompt="hi",
            is_new_session=True,
        ),
        "_render_subagent_invocation",
        "invoke_agent",
        {"agent_name": "pack-leader"},
        ROBOT,
        id="invoke_agent",
    ),
    pytest.param(
        UniversalConstructorMessage(action="list", success=True, summary="ok"),
        "_render_universal_constructor",
        "universal_constructor",
        {"action": "list"},
        "",
        id="universal_constructor",
    ),
    pytest.param(
        SKILL_LIST,
        "_render_skill_list",
        "list_or_search_skills",
        {"query": "pdf"},
        "",
        id="list_or_search_skills",
    ),
    pytest.param(
        SKILL_ACTIVATE,
        "_render_skill_activate",
        "activate_skill",
        {"skill_name": "pdf"},
        "",
        id="activate_skill",
    ),
]

# Legacy markup pinned from before the contract, with default colours.
LEGACY_BANNERS = [
    pytest.param(
        FileContentMessage(path=FILE, content="x", total_lines=1, num_tokens=1),
        "_render_file_content",
        "[bold white on steel_blue] READ FILE [/bold white on steel_blue]",
        id="read_file",
    ),
    pytest.param(
        FileListingMessage(
            directory="/work",
            files=[],
            recursive=False,
            total_size=0,
            dir_count=0,
            file_count=0,
        ),
        "_render_file_listing",
        "[bold white on dodger_blue2] DIRECTORY LISTING [/bold white on dodger_blue2]",
        id="list_files",
    ),
    pytest.param(
        GrepResultMessage(
            search_term="needle",
            directory="/work",
            matches=[],
            total_matches=0,
            files_searched=1,
        ),
        "_render_grep_result",
        "[bold white on grey37] GREP [/bold white on grey37]",
        id="grep",
    ),
    pytest.param(
        DiffMessage(path=FILE, operation="create"),
        "_render_diff",
        "[bold white on dark_goldenrod] CREATE FILE [/bold white on dark_goldenrod]",
        id="create_file",
    ),
    pytest.param(
        DiffMessage(path=FILE, operation="delete"),
        "_render_diff",
        "[bold white on blue] DELETE FILE [/bold white on blue]",
        id="delete_file-no-colour-configured",
    ),
    pytest.param(
        DiffMessage(path=FILE, operation="modify"),
        "_render_diff",
        "[bold white on dark_goldenrod] EDIT FILE [/bold white on dark_goldenrod]",
        id="replace_in_file",
    ),
    pytest.param(
        ShellStartMessage(command="ls -la"),
        "_render_shell_start",
        "[bold white on dark_orange3] SHELL COMMAND [/bold white on dark_orange3]",
        id="shell",
    ),
    pytest.param(
        AgentReasoningMessage(reasoning="thinking"),
        "_render_agent_reasoning",
        "[bold white on dark_violet] AGENT REASONING [/bold white on dark_violet]",
        id="agent_share_your_reasoning",
    ),
    pytest.param(
        SubAgentInvocationMessage(
            agent_name="pack-leader",
            session_id="s1",
            prompt="hi",
            is_new_session=True,
        ),
        "_render_subagent_invocation",
        f"[bold white on deep_pink4] {ROBOT}INVOKE AGENT [/bold white on deep_pink4]",
        id="invoke_agent",
    ),
    pytest.param(
        SKILL_LIST,
        "_render_skill_list",
        "[bold white on medium_purple4] LIST SKILLS [/bold white on medium_purple4]",
        id="list_or_search_skills",
    ),
    pytest.param(
        SKILL_ACTIVATE,
        "_render_skill_activate",
        "[bold white on medium_purple4] ACTIVATE SKILL [/bold white on medium_purple4]",
        id="activate_skill",
    ),
]


@pytest.fixture
def banner_colours(monkeypatch):
    """Route ``banner_color_*`` lookups through a dict; everything else stays real.

    Returns the dict so a test can set overrides. Starts empty, so defaults apply.
    """
    real_get_value = config.get_value
    overrides: dict[str, str] = {}

    def fake_get_value(key):
        if key.startswith("banner_color_"):
            return overrides.get(key)
        return real_get_value(key)

    monkeypatch.setattr(config, "get_value", fake_get_value)
    # Listings are hidden by default; these tests pin the banner, not that setting.
    monkeypatch.setattr(rich_renderer, "get_suppress_directory_listing", lambda: False)
    return overrides


def _renderer():
    console = Mock(spec=Console)
    return RichConsoleRenderer(MessageBus(), console=console), console


def _printed(console) -> str:
    return "\n".join(
        call.args[0]
        for call in console.print.call_args_list
        if call.args and isinstance(call.args[0], str)
    )


def _styled(text: Text) -> list[tuple[str, str]]:
    return [(text.plain[span.start : span.end], span.style) for span in text.spans]


def _render(message, method_name: str) -> str:
    renderer, console = _renderer()
    getattr(renderer, method_name)(message)
    return _printed(console)


@pytest.fixture
def list_agents_tool(monkeypatch):
    registered = []

    def decorator(func):
        registered.append(func)
        return func

    agent = MagicMock()
    agent.tool.return_value = decorator
    agent_tools.register_list_agents(agent)

    monkeypatch.setattr(
        "code_puppy.agents.get_available_agents", lambda: {"pack": "Pack"}
    )
    monkeypatch.setattr("code_puppy.agents.get_agent_descriptions", lambda: {})
    emitted = MagicMock()
    monkeypatch.setattr(agent_tools, "emit_info", emitted)
    return registered[0], emitted


@pytest.mark.parametrize(("message", "method", "tool", "args", "prefix"), RENDERED)
def test_renderer_banner_matches_banner_for_call(
    banner_colours, message, method, tool, args, prefix
):
    printed = _render(message, method)

    banner = banner_for_call(tool, args)
    colour = config.get_banner_color(banner.name)
    expected = (
        f"[bold white on {colour}] {prefix}{banner.label} [/bold white on {colour}]"
    )
    assert expected in printed


@pytest.mark.parametrize(("message", "method", "tool", "args", "prefix"), RENDERED)
def test_renderer_reads_name_and_label_from_definition(
    banner_colours, monkeypatch, message, method, tool, args, prefix
):
    probe = BannerDef("probe_key", "PROBE LABEL", "other")
    monkeypatch.setattr(banners, "get_banner_def", lambda _tool_name: probe)
    banner_colours["banner_color_probe_key"] = "magenta"

    printed = _render(message, method)

    assert f"[bold white on magenta] {prefix}PROBE LABEL [/bold white on magenta]" in (
        printed
    )


@pytest.mark.parametrize(("message", "method", "expected"), LEGACY_BANNERS)
def test_legacy_banner_markup_is_byte_identical(
    banner_colours, message, method, expected
):
    assert expected in _render(message, method)


@pytest.mark.parametrize(
    ("message", "method", "colour_key", "colour", "expected"),
    [
        pytest.param(
            FileContentMessage(path=FILE, content="x", total_lines=1, num_tokens=1),
            "_render_file_content",
            "banner_color_read_file",
            "red",
            "[bold white on red] READ FILE [/bold white on red]",
            id="read_file-red",
        ),
        pytest.param(
            DiffMessage(path=FILE, operation="delete"),
            "_render_diff",
            "banner_color_delete_file",
            "green",
            "[bold white on green] DELETE FILE [/bold white on green]",
            id="delete_file-green",
        ),
    ],
)
def test_configured_colour_is_honoured(
    banner_colours, message, method, colour_key, colour, expected
):
    banner_colours[colour_key] = colour

    assert expected in _render(message, method)


def test_list_agents_banner_matches_banner_for_call(banner_colours, list_agents_tool):
    tool, emitted = list_agents_tool

    tool(None)

    text = emitted.call_args.args[0]
    banner = banner_for_call("list_agents", {})
    colour = config.get_banner_color(banner.name)
    assert (f" {banner.label} ", f"bold white on {colour}") in _styled(text)


def test_list_agents_banner_is_byte_identical(banner_colours, list_agents_tool):
    tool, emitted = list_agents_tool

    tool(None)

    text = emitted.call_args.args[0]
    assert (" LIST AGENTS ", "bold white on dark_slate_gray3") in _styled(text)
    assert text.plain.startswith("\n LIST AGENTS  Found 1 agent(s).")


def test_list_agents_reads_name_and_label_from_definition(
    banner_colours, monkeypatch, list_agents_tool
):
    tool, emitted = list_agents_tool
    probe = BannerDef("probe_key", "PROBE LABEL", "other")
    monkeypatch.setattr(banners, "get_banner_def", lambda _tool_name: probe)
    banner_colours["banner_color_probe_key"] = "magenta"

    tool(None)

    text = emitted.call_args.args[0]
    assert (" PROBE LABEL ", "bold white on magenta") in _styled(text)
