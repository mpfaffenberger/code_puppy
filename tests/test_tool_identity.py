"""Hook identity survives metadata mutation, nesting, concurrency and cancellation."""

import asyncio
from dataclasses import FrozenInstanceError

import pytest

from code_puppy import callbacks
from code_puppy.tool_identity import current_tool_identity, tool_call_identity


@pytest.fixture(autouse=True)
def isolated_callbacks(monkeypatch):
    monkeypatch.setattr(
        callbacks, "_callbacks", {key: [] for key in callbacks._callbacks}
    )


@pytest.mark.parametrize("phase", ["pre_tool_call", "post_tool_call"])
async def test_mutable_context_does_not_change_identity_or_argument_contract(phase):
    seen = []

    def mutate(name, args, *rest):
        rest[-1]["tool_call_id"] = "mutated"
        rest[-1]["outcome"] = "ok"
        args["changed"] = True

    def observe(name, args, *rest):
        identity = current_tool_identity()
        seen.append(
            (identity.tool_call_id, identity.outcome, dict(args), dict(rest[-1]))
        )
        with pytest.raises(FrozenInstanceError):
            identity.tool_call_id = "forged"

    callbacks.register_callback(phase, mutate)
    callbacks.register_callback(phase, observe)
    context = {"tool_call_id": "original", "outcome": "blocked"}
    args = {}
    if phase == "pre_tool_call":
        await callbacks.on_pre_tool_call("operation", args, context)
    else:
        await callbacks.on_post_tool_call("operation", args, "result", 0, context)
    assert seen == [
        (
            "original",
            "blocked",
            {"changed": True},
            {"tool_call_id": "mutated", "outcome": "ok"},
        )
    ]
    assert current_tool_identity() is None


async def test_nested_and_parallel_dispatch_restore_enclosing_identity():
    seen = []

    async def observe(name, args, context):
        identity = current_tool_identity()
        if name == "outer":
            await callbacks.on_pre_tool_call("inner", {}, {"tool_call_id": "inner"})
            assert current_tool_identity() is identity
        await asyncio.sleep(0)
        seen.append((name, current_tool_identity().tool_call_id))

    callbacks.register_callback("pre_tool_call", observe)
    await asyncio.gather(
        *(
            callbacks.on_pre_tool_call(name, {}, {"tool_call_id": name})
            for name in ("outer", "parallel")
        )
    )
    assert sorted(seen) == [
        ("inner", "inner"),
        ("outer", "outer"),
        ("parallel", "parallel"),
    ]
    assert current_tool_identity() is None


async def test_cancel_restores_scope_and_missing_id_is_not_outside_scope():
    entered = asyncio.Event()

    async def wait(*args):
        assert current_tool_identity().tool_call_id == "cancelled"
        entered.set()
        await asyncio.Event().wait()

    callbacks.register_callback("pre_tool_call", wait)
    task = asyncio.create_task(
        callbacks.on_pre_tool_call("operation", {}, {"tool_call_id": "cancelled"})
    )
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel("original cancellation")
    with pytest.raises(asyncio.CancelledError, match="original cancellation"):
        await task
    assert current_tool_identity() is None
    with tool_call_identity({"tool_call_id": None}):
        assert current_tool_identity() is not None
        assert current_tool_identity().tool_call_id is None
    assert current_tool_identity() is None
