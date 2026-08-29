"""Content-assembly tests for the Tab-toggled help overlay.

help_catalog.py assembles content from the command registry and plugin
callbacks, so these tests mock those sources rather than depending on
whichever plugins happen to be installed on the machine running the suite.
"""

from unittest.mock import patch

import pytest

from code_puppy.command_line.command_registry import CommandInfo
from code_puppy.command_line.help_catalog import (
    _SECTION_ORDER,
    _keybinding_section,
    _parse_custom_command_result,
    build_help_sections,
)


def _cmd(name, description, category="core", aliases=None, usage=""):
    return CommandInfo(
        name=name,
        description=description,
        handler=lambda command: True,
        usage=usage,
        aliases=aliases or [],
        category=category,
    )


def _build(commands=(), custom_help=()):
    """Build sections against mocked registry + plugin-callback sources."""
    with (
        patch(
            "code_puppy.command_line.command_registry.get_unique_commands",
            return_value=list(commands),
        ),
        patch(
            "code_puppy.callbacks.on_custom_command_help",
            return_value=list(custom_help),
        ),
        patch("code_puppy.plugins.load_plugin_callbacks", return_value=None),
    ):
        return build_help_sections()


def test_static_sections_survive_an_empty_command_registry():
    titles = [s.title for s in _build()]
    assert "Keybindings" in titles
    assert "Modes & Passthrough" in titles


def test_sections_follow_the_curated_display_order():
    commands = [
        _cmd("help", "Show help", category="core", usage="/help"),
        _cmd("set", "Set config", category="config", usage="/set [key [value]]"),
        _cmd("clear", "Clear history", category="session", usage="/clear"),
        _cmd("grep", "Search files", category="tools", usage="/grep"),
        _cmd("wiggum", "A plugin command", category="plugin", usage="/wiggum"),
    ]
    assert [s.title for s in _build(commands)] == list(_SECTION_ORDER)


def test_commands_are_grouped_by_category_with_aliases_shown():
    commands = [
        _cmd("help", "Show help", category="core", usage="/help"),
        _cmd("session", "Show session", category="session", aliases=["s"]),
    ]
    by_title = {s.title: s for s in _build(commands)}

    assert any(e.left == "/help" for e in by_title["Core Commands"].entries)
    assert "/s" in by_title["Session Commands"].entries[0].left


def test_registry_plugin_category_merges_into_the_callback_plugin_section():
    """A registry command filed under category="plugin" must land in the
    same section as callback-advertised commands, not spawn a second,
    near-identical "Plugin" heading directly above it.
    """
    sections = _build(
        commands=[
            _cmd("wiggum", "Registry plugin", category="plugin", usage="/wiggum")
        ],
        custom_help=[("marketplace", "Browse the plugin marketplace")],
    )

    titles = [s.title for s in sections]
    assert titles.count("Plugin / Private Commands") == 1
    assert "Plugin" not in titles
    merged = next(s for s in sections if s.title == "Plugin / Private Commands")
    assert {"/wiggum", "/marketplace"} <= {e.left for e in merged.entries}


def test_no_plugin_commands_means_no_empty_plugin_section():
    assert "Plugin / Private Commands" not in [s.title for s in _build()]


def test_slash_prefixed_plugin_names_do_not_render_a_double_slash():
    by_title = {s.title: s for s in _build(custom_help=[[("/slashed", "desc")]])}
    assert by_title["Plugin / Private Commands"].entries[0].left == "/slashed"


def test_a_broken_plugin_help_callback_never_crashes_the_catalog():
    with (
        patch(
            "code_puppy.command_line.command_registry.get_unique_commands",
            return_value=[],
        ),
        patch(
            "code_puppy.callbacks.on_custom_command_help",
            side_effect=RuntimeError("boom"),
        ),
        patch("code_puppy.plugins.load_plugin_callbacks", return_value=None),
    ):
        sections = build_help_sections()

    assert any(s.title == "Keybindings" for s in sections)


@pytest.mark.parametrize(
    "raw, expected",
    [
        (("marketplace", "Browse plugins"), [("marketplace", "Browse plugins")]),
        (
            [("foo", "Do foo"), ("bar", "Do bar")],
            [("foo", "Do foo"), ("bar", "Do bar")],
        ),
        ([("/slashed", "desc")], [("slashed", "desc")]),
        (["/legacy - The legacy way"], [("legacy", "The legacy way")]),
        # Prose that merely contains " - " is not a legacy command line.
        (["Note: use --dry-run - to preview"], []),
        (None, []),
        ([], []),
        ([42, "no dash here"], []),
    ],
)
def test_parse_custom_command_result_tolerates_every_callback_shape(raw, expected):
    assert _parse_custom_command_result(raw) == expected


def test_ctrl_c_gets_one_combined_row_when_it_is_the_cancel_key():
    """Two rows both labelled "Ctrl+C" with contradictory descriptions is
    the exact confusion a live user hit, so the single row has to describe
    both real behaviours.
    """
    with patch(
        "code_puppy.command_line.help_catalog.get_cancel_agent_display_name",
        return_value="Ctrl+C",
    ):
        section = _keybinding_section()

    rows = [e for e in section.entries if e.left == "Ctrl+C"]
    assert len(rows) == 1
    assert "clear" in rows[0].right.lower()
    assert "cancel" in rows[0].right.lower()


def test_remapped_cancel_key_gives_ctrl_c_its_own_distinct_row():
    """Once cancel is remapped, plain Ctrl+C keeps its independent
    clear-the-line meaning, which is genuinely separate behaviour.
    """
    with patch(
        "code_puppy.command_line.help_catalog.get_cancel_agent_display_name",
        return_value="Ctrl+K",
    ):
        section = _keybinding_section()

    labels = [e.left for e in section.entries]
    assert labels.count("Ctrl+C") == 1
    assert labels.count("Ctrl+K") == 1
    rows = {e.left: e.right for e in section.entries}
    assert rows["Ctrl+C"] != rows["Ctrl+K"]


@pytest.mark.parametrize(
    "cancel_key, expect_kill_to_eol",
    [("Ctrl+C", True), ("Ctrl+K", False)],
)
def test_ctrl_k_documents_kill_to_eol_only_when_it_reaches_the_editor(
    cancel_key, expect_kill_to_eol
):
    """When Ctrl+K is the cancel key the listener intercepts it before the
    editor sees it, so kill-to-end-of-line is genuinely unreachable and
    must not be advertised.
    """
    with patch(
        "code_puppy.command_line.help_catalog.get_cancel_agent_display_name",
        return_value=cancel_key,
    ):
        section = _keybinding_section()

    rows = [e for e in section.entries if e.left == "Ctrl+K"]
    assert len(rows) == 1
    assert ("end of the line" in rows[0].right.lower()) is expect_kill_to_eol
