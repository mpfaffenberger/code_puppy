"""Tests for puppy_spinner customization: catalogue, user file, /spinner.

The animation lifecycle itself is covered by ``test_puppy_spinner.py``;
this file covers the style layer added around it -- builtin catalogue,
``spinners.json`` parsing, persistence, and the ``/spinner`` command.
"""

from __future__ import annotations

import json

import pytest
from rich.cells import cell_len

from code_puppy.plugins.puppy_spinner import commands as cmds
from code_puppy.plugins.puppy_spinner import picker
from code_puppy.plugins.puppy_spinner import register_callbacks as rc
from code_puppy.plugins.puppy_spinner import spinners as sp


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    """Point config + user file at scratch space; reset the cache."""
    store: dict[str, str] = {}
    monkeypatch.setattr(sp, "get_value", store.get)
    monkeypatch.setattr(sp, "set_value", store.__setitem__)
    monkeypatch.setattr(sp, "USER_SPINNERS_FILE", str(tmp_path / "spinners.json"))
    monkeypatch.setattr(sp, "CONFIG_DIR", str(tmp_path))
    sp.invalidate_cache()
    yield store
    sp.invalidate_cache()


def _write_user_file(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


# =========================================================================
# Builtin catalogue
# =========================================================================


def test_builtins_include_the_puppy_pack():
    for name in ("puppy", "bone", "zoomies", "paws", "dots"):
        assert name in sp.BUILTIN_SPINNERS


def test_builtins_include_the_cli_spinners_pack():
    for name in (
        "dots8Bit",
        "dotsWide",
        "chevrons",
        "bouncingBall",
        "sand",
        "pong",
        "aesthetic",
    ):
        assert name in sp.BUILTIN_SPINNERS


def test_every_builtin_defaults_to_point_two_except_the_classic():
    """One speed to rule them all -- per-spinner tuning is what the
    picker's speed keys and spinners.json tweaks are for. The default
    puppy is the lone exception: the kennel bounce trots at 0.06s.
    """
    for spinner in sp.BUILTIN_SPINNERS.values():
        expected = 0.06 if spinner.name == sp.DEFAULT_SPINNER else 0.2
        assert spinner.interval == pytest.approx(expected), spinner.name


def test_tick_interval_follows_the_puppy_default():
    """rc sources its fallback tempo from the catalogue, so the puppy's
    0.06s default and the tick loop can never disagree.
    """
    assert rc._TICK_INTERVAL_S == pytest.approx(0.06)
    assert rc._TICK_INTERVAL_S == sp.BUILTIN_SPINNERS[sp.DEFAULT_SPINNER].interval


def test_paint_gap_separates_frame_from_status(monkeypatch):
    """Non-empty frames get the gap appended; clearing paints a true
    empty string so nothing lingers in the prefix slot.
    """
    painted = []

    class FakeBar:
        def set_status_prefix(self, text):
            painted.append(text)

    monkeypatch.setattr(
        "code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: FakeBar()
    )
    rc._paint_prefix("(x) ")
    rc._clear_prefix()
    assert painted == ["(x) " + rc._PREFIX_GAP, ""]


def test_catalogue_is_alphabetical():
    names = list(sp.get_catalogue())
    assert names == sorted(names, key=str.lower)


def test_aesthetic_drains_to_all_hollow():
    """The cycle ends empty (all hollow), not snapped back to one-filled."""
    frames = sp.BUILTIN_SPINNERS["aesthetic"].frames
    assert frames[-1] == "\u25b1" * 7
    assert "\u25b0" not in frames[-1]


def test_cli_spinners_pack_has_descriptions():
    from code_puppy.plugins.puppy_spinner.builtin_frames import EXTRA_SPECS

    for name in EXTRA_SPECS:
        assert sp.BUILTIN_SPINNERS[name].description, name


def test_builtin_frames_are_uniform_cell_width_and_sane():
    """Uniform *cell* width, not len(): emoji are 2 cells but 1 char, and
    unequal display widths would make text after the spinner jump.
    """
    for spinner in sp.BUILTIN_SPINNERS.values():
        assert spinner.frames, spinner.name
        assert len({cell_len(f) for f in spinner.frames}) == 1, spinner.name
        assert 0.02 <= spinner.interval <= 1.0, spinner.name
        assert spinner.source == "builtin"


def test_paws_frames_share_cell_width_despite_unequal_len():
    """paws mixes 2-cell emoji counts per frame, so it's the canary for
    cell-width (not len-based) padding: equal display width, unequal len.
    """
    frames = sp.BUILTIN_SPINNERS["paws"].frames
    assert len({cell_len(f) for f in frames}) == 1
    assert len({len(f) for f in frames}) > 1


def test_default_spinner_matches_rc_frames():
    """DRY check: rc.FRAMES *is* the catalogue's puppy entry."""
    assert rc.FRAMES == sp.BUILTIN_SPINNERS[sp.DEFAULT_SPINNER].frames


# =========================================================================
# User spinners (spinners.json)
# =========================================================================


def test_missing_user_file_means_no_user_spinners():
    assert sp.load_user_spinners() == {}


def test_valid_user_spinner_is_loaded_and_padded():
    _write_user_file(
        sp.USER_SPINNERS_FILE,
        {"blinky": {"frames": ["*", "**", "***"], "interval": 0.2, "description": "d"}},
    )
    loaded = sp.load_user_spinners()
    assert set(loaded) == {"blinky"}
    blinky = loaded["blinky"]
    assert blinky.frames == ("*  ", "** ", "***")  # padded to width 3
    assert blinky.interval == 0.2
    assert blinky.source == "user"


def test_bad_entries_are_skipped_and_interval_clamped():
    _write_user_file(
        sp.USER_SPINNERS_FILE,
        {
            "no-frames": {"interval": 0.1},
            "empty-frames": {"frames": []},
            "not-an-object": ["a", "b"],
            "turbo": {"frames": ["a", "b"], "interval": 0.000001},
            "sloth": {"frames": ["a", "b"], "interval": 99},
        },
    )
    loaded = sp.load_user_spinners()
    assert set(loaded) == {"turbo", "sloth"}
    assert loaded["turbo"].interval == pytest.approx(0.02)  # clamped up
    assert loaded["sloth"].interval == pytest.approx(1.0)  # clamped down


def test_missing_interval_defaults_to_point_two():
    _write_user_file(sp.USER_SPINNERS_FILE, {"lazy": {"frames": ["a", "b"]}})
    assert sp.load_user_spinners()["lazy"].interval == pytest.approx(0.2)


def test_boolean_interval_is_rejected_not_one_second():
    """JSON `true` is an int subclass and float(True) == 1.0 -- accepting
    it would mean a silent 1-second spinner instead of the default.
    """
    _write_user_file(
        sp.USER_SPINNERS_FILE, {"boolish": {"frames": ["a", "b"], "interval": True}}
    )
    assert sp.load_user_spinners()["boolish"].interval == pytest.approx(0.2)


def test_broken_json_degrades_to_empty():
    with open(sp.USER_SPINNERS_FILE, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    assert sp.load_user_spinners() == {}


# =========================================================================
# Builtin tweaks: frameless entries that re-speed a builtin
# =========================================================================


def test_frameless_builtin_entry_inherits_frames_and_overrides_speed():
    _write_user_file(sp.USER_SPINNERS_FILE, {"zoomies": {"interval": 0.5}})
    tweaked = sp.get_catalogue()["zoomies"]
    assert tweaked.frames == sp.BUILTIN_SPINNERS["zoomies"].frames
    assert tweaked.interval == pytest.approx(0.5)
    assert tweaked.description == sp.BUILTIN_SPINNERS["zoomies"].description
    assert tweaked.source == "builtin+user"


def test_tweak_can_override_description_only():
    _write_user_file(
        sp.USER_SPINNERS_FILE, {"sand": {"description": "my custom blurb"}}
    )
    tweaked = sp.get_catalogue()["sand"]
    assert tweaked.description == "my custom blurb"
    assert tweaked.interval == sp.BUILTIN_SPINNERS["sand"].interval


def test_tweak_interval_is_validated_and_clamped():
    _write_user_file(sp.USER_SPINNERS_FILE, {"sand": {"interval": 99}})
    assert sp.get_catalogue()["sand"].interval == pytest.approx(sp.MAX_INTERVAL)


def test_tweak_overriding_nothing_is_skipped():
    _write_user_file(sp.USER_SPINNERS_FILE, {"sand": {}})
    untouched = sp.get_catalogue()["sand"]
    assert untouched.source == "builtin"


def test_frameless_entry_for_unknown_name_is_skipped():
    _write_user_file(sp.USER_SPINNERS_FILE, {"no-such": {"interval": 0.5}})
    assert "no-such" not in sp.get_catalogue()


def test_tick_loop_uses_json_tweak_of_puppy():
    """A frameless re-speed of the default puppy must not route through
    the module constants (source is 'builtin+user', not 'builtin').
    """
    _write_user_file(sp.USER_SPINNERS_FILE, {"puppy": {"interval": 0.4}})
    sp.invalidate_cache()
    frames, interval = rc._current_frames_and_interval()
    assert frames == sp.BUILTIN_SPINNERS["puppy"].frames
    assert interval == pytest.approx(0.4)


def test_user_spinner_overrides_builtin_in_catalogue():
    _write_user_file(
        sp.USER_SPINNERS_FILE, {"puppy": {"frames": ["custom"], "interval": 0.5}}
    )
    catalogue = sp.get_catalogue()
    assert catalogue["puppy"].source == "user"
    assert catalogue["puppy"].frames == ("custom",)


def test_write_template_creates_once():
    assert sp.write_template() is True
    assert sp.load_user_spinners()  # template parses
    assert sp.write_template() is False  # never clobbers


# =========================================================================
# Active spinner: persistence + fallback
# =========================================================================


def test_default_active_is_the_puppy():
    assert sp.get_active_spinner().name == sp.DEFAULT_SPINNER


def test_set_active_persists_and_caches(isolated_config):
    spinner = sp.set_active("dots")
    assert spinner.name == "dots"
    assert isolated_config[sp.CONFIG_KEY] == "dots"
    assert sp.get_active_spinner().name == "dots"


def test_set_active_rejects_unknown_names():
    with pytest.raises(KeyError):
        sp.set_active("does-not-exist")


def test_unknown_configured_name_falls_back_to_default(isolated_config):
    isolated_config[sp.CONFIG_KEY] = "vanished"
    sp.invalidate_cache()
    assert sp.get_active_spinner().name == sp.DEFAULT_SPINNER


def test_user_file_stamp_tracks_the_file():
    """The mtime signal shared by the tick loop and the open picker."""
    assert sp.user_file_stamp() is None  # no file yet
    _write_user_file(sp.USER_SPINNERS_FILE, {"x": {"frames": ["a"]}})
    assert sp.user_file_stamp() is not None


def test_active_spinner_follows_external_file_edits():
    """Editing spinners.json needs no reload: the active-spinner cache
    self-invalidates on the file's mtime, so even the mid-run animation
    picks up edits on the next frame.
    """
    import os

    sp.set_active("zoomies")
    assert sp.get_active_spinner().interval == pytest.approx(0.2)

    _write_user_file(sp.USER_SPINNERS_FILE, {"zoomies": {"interval": 0.9}})
    # belt-and-braces: guarantee the mtime moves even on coarse filesystems
    stat = os.stat(sp.USER_SPINNERS_FILE)
    os.utime(sp.USER_SPINNERS_FILE, (stat.st_atime, stat.st_mtime + 1))

    assert sp.get_active_spinner().interval == pytest.approx(0.9)  # no reload

    os.remove(sp.USER_SPINNERS_FILE)  # deleting the file also counts as an edit
    assert sp.get_active_spinner().interval == pytest.approx(0.2)


# =========================================================================
# Saving speeds to spinners.json: one source of truth
# =========================================================================


def test_set_active_with_interval_saves_into_spinners_json():
    """A dialed speed is just a saved value in user land -- the file is
    the single source of truth, no shadow override layer.
    """
    spinner = sp.set_active("sand", 0.45)
    assert spinner.interval == pytest.approx(0.45)
    with open(sp.USER_SPINNERS_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["sand"]["interval"] == pytest.approx(0.45)
    sp.invalidate_cache()  # survives a cold re-read
    assert sp.get_active_spinner().interval == pytest.approx(0.45)


def test_saved_speed_sticks_when_switching_spinners():
    """Applying another spinner doesn't erase a saved speed -- it lives
    in spinners.json until the user changes it again.
    """
    sp.set_active("sand", 0.45)
    spinner = sp.set_active("dots")
    assert spinner.interval == sp.BUILTIN_SPINNERS["dots"].interval
    assert sp.get_catalogue()["sand"].interval == pytest.approx(0.45)


def test_save_preserves_existing_entry_keys():
    """Re-speeding a full user spinner must not clobber its frames."""
    _write_user_file(
        sp.USER_SPINNERS_FILE,
        {"blinker": {"frames": ["x", "y"], "description": "blink"}},
    )
    sp.set_active("blinker", 0.5)
    with open(sp.USER_SPINNERS_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["blinker"]["frames"] == ["x", "y"]
    assert data["blinker"]["description"] == "blink"
    assert data["blinker"]["interval"] == pytest.approx(0.5)


def test_saved_interval_is_clamped():
    assert sp.set_active("sand", 99).interval == pytest.approx(sp.MAX_INTERVAL)
    assert sp.set_active("sand", 0.001).interval == pytest.approx(sp.MIN_INTERVAL)


def test_unwritable_file_still_honors_speed_for_the_session(tmp_path):
    """A corrupt spinners.json is never overwritten; the requested speed
    still applies for the session instead of being silently dropped.
    """
    with open(sp.USER_SPINNERS_FILE, "w", encoding="utf-8") as fh:
        fh.write("this is not json{")
    spinner = sp.set_active("sand", 0.45)
    assert spinner.interval == pytest.approx(0.45)  # session honors it
    with open(sp.USER_SPINNERS_FILE, encoding="utf-8") as fh:
        assert fh.read() == "this is not json{"  # file left untouched


# =========================================================================
# Ticker integration: the loop respects the active style
# =========================================================================


def test_tick_loop_uses_default_module_constants_by_default():
    frames, interval = rc._current_frames_and_interval()
    assert frames is rc.FRAMES
    assert interval == rc._TICK_INTERVAL_S


def test_tick_loop_uses_selected_spinner():
    sp.set_active("binary")
    frames, interval = rc._current_frames_and_interval()
    assert frames == sp.BUILTIN_SPINNERS["binary"].frames
    assert interval == sp.BUILTIN_SPINNERS["binary"].interval


def test_tick_loop_honors_speed_override_on_the_default_puppy():
    """A custom speed on the stock puppy must NOT route through the
    module constants (which would silently drop the override).
    """
    sp.set_active(sp.DEFAULT_SPINNER, 0.5)
    frames, interval = rc._current_frames_and_interval()
    assert frames == sp.BUILTIN_SPINNERS[sp.DEFAULT_SPINNER].frames
    assert interval == pytest.approx(0.5)


def test_tick_loop_uses_user_override_of_puppy():
    _write_user_file(
        sp.USER_SPINNERS_FILE, {"puppy": {"frames": ["custom"], "interval": 0.5}}
    )
    sp.invalidate_cache()
    frames, interval = rc._current_frames_and_interval()
    assert frames == ("custom",)
    assert interval == 0.5


# =========================================================================
# /spinner command handler
# =========================================================================


@pytest.fixture
def emitted(monkeypatch):
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(cmds, "emit_info", lambda m: messages.append(("info", m)))
    monkeypatch.setattr(cmds, "emit_warning", lambda m: messages.append(("warn", m)))
    monkeypatch.setattr(cmds, "emit_error", lambda m: messages.append(("error", m)))
    return messages


def test_handler_ignores_other_commands(emitted):
    assert cmds.handle_spinner("/theme", "theme") is None
    assert emitted == []


def test_apply_by_name(emitted):
    assert cmds.handle_spinner("/spinner sand", "spinner") is True
    assert sp.get_active_spinner().name == "sand"
    assert emitted[-1][0] == "info"


def test_apply_by_name_is_case_insensitive(emitted):
    """The command path lowercases args; camelCase names must still hit."""
    assert cmds.handle_spinner("/spinner dotswide", "spinner") is True
    assert sp.get_active_spinner().name == "dotsWide"


def test_apply_by_name_with_speed(emitted):
    assert cmds.handle_spinner("/spinner sand 0.4", "spinner") is True
    active = sp.get_active_spinner()
    assert active.name == "sand"
    assert active.interval == pytest.approx(0.4)
    assert "speed saved to spinners.json" in emitted[-1][1]


def test_apply_with_bad_speed_warns(emitted):
    assert cmds.handle_spinner("/spinner sand fast", "spinner") is True
    assert emitted[-1][0] == "warn"
    assert sp.get_active_spinner().name == sp.DEFAULT_SPINNER  # unchanged


def test_apply_unknown_name_warns(emitted):
    assert cmds.handle_spinner("/spinner bogus", "spinner") is True
    assert sp.get_active_spinner().name == sp.DEFAULT_SPINNER
    assert emitted[-1][0] == "warn"
    assert "bogus" in emitted[-1][1]


def test_init_template_is_usable_immediately(emitted):
    assert cmds.handle_spinner("/spinner init", "spinner") is True
    assert "sniffer" in sp.get_catalogue()  # no reload step required


def test_help_entries_advertise_the_command():
    entries = cmds.help_entries()
    assert any(name == "spinner" for name, _ in entries)


# =========================================================================
# Picker menu: plugins-menu style pagination
# =========================================================================


def _menu_text(entries, selected, page, active="puppy"):
    fragments = picker._format_menu(entries, selected, page, active)
    return "".join(text for _, text in fragments)


def _many_spinners(count):
    return [
        sp.Spinner(
            name=f"s{i:02d}", frames=("x",), interval=0.1, description="zzz-blurb"
        )
        for i in range(count)
    ]


def test_menu_shows_only_the_current_page():
    entries = _many_spinners(picker.PAGE_SIZE + 5)
    page0 = _menu_text(entries, 0, 0)
    assert "s00" in page0
    assert f"s{picker.PAGE_SIZE:02d}" not in page0  # first entry of page 2

    page1 = _menu_text(entries, picker.PAGE_SIZE, 1)
    assert f"s{picker.PAGE_SIZE:02d}" in page1
    assert "s00" not in page1


def test_menu_always_shows_page_info_like_plugins_menu():
    few = _many_spinners(3)
    assert "Page 1/1" in _menu_text(few, 0, 0)

    many = _many_spinners(picker.PAGE_SIZE + 1)
    assert "Page 1/2" in _menu_text(many, 0, 0)


def test_menu_advertises_plugins_menu_keys():
    text = _menu_text(_many_spinners(2), 0, 0)
    hints = (
        "up/down or j/k",
        "PgUp/PgDn",
        "g / G",
        "-/+",
        "Init spinners.json",
        "Enter",
        "q / Esc",
    )
    for hint in hints:
        assert hint in text


def test_preview_refresh_keeps_up_with_the_fastest_spinner():
    """The animator's cadence must match the speed floor, or a spinner
    dialed to MIN_INTERVAL would preview slower than it actually runs.
    """
    assert picker._REFRESH_INTERVAL_S == sp.MIN_INTERVAL


def test_hint_block_aligns_and_fits_the_pane():
    """Every key column is the same width (so the action column lines
    up), and the widest row fits the menu pane without truncation.
    """
    lines: list[tuple[str, str]] = []
    picker._render_hints(lines)
    keys = [text for _, text in lines[1::2]]
    labels = [text.rstrip("\n") for _, text in lines[2::2]]
    assert len(keys) == len(labels) == len(picker._HINTS)
    assert all(style == "class:tui.help" for style, _ in lines[2::2])
    assert [style for style, _ in lines[1::2]][-2:] == [
        "class:tui.success",
        "class:tui.error",
    ]
    assert len({cell_len(k) for k in keys}) == 1  # one aligned column
    widest = max(cell_len(k) + cell_len(lbl) for k, lbl in zip(keys, labels))
    assert widest <= 36  # the left Window's width -- no guillotined labels


def test_picker_fragments_use_shared_semantic_roles():
    entries = _many_spinners(2)
    menu = list(picker._format_menu(entries, 0, 0, active=entries[1].name))
    assert ("class:tui.header", " Spinners") in menu
    assert any(style == "class:tui.selected" for style, _ in menu)
    assert any(style == "class:tui.success" for style, _ in menu)
    assert any(style == "class:tui.muted" for style, _ in menu)

    preview = list(picker._format_preview(entries[0], 0, interval=0.2, notice="Saved"))
    styles = {style for style, _ in preview}
    assert {
        "class:tui.title",
        "class:tui.label",
        "class:tui.body",
        "class:tui.muted",
        "class:tui.warning",
    } <= styles


def test_speed_step_matches_the_clamp_floor():
    """Step == MIN_INTERVAL, so the floor is a grid point: no off-grid
    clamp artifacts, and every value the keys produce is reachable in
    reverse.
    """
    assert picker._SPEED_STEP_S == sp.MIN_INTERVAL


def test_step_interval_clamps_both_ends():
    step = picker._SPEED_STEP_S
    assert picker._step_interval(0.2, +step) == pytest.approx(0.22)
    assert picker._step_interval(0.2, -step) == pytest.approx(0.18)
    assert picker._step_interval(sp.MIN_INTERVAL, -step) == sp.MIN_INTERVAL
    assert picker._step_interval(sp.MAX_INTERVAL, +step) == sp.MAX_INTERVAL


def test_step_down_to_the_floor_and_back_walks_the_same_grid():
    """Down to the floor and back up retraces the exact same values --
    no drift (the old 0.05 grid turned the 0.02 floor into a permanent
    off-grid offset: 0.02 -> 0.07 -> 0.12 -> ...).
    """
    step = picker._SPEED_STEP_S
    value = 0.08
    seen = []
    for _ in range(5):  # 0.06, 0.04, 0.02, floor, floor
        value = picker._step_interval(value, -step)
        seen.append(value)
    assert seen[-1] == sp.MIN_INTERVAL
    for expected in (0.04, 0.06, 0.08):
        value = picker._step_interval(value, +step)
        assert value == pytest.approx(expected)


def test_step_interval_folds_off_grid_values_onto_the_grid():
    # e.g. a 0.147s spinners.json tweak: first nudge snaps to the lattice
    step = picker._SPEED_STEP_S
    assert picker._step_interval(0.147, +step) == pytest.approx(0.16)
    assert picker._step_interval(0.147, -step) == pytest.approx(0.12)


def test_preview_marks_custom_speed():
    spinner = sp.Spinner(name="demo", frames=("x",), interval=0.1)
    text = "".join(t for _, t in picker._format_preview(spinner, 0.0, 0.3))
    assert "0.30s" in text
    assert "Enter saves it" in text
    plain = "".join(t for _, t in picker._format_preview(spinner, 0.0))
    assert "Enter saves it" not in plain


def test_preview_shows_notice_when_given():
    spinner = sp.Spinner(name="demo", frames=("x",), interval=0.1)
    text = "".join(
        t for _, t in picker._format_preview(spinner, 0.0, notice="file written!")
    )
    assert "file written!" in text
    plain = "".join(t for _, t in picker._format_preview(spinner, 0.0))
    assert "file written!" not in plain


def test_menu_marks_selection_and_active_like_plugins_menu():
    entries = _many_spinners(3)
    text = _menu_text(entries, 1, 0, active="s02")
    assert " > " in text  # selection marker
    assert "* s02" in text  # active glyph in the status column
    # Descriptions belong to the preview pane now, not the list.
    assert "zzz-blurb" not in text


def test_preview_carries_the_description():
    spinner = sp.Spinner(
        name="demo", frames=("x",), interval=0.1, description="zzz-blurb"
    )
    fragments = picker._format_preview(spinner, 0.0)
    text = "".join(t for _, t in fragments)
    assert "zzz-blurb" in text
    assert "LIVE PREVIEW" in text
