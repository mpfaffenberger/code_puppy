"""Tests for code_puppy/plugins/agent_skills/skills_menu.py"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy_core_plugins.agent_skills.discovery import SkillInfo
from code_puppy_core_plugins.agent_skills.metadata import SkillMetadata

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
_MOD = "code_puppy_core_plugins.agent_skills.skills_menu"
_SAFE_INPUT = f"{_MOD}.safe_input"


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
        from code_puppy_core_plugins.agent_skills.skills_menu import SkillsMenu

        menu = SkillsMenu()
        assert menu.skills == []
        assert menu.skills_enabled is True
        assert menu.disabled_skills == ["disabled-one"]

    @patch(f"{_MOD}.get_skills_enabled", return_value=False)
    @patch(f"{_MOD}.get_skill_directories", return_value=[])
    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(f"{_MOD}.discover_skills", side_effect=RuntimeError("boom"))
    def test_init_refresh_error(self, *mocks):
        from code_puppy_core_plugins.agent_skills.skills_menu import SkillsMenu

        SkillsMenu()  # should not raise

    @patch(f"{_MOD}.get_skills_enabled", return_value=True)
    @patch(f"{_MOD}.get_skill_directories", return_value=[])
    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill()])
    def test_get_current_skill(self, *mocks):
        from code_puppy_core_plugins.agent_skills.skills_menu import SkillsMenu

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
            from code_puppy_core_plugins.agent_skills.skills_menu import SkillsMenu

            return SkillsMenu()

    def test_render_empty_skill_list(self):
        menu = self._make_menu()
        lines = menu._render_skill_list()
        text = "".join(t for _, t in lines)
        assert "No skills found" in text

    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_render_skill_list_with_skills(self, mock_meta):
        skills = [_make_skill(f"s{i}", f"/tmp/s{i}") for i in range(3)]
        menu = self._make_menu(skills=skills)
        lines = menu._render_skill_list()
        text = "".join(t for _, t in lines)
        assert "Page 1/1" in text

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
            from code_puppy_core_plugins.agent_skills.skills_menu import SkillsMenu

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
            from code_puppy_core_plugins.agent_skills.skills_menu import SkillsMenu

            return SkillsMenu()

    @pytest.mark.parametrize(
        ("text", "expected"),
        [("", [""]), ("hello world", ["hello world"])],
    )
    def test_wrap_short_inputs(self, text, expected):
        menu = self._make_menu()
        assert menu._wrap_text(text, 40) == expected

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
        from code_puppy_core_plugins.agent_skills.skills_menu import SkillsMenu

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
        from code_puppy_core_plugins.agent_skills.skills_menu import SkillsMenu

        menu = SkillsMenu()
        menu._toggle_current_skill()
        mock_set.assert_called_once_with("skill-a", False)

    @patch(f"{_MOD}.get_skills_enabled", return_value=True)
    @patch(f"{_MOD}.get_skill_directories", return_value=[])
    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(f"{_MOD}.discover_skills", return_value=[])
    def test_toggle_no_skill(self, *mocks):
        from code_puppy_core_plugins.agent_skills.skills_menu import SkillsMenu

        menu = SkillsMenu()
        menu._toggle_current_skill()  # should not raise


class TestSkillsMenuUpdateDisplay:
    def test_update_display_with_controls(self):
        with (
            patch(f"{_MOD}.get_skills_enabled", return_value=True),
            patch(f"{_MOD}.get_skill_directories", return_value=[]),
            patch(f"{_MOD}.get_disabled_skills", return_value=[]),
            patch(f"{_MOD}.discover_skills", return_value=[]),
        ):
            from code_puppy_core_plugins.agent_skills.skills_menu import SkillsMenu

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
            from code_puppy_core_plugins.agent_skills.skills_menu import SkillsMenu

            menu = SkillsMenu()
            menu.update_display()  # no crash with None controls


class TestSkillsMenuKeyBindings:
    """Drive the key dispatcher directly (headless)."""

    def _menu(self, skills=None, disabled=None):
        with (
            patch(f"{_MOD}.get_skills_enabled", return_value=True),
            patch(f"{_MOD}.get_skill_directories", return_value=[]),
            patch(f"{_MOD}.get_disabled_skills", return_value=disabled or []),
            patch(f"{_MOD}.discover_skills", return_value=skills or []),
        ):
            from code_puppy_core_plugins.agent_skills.skills_menu import SkillsMenu

            return SkillsMenu()

    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_navigation_keys(self, mock_meta):
        menu = self._menu([_make_skill(f"s{i}", f"/tmp/s{i}") for i in range(20)])
        menu.handle_key("down")
        assert menu.selected_idx == 1
        menu.handle_key("j")
        assert menu.selected_idx == 2
        menu.handle_key("up")
        assert menu.selected_idx == 1
        menu.handle_key("k")
        assert menu.selected_idx == 0
        menu.handle_key("up")
        assert menu.selected_idx == 0
        menu.handle_key("right")
        assert menu.current_page == 1
        menu.handle_key("left")
        assert menu.current_page == 0

    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_down_at_bottom(self, mock_meta):
        menu = self._menu([_make_skill("s0", "/tmp/s0")])
        menu.handle_key("down")
        assert menu.selected_idx == 0

    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_ctrl_p_and_ctrl_n(self, mock_meta):
        menu = self._menu([_make_skill(f"s{i}", f"/tmp/s{i}") for i in range(3)])
        menu.handle_key("ctrl-n")
        assert menu.selected_idx == 1
        menu.handle_key("ctrl-p")
        assert menu.selected_idx == 0

    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata())
    def test_exit_keys(self, mock_meta):
        for key in ("q", "escape", "ctrl-c"):
            menu = self._menu([_make_skill("s0", "/tmp/s0")])
            assert menu.handle_key(key) is True
            assert menu.result == "quit"


class TestSkillsMenuRun:
    """Test SkillsMenu.run() with the widget faked."""

    @patch(f"{_MOD}.set_awaiting_user_input")
    @patch("code_puppy_core_plugins.termflow_tui.FragmentTUI")
    def test_run_quit(self, mock_tui_cls, mock_await):
        with (
            patch(f"{_MOD}.get_skills_enabled", return_value=True),
            patch(f"{_MOD}.get_skill_directories", return_value=[]),
            patch(f"{_MOD}.get_disabled_skills", return_value=[]),
            patch(f"{_MOD}.discover_skills", return_value=[]),
        ):
            from code_puppy_core_plugins.agent_skills.skills_menu import SkillsMenu

            menu = SkillsMenu()

            def fake_run():
                menu.result = "quit"

            mock_tui_cls.return_value.run.side_effect = fake_run
            assert menu.run() == "quit"


# ---------------------------------------------------------------------------
# Top-level functions
# ---------------------------------------------------------------------------


class TestPromptForDirectory:
    def test_prompt_returns_path(self):
        with patch(
            _SAFE_INPUT,
            create=True,
            return_value="~/my-skills",
        ):
            from code_puppy_core_plugins.agent_skills.skills_menu import (
                _prompt_for_directory,
            )

            result = _prompt_for_directory()
            assert result is not None
            assert "~" not in result  # should be expanded

    def test_prompt_empty_returns_none(self):
        with patch(_SAFE_INPUT, create=True, return_value="  "):
            from code_puppy_core_plugins.agent_skills.skills_menu import (
                _prompt_for_directory,
            )

            result = _prompt_for_directory()
            assert result is None

    def test_prompt_keyboard_interrupt(self):
        with patch(
            _SAFE_INPUT,
            create=True,
            side_effect=KeyboardInterrupt,
        ):
            from code_puppy_core_plugins.agent_skills.skills_menu import (
                _prompt_for_directory,
            )

            result = _prompt_for_directory()
            assert result is None

    def test_prompt_eof_error(self):
        with patch(_SAFE_INPUT, create=True, side_effect=EOFError):
            from code_puppy_core_plugins.agent_skills.skills_menu import (
                _prompt_for_directory,
            )

            result = _prompt_for_directory()
            assert result is None


class TestShowDirectoriesMenu:
    @patch(f"{_MOD}.get_skill_directories", return_value=[])
    def test_no_dirs(self, mock_dirs):
        with patch(_SAFE_INPUT, create=True, return_value=""):
            from code_puppy_core_plugins.agent_skills.skills_menu import (
                _show_directories_menu,
            )

            result = _show_directories_menu()
            assert result is None

    @patch(f"{_MOD}.remove_skill_directory")
    @patch(f"{_MOD}.get_skill_directories", return_value=["/tmp/skills"])
    def test_remove_dir(self, mock_dirs, mock_remove):
        with patch(_SAFE_INPUT, create=True, side_effect=["1", "y"]):
            from code_puppy_core_plugins.agent_skills.skills_menu import (
                _show_directories_menu,
            )

            result = _show_directories_menu()
            assert result == "changed"
            mock_remove.assert_called_once()

    @patch(f"{_MOD}.get_skill_directories", return_value=["/tmp/skills"])
    def test_remove_dir_cancel(self, mock_dirs):
        with patch(_SAFE_INPUT, create=True, side_effect=["1", "n"]):
            from code_puppy_core_plugins.agent_skills.skills_menu import (
                _show_directories_menu,
            )

            result = _show_directories_menu()
            assert result is None

    @patch(f"{_MOD}.get_skill_directories", return_value=["/tmp/skills"])
    def test_out_of_range(self, mock_dirs):
        with patch(_SAFE_INPUT, create=True, return_value="99"):
            from code_puppy_core_plugins.agent_skills.skills_menu import (
                _show_directories_menu,
            )

            result = _show_directories_menu()
            assert result is None

    @patch(f"{_MOD}.get_skill_directories", return_value=["/tmp/skills"])
    def test_keyboard_interrupt(self, mock_dirs):
        with patch(
            _SAFE_INPUT,
            create=True,
            side_effect=KeyboardInterrupt,
        ):
            from code_puppy_core_plugins.agent_skills.skills_menu import (
                _show_directories_menu,
            )

            result = _show_directories_menu()
            assert result is None


class TestShowSkillsMenu:
    """Test the top-level show_skills_menu loop."""

    @pytest.mark.parametrize(
        "run_result, expected",
        [("quit", False), ("changed", True), (None, False)],
        ids=["quit", "changed", "none"],
    )
    @patch(f"{_MOD}.SkillsMenu")
    def test_run_result(self, mock_cls, run_result, expected):
        mock_menu = MagicMock()
        mock_menu.run.return_value = run_result
        mock_cls.return_value = mock_menu
        from code_puppy_core_plugins.agent_skills.skills_menu import show_skills_menu

        result = show_skills_menu()
        assert result is expected

    @patch(f"{_MOD}._prompt_for_directory", return_value="/tmp/new-dir")
    @patch(f"{_MOD}.add_skill_directory", return_value=True)
    @patch(f"{_MOD}.SkillsMenu")
    def test_add_directory_success(self, mock_cls, mock_add, mock_prompt):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["add_directory", "quit"]
        mock_cls.return_value = mock_menu
        from code_puppy_core_plugins.agent_skills.skills_menu import show_skills_menu

        show_skills_menu()
        mock_add.assert_called_once_with("/tmp/new-dir")

    @patch(f"{_MOD}._prompt_for_directory", return_value="/tmp/dup")
    @patch(f"{_MOD}.add_skill_directory", return_value=False)
    @patch(f"{_MOD}.SkillsMenu")
    def test_add_directory_duplicate(self, mock_cls, mock_add, mock_prompt):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["add_directory", "quit"]
        mock_cls.return_value = mock_menu
        from code_puppy_core_plugins.agent_skills.skills_menu import show_skills_menu

        show_skills_menu()

    @patch(f"{_MOD}._prompt_for_directory", return_value=None)
    @patch(f"{_MOD}.SkillsMenu")
    def test_add_directory_cancelled(self, mock_cls, mock_prompt):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["add_directory", "quit"]
        mock_cls.return_value = mock_menu
        from code_puppy_core_plugins.agent_skills.skills_menu import show_skills_menu

        show_skills_menu()

    @patch(f"{_MOD}._show_directories_menu", return_value="changed")
    @patch(f"{_MOD}.SkillsMenu")
    def test_show_directories_changed(self, mock_cls, mock_show):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["show_directories", "quit"]
        mock_cls.return_value = mock_menu
        from code_puppy_core_plugins.agent_skills.skills_menu import show_skills_menu

        result = show_skills_menu()
        assert result is True

    @patch(f"{_MOD}._show_directories_menu", return_value=None)
    @patch(f"{_MOD}.SkillsMenu")
    def test_show_directories_unchanged(self, mock_cls, mock_show):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["show_directories", "quit"]
        mock_cls.return_value = mock_menu
        from code_puppy_core_plugins.agent_skills.skills_menu import show_skills_menu

        result = show_skills_menu()
        assert result is False

    @patch(f"{_MOD}.SkillsMenu")
    def test_install_flow(self, mock_cls):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["install", "quit"]
        mock_cls.return_value = mock_menu
        with patch(
            "code_puppy_core_plugins.agent_skills.skills_install_menu.run_skills_install_menu",
            return_value=True,
        ):
            from code_puppy_core_plugins.agent_skills.skills_menu import (
                show_skills_menu,
            )

            result = show_skills_menu()
            assert result is True

    @patch(f"{_MOD}.SkillsMenu")
    def test_install_no_change(self, mock_cls):
        mock_menu = MagicMock()
        mock_menu.run.side_effect = ["install", "quit"]
        mock_cls.return_value = mock_menu
        with patch(
            "code_puppy_core_plugins.agent_skills.skills_install_menu.run_skills_install_menu",
            return_value=False,
        ):
            from code_puppy_core_plugins.agent_skills.skills_menu import (
                show_skills_menu,
            )

            result = show_skills_menu()
            assert result is False


# ---------------------------------------------------------------------------
# list_skills
# ---------------------------------------------------------------------------


class TestListSkills:
    @patch(f"{_MOD}.discover_skills", return_value=[])
    def test_no_skills(self, mock_disc):
        from code_puppy_core_plugins.agent_skills.skills_menu import list_skills

        assert list_skills() is True

    @patch(f"{_MOD}.get_skill_resources", return_value=["r1"])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata(desc="desc"))
    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill()])
    def test_with_skills(self, mock_disc, mock_dis, mock_meta, mock_res):
        from code_puppy_core_plugins.agent_skills.skills_menu import list_skills

        assert list_skills() is True

    @patch(f"{_MOD}.get_skill_resources", return_value=[])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=_make_metadata(desc=None))
    @patch(f"{_MOD}.get_disabled_skills", return_value=["skill-a"])
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill()])
    def test_disabled_no_desc(self, mock_disc, mock_dis, mock_meta, mock_res):
        from code_puppy_core_plugins.agent_skills.skills_menu import list_skills

        assert list_skills() is True

    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    @patch(f"{_MOD}.get_disabled_skills", return_value=["skill-a"])
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill()])
    def test_no_metadata(self, mock_disc, mock_dis, mock_meta):
        from code_puppy_core_plugins.agent_skills.skills_menu import list_skills

        assert list_skills() is True

    @patch(f"{_MOD}.discover_skills", side_effect=RuntimeError("boom"))
    def test_error(self, mock_disc):
        from code_puppy_core_plugins.agent_skills.skills_menu import list_skills

        assert list_skills() is False


# ---------------------------------------------------------------------------
# handle_skills_command
# ---------------------------------------------------------------------------


class TestHandleSkillsCommand:
    @pytest.mark.parametrize(
        "args, patch_target, expected",
        [
            ([], "show_skills_menu", True),
            (["list"], "list_skills", True),
            (["enable"], None, False),
            (["disable"], None, False),
            (["enable", "my-skill"], "_enable_skill", True),
            (["disable", "my-skill"], "_disable_skill", True),
            (["toggle"], "_toggle_skills_integration", True),
            (["refresh"], "_refresh_skills", True),
            (["help"], None, True),
            (["foobar"], None, False),
        ],
        ids=[
            "no_args",
            "list",
            "enable_no_name",
            "disable_no_name",
            "enable",
            "disable",
            "toggle",
            "refresh",
            "help",
            "unknown",
        ],
    )
    def test_handle_skills_command(self, args, patch_target, expected):
        from code_puppy_core_plugins.agent_skills.skills_menu import (
            handle_skills_command,
        )

        if patch_target is None:
            result = handle_skills_command(args)
        else:
            with patch(f"{_MOD}.{patch_target}", return_value=True):
                result = handle_skills_command(args)
        assert result is expected


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
        from code_puppy_core_plugins.agent_skills.skills_menu import _enable_skill

        assert _enable_skill("my-skill") is True

    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill("my-skill")])
    def test_enable_already_enabled(self, *mocks):
        from code_puppy_core_plugins.agent_skills.skills_menu import _enable_skill

        assert _enable_skill("my-skill") is True

    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    @patch(f"{_MOD}.discover_skills", return_value=[])
    def test_enable_not_found(self, *mocks):
        from code_puppy_core_plugins.agent_skills.skills_menu import _enable_skill

        assert _enable_skill("nonexistent") is False

    @patch(f"{_MOD}.discover_skills", side_effect=RuntimeError("boom"))
    def test_enable_error(self, *mocks):
        from code_puppy_core_plugins.agent_skills.skills_menu import _enable_skill

        assert _enable_skill("x") is False

    @patch(f"{_MOD}.refresh_skill_cache")
    @patch(f"{_MOD}.set_skill_disabled")
    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill("my-skill")])
    def test_disable_success(self, *mocks):
        from code_puppy_core_plugins.agent_skills.skills_menu import _disable_skill

        assert _disable_skill("my-skill") is True

    @patch(f"{_MOD}.get_disabled_skills", return_value=["my-skill"])
    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill("my-skill")])
    def test_disable_already_disabled(self, *mocks):
        from code_puppy_core_plugins.agent_skills.skills_menu import _disable_skill

        assert _disable_skill("my-skill") is True

    @patch(f"{_MOD}.parse_skill_metadata", return_value=None)
    @patch(f"{_MOD}.discover_skills", return_value=[])
    def test_disable_not_found(self, *mocks):
        from code_puppy_core_plugins.agent_skills.skills_menu import _disable_skill

        assert _disable_skill("nonexistent") is False

    @patch(f"{_MOD}.discover_skills", side_effect=RuntimeError("boom"))
    def test_disable_error(self, *mocks):
        from code_puppy_core_plugins.agent_skills.skills_menu import _disable_skill

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
        from code_puppy_core_plugins.agent_skills.skills_menu import _enable_skill

        assert _enable_skill("meta-name") is True

    @patch(f"{_MOD}.refresh_skill_cache")
    @patch(f"{_MOD}.set_skill_disabled")
    @patch(f"{_MOD}.get_disabled_skills", return_value=[])
    @patch(
        f"{_MOD}.parse_skill_metadata", return_value=_make_metadata(name="meta-name")
    )
    @patch(f"{_MOD}.discover_skills", return_value=[_make_skill("skill-a")])
    def test_disable_by_metadata_name(self, *mocks):
        from code_puppy_core_plugins.agent_skills.skills_menu import _disable_skill

        assert _disable_skill("meta-name") is True


# ---------------------------------------------------------------------------
# _toggle_skills_integration / _refresh_skills
# ---------------------------------------------------------------------------


class TestToggleAndRefresh:
    @patch(f"{_MOD}.set_skills_enabled")
    @patch(f"{_MOD}.get_skills_enabled", return_value=False)
    def test_toggle_on(self, mock_get, mock_set):
        from code_puppy_core_plugins.agent_skills.skills_menu import (
            _toggle_skills_integration,
        )

        assert _toggle_skills_integration() is True
        mock_set.assert_called_with(True)

    @patch(f"{_MOD}.set_skills_enabled")
    @patch(f"{_MOD}.get_skills_enabled", return_value=True)
    def test_toggle_off(self, mock_get, mock_set):
        from code_puppy_core_plugins.agent_skills.skills_menu import (
            _toggle_skills_integration,
        )

        assert _toggle_skills_integration() is True
        mock_set.assert_called_with(False)

    @patch(f"{_MOD}.get_skills_enabled", side_effect=RuntimeError("boom"))
    def test_toggle_error(self, mock_get):
        from code_puppy_core_plugins.agent_skills.skills_menu import (
            _toggle_skills_integration,
        )

        assert _toggle_skills_integration() is False

    @patch(f"{_MOD}.refresh_skill_cache")
    def test_refresh(self, mock_ref):
        from code_puppy_core_plugins.agent_skills.skills_menu import _refresh_skills

        assert _refresh_skills() is True

    @patch(f"{_MOD}.refresh_skill_cache", side_effect=RuntimeError("boom"))
    def test_refresh_error(self, mock_ref):
        from code_puppy_core_plugins.agent_skills.skills_menu import _refresh_skills

        assert _refresh_skills() is False


class TestShowHelp:
    def test_show_help(self):
        from code_puppy_core_plugins.agent_skills.skills_menu import _show_help

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
            from code_puppy_core_plugins.agent_skills.skills_menu import SkillsMenu

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
