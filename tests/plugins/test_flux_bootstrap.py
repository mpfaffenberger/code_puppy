"""Tests for the flux_bootstrap installer (copy / version-gate / backup)."""

from pathlib import Path

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
    # Everything-in-the-zip: the loose extras came along too.
    assert "commands/hello-world.md" in files


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
