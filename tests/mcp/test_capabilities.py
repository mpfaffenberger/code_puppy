"""Tests for per-server MCP capability wiring.

Covers the stateless-session subset only. Sampling and elicitation are
intentionally unsupported — SEP-2575 made MCP stateless, so a modern session
has no back-channel for server-initiated requests and pydantic-ai warns that
those handlers "will never be called". The tests below assert that we never
emit those kwargs (nor ``log_level``, which a modern session ignores).
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from code_puppy.mcp_.capabilities import (
    CapabilityConfig,
    build_capability_kwargs,
    make_log_handler,
    make_progress_handler,
    normalize_root,
)


def _log(params_level: str, data: str = "hello", logger: str | None = None):
    return SimpleNamespace(level=params_level, data=data, logger=logger)


class TestCapabilityConfig:
    def test_absent_block_uses_defaults(self):
        caps = CapabilityConfig.from_config({})
        assert caps.logging is True
        assert caps.progress is True
        # Instructions cost prompt tokens, so they stay opt-in.
        assert caps.instructions is False
        assert caps.roots == []

    def test_non_dict_block_is_ignored(self):
        assert CapabilityConfig.from_config({"capabilities": "yes"}).logging is True

    def test_flags_round_trip(self):
        caps = CapabilityConfig.from_config(
            {
                "capabilities": {
                    "logging": False,
                    "progress": False,
                    "instructions": True,
                    "cache_prompts": False,
                }
            }
        )
        assert caps.logging is False
        assert caps.progress is False
        assert caps.instructions is True
        assert caps.cache_prompts is False

    def test_unknown_keys_ignored(self):
        """A typo in hand-edited servers.json must not take a server down."""
        caps = CapabilityConfig.from_config({"capabilities": {"loggin": False}})
        assert caps.logging is True

    def test_sampling_and_elicitation_keys_are_inert(self):
        caps = CapabilityConfig.from_config(
            {"capabilities": {"sampling": True, "elicitation": "ask"}}
        )
        assert not hasattr(caps, "sampling")
        assert not hasattr(caps, "elicitation")

    @pytest.mark.parametrize("bad", ["verbose", 5, None, "TRACE"])
    def test_invalid_min_log_level_falls_back(self, bad):
        caps = CapabilityConfig.from_config({"capabilities": {"min_log_level": bad}})
        assert caps.min_log_level == "info"

    def test_min_log_level_is_case_insensitive(self):
        caps = CapabilityConfig.from_config(
            {"capabilities": {"min_log_level": "WARNING"}}
        )
        assert caps.min_log_level == "warning"

    def test_non_string_roots_dropped(self):
        caps = CapabilityConfig.from_config(
            {"capabilities": {"roots": ["/a", 7, None]}}
        )
        assert caps.roots == ["/a"]


class TestNormalizeRoot:
    def test_path_becomes_file_uri(self, tmp_path):
        assert normalize_root(str(tmp_path)).startswith("file://")

    def test_existing_uri_passes_through(self):
        assert normalize_root("https://example.com/x") == "https://example.com/x"

    def test_pwd_placeholder_expands(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        got = normalize_root("${PWD}")
        assert got == Path(tmp_path).resolve().as_uri()

    def test_env_var_expands(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CP_TEST_ROOT", str(tmp_path))
        assert normalize_root("$CP_TEST_ROOT").startswith("file://")

    def test_blank_returns_none(self):
        assert normalize_root("   ") is None


class TestBuildCapabilityKwargs:
    def test_never_emits_server_initiated_or_log_level(self):
        """The whole point of the stateless subset: these must never appear.

        Emitting them makes pydantic-ai warn at every connect, and they are
        unusable on a modern session regardless.
        """
        kwargs = build_capability_kwargs({}, "srv")
        for dead in (
            "sampling_handler",
            "sampling_model",
            "elicitation_handler",
            "log_level",
        ):
            assert dead not in kwargs

    def test_defaults_enable_logging_and_progress(self):
        kwargs = build_capability_kwargs({}, "srv")
        assert callable(kwargs["log_handler"])
        assert callable(kwargs["progress_handler"])
        assert "include_instructions" not in kwargs

    def test_disabling_omits_handlers(self):
        kwargs = build_capability_kwargs(
            {"capabilities": {"logging": False, "progress": False}}, "srv"
        )
        assert "log_handler" not in kwargs
        assert "progress_handler" not in kwargs

    def test_instructions_opt_in(self):
        kwargs = build_capability_kwargs({"capabilities": {"instructions": True}}, "s")
        assert kwargs["include_instructions"] is True

    def test_roots_resolved_to_uris(self, tmp_path):
        kwargs = build_capability_kwargs(
            {"capabilities": {"roots": [str(tmp_path)]}}, "srv"
        )
        assert all(u.startswith("file://") for u in kwargs["roots"])

    def test_all_unresolvable_roots_omits_key(self):
        kwargs = build_capability_kwargs({"capabilities": {"roots": ["  "]}}, "srv")
        assert "roots" not in kwargs

    def test_cache_flags_always_present(self):
        kwargs = build_capability_kwargs({}, "srv")
        assert kwargs["cache_prompts"] is True
        assert kwargs["cache_resources"] is True


class TestLogHandler:
    async def test_filters_below_threshold(self):
        """Client-side filtering matters: a stateless session ignores
        logging/setLevel, so the server sends every level regardless."""
        handler = make_log_handler("srv", min_level="warning")
        with patch("code_puppy.mcp_.capabilities.write_log") as wl:
            await handler(_log("debug"))
            await handler(_log("info"))
            assert wl.call_count == 0
            await handler(_log("error"))
            assert wl.call_count == 1

    async def test_writes_to_named_server_sink(self):
        handler = make_log_handler("my-server")
        with patch("code_puppy.mcp_.capabilities.write_log") as wl:
            await handler(_log("error", data="boom"))
        assert wl.call_args.args[0] == "my-server"
        assert "boom" in wl.call_args.args[1]
        assert wl.call_args.kwargs["level"] == "ERROR"

    async def test_logger_name_prefixed(self):
        handler = make_log_handler("srv")
        with patch("code_puppy.mcp_.capabilities.write_log") as wl:
            await handler(_log("info", data="msg", logger="auth"))
        assert "[auth] msg" in wl.call_args.args[1]

    async def test_non_string_data_is_repr_not_crash(self):
        handler = make_log_handler("srv")
        with patch("code_puppy.mcp_.capabilities.write_log") as wl:
            await handler(_log("info", data={"k": 1}))
        assert "k" in wl.call_args.args[1]

    async def test_fastmcp_structured_payload_is_unwrapped(self):
        """fastmcp's ctx.info() sends {"msg": ..., "extra": ...}; rendering
        that as a raw dict repr is unreadable in `/mcp logs`."""
        handler = make_log_handler("srv")
        with patch("code_puppy.mcp_.capabilities.write_log") as wl:
            await handler(_log("warning", data={"msg": "almost done", "extra": None}))
        assert wl.call_args.args[1] == "almost done"

    async def test_structured_payload_keeps_meaningful_extra(self):
        handler = make_log_handler("srv")
        with patch("code_puppy.mcp_.capabilities.write_log") as wl:
            await handler(_log("info", data={"msg": "hi", "extra": {"run": 7}}))
        text = wl.call_args.args[1]
        assert "hi" in text and "run" in text

    async def test_unknown_level_treated_as_info(self):
        handler = make_log_handler("srv", min_level="debug")
        with patch("code_puppy.mcp_.capabilities.write_log") as wl:
            await handler(_log("bogus"))
        assert wl.call_count == 1


class TestProgressHandler:
    async def test_percentage_when_total_known(self):
        handler = make_progress_handler("srv")
        with patch("code_puppy.mcp_.capabilities.write_log") as wl:
            await handler(5.0, 10.0, "halfway")
        text = wl.call_args.args[1]
        assert "5/10" in text and "50%" in text and "halfway" in text

    async def test_no_total_does_not_divide_by_zero(self):
        handler = make_progress_handler("srv")
        with patch("code_puppy.mcp_.capabilities.write_log") as wl:
            await handler(3.0, None, None)
        assert "3" in wl.call_args.args[1]

    async def test_zero_total_is_safe(self):
        handler = make_progress_handler("srv")
        with patch("code_puppy.mcp_.capabilities.write_log") as wl:
            await handler(0.0, 0.0, None)
        assert wl.call_count == 1
