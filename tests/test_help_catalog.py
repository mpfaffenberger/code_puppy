"""Content-assembly tests for the Tab-toggled help overlay (PUP-352).

help_catalog.py is an assembler over existing registries/callbacks, not a
new source of truth -- these tests mock those sources rather than relying
on whatever plugins happen to be installed on the machine running the
suite (see help_overlay.py's docstring / PLAN.md for the rationale).
"""

from unittest.mock import patch

from code_puppy.command_line.command_registry import CommandInfo
from code_puppy.command_line.help_catalog import (
    HelpEntry,
    HelpSection,
    _SECTION_ORDER,
    _keybinding_section,
    _modes_section,
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


def test_help_entry_and_section_are_simple_value_objects():
    entry = HelpEntry("left", "right")
    section = HelpSection("Title", [entry])
    assert section.title == "Title"
    assert section.entries == [entry]


def test_build_help_sections_always_includes_keybindings_and_modes():
    with patch(
        "code_puppy.command_line.command_registry.get_unique_commands",
        return_value=[],
    ), patch(
        "code_puppy.callbacks.on_custom_command_help",
        return_value=[],
    ), patch(
        "code_puppy.plugins.load_plugin_callbacks",
        return_value=None,
    ), patch(
        "code_puppy.agents.agent_manager.get_available_agents",
        return_value={},
    ):
        sections = build_help_sections()

    titles = [s.title for s in sections]
    assert "Keybindings" in titles
    assert "Modes & Passthrough" in titles


def test_help_sections_follow_the_curated_display_order():
    """Section order is a deliberate curated display order -- Session,
    Keybindings, Core, Modes & Passthrough, Configuration, MCP & Plugins,
    Plugin/Private, then Tool -- not build order or category-registration
    order. Uses one command per category so every section in
    ``_SECTION_ORDER`` actually appears, then checks the whole sequence."""
    commands = [
        _cmd("help", "Show help", category="core", usage="/help"),
        _cmd("set", "Set puppy config", category="config", usage="/set [key [value]]"),
        _cmd("clear", "Clear history", category="session", usage="/clear"),
        _cmd("grep", "Search files", category="tools", usage="/grep"),
        _cmd("wiggum", "A plugin command", category="plugin", usage="/wiggum"),
    ]
    with patch(
        "code_puppy.command_line.command_registry.get_unique_commands",
        return_value=commands,
    ), patch(
        "code_puppy.callbacks.on_custom_command_help",
        return_value=[],
    ), patch(
        "code_puppy.plugins.load_plugin_callbacks",
        return_value=None,
    ), patch(
        "code_puppy.agents.agent_manager.get_available_agents",
        return_value={},
    ):
        sections = build_help_sections()

    assert [s.title for s in sections] == list(_SECTION_ORDER)


def test_no_environment_variables_section():
    """Env vars are second-layer detail (shell config, not a command) --
    deliberately not documented in the cheat sheet. See module docstring."""
    with patch(
        "code_puppy.command_line.command_registry.get_unique_commands",
        return_value=[],
    ), patch(
        "code_puppy.callbacks.on_custom_command_help",
        return_value=[],
    ), patch(
        "code_puppy.plugins.load_plugin_callbacks",
        return_value=None,
    ), patch(
        "code_puppy.agents.agent_manager.get_available_agents",
        return_value={},
    ):
        sections = build_help_sections()

    titles = [s.title for s in sections]
    assert "Environment Variables" not in titles


def test_set_command_is_discoverable_as_a_first_layer_command():
    """``/set`` (the general settings entry point) must surface as its own
    top-layer command row -- most of its many sub-keys are self-explanatory
    once you're inside the interactive menu, so the cheat sheet doesn't
    enumerate them. YOLO mode is the one deliberate exception (see
    _modes_section) since it changes safety-prompt behavior in a way
    worth calling out up front."""
    commands = [
        _cmd(
            "set",
            "Set puppy config (e.g., /set yolo_mode true) or launch interactive menu",
            category="config",
            usage="/set [key [value]]",
        ),
    ]
    with patch(
        "code_puppy.command_line.command_registry.get_unique_commands",
        return_value=commands,
    ), patch(
        "code_puppy.callbacks.on_custom_command_help",
        return_value=[],
    ), patch(
        "code_puppy.plugins.load_plugin_callbacks",
        return_value=None,
    ), patch(
        "code_puppy.agents.agent_manager.get_available_agents",
        return_value={},
    ):
        sections = build_help_sections()

    by_title = {s.title: s for s in sections}
    config_section = by_title["Configuration Commands"]
    set_row = next(e for e in config_section.entries if e.left.startswith("/set"))
    assert "/set [key [value]]" in set_row.left


def test_modes_section_documents_yolo_mode():
    """YOLO mode skips confirmation prompts for destructive actions -- a
    safety-relevant behavior change worth surfacing up front rather than
    leaving buried as one of many /set sub-keys."""
    section = _modes_section()
    yolo_row = next(e for e in section.entries if e.left == "YOLO mode")
    assert "/set yolo_mode" in yolo_row.right


def test_builtin_commands_are_grouped_by_category_with_aliases_shown():
    commands = [
        _cmd("help", "Show help", category="core", usage="/help"),
        _cmd("session", "Show session", category="session", aliases=["s"]),
    ]
    with patch(
        "code_puppy.command_line.command_registry.get_unique_commands",
        return_value=commands,
    ), patch(
        "code_puppy.callbacks.on_custom_command_help",
        return_value=[],
    ), patch(
        "code_puppy.plugins.load_plugin_callbacks",
        return_value=None,
    ), patch(
        "code_puppy.agents.agent_manager.get_available_agents",
        return_value={},
    ):
        sections = build_help_sections()

    by_title = {s.title: s for s in sections}
    assert "Core Commands" in by_title
    assert any(e.left == "/help" for e in by_title["Core Commands"].entries)
    assert "Session Commands" in by_title
    session_entry = by_title["Session Commands"].entries[0]
    assert "/s" in session_entry.left  # alias surfaced for discoverability


def test_registry_plugin_category_merges_into_plugin_section_not_its_own():
    """Regression test (puppy-review validation finding): a registry
    command filed under category=\"plugin\" (real in the private fork's
    installed plugin set, invisible from a static read of the public tree)
    must land in the SAME \"Plugin / Private Commands\" section as
    callback-advertised commands -- not spawn its own bare \"Plugin\"
    heading sitting right above it. Two near-identical adjacent headings
    is exactly the confusion PUP-352 exists to remove."""
    commands = [
        _cmd("wiggum", "Registry-plugin command", category="plugin", usage="/wiggum"),
    ]
    with patch(
        "code_puppy.command_line.command_registry.get_unique_commands",
        return_value=commands,
    ), patch(
        "code_puppy.callbacks.on_custom_command_help",
        return_value=[("marketplace", "Browse the plugin marketplace")],
    ), patch(
        "code_puppy.plugins.load_plugin_callbacks",
        return_value=None,
    ), patch(
        "code_puppy.agents.agent_manager.get_available_agents",
        return_value={},
    ):
        sections = build_help_sections()

    titles = [s.title for s in sections]
    assert titles.count("Plugin / Private Commands") == 1
    assert "Plugin" not in [t for t in titles if t != "Plugin / Private Commands"]
    merged = next(s for s in sections if s.title == "Plugin / Private Commands")
    labels = [e.left for e in merged.entries]
    assert "/wiggum" in labels
    assert "/marketplace" in labels


def test_plugin_commands_use_flat_section_yagni_no_new_registry():
    with patch(
        "code_puppy.command_line.command_registry.get_unique_commands",
        return_value=[],
    ), patch(
        "code_puppy.callbacks.on_custom_command_help",
        return_value=[("marketplace", "Browse the plugin marketplace")],
    ), patch(
        "code_puppy.plugins.load_plugin_callbacks",
        return_value=None,
    ), patch(
        "code_puppy.agents.agent_manager.get_available_agents",
        return_value={},
    ):
        sections = build_help_sections()

    by_title = {s.title: s for s in sections}
    assert "Plugin / Private Commands" in by_title
    assert by_title["Plugin / Private Commands"].entries[0].left == "/marketplace"


def test_disabled_or_absent_plugin_commands_produce_no_empty_section():
    with patch(
        "code_puppy.command_line.command_registry.get_unique_commands",
        return_value=[],
    ), patch(
        "code_puppy.callbacks.on_custom_command_help",
        return_value=[],
    ), patch(
        "code_puppy.plugins.load_plugin_callbacks",
        return_value=None,
    ), patch(
        "code_puppy.agents.agent_manager.get_available_agents",
        return_value={},
    ):
        sections = build_help_sections()

    titles = [s.title for s in sections]
    assert "Plugin / Private Commands" not in titles


def test_agent_switching_is_documented_via_the_slash_command_not_a_roster():
    """Agent switching is deliberately documented ONLY via the /agent
    command entry that _builtin_command_sections() already surfaces from
    the core command registry -- no separate per-agent roster section.
    Mocking get_available_agents with a non-empty roster here proves the
    catalog doesn't even call it (no accidental roster leaking back in)."""
    with patch(
        "code_puppy.command_line.command_registry.get_unique_commands",
        return_value=[
            _cmd(
                "agent",
                "Switch to a different agent or show available agents",
                category="core",
                usage="/agent <name>, /a <name>",
                aliases=["a", "agents"],
            )
        ],
    ), patch(
        "code_puppy.callbacks.on_custom_command_help",
        return_value=[],
    ), patch(
        "code_puppy.plugins.load_plugin_callbacks",
        return_value=None,
    ), patch(
        "code_puppy.agents.agent_manager.get_available_agents",
        return_value={"code-puppy": "Code Puppy", "other-agent": "Other"},
    ) as mock_get_agents:
        sections = build_help_sections()

    titles = [s.title for s in sections]
    assert not any("Sub-Agent" in t for t in titles)
    mock_get_agents.assert_not_called()

    by_title = {s.title: s for s in sections}
    core = by_title["Core Commands"]
    agent_row = next(e for e in core.entries if e.left.startswith("/agent"))
    assert "/a" in agent_row.left  # alias surfaced, matches core_commands.py


def test_broken_custom_command_help_never_crashes_the_catalog():
    """A busted plugin's help callback must never take Tab down with it."""
    with patch(
        "code_puppy.command_line.command_registry.get_unique_commands",
        return_value=[],
    ), patch(
        "code_puppy.callbacks.on_custom_command_help",
        side_effect=RuntimeError("boom"),
    ), patch(
        "code_puppy.plugins.load_plugin_callbacks",
        return_value=None,
    ), patch(
        "code_puppy.agents.agent_manager.get_available_agents",
        side_effect=RuntimeError("boom"),
    ):
        sections = build_help_sections()  # must not raise

    assert any(s.title == "Keybindings" for s in sections)


def test_parse_custom_command_result_handles_single_tuple():
    assert _parse_custom_command_result(("marketplace", "Browse plugins")) == [
        ("marketplace", "Browse plugins")
    ]


def test_parse_custom_command_result_handles_list_of_tuples():
    result = _parse_custom_command_result([("foo", "Do foo"), ("bar", "Do bar")])
    assert result == [("foo", "Do foo"), ("bar", "Do bar")]


def test_parse_custom_command_result_strips_leading_slash_from_tuple_name():
    """A plugin returning ("/slashed", ...) must never render as //slashed
    in the cheat sheet -- see _plugin_command_section's f"/{name}"."""
    assert _parse_custom_command_result([("/slashed", "desc")]) == [
        ("slashed", "desc")
    ]


def test_parse_custom_command_result_handles_legacy_string_format():
    """Some plugins only implement the legacy list-of-strings shape (see
    command_handler.get_commands_help's Format 3) -- the cheat sheet must
    not silently drop those commands."""
    result = _parse_custom_command_result(["/legacy - The legacy way"])
    assert result == [("legacy", "The legacy way")]


def test_parse_custom_command_result_ignores_falsy_and_malformed_input():
    assert _parse_custom_command_result(None) == []
    assert _parse_custom_command_result([]) == []
    assert _parse_custom_command_result([42, "no dash here"]) == []


def test_parse_custom_command_result_legacy_format_requires_leading_slash():
    """A free-text string that merely contains \" - \" (e.g. usage prose in
    a longer help blob) must not be mistaken for a legacy command line --
    only lines that actually look like \"/name - description\" qualify."""
    result = _parse_custom_command_result(
        [
            "/legacy - The legacy way",
            "Note: use with --dry-run - to preview changes",
        ]
    )
    assert result == [("legacy", "The legacy way")]


def test_plugin_section_never_renders_double_slash_for_slash_prefixed_names():
    with patch(
        "code_puppy.command_line.command_registry.get_unique_commands",
        return_value=[],
    ), patch(
        "code_puppy.callbacks.on_custom_command_help",
        return_value=[[("/slashed", "desc")]],
    ), patch(
        "code_puppy.plugins.load_plugin_callbacks",
        return_value=None,
    ), patch(
        "code_puppy.agents.agent_manager.get_available_agents",
        return_value={},
    ):
        sections = build_help_sections()

    by_title = {s.title: s for s in sections}
    assert by_title["Plugin / Private Commands"].entries[0].left == "/slashed"


def test_keybinding_section_shows_ctrl_c_only_once_with_default_cancel_key():
    """Regression test: with the default cancel key (Ctrl+C -- true for the
    overwhelming majority of users, since remapping is opt-in via
    puppy.cfg), the section must show exactly ONE Ctrl+C row describing its
    real buffer-first behavior -- not two rows both labeled "Ctrl+C" with
    seemingly contradictory descriptions (one claiming 'clear the buffer',
    the other 'cancel the task'), which is what a live user actually hit."""
    with patch(
        "code_puppy.command_line.help_catalog.get_cancel_agent_display_name",
        return_value="Ctrl+C",
    ):
        section = _keybinding_section()

    ctrl_c_rows = [e for e in section.entries if e.left == "Ctrl+C"]
    assert len(ctrl_c_rows) == 1
    # The single row must mention BOTH real behaviors, not just one.
    assert "clear" in ctrl_c_rows[0].right.lower()
    assert "cancel" in ctrl_c_rows[0].right.lower()


def test_keybinding_section_shows_both_rows_when_cancel_key_is_remapped():
    """When the user has remapped the cancel key away from Ctrl+C, plain
    Ctrl+C keeps its own independent 'clear the line' meaning (confirmed in
    _key_listeners.py's dispatch fallthrough) -- that's genuinely different
    behavior worth a second, clearly-distinct row."""
    with patch(
        "code_puppy.command_line.help_catalog.get_cancel_agent_display_name",
        return_value="Ctrl+K",
    ):
        section = _keybinding_section()

    labels = [e.left for e in section.entries]
    assert labels.count("Ctrl+K") == 1
    assert labels.count("Ctrl+C") == 1
    ctrl_c_row = next(e for e in section.entries if e.left == "Ctrl+C")
    ctrl_k_row = next(e for e in section.entries if e.left == "Ctrl+K")
    assert ctrl_c_row.right != ctrl_k_row.right


def test_ctrl_k_documents_kill_to_eol_when_it_is_not_the_cancel_key():
    """With the default cancel key (Ctrl+C), Ctrl+K is unambiguously its
    real line_editor.py binding: kill-to-end-of-line."""
    with patch(
        "code_puppy.command_line.help_catalog.get_cancel_agent_display_name",
        return_value="Ctrl+C",
    ):
        section = _keybinding_section()

    ctrl_k_rows = [e for e in section.entries if e.left == "Ctrl+K"]
    assert len(ctrl_k_rows) == 1
    assert "end of the line" in ctrl_k_rows[0].right.lower()


def test_ctrl_k_kill_to_eol_row_suppressed_when_it_is_the_cancel_key():
    """Regression test (puppy-review validation finding): when the user
    has remapped the cancel key TO Ctrl+K, the key listener intercepts it
    before it ever reaches line_editor.py -- kill-to-end-of-line becomes
    genuinely unreachable in that state. Showing a stale 'kill to end of
    line' row right next to a 'cancel the task' row for the same label
    would recreate the exact Ctrl+C double-meaning bug this section was
    fixed for -- so there must be exactly ONE Ctrl+K row, and it must
    describe the cancel-key behavior, not the (now dead) editor binding."""
    with patch(
        "code_puppy.command_line.help_catalog.get_cancel_agent_display_name",
        return_value="Ctrl+K",
    ):
        section = _keybinding_section()

    ctrl_k_rows = [e for e in section.entries if e.left == "Ctrl+K"]
    assert len(ctrl_k_rows) == 1
    assert "end of the line" not in ctrl_k_rows[0].right.lower()
    assert "cancel" in ctrl_k_rows[0].right.lower()


def test_keybinding_section_documents_alt_enter_queue_submit():
    """Alt+Enter submits as a QUEUED turn (line_editor.py's
    self._submit(mode=\"queue\") on the ESC-then-Enter/Ctrl+J path) -- a
    real, distinct capability from plain Enter that had no cheat-sheet
    coverage at all."""
    section = _keybinding_section()
    assert any(e.left == "Alt+Enter" for e in section.entries)


def test_keybinding_section_documents_line_editing_keys():
    """Ctrl+A/E (jump home/end), Ctrl+U (clear buffer), Ctrl+W (delete
    word back), Ctrl+R (reverse search), and word-jump (Ctrl/Option+arrow,
    Meta-b/f) are all real, live bindings in line_editor.py /
    editor_actions.py / editor_keys.py that had zero cheat-sheet coverage
    before this fix (puppy-review validation finding)."""
    section = _keybinding_section()
    labels = " | ".join(e.left for e in section.entries)
    assert "Ctrl+A" in labels
    assert "Ctrl+E" in labels
    assert "Ctrl+U" in labels
    assert "Ctrl+W" in labels
    assert "Ctrl+R" in labels
    assert "word" in " ".join(e.right.lower() for e in section.entries)


def test_keybinding_section_documents_shift_tab():
    """Shift+Tab already cycles completions backward (CSI 'Z' -> 'shift_tab'
    in editor_keys.py / editor_actions.py) -- a real, pre-existing
    capability that must show up in an 'all capabilities' cheat sheet."""
    section = _keybinding_section()
    assert any("Shift+Tab" in e.left for e in section.entries)


def test_keybinding_section_documents_all_three_newline_gestures():
    """Ctrl+J, Shift+Enter, AND Ctrl+Enter all insert a newline (see
    editor_keys.py's CSI-action table mapping both Shift+Enter and
    Ctrl+Enter escape sequences to the same 'newline' action, plus
    line_editor.py's unconditional Ctrl+J handling, plus the 'c-j' /
    'c-enter' bindings in prompt_toolkit_completion.py). A cheat sheet
    that only lists one of the three -- as this one originally did,
    omitting the single most reliable option -- misleads users on
    terminals where the escape-sequence-based gestures don't arrive."""
    section = _keybinding_section()
    newline_row = next(e for e in section.entries if "newline" in e.right.lower())
    assert "Ctrl+J" in newline_row.left
    assert "Shift+Enter" in newline_row.left
    assert "Ctrl+Enter" in newline_row.left
