import pytest


def test_safety_validator_reauth_on_401_retries_once(monkeypatch):
    # Import inside the test so monkeypatching is clean
    import code_puppy.safety_validator as sv

    calls = {"count": 0, "headers": []}

    class FakeResponse:
        def __init__(self, status_code: int, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload
            self.text = text

        def json(self):
            if self._payload is None:
                raise ValueError("no json")
            return self._payload

    class FakeClient:
        def post(self, url, json=None, headers=None, timeout=None):
            calls["count"] += 1
            calls["headers"].append(dict(headers or {}))

            # First call returns 401, second returns 200
            if calls["count"] == 1:
                return FakeResponse(401, payload=None, text="unauthorized")
            return FakeResponse(
                200,
                payload={
                    "is_dangerous": False,
                    "risk_level": "low",
                    "reasoning": "ok",
                },
            )

    monkeypatch.setattr(sv, "create_client", lambda verify=False: FakeClient())

    # Token changes after reauth
    tokens = iter(["expired-token", "fresh-token"])

    def fake_get_puppy_token():
        return next(tokens)

    import code_puppy.config as cfg

    monkeypatch.setattr(cfg, "get_puppy_token", fake_get_puppy_token)

    # Reauth returns True
    import code_puppy.plugins.walmart_specific.auth as wmauth

    monkeypatch.setattr(wmauth, "reauthenticate_puppy_sync", lambda **_: True)

    result = sv.validate_command_safety("echo hi")

    assert result.is_safe is True
    assert result.risk_level == "low"
    assert calls["count"] == 2

    # First call used expired token, second used refreshed token
    assert calls["headers"][0].get("X-Api-Key") == "expired-token"
    assert calls["headers"][1].get("X-Api-Key") == "fresh-token"
