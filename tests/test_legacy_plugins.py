"""Finding, trusting and running Code Puppy 0.0.x plugins."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from pydantic_ai.exceptions import SkipToolExecution
from pydantic_ai.messages import ToolCallPart
from rich.console import Console

from code_puppy import callbacks, plugins
from code_puppy.compat import tools
from code_puppy.plugins import trust

if TYPE_CHECKING:
    from pydantic_ai import Agent

    from code_puppy.compat.bridge import LegacyPlugins


def write_plugin(folder: Path, name: str, body: str, **extra_files: str) -> Path:
    plugin = folder / name
    plugin.mkdir(parents=True)
    (plugin / "register_callbacks.py").write_text(
        textwrap.dedent(body), encoding="utf-8"
    )
    for file_name, content in extra_files.items():
        (plugin / f"{file_name}.py").write_text(
            textwrap.dedent(content), encoding="utf-8"
        )
    return plugin


REGISTER_STARTUP = """
    from code_puppy.callbacks import register_callback

    def _on_startup():
        return "{tag}"

    register_callback("startup", _on_startup)
"""


@pytest.fixture
def user_plugins(home: Path) -> Path:
    return home / ".code_puppy" / "plugins"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    (root / ".code_puppy" / "plugins").mkdir(parents=True)
    monkeypatch.chdir(root)
    return root


# --- discovery ---------------------------------------------------------------


def test_user_plugin_loads_with_its_own_modules(user_plugins: Path) -> None:
    write_plugin(
        user_plugins,
        "alpha_demo",
        """
        from code_puppy.callbacks import register_callback
        from . import helper
        from alpha_demo.helper import TAG

        register_callback("startup", helper.on_startup)
        """,
        helper="TAG = 'alpha'\ndef on_startup():\n    return TAG\n",
    )
    assert plugins.load_plugin_callbacks()["user"] == ["alpha_demo"]
    (hook,) = callbacks.get_callbacks("startup")
    assert hook() == "alpha" and callbacks.get_callback_owner(hook) == "alpha_demo"


def test_a_broken_plugin_is_contained(user_plugins: Path) -> None:
    write_plugin(
        user_plugins,
        "broken_demo",
        """
        from code_puppy.callbacks import register_callback
        register_callback("startup", print)
        raise RuntimeError("plugin exploded")
        """,
    )
    write_plugin(user_plugins, "fine_demo", REGISTER_STARTUP.format(tag="fine"))
    assert plugins.load_plugin_callbacks()["user"] == ["fine_demo"]
    statuses = {record.name: record for record in plugins.get_plugin_records()}
    assert statuses["broken_demo"].status == "failed"
    assert "plugin exploded" in statuses["broken_demo"].detail
    # The half-registered callback went with it.
    assert [hook() for hook in callbacks.get_callbacks("startup")] == ["fine"]


def test_folders_without_register_callbacks_are_not_plugins(user_plugins: Path) -> None:
    (user_plugins / "native_plugin").mkdir(parents=True)
    (user_plugins / "native_plugin" / "__init__.py").write_text("", encoding="utf-8")
    (user_plugins / "native_file.py").write_text("", encoding="utf-8")
    assert plugins.load_plugin_callbacks()["user"] == []


def test_project_plugins_need_trust(project: Path) -> None:
    folder = project / ".code_puppy" / "plugins"
    path = write_plugin(folder, "repo_demo", REGISTER_STARTUP.format(tag="repo"))

    assert plugins.load_plugin_callbacks()["project"] == []
    assert plugins.get_project_plugin_status() == {"repo_demo": trust.UNTRUSTED}
    assert callbacks.count_callbacks() == 0

    assert trust.trust_plugin(project, "repo_demo", path)
    assert plugins.load_project_plugin_now("repo_demo") is True
    assert "project_plugins.repo_demo.register_callbacks" in sys.modules
    assert [hook() for hook in callbacks.get_callbacks("startup")] == ["repo"]


def test_editing_a_trusted_project_plugin_revokes_it(project: Path) -> None:
    folder = project / ".code_puppy" / "plugins"
    path = write_plugin(folder, "repo_edit", REGISTER_STARTUP.format(tag="v1"))
    trust.trust_plugin(project, "repo_edit", path)
    (path / "register_callbacks.py").write_text(
        "raise SystemExit('pwned')", encoding="utf-8"
    )

    assert plugins.load_plugin_callbacks()["project"] == []
    assert plugins.get_project_plugin_status() == {"repo_edit": trust.CHANGED}
    assert plugins.load_project_plugin_now("repo_edit") is False


def test_trusted_project_plugin_replaces_the_user_one(
    project: Path, user_plugins: Path
) -> None:
    write_plugin(user_plugins, "same_name", REGISTER_STARTUP.format(tag="user"))
    path = write_plugin(
        project / ".code_puppy" / "plugins",
        "same_name",
        REGISTER_STARTUP.format(tag="project"),
    )
    trust.trust_plugin(project, "same_name", path)

    loaded = plugins.load_plugin_callbacks()
    assert loaded["user"] == [] and loaded["project"] == ["same_name"]
    assert [hook() for hook in callbacks.get_callbacks("startup")] == ["project"]


def test_the_retired_core_plugins_distribution_is_skipped(
    monkeypatch: pytest.MonkeyPatch, user_plugins: Path
) -> None:
    write_plugin(user_plugins, "third_party_ep", REGISTER_STARTUP.format(tag="third"))
    monkeypatch.syspath_prepend(str(user_plugins))

    def entry(name: str, value: str, distribution: str) -> SimpleNamespace:
        return SimpleNamespace(
            name=name, value=value, dist=SimpleNamespace(name=distribution)
        )

    def fake_entry_points(*, group: str) -> list[SimpleNamespace]:
        assert group == "code_puppy.plugins"
        return [
            entry(
                "herdr",
                "code_puppy_core_plugins.herdr.register_callbacks",
                "code_puppy_core_plugins",
            ),
            entry("third", "third_party_ep.register_callbacks", "someones-plugin"),
        ]

    monkeypatch.setattr(plugins, "entry_points", fake_entry_points)
    monkeypatch.setattr(plugins, "_load_user", lambda folder, skip: None)
    assert plugins.load_plugin_callbacks()["installed"] == ["third"]
    statuses = {record.name: record.status for record in plugins.get_plugin_records()}
    assert statuses == {"herdr": "retired", "third": "loaded"}


# --- vocabulary --------------------------------------------------------------


def test_tool_calls_are_described_in_0_0_x_terms() -> None:
    assert tools.legacy_tool_name("run_command") == "agent_run_shell_command"
    assert tools.legacy_tool_name("write_file") == "create_file"
    assert tools.legacy_tool_name("read_file") == "read_file"
    assert tools.legacy_tool_args("write_file", {"path": "a.py", "content": "x"}) == {
        "path": "a.py",
        "file_path": "a.py",
        "content": "x",
    }


@pytest.mark.parametrize(
    ("advertised", "name"),
    [
        ("/kennel", "kennel"),
        ("wiggum <prompt>", "wiggum"),
        ("  /my-cmd x", "my-cmd"),
        ("???", None),
    ],
)
def test_command_names_are_read_from_help_entries(
    advertised: str, name: str | None
) -> None:
    assert tools.command_name(advertised) == name


# --- the bridge --------------------------------------------------------------


class Host:
    """The parts of a ``PluginHost`` the bridge uses."""

    def __init__(self) -> None:
        self.output = io.StringIO()
        self.console = Console(file=self.output, force_terminal=False, width=200)
        self.prompts: list[str] = []
        self.default_model_name = "test:model"
        self.session_id = "session-1"

    def submit_prompt(self, text: str) -> None:
        self.prompts.append(text)


@pytest.fixture
def bridge(installed_distribution: None) -> LegacyPlugins:
    from pydantic_ai_pax.plugins import NoSettings

    from code_puppy.compat.bridge import LegacyPlugins

    return LegacyPlugins(Host(), NoSettings())  # type: ignore[arg-type]


def call(tool: str, **args: object) -> dict[str, Any]:
    return {
        "call": ToolCallPart(tool_name=tool, args=args, tool_call_id="call-1"),
        "tool_def": None,
        "args": args,
    }


async def test_commands_come_from_help_entries_and_dispatch(
    bridge: LegacyPlugins,
) -> None:
    seen: list[tuple[str, str]] = []

    def handle(command: str, name: str) -> bool | str | None:
        seen.append((command, name))
        return {"bark": True, "ask": "please explain this repo"}.get(name)

    callbacks.register_callback(
        "custom_command_help", lambda: [("/bark", "Bark"), ("ask <q>", "Ask")]
    )
    callbacks.register_callback("custom_command", handle)

    commands = {command.name: command for command in bridge.get_commands()}
    assert set(commands) == {"puppy-plugins", "bark", "ask"}
    assert await commands["bark"].handler(["loud twice"]) == ""
    assert seen == [("/bark loud twice", "bark")]
    assert await commands["ask"].handler([]) == ""
    assert bridge.host.prompts == ["please explain this repo"]
    assert "no 0.0.x plugin handled" in await bridge._run_command("ghost", [])


async def test_pre_tool_call_guards_see_legacy_names_and_can_block(
    bridge: LegacyPlugins,
) -> None:
    seen: list[tuple[str, dict[str, Any]]] = []

    def guard(
        tool_name: str, tool_args: dict[str, Any], context: object = None
    ) -> dict[str, Any] | None:
        seen.append((tool_name, tool_args))
        if tool_name == "agent_run_shell_command" and "rm -rf" in tool_args["command"]:
            return {"blocked": True, "reason": "no deleting"}
        return None

    callbacks.register_callback("pre_tool_call", guard)
    allowed = await bridge._before_tool(
        None, **call("write_file", path="a.py", content="x")
    )
    assert allowed == {"path": "a.py", "content": "x"}
    assert seen[0] == (
        "create_file",
        {"path": "a.py", "file_path": "a.py", "content": "x"},
    )
    with pytest.raises(SkipToolExecution) as blocked:
        await bridge._before_tool(None, **call("run_command", command="rm -rf /"))
    assert blocked.value.result == "no deleting"


async def test_a_crashing_guard_blocks_only_when_fail_closed(
    bridge: LegacyPlugins,
) -> None:
    def crash(*args: object, **kwargs: object) -> None:
        raise RuntimeError("guard bug")

    callbacks.register_callback("pre_tool_call", crash)
    assert await bridge._before_tool(None, **call("read_file", path="a")) == {
        "path": "a"
    }
    assert "failed in its pre_tool_call hook" in bridge.host.output.getvalue()

    callbacks.clear_callbacks()
    callbacks.register_callback("pre_tool_call", crash, fail_closed=True)
    with pytest.raises(SkipToolExecution):
        await bridge._before_tool(None, **call("read_file", path="a"))


async def test_run_shell_command_hooks_can_block_and_rewrite(
    bridge: LegacyPlugins,
) -> None:
    def rewrite(
        context: object, command: str, cwd: str | None = None, timeout: int = 60
    ) -> dict[str, Any]:
        return (
            {"blocked": True}
            if command == "curl evil"
            else {"rewrite": f"rtk {command}"}
        )

    callbacks.register_callback("run_shell_command", rewrite)
    args = await bridge._before_tool(None, **call("run_command", command="git status"))
    assert args == {"command": "rtk git status"}
    with pytest.raises(SkipToolExecution):
        await bridge._before_tool(None, **call("run_command", command="curl evil"))
    # Not a shell tool: the shell hook is not consulted.
    assert await bridge._before_tool(None, **call("read_file", path="x")) == {
        "path": "x"
    }


async def test_post_tool_call_gets_the_result_and_a_duration(
    bridge: LegacyPlugins,
) -> None:
    seen: list[tuple[Any, ...]] = []
    callbacks.register_callback("post_tool_call", lambda *args: seen.append(args))
    arguments = call("run_command", command="ls")
    await bridge._start_timer(None, **arguments)
    assert await bridge._after_tool(None, **arguments, result="files") == "files"
    name, args, result, duration_ms, context = seen[0]
    assert (name, args, result, context) == (
        "agent_run_shell_command",
        {"command": "ls"},
        "files",
        None,
    )
    assert duration_ms >= 0


def test_capabilities_follow_what_plugins_registered(bridge: LegacyPlugins) -> None:
    assert list(bridge.get_capabilities()) == []

    def register(agent: Agent[Any, Any]) -> None:
        @agent.tool_plain
        def fetch_bone(size: str) -> str:
            """Fetch a bone."""
            return f"{size} bone"

    callbacks.register_callback("pre_tool_call", lambda *a, **k: None)
    callbacks.register_callback("load_prompt", lambda: "Always wag.")
    callbacks.register_callback("load_prompt", lambda: None)
    callbacks.register_callback(
        "register_tools", lambda: [{"name": "fetch_bone", "register_func": register}]
    )

    kinds = [type(capability).__name__ for capability in bridge.get_capabilities()]
    assert kinds == ["Hooks", "Capability", "Toolset"]
    assert bridge._legacy_prompt() == "Always wag."
    toolset = tools.legacy_toolset()
    assert toolset is not None and toolset.defer_loading is True
    assert "fetch_bone" in (toolset.description or "")


async def test_turn_moments_fire_legacy_hooks_and_can_replace_the_prompt(
    bridge: LegacyPlugins,
) -> None:
    from pydantic_ai_pax.plugins import TurnEnd, TurnStart

    log: list[tuple[Any, ...]] = []
    callbacks.register_callback(
        "user_prompt_submit", lambda prompt, session_id=None: f"{prompt} (be brief)"
    )
    callbacks.register_callback(
        "agent_run_start", lambda *args: log.append(("start", *args))
    )
    callbacks.register_callback(
        "agent_run_end", lambda *args, **kwargs: log.append(("end", kwargs["success"]))
    )
    callbacks.register_callback(
        "interactive_turn_end", lambda *args, **kwargs: log.append(("turn_end",))
    )
    callbacks.register_callback(
        "interactive_turn_cancel",
        lambda prompt, **kwargs: log.append(("cancel", prompt)),
    )

    start = TurnStart(text="hi")
    await bridge.on_turn_start(start)
    assert start.text == "hi (be brief)"
    await bridge.on_turn_end(TurnEnd(text="hi", outcome="completed"))
    await bridge.on_turn_end(TurnEnd(text="hi", outcome="cancelled"))
    assert log == [
        ("start", "code-puppy", "test:model", "session-1"),
        ("end", True),
        ("turn_end",),
        ("end", False),
        ("cancel", "hi"),
    ]


def test_manage_command_lists_and_trusts(bridge: LegacyPlugins, project: Path) -> None:
    write_plugin(
        project / ".code_puppy" / "plugins",
        "repo_cmd",
        REGISTER_STARTUP.format(tag="x"),
    )
    assert bridge._manage(["bogus"]).startswith("Usage: /puppy-plugins")
    assert "No project plugin named 'nope'" in bridge._manage(["trust", "nope"])
    assert bridge._manage(["trust", "repo_cmd"]).startswith("Trusted repo_cmd.")
    assert "repo_cmd" in bridge._manage([]) and "loaded" in bridge._manage([])
    assert bridge._manage(["revoke", "repo_cmd"]).startswith("Revoked repo_cmd.")
    assert bridge._manage(["revoke", "repo_cmd"]) == "repo_cmd was not trusted."


# --- end to end ---------------------------------------------------------------

E2E_PLUGIN = """
    import os
    from code_puppy.callbacks import register_callback

    LOG = os.environ["PUP_E2E_LOG"]

    def note(text):
        with open(LOG, "a", encoding="utf-8") as file:
            file.write(text + "\\n")

    def block_everything(tool_name, tool_args, context=None):
        # The test model calls every tool with made-up arguments; none may run.
        return {"blocked": True, "reason": "blocked by the e2e guard"}

    register_callback("startup", lambda: note("startup"))
    register_callback("user_prompt_submit", lambda prompt, session_id=None: note("prompt"))
    register_callback("agent_run_start", lambda *a: note("run_start:" + a[0]))
    register_callback("agent_run_end", lambda *a, **k: note("run_end"))
    register_callback("pre_tool_call", block_everything, fail_closed=True)
    register_callback("shutdown", lambda: note("shutdown"))
    register_callback("stream_event", lambda *a, **k: note("never"))
"""


def test_a_real_session_runs_a_0_0_x_plugin(home: Path, tmp_path: Path) -> None:
    """The stock agent, through the real CLI, loads a 0.0.x plugin and fires its hooks.

    Only the hooks are asserted, not the turn's outcome: on Windows the runtime
    has no local workspace yet, so the stock agent's turn fails after the
    plugin's hooks have run.
    """
    write_plugin(home / ".code_puppy" / "plugins", "e2e_demo", E2E_PLUGIN)
    work = tmp_path / "work"
    work.mkdir()
    log = tmp_path / "hooks.log"
    env = {**os.environ, "CODE_PUPPY_NO_SPLASH": "1", "PUP_E2E_LOG": str(log)}
    subprocess.run(
        [sys.executable, "-m", "code_puppy", "-m", "test", "-p", "say hi"],
        capture_output=True,
        text=True,
        env=env,
        cwd=work,
        timeout=180,
        check=False,
    )
    assert log.read_text(encoding="utf-8").split() == [
        "startup",
        "prompt",
        "run_start:code-puppy",
        "run_end",
        "shutdown",
    ]
