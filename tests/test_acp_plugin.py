"""Tests for the ACP (ACP native agent) plugin, built on the official SDK.

The plugin implements the ``acp`` SDK's ``Agent`` interface, so these tests
drive ``CodePuppyAgent`` directly and assert on the SDK model objects it emits
through a fake ``AgentSideConnection``. No real stdio is bound.

Coverage:
  * capability negotiation + client-cap parsing
  * prompt content-block flattening (incl. embedded resources)
  * agent lifecycle: initialize / new_session / prompt (stream + fallback) /
    cancel / list_sessions / close_session / unknown-session error
  * tool-call event bridging + correlation (via run-context ``state``)
  * permission delegation (file approval backend + shell hook)
  * I/O delegation core seams + client-backed fs/terminal backends
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, List, Optional, Tuple

import pytest
import pytest_asyncio

from acp.schema import (
    AllowedOutcome,
    ClientCapabilities,
    CreateTerminalResponse,
    DeniedOutcome,
    FileSystemCapabilities,
    ReadTextFileResponse,
    RequestPermissionResponse,
    TerminalExitStatus,
    TerminalOutputResponse,
    WaitForTerminalExitResponse,
)

from code_puppy.plugins.acp import (
    bridge as bridge_mod,
    capabilities,
    content,
    io_delegation,
    permissions,
    state,
)
from code_puppy.plugins.acp.agent import CodePuppyAgent


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeConnection:
    """Stands in for the SDK's ``AgentSideConnection`` (client handle)."""

    def __init__(self, permission_outcome: Any = None) -> None:
        self.updates: List[Tuple[str, Any]] = []
        self.perm_requests: List[Any] = []
        self.writes: List[Tuple[str, str]] = []
        self.released = False
        self.created: Optional[Tuple[str, list, Any]] = None
        self._permission_outcome = permission_outcome

    async def session_update(self, session_id: str, update: Any) -> None:
        self.updates.append((session_id, update))

    async def request_permission(self, options, session_id, tool_call):
        self.perm_requests.append((session_id, tool_call))
        return RequestPermissionResponse(outcome=self._permission_outcome)

    async def read_text_file(self, path, session_id, **_):
        return ReadTextFileResponse(content=f"contents of {path}")

    async def write_text_file(self, content, path, session_id, **_):
        self.writes.append((path, content))

    async def create_terminal(self, command, session_id, args=None, cwd=None, **_):
        self.created = (command, args, cwd)
        return CreateTerminalResponse(terminal_id="term1")

    async def wait_for_terminal_exit(self, session_id, terminal_id, **_):
        return WaitForTerminalExitResponse(exit_code=0)

    async def terminal_output(self, session_id, terminal_id, **_):
        return TerminalOutputResponse(
            output="hi there\n",
            exit_status=TerminalExitStatus(exit_code=0),
            truncated=False,
        )

    async def kill_terminal(self, session_id, terminal_id, **_):
        return None

    async def release_terminal(self, session_id, terminal_id, **_):
        self.released = True
        return None


class FakeAgent:
    """Minimal ``BaseAgent`` stand-in that streams via the real hooks."""

    def __init__(self, stream: bool) -> None:
        self._message_history: List[Any] = []
        self._stream = stream

    def get_message_history(self) -> List[Any]:
        return self._message_history

    def set_message_history(self, history: List[Any]) -> None:
        self._message_history = list(history)

    async def run_with_mcp(self, prompt: str, **_: Any) -> Any:
        if self._stream:
            from code_puppy import callbacks

            delta = SimpleNamespace(content_delta="Hello ")
            await callbacks.on_stream_event(
                "part_delta", {"delta_type": "TextPartDelta", "delta": delta}
            )
        usage = SimpleNamespace(input_tokens=12, output_tokens=8, total_tokens=20)
        return SimpleNamespace(output="Hello puppy", usage=lambda: usage)


def _update_types(conn: FakeConnection) -> List[str]:
    return [getattr(u, "session_update", None) for _, u in conn.updates]


@pytest_asyncio.fixture
async def wired_agent(monkeypatch):
    """A ``CodePuppyAgent`` connected to a fake connection, with cleanup.

    Async so ``on_connect`` runs *inside* the test's event loop — exactly like
    production (the SDK calls it from within ``run_agent``), so
    ``asyncio.get_running_loop()`` succeeds.
    """
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_current_agent_name", lambda: "code-puppy"
    )
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.load_agent",
        lambda name: FakeAgent(stream=True),
    )
    conn = FakeConnection()
    agent = CodePuppyAgent()
    agent.on_connect(conn)
    yield agent, conn
    permissions.uninstall()
    io_delegation.uninstall()
    state.set_connection(None, None)


# --------------------------------------------------------------------------- #
# Capabilities
# --------------------------------------------------------------------------- #
def test_agent_capabilities_shape():
    caps = capabilities.agent_capabilities()
    assert caps.load_session is True
    assert caps.prompt_capabilities.embedded_context is True
    assert caps.prompt_capabilities.image is True
    # list/close/fork/resume/additional_directories all advertised via markers.
    assert caps.session_capabilities.list is not None
    assert caps.session_capabilities.close is not None
    assert caps.session_capabilities.fork is not None
    assert caps.session_capabilities.resume is not None
    assert caps.session_capabilities.additional_directories is not None


def test_client_io_caps_parsing():
    assert capabilities.client_io_caps(None) == (False, False, False)
    caps = ClientCapabilities(
        fs=FileSystemCapabilities(read_text_file=True, write_text_file=False),
        terminal=True,
    )
    assert capabilities.client_io_caps(caps) == (True, False, True)


# --------------------------------------------------------------------------- #
# Content flattening
# --------------------------------------------------------------------------- #
def test_flatten_prompt_text_and_embedded_resource():
    from acp.helpers import embedded_text_resource, resource_block, text_block

    blocks = [
        text_block("do the thing"),
        resource_block(embedded_text_resource("file:///a.py", "print(1)")),
        SimpleNamespace(type="resource_link", uri="file:///b.py", name="b.py"),
    ]
    out = content.flatten_prompt(blocks)
    assert "do the thing" in out
    assert "print(1)" in out
    assert "file:///a.py" in out
    assert "b.py" in out


def test_flatten_prompt_empty():
    assert content.flatten_prompt([]) == ""


# --------------------------------------------------------------------------- #
# Agent lifecycle
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_initialize_returns_versioned_capabilities(wired_agent):
    agent, _ = wired_agent
    resp = await agent.initialize(protocol_version=1, client_capabilities=None)
    assert resp.protocol_version == 1
    assert resp.agent_info.name == "code-puppy"
    assert resp.agent_capabilities.load_session is True


@pytest.mark.asyncio
async def test_new_session_and_prompt_streams(wired_agent):
    agent, conn = wired_agent
    new = await agent.new_session(cwd="/tmp")
    assert new.session_id in agent._sessions
    assert agent._sessions[new.session_id].cwd == "/tmp"

    resp = await agent.prompt([SimpleNamespace(type="text", text="hi")], new.session_id)
    assert resp.stop_reason == "end_turn"
    # Exactly one agent_message_chunk from streaming; no duplicate final chunk.
    assert _update_types(conn).count("agent_message_chunk") == 1


@pytest.mark.asyncio
async def test_prompt_absorbs_history_for_memory_and_persistence(monkeypatch):
    """A completed turn must fold result.all_messages() back into the agent.

    The shared runtime does not do this on the normal path -- the caller must,
    like cli_runner does. Without it the agent forgets every turn and
    persistence saves only the user's prompt (no assistant reply), which is
    what made ACP sessions reload with no history and no memory.
    """
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        UserPromptPart,
    )

    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_current_agent_name", lambda: "code-puppy"
    )

    class MemAgent:
        def __init__(self):
            self._h = []

        def get_message_history(self):
            return self._h

        def set_message_history(self, h):
            self._h = list(h)

        def estimate_tokens_for_message(self, _m):
            return 1

        async def run_with_mcp(self, prompt, **_):
            new = list(self._h) + [
                ModelRequest(parts=[UserPromptPart(content=prompt)]),
                ModelResponse(parts=[TextPart(content=f"reply:{prompt}")]),
            ]
            return SimpleNamespace(
                all_messages=lambda: new, usage=lambda: None, output="reply"
            )

    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.load_agent", lambda name: MemAgent()
    )
    conn = FakeConnection()
    agent = CodePuppyAgent()
    agent.on_connect(conn)
    try:
        new = await agent.new_session(cwd="/tmp")
        sid = new.session_id
        await agent.prompt([SimpleNamespace(type="text", text="one")], sid)
        # Turn 1 folded request + response into the agent's memory.
        assert len(agent._sessions[sid].agent.get_message_history()) == 2
        await agent.prompt([SimpleNamespace(type="text", text="two")], sid)
        # Turn 2 remembered turn 1 (grew, didn't reset).
        assert len(agent._sessions[sid].agent.get_message_history()) == 4
    finally:
        permissions.uninstall()
        io_delegation.uninstall()
        state.set_connection(None, None)


@pytest.mark.asyncio
async def test_stream_part_start_content_not_dropped(wired_agent):
    """The opening chunk (carried on part_start) must reach the client.

    pydantic-ai often front-loads the first token(s) into the PartStartEvent's
    ``part.content`` rather than the first delta. Forwarding only part_delta
    truncates the start of every message (the reported bug). Start + deltas are
    disjoint, so both are emitted and reconstruct the full text.
    """
    from code_puppy.plugins.acp.bridge import EventBridge

    agent, conn = wired_agent
    state.begin_run("sess_stream")
    try:
        bridge = EventBridge()
        await bridge._on_stream_event(
            "part_start",
            {
                "index": 0,
                "part_type": "TextPart",
                "part": SimpleNamespace(content="Hello "),
            },
        )
        await bridge._on_stream_event(
            "part_delta",
            {
                "index": 0,
                "delta_type": "TextPartDelta",
                "delta": SimpleNamespace(content_delta="world"),
            },
        )
    finally:
        state.end_run()
    texts = [
        getattr(getattr(u, "content", None), "text", None)
        for _, u in conn.updates
        if getattr(u, "session_update", None) == "agent_message_chunk"
    ]
    assert "".join(t for t in texts if t) == "Hello world"


@pytest.mark.asyncio
async def test_prompt_reports_token_usage(wired_agent):
    agent, _ = wired_agent
    new = await agent.new_session(cwd="/tmp")
    resp = await agent.prompt([SimpleNamespace(type="text", text="hi")], new.session_id)
    assert resp.usage is not None
    assert resp.usage.input_tokens == 12
    assert resp.usage.output_tokens == 8
    assert resp.usage.total_tokens == 20


@pytest.mark.asyncio
async def test_prompt_final_fallback_when_no_stream(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_current_agent_name", lambda: "code-puppy"
    )
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.load_agent",
        lambda name: FakeAgent(stream=False),
    )
    conn = FakeConnection()
    agent = CodePuppyAgent()
    agent.on_connect(conn)
    try:
        new = await agent.new_session(cwd="/tmp")
        await agent.prompt([SimpleNamespace(type="text", text="hi")], new.session_id)
        chunks = [
            u
            for sid, u in conn.updates
            if getattr(u, "session_update", None) == "agent_message_chunk"
        ]
        assert len(chunks) == 1
        assert chunks[0].content.text == "Hello puppy"
    finally:
        permissions.uninstall()
        io_delegation.uninstall()
        state.set_connection(None, None)


@pytest.mark.asyncio
async def test_prompt_unknown_session_raises(wired_agent):
    agent, _ = wired_agent
    with pytest.raises(ValueError):
        await agent.prompt([], "nope")


@pytest.mark.asyncio
async def test_list_and_close_session(wired_agent):
    agent, _ = wired_agent
    a = await agent.new_session(cwd="/one")
    b = await agent.new_session(cwd="/two")
    listed = await agent.list_sessions()
    ids = {s.session_id for s in listed.sessions}
    assert {a.session_id, b.session_id} <= ids

    await agent.close_session(a.session_id)
    assert a.session_id not in agent._sessions


@pytest.mark.asyncio
async def test_cancel_stops_run(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_current_agent_name", lambda: "code-puppy"
    )

    class SlowAgent:
        _message_history: list = []

        async def run_with_mcp(self, prompt, **_):
            await asyncio.sleep(30)
            return SimpleNamespace(output="never")

    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.load_agent", lambda name: SlowAgent()
    )
    conn = FakeConnection()
    agent = CodePuppyAgent()
    agent.on_connect(conn)
    try:
        new = await agent.new_session(cwd="/tmp")
        task = asyncio.ensure_future(
            agent.prompt([SimpleNamespace(type="text", text="go")], new.session_id)
        )
        await asyncio.sleep(0.05)
        await agent.cancel(new.session_id)
        resp = await task
        assert resp.stop_reason == "cancelled"
    finally:
        permissions.uninstall()
        io_delegation.uninstall()
        state.set_connection(None, None)


# --------------------------------------------------------------------------- #
# Event bridge — tool-call correlation
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_tool_call_kind_locations_and_correlation():
    conn = FakeConnection()
    state.set_connection(conn, asyncio.get_event_loop())
    state.begin_run("s1")
    bridge = bridge_mod.EventBridge()
    try:
        await bridge._on_pre_tool_call("edit_file", {"file_path": "foo.py"})
        _, start = conn.updates[-1]
        assert start.session_update == "tool_call"
        assert start.kind == "edit"
        assert start.title == "Edit foo.py"
        assert start.locations[0].path.endswith("foo.py")

        name, tool_call_id = state.current_tool_call()
        assert name == "edit_file"
        assert start.tool_call_id == tool_call_id

        await bridge._on_post_tool_call(
            "edit_file", {}, {"success": True, "diff": "- old\n+ new\n"}, 1.0
        )
        _, done = conn.updates[-1]
        assert done.session_update == "tool_call_update"
        assert done.status == "completed"
        assert done.tool_call_id == tool_call_id
        # Unified diff surfaced as an inline content block.
        assert done.content and "old" in done.content[0].content.text
        assert state.current_tool_call() is None
    finally:
        state.end_run()
        state.set_connection(None, None)


# --------------------------------------------------------------------------- #
# Approval-backend seam (core: tools.common)
# --------------------------------------------------------------------------- #
def test_approval_backend_sync_overrides_stdin():
    from code_puppy.tools import common

    seen = []

    def backend(title, message, preview):
        seen.append((title, message, preview))
        return True, None

    common.set_approval_backend(backend)
    try:
        approved, feedback = common.get_user_approval("Op", "do it?", preview="diff")
    finally:
        common.set_approval_backend(None)

    assert approved is True and feedback is None
    assert seen == [("Op", "do it?", "diff")]


@pytest.mark.asyncio
async def test_approval_backend_async_runs_in_executor():
    from code_puppy.tools import common

    def backend(title, message, preview):
        return False, None

    common.set_approval_backend(backend)
    try:
        approved, _ = await common.get_user_approval_async("Op", "do it?")
    finally:
        common.set_approval_backend(None)
    assert approved is False


# --------------------------------------------------------------------------- #
# Permission delegation to the client
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_ask_client_allow_and_deny():
    loop = asyncio.get_event_loop()

    allow = FakeConnection(AllowedOutcome(option_id="allow_once", outcome="selected"))
    state.set_connection(allow, loop)
    state.begin_run("s1")
    try:
        assert await permissions._ask_client("s1", "t") is True
    finally:
        state.end_run()

    deny = FakeConnection(DeniedOutcome(outcome="cancelled"))
    state.set_connection(deny, loop)
    state.begin_run("s1")
    try:
        assert await permissions._ask_client("s1", "t") is False
    finally:
        state.end_run()
        state.set_connection(None, None)


@pytest.mark.asyncio
async def test_shell_hook_gates_through_client(monkeypatch):
    # The client-dialog edge only applies in non-yolo mode (yolo defaults ON).
    monkeypatch.setattr("code_puppy.config.get_yolo_mode", lambda: False)
    loop = asyncio.get_event_loop()

    deny = FakeConnection(DeniedOutcome(outcome="cancelled"))
    state.set_connection(deny, loop)
    state.begin_run("s1")
    try:
        blocked = await permissions._on_run_shell_command(None, "rm -rf /", None, 60)
    finally:
        state.end_run()
    assert blocked["blocked"] is True

    allow = FakeConnection(AllowedOutcome(option_id="allow_once", outcome="selected"))
    state.set_connection(allow, loop)
    state.begin_run("s1")
    try:
        ok = await permissions._on_run_shell_command(None, "ls", None, 60)
    finally:
        state.end_run()
        state.set_connection(None, None)
    assert ok is None


@pytest.mark.asyncio
async def test_shell_hook_yolo_mode_does_not_prompt(monkeypatch):
    """In yolo mode the shell hook auto-allows without a client dialog.

    Matches the file-permission edge (which skips its prompt in yolo mode), so
    ACP + yolo doesn't silently auto-approve writes yet prompt for every shell.
    """
    monkeypatch.setattr("code_puppy.config.get_yolo_mode", lambda: True)
    # A connection that would DENY if asked -- proves we never ask.
    deny = FakeConnection(DeniedOutcome(outcome="cancelled"))
    state.set_connection(deny, asyncio.get_event_loop())
    state.begin_run("s1")
    try:
        result = await permissions._on_run_shell_command(None, "rm -rf /", None, 60)
    finally:
        state.end_run()
        state.set_connection(None, None)
    assert result is None  # allowed
    assert deny.perm_requests == []  # dialog never shown


@pytest.mark.asyncio
async def test_shell_hook_inert_without_connection():
    assert await permissions._on_run_shell_command(None, "ls", None, 60) is None


@pytest.mark.asyncio
async def test_file_approval_bridges_worker_thread_to_client():
    """Sync approval backend (from a tool thread) reaches the client via the ACP loop
    and gets an answer — the deadlock-prone path.
    """
    loop = asyncio.get_event_loop()
    conn = FakeConnection(AllowedOutcome(option_id="allow_once", outcome="selected"))
    state.set_connection(conn, loop)
    state.begin_run("s1")
    try:
        approved, feedback = await asyncio.to_thread(
            permissions._approval_backend, "Edit foo.py", "write?", "diff"
        )
    finally:
        state.end_run()
        state.set_connection(None, None)
    assert approved is True and feedback is None
    assert conn.perm_requests


# --------------------------------------------------------------------------- #
# I/O delegation — core seams
# --------------------------------------------------------------------------- #
def test_write_project_file_delegates_then_falls_back(tmp_path):
    from code_puppy.tools import common, io_backends

    writes = []

    class _FS:
        def read_text_file(self, path, line=None, limit=None):
            return ""

        def write_text_file(self, path, content):
            writes.append((path, content))

    io_backends.set_filesystem_backend(_FS())
    try:
        common.write_project_file("/somewhere/x.txt", "delegated")
    finally:
        io_backends.set_filesystem_backend(None)
    assert writes == [("/somewhere/x.txt", "delegated")]

    local = tmp_path / "y.txt"
    common.write_project_file(str(local), "local")
    assert local.read_text() == "local"


def test_read_file_uses_backend_with_slicing():
    from code_puppy.tools import io_backends
    from code_puppy.tools.file_operations import _read_file

    class _FS:
        def read_text_file(self, path, line=None, limit=None):
            lines = ["line1\n", "line2\n", "line3\n"]
            if line is not None and limit is not None:
                return "".join(lines[line - 1 : line - 1 + limit])
            return "".join(lines)

        def write_text_file(self, path, content):
            pass

    io_backends.set_filesystem_backend(_FS())
    try:
        full = _read_file(None, "/virtual/foo.py")
        sliced = _read_file(None, "/virtual/foo.py", start_line=2, num_lines=1)
    finally:
        io_backends.set_filesystem_backend(None)

    assert "line2" in full.content
    assert sliced.content.strip() == "line2"


# --------------------------------------------------------------------------- #
# I/O delegation — client-delegated backends (capability-gated)
# --------------------------------------------------------------------------- #
def test_io_delegation_install_is_capability_gated():
    from code_puppy.tools import io_backends

    io_delegation.install(ClientCapabilities())
    assert io_backends.get_filesystem_backend() is None
    assert io_backends.get_command_executor() is None

    io_delegation.install(
        ClientCapabilities(
            fs=FileSystemCapabilities(read_text_file=True, write_text_file=True)
        )
    )
    assert io_backends.get_filesystem_backend() is not None
    assert io_backends.get_command_executor() is None

    io_delegation.install(ClientCapabilities(terminal=True))
    assert io_backends.get_command_executor() is not None

    io_delegation.uninstall()
    assert io_backends.get_filesystem_backend() is None
    assert io_backends.get_command_executor() is None


@pytest.mark.asyncio
async def test_command_executor_runs_through_terminal():
    conn = FakeConnection()
    state.set_connection(conn, asyncio.get_event_loop())
    state.begin_run("s1")
    try:
        result = await io_delegation.DelegatedCommandExecutor().run(
            "echo hi", "/tmp", 60
        )
    finally:
        state.end_run()
        state.set_connection(None, None)

    assert result.exit_code == 0
    assert "hi there" in result.output
    assert result.timed_out is False
    assert conn.released is True
    assert conn.created[1] in (["-c", "echo hi"], ["/c", "echo hi"])


@pytest.mark.asyncio
async def test_fs_backend_read_bridges_worker_thread():
    conn = FakeConnection()
    state.set_connection(conn, asyncio.get_event_loop())
    state.begin_run("s1")
    try:
        backend = io_delegation.DelegatedFileSystemBackend()
        content_out = await asyncio.to_thread(backend.read_text_file, "/proj/a.py")
    finally:
        state.end_run()
        state.set_connection(None, None)
    assert content_out == "contents of /proj/a.py"


# --------------------------------------------------------------------------- #
# Gap-closing features: fork / persistence / extra-dirs / commands / images /
# mcp / models / config options
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_fork_session_copies_history(wired_agent):
    agent, _ = wired_agent
    src = await agent.new_session(cwd="/tmp")
    agent._sessions[src.session_id].agent.set_message_history(["turn-1", "turn-2"])
    forked = await agent.fork_session(cwd="/tmp", session_id=src.session_id)
    assert forked.session_id != src.session_id
    assert agent._sessions[forked.session_id].agent.get_message_history() == [
        "turn-1",
        "turn-2",
    ]


@pytest.mark.asyncio
async def test_load_session_rehydrates_history(wired_agent, monkeypatch):
    agent, _ = wired_agent
    monkeypatch.setattr(
        "code_puppy.plugins.acp.persistence.load_history",
        lambda sid: ["persisted-a", "persisted-b"],
    )
    await agent.load_session(cwd="/tmp", session_id="sess_restored")
    hist = agent._sessions["sess_restored"].agent.get_message_history()
    assert hist == ["persisted-a", "persisted-b"]


@pytest.mark.asyncio
async def test_load_session_replays_history_to_client(wired_agent, monkeypatch):
    """session/load must stream the conversation back so the client rebuilds it.

    Rehydrating the agent's memory is not enough: without replayed
    ``session/update`` notifications the client shows (and may discard) an
    empty thread -- the reported "click a session, it disappears, no history".
    """
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        UserPromptPart,
    )

    agent, conn = wired_agent
    history = [
        ModelRequest(parts=[UserPromptPart(content="hello")]),
        ModelResponse(parts=[TextPart(content="hi there")]),
    ]
    monkeypatch.setattr(
        "code_puppy.plugins.acp.persistence.load_history", lambda sid: history
    )
    await agent.load_session(cwd="/tmp", session_id="sess_replay")
    kinds = [getattr(u, "session_update", None) for _, u in conn.updates]
    assert "user_message_chunk" in kinds
    assert "agent_message_chunk" in kinds
    # Ordering: the user turn is replayed before the agent's reply.
    assert kinds.index("user_message_chunk") < kinds.index("agent_message_chunk")


@pytest.mark.asyncio
async def test_additional_directories_reported(wired_agent):
    agent, _ = wired_agent
    await agent.new_session(cwd="/root", additional_directories=["/extra"])
    listed = await agent.list_sessions()
    assert any(s.additional_directories == ["/extra"] for s in listed.sessions)


@pytest.mark.asyncio
async def test_list_sessions_includes_persisted_after_restart(wired_agent, monkeypatch):
    """A session persisted by a prior process must still be listable + revivable.

    Simulates the reported bug: nothing live in ``_sessions`` (fresh process),
    but a session pickled to disk. ``list_sessions`` must surface it (with the
    required ``cwd``) so the client's picker can revive it.
    """
    from code_puppy.plugins.acp import persistence

    agent, _ = wired_agent
    monkeypatch.setattr(
        persistence,
        "list_persisted",
        lambda: [
            persistence.PersistedSession(
                session_id="sess_ghost",
                cwd="/proj",
                additional_directories=["/extra"],
                updated_at="2026-01-01T00:00:00",
            )
        ],
    )
    listed = await agent.list_sessions()
    ghost = next(s for s in listed.sessions if s.session_id == "sess_ghost")
    assert ghost.cwd == "/proj"
    assert ghost.additional_directories == ["/extra"]


@pytest.mark.asyncio
async def test_list_sessions_live_wins_over_persisted(wired_agent, monkeypatch):
    """A live session and its on-disk copy must dedupe to a single entry."""
    from code_puppy.plugins.acp import persistence

    agent, _ = wired_agent
    live = await agent.new_session(cwd="/live")
    monkeypatch.setattr(
        persistence,
        "list_persisted",
        lambda: [
            persistence.PersistedSession(session_id=live.session_id, cwd="/stale")
        ],
    )
    listed = await agent.list_sessions()
    matches = [s for s in listed.sessions if s.session_id == live.session_id]
    assert len(matches) == 1
    assert matches[0].cwd == "/live"


@pytest.mark.asyncio
async def test_close_session_deletes_persisted(wired_agent, monkeypatch):
    """Closing a session tombstones its disk copy so it can't resurrect."""
    from code_puppy.plugins.acp import persistence

    agent, _ = wired_agent
    deleted: list = []
    monkeypatch.setattr(persistence, "delete", lambda sid: deleted.append(sid))
    new = await agent.new_session(cwd="/tmp")
    await agent.close_session(new.session_id)
    assert deleted == [new.session_id]


def test_persistence_roundtrip_lists_and_deletes(tmp_path):
    """``list_persisted`` finds real sessions; ``delete`` removes them.

    Fully hermetic and deterministic: the on-disk state (pickle + ACP sidecar)
    is written directly into an injected ``base_dir``, so this exercises the
    code under test (glob sidecars, require the pickle, parse, delete) without
    depending on the ``session_storage`` save path, the process environment, or
    any global location -- it can neither be perturbed by nor perturb other
    tests.
    """
    import json
    import pickle

    from code_puppy.plugins.acp import persistence

    # A complete session: pickle + sidecar (what list_persisted keys on).
    (tmp_path / "sess_x.pkl").write_bytes(pickle.dumps(["turn-1"]))
    (tmp_path / "sess_x_acp.json").write_text(
        json.dumps(
            {
                "session_id": "sess_x",
                "cwd": "/work",
                "additional_directories": ["/aux"],
                "updated_at": "2026-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    records = persistence.list_persisted(base_dir=tmp_path)
    assert len(records) == 1
    assert records[0].session_id == "sess_x"
    assert records[0].cwd == "/work"
    assert records[0].additional_directories == ["/aux"]

    # A sidecar whose pickle vanished is skipped -- nothing left to rehydrate.
    (tmp_path / "sess_orphan_acp.json").write_text(
        json.dumps({"session_id": "sess_orphan", "cwd": "/o"}), encoding="utf-8"
    )
    assert {r.session_id for r in persistence.list_persisted(base_dir=tmp_path)} == {
        "sess_x"
    }

    persistence.delete("sess_x", base_dir=tmp_path)
    assert persistence.list_persisted(base_dir=tmp_path) == []


def test_persistence_save_writes_listable_session(tmp_path):
    """``save`` writes a pickle + sidecar that ``list_persisted`` then surfaces.

    Covers the write path end-to-end against an injected ``base_dir`` (no
    globals). Kept separate from the list/delete unit test so a failure points
    at the right half.
    """
    from code_puppy.plugins.acp import persistence

    class _Agent:
        def get_message_history(self):
            return ["turn-1"]

    persistence.save(
        "sess_saved",
        _Agent(),
        cwd="/work",
        additional_directories=["/aux"],
        base_dir=tmp_path,
    )
    assert (tmp_path / "sess_saved.pkl").exists()
    assert (tmp_path / "sess_saved_acp.json").exists()
    records = persistence.list_persisted(base_dir=tmp_path)
    assert [r.session_id for r in records] == ["sess_saved"]
    assert records[0].cwd == "/work"


@pytest.mark.asyncio
async def test_slash_command_handled_not_modelled(wired_agent, monkeypatch):
    """A handled command (handler returns True) is routed, not sent to the model."""
    agent, conn = wired_agent
    new = await agent.new_session(cwd="/tmp")

    calls = {}

    def fake_handle(cmd):
        calls["cmd"] = cmd
        return True  # handled; nothing to feed the model

    monkeypatch.setattr(
        "code_puppy.command_line.command_handler.handle_command", fake_handle
    )
    resp = await agent.prompt(
        [SimpleNamespace(type="text", text="/help")], new.session_id
    )
    assert resp.stop_reason == "end_turn"
    assert calls["cmd"] == "/help"
    texts = [
        u.content.text
        for _, u in conn.updates
        if getattr(u, "session_update", None) == "agent_message_chunk"
    ]
    # The command ran; the model did NOT (the streaming FakeAgent would have
    # emitted "Hello "). A confirmation chunk stands in for the command output.
    assert not any("Hello" in t for t in texts)
    assert any("Ran" in t for t in texts)


@pytest.mark.asyncio
async def test_slash_command_string_result_runs_model(wired_agent, monkeypatch):
    """A command that returns a string expands into a prompt run by the model.

    Custom/markdown commands return their expanded text (like ``cli_runner``'s
    string command result), which must be fed to the agent -- not displayed as
    if it were the answer.
    """
    agent, _ = wired_agent
    new = await agent.new_session(cwd="/tmp")

    calls = {}

    def fake_handle(cmd):
        calls["cmd"] = cmd
        return "expanded prompt for the model"

    monkeypatch.setattr(
        "code_puppy.command_line.command_handler.handle_command", fake_handle
    )

    captured = {}

    async def echo_run(prompt, **_):
        captured["prompt"] = prompt
        return SimpleNamespace(
            output="modelled reply", usage=lambda: None, all_messages=lambda: []
        )

    agent._sessions[new.session_id].agent.run_with_mcp = echo_run
    resp = await agent.prompt(
        [SimpleNamespace(type="text", text="/plan feature")], new.session_id
    )
    assert resp.stop_reason == "end_turn"
    assert calls["cmd"] == "/plan feature"
    # The expanded string was fed to the model, not displayed verbatim.
    assert captured["prompt"] == "expanded prompt for the model"


@pytest.mark.asyncio
async def test_slash_command_sentinel_not_modelled(wired_agent, monkeypatch):
    """A ``__SENTINEL__`` string (TUI-only) must not be modelled over ACP."""
    agent, _ = wired_agent
    new = await agent.new_session(cwd="/tmp")

    monkeypatch.setattr(
        "code_puppy.command_line.command_handler.handle_command",
        lambda cmd: "__AUTOSAVE_LOAD__",
    )

    modelled = {"called": False}

    async def guard_run(prompt, **_):
        modelled["called"] = True
        return SimpleNamespace(output="x", usage=lambda: None, all_messages=lambda: [])

    agent._sessions[new.session_id].agent.run_with_mcp = guard_run
    resp = await agent.prompt(
        [SimpleNamespace(type="text", text="/load")], new.session_id
    )
    assert resp.stop_reason == "end_turn"
    assert modelled["called"] is False


def test_image_block_becomes_attachment():
    import base64

    png = base64.b64encode(b"\x89PNG fake").decode()
    parsed = content.parse_prompt(
        [
            SimpleNamespace(type="text", text="look"),
            SimpleNamespace(type="image", data=png, mime_type="image/png", uri=None),
        ]
    )
    assert parsed.text == "look"
    assert len(parsed.attachments) == 1
    assert parsed.attachments[0].media_type == "image/png"


def test_mcp_config_attach_stdio():
    from code_puppy.plugins.acp import mcp_config

    class _Agent:
        _mcp_servers: list = []

    agent = _Agent()
    spec = SimpleNamespace(
        name="fs", command="mcp-fs", args=["--root", "/x"], env=None, url=None
    )
    mcp_config.attach(agent, [spec])
    assert len(agent._mcp_servers) == 1


@pytest.mark.asyncio
async def test_set_config_option_toggles_streaming(wired_agent, monkeypatch):
    agent, _ = wired_agent
    written = {}
    monkeypatch.setattr(
        "code_puppy.config.set_config_value",
        lambda k, v: written.__setitem__(k, v),
    )
    monkeypatch.setattr("code_puppy.config.get_enable_streaming", lambda: False)
    new = await agent.new_session(cwd="/tmp")
    # Streaming is an On/Off select (Zed only renders selects), so the value is
    # the string "off", not a bool.
    resp = await agent.set_config_option("enable_streaming", new.session_id, "off")
    assert written["enable_streaming"] == "false"
    assert resp.config_options is not None
    streaming = next(o for o in resp.config_options if o.id == "enable_streaming")
    assert streaming.type == "select"
    assert [o.value for o in streaming.options] == ["on", "off"]


@pytest.mark.asyncio
async def test_set_config_model_rebinds_model(wired_agent, monkeypatch):
    """Switching the 'model' config option rebinds the agent, keeping history."""
    agent, _ = wired_agent
    picked = {}
    monkeypatch.setattr(
        "code_puppy.command_line.model_picker_completion.load_model_names",
        lambda: ["gpt-9"],
    )
    monkeypatch.setattr(
        "code_puppy.config.set_model_name", lambda m: picked.__setitem__("m", m)
    )
    new = await agent.new_session(cwd="/tmp")
    agent._sessions[new.session_id].agent.set_message_history(["keep-me"])
    await agent.set_config_option("model", new.session_id, "gpt-9")
    assert picked["m"] == "gpt-9"
    # History carried across the model rebind.
    assert agent._sessions[new.session_id].agent.get_message_history() == ["keep-me"]


@pytest.mark.asyncio
async def test_set_session_mode_is_noop(wired_agent, monkeypatch):
    """session/set_mode never switches models (Code Puppy has no modes)."""
    agent, _ = wired_agent
    called = {}
    monkeypatch.setattr(
        "code_puppy.config.set_model_name", lambda m: called.__setitem__("m", m)
    )
    new = await agent.new_session(cwd="/tmp")
    await agent.set_session_mode("anything", new.session_id)
    assert called == {}


def test_config_options_expose_model_select(monkeypatch):
    """The model picker is a category='model', type='select' config option."""
    from code_puppy.plugins.acp import session_config

    monkeypatch.setattr(
        "code_puppy.command_line.model_picker_completion.load_model_names",
        lambda: ["alpha", "beta"],
    )
    monkeypatch.setattr("code_puppy.config.get_global_model_name", lambda: "beta")
    opts = session_config.config_options()
    model_opt = next(o for o in opts if o.id == "model")
    assert model_opt.category == "model"
    assert model_opt.type == "select"
    assert [o.value for o in model_opt.options] == ["alpha", "beta"]
    assert model_opt.current_value == "beta"
    # A current model outside the list falls back to the first offered.
    monkeypatch.setattr("code_puppy.config.get_global_model_name", lambda: "gone")
    opts2 = session_config.config_options()
    assert next(o for o in opts2 if o.id == "model").current_value == "alpha"


def test_mode_state_is_single_default():
    """We advertise one 'default' mode as a category=mode select (not blank)."""
    from code_puppy.plugins.acp import session_config

    opts = session_config.config_options()
    mode_opt = next(o for o in opts if o.id == "mode")
    assert mode_opt.category == "mode"
    assert mode_opt.type == "select"
    assert mode_opt.current_value == "default"
    assert [o.value for o in mode_opt.options] == ["default"]


@pytest.mark.asyncio
async def test_interactive_tool_blocked_over_acp():
    """ask_user_question can't run headless; the bridge blocks it (steering the
    model to ask in plain text) without opening a dangling tool-call entry.
    """
    conn = FakeConnection()
    state.set_connection(conn, asyncio.get_event_loop())
    state.begin_run("s1")
    bridge = bridge_mod.EventBridge()
    try:
        result = await bridge._on_pre_tool_call("ask_user_question", {})
        assert isinstance(result, dict) and result["blocked"] is True
        assert "text response" in result["error_message"]
        # No tool_call update emitted and nothing pushed onto the stack.
        assert conn.updates == []
        assert state.current_tool_call() is None
    finally:
        state.end_run()
        state.set_connection(None, None)


# --------------------------------------------------------------------------- #
# Run-context isolation (concurrent prompts on one connection)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_run_context_is_task_isolated():
    """Two concurrent runs in separate tasks must not see each other's session.

    The SDK dispatches each ``session/prompt`` as its own task, so a shared
    module global would let one run clobber the other's active session id. The
    ``ContextVar`` keeps each run's state in its own task context.
    """
    seen = {}

    async def run(name):
        state.begin_run(name)
        await asyncio.sleep(0)  # yield so the sibling task interleaves here
        seen[name] = state.get_active_session_id()
        state.end_run()

    await asyncio.gather(run("A"), run("B"))
    assert seen == {"A": "A", "B": "B"}


@pytest.mark.asyncio
async def test_run_context_shared_with_child_task():
    """A mutation made in a spawned child task is visible in the parent run.

    ``note_streamed_text`` fires deep inside the run task, while the streamed
    fallback is read back in the prompt coroutine's ``finally``; the run state
    is a shared mutable so that write propagates despite the task boundary.
    """
    state.begin_run("s")
    try:

        async def child():
            state.note_streamed_text()

        await asyncio.ensure_future(child())
        assert state.streamed_text() is True
    finally:
        state.end_run()


def test_bridge_unregister_removes_callbacks():
    """``EventBridge.unregister`` leaves the callback registry as it found it."""
    from code_puppy import callbacks

    phases = ("stream_event", "pre_tool_call", "post_tool_call")
    before = {p: callbacks.count_callbacks(p) for p in phases}
    bridge = bridge_mod.EventBridge()
    bridge.register()
    assert all(callbacks.count_callbacks(p) == before[p] + 1 for p in phases)
    bridge.unregister()
    assert {p: callbacks.count_callbacks(p) for p in phases} == before


# --------------------------------------------------------------------------- #
# CR follow-ups: core seams + hardened behaviors
# --------------------------------------------------------------------------- #
def test_resolve_path_honors_working_directory_contextvar():
    from code_puppy.tools import common

    token = common.set_working_directory("/work/base")
    try:
        # Relative paths resolve against the override; absolute pass through.
        assert common.resolve_path("foo/bar.py") == "/work/base/foo/bar.py"
        assert common.resolve_path("/abs/x.py") == "/abs/x.py"
    finally:
        common.reset_working_directory(token)
    # After reset, no override -> falls back to process cwd.
    import os as _os

    assert common.resolve_path("rel.py") == _os.path.join(_os.getcwd(), "rel.py")


def test_write_project_file_rejects_non_utf8_over_backend():
    from code_puppy.tools import common, io_backends

    class _FS:
        def read_text_file(self, path, line=None, limit=None):
            return ""

        def write_text_file(self, path, content):
            pass

    io_backends.set_filesystem_backend(_FS())
    try:
        with pytest.raises(ValueError):
            common.write_project_file("/x.txt", "hi", encoding="latin-1")
    finally:
        io_backends.set_filesystem_backend(None)


def test_approval_backend_precedence_sync():
    from code_puppy.tools import common

    calls = []

    def backend(title, message, preview):
        calls.append((title, message, preview))
        return True, None

    common.set_approval_backend(backend)
    try:
        approved, feedback = common._get_user_approval_impl("Edit x.py", "body", None)
    finally:
        common.set_approval_backend(None)
    assert approved is True and feedback is None
    assert calls and calls[0][0] == "Edit x.py"


@pytest.mark.asyncio
async def test_approval_backend_precedence_async():
    from code_puppy.tools import common

    def backend(title, message, preview):
        return False, None

    common.set_approval_backend(backend)
    try:
        approved, _ = await common._get_user_approval_async_impl(
            "Run: rm", "body", None
        )
    finally:
        common.set_approval_backend(None)
    assert approved is False


@pytest.mark.asyncio
async def test_execute_via_backend_maps_result():
    from code_puppy.tools import command_runner, io_backends

    class _Exec:
        async def run(self, command, cwd, timeout):
            return io_backends.ExecResult(exit_code=0, output="hello\nworld")

    io_backends.set_command_executor(_Exec())
    try:
        out = await command_runner._execute_via_backend(
            _Exec(), "echo hi", None, 60, "grp", True
        )
    finally:
        io_backends.set_command_executor(None)
    assert out.success is True
    assert out.exit_code == 0
    assert "world" in out.stdout


@pytest.mark.asyncio
async def test_set_config_model_reattaches_mcp(wired_agent, monkeypatch):
    agent, _ = wired_agent
    monkeypatch.setattr(
        "code_puppy.command_line.model_picker_completion.load_model_names",
        lambda: ["gpt-9"],
    )
    monkeypatch.setattr("code_puppy.config.set_model_name", lambda m: None)
    reattached = {}
    monkeypatch.setattr(
        "code_puppy.plugins.acp.mcp_config.attach",
        lambda ag, specs: reattached.update(specs=specs),
    )
    new = await agent.new_session(cwd="/tmp")
    agent._sessions[new.session_id].mcp_specs = [SimpleNamespace(name="fs")]
    await agent.set_config_option("model", new.session_id, "gpt-9")
    assert "specs" in reattached and reattached["specs"][0].name == "fs"


@pytest.mark.asyncio
async def test_fork_unknown_session_raises(wired_agent):
    agent, _ = wired_agent
    with pytest.raises(ValueError):
        await agent.fork_session(cwd="/tmp", session_id="does-not-exist")


@pytest.mark.asyncio
async def test_refusal_sends_error_notice(wired_agent, monkeypatch):
    agent, conn = wired_agent
    new = await agent.new_session(cwd="/tmp")

    async def boom(*a, **k):
        raise RuntimeError("kaboom")

    agent._sessions[new.session_id].agent.run_with_mcp = boom
    resp = await agent.prompt([SimpleNamespace(type="text", text="hi")], new.session_id)
    assert resp.stop_reason == "refusal"
    texts = [
        u.content.text
        for _, u in conn.updates
        if getattr(u, "session_update", None) == "agent_message_chunk"
    ]
    assert any("failed" in t for t in texts)
