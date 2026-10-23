"""The true-exception policy: what may reach ``errors.log``."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from code_puppy import error_policy
from code_puppy.error_policy import (
    NEVER_REPORT,
    ExpectedFlow,
    is_expected,
    never_report,
    should_report,
)
from tests.error_ast_support import module_imports


class _CancelSub(asyncio.CancelledError):
    pass


@pytest.mark.parametrize("exc_type", NEVER_REPORT)
def test_never_report_types_and_subclasses(exc_type):
    assert should_report(exc_type()) is False
    assert never_report(exc_type()) is True
    assert is_expected(exc_type()) is False  # suppressed, but not "expected"
    assert should_report(_CancelSub()) is False
    assert never_report(_CancelSub()) is True


@pytest.mark.parametrize(
    ("exc", "kwargs"),
    [(ExpectedFlow(), {}), (ValueError(), {"expected": True})],
)
def test_expected_flow_is_expected_and_not_reported(exc, kwargs):
    assert is_expected(exc, **kwargs) is True
    assert should_report(exc, **kwargs) is False


def test_plain_error_is_reported_and_not_expected():
    assert should_report(ValueError("x")) is True
    assert is_expected(ValueError("x")) is False


def test_chain_context_is_ignored():
    try:
        try:
            raise KeyboardInterrupt
        except KeyboardInterrupt as inner:
            raise ValueError("wrapped") from inner
    except ValueError as err:
        assert should_report(err) is True


@pytest.mark.parametrize(
    ("group", "reported"),
    [
        (
            BaseExceptionGroup("g", [KeyboardInterrupt(), asyncio.CancelledError()]),
            False,
        ),
        (BaseExceptionGroup("g", [KeyboardInterrupt(), ValueError()]), True),
        (
            BaseExceptionGroup(
                "g", [BaseExceptionGroup("n", [SystemExit()]), _CancelSub()]
            ),
            False,
        ),
        (ExceptionGroup("g", [ExpectedFlow(), ExpectedFlow()]), False),
        (ExceptionGroup("g", [ValueError()]), True),
    ],
)
def test_groups_judged_by_leaves(group, reported):
    assert should_report(group) is reported


def test_group_context_not_walked():
    try:
        try:
            raise ValueError("ctx")
        except ValueError:
            raise BaseExceptionGroup("g", [KeyboardInterrupt()])
    except BaseExceptionGroup as grp:
        assert should_report(grp) is False


def test_never_report_distinguishes_control_flow_from_expected_flow():
    assert never_report(KeyboardInterrupt()) is True
    assert never_report(ExpectedFlow()) is False
    assert should_report(KeyboardInterrupt(), expected=True) is False


def test_module_is_stdlib_only():
    imported = module_imports(Path(error_policy.__file__))
    assert {name.split(".")[0] for name in imported} <= {
        "__future__",
        "asyncio",
        "typing",
    }
