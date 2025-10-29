"""Unit tests to ensure hover defaults are sane."""

from __future__ import annotations

from code_puppy.tools.rpa.click_debugging import register_click_debugging_tools


def test_hover_duration_default_value():
    class DummyAgent:
        def tool(self, func):
            # Return func so we can inspect signature
            return func

    agent = DummyAgent()
    hover_tool = register_click_debugging_tools(agent)
    # The function returns None; we introspect via reading the module signature instead
    # Import function directly and check default
    import inspect
    # Retrieve function from closure: we re-register and fetch from module
    # To keep it simple, import the module and inspect the function default
    from code_puppy.tools.rpa.click_debugging import register_click_debugging_tools as reg
    # Register on a dummy and inspect
    class Collector:
        def __init__(self):
            self.tools = {}
        def tool(self, func):
            self.tools[func.__name__] = func
            return func
    collector = Collector()
    reg(collector)
    fn = collector.tools.get('desktop_hover_and_verify')
    sig = inspect.signature(fn)
    assert sig.parameters['duration'].default == 0.5
