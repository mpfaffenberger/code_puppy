"""``register_tools_for_agent`` swap-in behavior for the Anthropic native
editor (Phase 3): when active, overlapping portable tools are replaced by
the native tool ONLY for an agent that already carries the full portable
read+write surface (read_file AND create_file AND replace_in_file); delete
tools are always preserved; and an agent that never requested the full
surface never gains the native tool either -- see
has_full_native_editor_mutation_surface in model_capabilities.py for why
partial overlap must not trigger it, and the read_file requirement at the
call site for why the mutation subset alone isn't sufficient either.
"""

from unittest.mock import MagicMock, patch

from code_puppy.tools import TOOL_REGISTRY, register_tools_for_agent


def _registered_names(tool_names, model_name="claude-direct", capability=True):
    """Run register_tools_for_agent and return which registry entries fired."""
    mock_agent = MagicMock()
    calls: list[str] = []
    fake_registry = {
        name: (lambda agent, n=name: calls.append(n)) for name in TOOL_REGISTRY
    }
    with (
        patch.dict("code_puppy.tools.TOOL_REGISTRY", fake_registry, clear=True),
        patch(
            "code_puppy.tools.supports_anthropic_native_editor",
            return_value=capability,
        ),
    ):
        register_tools_for_agent(mock_agent, tool_names, model_name=model_name)
    return calls


def test_native_editor_replaces_overlapping_tools_when_capability_active():
    calls = _registered_names(
        ["read_file", "replace_in_file", "create_file", "list_files", "delete_snippet"],
        capability=True,
    )
    assert sorted(calls) == sorted(
        ["list_files", "delete_snippet", "str_replace_based_edit_tool"]
    )


def test_delete_tools_are_never_hidden_even_when_native_editor_active():
    calls = _registered_names(
        [
            "read_file",
            "replace_in_file",
            "create_file",
            "list_files",
            "delete_snippet",
            "delete_file",
        ],
        capability=True,
    )
    assert "delete_snippet" in calls
    assert "delete_file" in calls
    assert "replace_in_file" not in calls
    assert "create_file" not in calls


def test_portable_tools_kept_as_is_when_capability_inactive():
    tool_names = ["read_file", "replace_in_file", "create_file", "delete_snippet"]
    calls = _registered_names(tool_names, capability=False)
    assert sorted(calls) == sorted(tool_names)
    assert "str_replace_based_edit_tool" not in calls


def test_agent_that_never_requested_editing_tools_does_not_gain_native_editor():
    """Least-privilege: capability alone must not grant an editing tool to
    an agent whose own tool list never asked for one."""
    calls = _registered_names(["list_files", "grep"], capability=True)
    assert calls == ["list_files", "grep"]
    assert "str_replace_based_edit_tool" not in calls


def test_read_only_agent_without_a_mutation_tool_does_not_gain_write_access():
    """Regression: a read-only profile (read_file + non-editing tools, no
    replace_in_file/create_file) must not be silently upgraded to the
    native editor -- read_file alone being in OVERLAPPING_PORTABLE_TOOLS
    must not be the trigger, only the full mutation surface may be."""
    calls = _registered_names(["list_files", "read_file", "grep"], capability=True)
    assert sorted(calls) == sorted(["list_files", "read_file", "grep"])
    assert "str_replace_based_edit_tool" not in calls


def test_create_only_agent_does_not_gain_replace_and_insert_access():
    """Regression: agent_model_judge's real profile is read_file+create_file
    with no replace_in_file. Swapping it to the native editor would grant
    str_replace/insert access to arbitrary *existing* files (and the
    native `create` command's always-overwrite semantics) it never had
    and never asked for -- create_file alone must not trigger the swap.
    """
    tool_names = ["read_file", "create_file"]
    calls = _registered_names(tool_names, capability=True)
    assert sorted(calls) == sorted(tool_names)
    assert "str_replace_based_edit_tool" not in calls


def test_replace_only_agent_does_not_gain_create_access():
    """Symmetric regression: an agent with only replace_in_file (no
    create_file) must not gain the native `create` command's always-
    overwrite whole-file write, which it could never do before.
    """
    tool_names = ["read_file", "replace_in_file"]
    calls = _registered_names(tool_names, capability=True)
    assert sorted(calls) == sorted(tool_names)
    assert "str_replace_based_edit_tool" not in calls


def test_full_mutation_surface_without_read_file_does_not_gain_view_access():
    """Regression: an agent with the full write surface (create_file AND
    replace_in_file) but no read_file -- an unusual but legal, deliberately
    write-only JSON agent config -- must not be swapped to the native
    editor. `view` is a brand-new read capability that surface never had;
    the swap must require read_file's presence too, not just the mutation
    subset."""
    tool_names = ["replace_in_file", "create_file", "delete_snippet"]
    calls = _registered_names(tool_names, capability=True)
    assert sorted(calls) == sorted(tool_names)
    assert "str_replace_based_edit_tool" not in calls


def test_full_mutation_and_read_surface_without_list_files_does_not_gain_directory_view():
    """Regression: an agent with the full read+write surface (read_file,
    create_file, replace_in_file) but no list_files must not be swapped --
    `view` on a directory path returns a directory listing, which is
    list_files's equivalent capability, not read_file's. Gaining it as a
    side effect of the swap would be a least-privilege violation identical
    in kind to the read_file-less case above."""
    tool_names = ["read_file", "replace_in_file", "create_file", "delete_snippet"]
    calls = _registered_names(tool_names, capability=True)
    assert sorted(calls) == sorted(tool_names)
    assert "str_replace_based_edit_tool" not in calls


def test_explicit_models_config_is_forwarded_to_the_capability_check():
    """Regression: register_tools_for_agent's own callers may have already
    loaded a fresh models config (e.g. the agent builder, right before
    picking the model class from that same config). Without threading it
    through here too, this call would fall back to a separately-TTL-cached
    config load that can very briefly disagree with the fresh one -- a
    real (if narrow) window for the model class and the registered tool
    set to be decided from two different configs. Asserted via the actual
    call arguments, not just behavior, so a future refactor that silently
    drops the parameter is caught even if it doesn't happen to flip any
    single test's capability outcome."""
    mock_agent = MagicMock()
    sentinel_config = {"claude-direct": {"type": "anthropic"}}
    with patch(
        "code_puppy.tools.supports_anthropic_native_editor", return_value=False
    ) as mock_supports:
        register_tools_for_agent(
            mock_agent,
            ["read_file", "replace_in_file", "create_file", "list_files"],
            model_name="claude-direct",
            models_config=sentinel_config,
        )
    assert mock_supports.called
    for call in mock_supports.call_args_list:
        assert call.args == ("claude-direct", sentinel_config)


def test_capability_check_evaluated_exactly_once_per_registration_call():
    """Regression: supports_anthropic_native_editor() re-reads the live
    feature flag on every call (never cached), so evaluating it twice
    within one register_tools_for_agent() pass -- once for the swap
    trigger, once for the defense-in-depth re-check that fires when the
    tool is also named explicitly -- could observe two different answers
    if config changed mid-call. Demonstrated with a side effect that flips
    its answer on a second call: under the old double-evaluation code this
    left the agent with NEITHER the portable mutation tools (removed by
    the swap) NOR the native editor (rejected by the now-stale re-check).
    """
    mock_agent = MagicMock()
    calls: list[str] = []
    fake_registry = {
        name: (lambda agent, n=name: calls.append(n)) for name in TOOL_REGISTRY
    }
    answers = iter([True, False])
    with (
        patch.dict("code_puppy.tools.TOOL_REGISTRY", fake_registry, clear=True),
        patch(
            "code_puppy.tools.supports_anthropic_native_editor",
            side_effect=lambda *a, **k: next(answers),
        ) as mock_supports,
    ):
        register_tools_for_agent(
            mock_agent,
            [
                "read_file",
                "replace_in_file",
                "create_file",
                "list_files",
                "str_replace_based_edit_tool",
            ],
            model_name="claude-direct",
        )
    assert mock_supports.call_count == 1
    assert sorted(calls) == sorted(["list_files", "str_replace_based_edit_tool"])
