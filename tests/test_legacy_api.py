"""The 0.0.x modules plugins import: callbacks, config, messaging, i18n."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from rich.console import Console

from code_puppy import callbacks, config, i18n, messaging
from code_puppy.legacy_store import LegacyStore

# Every hook name Code Puppy 0.0.969 accepted. A plugin registering any of
# these must keep importing, whether or not 1.0 fires the hook.
HOOKS_0_0_X = """
startup shutdown invoke_agent agent_exception version_check edit_file create_file
replace_in_file delete_snippet delete_file run_shell_command run_shell_command_output
load_model_config load_models_config load_model_descriptions load_prompt agent_reload
custom_command custom_command_help usage_status file_permission pre_tool_call
post_tool_call stream_event thinking_display_filter termflow_style prompt_toolkit_style
termflow_highlighter prompt_text_color register_tools register_agent_tools register_agents
register_model_type register_skills register_settings register_kennel_memory
register_cli_args handle_cli_args get_model_system_prompt prepare_model_prompt
agent_run_start agent_run_end agent_run_result model_select provider_credential_flow
register_mcp_catalog_servers register_browser_types register_model_providers
register_completion_provider check_claude_oauth_token_expiry refresh_claude_oauth_token
load_claude_oauth_models claude_oauth_authenticate message_history_processor_start
message_history_processor_end on_message wrap_pydantic_agent agent_run_context
agent_run_cancel agent_event_stream_start should_skip_fallback_render pre_mcp_autostart
interactive_turn_end interactive_turn_cancel user_prompt_submit pre_compact session_end
post_autosave session_browser_open notification awaiting_user_input git_branch_provider
feature_capability transform_model_messages error_logged banner_notice prompt_ready
""".split()


# --- callbacks ---------------------------------------------------------------


def test_every_0_0_x_hook_still_registers() -> None:
    assert len(HOOKS_0_0_X) == 77
    assert set(HOOKS_0_0_X) == callbacks.ALL_PHASES
    tiers = (callbacks.SUPPORTED, callbacks.ACCEPTED, callbacks.REMOVED)
    assert sum(map(len, tiers)) == 77  # no hook is in two tiers
    for phase in HOOKS_0_0_X:
        callbacks.register_callback(phase, lambda *a, **k: None)


def test_unknown_hooks_and_misused_fail_closed_are_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported callback phase"):
        callbacks.register_callback("not_a_hook", print)
    with pytest.raises(ValueError, match="fail_closed"):
        callbacks.register_callback("startup", print, fail_closed=True)
    with pytest.raises(TypeError):
        callbacks.register_callback("startup", "not callable")  # type: ignore[arg-type]


def test_registration_is_deduplicated_and_reversible() -> None:
    def hook() -> None: ...

    callbacks.register_callback("startup", hook)
    callbacks.register_callback("startup", hook)
    assert callbacks.get_callbacks("startup") == [hook]
    assert callbacks.unregister_callback("startup", hook) is True
    assert callbacks.unregister_callback("startup", hook) is False
    assert callbacks.count_callbacks() == 0


def test_callbacks_are_attributed_to_the_plugin_that_registered_them() -> None:
    def mine() -> None: ...

    def theirs() -> None: ...

    with callbacks.owned_by("alpha"):
        callbacks.register_callback("startup", mine)
        callbacks.register_callback("stream_event", mine)
    callbacks.register_callback("shutdown", theirs)
    assert callbacks.get_callback_owner(mine) == "alpha"
    assert callbacks.get_callback_owner(theirs) is None
    assert callbacks.inert_registrations() == {"alpha": ["stream_event"]}
    assert callbacks.unregister_owner("alpha") == 2
    assert callbacks.count_callbacks() == 1


async def test_fire_awaits_async_callbacks_and_contains_failures() -> None:
    async def slow() -> str:
        return "async"

    def boom() -> None:
        raise RuntimeError("nope")

    callbacks.register_callback("startup", slow)
    callbacks.register_callback("startup", boom)
    callbacks.register_callback("startup", lambda: "sync")
    first, second, third = await callbacks.fire("startup")
    assert (first, third) == ("async", "sync")
    assert isinstance(second, callbacks.CallbackError) and str(second.error) == "nope"


def test_fire_sync_refuses_to_leak_a_coroutine() -> None:
    async def wrong() -> None: ...

    callbacks.register_callback("load_prompt", wrong)
    (result,) = callbacks.fire_sync("load_prompt")
    assert isinstance(result, callbacks.CallbackError)


# --- config ------------------------------------------------------------------


def test_config_round_trips_plugin_keys(
    home: Path, installed_distribution: None
) -> None:
    assert config.get_value("kennel_enabled") is None
    config.set_config_value("kennel_enabled", "true")
    assert config.get_value("kennel_enabled") == "true"
    assert config.get_truthy_bool_value("kennel_enabled") is True
    assert "kennel_enabled" in config.get_config_keys()
    config.set_value("kennel_enabled", "")  # 0.0.x: an empty value forgets the key
    assert config.get_value("kennel_enabled") is None
    assert config.get_truthy_bool_value("kennel_enabled", True) is True


def test_config_reads_migrated_values_and_names(
    home: Path, installed_distribution: None
) -> None:
    LegacyStore().set("puppy_name", "Boodler")
    assert config.get_puppy_name() == "Boodler"
    assert config.get_owner_name() == "Master"


def test_runtime_owned_keys_come_from_the_runtime(
    home: Path, installed_distribution: None
) -> None:
    from pydantic_clai2.config.settings_store import SettingsStore

    store = SettingsStore()
    store.set("model", "anthropic:claude-sonnet-5")
    store.set("run.permissions", "read-only")
    store.set("run.request_limit", 42)
    assert config.get_global_model_name() == "anthropic:claude-sonnet-5"
    assert config.get_yolo_mode() is False
    assert config.get_message_limit() == 42
    # A 0.0.x plugin writing the key cannot change the runtime's setting.
    config.set_config_value("model", "something-else")
    assert config.get_value("model") == "anthropic:claude-sonnet-5"


# --- messaging ---------------------------------------------------------------


def test_emit_functions_print_to_the_session_console() -> None:
    buffer = io.StringIO()
    messaging.set_console(Console(file=buffer, force_terminal=False, width=80))
    messaging.emit_info("hello")
    messaging.emit_warning("careful")
    messaging.emit_error("[/not-markup]")  # must not raise on stray brackets
    messaging.emit_success("done", message_group="x")
    messaging.emit_debug("dropped")
    assert buffer.getvalue().split() == ["hello", "careful", "[/not-markup]", "done"]


def test_bus_module_is_importable_from_its_old_path() -> None:
    from code_puppy.messaging.bus import emit_debug, emit_info

    assert emit_info is messaging.emit_info and emit_debug is messaging.emit_debug


# --- i18n --------------------------------------------------------------------


def test_t_resolves_registered_catalogs_in_english(tmp_path: Path) -> None:
    (tmp_path / "en-US.json").write_text(
        json.dumps({"demo.hello": "Hello {name}", "demo.files.one": "{count} file"}),
        encoding="utf-8",
    )
    (tmp_path / "fr-FR.json").write_text(
        json.dumps({"demo.hello": "Bonjour"}), encoding="utf-8"
    )
    assert i18n.register_plugin_catalog("demo", tmp_path) is True
    assert i18n.t("demo.hello", name="Mike") == "Hello Mike"
    assert i18n.ngettext("demo.files", 1) == "1 file"
    assert i18n.t("demo.unknown") == "demo.unknown"
    assert i18n.add_catalog_dir(tmp_path / "missing") is False


def test_t_never_evaluates_format_expressions() -> None:
    assert i18n.t("{user.__class__}", user="x") == "{user.__class__}"
