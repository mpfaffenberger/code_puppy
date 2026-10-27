"""Regression tests for forced ``tool_choice`` support on Claude 5.5 models.

``claude-sonnet-5-5`` and ``claude-opus-5-5`` reject forced ``tool_choice``
(``any``/``tool``) with ``[HTTP 400] tool_choice: type "tool" and "any" are not
supported for this model.`` pydantic-ai's own profile table now knows both, so
Code Puppy no longer patches the gap. These tests keep us honest if a future
upgrade regresses that table.
"""

import os
from unittest.mock import patch

import pytest

from code_puppy.model_factory import ModelFactory


@pytest.mark.parametrize(
    ("model_id", "supported"),
    [
        ("claude-sonnet-5-5", False),
        ("claude-opus-5-5", False),
        ("claude-sonnet-5", True),
        ("claude-opus-5", True),
    ],
)
@pytest.mark.parametrize("model_type", ["anthropic", "custom_anthropic"])
def test_get_model_reports_upstream_forced_tool_choice_support(
    model_id, supported, model_type
):
    config = {"alias": {"type": model_type, "name": model_id}}
    if model_type == "custom_anthropic":
        config["alias"]["custom_endpoint"] = {
            "url": "https://proxy.example.com",
            "api_key": "test-key",
        }
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        model = ModelFactory.get_model("alias", config)

    assert model.profile.get("supports_forced_tool_choice") is supported
