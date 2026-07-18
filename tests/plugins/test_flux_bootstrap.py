"""Tests for the flux_bootstrap installer (copy / version-gate / backup)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.plugins.flux_bootstrap import installer


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    return tmp_path / "code_puppy_home"


def test_bundled_payload_present():
    """The plugin must actually ship the Flux command set + scripts."""
    files = {
        p.relative_to(installer.BUNDLED_DIR).as_posix()
        for p in installer._iter_bundled_files()
    }
    assert "commands/flux/rebase.md" in files
    assert "commands/flux/status.md" in files
    assert "scripts/flux_status.py" in files
    # The stock OSS payload must ship ONLY namespaced flux commands -- no loose
    # top-level commands that could shadow a user's own same-named globals on a
    # fresh install (see test_fresh_install_preserves_preexisting_user_command).
    assert "commands/hello-world.md" not in files
    assert "commands/smoke-test.md" not in files
    assert all(
        rel.startswith("commands/flux/") or rel.startswith("scripts/") for rel in files
    ), f"unexpected non-flux payload files: {files}"


def test_fresh_install_copies_everything(config_dir: Path):
    assert installer.needs_install(config_dir, "1.0.0") is True

    report = installer.install_bundled_commands(config_dir, "1.0.0")

    assert report.changed
    assert not report.updated and not report.backed_up
    # Files landed where the exec directives expect them.
    assert (config_dir / "commands" / "flux" / "rebase.md").is_file()
    assert (config_dir / "scripts" / "flux_status.py").is_file()
    # Version marker written -> no longer needs install.
    assert installer.read_installed_version(config_dir) == "1.0.0"
    assert installer.needs_install(config_dir, "1.0.0") is False


def test_reinstall_same_version_is_idempotent(config_dir: Path):
    installer.install_bundled_commands(config_dir, "1.0.0")
    report = installer.install_bundled_commands(config_dir, "1.0.0")

    assert not report.changed
    assert report.skipped  # everything already current


def test_version_bump_updates_unmodified_files(config_dir: Path):
    installer.install_bundled_commands(config_dir, "1.0.0")
    target = config_dir / "commands" / "flux" / "rebase.md"

    # Simulate a shipped change: the on-disk copy no longer matches bundled.
    target.write_text("STALE CONTENT", encoding="utf-8")
    # ...but pretend the manifest still thinks *we* wrote STALE (i.e. it's the
    # previous bundled version, untouched by the user).
    manifest = installer._load_manifest(config_dir)
    manifest[target.relative_to(config_dir).as_posix()] = installer._sha256(target)
    installer._save_manifest(config_dir, manifest)

    report = installer.install_bundled_commands(config_dir, "2.0.0")

    rel = "commands/flux/rebase.md"
    assert rel in report.updated
    assert rel not in report.backed_up  # unmodified -> no backup
    assert target.read_text(encoding="utf-8") != "STALE CONTENT"


def test_user_edited_file_is_backed_up(config_dir: Path):
    installer.install_bundled_commands(config_dir, "1.0.0")
    target = config_dir / "commands" / "flux" / "rebase.md"

    # User hand-edits the file (manifest still holds the original hash, so the
    # on-disk hash won't match -> flagged as user-modified).
    target.write_text("MY LOCAL TWEAKS", encoding="utf-8")

    report = installer.install_bundled_commands(config_dir, "2.0.0")

    backup = target.with_name(target.name + ".bak")
    # report.backed_up now records the actual backup path (relative to config).
    assert backup.relative_to(config_dir).as_posix() in report.backed_up
    assert backup.is_file()
    assert backup.read_text(encoding="utf-8") == "MY LOCAL TWEAKS"
    # Fresh bundled content is now in place.
    assert target.read_text(encoding="utf-8") != "MY LOCAL TWEAKS"


def test_repeated_edits_get_unique_backups(config_dir: Path):
    """Two version bumps against a repeatedly-edited file keep both backups."""
    installer.install_bundled_commands(config_dir, "1.0.0")
    target = config_dir / "commands" / "flux" / "rebase.md"

    target.write_text("EDIT ONE", encoding="utf-8")
    installer.install_bundled_commands(config_dir, "2.0.0")

    target.write_text("EDIT TWO", encoding="utf-8")
    installer.install_bundled_commands(config_dir, "3.0.0")

    bak = target.with_name(target.name + ".bak")
    bak1 = target.with_name(target.name + ".bak.1")
    assert bak.read_text(encoding="utf-8") == "EDIT ONE"
    assert bak1.read_text(encoding="utf-8") == "EDIT TWO"


def test_installed_scripts_keep_executable_bit(config_dir: Path):
    """Permission bits from the bundled source survive the copy."""
    import stat as _stat

    installer.install_bundled_commands(config_dir, "1.0.0")
    for src in installer._iter_bundled_files():
        rel = src.relative_to(installer.BUNDLED_DIR).as_posix()
        dest = config_dir / rel
        assert _stat.S_IMODE(dest.stat().st_mode) == _stat.S_IMODE(src.stat().st_mode)


def test_needs_install_on_version_change(config_dir: Path):
    installer.install_bundled_commands(config_dir, "1.0.0")
    assert installer.needs_install(config_dir, "1.0.0") is False
    assert installer.needs_install(config_dir, "1.0.1") is True


def test_fresh_install_preserves_preexisting_user_command(config_dir: Path):
    """A user's own global command must survive a first Flux install untouched.

    Regression for the finding that a fresh install backed up + overwrote any
    existing file it didn't have a manifest entry for. A pre-existing,
    user-owned command that merely shares a name with our payload must be left
    exactly in place: no overwrite, no ``.bak``, and never claimed in the
    manifest.
    """
    # Pretend the user already had a hand-written command at a path our payload
    # also happens to occupy. (rebase.md is genuinely in the bundle.)
    target = config_dir / "commands" / "flux" / "rebase.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("MY OWN REBASE COMMAND", encoding="utf-8")

    report = installer.install_bundled_commands(config_dir, "1.0.0")

    rel = "commands/flux/rebase.md"
    # Preserved verbatim -- not overwritten.
    assert target.read_text(encoding="utf-8") == "MY OWN REBASE COMMAND"
    # No backup was created for a file we never owned.
    assert not target.with_name(target.name + ".bak").exists()
    assert rel not in report.backed_up
    assert rel not in report.updated
    assert rel in report.skipped
    # We must NOT have claimed the user's file in the manifest.
    assert rel not in installer._load_manifest(config_dir)


def test_preexisting_user_command_survives_version_bump(config_dir: Path):
    """Once preserved, a user's same-named command keeps winning across bumps."""
    target = config_dir / "commands" / "flux" / "rebase.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("MY OWN REBASE COMMAND", encoding="utf-8")

    installer.install_bundled_commands(config_dir, "1.0.0")
    installer.install_bundled_commands(config_dir, "2.0.0")

    assert target.read_text(encoding="utf-8") == "MY OWN REBASE COMMAND"
    assert not target.with_name(target.name + ".bak").exists()


def test_first_run_lifecycle_makes_flux_dispatchable_without_restart(config_dir: Path):
    """Full plugin lifecycle: on a fresh install /flux/status is usable *now*.

    Regression for the BLOCKER: the customizable_commands cache is populated at
    plugin import time (before Flux is installed), and Flux installs later in the
    ``startup`` hook. Without an explicit cache reload after the install, the
    freshly-written /flux/... files are invisible until the next restart.

    This drives the real code path: an empty command cache (mirroring the
    import-time load that happened before Flux existed on disk), then the flux
    bootstrap ``startup`` callback, then an assertion that the command is
    dispatchable -- with no manual reload in the test.
    """
    from code_puppy.plugins.customizable_commands import register_callbacks as cc
    from code_puppy.plugins.flux_bootstrap import register_callbacks as flux_rc

    commands_dir = config_dir / "commands"

    # Snapshot + restore the module-level cache so we don't leak into other
    # tests. IMPORTANT: other test modules import these dicts *by reference*, so
    # we must restore them in place (clear + update) rather than rebind -- a
    # rebind would leave those modules pointing at the polluted originals.
    saved_commands = dict(cc._custom_commands)
    saved_descriptions = dict(cc._command_descriptions)
    saved_exec = dict(cc._command_exec_directives)
    saved_loaded = cc._commands_loaded
    try:
        with (
            patch.object(flux_rc, "CONFIG_DIR", str(config_dir)),
            patch.object(cc, "_COMMAND_DIRECTORIES", [str(commands_dir)]),
            patch.object(
                cc, "_TRUSTED_EXEC_DIRECTORIES", frozenset({str(commands_dir)})
            ),
        ):
            # 1. Simulate the import-time load that ran BEFORE Flux was on disk:
            #    the dir doesn't exist yet, so the cache comes up empty.
            cc._load_markdown_commands()
            assert "flux/status" not in cc._custom_commands
            assert "flux/status" not in cc._command_exec_directives

            # 2. Run the actual flux bootstrap startup callback (install + reload).
            flux_rc._install_flux_commands()

            # 3. Files landed AND the cache was reloaded -> dispatchable now,
            #    no restart. /flux/status is an exec: command.
            assert (commands_dir / "flux" / "status.md").is_file()
            assert cc.is_custom_command("flux/status")
            assert "flux/status" in cc._command_exec_directives
    finally:
        cc._custom_commands.clear()
        cc._custom_commands.update(saved_commands)
        cc._command_descriptions.clear()
        cc._command_descriptions.update(saved_descriptions)
        cc._command_exec_directives.clear()
        cc._command_exec_directives.update(saved_exec)
        cc._commands_loaded = saved_loaded
