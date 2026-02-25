"""Tests for code_puppy/plugins/agent_skills/skills_menu.py"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from code_puppy.plugins.agent_skills.discovery import SkillInfo
from code_puppy.plugins.agent_skills.metadata import SkillMetadata

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_skill(name="skill-a", path="/tmp/skills/skill-a"):
    return SkillInfo(name=name, path=Path(path), has_skill_md=True)


def _make_metadata(
    name="skill-a", desc="A skill", tags=None, path="/tmp/skills/skill-a"
):
    return SkillMetadata(
        name=name,
        description=desc,
        path=Path(path),
        tags=tags or ["tag1", "tag2"],
    )


# Patch targets (module under test)
_MOD = "code_puppy.plugins.agent_skills.skills_menu"


# ---------------------------------------------------------------------------
# SkillsMenu unit tests (no TUI)
# ---------------------------------------------------------------------------


class TestSkillsMenuInit:
    """Test SkillsMenu initialization and data methods."""

    @patch(f"{_MOD}.get_skills_enabled", return_value=True)
    @patch(f"{_MOD}.get_skill_directories", return_value=[])
    @patch(f"{_MOD}.get_disabled_skills", return_value=["disabled-one"])
    @patch(f"{_MOD}.discover_skills", return_value=[])
    def test_init_empty(self, mock_disc, mock_dis, mock_dirs, mock_en):
        from code_puppy.plugins.agent_skills.skills_menu import SkillsMenu

        menu = SkillsMenu()
        assert menu.skills == []
        assert menu.skills_enabled is True
        assert menu.disabled_skills == ["disabled-one"]

    @patch(f"{_MOD}.get_skills_enabled", return_value=False)
    @patch(f"{_MOD}.get_skill_directories", return_value=[])
    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(f"{_MOD}.discover_skills", side_effect=RuntimeError("boom"))
    def test_init_refresh_error(self, *mocks):
        from code_puppy.plugins.agent_skills.skills_menu import SkillsMenu

        SkillsMenu()  # should not raise

    @patch(f"{_MOD}.get_skills_enabled", return_value=True)
    @patch(f"{_MOD}.get_skill_directories", return_value=[])
    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill()])
    def test_get_current_skill(self, *mocks):
        from code_puppy.plugins.agent_skills.skills_menu import SkillsMenu

        menu = SkillsMenu()
        assert menu._get_current_skill() is not None
        menu.selected_idx = 99
        assert menu._get_current_skill() is None


class TestSkillsMenuRendering:
    """Test rendering methods of SkillsMenu."""

    def _make_menu(self, skills=None, disabled=None, enabled=True):
        with (
            patch(f"{_MOD}.get_skills_enabled", return_value=enabled),
            patch(f"{_MOD}.get_skill_directories", return_value=[]),
            patch(f"{_MOD}.get_disabled_skills", return_value=disabled or []),
            patch(f"{_MOD}.discover_skills", return_value=skills or []),
        ):
            from code_puppy.plugins.agent_skills.skills_menu import SkillsMenu

            return SkillsMenu()

    def test_render_empty_skill_list(self):
        menu = self._make_menu()
        lines = menu._render_skill_list()
        text = "".join(t for _, t in lines)
        assert "No skills found" in text

    def test_render_skill_list_disabled_system(self):
        menu = self._make_menu(enabled=False)
        lines = menu._render_skill_list()
        text = "".join(t for _, t in lines)
        assert "DISABLED" in text

    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_render_skill_list_with_skills(self, mock_meta):
        skills = [_make_skill(f"s{i}", f"/tmp/s{i}") for i in range(3)]
        menu = self._make_menu(skills=skills)
        lines = menu._render_skill_list()
        text = "".join(t for _, t in lines)
        assert "Page 1/1" in text

    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_render_skill_list_with_disabled_skill(self, mock_meta):
        skills = [_make_skill("skill-a")]
        menu = self._make_menu(skills=skills, disabled=["skill-a"])
        lines = menu._render_skill_list()
        text = "".join(t for _, t in lines)
        assert "✗" in text

    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    def test_render_skill_list_no_metadata(self, mock_meta):
        skills = [_make_skill("skill-a")]
        menu = self._make_menu(skills=skills, disabled=["skill-a"])
        lines = menu._render_skill_list()
        text = "".join(t for _, t in lines)
        assert "skill-a" in text

    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_render_selected_vs_unselected(self, mock_meta):
        skills = [_make_skill("s0", "/tmp/s0"), _make_skill("s1", "/tmp/s1")]
        menu = self._make_menu(skills=skills)
        menu.selected_idx = 1
        lines = menu._render_skill_list()
        # Just ensure no crash
        assert len(lines) > 0

    def test_render_details_no_skill(self):
        menu = self._make_menu()
        lines = menu._render_skill_details()
        text = "".join(t for _, t in lines)
        assert "No skill selected" in text

    @patch(f"{_MOD}.get_skill_resources", return_value=[])
    @patch(
        f"{_MOD}.parse_skill_metadata",
        return_value=_make_metadata(
            desc="A very long description that should be wrapped properly",
            tags=["t1", "t2"],
        ),
    )
    def test_render_details_with_metadata(self, mock_meta, mock_res):
        skills = [_make_skill()]
        menu = self._make_menu(skills=skills)
        lines = menu._render_skill_details()
        text = "".join(t for _, t in lines)
        assert "skill-a" in text
        assert "Description" in text
        assert "Tags" in text

    @patch(f"{_MOD}.get_skill_resources")
    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_render_details_with_resources(self, mock_meta, mock_res):
        # Create 7 resources to test truncation
        resources = [MagicMock(name=f"res{i}") for i in range(7)]
        for i, r in enumerate(resources):
            r.name = f"resource-{i}"
        mock_res.return_value = resources
        skills = [_make_skill()]
        menu = self._make_menu(skills=skills)
        lines = menu._render_skill_details()
        text = "".join(t for _, t in lines)
        assert "Resources" in text
        assert "and 2 more" in text

    @patch(f"{_MOD}.get_skill_resources", return_value=[])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    def test_render_details_no_metadata(self, mock_meta, mock_res):
        skills = [_make_skill()]
        menu = self._make_menu(skills=skills)
        lines = menu._render_skill_details()
        text = "".join(t for _, t in lines)
        assert "No metadata available" in text

    @patch(f"{_MOD}.get_skill_resources", return_value=[])
    @patch(
        f"{_MOD}.parse_skill_metadata", return_value=_make_metadata(desc=None, tags=[])
    )
    def test_render_details_no_desc_no_tags(self, mock_meta, mock_res):
        skills = [_make_skill()]
        menu = self._make_menu(skills=skills)
        lines = menu._render_skill_details()
        text = "".join(t for _, t in lines)
        assert "Path" in text

    @patch(f"{_MOD}.get_skill_resources", return_value=[])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_render_details_long_path(self, mock_meta, mock_res):
        skills = [_make_skill(path="/very/long/path/" + "x" * 100)]
        menu = self._make_menu(skills=skills)
        lines = menu._render_skill_details()
        text = "".join(t for _, t in lines)
        assert "..." in text


class TestSkillsMenuGetMetadata:
    def _make_menu(self):
        with (
            patch(f"{_MOD}.get_skills_enabled", return_value=True),
            patch(f"{_MOD}.get_skill_directories", return_value=[]),
            patch(f"{_MOD}.get_disabled_skills", return_value=[]),
            patch(f"{_MOD}.discover_skills", return_value=[_make_skill()]),
        ):
            from code_puppy.plugins.agent_skills.skills_menu import SkillsMenu

            return SkillsMenu()

    @patch(f"{_MOD}.parse_skill_metadata", side_effect=RuntimeError("bad"))
    def test_get_skill_metadata_error(self, mock_meta):
        menu = self._make_menu()
        skill = _make_skill()
        assert menu._get_skill_metadata(skill) is None

    @patch(f"{_MOD}.parse_skill_metadata", side_effect=RuntimeError("bad"))
    def test_is_skill_disabled_no_metadata_fallback(self, mock_meta):
        menu = self._make_menu()
        menu.disabled_skills = ["skill-a"]
        skill = _make_skill()
        assert menu._is_skill_disabled(skill) is True


class TestSkillsMenuWrapText:
    def _make_menu(self):
        with (
            patch(f"{_MOD}.get_skills_enabled", return_value=True),
            patch(f"{_MOD}.get_skill_directories", return_value=[]),
            patch(f"{_MOD}.get_disabled_skills", return_value=[]),
            patch(f"{_MOD}.discover_skills", return_value=[]),
        ):
            from code_puppy.plugins.agent_skills.skills_menu import SkillsMenu

            return SkillsMenu()

    def test_wrap_empty(self):
        menu = self._make_menu()
        assert menu._wrap_text("", 40) == [""]

    def test_wrap_short(self):
        menu = self._make_menu()
        assert menu._wrap_text("hello world", 40) == ["hello world"]

    def test_wrap_long(self):
        menu = self._make_menu()
        result = menu._wrap_text("word " * 20, 15)
        assert len(result) > 1
        for line in result:
            assert len(line) <= 20  # some tolerance


class TestSkillsMenuToggle:
    @patch(f"{_MOD}.refresh_skill_cache")
    @patch(f"{_MOD}.set_skill_disabled")
    @patch(f"{_MOD}.get_skills_enabled", return_value=True)
    @patch(f"{_MOD}.get_skill_directories", return_value=[])
    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill()])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_toggle_enables(
        self, mock_meta, mock_disc, mock_dis, mock_dirs, mock_en, mock_set, mock_refresh
    ):
        from code_puppy.plugins.agent_skills.skills_menu import SkillsMenu

        menu = SkillsMenu()
        menu._toggle_current_skill()
        mock_set.assert_called_once_with("skill-a", True)

    @patch(f"{_MOD}.refresh_skill_cache")
    @patch(f"{_MOD}.set_skill_disabled")
    @patch(f"{_MOD}.get_skills_enabled", return_value=True)
    @patch(f"{_MOD}.get_skill_directories", return_value=[])
    @patch(f"{_MOD}.get_disabled_skills", return_value=["skill-a"])
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill()])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_toggle_disables(
        self, mock_meta, mock_disc, mock_dis, mock_dirs, mock_en, mock_set, mock_refresh
    ):
        from code_puppy.plugins.agent_skills.skills_menu import SkillsMenu

        menu = SkillsMenu()
        menu._toggle_current_skill()
        mock_set.assert_called_once_with("skill-a", False)

    @patch(f"{_MOD}.get_skills_enabled", return_value=True)
    @patch(f"{_MOD}.get_skill_directories", return_value=[])
    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(f"{_MOD}.discover_skills", return_value=[])
    def test_toggle_no_skill(self, *mocks):
        from code_puppy.plugins.agent_skills.skills_menu import SkillsMenu

        menu = SkillsMenu()
        menu._toggle_current_skill()  # should not raise

    @patch(f"{_MOD}.refresh_skill_cache")
    @patch(f"{_MOD}.set_skill_disabled")
    @patch(f"{_MOD}.get_skills_enabled", return_value=True)
    @patch(f"{_MOD}.get_skill_directories", return_value=[])
    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill()])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    def test_toggle_no_metadata(
        self, mock_meta, mock_disc, mock_dis, mock_dirs, mock_en, mock_set, mock_refresh
    ):
        from code_puppy.plugins.agent_skills.skills_menu import SkillsMenu

        menu = SkillsMenu()
        menu._toggle_current_skill()
        mock_set.assert_called_once_with("skill-a", True)


class TestSkillsMenuUpdateDisplay:
    def test_update_display_with_controls(self):
        with (
            patch(f"{_MOD}.get_skills_enabled", return_value=True),
            patch(f"{_MOD}.get_skill_directories", return_value=[]),
            patch(f"{_MOD}.get_disabled_skills", return_value=[]),
            patch(f"{_MOD}.discover_skills", return_value=[]),
        ):
            from code_puppy.plugins.agent_skills.skills_menu import SkillsMenu

            menu = SkillsMenu()
            menu.menu_control = MagicMock()
            menu.preview_control = MagicMock()
            menu.update_display()
            assert menu.menu_control.text is not None
            assert menu.preview_control.text is not None

    def test_update_display_without_controls(self):
        with (
            patch(f"{_MOD}.get_skills_enabled", return_value=True),
            patch(f"{_MOD}.get_skill_directories", return_value=[]),
            patch(f"{_MOD}.get_disabled_skills", return_value=[]),
            patch(f"{_MOD}.discover_skills", return_value=[]),
        ):
            from code_puppy.plugins.agent_skills.skills_menu import SkillsMenu

            menu = SkillsMenu()
            menu.update_display()  # no crash with None controls


def _invoke_kb_handler(kb, key_name, app_mock=None):
    """Find and invoke a key binding handler by key name."""
    # Build a lookup of key aliases
    _ALIASES = {
        "enter": "c-m",
        "up": "up",
        "down": "down",
        "left": "left",
        "right": "right",
        "escape": "escape",
        "space": " ",
        "backspace": "c-h",
    }
    target = _ALIASES.get(key_name, key_name)
    event = MagicMock()
    event.app = app_mock or MagicMock()
    for binding in kb.bindings:
        for k in binding.keys:
            name = k.value if hasattr(k, "value") else str(k)
            if name == target or name == key_name:
                binding.handler(event)
                return event
    raise ValueError(f"No handler found for key: {key_name} (target={target})")


class TestSkillsMenuKeyBindings:
    """Test key binding handlers by capturing KeyBindings during run()."""

    def _run_with_key_capture(self, skills=None, disabled=None, callback=None):
        captured_kb = [None]
        orig_kb = __import__(
            "prompt_toolkit.key_binding", fromlist=["KeyBindings"]
        ).KeyBindings

        class CapturingKB(orig_kb):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                captured_kb[0] = self

        with (
            patch(f"{_MOD}.get_skills_enabled", return_value=True),
            patch(f"{_MOD}.get_skill_directories", return_value=[]),
            patch(f"{_MOD}.get_disabled_skills", return_value=disabled or []),
            patch(f"{_MOD}.discover_skills", return_value=skills or []),
            patch(f"{_MOD}.set_awaiting_user_input"),
            patch(f"{_MOD}.KeyBindings", CapturingKB),
            patch(f"{_MOD}.Application") as mock_app_cls,
            patch(f"{_MOD}.time"),
            patch("sys.stdout"),
        ):
            from code_puppy.plugins.agent_skills.skills_menu import SkillsMenu

            menu = SkillsMenu()
            mock_app = MagicMock()

            def fake_run(**kwargs):
                if callback:
                    callback(menu, captured_kb[0], mock_app)
                else:
                    menu.result = "quit"

            mock_app.run.side_effect = fake_run
            mock_app_cls.return_value = mock_app
            result = menu.run()
            return menu, result, captured_kb[0]

    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_navigation_keys(self, mock_meta):
        skills = [_make_skill(f"s{i}", f"/tmp/s{i}") for i in range(20)]

        def exercise_keys(menu, kb, app):
            # Navigate down
            _invoke_kb_handler(kb, "down", app)
            assert menu.selected_idx == 1
            _invoke_kb_handler(kb, "j", app)
            assert menu.selected_idx == 2
            # Navigate up
            _invoke_kb_handler(kb, "up", app)
            assert menu.selected_idx == 1
            _invoke_kb_handler(kb, "k", app)
            assert menu.selected_idx == 0
            # Up at top (no-op)
            _invoke_kb_handler(kb, "up", app)
            assert menu.selected_idx == 0
            # Page right
            _invoke_kb_handler(kb, "right", app)
            assert menu.current_page == 1
            # Page left
            _invoke_kb_handler(kb, "left", app)
            assert menu.current_page == 0
            # Left at start (no-op)
            _invoke_kb_handler(kb, "left", app)
            assert menu.current_page == 0
            # Enter (toggle)
            _invoke_kb_handler(kb, "enter", app)
            assert menu.result == "changed"
            # Toggle system
            _invoke_kb_handler(kb, "t", app)
            # Refresh
            _invoke_kb_handler(kb, "r", app)
            # Install
            _invoke_kb_handler(kb, "i", app)
            assert menu.result == "install"
            # Ctrl+A (add dir)
            menu.result = None
            _invoke_kb_handler(kb, "c-a", app)
            assert menu.result == "add_directory"
            # Ctrl+D (show dirs)
            menu.result = None
            _invoke_kb_handler(kb, "c-d", app)
            assert menu.result == "show_directories"
            # Quit
            menu.result = None
            _invoke_kb_handler(kb, "q", app)
            assert menu.result == "quit"
            # Escape
            menu.result = None
            _invoke_kb_handler(kb, "escape", app)
            assert menu.result == "quit"
            # Ctrl+C
            menu.result = None
            _invoke_kb_handler(kb, "c-c", app)
            assert menu.result == "quit"

        self._run_with_key_capture(
            skills=skills,
            callback=exercise_keys,
        )

    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_down_at_bottom(self, mock_meta):
        skills = [_make_skill("s0", "/tmp/s0")]

        def exercise(menu, kb, app):
            _invoke_kb_handler(kb, "down", app)
            assert menu.selected_idx == 0  # already at bottom
            # Right when only 1 page
            _invoke_kb_handler(kb, "right", app)
            assert menu.current_page == 0
            menu.result = "quit"

        self._run_with_key_capture(skills=skills, callback=exercise)

    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_ctrl_p_and_ctrl_n(self, mock_meta):
        skills = [_make_skill(f"s{i}", f"/tmp/s{i}") for i in range(3)]

        def exercise(menu, kb, app):
            _invoke_kb_handler(kb, "c-n", app)
            assert menu.selected_idx == 1
            _invoke_kb_handler(kb, "c-p", app)
            assert menu.selected_idx == 0
            menu.result = "quit"

        self._run_with_key_capture(skills=skills, callback=exercise)


class TestSkillsMenuRun:
    """Test SkillsMenu.run() with mocked Application."""

    @patch(f"{_MOD}.set_awaiting_user_input")
    @patch(f"{_MOD}.Application")
    @patch(f"{_MOD}.time")
    @patch("sys.stdout")
    def test_run_quit(self, mock_stdout, mock_time, mock_app_cls, mock_await):
        with (
            patch(f"{_MOD}.get_skills_enabled", return_value=True),
            patch(f"{_MOD}.get_skill_directories", return_value=[]),
            patch(f"{_MOD}.get_disabled_skills", return_value=[]),
            patch(f"{_MOD}.discover_skills", return_value=[]),
        ):
            from code_puppy.plugins.agent_skills.skills_menu import SkillsMenu

            menu = SkillsMenu()
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app

            def fake_run(**kwargs):
                menu.result = "quit"

            mock_app.run.side_effect = fake_run
            result = menu.run()
            assert result == "quit"


# ---------------------------------------------------------------------------
# Top-level functions
# ---------------------------------------------------------------------------


class TestPromptForDirectory:
    def test_prompt_returns_path(self):
        with patch(
            "code_puppy.tools.common.safe_input",
            create=True,
            return_value="~/my-skills",
        ):
            from code_puppy.plugins.agent_skills.skills_menu import (
                _prompt_for_directory,
            )

            result = _prompt_for_directory()
            assert result is not None
            assert "~" not in result  # should be expanded

    def test_prompt_empty_returns_none(self):
        with patch(
            "code_puppy.tools.common.safe_input", create=True, return_value="  "
        ):
            from code_puppy.plugins.agent_skills.skills_menu import (
                _prompt_for_directory,
            )

            result = _prompt_for_directory()
            assert result is None

    def test_prompt_keyboard_interrupt(self):
        with patch(
            "code_puppy.tools.common.safe_input",
            create=True,
            side_effect=KeyboardInterrupt,
        ):
            from code_puppy.plugins.agent_skills.skills_menu import (
                _prompt_for_directory,
            )

            result = _prompt_for_directory()
            assert result is None

    def test_prompt_eof_error(self):
        with patch(
            "code_puppy.tools.common.safe_input", create=True, side_effect=EOFError
        ):
            from code_puppy.plugins.agent_skills.skills_menu import (
                _prompt_for_directory,
            )

            result = _prompt_for_directory()
            assert result is None


class TestShowDirectoriesMenu:
    @patch(f"{_MOD}.get_skill_directories", return_value=[])
    def test_no_dirs(self, mock_dirs):
        with patch("code_puppy.tools.common.safe_input", create=True, return_value=""):
            from code_puppy.plugins.agent_skills.skills_menu import (
                _show_directories_menu,
            )

            result = _show_directories_menu()
            assert result is None

    @patch(f"{_MOD}.remove_skill_directory")
    @patch(f"{_MOD}.get_skill_directories", return_value=["/tmp/skills"])
    def test_remove_dir(self, mock_dirs, mock_remove):
        with patch(
            "code_puppy.tools.common.safe_input", create=True, side_effect=["1", "y"]
        ):
            from code_puppy.plugins.agent_skills.skills_menu import (
                _show_directories_menu,
            )

            result = _show_directories_menu()
            assert result == "changed"
            mock_remove.assert_called_once()

    @patch(f"{_MOD}.get_skill_directories", return_value=["/tmp/skills"])
    def test_remove_dir_cancel(self, mock_dirs):
        with patch(
            "code_puppy.tools.common.safe_input", create=True, side_effect=["1", "n"]
        ):
            from code_puppy.plugins.agent_skills.skills_menu import (
                _show_directories_menu,
            )

            result = _show_directories_menu()
            assert result is None

    @patch(f"{_MOD}.get_skill_directories", return_value=["/tmp/skills"])
    def test_invalid_choice(self, mock_dirs):
        with patch(
            "code_puppy.tools.common.safe_input", create=True, return_value="abc"
        ):
            from code_puppy.plugins.agent_skills.skills_menu import (
                _show_directories_menu,
            )

            result = _show_directories_menu()
            assert result is None

    @patch(f"{_MOD}.get_skill_directories", return_value=["/tmp/skills"])
    def test_out_of_range(self, mock_dirs):
        with patch(
            "code_puppy.tools.common.safe_input", create=True, return_value="99"
        ):
            from code_puppy.plugins.agent_skills.skills_menu import (
                _show_directories_menu,
            )

            result = _show_directories_menu()
            assert result is None

    @patch(f"{_MOD}.get_skill_directories", return_value=["/tmp/skills"])
    def test_keyboard_interrupt(self, mock_dirs):
        with patch(
            "code_puppy.tools.common.safe_input",
            create=True,
            side_effect=KeyboardInterrupt,
        ):
            from code_puppy.plugins.agent_skills.skills_menu import (
                _show_directories_menu,
            )

            result = _show_directories_menu()
            assert result is None


class TestShowSkillsMenu:
    """Test the top-level show_skills_menu loop."""

    @patch(f"{_MOD}.SkillsMenu")
    def test_quit(self, mock_cls):
        mock_menu = MagicMock()
        mock_menu.run.return_value = "quit"
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.agent_skills.skills_menu import show_skills_menu

        result = show_skills_menu()
        assert result is False

    @patch(f"{_MOD}.SkillsMenu")
    def test_changed(self, mock_cls):
        mock_menu = MagicMock()
        mock_menu.run.return_value = "changed"
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.agent_skills.skills_menu import show_skills_menu

        result = show_skills_menu()
        assert result is True

    @patch(f"{_MOD}.SkillsMenu")
    def test_none_result(self, mock_cls):
        mock_menu = MagicMock()
        mock_menu.run.return_value = None
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.agent_skills.skills_menu import show_skills_menu

        result = show_skills_menu()
        assert result is False

    @patch(f"{_MOD}._prompt_for_directory", return_value="/tmp/new-dir")
    @patch(f"{_MOD}.add_skill_directory", return_value=True)
    @patch(f"{_MOD}.SkillsMenu")
    def test_add_directory_success(self, mock_cls, mock_add, mock_prompt):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["add_directory", "quit"]
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.agent_skills.skills_menu import show_skills_menu

        show_skills_menu()
        mock_add.assert_called_once_with("/tmp/new-dir")

    @patch(f"{_MOD}._prompt_for_directory", return_value="/tmp/dup")
    @patch(f"{_MOD}.add_skill_directory", return_value=False)
    @patch(f"{_MOD}.SkillsMenu")
    def test_add_directory_duplicate(self, mock_cls, mock_add, mock_prompt):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["add_directory", "quit"]
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.agent_skills.skills_menu import show_skills_menu

        show_skills_menu()

    @patch(f"{_MOD}._prompt_for_directory", return_value=None)
    @patch(f"{_MOD}.SkillsMenu")
    def test_add_directory_cancelled(self, mock_cls, mock_prompt):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["add_directory", "quit"]
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.agent_skills.skills_menu import show_skills_menu

        show_skills_menu()

    @patch(f"{_MOD}._show_directories_menu", return_value="changed")
    @patch(f"{_MOD}.SkillsMenu")
    def test_show_directories_changed(self, mock_cls, mock_show):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["show_directories", "quit"]
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.agent_skills.skills_menu import show_skills_menu

        result = show_skills_menu()
        assert result is True

    @patch(f"{_MOD}._show_directories_menu", return_value=None)
    @patch(f"{_MOD}.SkillsMenu")
    def test_show_directories_unchanged(self, mock_cls, mock_show):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["show_directories", "quit"]
        mock_cls.return_value = mock_menu
        from code_puppy.plugins.agent_skills.skills_menu import show_skills_menu

        result = show_skills_menu()
        assert result is False

    @patch(f"{_MOD}.SkillsMenu")
    def test_install_flow(self, mock_cls):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["install", "quit"]
        mock_cls.return_value = mock_menu
        with patch(
            "code_puppy.plugins.agent_skills.skills_install_menu.run_skills_install_menu",
            return_value=True,
        ):
            from code_puppy.plugins.agent_skills.skills_menu import show_skills_menu

            result = show_skills_menu()
            assert result is True

    @patch(f"{_MOD}.SkillsMenu")
    def test_install_no_change(self, mock_cls):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["install", "quit"]
        mock_cls.return_value = mock_menu
        with patch(
            "code_puppy.plugins.agent_skills.skills_install_menu.run_skills_install_menu",
            return_value=False,
        ):
            from code_puppy.plugins.agent_skills.skills_menu import show_skills_menu

            result = show_skills_menu()
            assert result is False


# ---------------------------------------------------------------------------
# list_skills
# ---------------------------------------------------------------------------


class TestListSkills:
    @patch(f"{_MOD}.discover_skills", return_value=[])
    def test_no_skills(self, mock_disc):
        from code_puppy.plugins.agent_skills.skills_menu import list_skills

        assert list_skills() is True

    @patch(f"{_MOD}.get_skill_resources", return_value=["r1"])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata(desc="desc"))
    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill()])
    def test_with_skills(self, mock_disc, mock_dis, mock_meta, mock_res):
        from code_puppy.plugins.agent_skills.skills_menu import list_skills

        assert list_skills() is True

    @patch(f"{_MOD}.get_skill_resources", return_value=[])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata(desc=None))
    @patch(f"{_MOD}.get_disabled_skills", return_value=["skill-a"])
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill()])
    def test_disabled_no_desc(self, mock_disc, mock_dis, mock_meta, mock_res):
        from code_puppy.plugins.agent_skills.skills_menu import list_skills

        assert list_skills() is True

    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    @patch(f"{_MOD}.get_disabled_skills", return_value=["skill-a"])
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill()])
    def test_no_metadata(self, mock_disc, mock_dis, mock_meta):
        from code_puppy.plugins.agent_skills.skills_menu import list_skills

        assert list_skills() is True

    @patch(f"{_MOD}.discover_skills", side_effect=RuntimeError("boom"))
    def test_error(self, mock_disc):
        from code_puppy.plugins.agent_skills.skills_menu import list_skills

        assert list_skills() is False


# ---------------------------------------------------------------------------
# handle_skills_command
# ---------------------------------------------------------------------------


class TestHandleSkillsCommand:
    @patch(f"{_MOD}.show_skills_menu", return_value=True)
    def test_no_args(self, mock_show):
        from code_puppy.plugins.agent_skills.skills_menu import handle_skills_command

        assert handle_skills_command([]) is True

    @patch(f"{_MOD}.list_skills", return_value=True)
    def test_list(self, mock_list):
        from code_puppy.plugins.agent_skills.skills_menu import handle_skills_command

        assert handle_skills_command(["list"]) is True

    def test_enable_no_name(self):
        from code_puppy.plugins.agent_skills.skills_menu import handle_skills_command

        assert handle_skills_command(["enable"]) is False

    def test_disable_no_name(self):
        from code_puppy.plugins.agent_skills.skills_menu import handle_skills_command

        assert handle_skills_command(["disable"]) is False

    @patch(f"{_MOD}._enable_skill", return_value=True)
    def test_enable(self, mock_en):
        from code_puppy.plugins.agent_skills.skills_menu import handle_skills_command

        assert handle_skills_command(["enable", "my-skill"]) is True

    @patch(f"{_MOD}._disable_skill", return_value=True)
    def test_disable(self, mock_dis):
        from code_puppy.plugins.agent_skills.skills_menu import handle_skills_command

        assert handle_skills_command(["disable", "my-skill"]) is True

    @patch(f"{_MOD}._toggle_skills_integration", return_value=True)
    def test_toggle(self, mock_toggle):
        from code_puppy.plugins.agent_skills.skills_menu import handle_skills_command

        assert handle_skills_command(["toggle"]) is True

    @patch(f"{_MOD}._refresh_skills", return_value=True)
    def test_refresh(self, mock_ref):
        from code_puppy.plugins.agent_skills.skills_menu import handle_skills_command

        assert handle_skills_command(["refresh"]) is True

    def test_help(self):
        from code_puppy.plugins.agent_skills.skills_menu import handle_skills_command

        assert handle_skills_command(["help"]) is True

    def test_unknown(self):
        from code_puppy.plugins.agent_skills.skills_menu import handle_skills_command

        assert handle_skills_command(["foobar"]) is False


# ---------------------------------------------------------------------------
# _enable_skill / _disable_skill
# ---------------------------------------------------------------------------


class TestEnableDisableSkill:
    @patch(f"{_MOD}.refresh_skill_cache")
    @patch(f"{_MOD}.set_skill_disabled")
    @patch(f"{_MOD}.get_disabled_skills", return_value=["my-skill"])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill("my-skill")])
    def test_enable_success(self, *mocks):
        from code_puppy.plugins.agent_skills.skills_menu import _enable_skill

        assert _enable_skill("my-skill") is True

    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill("my-skill")])
    def test_enable_already_enabled(self, *mocks):
        from code_puppy.plugins.agent_skills.skills_menu import _enable_skill

        assert _enable_skill("my-skill") is True

    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    @patch(f"{_MOD}.discover_skills", return_value=[])
    def test_enable_not_found(self, *mocks):
        from code_puppy.plugins.agent_skills.skills_menu import _enable_skill

        assert _enable_skill("nonexistent") is False

    @patch(f"{_MOD}.discover_skills", side_effect=RuntimeError("boom"))
    def test_enable_error(self, *mocks):
        from code_puppy.plugins.agent_skills.skills_menu import _enable_skill

        assert _enable_skill("x") is False

    @patch(f"{_MOD}.refresh_skill_cache")
    @patch(f"{_MOD}.set_skill_disabled")
    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill("my-skill")])
    def test_disable_success(self, *mocks):
        from code_puppy.plugins.agent_skills.skills_menu import _disable_skill

        assert _disable_skill("my-skill") is True

    @patch(f"{_MOD}.get_disabled_skills", return_value=["my-skill"])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill("my-skill")])
    def test_disable_already_disabled(self, *mocks):
        from code_puppy.plugins.agent_skills.skills_menu import _disable_skill

        assert _disable_skill("my-skill") is True

    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    @patch(f"{_MOD}.discover_skills", return_value=[])
    def test_disable_not_found(self, *mocks):
        from code_puppy.plugins.agent_skills.skills_menu import _disable_skill

        assert _disable_skill("nonexistent") is False

    @patch(f"{_MOD}.discover_skills", side_effect=RuntimeError("boom"))
    def test_disable_error(self, *mocks):
        from code_puppy.plugins.agent_skills.skills_menu import _disable_skill

        assert _disable_skill("x") is False

    # With metadata names
    @patch(f"{_MOD}.refresh_skill_cache")
    @patch(f"{_MOD}.set_skill_disabled")
    @patch(f"{_MOD}.get_disabled_skills", return_value=["meta-name"])
    @patch(
        f"{_MOD}.parse_skill_metadata", return_value=_make_metadata(name="meta-name")
    )
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill("skill-a")])
    def test_enable_by_metadata_name(self, *mocks):
        from code_puppy.plugins.agent_skills.skills_menu import _enable_skill

        assert _enable_skill("meta-name") is True

    @patch(f"{_MOD}.refresh_skill_cache")
    @patch(f"{_MOD}.set_skill_disabled")
    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(
        f"{_MOD}.parse_skill_metadata", return_value=_make_metadata(name="meta-name")
    )
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill("skill-a")])
    def test_disable_by_metadata_name(self, *mocks):
        from code_puppy.plugins.agent_skills.skills_menu import _disable_skill

        assert _disable_skill("meta-name") is True


# ---------------------------------------------------------------------------
# _toggle_skills_integration / _refresh_skills
# ---------------------------------------------------------------------------


class TestToggleAndRefresh:
    @patch(f"{_MOD}.set_skills_enabled")
    @patch(f"{_MOD}.get_skills_enabled", return_value=False)
    def test_toggle_on(self, mock_get, mock_set):
        from code_puppy.plugins.agent_skills.skills_menu import (
            _toggle_skills_integration,
        )

        assert _toggle_skills_integration() is True
        mock_set.assert_called_with(True)

    @patch(f"{_MOD}.set_skills_enabled")
    @patch(f"{_MOD}.get_skills_enabled", return_value=True)
    def test_toggle_off(self, mock_get, mock_set):
        from code_puppy.plugins.agent_skills.skills_menu import (
            _toggle_skills_integration,
        )

        assert _toggle_skills_integration() is True
        mock_set.assert_called_with(False)

    @patch(f"{_MOD}.get_skills_enabled", side_effect=RuntimeError("boom"))
    def test_toggle_error(self, mock_get):
        from code_puppy.plugins.agent_skills.skills_menu import (
            _toggle_skills_integration,
        )

        assert _toggle_skills_integration() is False

    @patch(f"{_MOD}.refresh_skill_cache")
    def test_refresh(self, mock_ref):
        from code_puppy.plugins.agent_skills.skills_menu import _refresh_skills

        assert _refresh_skills() is True

    @patch(f"{_MOD}.refresh_skill_cache", side_effect=RuntimeError("boom"))
    def test_refresh_error(self, mock_ref):
        from code_puppy.plugins.agent_skills.skills_menu import _refresh_skills

        assert _refresh_skills() is False


class TestShowHelp:
    def test_show_help(self):
        from code_puppy.plugins.agent_skills.skills_menu import _show_help

        _show_help()  # just ensure no crash


# ---------------------------------------------------------------------------
# Pagination rendering (many skills)
# ---------------------------------------------------------------------------


class TestPagination:
    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_multi_page(self, mock_meta):
        skills = [_make_skill(f"s{i}", f"/tmp/s{i}") for i in range(20)]
        with (
            patch(f"{_MOD}.get_skills_enabled", return_value=True),
            patch(f"{_MOD}.get_skill_directories", return_value=[]),
            patch(f"{_MOD}.get_disabled_skills", return_value=[]),
            patch(f"{_MOD}.discover_skills", return_value=skills),
        ):
            from code_puppy.plugins.agent_skills.skills_menu import SkillsMenu

            menu = SkillsMenu()
            # Page 1
            lines = menu._render_skill_list()
            text = "".join(t for _, t in lines)
            assert "Page 1/2" in text
            # Page 2
            menu.current_page = 1
            menu.selected_idx = 15
            lines = menu._render_skill_list()
            text = "".join(t for _, t in lines)
            assert "Page 2/2" in text
