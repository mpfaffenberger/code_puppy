from unittest.mock import patch, MagicMock
from code_puppy.tools.web_search import register_web_search_tools
from types import SimpleNamespace


class DummyAgent:
    def __init__(self):
        self.tools = {}

    def tool(self, f):
        self.tools[f.__name__] = f
        return f


def make_context():
    # Minimal stand-in for RunContext
    return SimpleNamespace()


def test_grab_json_from_url_success():
    agent = DummyAgent()
    register_web_search_tools(agent)
    tool = agent.tools["grab_json_from_url"]
    resp = MagicMock()
    resp.headers = {"Content-Type": "application/json"}
    resp.json.return_value = {"foo": "bar"}
    resp.raise_for_status.return_value = None
    with patch("requests.get", return_value=resp) as mget:
        result = tool(make_context(), "http://test")
        assert result == {"foo": "bar"}
        mget.assert_called_once_with("http://test")


def test_grab_json_from_url_truncates_large_list():
    agent = DummyAgent()
    register_web_search_tools(agent)
    tool = agent.tools["grab_json_from_url"]
    resp = MagicMock()
    resp.headers = {"Content-Type": "application/json"}
    resp.json.return_value = list(range(2000))
    resp.raise_for_status.return_value = None
    with patch("requests.get", return_value=resp):
        result = tool(make_context(), "http://test")
        assert result == list(range(1000))


def test_grab_json_from_url_non_json_response():
    agent = DummyAgent()
    register_web_search_tools(agent)
    tool = agent.tools["grab_json_from_url"]
    resp = MagicMock()
    resp.headers = {"Content-Type": "text/html"}
    resp.json.return_value = None
    resp.raise_for_status.return_value = None
    with patch("requests.get", return_value=resp):
        result = tool(make_context(), "http://test")
        assert "error" in result
        assert "not of type application/json" in result["error"]


def test_grab_json_from_url_http_error():
    agent = DummyAgent()
    register_web_search_tools(agent)
    tool = agent.tools["grab_json_from_url"]
    resp = MagicMock()
    resp.raise_for_status.side_effect = Exception("boom")
    with patch("requests.get", return_value=resp):
        result = tool(make_context(), "http://test")
        assert "error" in result
        assert "boom" in result["error"]
