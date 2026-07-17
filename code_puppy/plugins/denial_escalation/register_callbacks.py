"""Scope denial counters to each top-level agent run."""

from code_puppy.callbacks import register_callback
from code_puppy.command_line.set_menu_schema import Setting, SettingsCategory
from code_puppy.safety.denials import clear_denial_scope, start_denial_scope


def _start(agent_name, model_name, session_id=None):
    del agent_name, model_name
    start_denial_scope(session_id)


def _end(*args, **kwargs):
    del args, kwargs
    clear_denial_scope()


def _settings():
    return SettingsCategory(
        name="Safety",
        settings=(
            Setting(
                key="denial_consecutive_threshold",
                display_name="Consecutive Denial Escalation",
                description="Prompt a human after this many consecutive denied actions.",
                type_hint="int",
                effective_getter=lambda: 3,
            ),
            Setting(
                key="denial_total_threshold",
                display_name="Total Denial Escalation",
                description="Prompt a human after this many denied actions in one run.",
                type_hint="int",
                effective_getter=lambda: 20,
            ),
        ),
    )


register_callback("agent_run_start", _start)
register_callback("agent_run_end", _end)
register_callback("register_settings", _settings)
