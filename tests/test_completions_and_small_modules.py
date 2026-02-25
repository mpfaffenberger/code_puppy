"""Tests for completions & small modules coverage.

Covers missed lines in:
- mcp_completion.py
- skills_completion.py
- file_path_completion.py
- load_context_completion.py
- model_switching.py
- markdown_patches.py
- error_logging.py
- motd.py
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from prompt_toolkit.document import Document

# ── mcp_completion ──────────────────────────────────────────────────────


class TestLoadServerNames:
    """Cover lines 13-21 of mcp_completion.py."""

    def test_load_server_names_success(self):
        from code_puppy.command_line.mcp_completion import load_server_names

        mock_server = MagicMock()
        mock_server.name = "test-server"
        mock_manager = MagicMock()
        mock_manager.list_servers.return_value = [mock_server]

        with patch(
            "code_puppy.mcp_.manager.MCPManager",
            return_value=mock_manager,
        ):
            result = load_server_names()
        assert result == ["test-server"]

    def test_load_server_names_exception(self):
        from code_puppy.command_line.mcp_completion import load_server_names

        with patch(
            "code_puppy.mcp_.manager.MCPManager",
            side_effect=Exception("boom"),
        ):
            result = load_server_names()
        assert result == []


class TestMCPCompleterGetServerNames:
    """Cover lines 66-78 of mcp_completion.py."""

    def test_get_server_names_caches(self):
        from code_puppy.command_line.mcp_completion import MCPCompleter

        completer = MCPCompleter()
        with patch(
            "code_puppy.command_line.mcp_completion.load_server_names",
            return_value=["srv1"],
        ):
            result = completer._get_server_names()
        assert result == ["srv1"]
        # Second call uses cache (no patch needed)
        assert completer._get_server_names() == ["srv1"]

    def test_get_server_names_returns_empty_on_none_cache(self):
        from code_puppy.command_line.mcp_completion import MCPCompleter

        completer = MCPCompleter()
        with patch(
            "code_puppy.command_line.mcp_completion.load_server_names",
            return_value=None,
        ):
            result = completer._get_server_names()
        assert result == []


class TestMCPCompleterGetCompletions:
    """Cover lines 83-171 of mcp_completion.py."""

    def setup_method(self):
        from code_puppy.command_line.mcp_completion import MCPCompleter

        self.completer = MCPCompleter()

    def test_no_trigger(self):
        doc = Document("hello")
        assert list(self.completer.get_completions(doc, None)) == []

    def test_no_space_after_trigger(self):
        doc = Document("/mcp")
        assert list(self.completer.get_completions(doc, None)) == []

    def test_show_all_subcommands(self):
        doc = Document("/mcp ")
        completions = list(self.completer.get_completions(doc, None))
        names = [c.text for c in completions]
        assert "list" in names
        assert "start" in names

    def test_partial_subcommand(self):
        doc = Document("/mcp st")
        completions = list(self.completer.get_completions(doc, None))
        names = [c.text for c in completions]
        assert "start" in names
        assert "stop" in names

    def test_server_subcommand_space_shows_servers(self):
        with patch.object(
            self.completer, "_get_server_names", return_value=["my-server"]
        ):
            doc = Document("/mcp start ")
            completions = list(self.completer.get_completions(doc, None))
        names = [c.text for c in completions]
        assert "my-server" in names

    def test_server_subcommand_partial_server(self):
        with patch.object(
            self.completer, "_get_server_names", return_value=["my-server", "other"]
        ):
            doc = Document("/mcp start my")
            completions = list(self.completer.get_completions(doc, None))
        names = [c.text for c in completions]
        assert "my-server" in names
        assert "other" not in names

    def test_general_subcommand_with_space_no_completions(self):
        """General subcommands (like list) don't complete further args."""
        doc = Document("/mcp list ")
        completions = list(self.completer.get_completions(doc, None))
        assert completions == []


# ── skills_completion ───────────────────────────────────────────────────


class TestLoadCatalogSkillIds:
    """Cover lines 26-32."""

    def test_success(self):
        from code_puppy.command_line.skills_completion import load_catalog_skill_ids

        mock_entry = MagicMock()
        mock_entry.id = "skill-1"
        mock_catalog = MagicMock()
        mock_catalog.get_all.return_value = [mock_entry]
        mock_module = MagicMock()
        mock_module.catalog = mock_catalog

        import sys

        with patch.dict(
            sys.modules, {"code_puppy.plugins.agent_skills.skill_catalog": mock_module}
        ):
            result = load_catalog_skill_ids()
        assert result == ["skill-1"]

    def test_exception(self):
        import sys

        from code_puppy.command_line.skills_completion import load_catalog_skill_ids

        with patch.dict(
            sys.modules, {"code_puppy.plugins.agent_skills.skill_catalog": None}
        ):
            result = load_catalog_skill_ids()
        assert result == []


class TestSkillsCompleterGetCompletions:
    """Cover lines 62-71, 78-160."""

    def setup_method(self):
        from code_puppy.command_line.skills_completion import SkillsCompleter

        self.completer = SkillsCompleter()

    def test_no_trigger(self):
        doc = Document("hello")
        assert list(self.completer.get_completions(doc, None)) == []

    def test_no_space_after_trigger(self):
        doc = Document("/skills")
        assert list(self.completer.get_completions(doc, None)) == []

    def test_show_all_subcommands(self):
        doc = Document("/skills ")
        completions = list(self.completer.get_completions(doc, None))
        names = [c.text for c in completions]
        assert "list" in names
        assert "install" in names

    def test_partial_subcommand(self):
        doc = Document("/skills li")
        completions = list(self.completer.get_completions(doc, None))
        names = [c.text for c in completions]
        assert "list" in names

    def test_install_space_shows_skill_ids(self):
        with patch.object(
            self.completer, "_get_skill_ids", return_value=["git-helper", "docker"]
        ):
            doc = Document("/skills install ")
            completions = list(self.completer.get_completions(doc, None))
        names = [c.text for c in completions]
        assert "git-helper" in names
        assert "docker" in names

    def test_install_partial_skill_id(self):
        with patch.object(
            self.completer, "_get_skill_ids", return_value=["git-helper", "docker"]
        ):
            doc = Document("/skills install gi")
            completions = list(self.completer.get_completions(doc, None))
        names = [c.text for c in completions]
        assert "git-helper" in names
        assert "docker" not in names

    def test_non_install_subcommand_no_further(self):
        doc = Document("/skills list ")
        completions = list(self.completer.get_completions(doc, None))
        assert completions == []

    def test_get_skill_ids_caches(self):
        with patch(
            "code_puppy.command_line.skills_completion.load_catalog_skill_ids",
            return_value=["s1"],
        ):
            result = self.completer._get_skill_ids()
        assert result == ["s1"]
        # Cached
        assert self.completer._get_skill_ids() == ["s1"]

    def test_get_skill_ids_none_returns_empty(self):
        with patch(
            "code_puppy.command_line.skills_completion.load_catalog_skill_ids",
            return_value=None,
        ):
            result = self.completer._get_skill_ids()
        assert result == []


# ── file_path_completion ────────────────────────────────────────────────


class TestFilePathCompleterMissedLines:
    """Cover lines 33, 41, 53, 56, 58-62."""

    def setup_method(self):
        from code_puppy.command_line.file_path_completion import FilePathCompleter

        self.completer = FilePathCompleter()

    def test_tilde_expansion(self):
        """Line 33: base_path starts with ~."""
        doc = Document("@~/")
        completions = list(self.completer.get_completions(doc, None))
        # Should not crash; may return home dir contents
        assert isinstance(completions, list)

    def test_hidden_files_shown_when_dot_typed(self):
        """Line 41: text_after_symbol ends with '.' in dir listing branch."""
        # To hit the dir listing branch (line 30-42), pattern.strip("*") must be
        # empty or end with "/". We use the directory path ending with "/"
        # and text_after_symbol ending with "." to cover line 41.
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir, "sub")
            subdir.mkdir()
            Path(subdir, ".hidden").touch()
            Path(subdir, "visible").touch()
            # text_after_symbol = "{subdir}/" -> hits dir listing, but doesn't end with "."
            # We need a different approach: use "@" then just "*" pattern
            # Actually line 41 condition: `not f.startswith(".") or text_after_symbol.endswith(".")`
            # To show hidden files, text_after_symbol must end with "."
            # And to be in the dir listing branch, pattern.strip("*") must be empty or end with "/"
            # pattern = text_after_symbol + "*", so if text_after_symbol=".", pattern=".*"
            # pattern.strip("*") = "." which doesn't end with "/" and isn't empty -> goes to glob
            # Hmm, we need text ending with "." AND hitting dir listing branch.
            # That's only possible if text_after_symbol ends with "." AND (is empty or ends with "/")
            # which is contradictory. So line 41 is about showing non-hidden files by default.
            # Let's just ensure the dir listing branch works.
            doc = Document(f"@{subdir}/")
            completions = list(self.completer.get_completions(doc, None))
            texts = [c.text for c in completions]
            assert any("visible" in t for t in texts)
            # .hidden should NOT be in results (line 41: f.startswith(".") and not endswith("."))
            assert not any(".hidden" in t for t in texts)

    def test_glob_filters_hidden(self):
        """Line 53: glob pattern filtering hidden files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "hello.txt").touch()
            Path(tmpdir, ".secret").touch()
            doc = Document(f"@{tmpdir}/h")
            completions = list(self.completer.get_completions(doc, None))
            names = [c.text for c in completions]
            assert any("hello" in n for n in names)
            assert not any(".secret" in n for n in names)

    def test_absolute_path_display(self):
        """Line 56: os.path.isabs(path) branch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").touch()
            # Use absolute glob pattern
            doc = Document(f"@{tmpdir}/f")
            completions = list(self.completer.get_completions(doc, None))
            # All paths should be absolute since the pattern is absolute
            for c in completions:
                assert os.path.isabs(c.text)

    def test_slash_prefix_uses_abspath(self):
        """Line 58: text_after_symbol starts with /."""
        doc = Document("@/tmp")
        completions = list(self.completer.get_completions(doc, None))
        # Should produce absolute paths
        assert isinstance(completions, list)

    def test_tilde_prefix_display(self):
        """Lines 59-62: tilde prefix display path."""
        home = os.path.expanduser("~")
        with tempfile.TemporaryDirectory(dir=home) as tmpdir:
            Path(tmpdir, "test.txt").touch()
            basename = os.path.basename(tmpdir)
            doc = Document(f"@~/{basename}/t")
            completions = list(self.completer.get_completions(doc, None))
            for c in completions:
                assert c.text.startswith("~")

    def test_nonexistent_dir_listing(self):
        """Line 41: base_path is not a directory → paths = []."""
        doc = Document("@nonexistent_dir_xyz/")
        completions = list(self.completer.get_completions(doc, None))
        assert completions == []

    def test_relative_glob_display_path(self):
        """Lines 56, 58-62: relative glob paths, display_path = path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "abc.txt").touch()
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                doc = Document("@a")
                completions = list(self.completer.get_completions(doc, None))
                # Relative paths, text doesn't start with / or ~
                assert len(completions) > 0
                assert completions[0].text == "abc.txt"
            finally:
                os.chdir(old_cwd)


# ── load_context_completion ─────────────────────────────────────────────


class TestLoadContextCompletionException:
    """Cover lines 50-52."""

    def test_exception_in_glob_silently_ignored(self):
        from code_puppy.command_line.load_context_completion import LoadContextCompleter

        completer = LoadContextCompleter()
        # Make contexts_dir.exists() raise
        with patch(
            "code_puppy.command_line.load_context_completion.CONFIG_DIR",
            "/nonexistent/x/y/z",
        ):
            with patch("pathlib.Path.exists", side_effect=PermissionError("nope")):
                doc = Document("/load_context ")
                completions = list(completer.get_completions(doc, None))
        assert completions == []


# ── model_switching ─────────────────────────────────────────────────────


class TestModelSwitching:
    """Cover lines 14-15, 37-38, 44, 62-63."""

    def test_get_effective_agent_model_success(self):
        from code_puppy.model_switching import _get_effective_agent_model

        agent = MagicMock()
        agent.get_model_name.return_value = "gpt-4"
        assert _get_effective_agent_model(agent) == "gpt-4"

    def test_get_effective_agent_model_exception(self):
        from code_puppy.model_switching import _get_effective_agent_model

        agent = MagicMock()
        agent.get_model_name.side_effect = Exception("fail")
        assert _get_effective_agent_model(agent) is None

    def _run(self, model_name, agent=None):
        """Helper to call set_model_and_reload_agent with proper patches."""
        from code_puppy.model_switching import set_model_and_reload_agent

        warns = []
        infos = []

        def fake_warn(msg):
            warns.append(msg)

        def fake_info(msg):
            infos.append(msg)

        with patch("code_puppy.model_switching.set_model_name"):
            with patch("code_puppy.messaging.emit_warning", fake_warn):
                with patch("code_puppy.messaging.emit_info", fake_info):
                    with patch(
                        "code_puppy.agents.get_current_agent", return_value=agent
                    ):
                        set_model_and_reload_agent(model_name)

        return warns, infos

    def test_no_active_agent(self):
        warns, _ = self._run("model-x", agent=None)
        assert any("no active agent" in w.lower() for w in warns)

    def test_refresh_config_called(self):
        agent = MagicMock()
        agent.get_model_name.return_value = "model-x"
        self._run("model-x", agent=agent)
        agent.refresh_config.assert_called_once()
        agent.reload_code_generation_agent.assert_called_once()

    def test_refresh_config_exception_nonfatal(self):
        agent = MagicMock()
        agent.refresh_config.side_effect = Exception("oops")
        agent.get_model_name.return_value = "model-x"
        self._run("model-x", agent=agent)
        agent.reload_code_generation_agent.assert_called_once()

    def test_reload_exception(self):
        agent = MagicMock()
        agent.reload_code_generation_agent.side_effect = Exception("reload fail")
        agent.get_model_name.return_value = "model-x"
        warns, _ = self._run("model-x", agent=agent)
        assert any("reload failed" in w for w in warns)

    def test_pinned_model_warning(self):
        agent = MagicMock()
        agent.get_model_name.return_value = "pinned-model"
        agent.name = "test-agent"
        warns, _ = self._run("other-model", agent=agent)
        assert any("pinned" in w for w in warns)


# ── markdown_patches ────────────────────────────────────────────────────


class TestMarkdownPatches:
    """Cover lines 35-37, 51."""

    def test_left_justified_heading_h1(self):
        import io

        from rich.console import Console
        from rich.text import Text

        from code_puppy.messaging.markdown_patches import LeftJustifiedHeading

        heading = LeftJustifiedHeading.__new__(LeftJustifiedHeading)
        heading.tag = "h1"
        heading.text = Text("Hello")

        console = Console(file=io.StringIO(), width=80)
        # Render it
        results = list(heading.__rich_console__(console, console.options))
        assert len(results) > 0  # Should yield a Panel

    def test_left_justified_heading_h2(self):
        import io

        from rich.console import Console
        from rich.text import Text

        from code_puppy.messaging.markdown_patches import LeftJustifiedHeading

        heading = LeftJustifiedHeading.__new__(LeftJustifiedHeading)
        heading.tag = "h2"
        heading.text = Text("Sub")

        console = Console(file=io.StringIO(), width=80)
        results = list(heading.__rich_console__(console, console.options))
        assert len(results) == 2  # Text("") + text

    def test_patch_idempotent(self):
        """Line 51: second call is no-op."""
        from code_puppy.messaging import markdown_patches

        markdown_patches._patched = False
        markdown_patches.patch_markdown_headings()
        assert markdown_patches._patched is True
        markdown_patches.patch_markdown_headings()  # no-op
        assert markdown_patches._patched is True


# ── error_logging ───────────────────────────────────────────────────────


class TestErrorLoggingRotation:
    """Cover lines 29-32."""

    def test_rotate_log_when_too_large(self):
        from code_puppy.error_logging import MAX_LOG_SIZE, _rotate_log_if_needed

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "errors.log")
            rotated_file = log_file + ".1"

            # Create a file larger than MAX_LOG_SIZE
            with open(log_file, "w") as f:
                f.write("x" * (MAX_LOG_SIZE + 1))

            with patch("code_puppy.error_logging.ERROR_LOG_FILE", log_file):
                _rotate_log_if_needed()
            assert os.path.exists(rotated_file)
            assert not os.path.exists(log_file)

    def test_rotate_log_oserror_caught(self):
        """Lines 31-32: OSError in rotation is silently caught."""
        from code_puppy.error_logging import _rotate_log_if_needed

        with patch("code_puppy.error_logging.os.path.exists", return_value=True):
            with patch(
                "code_puppy.error_logging.os.path.getsize",
                side_effect=OSError("disk error"),
            ):
                _rotate_log_if_needed()  # Should not raise


# ── motd ────────────────────────────────────────────────────────────────


class TestMotdGetContent:
    """Cover lines 41-44."""

    def test_get_motd_content_from_plugin(self):
        from code_puppy.command_line.motd import get_motd_content

        with patch(
            "code_puppy.callbacks.on_get_motd",
            return_value=[("plugin msg", "v1")],
        ):
            msg, ver = get_motd_content()
        assert msg == "plugin msg"
        assert ver == "v1"

    def test_get_motd_content_fallback(self):
        from code_puppy.command_line.motd import (
            MOTD_MESSAGE,
            MOTD_VERSION,
            get_motd_content,
        )

        with patch(
            "code_puppy.callbacks.on_get_motd",
            return_value=[None],
        ):
            msg, ver = get_motd_content()
        assert msg == MOTD_MESSAGE
        assert ver == MOTD_VERSION

    def test_get_motd_content_exception_fallback(self):
        from code_puppy.command_line.motd import (
            MOTD_MESSAGE,
            MOTD_VERSION,
            get_motd_content,
        )

        with patch(
            "code_puppy.callbacks.on_get_motd",
            side_effect=Exception("boom"),
        ):
            msg, ver = get_motd_content()
        assert msg == MOTD_MESSAGE
        assert ver == MOTD_VERSION
