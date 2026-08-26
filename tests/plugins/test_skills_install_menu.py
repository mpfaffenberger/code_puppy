"""Tests for code_puppy/plugins/agent_skills/skills_install_menu.py"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


_MOD = "code_puppy_core_plugins.agent_skills.skills_install_menu"


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


class TestFormatBytes:
    def test_zero(self):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            _format_bytes,
        )

        assert _format_bytes(0) == "0 B"

    def test_bytes(self):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            _format_bytes,
        )

        assert _format_bytes(500) == "500 B"

    def test_kb(self):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            _format_bytes,
        )

        result = _format_bytes(2048)
        assert "KB" in result

    def test_mb(self):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            _format_bytes,
        )

        result = _format_bytes(2 * 1024 * 1024)
        assert "MB" in result

    def test_gb(self):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            _format_bytes,
        )

        result = _format_bytes(5 * 1024 * 1024 * 1024)
        assert "GB" in result

    def test_negative(self):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            _format_bytes,
        )

        assert _format_bytes(-100) == "0 B"

    def test_invalid(self):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            _format_bytes,
        )

        assert _format_bytes("not a number") == "0 B"


class TestWrapText:
    def test_empty(self):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import _wrap_text

        assert _wrap_text("", 40) == []

    def test_short(self):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import _wrap_text

        assert _wrap_text("hello world", 40) == ["hello world"]

    def test_wrap(self):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import _wrap_text

        result = _wrap_text("word " * 20, 15)
        assert len(result) > 1


class TestCategoryKey:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Data", "data"),
            ("Product Management!", "productmanagement"),
            (None, ""),
            ("", ""),
        ],
        ids=["normal", "special_chars", "none", "empty"],
    )
    def test_category_key(self, raw, expected):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            _category_key,
        )

        assert _category_key(raw) == expected


class TestIsSkillInstalled:
    @patch("pathlib.Path.is_file", return_value=True)
    def test_installed(self, mock_is_file):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            is_skill_installed,
        )

        assert is_skill_installed("my-skill") is True

    @patch("pathlib.Path.is_file", return_value=False)
    def test_not_installed(self, mock_is_file):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            is_skill_installed,
        )

        assert is_skill_installed("my-skill") is False


# ---------------------------------------------------------------------------
# SkillsInstallMenu
# ---------------------------------------------------------------------------


def _make_entry(**kwargs):
    from code_puppy_core_plugins.agent_skills.skill_catalog import SkillCatalogEntry

    defaults = dict(
        id="test-skill",
        name="test-skill",
        display_name="Test Skill",
        description="A test skill",
        category="Data",
        tags=["test"],
        has_scripts=True,
        has_references=False,
        file_count=3,
        download_url="https://example.com/test.zip",
        zip_size_bytes=1024,
    )
    defaults.update(kwargs)
    return SkillCatalogEntry(**defaults)


class TestSkillsInstallMenuInit:
    @patch(f"{_MOD}.catalog")
    def test_init_with_catalog(self, mock_catalog):
        mock_catalog.list_categories.return_value = ["Data", "Finance"]
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            SkillsInstallMenu,
        )

        menu = SkillsInstallMenu()
        assert menu.categories == ["Data", "Finance"]

    @patch(f"{_MOD}.catalog")
    def test_init_catalog_error(self, mock_catalog):
        mock_catalog.list_categories.side_effect = RuntimeError("offline")
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            SkillsInstallMenu,
        )

        menu = SkillsInstallMenu()
        assert menu.categories == []


class TestSkillsInstallMenuRendering:
    def _make_menu(self, categories=None, catalog_mock=None):
        with patch(f"{_MOD}.catalog") as mc:
            mc.list_categories.return_value = categories or []
            if catalog_mock:
                mc.get_by_category = catalog_mock
            else:
                mc.get_by_category.return_value = []
            from code_puppy_core_plugins.agent_skills.skills_install_menu import (
                SkillsInstallMenu,
            )

            menu = SkillsInstallMenu()
            # Re-assign catalog for rendering calls
            menu.catalog = mc
            return menu

    def test_render_category_list_empty(self):
        menu = self._make_menu()
        lines = menu._render_category_list()
        text = "".join(t for _, t in lines)
        assert "No remote categories" in text

    def test_render_category_list_with_items(self):
        menu = self._make_menu(categories=["Data", "Finance"])
        lines = menu._render_category_list()
        text = "".join(t for _, t in lines)
        assert "Data" in text
        assert "Finance" in text

    def test_render_category_list_pagination(self):
        cats = [f"Cat{i}" for i in range(20)]
        menu = self._make_menu(categories=cats)
        lines = menu._render_category_list()
        text = "".join(t for _, t in lines)
        assert "Page 1/" in text

    def test_render_category_list_catalog_error(self):
        def boom(cat):
            raise RuntimeError("fail")

        menu = self._make_menu(categories=["Data"], catalog_mock=boom)
        lines = menu._render_category_list()
        text = "".join(t for _, t in lines)
        assert "Data" in text

    def test_get_category_icon_known(self):
        menu = self._make_menu()
        assert menu._get_category_icon("Data") == "📊"
        assert menu._get_category_icon("Finance") == "💰"
        assert menu._get_category_icon("Legal") == "\u2696\ufe0f"
        assert menu._get_category_icon("Office") == "📄"
        assert menu._get_category_icon("Product Management") == "📦"
        assert menu._get_category_icon("Sales") == "💼"
        assert menu._get_category_icon("Biology") == "🧬"

    def test_get_category_icon_unknown(self):
        menu = self._make_menu()
        assert menu._get_category_icon("Unknown") == "📁"

    def test_get_current_category(self):
        menu = self._make_menu(categories=["Data"])
        assert menu._get_current_category() == "Data"
        menu.selected_category_idx = 99
        assert menu._get_current_category() is None

    def test_get_current_skill_none(self):
        menu = self._make_menu()
        assert menu._get_current_skill() is None

    def test_get_current_skill_in_skills_mode(self):
        menu = self._make_menu(categories=["Data"])
        entry = _make_entry()
        menu.view_mode = "skills"
        menu.current_skills = [entry]
        menu.selected_skill_idx = 0
        assert menu._get_current_skill() == entry

    def test_get_current_skill_out_of_range(self):
        menu = self._make_menu()
        menu.view_mode = "skills"
        menu.current_skills = [_make_entry()]
        menu.selected_skill_idx = 99
        assert menu._get_current_skill() is None

    def test_render_skill_list_no_category(self):
        menu = self._make_menu()
        menu.view_mode = "skills"
        menu.current_category = None
        lines = menu._render_skill_list()
        text = "".join(t for _, t in lines)
        assert "No category selected" in text

    def test_render_skill_list_empty(self):
        menu = self._make_menu(categories=["Data"])
        menu.view_mode = "skills"
        menu.current_category = "Data"
        menu.current_skills = []
        lines = menu._render_skill_list()
        text = "".join(t for _, t in lines)
        assert "No skills in this category" in text

    @patch(f"{_MOD}.is_skill_installed", return_value=False)
    def test_render_skill_list_with_skills(self, mock_inst):
        menu = self._make_menu(categories=["Data"])
        menu.view_mode = "skills"
        menu.current_category = "Data"
        menu.current_skills = [_make_entry(), _make_entry(id="s2", display_name="S2")]
        menu.selected_skill_idx = 0
        lines = menu._render_skill_list()
        text = "".join(t for _, t in lines)
        assert "Test Skill" in text

    @patch(f"{_MOD}.is_skill_installed", return_value=False)
    def test_render_skill_list_pagination(self, mock_inst):
        entries = [
            _make_entry(id=f"s{i}", display_name=f"Skill {i}") for i in range(20)
        ]
        menu = self._make_menu(categories=["Data"])
        menu.view_mode = "skills"
        menu.current_category = "Data"
        menu.current_skills = entries
        lines = menu._render_skill_list()
        text = "".join(t for _, t in lines)
        assert "Page 1/" in text

    def test_render_details_categories_mode_no_selection(self):
        menu = self._make_menu()
        menu.selected_category_idx = 99
        lines = menu._render_details()
        text = "".join(t for _, t in lines)
        assert "No category selected" in text

    def test_render_details_categories_mode_with_skills(self):
        entries = [_make_entry(id=f"s{i}", display_name=f"S{i}") for i in range(3)]
        menu = self._make_menu(categories=["Data"])
        menu.catalog.get_by_category.return_value = entries
        lines = menu._render_details()
        text = "".join(t for _, t in lines)
        assert "Data" in text
        assert "3 skills available" in text

    def test_render_details_categories_catalog_error(self):
        menu = self._make_menu(categories=["Data"])
        menu.catalog.get_by_category.side_effect = RuntimeError("fail")
        lines = menu._render_details()
        text = "".join(t for _, t in lines)
        assert "0 skills available" in text

    @patch(f"{_MOD}.is_skill_installed", return_value=False)
    def test_render_details_skills_mode(self, mock_inst):
        entry = _make_entry()
        menu = self._make_menu(categories=["Data"])
        menu.view_mode = "skills"
        menu.current_skills = [entry]
        menu.selected_skill_idx = 0
        lines = menu._render_details()
        text = "".join(t for _, t in lines)
        assert "Test Skill" in text
        assert "Not installed" in text
        assert "Description" in text

    def test_render_details_no_skill_selected(self):
        menu = self._make_menu()
        menu.view_mode = "skills"
        menu.current_skills = []
        lines = menu._render_details()
        text = "".join(t for _, t in lines)
        assert "No skill selected" in text


class TestSkillsInstallMenuNavigation:
    def _make_menu(self, categories=None):
        with patch(f"{_MOD}.catalog") as mc:
            mc.list_categories.return_value = categories or []
            mc.get_by_category.return_value = [_make_entry()]
            from code_puppy_core_plugins.agent_skills.skills_install_menu import (
                SkillsInstallMenu,
            )

            menu = SkillsInstallMenu()
            menu.catalog = mc
            menu.menu_control = MagicMock()
            menu.preview_control = MagicMock()
            return menu

    def test_enter_category(self):
        menu = self._make_menu(categories=["Data"])
        menu._enter_category()
        assert menu.view_mode == "skills"
        assert menu.current_category == "Data"

    def test_enter_category_no_selection(self):
        menu = self._make_menu()
        menu._enter_category()  # no categories, should not crash
        assert menu.view_mode == "categories"

    def test_enter_category_catalog_error(self):
        menu = self._make_menu(categories=["Data"])
        menu.catalog.get_by_category.side_effect = RuntimeError("fail")
        menu._enter_category()
        assert menu.current_skills == []

    def test_go_back_to_categories(self):
        menu = self._make_menu(categories=["Data"])
        menu._enter_category()
        menu._go_back_to_categories()
        assert menu.view_mode == "categories"
        assert menu.current_category is None

    def test_select_current_skill(self):
        menu = self._make_menu(categories=["Data"])
        menu._enter_category()
        menu._select_current_skill()
        assert menu.result == "pending_install"
        assert menu.pending_entry is not None

    def test_select_current_skill_no_skill(self):
        menu = self._make_menu()
        menu.view_mode = "skills"
        menu.current_skills = []
        menu._select_current_skill()
        assert menu.pending_entry is None

    def test_update_display_categories(self):
        menu = self._make_menu(categories=["Data"])
        menu.update_display()
        # No crash

    def test_update_display_skills(self):
        menu = self._make_menu(categories=["Data"])
        menu.view_mode = "skills"
        menu.current_category = "Data"
        menu.current_skills = [_make_entry()]
        menu.update_display()


# ---------------------------------------------------------------------------
# _prompt_and_install
# ---------------------------------------------------------------------------


class TestPromptAndInstall:
    @patch(f"{_MOD}.download_and_install_skill")
    @patch(f"{_MOD}.safe_input", return_value="y")
    @patch(f"{_MOD}.is_skill_installed", return_value=False)
    def test_install_success(self, mock_inst, mock_input, mock_download):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            _prompt_and_install,
        )
        from code_puppy_core_plugins.agent_skills.installer import InstallResult

        mock_download.return_value = InstallResult(
            success=True, message="OK", installed_path=Path("/tmp/s")
        )
        entry = _make_entry()
        assert _prompt_and_install(entry) is True

    @pytest.mark.parametrize("installed", [False, True], ids=["fresh", "reinstall"])
    @patch(f"{_MOD}.safe_input", return_value="n")
    def test_install_cancelled(self, mock_input, installed):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            _prompt_and_install,
        )

        with patch(f"{_MOD}.is_skill_installed", return_value=installed):
            assert _prompt_and_install(_make_entry()) is False

    @patch(f"{_MOD}.download_and_install_skill")
    @patch(f"{_MOD}.safe_input", return_value="y")
    @patch(f"{_MOD}.is_skill_installed", return_value=True)
    def test_reinstall(self, mock_inst, mock_input, mock_download):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            _prompt_and_install,
        )
        from code_puppy_core_plugins.agent_skills.installer import InstallResult

        mock_download.return_value = InstallResult(success=True, message="OK")
        assert _prompt_and_install(_make_entry()) is True

    @pytest.mark.parametrize(
        "exc", [KeyboardInterrupt, EOFError], ids=["keyboard_interrupt", "eof_error"]
    )
    @patch(f"{_MOD}.safe_input")
    def test_safe_input_abort(self, mock_input, exc):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            _prompt_and_install,
        )

        mock_input.side_effect = exc()
        with patch(f"{_MOD}.is_skill_installed", return_value=False):
            assert _prompt_and_install(_make_entry()) is False

    @patch(f"{_MOD}.download_and_install_skill", side_effect=RuntimeError("net error"))
    @patch(f"{_MOD}.safe_input", return_value="y")
    @patch(f"{_MOD}.is_skill_installed", return_value=False)
    def test_download_error(self, mock_inst, mock_input, mock_download):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            _prompt_and_install,
        )

        assert _prompt_and_install(_make_entry()) is False

    @patch(f"{_MOD}.download_and_install_skill")
    @patch(f"{_MOD}.safe_input", return_value="y")
    @patch(f"{_MOD}.is_skill_installed", return_value=False)
    def test_install_failure_result(self, mock_inst, mock_input, mock_download):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            _prompt_and_install,
        )
        from code_puppy_core_plugins.agent_skills.installer import InstallResult

        mock_download.return_value = InstallResult(success=False, message="Failed")
        assert _prompt_and_install(_make_entry()) is False


# ---------------------------------------------------------------------------
# SkillsInstallMenu.run() and run_skills_install_menu()
# ---------------------------------------------------------------------------


class TestSkillsInstallMenuRun:
    @patch(f"{_MOD}.set_awaiting_user_input")
    @patch("code_puppy_core_plugins.termflow_tui.FragmentTUI")
    @patch(f"{_MOD}.catalog")
    def test_run_no_install(self, mock_cat, mock_tui_cls, mock_await):
        mock_cat.list_categories.return_value = []
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            SkillsInstallMenu,
        )

        menu = SkillsInstallMenu()
        mock_tui_cls.return_value = MagicMock()
        assert menu.run() is False

    @patch(f"{_MOD}._prompt_and_install", return_value=True)
    @patch(f"{_MOD}.set_awaiting_user_input")
    @patch("code_puppy_core_plugins.termflow_tui.FragmentTUI")
    @patch(f"{_MOD}.catalog")
    def test_run_with_pending_install(
        self, mock_cat, mock_tui_cls, mock_await, mock_prompt
    ):
        mock_cat.list_categories.return_value = []
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            SkillsInstallMenu,
        )

        menu = SkillsInstallMenu()

        def fake_run():
            menu.result = "pending_install"
            menu.pending_entry = _make_entry()

        mock_tui_cls.return_value.run.side_effect = fake_run
        assert menu.run() is True
        mock_prompt.assert_called_once()


class TestSkillsInstallMenuKeyBindings:
    def _menu(self, categories=None, skills=None):
        from code_puppy_core_plugins.agent_skills.skills_install_menu import (
            SkillsInstallMenu,
        )

        with patch(f"{_MOD}.catalog") as mock_cat:
            mock_cat.list_categories.return_value = categories or []
            menu = SkillsInstallMenu()
        return menu

    def test_category_navigation(self):
        menu = self._menu(categories=[f"Cat{i}" for i in range(20)])
        assert menu.handle_key("down") is False
        assert menu.selected_category_idx == 1
        menu.handle_key("up")
        assert menu.selected_category_idx == 0
        menu.handle_key("up")
        assert menu.selected_category_idx == 0
        menu.handle_key("right")
        assert menu.current_page == 1
        menu.handle_key("left")
        assert menu.current_page == 0
        menu.handle_key("left")
        assert menu.current_page == 0

    def test_skills_pagination(self):
        menu = self._menu(categories=["Cat0"])
        menu.view_mode = "skills"
        menu.current_skills = [_make_entry() for _ in range(20)]
        menu.handle_key("down")
        assert menu.selected_skill_idx == 1
        menu.handle_key("right")
        assert menu.current_page == 1
        menu.handle_key("left")
        assert menu.current_page == 0
        menu.handle_key("escape")
        assert menu.view_mode == "categories"

    def test_right_no_items(self):
        menu = self._menu(categories=[])
        menu.handle_key("right")
        assert menu.current_page == 0

    def test_enter_on_skill_exits_with_pending(self):
        menu = self._menu(categories=["Cat0"])
        menu.view_mode = "skills"
        menu.current_skills = [_make_entry()]
        assert menu.handle_key("enter") is True
        assert menu.result == "pending_install"

    def test_ctrl_c_exits(self):
        menu = self._menu(categories=["Cat0"])
        assert menu.handle_key("ctrl-c") is True


class TestNavigationHints:
    def _make_menu(self):
        with patch(f"{_MOD}.catalog") as mc:
            mc.list_categories.return_value = []
            from code_puppy_core_plugins.agent_skills.skills_install_menu import (
                SkillsInstallMenu,
            )

            return SkillsInstallMenu()

    def test_hints_categories_mode(self):
        menu = self._make_menu()
        lines = []
        menu._render_navigation_hints(lines)
        text = "".join(t for _, t in lines)
        assert "Browse Skills" in text

    def test_hints_skills_mode(self):
        menu = self._make_menu()
        menu.view_mode = "skills"
        lines = []
        menu._render_navigation_hints(lines)
        text = "".join(t for _, t in lines)
        assert "Install Skill" in text
        assert "Back" in text
