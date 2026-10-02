"""Web-serve wiring: command building + arg parsing (no real server boot)."""

import sys

from code_puppy.tui import serve as serve_mod


def test_build_command_relaunches_tui():
    cmd = serve_mod._build_command()
    assert "-m code_puppy --tui" in cmd
    assert sys.executable.split("/")[-1] in cmd


def test_run_web_server_constructs_server(monkeypatch):
    calls = {}

    class _FakeServer:
        def __init__(self, command, host, port, title, public_url):
            calls.update(
                command=command,
                host=host,
                port=port,
                title=title,
                public_url=public_url,
            )

        def serve(self, debug=False):
            calls["served"] = True
            calls["debug"] = debug

    import textual_serve.server as ts

    monkeypatch.setattr(ts, "Server", _FakeServer)

    rc = serve_mod.run_web_server(host="0.0.0.0", port=9999, debug=True)
    assert rc == 0
    assert calls["host"] == "0.0.0.0"
    assert calls["port"] == 9999
    assert calls["title"] == "Code Puppy"
    assert calls["served"] is True
    assert calls["debug"] is True
    assert "-m code_puppy --tui" in calls["command"]


def test_run_web_server_from_args_parses_flags(monkeypatch):
    captured = {}

    def _fake_run(host, port, public_url, *, debug):
        captured.update(host=host, port=port, public_url=public_url, debug=debug)
        return 0

    monkeypatch.setattr(serve_mod, "run_web_server", _fake_run)

    rc = serve_mod.run_web_server_from_args(
        ["--serve", "--host", "1.2.3.4", "--port", "1234", "--serve-debug"]
    )
    assert rc == 0
    assert captured == {
        "host": "1.2.3.4",
        "port": 1234,
        "public_url": None,
        "debug": True,
    }
