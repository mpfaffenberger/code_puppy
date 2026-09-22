"""Tests for how the model-type dispatcher reports plugin handler failures.

The dispatcher in ``ModelFactory.get_model`` is the single place that
converts a plugin model-type handler failure into a graceful ``None``.
Two properties matter and are easy to regress:

1. It logs with ``exc_info`` so a traceback reaches the log. Without it
   the only diagnostic is ``str(e)``, which for an ``AttributeError`` or
   ``TypeError`` carries no file or line at all.
2. It still returns ``None`` rather than propagating, so the user gets a
   fallback model instead of a crash.
"""

import logging

import pytest

from code_puppy.model_factory import ModelFactory


@pytest.fixture
def exploding_handler(monkeypatch):
    """Register a model type whose handler always raises."""

    def handler(model_name, model_config, config):
        raise AttributeError("property 'provider' has no setter")

    monkeypatch.setattr(
        "code_puppy.model_factory.callbacks.on_register_model_types",
        lambda: [[{"type": "exploding", "handler": handler}]],
    )
    return handler


@pytest.fixture
def exploding_config():
    return {"boom": {"name": "boom", "type": "exploding"}}


def test_handler_failure_returns_none_for_graceful_fallback(
    exploding_handler, exploding_config
):
    """A handler blowing up must not crash model selection."""
    assert ModelFactory.get_model("boom", exploding_config) is None


def test_handler_failure_logs_a_traceback(exploding_handler, exploding_config, caplog):
    """Regression: the log record must carry exc_info.

    Without this the underlying bug is unplaceable from logs alone.
    """
    with caplog.at_level(logging.ERROR, logger="code_puppy.model_factory"):
        ModelFactory.get_model("boom", exploding_config)

    records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert records, "handler failure should log at ERROR"
    assert records[0].exc_info is not None, "log record must include a traceback"
    assert "AttributeError" in caplog.text


def test_handler_failure_log_identifies_the_model_and_type(
    exploding_handler, exploding_config, caplog
):
    """The message must name the model, not just the type.

    One type can back many models; 'type exploding failed' alone does not
    say which /model selection broke.
    """
    with caplog.at_level(logging.ERROR, logger="code_puppy.model_factory"):
        ModelFactory.get_model("boom", exploding_config)

    assert "boom" in caplog.text
    assert "exploding" in caplog.text
