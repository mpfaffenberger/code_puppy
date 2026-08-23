"""Coverage for the /resume seams: picker wrapper, history echo, and the
two-pane session browser's data layer + widget.

Widget tests drive a real ``SessionBrowser`` headlessly with scripted
keys (injected ``key_source``/``output``/``size``) -- same recipe as the
other termflow menus.
"""

import json
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from termflow.ansi.utils import visible

from code_puppy.command_line.autosave_menu import interactive_autosave_picker
from code_puppy.command_line.session_browser import (
    _extract_message_content,
    build_session_browser,
)
from code_puppy.command_line.session_browser_data import (
    SessionEntry,
    _get_session_entries,
    _get_session_metadata,
    date_label,
    derive_titles,
    ensure_titles,
    group_by_project,
    sort_sessions,
    time_label,
    token_label,
)


class MockMessagePart:
    """Mock message part with configurable part_kind and attributes."""

    def __init__(
        self,
        part_kind: str = "text",
        content: str | None = None,
        tool_name: str | None = None,
        args: dict | None = None,
    ):
        self.part_kind = part_kind
        if content is not None:
            self.content = content
        if tool_name is not None:
            self.tool_name = tool_name
        if args is not None:
            self.args = args


class MockModelMessage:
    """Mock model message with configurable kind and parts."""

    def __init__(self, kind: str, parts: list):
        self.kind = kind
        self.parts = parts


def _entry(
    name, *, ts=None, scope=None, msgs=0, tokens=0, title=None, subtitle=None, tags=None
):
    meta = {}
    if tags:
        meta["tags"] = tags
    if ts is not None:
        meta["timestamp"] = ts
    if scope is not None:
        meta["scope_key"] = scope
    if msgs:
        meta["message_count"] = msgs
    if tokens:
        meta["total_tokens"] = tokens
    if title:
        meta["title"] = title
    if subtitle:
        meta["subtitle"] = subtitle
    return SessionEntry.from_pair(name, meta)


class TestDisplayResumedHistory:
    """Test the display_resumed_history function."""

    def test_displays_last_n_messages(self, capsys):
        """Should display the last N messages from history."""
        from code_puppy.command_line.autosave_menu import display_resumed_history

        messages = []
        for i in range(5):
            msg = MagicMock()
            msg.kind = "request"
            part = MagicMock()
            part.part_kind = "user-prompt"
            part.content = f"Message {i}"
            msg.parts = [part]
            messages.append(msg)

        display_resumed_history(messages, num_messages=3)

        captured = capsys.readouterr()
        assert "Message 2" in captured.out
        assert "Message 3" in captured.out
        assert "Message 4" in captured.out
        assert "1 earlier messages" in captured.out
        assert "Session Resumed" in captured.out

    def test_empty_history_returns_early(self):
        from code_puppy.command_line.autosave_menu import display_resumed_history

        display_resumed_history([])

    def test_renders_different_roles_correctly(self, capsys):
        from code_puppy.command_line.autosave_menu import display_resumed_history

        sys_msg = MagicMock()
        sys_msg.kind = "request"
        sys_msg.parts = []

        user_msg = MagicMock()
        user_msg.kind = "request"
        user_part = MagicMock()
        user_part.part_kind = "user-prompt"
        user_part.content = "Hello from user"
        user_msg.parts = [user_part]

        assistant_msg = MagicMock()
        assistant_msg.kind = "response"
        assistant_part = MagicMock()
        assistant_part.part_kind = "text"
        assistant_part.content = "Hello from assistant"
        assistant_msg.parts = [assistant_part]

        tool_msg = MagicMock()
        tool_msg.kind = "request"
        tool_part = MagicMock()
        tool_part.part_kind = "tool-return"
        tool_part.tool_name = "test_tool"
        tool_part.content = "Tool result"
        tool_msg.parts = [tool_part]

        display_resumed_history(
            [sys_msg, user_msg, assistant_msg, tool_msg], num_messages=10
        )

        captured = capsys.readouterr()
        assert "Hello from user" in captured.out
        assert "AGENT RESPONSE" in captured.out
        assert "Hello from assistant" in captured.out
        assert "Tool result" in captured.out or "test_tool" in captured.out

    def test_single_system_message_returns_early(self):
        from code_puppy.command_line.autosave_menu import display_resumed_history

        mock_msg = MagicMock()
        mock_msg.kind = "request"
        mock_msg.parts = []

        display_resumed_history([mock_msg])


class TestEdgeCasesAndErrorHandling:
    """Listing tolerates missing dirs and permission errors."""

    def test_with_nonexistent_autosave_dir(self):
        with patch(
            "code_puppy.command_line.session_browser_data.list_sessions",
            side_effect=FileNotFoundError(),
        ):
            entries = _get_session_entries(Path("/nonexistent/path"))
            assert isinstance(entries, list)

    def test_with_permission_denied_access(self):
        with patch(
            "code_puppy.command_line.session_browser_data._get_session_metadata",
            side_effect=PermissionError("Access denied"),
        ):
            with patch(
                "code_puppy.command_line.session_browser_data.list_sessions",
                return_value=["session1"],
            ):
                entries = _get_session_entries(Path("/protected/path"))
                assert len(entries) == 1
                assert entries[0][1] == {}


class TestExtractMessageContent:
    """Test the _extract_message_content function."""

    def test_mixed_parts_in_response_returns_assistant(self):
        msg = MockModelMessage(
            kind="response",
            parts=[
                MockMessagePart(part_kind="text", content="Let me help"),
                MockMessagePart(part_kind="tool-call", tool_name="read_file", args={}),
            ],
        )
        role, content = _extract_message_content(msg)
        assert role == "assistant"

    def test_tool_call_returns_tool_role(self):
        msg = MockModelMessage(
            kind="response",
            parts=[
                MockMessagePart(
                    part_kind="tool-call",
                    tool_name="edit_file",
                    args={"file_path": "test.py"},
                )
            ],
        )
        role, content = _extract_message_content(msg)
        assert role == "tool"
        assert "Tool Call: edit_file" in content

    def test_tool_call_truncates_long_args(self):
        long_args = {"content": "x" * 200}
        msg = MockModelMessage(
            kind="response",
            parts=[
                MockMessagePart(
                    part_kind="tool-call", tool_name="edit_file", args=long_args
                )
            ],
        )
        role, content = _extract_message_content(msg)
        assert "..." in content

    def test_tool_return_returns_tool_role(self):
        msg = MockModelMessage(
            kind="request",
            parts=[
                MockMessagePart(
                    part_kind="tool-return",
                    tool_name="read_file",
                    content="file contents here",
                )
            ],
        )
        role, content = _extract_message_content(msg)
        assert role == "tool"
        assert "\U0001f4e5 Tool Result: read_file" in content

    def test_tool_return_truncates_long_result(self):
        msg = MockModelMessage(
            kind="request",
            parts=[
                MockMessagePart(
                    part_kind="tool-return",
                    tool_name="read_file",
                    content="x" * 300,
                )
            ],
        )
        role, content = _extract_message_content(msg)
        assert "..." in content

    def test_user_prompt_returns_user_role(self):
        msg = MockModelMessage(
            kind="request",
            parts=[MockMessagePart(part_kind="user-prompt", content="Hello there")],
        )
        role, content = _extract_message_content(msg)
        assert role == "user"
        assert "Hello there" in content


class TestGetSessionEntries:
    """Test the _get_session_entries function."""

    @patch("code_puppy.command_line.session_browser_data.list_sessions")
    @patch("code_puppy.command_line.session_browser_data._get_session_metadata")
    def test_handles_invalid_timestamps(self, mock_metadata, mock_list):
        mock_list.return_value = ["invalid_ts", "valid_ts"]
        mock_metadata.side_effect = [
            {"timestamp": "invalid-date"},
            {"timestamp": "2024-01-01T12:00:00"},
        ]
        result = _get_session_entries(Path("/fake/dir"))
        assert result[0][0] == "valid_ts"
        assert result[1][0] == "invalid_ts"

    @patch("code_puppy.command_line.session_browser_data.list_sessions")
    @patch("code_puppy.command_line.session_browser_data._get_session_metadata")
    def test_handles_missing_timestamps(self, mock_metadata, mock_list):
        mock_list.return_value = ["no_timestamp", "valid_timestamp"]
        mock_metadata.side_effect = [{}, {"timestamp": "2024-01-01T12:00:00"}]
        result = _get_session_entries(Path("/fake/dir"))
        assert result[0][0] == "valid_timestamp"
        assert result[1][0] == "no_timestamp"

    @patch("code_puppy.command_line.session_browser_data.list_sessions")
    @patch("code_puppy.command_line.session_browser_data._get_session_metadata")
    def test_sorts_entries_by_timestamp_desc(self, mock_metadata, mock_list):
        mock_list.return_value = ["session1", "session2", "session3"]
        mock_metadata.side_effect = [
            {"timestamp": "2024-01-01T10:00:00"},
            {"timestamp": "2024-01-01T14:00:00"},
            {"timestamp": "2024-01-01T12:00:00"},
        ]
        result = _get_session_entries(Path("/fake/dir"))
        assert [name for name, _ in result] == ["session2", "session3", "session1"]


class TestGetSessionMetadata:
    def test_handles_missing_file(self, tmp_path):
        assert _get_session_metadata(tmp_path, "nonexistent_session") == {}

    def test_loads_valid_metadata(self, tmp_path):
        metadata = {"timestamp": "2024-01-01T12:00:00", "message_count": 5}
        (tmp_path / "test_session_meta.json").write_text(json.dumps(metadata))
        assert _get_session_metadata(tmp_path, "test_session") == metadata


class TestInteractiveAutosavePicker:
    """Test the interactive_autosave_picker function."""

    @patch("code_puppy.command_line.autosave_menu._get_session_entries")
    async def test_returns_none_for_no_sessions(self, mock_entries):
        mock_entries.return_value = []
        result = await interactive_autosave_picker()
        assert result is None

    async def test_fires_session_browser_open_hook_with_live_meta(self):
        from unittest.mock import AsyncMock

        from code_puppy.command_line.session_browser import BrowseResult

        stub_browser = MagicMock()
        stub_browser.run.return_value = BrowseResult(cancelled=True)
        hook = AsyncMock(return_value=[])
        pairs = [("s1", {"timestamp": "2026-01-01T10:00:00"})]
        with (
            patch(
                "code_puppy.command_line.autosave_menu._get_session_entries",
                return_value=pairs,
            ),
            patch(
                "code_puppy.command_line.autosave_menu.build_session_browser",
                return_value=stub_browser,
            ),
            patch("code_puppy.command_line.autosave_menu.menu_session", MagicMock()),
            patch("code_puppy.command_line.autosave_menu.set_awaiting_user_input"),
            patch("code_puppy.callbacks.on_session_browser_open", hook),
        ):
            result = await interactive_autosave_picker()

        assert result is None
        hook.assert_awaited_once()
        base_dir, entries = hook.await_args.args
        assert isinstance(base_dir, str)
        # The hook receives the browser's LIVE meta dicts, so plugin
        # enrichment (titles/tags) surfaces on repaint.
        assert entries[0][0] == "s1"
        assert entries[0][1] is pairs[0][1]


class TestSessionBrowserData:
    """Pure data-layer helpers: grouping, labels, titles."""

    def test_date_label_buckets(self):
        from datetime import date

        today = date(2026, 8, 23)
        assert date_label(datetime(2026, 8, 23, 9), today) == "TODAY"
        assert date_label(datetime(2026, 8, 22, 9), today) == "YESTERDAY"
        assert date_label(datetime(2026, 8, 21, 9), today) == "AUG 21"
        assert date_label(datetime(2025, 12, 1, 9), today) == "DEC 1, 2025"
        assert date_label(None, today) == "UNDATED"

    def test_time_and_token_labels(self):
        assert time_label(datetime(2026, 8, 23, 9, 54)) == "9:54 AM"
        assert time_label(None) == "--:--"
        assert token_label(90211) == "90k tok"
        assert token_label(900) == "900 tok"

    def test_group_by_project_pins_unscoped_last(self):
        entries = [
            _entry("legacy"),
            _entry("a1", ts="2026-01-01T10:00:00", scope="/code/alpha"),
            _entry("b1", ts="2026-01-02T10:00:00", scope="/code/beta"),
        ]
        projects = group_by_project(entries)
        # beta is more recent -> first; unscoped always last.
        assert [p.label for p in projects] == ["beta", "alpha", "(unscoped)"]
        assert projects[-1].unscoped
        assert [e.name for e in projects[-1].sessions] == ["legacy"]

    def test_group_by_project_disambiguates_basename_collisions(self):
        entries = [
            _entry("x", ts="2026-01-01T10:00:00", scope="/home/a/proj"),
            _entry("y", ts="2026-01-02T10:00:00", scope="/home/b/proj"),
        ]
        labels = sorted(p.label for p in group_by_project(entries))
        assert labels == [str(Path("a/proj")), str(Path("b/proj"))]

    def test_sort_sessions_modes(self):
        entries = [
            _entry("old", ts="2026-01-01T10:00:00", msgs=9, tokens=1),
            _entry("new", ts="2026-01-02T10:00:00", msgs=1, tokens=99),
        ]
        assert [e.name for e in sort_sessions(entries, "recent")] == ["new", "old"]
        assert [e.name for e in sort_sessions(entries, "msgs")] == ["old", "new"]
        assert [e.name for e in sort_sessions(entries, "tokens")] == ["new", "old"]

    def test_entry_title_fallbacks(self):
        entry = _entry("auto_session_x", msgs=7)
        assert entry.title == "auto_session_x"
        assert entry.subtitle == "7 messages"
        titled = _entry("s", title="Fix the bug", subtitle="in the parser")
        assert titled.title == "Fix the bug"
        assert titled.subtitle == "in the parser"

    def test_derive_titles_skips_context_preamble(self):
        # Harnesses inject long preambles/summaries as leading user
        # prompts; titles come from the first human-sized text instead.
        history = [
            MockModelMessage(
                "request",
                [
                    MockMessagePart(
                        part_kind="user-prompt",
                        content="You are a helpful agent... " * 40,
                    )
                ],
            ),
            MockModelMessage(
                "request",
                [MockMessagePart(part_kind="user-prompt", content="Fix the bug\nplz")],
            ),
            MockModelMessage(
                "response", [MockMessagePart(part_kind="text", content="done")]
            ),
            MockModelMessage(
                "request",
                [MockMessagePart(part_kind="user-prompt", content="now add tests")],
            ),
        ]
        title, subtitle = derive_titles(history)
        assert title == "Fix the bug"
        assert subtitle == "now add tests"
        assert derive_titles([]) == ("", "")

    def test_derive_titles_falls_back_when_only_context_exists(self):
        # A session whose only user text is a long context block still
        # gets a title from it -- better than nothing.
        history = [
            MockModelMessage(
                "request",
                [
                    MockMessagePart(
                        part_kind="user-prompt",
                        content="long context block " * 40,
                    )
                ],
            )
        ]
        title, _ = derive_titles(history)
        assert title.startswith("long context block")

    def test_derive_titles_single_short_prompt(self):
        history = [
            MockModelMessage(
                "request",
                [MockMessagePart(part_kind="user-prompt", content="only prompt")],
            )
        ]
        assert derive_titles(history) == ("only prompt", "")

    @patch("code_puppy.command_line.session_browser_data.load_session")
    def test_ensure_titles_caches_back_to_sidecar(self, mock_load, tmp_path):
        mock_load.return_value = [
            MockModelMessage(
                "request",
                [MockMessagePart(part_kind="user-prompt", content="Do the thing")],
            )
        ]
        (tmp_path / "s1_meta.json").write_text(json.dumps({"message_count": 3}))
        entry = _entry("s1", msgs=3)

        assert ensure_titles(tmp_path, entry) is True
        assert entry.title == "Do the thing"
        sidecar = json.loads((tmp_path / "s1_meta.json").read_text())
        assert sidecar["title"] == "Do the thing"
        assert sidecar["message_count"] == 3  # merged, not clobbered
        # Second call is a no-op: title already present.
        assert ensure_titles(tmp_path, entry) is False

    @patch(
        "code_puppy.command_line.session_browser_data.load_session",
        side_effect=OSError("gone"),
    )
    def test_ensure_titles_tolerates_broken_sessions(self, _mock, tmp_path):
        entry = _entry("broken")
        assert ensure_titles(tmp_path, entry) is False


class TestSessionBrowser:
    """Headless drives of the two-pane widget."""

    def drive(self, entries, script, size=lambda: (110, 30)):
        output = StringIO()
        browser = build_session_browser(
            entries=entries,
            base_dir=Path("/fake"),
            key_source=lambda: next(script),
            output=output,
            size=size,
            use_alt_screen=False,
        )
        result = browser.run()
        return browser, result, visible(output.getvalue()), output.getvalue()

    def sample_entries(self):
        now = datetime.now()
        stamp = lambda **kw: (now - timedelta(**kw)).isoformat()  # noqa: E731
        return [
            _entry(
                "fix-pyte",
                ts=stamp(hours=1),
                scope="/code/code_puppy",
                msgs=86,
                tokens=90211,
                title="Fix pyte rendering gaps",
                subtitle="PyPI release missing renderer fixes",
            ),
            _entry(
                "debug-restore",
                ts=stamp(hours=2),
                scope="/code/code_puppy",
                msgs=43,
                tokens=51000,
                title="Debug session restore bug",
            ),
            _entry(
                "repl-echo",
                ts=stamp(days=1, hours=2),
                scope="/code/termflow",
                msgs=36,
                tokens=28000,
                title="REPL echo analysis",
            ),
            _entry("legacy", msgs=5, tokens=900),
        ]

    def test_open_project_and_select_session(self):
        browser, result, output, _ = self.drive(
            self.sample_entries(), iter(["enter", "down", "enter"])
        )
        assert result.session == "debug-restore"
        assert not result.cancelled
        assert "CODE PUPPY" in output
        assert "PROJECTS (3)" in output
        assert "Fix pyte rendering gaps" in output
        assert "90k tok" in output
        assert "TODAY" in output

    def test_unscoped_bucket_is_last_and_selectable(self):
        browser, result, _, _ = self.drive(
            self.sample_entries(), iter(["down", "down", "enter", "enter"])
        )
        assert result.session == "legacy"
        assert browser._projects[-1].unscoped

    def test_escape_from_projects_cancels(self):
        _, result, _, _ = self.drive(self.sample_entries(), iter(["escape"]))
        assert result.cancelled

    def test_left_returns_to_projects_pane(self):
        browser, result, _, _ = self.drive(
            self.sample_entries(), iter(["enter", "left", "q"])
        )
        assert result.cancelled
        assert browser._mode == "projects"

    def test_search_filters_and_escape_clears(self):
        entries = self.sample_entries()
        browser, result, output, _ = self.drive(
            entries, iter(["enter", "/", "p", "y", "t", "e", "enter", "enter"])
        )
        assert result.session == "fix-pyte"
        assert "/ pyte" in output  # live search buffer in the header

        browser, result, _, _ = self.drive(
            entries, iter(["enter", "/", "z", "z", "enter", "escape", "down", "enter"])
        )
        # 'zz' matches nothing; escape clears the filter, then select works.
        assert result.session == "debug-restore"

    def test_search_works_immediately_from_projects_pane(self):
        # The exact regression: '/' pressed right after the browser
        # opens (projects pane focused) must start a search, not no-op.
        _, result, output, _ = self.drive(
            self.sample_entries(), iter(["/", "e", "c", "h", "o", "enter", "enter"])
        )
        assert result.session == "repl-echo"

    def test_search_is_global_across_projects(self):
        # 'repl-echo' lives in /code/termflow; the selected project is
        # /code/code_puppy. A search must still find it.
        browser, result, output, _ = self.drive(
            self.sample_entries(),
            iter(["enter", "/", "e", "c", "h", "o", "enter", "enter"]),
        )
        assert result.session == "repl-echo"
        assert "across all projects" in output

    def test_search_no_matches_message(self):
        _, result, output, _ = self.drive(
            self.sample_entries(),
            iter(["enter", "/", "z", "z", "z", "enter", "escape", "escape", "q"]),
        )
        assert result.cancelled
        assert "No matches for 'zzz'." in output

    def test_delete_during_global_search_removes_from_owning_project(self, tmp_path):
        entries = [
            _entry("here", ts="2026-01-02T10:00:00", scope="/alpha", msgs=2),
            _entry(
                "elsewhere",
                ts="2026-01-01T10:00:00",
                scope="/beta",
                msgs=1,
                title="findme special",
            ),
        ]
        for entry in entries:
            self._touch_session(tmp_path, entry.name)
        browser, result, _ = self._drive_dir(
            entries,
            iter(["/", "f", "i", "n", "d", "m", "e", "enter", "d", "y", "q", "q"]),
            tmp_path,
        )
        assert result.cancelled
        assert not (tmp_path / "elsewhere.json").exists()
        # The /beta bucket collapsed with its only session.
        assert [p.label for p in browser._projects] == ["alpha"]

    def test_sort_cycle_reorders_sessions(self):
        entries = [
            _entry("small", ts="2026-01-02T10:00:00", scope="/p", msgs=1, tokens=5),
            _entry("big", ts="2026-01-01T10:00:00", scope="/p", msgs=99, tokens=999),
        ]
        browser, result, _, _ = self.drive(entries, iter(["enter", "s", "enter"]))
        # After one 's', sort=msgs -> 'big' first and highlighted.
        assert result.session == "big"

    @patch("code_puppy.session_storage.load_session")
    def test_browse_overlay_and_escape(self, mock_load):
        mock_load.return_value = [
            MockModelMessage(
                "request", [MockMessagePart(part_kind="user-prompt", content="old")]
            ),
            MockModelMessage(
                "response", [MockMessagePart(part_kind="text", content="new")]
            ),
        ]
        browser, result, output, _ = self.drive(
            self.sample_entries(),
            iter(["enter", "right", "up", "down", "escape", "escape", "q"]),
        )
        assert result.cancelled
        assert "MESSAGE BROWSER" in output

    def test_theme_accents_reach_the_frame(self):
        from termflow.ansi.color import fg_color

        ansi = ["#000000"] * 16
        ansi[10] = "#234567"
        ansi[12] = "#123456"
        palette = {"ansi": ansi, "bg": "#010101"}
        with patch(
            "code_puppy.command_line.tui_style.get_value",
            return_value=json.dumps(palette),
        ):
            _, result, _, raw = self.drive(self.sample_entries(), iter(["escape"]))
        assert result.cancelled
        assert fg_color(ansi[12]) in raw  # bright accent from the active theme

    def test_tags_render_and_are_searchable(self):
        entries = [
            _entry(
                "tagged",
                ts="2026-01-02T10:00:00",
                scope="/p",
                msgs=5,
                tokens=100,
                title="Fix rendering",
                subtitle="gaps in pyte",
                tags=["pyte", "tui"],
            ),
            _entry(
                "plain",
                ts="2026-01-01T10:00:00",
                scope="/p",
                msgs=3,
                tokens=50,
                title="Other work",
            ),
        ]
        browser, result, output, _ = self.drive(
            entries, iter(["enter", "/", "t", "u", "i", "enter", "enter"])
        )
        # 'tui' matches only via the tag; title/content don't contain it.
        assert result.session == "tagged"
        assert "#pyte #tui" in output

    def _drive_dir(self, entries, script, base_dir):
        output = StringIO()
        browser = build_session_browser(
            entries=entries,
            base_dir=base_dir,
            key_source=lambda: next(script),
            output=output,
            size=lambda: (110, 30),
            use_alt_screen=False,
        )
        result = browser.run()
        return browser, result, visible(output.getvalue())

    def _touch_session(self, base_dir, name):
        (base_dir / f"{name}.json").write_text("{}")
        (base_dir / f"{name}_meta.json").write_text("{}")

    def test_delete_confirm_removes_session_and_files(self, tmp_path):
        entries = [
            _entry("keep", ts="2026-01-02T10:00:00", scope="/p", msgs=2, tokens=5),
            _entry("doomed", ts="2026-01-01T10:00:00", scope="/p", msgs=1, tokens=5),
        ]
        for entry in entries:
            self._touch_session(tmp_path, entry.name)
        browser, result, output = self._drive_dir(
            entries, iter(["enter", "down", "d", "y", "enter"]), tmp_path
        )
        # 'doomed' is gone from disk and the list; enter resumes 'keep'.
        assert result.session == "keep"
        assert "Delete 'doomed'?" in output
        assert not (tmp_path / "doomed.json").exists()
        assert not (tmp_path / "doomed_meta.json").exists()
        assert (tmp_path / "keep.json").exists()
        assert [e.name for e in browser.visible_sessions()] == ["keep"]

    def test_delete_any_other_key_cancels(self, tmp_path):
        entries = [_entry("safe", ts="2026-01-01T10:00:00", scope="/p", msgs=1)]
        self._touch_session(tmp_path, "safe")
        browser, result, _ = self._drive_dir(
            entries, iter(["enter", "d", "n", "enter"]), tmp_path
        )
        assert result.session == "safe"
        assert (tmp_path / "safe.json").exists()

    def test_deleting_last_session_collapses_project(self, tmp_path):
        entries = [
            _entry("only", ts="2026-01-02T10:00:00", scope="/solo", msgs=1),
            _entry("other", ts="2026-01-01T10:00:00", scope="/full", msgs=1),
        ]
        for entry in entries:
            self._touch_session(tmp_path, entry.name)
        browser, result, _ = self._drive_dir(
            entries, iter(["enter", "d", "y", "q"]), tmp_path
        )
        # /solo emptied out: back on the projects pane, bucket gone.
        assert result.cancelled
        assert browser._mode == "projects"
        assert [p.label for p in browser._projects] == ["full"]

    def test_tiny_terminal_survives(self):
        _, result, _, _ = self.drive(
            self.sample_entries(),
            iter(["enter", "down", "down", "down", "escape", "escape"]),
            size=lambda: (40, 8),
        )
        assert result.cancelled

    def _hostile_entries(self):
        return [
            _entry(
                "wide",
                ts="2026-01-02T10:00:00",
                scope="/projects/a-rather-long-project-directory-name",
                msgs=273,
                tokens=1170000,
                title="A very long descriptive session title that keeps on going",
                subtitle="An even longer subtitle stuffed with implementation "
                "detail that cannot possibly fit on one row",
                tags=["refactoring", "capabilities", "observability", "testing"],
            ),
            _entry(
                "narrow",
                ts="2026-01-01T10:00:00",
                scope="/projects/a-rather-long-project-directory-name",
                msgs=1,
                tokens=5,
                title="tiny",
            ),
        ]

    def _frame_lines(self, raw):
        for frame in raw.split("\x1b[H")[1:]:
            for line in frame.replace("\x1b[J", "").split("\r\n"):
                yield line.replace("\x1b[K", "")

    def test_no_line_ever_exceeds_terminal_width(self):
        from termflow.ansi.utils import visible_length

        for width in (60, 80, 100, 140):
            output = StringIO()
            script = iter(["enter", "down", "/", "x", "escape", "escape", "escape"])
            browser = build_session_browser(
                entries=self._hostile_entries(),
                base_dir=Path("/fake"),
                key_source=lambda: next(script),
                output=output,
                size=lambda: (width, 20),
                use_alt_screen=False,
            )
            browser.run()
            for line in self._frame_lines(output.getvalue()):
                assert visible_length(line) <= width, (
                    f"line overflows {width} cols: {line!r}"
                )

    def test_tags_drop_whole_not_partial_when_narrow(self):
        _, result, output, _ = self.drive(
            self._hostile_entries(),
            iter(["enter", "escape", "escape"]),
            size=lambda: (80, 20),
        )
        assert result.cancelled
        # Whichever tags render are complete words; no mid-tag amputation.
        rendered = [t for t in ("#refactoring", "#capabilities") if t in output]
        for tag in rendered:
            assert tag in output
        assert "#observab\u2026" not in output and "#observabi" not in output
