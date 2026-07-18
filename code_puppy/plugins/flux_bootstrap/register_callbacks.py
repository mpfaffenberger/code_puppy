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
    except Exception as exc:  # never let bootstrap break startup
        emit_warning(f"Flux bootstrap skipped (install failed): {exc}")


register_callback("startup", _install_flux_commands)
