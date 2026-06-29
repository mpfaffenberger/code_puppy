"""Tests for the plugin metadata surface.

Covers three collaborating pieces added on the plugin-enhancements branch:

* ``plugin_list.plugin_meta`` — description / file-path / hook resolution
  across the builtin/user/project tiers and the unresolved-module path.
  ``get_hooks`` ownership lookup is covered here too, including the
  disabled-but-still-registered case and the empty case.
* ``plugins_menu`` preview rendering of the Description / Lifecycle hooks / Path
  sections.
"""

from __future__ import annotations

import types
from unittest.mock import patch

import pytest

from code_puppy import callbacks
from code_puppy.plugins.plugin_list import plugin_meta
from code_puppy.plugins.plugin_list.plugins_menu_render import fill_pane, render_detail

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def clean_callbacks():
    """Snapshot and restore the global callback registries.

    Tests register fake-owner callbacks via the loading-context machinery;
    this keeps that pollution from leaking into other tests.
    """
    saved_callbacks = {
        phase: list(funcs) for phase, funcs in callbacks._callbacks.items()
    }
    saved_owners = dict(callbacks._callback_owners)
    saved_loading = callbacks._current_loading_plugin
    try:
        yield
    finally:
        for phase in callbacks._callbacks:
            callbacks._callbacks[phase] = saved_callbacks.get(phase, [])
        callbacks._callback_owners.clear()
        callbacks._callback_owners.update(saved_owners)
        callbacks._current_loading_plugin = saved_loading


def _register_owned(owner: str, phase: str):
    """Register a fresh callback for *phase* owned by *owner*; return it."""

    def _cb(*args, **kwargs):  # pragma: no cover - never dispatched
        return None

    callbacks.set_loading_context(owner)
    try:
        callbacks.register_callback(phase, _cb)
    finally:
        callbacks.clear_loading_context()
    return _cb


def _fake_module(doc=None, file=None):
    """Build a stand-in module object with __doc__/__file__ attributes."""
    mod = types.ModuleType("fake_plugin_module")
    mod.__doc__ = doc
    if file is not None:
        mod.__file__ = file
    return mod


# ── plugin_meta._resolve_module / tier templates ──────────────────────────


class TestResolveModule:
    def test_unknown_tier_returns_none(self):
        assert plugin_meta._resolve_module("anything", "bogus_tier") is None

    @pytest.mark.parametrize(
        "tier,template",
        [
            ("builtin", "code_puppy.plugins.{name}.register_callbacks"),
            ("user", "{name}.register_callbacks"),
            ("project", "project_plugins.{name}.register_callbacks"),
        ],
    )
    def test_resolves_each_tier(self, tier, template, monkeypatch):
        mod = _fake_module(doc="x")
        modname = template.format(name="fakeplug")
        monkeypatch.setitem(__import__("sys").modules, modname, mod)
        assert plugin_meta._resolve_module("fakeplug", tier) is mod

    def test_missing_module_returns_none(self):
        # Nothing registered under this name → None.
        assert plugin_meta._resolve_module("definitely_not_loaded", "builtin") is None


# ── plugin_meta.get_description ───────────────────────────────────────────


class TestGetDescription:
    def _install(self, monkeypatch, doc):
        mod = _fake_module(doc=doc, file="/x/register_callbacks.py")
        monkeypatch.setitem(
            __import__("sys").modules,
            "code_puppy.plugins.descplug.register_callbacks",
            mod,
        )

    def test_first_paragraph_only(self, monkeypatch):
        self._install(
            monkeypatch,
            "Short summary line.\n\nA second paragraph with extra detail "
            "that should be dropped.",
        )
        assert (
            plugin_meta.get_description("descplug", "builtin") == "Short summary line."
        )

    def test_newline_collapsing(self, monkeypatch):
        self._install(
            monkeypatch,
            "First wrapped\nsummary line\nspanning three rows.\n\nrest",
        )
        assert (
            plugin_meta.get_description("descplug", "builtin")
            == "First wrapped summary line spanning three rows."
        )

    def test_none_when_module_missing(self):
        assert plugin_meta.get_description("nope_missing", "builtin") is None

    def test_none_when_docstring_missing(self, monkeypatch):
        self._install(monkeypatch, None)
        assert plugin_meta.get_description("descplug", "builtin") is None

    def test_none_when_docstring_only_whitespace(self, monkeypatch):
        self._install(monkeypatch, "   \n\n   ")
        assert plugin_meta.get_description("descplug", "builtin") is None

    def test_none_for_unknown_tier(self, monkeypatch):
        self._install(monkeypatch, "Has a docstring.")
        assert plugin_meta.get_description("descplug", "bogus_tier") is None


# ── plugin_meta.get_file_path ─────────────────────────────────────────────


class TestGetFilePath:
    def test_returns_file_when_resolvable(self, monkeypatch):
        mod = _fake_module(doc="d", file="/plugins/pathplug/register_callbacks.py")
        monkeypatch.setitem(
            __import__("sys").modules,
            "user_pathplug.register_callbacks",
            mod,
        )
        # user tier template is "{name}.register_callbacks"
        assert (
            plugin_meta.get_file_path("user_pathplug", "user")
            == "/plugins/pathplug/register_callbacks.py"
        )

    def test_none_when_module_missing(self):
        assert plugin_meta.get_file_path("nope_missing", "builtin") is None

    def test_none_when_file_attr_missing(self, monkeypatch):
        mod = _fake_module(doc="d")  # no __file__ set
        # ensure no __file__ leaks from ModuleType defaults
        if hasattr(mod, "__file__"):
            del mod.__file__
        monkeypatch.setitem(
            __import__("sys").modules,
            "code_puppy.plugins.nofile.register_callbacks",
            mod,
        )
        assert plugin_meta.get_file_path("nofile", "builtin") is None

    def test_none_for_unknown_tier(self):
        assert plugin_meta.get_file_path("anything", "bogus_tier") is None


# ── plugin_meta.get_hooks ─────────────────────────────────────────────────


class TestGetHooks:
    def test_returns_sorted_phases(self, clean_callbacks):
        _register_owned("hookplug", "shutdown")
        _register_owned("hookplug", "startup")
        _register_owned("hookplug", "load_prompt")
        assert plugin_meta.get_hooks("hookplug") == [
            "load_prompt",
            "shutdown",
            "startup",
        ]

    def test_empty_when_none(self, clean_callbacks):
        assert plugin_meta.get_hooks("plugin_with_no_hooks") == []

    def test_ignores_other_owners(self, clean_callbacks):
        _register_owned("ownerA", "startup")
        _register_owned("ownerB", "shutdown")
        assert plugin_meta.get_hooks("ownerA") == ["startup"]
        assert plugin_meta.get_hooks("ownerB") == ["shutdown"]

    def test_disabled_plugin_still_registered(self, clean_callbacks):
        """Disabled plugins keep their callbacks registered — only dispatch
        skips them — so the preview must still surface their hooks.

        ``get_hooks`` relies on ``get_callbacks(include_disabled=True)`` to
        bypass the dispatch-time disabled filter.
        """
        _register_owned("disabledplug", "startup")
        _register_owned("disabledplug", "stream_event")
        with patch(
            "code_puppy.plugins.config.get_disabled_plugins",
            return_value={"disabledplug"},
        ):
            assert plugin_meta.get_hooks("disabledplug") == [
                "startup",
                "stream_event",
            ]

    def test_empty_for_unknown_plugin(self, clean_callbacks):
        assert plugin_meta.get_hooks("never_seen_plugin") == []


# ── plugins_menu preview rendering ────────────────────────────────────────


def _make_menu(name="previewplug", tier="builtin"):
    """Construct a PluginsMenu with one entry, bypassing real discovery."""
    from code_puppy.plugins.plugin_list.plugins_menu import PluginsMenu, _PluginEntry

    with (
        patch(
            "code_puppy.plugins.get_loaded_plugins",
            return_value={"builtin": [], "user": [], "project": []},
        ),
        patch(
            "code_puppy.plugins.config.get_disabled_plugins",
            return_value=set(),
        ),
    ):
        menu = PluginsMenu()
    menu.plugins = [_PluginEntry(name, tier)]
    menu.selected_idx = 0
    return menu


def _flatten(fragments) -> str:
    return "".join(text for _style, text in fragments)


class TestMenuPreview:
    def test_renders_description_hooks_and_path(self):
        menu = _make_menu()
        with (
            patch.object(
                plugin_meta, "get_description", return_value="A tidy summary."
            ),
            patch.object(
                plugin_meta,
                "get_hooks",
                return_value=["startup", "shutdown"],
            ),
            patch.object(
                plugin_meta,
                "get_file_path",
                return_value="/abs/path/register_callbacks.py",
            ),
        ):
            text = _flatten(render_detail(menu))

        assert "previewplug" in text
        # Description section
        assert "A tidy summary." in text
        # Lifecycle-hooks section: header carries the count, bullets list each hook
        assert "Lifecycle hooks used (2):" in text
        assert "• startup" in text
        assert "• shutdown" in text
        assert "(none registered)" not in text
        # Path section
        assert "Path:" in text
        assert "/abs/path/register_callbacks.py" in text

    def test_renders_none_registered_when_no_hooks(self):
        menu = _make_menu()
        with (
            patch.object(plugin_meta, "get_description", return_value=None),
            patch.object(plugin_meta, "get_hooks", return_value=[]),
            patch.object(plugin_meta, "get_file_path", return_value=None),
        ):
            text = _flatten(render_detail(menu))

        assert "Lifecycle hooks used (0):" in text
        assert "(none registered)" in text
        # No path section when path is unresolved.
        assert "Path:" not in text

    def test_no_description_section_when_missing(self):
        menu = _make_menu()
        with (
            patch.object(plugin_meta, "get_description", return_value=None),
            patch.object(plugin_meta, "get_hooks", return_value=["startup"]),
            patch.object(plugin_meta, "get_file_path", return_value="/x.py"),
        ):
            fragments = render_detail(menu)
            text = _flatten(fragments)

        # Lifecycle hooks still render, description simply omitted.
        assert "Lifecycle hooks used (1):" in text
        assert "• startup" in text

    def test_no_plugin_selected(self):
        menu = _make_menu()
        menu.plugins = []
        text = _flatten(render_detail(menu))
        assert "No plugin selected." in text


# ── plugins_menu "Contributes" rendering ───────────────────────────────────

from code_puppy.plugins.plugin_list import plugin_contributions as pc  # noqa: E402

_EMPTY_CONTRIB = {key: [] for key in pc._EXTRACTORS}


def _contrib(**overrides):
    """Build a full contributions dict, overriding only the named categories."""
    data = dict(_EMPTY_CONTRIB)
    data.update(overrides)
    return data


class TestMenuContributes:
    def _render(self, contributions, hooks=None):
        """Render the detail pane with patched extraction + hooks."""
        menu = _make_menu()
        with (
            patch.object(plugin_meta, "get_description", return_value=None),
            patch.object(plugin_meta, "get_hooks", return_value=hooks or []),
            patch.object(plugin_meta, "get_file_path", return_value=None),
            patch.object(pc, "get_contributions", return_value=contributions),
        ):
            return _flatten(render_detail(menu))

    def test_groups_categories_with_names_and_descriptions(self):
        text = self._render(
            _contrib(
                tools=["do_thing"],
                commands=["/foo — Do foo"],
                agents=["my-agent"],
                skills=["my-skill"],
            )
        )
        assert "Contributes:" in text
        assert "Tools:" in text
        assert "• do_thing" in text
        assert "Slash Commands:" in text
        assert "• /foo — Do foo" in text
        assert "Agents:" in text
        assert "• my-agent" in text
        assert "Skills:" in text
        assert "• my-skill" in text

    def test_skips_empty_categories(self):
        text = self._render(_contrib(tools=["only_tool"]))
        assert "Tools:" in text
        assert "• only_tool" in text
        # Categories with nothing in them are not rendered at all.
        assert "Slash Commands:" not in text
        assert "Agents:" not in text
        assert "Skills:" not in text
        assert "Model Types:" not in text

    def test_renders_nothing_when_no_contributions(self):
        text = self._render(_contrib())
        assert "Contributes:" not in text
        # The other sections still render so the preview isn't blank.
        assert "Lifecycle hooks used (0):" in text

    def test_command_handler_without_help_shows_placeholder(self):
        # No custom_command_help entries, but a custom_command hook exists.
        text = self._render(_contrib(), hooks=["custom_command"])
        assert "Contributes:" in text
        assert "Slash Commands:" in text
        assert "• command handler (name unknown)" in text

    def test_real_commands_win_over_placeholder(self):
        # When help entries exist we never fall back to the placeholder, even
        # if a custom_command hook is also registered.
        text = self._render(
            _contrib(commands=["/named — A real command"]),
            hooks=["custom_command"],
        )
        assert "• /named — A real command" in text
        assert "command handler (name unknown)" not in text

    def test_all_categories_render(self):
        text = self._render(
            _contrib(
                tools=["t"],
                commands=["/c"],
                agents=["a"],
                skills=["s"],
                model_types=["mt"],
                model_providers=["mp"],
                mcp_servers=["srv"],
                browser_types=["bt"],
                agent_tools=["at"],
            )
        )
        for label in (
            "Tools:",
            "Slash Commands:",
            "Agents:",
            "Skills:",
            "Model Types:",
            "Model Providers:",
            "MCP Servers:",
            "Browser Types:",
            "Agent Tools:",
        ):
            assert label in text

    def test_long_contributions_get_wrapped(self):
        """Long entries (e.g. agent_skills /<skill>) must wrap to pane width.

        Without wrapping, the long tail extends past our padding cap and leaves
        stale glyphs (a literal "...") when the user navigates to a plugin
        whose detail content doesn't reach those columns.
        """
        menu = _make_menu()
        # Force a narrow detail pane so wrapping is unambiguous.
        menu._detail_cols = 40
        long_cmd = "/x — " + ("long " * 20).strip()
        with (
            patch.object(plugin_meta, "get_description", return_value=None),
            patch.object(plugin_meta, "get_hooks", return_value=[]),
            patch.object(plugin_meta, "get_file_path", return_value=None),
            patch.object(
                pc, "get_contributions", return_value=_contrib(commands=[long_cmd])
            ),
        ):
            fragments = render_detail(menu)

        # Every (style, text) fragment whose payload is real content (not just
        # whitespace/newlines) must fit within the pane's inner width.
        inner = menu._detail_cols - 2
        for _style, text in fragments:
            for line in text.split("\n"):
                assert len(line) <= inner, f"Line exceeds inner width {inner}: {line!r}"

    def test_extraction_failure_degrades_gracefully(self):
        """A raising ``get_contributions`` renders nothing extra, not a crash."""
        menu = _make_menu()
        with (
            patch.object(plugin_meta, "get_description", return_value=None),
            patch.object(plugin_meta, "get_hooks", return_value=[]),
            patch.object(plugin_meta, "get_file_path", return_value=None),
            patch.object(pc, "get_contributions", side_effect=RuntimeError("boom")),
        ):
            text = _flatten(render_detail(menu))
        assert "Contributes:" not in text
        assert "Lifecycle hooks used (0):" in text


# ── detail pane scrolling ──────────────────────────────────────────────────

from code_puppy.plugins.plugin_list import plugin_text_utils as ptu  # noqa: E402


class TestLineSlicing:
    def test_count_lines(self):
        assert ptu.count_lines([("", "a\nb\n"), ("", "c\n")]) == 3
        assert ptu.count_lines([("", "no newline")]) == 0

    def test_drop_zero_returns_all(self):
        frags = [("s", "a\n"), ("s", "b\n")]
        assert ptu.drop_leading_lines(frags, 0) == frags

    def test_drop_leading_lines(self):
        frags = [("x", "l0\n"), ("y", "l1\n"), ("z", "l2\n")]
        assert _flatten(ptu.drop_leading_lines(frags, 2)) == "l2\n"

    def test_drop_across_fragment_boundary(self):
        # One logical line spread across two fragments, then the next line.
        frags = [("a", "line0 "), ("b", "rest\n"), ("c", "line1\n")]
        assert _flatten(ptu.drop_leading_lines(frags, 1)) == "line1\n"

    def test_drop_more_than_available(self):
        assert ptu.drop_leading_lines([("a", "only\n")], 5) == []

    def test_wrap_text_short_returns_single_piece(self):
        assert ptu.wrap_text("hi there", 20) == ["hi there"]

    def test_wrap_text_breaks_after_last_space(self):
        # Width 10 -> first window "the quick " (10 chars, break after space).
        pieces = ptu.wrap_text("the quick brown fox", 10)
        assert "".join(pieces) == "the quick brown fox"
        assert all(len(p) <= 10 for p in pieces)

    def test_wrap_text_hard_breaks_long_unbroken_token(self):
        # A path-like string with no spaces should hard-break, losing nothing.
        path = "C:\\Users\\weege\\code\\thing.py"
        pieces = ptu.wrap_text(path, 8)
        assert "".join(pieces) == path
        assert all(len(p) <= 8 for p in pieces)

    def test_wrap_text_zero_width_is_noop(self):
        assert ptu.wrap_text("anything", 0) == ["anything"]

    def test_cell_width_ascii_matches_len(self):
        assert ptu.cell_width("hello") == 5

    def test_cell_width_emoji_is_two(self):
        # \U0001F436 is the dog-face emoji (1 Python char, 2 terminal cells).
        assert ptu.cell_width("\U0001f436") == 2

    def test_cell_width_hammer_wrench_with_vs16_is_two(self):
        # U+1F6E0 + U+FE0F (variation selector). prompt_toolkit's get_cwidth
        # under-reports the hammer-wrench at 1 cell; our emoji-range override
        # forces it to 2. VS16 stays at 0. This is the exact bug that surfaces
        # in agent_skills contributions, where every /skill is labelled with
        # this glyph and the undercount bled into the divider.
        assert ptu.cell_width("\U0001f6e0\ufe0f") == 2

    def test_cell_width_dingbat_is_two(self):
        # U+2705 (white heavy check mark) sits in the Dingbats range our
        # override covers; terminals render it at 2 cells.
        assert ptu.cell_width("\u2705") == 2

    def test_strip_emojis_removes_emoji_and_vs16(self):
        # Hammer-wrench + VS16, dog face, check mark — all gone. ASCII stays.
        assert (
            ptu.strip_emojis("foo \U0001f6e0\ufe0f bar \U0001f436 baz \u2705")
            == "foo  bar  baz "
        )

    def test_strip_emojis_removes_zwj(self):
        # ZWJ sequences (e.g. family emoji) leave no residue.
        assert ptu.strip_emojis("a\u200db") == "ab"

    def test_strip_emojis_preserves_ascii_and_newlines(self):
        assert ptu.strip_emojis("hello\nworld\t!") == "hello\nworld\t!"

    def test_strip_emojis_from_fragments_walks_every_fragment(self):
        frags = [("bold", "a\U0001f436b"), ("", "c\u2705d")]
        assert ptu.strip_emojis_from_fragments(frags) == [
            ("bold", "ab"),
            ("", "cd"),
        ]

    def test_pad_lines_to_cells_pads_short_lines(self):
        frags = [("", "hi\n")]
        out = ptu.pad_lines_to_cells(frags, 5)
        assert _flatten(out) == "hi   \n"

    def test_pad_lines_to_cells_accounts_for_emoji_width(self):
        # Emoji is 2 cells, so " X" (where X is the emoji) is 3 cells total
        # and needs 2 trailing spaces to reach width 5.
        frags = [("", " \U0001f436\n")]
        out = ptu.pad_lines_to_cells(frags, 5)
        assert _flatten(out) == " \U0001f436  \n"

    def test_pad_lines_to_cells_zero_width_noop(self):
        frags = [("", "x\n")]
        assert ptu.pad_lines_to_cells(frags, 0) == frags


class TestRecomputeDimensions:
    def test_first_call_returns_true_and_sets_widths(self):
        menu = _make_menu()
        with patch.object(menu, "_measure_terminal", return_value=(120, 40)):
            changed = menu._recompute_dimensions()
        assert changed is True
        assert menu._menu_cols > 0
        assert menu._detail_cols > 0
        assert menu._last_size == (120, 40)

    def test_unchanged_size_is_noop(self):
        menu = _make_menu()
        with patch.object(menu, "_measure_terminal", return_value=(120, 40)):
            menu._recompute_dimensions()
            assert menu._recompute_dimensions() is False

    def test_resize_triggers_recompute(self):
        menu = _make_menu()
        with patch.object(menu, "_measure_terminal", return_value=(120, 40)):
            menu._recompute_dimensions()
            first_detail = menu._detail_cols
        with patch.object(menu, "_measure_terminal", return_value=(200, 50)):
            assert menu._recompute_dimensions() is True
        assert menu._detail_cols != first_detail
        assert menu._last_size == (200, 50)


class TestDetailScroll:
    def test_scroll_clamps_at_top(self):
        menu = _make_menu()
        menu._scroll_detail(-1)
        assert menu.detail_scroll == 0

    def test_scroll_down_then_up(self):
        menu = _make_menu()
        with patch.object(menu, "_max_detail_scroll", return_value=5):
            menu._scroll_detail(3)
            assert menu.detail_scroll == 3
            menu._scroll_detail(-1)
            assert menu.detail_scroll == 2

    def test_scroll_clamped_to_max(self):
        menu = _make_menu()
        with patch.object(menu, "_max_detail_scroll", return_value=2):
            menu._scroll_detail(10)
            assert menu.detail_scroll == 2

    def test_update_display_applies_scroll(self):
        from prompt_toolkit.layout.controls import FormattedTextControl

        menu = _make_menu()
        # Disable cell-padding and blank-row filling so this test stays focused
        # on slice behaviour.
        menu._menu_cols = 0
        menu._detail_cols = 0
        menu._pane_rows = 0
        menu.menu_control = FormattedTextControl(text="")
        menu.detail_control = FormattedTextControl(text="")
        # Patch the name as it's bound inside plugins_menu (which imported
        # ``render_detail`` at module-load time) so update_display() picks
        # up the stub.
        with patch(
            "code_puppy.plugins.plugin_list.plugins_menu.render_detail",
            return_value=[("", "l0\n"), ("", "l1\n"), ("", "l2\n")],
        ):
            menu.detail_scroll = 1
            menu.update_display()
        assert _flatten(menu.detail_control.text) == "l1\nl2\n"


class TestFillPane:
    def test_short_content_padded_to_pane_rows(self):
        # pane_cols=10 -> inner width = 8 (cols - 2 for frame border).
        out = fill_pane([("", "hi\n")], pane_cols=10, pane_rows=5)
        text = _flatten(out)
        # 5 rows total: 1 real (padded to 8 cells) + 4 blank (each 8 spaces).
        assert text.count("\n") == 5
        assert text.startswith("hi      \n")
        # Every blank row is 8 spaces.
        for line in text.split("\n")[1:-1]:
            assert line == " " * 8

    def test_content_already_full_height_not_extra_padded(self):
        out = fill_pane(
            [("", "a\n"), ("", "b\n"), ("", "c\n")], pane_cols=5, pane_rows=3
        )
        # 3 rows of content, 3 rows requested -> no extra blanks.
        assert _flatten(out).count("\n") == 3

    def test_content_without_trailing_newline_gets_one(self):
        out = fill_pane([("", "no-newline")], pane_cols=15, pane_rows=3)
        # Trailing \n added, then padded to 3 rows total.
        assert _flatten(out).count("\n") == 3
