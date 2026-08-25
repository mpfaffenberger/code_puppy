"""``register_tools_for_agent`` swap-in behavior for the Anthropic native
editor (Phase 3): when active, overlapping portable tools are replaced by
the native tool ONLY for an agent that already carries the full portable
mutation surface (create_file AND replace_in_file); delete tools are always
preserved; and an agent that never requested the full surface never gains
the native tool either -- see has_full_native_editor_mutation_surface in
model_capabilities.py for why partial overlap must not trigger it.
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
        ["read_file", "replace_in_file", "create_file", "delete_snippet"],
        capability=True,
    )
    assert sorted(calls) == sorted(["delete_snippet", "str_replace_based_edit_tool"])


def test_delete_tools_are_never_hidden_even_when_native_editor_active():
    calls = _registered_names(
        ["replace_in_file", "create_file", "delete_snippet", "delete_file"],
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
