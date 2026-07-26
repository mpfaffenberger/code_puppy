"""Flux bootstrap plugin.

Installs the bundled Flux slash-command suite into ``~/.code_puppy`` on a fresh
install and after every code-puppy version bump, so ``/flux/...`` commands work
out of the box without the user copying anything by hand.

The heavy lifting (copy / backup / version-gating) lives in :mod:`installer`;
this module only wires it to the ``startup`` hook and makes sure a failure can
never crash the app.
"""

from pathlib import Path

from code_puppy.callbacks import register_callback
from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_info, emit_warning

from .installer import install_bundled_commands, needs_install


def _reload_command_cache() -> None:
    """Ask the customizable_commands loader to rescan its dirs. Never raises.

    Imported lazily (not at module scope) so a refactor/rename of that plugin
    can't break flux_bootstrap's own import, and so we don't create a hard
    load-order dependency between the two plugins.
    """
    try:
        from code_puppy.plugins.customizable_commands.register_callbacks import (
            reload_commands,
        )

        reload_commands()
    except Exception as exc:  # a stale cache is not worth crashing over
        emit_warning(f"Flux installed but command cache reload failed: {exc}")


def _current_version() -> str:
    try:
        from code_puppy import __version__

        return str(__version__)
    except Exception:
        return "0.0.0-dev"


def _install_flux_commands() -> None:
    """Version-gated install of the bundled Flux command set. Never raises."""
    try:
        config_dir = Path(CONFIG_DIR)
        version = _current_version()

        if not needs_install(config_dir, version):
            return

        report = install_bundled_commands(config_dir, version)
        if report.changed:
            emit_info(f"Flux commands installed -> {config_dir} ({report.summary()})")
            if report.backed_up:
                emit_warning(
                    "Backed up locally-modified Flux files (see *.bak): "
                    + ", ".join(report.backed_up)
                )
            # The command cache was populated at plugin import time -- before we
            # just wrote these files. Force a rescan so /flux/... is
            # dispatchable *this* session instead of after a restart.
            _reload_command_cache()
    except Exception as exc:  # never let bootstrap break startup
        emit_warning(f"Flux bootstrap skipped (install failed): {exc}")


register_callback("startup", _install_flux_commands)
