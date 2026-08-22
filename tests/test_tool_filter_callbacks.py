from __future__ import annotations

from code_puppy import callbacks


def test_agent_tool_filters_compose_in_registration_order():
    callbacks.clear_callbacks("filter_agent_tools")
    try:
        callbacks.register_callback(
            "filter_agent_tools",
            lambda _agent, tools: tools + ["added"],
        )
        callbacks.register_callback(
            "filter_agent_tools",
            lambda _agent, tools: [name for name in tools if name != "removed"],
        )

        assert callbacks.on_filter_agent_tools("code-puppy", ["kept", "removed"]) == [
            "kept",
            "added",
        ]
    finally:
        callbacks.clear_callbacks("filter_agent_tools")


def test_agent_tool_filter_failure_leaves_previous_result_usable():
    callbacks.clear_callbacks("filter_agent_tools")

    def explode(_agent, _tools):
        raise RuntimeError("boom")

    try:
        callbacks.register_callback("filter_agent_tools", explode)
        assert callbacks.on_filter_agent_tools("code-puppy", ["kept"]) == ["kept"]
    finally:
        callbacks.clear_callbacks("filter_agent_tools")


def test_invalid_agent_tool_filter_result_is_ignored():
    callbacks.clear_callbacks("filter_agent_tools")
    try:
        callbacks.register_callback(
            "filter_agent_tools", lambda _agent, _tools: "not-a-list"
        )
        assert callbacks.on_filter_agent_tools("code-puppy", ["kept"]) == ["kept"]
    finally:
        callbacks.clear_callbacks("filter_agent_tools")
