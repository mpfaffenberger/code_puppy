"""Risk-acceptance flow for enabling project-level plugins.

Project plugins (``<CWD>/.code_puppy/plugins/``) are **disabled by default**
because they execute arbitrary repo-supplied code at import time.

The risk-acceptance ceremony lives in the ``/plugins`` TUI (select the
plugin, press Enter, type ``trust`` in the popup). This module provides the
non-interactive primitives the TUI calls — ``grant_trust_and_load`` and
``activate_project_plugin`` — plus the slash-command handlers, which for
untrusted plugins LAUNCH the TUI (preselected, popup open) rather than
prompting inline.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# The word the user must type in the TUI popup to accept the risk. A y/n
# would be too easy to fat-finger; typing the word is a deliberate speed bump.
ACCEPT_WORD = "trust"


def plugin_file_listing(plugin_dir: Path, limit: int = 20) -> str:
    """Bullet list of the files the user is about to trust."""
    try:
        files = sorted(
            p.relative_to(plugin_dir).as_posix()
            for p in plugin_dir.rglob("*")
            if p.is_file() and "__pycache__" not in p.relative_to(plugin_dir).parts
        )
    except OSError as exc:
        logger.warning("Could not list plugin dir %s: %s", plugin_dir, exc)
        return "  (unreadable)"
    lines = [f"  • {name}" for name in files[:limit]]
    if len(files) > limit:
        lines.append(f"  … and {len(files) - limit} more")
    return "\n".join(lines) if lines else "  (no files)"


def activate_project_plugin(plugin_name: str) -> tuple[bool, str]:
    """Clear the disabled flag and hot-load an ALREADY TRUSTED project plugin.

    Fail closed: ``load_project_plugin_now`` re-checks the trust store, so
    calling this for an untrusted plugin loads nothing.

    Returns ``(ok, human_message)``.
    """
    from code_puppy.plugins import get_loaded_plugins, load_project_plugin_now
    from code_puppy.plugins.config import set_plugin_disabled

    set_plugin_disabled(plugin_name, False)

    if plugin_name in get_loaded_plugins()["project"]:
        return True, f"Project plugin '{plugin_name}' enabled."
    if load_project_plugin_now(plugin_name):
        return True, (
            f"Project plugin '{plugin_name}' trusted and loaded — no restart needed."
        )
    return False, f"Loading '{plugin_name}' failed — check the logs."


def grant_trust_and_load(plugin_name: str) -> tuple[bool, str]:
    """Record trust at the current content hash, then activate.

    ONLY call this after the user completed the TUI risk-acceptance popup
    (typed the accept word). This function does no prompting itself.

    Returns ``(ok, human_message)``.
    """
    from code_puppy.plugins import get_project_plugins_directory
    from code_puppy.plugins import trust as plugin_trust

    project_dir = get_project_plugins_directory()
    if project_dir is None:
        return False, "No project plugins directory in this project."
    plugin_dir = project_dir / plugin_name
    if not plugin_dir.is_dir():
        return False, f"'{plugin_name}' is not a project plugin here."

    project_root = project_dir.parent.parent
    if not plugin_trust.trust_plugin(project_root, plugin_name, plugin_dir):
        return False, f"Could not record trust for '{plugin_name}' — see logs."
    return activate_project_plugin(plugin_name)


def try_enable_project_plugin(plugin_name: str) -> bool:
    """Handle ``/plugins enable`` for project plugins.

    Trusted plugins (e.g. previously disabled) are activated directly.
    Untrusted/changed plugins are NOT prompted for inline — the ceremony
    lives in the TUI, so we open it with the plugin preselected and the
    popup already up. Returns True if *plugin_name* is a project plugin
    (fully handled either way); False lets the generic enable path run.
    """
    from code_puppy.messaging import emit_error, emit_info, emit_success
    from code_puppy.plugins import get_project_plugins_directory
    from code_puppy.plugins import trust as plugin_trust

    project_dir = get_project_plugins_directory()
    if project_dir is None:
        return False
    plugin_dir = project_dir / plugin_name
    if not plugin_dir.is_dir():
        return False  # not a project plugin — let the generic toggle handle it

    project_root = project_dir.parent.parent
    status = plugin_trust.get_trust_status(project_root, plugin_name, plugin_dir)

    if status != plugin_trust.TRUSTED:
        # Don't tell the user where the ceremony lives — take them there,
        # preselected with the popup already open. Text fallback only if
        # the TUI can't run (headless/non-tty).
        try:
            from code_puppy.plugins.plugin_list.plugins_menu import (
                run_plugins_menu,
            )

            run_plugins_menu(focus_plugin=plugin_name)
        except Exception as exc:
            logger.warning("Plugins TUI failed for enable ceremony: %s", exc)
            emit_info(
                f"Project plugin '{plugin_name}' requires the review "
                "ceremony: run /plugins, select it, press Enter, and type "
                f"'{ACCEPT_WORD}'."
            )
        return True

    ok, message = activate_project_plugin(plugin_name)
    (emit_success if ok else emit_error)(message)
    return True


def revoke_project_plugin(plugin_name: str) -> bool:
    """Handle ``/plugins revoke <name>`` — remove trust for a project plugin.

    Always returns True (the command is fully handled, with messaging).
    """
    from code_puppy.messaging import emit_info, emit_success, emit_warning
    from code_puppy.plugins import get_loaded_plugins, get_project_plugins_directory
    from code_puppy.plugins import trust as plugin_trust
    from code_puppy.plugins.config import set_plugin_disabled

    project_dir = get_project_plugins_directory()
    if project_dir is None:
        emit_info("No project plugins directory in this project.")
        return True

    project_root = project_dir.parent.parent
    if plugin_trust.revoke_plugin(project_root, plugin_name):
        emit_success(f"Trust revoked for project plugin '{plugin_name}'.")
        if plugin_name in get_loaded_plugins()["project"]:
            # Already imported this session — best we can do is stop its
            # callbacks now; a restart fully unloads it.
            set_plugin_disabled(plugin_name, True)
            emit_warning(
                "It was already loaded this session — callbacks are now "
                "skipped; restart Code Puppy to fully unload it."
            )
    else:
        emit_info(f"'{plugin_name}' was not trusted — nothing to revoke.")
    return True
