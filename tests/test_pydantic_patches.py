"""Tests for code_puppy.pydantic_patches loud-failure behavior.

The contract under test:
- Patches never raise (no-crash guarantee).
- Failure to patch a pydantic-ai internal logs a LOUD ``logging.ERROR``
  record naming the patch.
- A missing OPTIONAL third-party lib stays quiet (DEBUG at most).
- ``apply_all_patches`` returns a dict of patch name -> applied and logs
  one summary line listing real failures.
"""

import builtins
import json
import logging
from types import SimpleNamespace

import pytest

from code_puppy import pydantic_patches

LOGGER_NAME = "code_puppy.pydantic_patches"


@pytest.fixture(autouse=True)
def _reset_placeholder_warned_keys():
    """Isolate the module-level dedup set: any test may seed it, and a
    later WARNING assertion must not silently see DEBUG instead."""
    pydantic_patches._PLACEHOLDER_WARNED_KEYS.clear()
    yield

SHATTERING_MALFORMED_JSON = (
    '{"file_path": "demo.py", "content": "print(f\\"wrote {n_rows:,} rows\\")\n'
    'print(f"  {name:<30}{count:>10,}")\n'
    "total_mb = 34.56 * len(ss) / total_sigs\n"
    '"}'
)


def test_valid_tool_call_json_passes_through_without_repair(monkeypatch):
    import json_repair

    payload = json.dumps(
        {
            "file_path": "demo.py",
            "content": 'print(f"{n_rows:,} rows")\nsummary = {"a": 1}\n',
        }
    )

    def unexpected_repair(_raw):
        pytest.fail("valid JSON must not be handed to json_repair")

    monkeypatch.setattr(json_repair, "repair_json", unexpected_repair)

    assert pydantic_patches._repair_tool_call_json(payload) == payload


def test_non_object_tool_call_json_repair_is_rejected():
    import json_repair

    repaired = json.loads(json_repair.repair_json(SHATTERING_MALFORMED_JSON))
    assert not isinstance(repaired, dict)
    assert (
        pydantic_patches._repair_tool_call_json(SHATTERING_MALFORMED_JSON)
        == SHATTERING_MALFORMED_JSON
    )


@pytest.mark.parametrize(
    "error",
    [
        RecursionError("maximum recursion depth exceeded"),
        ValueError("strict parser rejected input"),
    ],
)
def test_strict_parse_failure_returns_original(monkeypatch, error):
    raw = '{"value": {"nested": true}}'

    def parse_failure(_raw):
        raise error

    monkeypatch.setattr(pydantic_patches.json, "loads", parse_failure)

    assert pydantic_patches._repair_tool_call_json(raw) == raw


def test_recoverable_tool_call_json_is_repaired():
    malformed = '{"file_path": "demo.py", "content": "hi",}'

    repaired = pydantic_patches._repair_tool_call_json(malformed)

    assert repaired != malformed
    assert json.loads(repaired) == {"file_path": "demo.py", "content": "hi"}


def test_tool_call_json_repair_exception_returns_original(monkeypatch):
    import json_repair

    malformed = "{not json at all"

    def explode(_raw):
        raise RuntimeError("boom")

    monkeypatch.setattr(json_repair, "repair_json", explode)

    assert pydantic_patches._repair_tool_call_json(malformed) == malformed


@pytest.mark.asyncio
async def test_json_repair_patch_rejects_non_object_repair(monkeypatch):
    from pydantic_ai.tool_manager import ToolManager

    async def validate_tool_call(_manager, call, **_kwargs):
        return call.args

    monkeypatch.setattr(ToolManager, "validate_tool_call", validate_tool_call)
    assert pydantic_patches.patch_tool_call_json_repair() is True
    call = SimpleNamespace(args=SHATTERING_MALFORMED_JSON)

    result = await ToolManager.validate_tool_call(SimpleNamespace(), call)

    assert result == SHATTERING_MALFORMED_JSON
    assert call.args == SHATTERING_MALFORMED_JSON


# ---------------------------------------------------------------------------
# Spurious {"arguments": ...} envelope from zero-parameter tool calls.
#
# Some models encode the *function-call envelope* as the args object itself
# ({"arguments": {}}) instead of an empty dict. pydantic-ai declares tool
# schemas with additionalProperties: false, so the stray key hard-fails
# validation and the tool can never be called (seen with `list_agents`).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ({"arguments": {}}, {}),
        ({"arguments": "{}"}, {}),
        ({"arguments": {"a": 1}}, {"a": 1}),
        ({"arguments": '{"a": 1}'}, {"a": 1}),
    ],
)
def test_arguments_envelope_is_unwrapped(raw, expected):
    assert pydantic_patches._unwrap_arguments_envelope(raw, {}) == expected


@pytest.mark.parametrize(
    "raw",
    [
        {"arguments": {"a": 1}},  # tool really declares an `arguments` property
        {"arguments": "not json"},
        {"arguments": 5},
        {"arguments": None},
        {"arguments": {}, "extra": 1},  # not the sole key
        {},
        {"file_path": "puppy.py"},
        "not-a-dict",
    ],
)
def test_ambiguous_or_legit_args_are_left_untouched(raw):
    properties = {"arguments": {"type": "object"}}
    assert pydantic_patches._unwrap_arguments_envelope(raw, properties) == raw


@pytest.mark.parametrize(
    "raw",
    [
        {"arguments": "not json"},
        {"arguments": 5},
        {"arguments": None},
        {"arguments": [1, 2]},
    ],
)
def test_non_dict_envelope_payloads_are_left_untouched(raw):
    """No declared `arguments` property, but the payload isn't an object."""
    assert pydantic_patches._unwrap_arguments_envelope(raw, {}) == raw


def test_sanitize_unwraps_dict_args_in_place():
    call = SimpleNamespace(args={"arguments": {"file_path": "puppy.py"}})

    # The tool really takes ``file_path``; only the envelope is spurious.
    pydantic_patches._sanitize_tool_call_args(
        _stub_manager({"file_path": {"type": "string"}}), call
    )

    assert call.args == {"file_path": "puppy.py"}


def test_sanitize_unwraps_string_args_and_keeps_string_shape():
    call = SimpleNamespace(args='{"arguments": "{}"}')

    pydantic_patches._sanitize_tool_call_args(_stub_manager({}), call)

    assert call.args == "{}"
    assert isinstance(call.args, str)


def test_sanitize_leaves_invalid_json_string_for_the_repairer():
    call = SimpleNamespace(args="{not json at all")

    pydantic_patches._sanitize_tool_call_args(_stub_manager({}), call)

    assert call.args == "{not json at all"


@pytest.mark.parametrize(
    "junk_args",
    [
        {"command": "list_agents"},
        {"extra": "ignore"},
        {"dummy": "x"},
        {"city": "ignore"},
    ],
)
def test_zero_param_tool_placeholder_args_are_stripped(junk_args):
    """Observed in the wild: a provider that cannot emit an empty arguments
    object injects one placeholder key, and the call dies with
    ``extra_forbidden`` while the model insists it sent ``{}``."""
    call = SimpleNamespace(tool_name="list_agents", args=junk_args)

    pydantic_patches._sanitize_tool_call_args(_stub_manager({}), call)

    assert call.args == {}


def test_zero_param_tool_placeholder_args_string_shape_preserved():
    call = SimpleNamespace(tool_name="list_agents", args='{"city": "ignore"}')

    pydantic_patches._sanitize_tool_call_args(_stub_manager({}), call)

    assert call.args == "{}"
    assert isinstance(call.args, str)


def test_parameterized_tool_junk_args_are_not_stripped():
    """Only zero-parameter tools get the nuclear option; stripping unknown
    keys from a tool with real parameters could mask a confused call."""
    args = {"command": "echo hi"}
    call = SimpleNamespace(tool_name="shell", args=args)

    pydantic_patches._sanitize_tool_call_args(
        _stub_manager({"command": {"type": "string"}}), call
    )

    assert call.args is args


def test_unknown_schema_junk_args_are_not_stripped():
    """No resolvable schema means we cannot know the tool is zero-param."""
    args = {"command": "list_agents"}
    call = SimpleNamespace(tool_name="mystery", args=args)

    pydantic_patches._sanitize_tool_call_args(
        SimpleNamespace(get_tool_def=lambda _name: None), call
    )

    assert call.args is args


@pytest.mark.parametrize(
    "additional_properties",
    [
        True,  # explicitly permissive
        None,  # key omitted — JSON-Schema default is to ALLOW extras
        {},  # permissive-with-constraints; falsy in Python, still allows!
    ],
)
def test_permissive_zero_prop_schema_args_are_never_stripped(additional_properties):
    """MAJOR regression guard: a schema that permits extra properties may
    carry legitimate free-form args; wiping them breaks the tool silently."""
    args = {"payload": "legit data"}
    call = SimpleNamespace(tool_name="mcp_tool", args=args)

    pydantic_patches._sanitize_tool_call_args(
        _stub_manager({}, additional_properties=additional_properties), call
    )

    assert call.args is args


def test_schema_omitting_properties_still_strips():
    """A resolved schema without ``properties`` is zero-param, not unknown:
    the production bug must stay fixed for such tools too."""
    manager = SimpleNamespace(
        get_tool_def=lambda _name: SimpleNamespace(
            parameters_json_schema={
                "type": "object",
                "additionalProperties": False,
            }
        )
    )
    call = SimpleNamespace(tool_name="list_agents", args={"command": "list_agents"})

    pydantic_patches._sanitize_tool_call_args(manager, call)

    assert call.args == {}


def test_non_object_schema_args_are_not_stripped():
    """Foreign schema shapes are exotic; we do not guess for them."""
    manager = SimpleNamespace(
        get_tool_def=lambda _name: SimpleNamespace(
            parameters_json_schema={"type": "string"}
        )
    )
    args = {"command": "list_agents"}
    call = SimpleNamespace(tool_name="weird", args=args)

    pydantic_patches._sanitize_tool_call_args(manager, call)

    assert call.args is args


@pytest.mark.parametrize(
    "schema",
    [
        # legal JSON-Schema variants that still admit object args:
        {"type": ["object", "null"], "properties": {}, "additionalProperties": False},
        # type-less schema constraining objects only via keywords:
        {"additionalProperties": False},
    ],
)
def test_object_admitting_type_variants_still_strip(schema):
    """Nullable/typeless strict-zero-param tools keep the production fix."""
    manager = SimpleNamespace(
        get_tool_def=lambda _name: SimpleNamespace(parameters_json_schema=schema)
    )
    call = SimpleNamespace(tool_name="list_agents", args={"command": "list_agents"})

    pydantic_patches._sanitize_tool_call_args(manager, call)

    assert call.args == {}


@pytest.mark.parametrize(
    "raw",
    [
        {"arguments": {"command": "x"}},  # the two-malformation composition
        {"arguments": 5},  # non-dict envelope payload, zero-param tool
        {"arguments": "not json"},
    ],
)
def test_strict_zero_param_tool_envelope_payloads_end_up_empty(raw):
    """Pipeline-level pin: for a strict zero-param tool, envelope leftovers
    are junk by contract (validation would reject them anyway) and collapse
    to ``{}`` — in both arg shapes."""
    call = SimpleNamespace(tool_name="list_agents", args=raw)
    pydantic_patches._sanitize_tool_call_args(_stub_manager({}), call)
    assert call.args == {}

    call = SimpleNamespace(tool_name="list_agents", args=json.dumps(raw))
    pydantic_patches._sanitize_tool_call_args(_stub_manager({}), call)
    assert call.args == "{}"


def test_parameterized_tool_envelope_payload_stays_untouched():
    """A tool with a real ``arguments`` property keeps its envelope."""
    args = {"arguments": 5}
    call = SimpleNamespace(tool_name="enveloper", args=args)

    pydantic_patches._sanitize_tool_call_args(
        _stub_manager({"arguments": {"type": "integer"}}), call
    )

    assert call.args is args


def test_placeholder_strip_logs_once_per_quirk(caplog):
    """WARNING once per (tool, quirk) then DEBUG for identical repeats —
    but a NEW quirk on the same tool still surfaces at WARNING."""
    quirks = [{"city": "ignore"}, {"city": "ignore"}, {"dummy": "x"}]
    with caplog.at_level("DEBUG", logger=LOGGER_NAME):
        for junk in quirks:
            call = SimpleNamespace(tool_name="list_agents", args=junk)
            pydantic_patches._sanitize_tool_call_args(_stub_manager({}), call)

    warnings = [
        r for r in caplog.records if r.levelname == "WARNING" and "placeholder" in r.message
    ]
    debugs = [
        r for r in caplog.records if r.levelname == "DEBUG" and "placeholder" in r.message
    ]
    assert len(warnings) == 2  # city-quirk, then dummy-quirk
    assert len(debugs) == 1  # the repeated city-quirk
    assert "list_agents" in warnings[0].getMessage()
    assert "city" in warnings[0].getMessage()  # values identify the provider quirk


def test_permissive_schema_keeps_legit_arguments_arg():
    """A schema that omits properties may accept free-form args; a real
    ``arguments`` arg must survive the envelope unwrap untouched."""
    manager = SimpleNamespace(
        get_tool_def=lambda _name: SimpleNamespace(
            parameters_json_schema={"type": "object"}
        )
    )
    args = {"arguments": {"legit": 1}}
    call = SimpleNamespace(tool_name="freeform", args=args)

    pydantic_patches._sanitize_tool_call_args(manager, call)

    assert call.args is args


def test_unresolvable_schema_keeps_envelope():
    """No schema, no proof the envelope is spurious — hands off."""
    args = {"arguments": {"x": 1}}
    call = SimpleNamespace(tool_name="mystery", args=args)

    pydantic_patches._sanitize_tool_call_args(
        SimpleNamespace(get_tool_def=lambda _name: None), call
    )

    assert call.args is args


def test_placeholder_strip_survives_mixed_type_keys():
    """Exotic args must not crash the validation hot path."""
    call = SimpleNamespace(tool_name="list_agents", args={1: "int key", "city": "ignore"})

    pydantic_patches._sanitize_tool_call_args(_stub_manager({}), call)

    assert call.args == {}


class _ReprHostileKey:
    """Hashable key whose repr raises — defeats json.dumps *and* repr."""

    def __repr__(self):  # pragma: no cover - exercised via logging fallback
        raise RuntimeError("no repr for you")


class _ReprHostileValue:
    """Value that defeats json.dumps via ``default=str`` -> ``__str__``
    (object.__str__ delegates to the raising __repr__) and then repr too."""

    def __repr__(self):  # pragma: no cover - exercised via logging fallback
        raise RuntimeError("no repr for you either")


def test_placeholder_strip_survives_repr_hostile_key(caplog):
    """The deepest logging guard: neither serializer works, the strip still
    completes and the log names the situation instead of raising."""
    with caplog.at_level("DEBUG", logger=LOGGER_NAME):
        call = SimpleNamespace(
            tool_name="list_agents", args={_ReprHostileKey(): "x"}
        )
        pydantic_patches._sanitize_tool_call_args(_stub_manager({}), call)

    assert call.args == {}
    assert any("unrepr-able" in r.message for r in caplog.records)


def test_placeholder_strip_survives_repr_hostile_value(caplog):
    """Same guarantee reached via a hostile *value*: json.dumps fails in
    ``default=str`` (``__str__`` delegates to the raising ``__repr__``),
    then the repr fallback fails too."""
    with caplog.at_level("DEBUG", logger=LOGGER_NAME):
        call = SimpleNamespace(
            tool_name="list_agents", args={"city": _ReprHostileValue()}
        )
        pydantic_patches._sanitize_tool_call_args(_stub_manager({}), call)

    assert call.args == {}
    assert any("unrepr-able" in r.message for r in caplog.records)


def test_dedup_signature_uses_log_line_bound(caplog):
    """Two quirks differing only past char 200 dedup as one: the signature
    reuses the log line's 200-char bound."""
    quirks = [{"junk": "a" * 300}, {"junk": "a" * 300 + "b"}]
    with caplog.at_level("DEBUG", logger=LOGGER_NAME):
        for junk in quirks:
            call = SimpleNamespace(tool_name="list_agents", args=junk)
            pydantic_patches._sanitize_tool_call_args(_stub_manager({}), call)

    warnings = [
        r for r in caplog.records if r.levelname == "WARNING" and "placeholder" in r.message
    ]
    debugs = [
        r for r in caplog.records if r.levelname == "DEBUG" and "placeholder" in r.message
    ]
    assert len(warnings) == 1
    assert len(debugs) == 1


def test_dedup_set_at_cap_always_warns_and_stops_growing(monkeypatch, caplog):
    """With the set full, a new quirk still logs WARNING and the set does
    not grow — no silent dedup, no unbounded memory."""
    monkeypatch.setattr(pydantic_patches, "_PLACEHOLDER_WARNED_KEYS_MAX", 1)
    pydantic_patches._PLACEHOLDER_WARNED_KEYS.add(("other-tool", "seed"))

    with caplog.at_level("DEBUG", logger=LOGGER_NAME):
        for junk in ({"city": "ignore"}, {"dummy": "x"}):
            call = SimpleNamespace(tool_name="list_agents", args=junk)
            pydantic_patches._sanitize_tool_call_args(_stub_manager({}), call)

    warnings = [
        r for r in caplog.records if r.levelname == "WARNING" and "placeholder" in r.message
    ]
    debugs = [
        r for r in caplog.records if r.levelname == "DEBUG" and "placeholder" in r.message
    ]
    assert len(warnings) == 2  # both quirks surface: set is full, no dedup
    assert len(debugs) == 0
    assert pydantic_patches._PLACEHOLDER_WARNED_KEYS == {("other-tool", "seed")}


def test_omitted_properties_strict_schema_collapses_envelope_via_strip():
    """Composition: a strict zero-param schema that omits ``properties``
    keeps the envelope from the unwrap (unproven), but the strip still
    collapses the whole junk envelope to ``{}``."""
    manager = SimpleNamespace(
        get_tool_def=lambda _name: SimpleNamespace(
            parameters_json_schema={"type": "object", "additionalProperties": False}
        )
    )
    call = SimpleNamespace(tool_name="list_agents", args={"arguments": {"junk": 1}})

    pydantic_patches._sanitize_tool_call_args(manager, call)

    assert call.args == {}


def _stub_manager(properties, additional_properties=False):
    """A ToolManager stand-in whose tool's schema is built to order.

    ``properties`` declares the tool's parameters (empty = zero-param);
    ``additional_properties=False`` forbids extras (pass ``None`` to omit
    the key, ``True``/a dict for permissive variants).
    """
    schema = {"type": "object", "properties": properties}
    if additional_properties is not None:
        schema["additionalProperties"] = additional_properties
    return SimpleNamespace(
        get_tool_def=lambda _name: SimpleNamespace(parameters_json_schema=schema)
    )


@pytest.mark.asyncio
async def test_zero_arg_tool_call_with_arguments_envelope_validates(monkeypatch):
    """The whole point: list_agents-style calls must survive validation."""
    from pydantic_ai.tool_manager import ToolManager

    async def validate_tool_call(_manager, call, **_kwargs):
        return call.args

    monkeypatch.setattr(ToolManager, "validate_tool_call", validate_tool_call)
    assert pydantic_patches.patch_tool_call_json_repair() is True

    manager = _stub_manager({})
    call = SimpleNamespace(tool_name="list_agents", args={"arguments": {}})

    result = await ToolManager.validate_tool_call(manager, call)

    assert result == {}
    assert call.args == {}


@pytest.mark.asyncio
async def test_zero_arg_tool_call_with_placeholder_key_validates(monkeypatch):
    """Same contract, wilder malformation: ``{"command": "list_agents"}``."""
    from pydantic_ai.tool_manager import ToolManager

    async def validate_tool_call(_manager, call, **_kwargs):
        return call.args

    monkeypatch.setattr(ToolManager, "validate_tool_call", validate_tool_call)
    assert pydantic_patches.patch_tool_call_json_repair() is True

    manager = _stub_manager({})
    call = SimpleNamespace(
        tool_name="list_agents", args='{"command": "list_agents"}'
    )

    result = await ToolManager.validate_tool_call(manager, call)

    assert result == "{}"
    assert call.args == "{}"


@pytest.mark.parametrize("tool_name", ["replace_in_file", "create_file"])
def test_editor_args_are_repaired_before_pre_tool_call(tool_name):
    """Every editor tool reaches hooks with repaired JSON args."""
    raw_args = f'{{"tool": "{tool_name}", "file_path": "puppy.py"'

    args, mode = pydantic_patches._tool_args_for_pre_tool_call(raw_args)

    assert args == {"tool": tool_name, "file_path": "puppy.py"}
    assert mode == "str"


def test_unrepairable_pre_tool_args_are_not_marked_for_writeback(monkeypatch):
    import json_repair

    monkeypatch.setattr(json_repair, "repair_json", lambda _value: "[]")

    args, mode = pydantic_patches._tool_args_for_pre_tool_call("nope")

    assert args == {"raw": "nope"}
    assert mode is None


def test_prefixed_private_agent_tool_resolves_against_its_registry(monkeypatch):
    """A Claude private agent need not match the globally selected model."""
    monkeypatch.setattr(
        "code_puppy.config.get_global_model_name", lambda: "codex-gpt-5.6"
    )
    manager = SimpleNamespace(tools={"final_result": object()})

    normalized = pydantic_patches._normalize_claude_code_tool_name(
        manager, "cp_final_result"
    )

    assert normalized == "final_result"


def test_registered_prefixed_tool_name_is_preserved():
    manager = SimpleNamespace(tools={"cp_status": object(), "status": object()})

    normalized = pydantic_patches._normalize_claude_code_tool_name(manager, "cp_status")

    assert normalized == "cp_status"


@pytest.mark.asyncio
async def test_structured_output_validation_normalizes_prefixed_tool(monkeypatch):
    from pydantic_ai.tool_manager import ToolManager

    calls = []

    async def validate_output(_manager, call, **kwargs):
        calls.append((call.tool_name, kwargs))
        return "validated"

    # Record every method the patch replaces so monkeypatch restores the class
    # after this focused behavior test.
    for method_name in ("execute_tool_call", "get_tool_def", "validate_tool_call"):
        monkeypatch.setattr(ToolManager, method_name, getattr(ToolManager, method_name))
    monkeypatch.setattr(ToolManager, "validate_output_tool_call", validate_output)

    assert pydantic_patches.patch_tool_call_callbacks() is True
    manager = SimpleNamespace(tools={"final_result": object()})
    call = SimpleNamespace(tool_name="cp_final_result")

    result = await ToolManager.validate_output_tool_call(
        manager, call, schema="decision"
    )

    assert result == "validated"
    assert call.tool_name == "final_result"
    assert calls == [("final_result", {"schema": "decision"})]


def _error_records(caplog):
    return [
        r
        for r in caplog.records
        if r.name == LOGGER_NAME and r.levelno >= logging.ERROR
    ]


# ---------------------------------------------------------------------------
# Success path: everything installed in the test env, so all patches apply
# cleanly and NO error records are emitted.
# ---------------------------------------------------------------------------


def test_apply_all_patches_success_no_errors(caplog):
    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        results = pydantic_patches.apply_all_patches()

    assert results == {p.__name__: True for p in pydantic_patches._ALL_PATCHES}
    assert _error_records(caplog) == []


def test_apply_all_patches_returns_all_patch_names():
    results = pydantic_patches.apply_all_patches()
    assert set(results) == {p.__name__ for p in pydantic_patches._ALL_PATCHES}


# ---------------------------------------------------------------------------
# Loud failures: a missing pydantic-ai internal must log ERROR, return False,
# and never raise.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "patch_fn_name,break_it",
    [
        (
            "patch_user_agent",
            lambda mp: mp.delattr("pydantic_ai.models.get_user_agent"),
        ),
        (
            "patch_message_history_cleaning",
            lambda mp: mp.delattr("pydantic_ai._agent_graph._clean_message_history"),
        ),
        (
            "patch_tool_call_callbacks",
            lambda mp: mp.delattr(
                "pydantic_ai.tool_manager.ToolManager.execute_tool_call"
            ),
        ),
        (
            "patch_tool_call_callbacks",
            lambda mp: mp.delattr(
                "pydantic_ai.tool_manager.ToolManager.validate_output_tool_call"
            ),
        ),
        (
            "patch_tool_call_json_repair",
            lambda mp: mp.delattr(
                "pydantic_ai.tool_manager.ToolManager.validate_tool_call"
            ),
        ),
    ],
)
def test_missing_pydantic_internal_logs_error(
    monkeypatch, caplog, patch_fn_name, break_it
):
    break_it(monkeypatch)
    patch_fn = getattr(pydantic_patches, patch_fn_name)

    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        result = patch_fn()  # must NOT raise

    assert result is False
    errors = _error_records(caplog)
    assert len(errors) == 1
    message = errors[0].getMessage()
    assert patch_fn_name in message
    assert "FAILED to apply" in message


def test_tool_call_callbacks_failure_names_disabled_hooks(monkeypatch, caplog):
    """The security-critical patch must spell out the consequence."""
    monkeypatch.delattr("pydantic_ai.tool_manager.ToolManager.execute_tool_call")
    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        assert pydantic_patches.patch_tool_call_callbacks() is False
    message = _error_records(caplog)[0].getMessage()
    assert "pre/post tool hooks and hook-blocking are DISABLED" in message


# ---------------------------------------------------------------------------
# Optional dependencies: ImportError of json_repair/wcwidth/prompt_toolkit/
# termflow stays quiet (DEBUG at most, never ERROR).
# ---------------------------------------------------------------------------


def _block_import(monkeypatch, *names):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in names or any(name.startswith(f"{n}.") for n in names):
            raise ImportError(f"No module named {name!r} (simulated)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


@pytest.mark.parametrize(
    "patch_fn_name,blocked_libs",
    [
        ("patch_tool_call_json_repair", ("json_repair",)),
        ("patch_termflow_clipboard", ("termflow",)),
        ("patch_termflow_code_padding", ("termflow",)),
        ("patch_termflow_blockquote_gutter", ("termflow",)),
    ],
)
def test_missing_optional_lib_is_quiet(
    monkeypatch, caplog, patch_fn_name, blocked_libs
):
    _block_import(monkeypatch, *blocked_libs)
    patch_fn = getattr(pydantic_patches, patch_fn_name)

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        result = patch_fn()  # must NOT raise

    assert result is False
    assert _error_records(caplog) == []
    debug_msgs = [
        r.getMessage()
        for r in caplog.records
        if r.name == LOGGER_NAME and r.levelno == logging.DEBUG
    ]
    assert any(patch_fn_name in m for m in debug_msgs)


# ---------------------------------------------------------------------------
# apply_all_patches summary behavior.
# ---------------------------------------------------------------------------


def test_apply_all_patches_summary_lists_loud_failures(monkeypatch, caplog):
    monkeypatch.delattr("pydantic_ai._agent_graph._clean_message_history")

    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        results = pydantic_patches.apply_all_patches()  # must NOT raise

    assert results["patch_message_history_cleaning"] is False
    # Everything else still applies.
    assert all(
        ok for name, ok in results.items() if name != "patch_message_history_cleaning"
    )
    summary = [
        r.getMessage()
        for r in _error_records(caplog)
        if "FAILED to apply:" in r.getMessage()
    ]
    assert len(summary) == 1
    assert "patch_message_history_cleaning" in summary[0]


def test_apply_all_patches_no_summary_for_optional_skips(monkeypatch, caplog):
    """A skipped optional dep is False in the dict but NOT a loud failure."""
    _block_import(monkeypatch, "termflow")

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        results = pydantic_patches.apply_all_patches()

    assert results["patch_termflow_clipboard"] is False
    assert results["patch_termflow_code_padding"] is False
    assert _error_records(caplog) == []


# ---------------------------------------------------------------------------
# termflow clipboard: behavior against the installed termflow, not internals.
# ---------------------------------------------------------------------------

_OSC52 = "\x1b]52;"


def _render_code_block(**renderer_kwargs) -> str:
    import io

    from termflow import Parser, Renderer

    out = io.StringIO()
    parser = Parser()
    renderer = Renderer(output=out, width=80, **renderer_kwargs)
    for line in ["```python", "print('hi')", "```"]:
        renderer.render_all(parser.parse_line(line))
    renderer.render_all(parser.finalize())
    return out.getvalue()


@pytest.fixture
def restore_termflow_renderer_init():
    from termflow.render.renderer import Renderer

    original = Renderer.__init__
    yield
    Renderer.__init__ = original


def test_default_renderer_emits_no_osc52_after_patch(
    restore_termflow_renderer_init,
):
    """termflow defaults to clipboard=True; no renderer may write OSC 52."""
    assert pydantic_patches.patch_termflow_clipboard() is True

    rendered = _render_code_block()

    assert "print" in rendered
    assert _OSC52 not in rendered


def test_clipboard_patch_copies_caller_features(restore_termflow_renderer_init):
    from termflow.render.style import RenderFeatures

    assert pydantic_patches.patch_termflow_clipboard() is True
    shared = RenderFeatures(clipboard=True)

    assert _OSC52 not in _render_code_block(features=shared)
    # The caller's (possibly shared) config object is never mutated.
    assert shared.clipboard is True


def test_clipboard_patch_is_idempotent(restore_termflow_renderer_init):
    from termflow.render.renderer import Renderer

    assert pydantic_patches.patch_termflow_clipboard() is True
    patched = Renderer.__init__

    assert pydantic_patches.patch_termflow_clipboard() is True
    assert Renderer.__init__ is patched
