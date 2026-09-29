"""Only browser inspection tools that avoid implicit writes may speculate."""

from pydantic_ai import Agent

from code_puppy.tools.browser import browser_workflows


def test_browser_inspection_metadata():
    agent = Agent("test")
    for register in (
        browser_workflows.register_list_workflows,
        browser_workflows.register_read_workflow,
        browser_workflows.register_save_workflow,
    ):
        register(agent)

    tools = agent._function_toolset.tools
    for name in (
        "browser_list_workflows",
        "browser_read_workflow",
    ):
        assert tools[name].metadata["speculatable"] is True
    for name in ("browser_save_workflow",):
        assert not (tools[name].metadata or {}).get("speculatable", False)


def test_workflow_reads_do_not_create_directory(tmp_path, monkeypatch):
    import asyncio

    monkeypatch.setattr(browser_workflows.config, "DATA_DIR", tmp_path)
    assert asyncio.run(browser_workflows.list_workflows())["success"]
    assert not asyncio.run(browser_workflows.read_workflow("missing"))["success"]
    assert not (tmp_path / "browser_workflows").exists()
