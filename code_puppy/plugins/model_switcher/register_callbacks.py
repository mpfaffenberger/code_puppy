"""/model — theme-style split-panel model switcher.

Replaces the core single-pane /model picker with a curated, /theme-like
experience:

  /model            → interactive split-panel picker with live preview
  /model <name>     → switch by name
  /model show       → show the active model

The command is registered over the core entry (plugins load after built-in
commands), so /model and /m both land here without touching command_line/.
"""

from __future__ import annotations

# Plugins load at cli_runner import time, but core_commands is imported lazily
# on first command dispatch -- which would otherwise re-register the CORE /model
# handler and silently override this plugin. Forcing the import here guarantees
# core registers first, so the override below wins for the whole session.
import code_puppy.command_line.core_commands  # noqa: F401

from code_puppy.command_line.command_registry import register_command


def _handle_model(command: str) -> bool:
    import asyncio
    import concurrent.futures

    from code_puppy.command_line.model_picker_completion import (
        get_active_model,
        load_model_names,
        update_model_in_input,
    )
    from code_puppy.i18n import t
    from code_puppy.messaging import emit_info, emit_success, emit_warning

    tokens = command.split()

    # No args → interactive split-panel picker.
    if len(tokens) == 1:
        try:
            from code_puppy.model_switching import set_model_and_reload_agent
            from code_puppy.plugins.model_switcher.picker import (
                interactive_model_picker,
            )

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    lambda: asyncio.run(interactive_model_picker())
                )
                selected = future.result(timeout=300)

            if selected:
                set_model_and_reload_agent(selected)
                emit_success(t("cmd.model.success", model=selected))
            else:
                emit_warning(t("cmd.model.cancelled"))
            return True
        except Exception as e:
            import traceback

            emit_warning(t("cmd.model.picker_failed", error=e))
            emit_warning(f"Traceback: {traceback.format_exc()}")
            emit_warning(t("cmd.model.usage"))
            return True

    if tokens[1].lower() in ("show", "current"):
        emit_info(f"Active model: {get_active_model()}")
        return True

    # By-name path: reuse the core /model <name> matcher.
    model_command = command
    if command.startswith("/model"):
        model_command = command.replace("/model", "/m", 1)

    new_input = update_model_in_input(model_command)
    if new_input is not None:
        model = get_active_model()
        emit_success(t("cmd.model.success", model=model))
        return True

    model_names = load_model_names()
    emit_warning(t("cmd.model.usage"))
    emit_warning(t("cmd.model.available", models=", ".join(model_names)))
    return True


register_command(
    name="model",
    description="Pick the active model (theme-style split-panel picker)",
    usage="/model, /m <model>",
    aliases=["m"],
    category="core",
)(_handle_model)
